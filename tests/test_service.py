import io
import json
import os
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from service.client import Client
from service.domain import ServiceError, parse_product, check_draft
from service.generate import generate_free as generate
from service.__main__ import main


def product():
    return parse_product(json.dumps({'name': 'Прибор', 'specs': {'давление': '1 МПа', 'материал': None}}))


def valid_draft():
    return {'seo_title': 'Прибор', 'seo_description': 'Описание прибора. ' * 55,
            'search_queries': ['прибор', 'прибор давление', 'измеритель давления'],
            'commercial_block': 'Для измерения давления.', 'warnings': [], 'conflicts': []}


class FakeClient:
    model = 'test-double'

    def __init__(self, replies):
        self.replies = iter(replies)
        self.calls = 0
        self.requests = []

    def generate(self, system, user):
        self.calls += 1
        self.requests.append(user)
        return next(self.replies)


class DomainTests(unittest.TestCase):
    def test_invalid_inputs(self):
        for text in ('', '[]', '{}', '{', '{"name": 1}', '{"name":"A","specs":{"x":3}}'):
            with self.subTest(text=text), self.assertRaises(ServiceError):
                parse_product(text)

    def test_missing_and_sources(self):
        p, missing = product()
        self.assertIn('manufacturer', missing)
        self.assertIn('specs.материал', missing)
        result = generate(p, missing, FakeClient([json.dumps(valid_draft())]))
        self.assertEqual(result['characteristics'][1]['value'], 'данных нет')
        self.assertEqual(result['characteristics'][0]['source'], 'specs.давление')
        self.assertEqual(result['status'], 'needs_review')

    def test_numeric_hallucination_and_lengths(self):
        p, _ = product()
        draft = valid_draft()
        draft['seo_title'] = 'x' * 71
        draft['seo_description'] = 'Новый диапазон 999 МПа'
        self.assertEqual(len(check_draft(draft, p)), 3)

    def test_observed_unsupported_claims_rejected(self):
        p, _ = product()
        for claim in ('Компактность установки.', 'Для стандартных трубопроводов.',
                      'Защита от пыли.', 'Для отопления.', 'Цифровая панель.',
                      'Калибровка без оборудования.', 'Простоту монтажа обеспечивает корпус.',
                      'Защита от крупных частиц.', 'Работает без дополнительных модификаций.'):
            draft = valid_draft()
            draft['commercial_block'] = claim
            with self.subTest(claim=claim):
                self.assertTrue(any('Неподтверждённая категория' in issue for issue in check_draft(draft, p)))

    def test_explicit_dust_claim_in_source_allowed(self):
        p, _ = product()
        p['description'] = 'В исходном описании прямо указана защита от пыли.'
        draft = valid_draft()
        draft['commercial_block'] = 'Защита от пыли.'
        self.assertFalse(check_draft(draft, p))

    def test_repair_and_bounded_failure(self):
        p, missing = product()
        client = FakeClient(['not json', json.dumps(valid_draft())])
        self.assertEqual(generate(p, missing, client)['status'], 'needs_review')
        self.assertEqual(client.calls, 2)
        with self.assertRaises(ServiceError):
            generate(p, missing, FakeClient(['[]', '[]']))

    def test_repair_receives_previous_draft_and_measured_length(self):
        p, missing = product()
        draft = valid_draft()
        draft['seo_description'] = 'Короткое описание.'
        client = FakeClient([json.dumps(draft), json.dumps(valid_draft())])
        result = generate(p, missing, client)
        self.assertEqual(result['status'], 'needs_review')
        self.assertIn('Короткое описание.', client.requests[1])
        self.assertIn(f'сейчас {len(draft["seo_description"])} символов', client.requests[1])

    def test_unresolved_length_and_conflict(self):
        p, missing = product()
        draft = valid_draft()
        draft['seo_description'] = 'Коротко'
        draft['conflicts'] = ['Нужно уточнение источника']
        result = generate(p, missing, FakeClient([json.dumps(draft)] * 2))
        self.assertEqual(result['status'], 'needs_revision')
        self.assertFalse(result['validation']['automated_checks_passed'])

    def test_wrong_query_type_does_not_reach_export(self):
        p, missing = product()
        draft = valid_draft()
        draft['search_queries'] = 9
        with self.assertRaises(ServiceError):
            generate(p, missing, FakeClient([json.dumps(draft)] * 2))

    def test_cli_writes_both_formats_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'input.json'
            target = Path(directory) / 'card.json'
            source.write_text(json.dumps({'name': 'Прибор', 'specs': {'давление': '1 МПа'}, 'description': 'Предназначен для измерения давления. ' * 7}), encoding='utf-8')
            with patch('sys.argv', ['service', str(source), '--output', str(target)]), patch(
                'service.__main__.Client', return_value=FakeClient([json.dumps({'title_id': 't0', 'spec_order': ['s0'], 'query_ids': ['q0', 'q1', 'q2']})])
            ), patch('sys.stdout', new_callable=io.StringIO), patch('sys.stderr', new_callable=io.StringIO):
                self.assertEqual(main(), 0)
                self.assertEqual(json.loads(target.read_text(encoding='utf-8'))['status'], 'needs_review')
                self.assertIn('## SEO-описание', target.with_suffix('.md').read_text(encoding='utf-8'))
                original = target.read_bytes()
                self.assertEqual(main(), 2)
                self.assertEqual(target.read_bytes(), original)


