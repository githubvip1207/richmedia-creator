"""Independent quotes, plan consumption and offline CLI integration."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from core import submission_store as store
from core.cost_quote import consume_quote
from cost_fixture import calculate, as_native
from core.request import ROOT


def image():
    return {'provider': 'volcengine', 'model': 'seedream-5.0-flash',
            'operation': 'text-to-image', 'prompt': 'A red hula hoop',
            'parameters': {'size': '1K', 'ratio': '1:1'}, 'assets': []}


class IndependentCosts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_consume_saved_cost_without_recalculation(self):
        spec=image();quote=calculate(spec)
        with patch('core.cost_quote.estimate',side_effect=AssertionError('Unexpected calculation')):
            self.assertEqual(consume_quote(as_native(spec),quote)[3],quote['result'])
        self.assertNotIn('quote_hash',quote)
        self.assertNotIn('catalog_hash',quote)

    def test_reject_changed_billing_inputs(self):
        spec=image();quote=calculate(spec)
        for update in ({'parameters':{'size':'2K','ratio':'1:1'}},
                       {'provider':'byteplus'}, {'estimate_context':{'output_dimensions':[854,480]}}):
            changed=copy.deepcopy(spec);changed.update(update)
            with self.assertRaisesRegex(ValueError,'differs'):
                consume_quote(as_native(changed),quote)

    def test_reject_expired_quote(self):
        quote=calculate(image());quote['calculation']['created_at']='2020-01-01T00:00:00+00:00'
        with self.assertRaisesRegex(ValueError,'expired'):
            consume_quote(as_native(image()),quote)

    def test_video_formula_and_missing_floor(self):
        spec = {'provider': 'volcengine', 'model': 'seedance-2.5', 'operation': 'text-to-video',
                'prompt': 'A panda rolls', 'parameters': {'ratio': '16:9', 'duration': 4},
                'optimizer': {'skill': 'sd25-pe', 'status': 'applied'}}
        quote = calculate(spec)
        import math
        expected = math.ceil(4*854*480*24/1024)
        self.assertEqual(quote['calculation']['tokens'], [expected, expected])
        rate = quote['calculation']['unit_price_per_million_tokens']
        self.assertEqual(list(quote['result']['amount'].values()), [round(expected*rate/1_000_000, 6)]*2)

    def test_cli_single_and_multiple_quotes(self):
        request = self.root/'request.json'
        request.write_text(json.dumps(image()))
        def run(script, *args, success=True, input_data=None):
            r = subprocess.run([sys.executable, str(ROOT/'scripts'/script), *map(str,args)],
                               cwd=self.root, capture_output=True, text=True,
                               input=json.dumps(input_data) if input_data is not None else None)
            if success:
                self.assertEqual(r.returncode, 0, r.stderr)
            return r
        cost = self.root/'volcengine-priceing.json'
        inputs = {'provider': 'volcengine', 'model': 'seedream-5.0-flash',
                  'operation': 'text-to-image', 'size': '1K'}
        result = run('main.py', 'estimate-cost', '--workdir', self.root, input_data=inputs)
        data = store.read(cost)
        self.assertEqual({k: json.loads(result.stdout)[k] for k in ('input','calculation','result')}, data)
        self.assertEqual(Path(json.loads(result.stdout)['quote']).resolve(), cost.resolve())
        self.assertEqual(data['input'], inputs)
        self.assertEqual(data['result']['currency'], 'CNY')
        self.assertNotIn('prompt', data['input'])
        # The fixed output filename is updated when inputs change.
        inputs['size'] = '2K'
        run('main.py', 'estimate-cost', '--workdir', self.root, input_data=inputs)
        self.assertEqual(store.read(cost)['input']['size'], '2K')
        inputs['size'] = '1K'
        run('main.py', 'estimate-cost', '--workdir', self.root, input_data=inputs)
        inputs['provider'] = 'byteplus'
        run('main.py', 'estimate-cost', '--workdir', self.root, input_data=inputs)
        self.assertEqual(store.read(self.root/'byteplus-priceing.json')['result']['currency'], 'USD')

    def test_cli_text_video_quotes_for_both_suppliers(self):
        args = [sys.executable, str(ROOT/'scripts/main.py'), 'estimate-cost', '--workdir', str(self.root)]
        for provider in ('volcengine', 'byteplus'):
            inputs = {'provider': provider, 'model': 'seedance-2.0', 'operation': 'text-to-video',
                      'resolution': '480p', 'ratio': '16:9', 'duration': 4}
            result = subprocess.run(args, cwd=self.root, capture_output=True, text=True, input=json.dumps(inputs))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['result']['status'], 'estimate')
            self.assertTrue((self.root/(provider + '-priceing.json')).exists())

    def test_stdin_invalid_json_creates_no_cost_file(self):
        args = [sys.executable, str(ROOT/'scripts/main.py'), 'estimate-cost', '--workdir', str(self.root)]
        for raw in ['', '{', '[]', '{"provider":"volcengine","model":"seedream-5.0-flash","operation":"text-to-image","size":"1K","input_images":NaN}',
                    '{"provider":"volcengine","model":"seedream-5.0-flash","operation":"text-to-image","size":"1K","typo":1}']:
            result = subprocess.run(args, cwd=self.root, capture_output=True, text=True, input=raw)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((self.root/'volcengine-priceing.json').exists())


if __name__ == '__main__':
    unittest.main()
