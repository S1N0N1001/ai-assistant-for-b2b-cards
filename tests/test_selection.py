import copy
import json
from pathlib import Path
import unittest
from service.domain import ServiceError, parse_product
from service.selection import catalogue, generate, validate_plan

ROOT = Path(__file__).resolve().parent.parent


class FakeClient:
    model = 'test-double-not-live'

    def __init__(self, replies):
        self.replies = iter(replies)
        self.calls = 0

    def generate(self, system, user):
        self.calls += 1
        return next(self.replies)


def fixture(number=1):
    return parse_product((ROOT / f'examples/inputs/product_0{number}.json').read_text(encoding='utf-8'))


def plan_for(product):
    source = catalogue(product)
    return {'title_id': 't0', 'spec_order': list(reversed(source['specs'])), 'query_ids': list(source['queries'])[:3]}


class SelectionTests(unittest.TestCase):
    def test_both_products_preserve_conditions_and_respond_to_selection(self):
        for number in (1, 2):
            with self.subTest(number=number):
                product, missing = fixture(number)
                plan = plan_for(product)
                result = generate(product, missing, FakeClient([json.dumps(plan)]))
                self.assertEqual(result['status'], 'needs_review')
                self.assertEqual(result['metadata']['assembly_mode'], 'llm_selection_source_template')
                self.assertEqual(result['metadata']['prompt_version'], '2.0')
                self.assertEqual(result['metadata']['selection_attempts'], 1)
                self.assertEqual(result['characteristics'][0]['name'], list(product['specs'])[-1])
                self.assertIn(product['description'], result['seo_description'])
                self.assertTrue(800 <= len(result['seo_description']) <= 1200)
                self.assertEqual(result['selection_plan'], plan)

    def test_malicious_and_incomplete_plans_rejected(self):
        product, _ = fixture()
        source = catalogue(product)
        valid = plan_for(product)
        cases = [[], None, {'title_id': 't0'}, {**valid, 'seo_description': 'Выдумка'},
                 {**valid, 'title_id': 'Материал корпуса: сталь'},
                 {**valid, 'spec_order': ['s0']}, {**valid, 'spec_order': ['s0'] * 4},
                 {**valid, 'query_ids': ['q0', 'q1', 'fake']},
                 {**valid, 'query_ids': ['q0', 'q0', 'q1']},
                 {**valid, 'query_ids': [[], 'q1', 'q2']}]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ServiceError):
                validate_plan(case, source)

    def test_bad_then_valid_plan_repairs_once(self):
        product, missing = fixture()
        client = FakeClient(['not json', json.dumps(plan_for(product))])
        result = generate(product, missing, client)
        self.assertEqual(client.calls, 2)
        self.assertEqual(result['metadata']['selection_attempts'], 2)

    def test_no_silent_template_fallback_for_invalid_model_plan(self):
        product, missing = fixture()
        client = FakeClient(['{}', '{}'])
        with self.assertRaises(ServiceError):
            generate(product, missing, client)
        self.assertEqual(client.calls, 2)

    def test_empty_specs_and_missing_manufacturer(self):
        product, missing = parse_product(json.dumps({'name': 'Прибор', 'description': 'Описание.'}))
        plan = plan_for(product)
        result = generate(product, missing, FakeClient([json.dumps(plan)]))
        self.assertEqual(result['characteristics'], [])
        self.assertIn('manufacturer', result['missing_fields'])
        self.assertEqual(result['status'], 'needs_revision')

    def test_input_digest_changes_with_source(self):
        product, missing = fixture()
        first = generate(product, missing, FakeClient([json.dumps(plan_for(product))]))
        changed = copy.deepcopy(product)
        changed['description'] += ' Уточнение от пользователя.'
        second = generate(changed, missing, FakeClient([json.dumps(plan_for(changed))]))
        self.assertNotEqual(first['metadata']['input_sha256'], second['metadata']['input_sha256'])