@patch.dict(os.environ, {'GROQ_API_KEY': 'test-secret', 'GROQ_MODEL': 'test-model'})
class ClientTests(unittest.TestCase):
    def test_missing_configuration(self):
        with patch.dict(os.environ, {'GROQ_API_KEY': ''}), self.assertRaises(ServiceError):
            Client()

    @patch('service.client.time.sleep')
    @patch('service.client.urlopen')
    def test_auth_does_not_retry_or_leak(self, open_mock, sleep):
        open_mock.side_effect = HTTPError('url', 401, 'test-secret', {}, None)
        with self.assertRaises(ServiceError) as caught:
            Client().generate('system', 'user')
        self.assertNotIn('test-secret', str(caught.exception))
        self.assertEqual(open_mock.call_count, 1)

    @patch('service.client.urlopen')
    def test_forbidden_diagnostic_redacts_key(self, open_mock):
        body = json.dumps({'error': {'message': 'Model access denied test-secret gsk_example123'}}).encode()
        open_mock.side_effect = HTTPError('url', 403, '', {}, io.BytesIO(body))
        with self.assertRaises(ServiceError) as caught:
            Client().generate('s', 'u')
        message = str(caught.exception)
        self.assertIn('HTTP 403', message)
        self.assertIn('Model access denied', message)
        self.assertNotIn('test-secret', message)
        self.assertNotIn('gsk_example123', message)
        self.assertEqual(open_mock.call_count, 1)

    @patch('service.client.urlopen')
    def test_forbidden_html_not_exposed(self, open_mock):
        open_mock.side_effect = HTTPError('url', 403, '', {}, io.BytesIO(b'<html>private proxy page</html>'))
        with self.assertRaises(ServiceError) as caught:
            Client().generate('s', 'u')
        self.assertIn('сетевого фильтра', str(caught.exception))
        self.assertNotIn('private proxy', str(caught.exception))

    @patch('service.client.time.sleep')
    @patch('service.client.urlopen')
    def test_rate_limit_retries_once(self, open_mock, sleep):
        open_mock.side_effect = HTTPError('url', 429, '', {}, None)
        with self.assertRaises(ServiceError):
            Client().generate('system', 'user')
        self.assertEqual(open_mock.call_count, 2)

    @patch('service.client.time.sleep')
    @patch('service.client.urlopen')
    def test_network_retries_once(self, open_mock, sleep):
        open_mock.side_effect = URLError('secret in network error')
        with self.assertRaises(ServiceError) as caught:
            Client().generate('system', 'user')
        self.assertNotIn('secret', str(caught.exception))
        self.assertEqual(open_mock.call_count, 2)

    @patch('service.client.urlopen')
    def test_successful_protocol(self, open_mock):
        response = open_mock.return_value.__enter__.return_value
        response.read.return_value = json.dumps({'choices': [{'finish_reason': 'stop', 'message': {'content': '{}'}}]}).encode()
        self.assertEqual(Client().generate('s', 'u'), '{}')
        request = open_mock.call_args.args[0]
        body = json.loads(request.data)
        self.assertEqual(body['messages'][0], {'role': 'system', 'content': 's'})
        self.assertEqual(body['messages'][1]['content'], 'u')
        self.assertEqual(body['response_format'], {'type': 'json_object'})
        self.assertEqual(request.full_url, 'https://api.groq.com/openai/v1/chat/completions')
        self.assertEqual(request.get_header('Authorization'), 'Bearer test-secret')

    @patch('service.client.urlopen')
    def test_truncated_response_rejected(self, open_mock):
        response = open_mock.return_value.__enter__.return_value
        response.read.return_value = json.dumps({'choices': [{'finish_reason': 'length', 'message': {'content': '{}'}}]}).encode()
        with self.assertRaises(ServiceError):
            Client().generate('s', 'u')

    @patch('service.client.urlopen')
    def test_empty_choices_rejected(self, open_mock):
        response = open_mock.return_value.__enter__.return_value
        response.read.return_value = b'{"choices":[]}'
        with self.assertRaises(ServiceError):
            Client().generate('s', 'u')


if __name__ == '__main__':
    unittest.main()
