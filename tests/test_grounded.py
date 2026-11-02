import json
from pathlib import Path
import unittest
from service.domain import parse_product
from service.grounded import grounded_result

ROOT = Path(__file__).resolve().parent.parent


class GroundedTests(unittest.TestCase):
    def test_provided_products_preserve_sources_and_meet_lengths(self):
        for filename in ('product_01.json', 'product_02.json'):
            with self.subTest(filename=filename):
                product, missing = parse_product((ROOT / 'examples/inputs' / filename).read_text(encoding='utf-8'))
                result = grounded_result(product, missing, 'test-model')
                self.assertEqual(result['status'], 'needs_review')
                self.assertTrue(800 <= len(result['seo_description']) <= 1200)
                self.assertIn(product['description'], result['seo_description'])
                for key, value in product['specs'].items():
                    self.assertIn(f'{key}: {value}', result['seo_description'])
                self.assertEqual(result['metadata']['assembly_mode'], 'source_template')

    def test_large_source_remains_revision_instead_of_truncation(self):
        product, missing = parse_product(json.dumps({'name': 'A', 'description': 'Описание. ' * 200}))
        result = grounded_result(product, missing, 'test-model')
        self.assertEqual(result['status'], 'needs_revision')
        self.assertIn(product['description'], result['seo_description'])
