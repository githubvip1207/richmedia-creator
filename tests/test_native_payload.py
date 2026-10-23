"""Native image requests preserve the approved API body through submission."""
import copy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from commands import submit as submit_command, download as download_command
from core.request import compile_request
from cost_fixture import calculate, save_with_cost
from core import submission_store as store
from providers import volcengine
from config_fixture import config_fixture


class NativePayload(unittest.TestCase):
    def setUp(self):
        self.spec = {'provider': 'volcengine', 'operation': 'text-to-image',
                     'original_prompt': '熊猫', 'payload': {
                         'model': 'doubao-seedream-5-0-flash-260915',
                         'prompt': '熊猫。构图比例偏好：1:1。', 'size': '1K',
                         'output_format': 'png', 'response_format': 'url',
                         'watermark': False, 'background': 'opaque',
                         'layer_decomposition': False}}

    def test_submission_preserves_exact_payload_and_records_response(self):
        before = copy.deepcopy(self.spec)
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            (work/'volcengine').mkdir()
            save_with_cost(self.spec, work)
            response = {'data': [{'url': 'https://example.com/image.png'}]}
            with config_fixture({'VOLCENGINE_API_KEY': 'fixture-only'}), \
                    patch.object(volcengine, 'request', return_value=response) as post:
                submit_command.submit(work, self.spec, 'TEST CONFIRMATION')
            post.assert_called_once_with('POST', '/images/generations', self.spec['payload'])
            self.assertEqual(store.read(work/'submit-001.json')['response'], response)
            self.assertEqual({k:v for k,v in store.read(work/'submit-001.json').items() if k != 'execution'}, {**before, 'response': response})
            self.assertEqual(store.read(work/'submit-001.json')['execution']['compiled']['payload_template'], self.spec['payload'])
        self.assertEqual(self.spec, before)

    def test_missing_required_settings_are_rejected(self):
        self.spec['payload'] = {k:self.spec['payload'][k] for k in ('model','prompt')}
        with self.assertRaisesRegex(ValueError, 'size'):
            compile_request(self.spec)

    def test_rejects_invalid_payloads(self):
        for fields in ({'n': 2}, {'size': '1024x768'}, {'layer_decomposition': True},
                       {'background': 'transparent'}, {'model': 'seedream-5.0-flash'},
                       {'optimize_prompt_options': {'mode': 'fast'}}):
            with self.subTest(fields=fields):
                spec = copy.deepcopy(self.spec)
                spec['payload'].update(fields)
                with self.assertRaises(ValueError):
                    compile_request(spec)

    def test_cost_mismatch_never_posts(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            (work/'volcengine').mkdir()
            save_with_cost(self.spec, work)
            self.spec['payload']['size'] = '2K'
            with patch.object(volcengine, 'request') as post:
                with self.assertRaises(ValueError):
                    submit_command.submit(work, self.spec, 'TEST CONFIRMATION')
                post.assert_not_called()
            self.assertFalse((work/'submit-001.json').exists())

    def test_record_number_uses_largest_existing_sequence(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            self.assertEqual(store.next_submit_record(work).name, 'submit-001.json')
            store.write(work/'submit-001.json', {})
            store.write(work/'submit-009.json', {})
            store.write(work/'submit-other.json', {})
            self.assertEqual(store.next_submit_record(work).name, 'submit-010.json')
            store.write(work/'submit-999.json', {})
            self.assertEqual(store.next_submit_record(work).name, 'submit-1000.json')

    def test_confirmed_repeat_numbers_records_and_preserves_downloads(self):
        import base64
        from test_runtime import png
        response = {'data': [{'b64_json': base64.b64encode(png()).decode()}]}
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            (work/'volcengine').mkdir()
            save_with_cost(self.spec, work)
            with config_fixture({'VOLCENGINE_API_KEY': 'fixture-only'}), \
                    patch.object(volcengine, 'request', return_value=response) as post:
                submit_command.submit(work, self.spec, 'TEST FIRST CONFIRMATION')
                first = download_command.download(work)
                first_path = Path(first['files'][0]['path'])
                first_bytes = first_path.read_bytes()
                with self.assertRaises(ValueError):
                    submit_command.submit(work, self.spec, '')
                self.assertEqual(post.call_count, 1)
                submit_command.submit(work, self.spec, 'TEST SECOND CONFIRMATION')
                second = download_command.download(work)
                self.assertEqual(post.call_count, 2)
            self.assertEqual(store.read(work/'submit-001.json')['response'], response)
            self.assertEqual(store.read(work/'submit-002.json')['response'], response)
            self.assertEqual(store.read(work/'submit-001.json')['execution']['approval']['text'], 'TEST FIRST CONFIRMATION')
            self.assertTrue(store.read(work/'submit-001.json')['result']['files'])
            self.assertIn('output-002', second['files'][0]['path'])
            self.assertEqual(first_path.read_bytes(), first_bytes)
            self.assertEqual(download_command.download(work/'submit-001.json')['files'][0]['path'], str(first_path))
            for old_name in ('job.json', 'response.json', 'result.json', 'submit-001-job.json', 'submit-001-result.json'):
                self.assertFalse((work/old_name).exists())
