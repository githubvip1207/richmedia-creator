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
from core import jobs
from core.costing import calculate, consume_quote
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
        with patch('core.costing.estimate',side_effect=AssertionError('Unexpected calculation')):
            self.assertEqual(consume_quote(spec,quote)[3],quote['result'])
        self.assertNotIn('quote_hash',quote)
        self.assertNotIn('catalog_hash',quote)

    def test_reject_changed_billing_inputs(self):
        spec=image();quote=calculate(spec)
        for update in ({'parameters':{'size':'2K','ratio':'1:1'}},
                       {'provider':'byteplus'}, {'estimate_context':{'output_dimensions':[854,480]}}):
            changed=copy.deepcopy(spec);changed.update(update)
            with self.assertRaisesRegex(ValueError,'differs'):
                consume_quote(changed,quote)

    def test_reject_expired_quote(self):
        quote=calculate(image());quote['calculation']['created_at']='2020-01-01T00:00:00+00:00'
        with self.assertRaisesRegex(ValueError,'expired'):
            consume_quote(image(),quote)

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
        cost = self.root/'volcengine/cost.json'
        inputs = {'provider': 'volcengine', 'model': 'seedream-5.0-flash',
                  'operation': 'text-to-image', 'size': '1K'}
        result = run('media.py', 'estimate-cost', '--workdir', self.root, input_data=inputs)
        data = jobs.read(cost)
        self.assertEqual(json.loads(result.stdout), data)
        self.assertEqual(data['input'], inputs)
        self.assertEqual(data['result']['currency'], 'CNY')
        self.assertNotIn('prompt', data['input'])
        # The fixed output filename is updated when inputs change.
        inputs['size'] = '2K'
        run('media.py', 'estimate-cost', '--workdir', self.root, input_data=inputs)
        self.assertEqual(jobs.read(cost)['input']['size'], '2K')
        inputs['size'] = '1K'
        run('media.py', 'estimate-cost', '--workdir', self.root, input_data=inputs)
        inputs['provider'] = 'byteplus'
        run('media.py', 'estimate-cost', '--workdir', self.root, input_data=inputs)
        self.assertEqual(jobs.read(self.root/'byteplus/cost.json')['result']['currency'], 'USD')

    def test_cli_multiple_input_videos_and_unknown_floor(self):
        args = [sys.executable, str(ROOT/'scripts/media.py'), 'estimate-cost', '--workdir', str(self.root)]
        import os
        tool = self.root/'ffprobe'
        tool.write_text('#!'+sys.executable+'\nimport json,sys\n' +
                        'print(json.dumps({"streams":[{"codec_type":"video","width":1280,"height":720,"duration":3 if sys.argv[-1].endswith("a.mp4") else 5}]}))\n')
        tool.chmod(0o700)
        for name in ('a.mp4', 'b.mp4'):
            (self.root/name).touch()
        inputs = {'provider': 'volcengine', 'model': 'seedance-2.0', 'operation': 'reference-to-video', 'mode': 'edit',
                  'resolution': '480p', 'ratio': '16:9', 'duration': 4,
                  'assets': [{'kind': 'video', 'source': str(self.root/name)} for name in ('a.mp4','b.mp4')]}
        result = subprocess.run(args, cwd=self.root, capture_output=True, text=True, input=json.dumps(inputs),
                                env={**os.environ, 'PATH': str(self.root)+os.pathsep+os.environ.get('PATH','')})
        self.assertEqual(result.returncode, 0, result.stderr)
        data = jobs.read(self.root/'volcengine/cost.json')
        self.assertEqual(data['input'], inputs)
        self.assertEqual(data['calculation']['input_video_seconds'], [3.0, 5.0])
        self.assertEqual(json.loads(result.stdout), data)
        self.assertEqual(data['calculation']['total_input_video_seconds'], 8)
        self.assertEqual(data['result']['status'], 'lower_bound')
        self.assertIsNone(list(data['result']['amount'].values())[1])

    def test_stdin_invalid_json_creates_no_cost_file(self):
        args = [sys.executable, str(ROOT/'scripts/media.py'), 'estimate-cost', '--workdir', str(self.root)]
        for raw in ['', '{', '[]', '{"provider":"volcengine","model":"seedream-5.0-flash","operation":"text-to-image","size":"1K","input_images":NaN}',
                    '{"provider":"volcengine","model":"seedream-5.0-flash","operation":"text-to-image","size":"1K","typo":1}']:
            result = subprocess.run(args, cwd=self.root, capture_output=True, text=True, input=raw)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((self.root/'volcengine/cost.json').exists())


if __name__ == '__main__':
    unittest.main()
