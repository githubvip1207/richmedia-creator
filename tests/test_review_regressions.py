"""Regression cases reproduced during the script audit; generation is always mocked."""
import copy
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from commands import submit, deliver as download, status
from core import submission_store as store
from core.assets import inspect_asset
from core.envfile import read_config
from core.request import compile_request
from cost_fixture import save_with_cost
from config_fixture import config_fixture
from providers import byteplus, volcengine
from test_native_byteplus import request
from test_runtime import png


class ReviewRegressions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)
        self.spec = request()
        save_with_cost(self.spec, self.work)

    def post(self, response):
        with config_fixture({'BYTEPLUS_API_KEY': 'fixture-key'}), patch.object(byteplus, 'request', return_value=response):
            return submit.submit(self.work, self.spec, 'TEST CONFIRMATION')

    def test_empty_or_missing_image_output_stays_unknown_and_cannot_be_reposted(self):
        for entry in ({}, {'url': ''}, {'url': 'http://example.com/out.png'}, None):
            with self.subTest(entry=entry), tempfile.TemporaryDirectory() as tmp:
                work = Path(tmp)
                save_with_cost(self.spec, work)
                with config_fixture({'BYTEPLUS_API_KEY': 'fixture-key'}), patch.object(byteplus, 'request', return_value={'data': [entry]}) as post:
                    with self.assertRaises(ValueError):
                        submit.submit(work, self.spec, 'TEST CONFIRMATION')
                    self.assertEqual(store.read(work/'submit-001.json')['execution']['state'], 'submission_unknown')
                    with self.assertRaises(ValueError):
                        submit.submit(work, self.spec, 'TEST CONFIRMATION')
                    post.assert_called_once()

    def test_unexpected_multiple_outputs_are_not_marked_successful(self):
        with self.assertRaisesRegex(ValueError, 'count'):
            self.post({'data': [{'url': 'https://example.com/a.png'}, {'url': 'https://example.com/b.png'}]})
        self.assertEqual(store.read(self.work/'submit-001.json')['execution']['state'], 'submission_unknown')

    def test_partial_errors_are_sanitized_before_every_write(self):
        response = {'data': [{'url': 'https://example.com/out.png'},
                            {'error': {'code': 'Rejected', 'message': self.spec['payload']['prompt'] + ' fixture-key https://private.example/x?token=sentinel'}}]}
        snapshots = []
        original = store.write
        def capture(path, value):
            snapshots.append(json.dumps(value, ensure_ascii=False))
            original(path, value)
        with patch.object(submit, 'write', side_effect=capture):
            state = self.post(response)
        self.assertEqual(state['state'], 'partial_failed')
        for snapshot in snapshots:
            self.assertNotIn('sentinel', snapshot)
            self.assertNotIn('fixture-key', snapshot)
        saved = store.read(state['submission'])
        self.assertEqual(saved['response']['data'][0]['url'], response['data'][0]['url'])
        self.assertEqual(saved['response']['data'][1]['error']['code'], 'Rejected')

    def test_truncated_png_and_wrong_exact_dimensions_cannot_complete_download(self):
        for data, size in ((b'\x89PNG\r\n\x1a\n', '1K'), (png()[:45], '1K'), (png(), '1024x1024')):
            with self.subTest(size=size, length=len(data)):
                record = {'response': {'data': [{'url': 'https://example.com/out.png'}]},
                          'execution': {'state': 'succeeded', 'compiled': compile_request(self.spec)}}
                record['execution']['compiled']['parameters']['size'] = size
                store.write(self.work/'submit-001.json', record)
                with patch.object(download, 'download_url', side_effect=lambda url, path: path.write_bytes(data)):
                    with self.assertRaisesRegex(ValueError, 'valid media'):
                        download._download(self.work/'submit-001.json')
                self.assertFalse(store.read(self.work/'submit-001.json')['execution']['download_complete'])

    def test_valid_image_can_be_decoded_and_reused_without_network(self):
        state = self.post({'data': [{'url': 'https://example.com/out.png'}]})
        with patch.object(download, 'download_url', side_effect=lambda url, path: path.write_bytes(png())) as get:
            result = download._download(state['submission'])
            download._download(state['submission'])
            get.assert_called_once()
        self.assertTrue(store.read(state['submission'])['execution']['download_complete'])
        self.assertEqual(Path(result['files'][0]['path']).read_bytes(), png())

    def test_local_rgba_image_reports_dimensions_and_alpha(self):
        path = self.work/'rgba.png'
        path.write_bytes(png())
        asset = inspect_asset({'kind': 'image', 'source': str(path), 'purpose': 'fixture'})
        self.assertEqual((asset['metadata']['width'], asset['metadata']['height']), (400, 400))
        self.assertTrue(asset['metadata']['has_alpha'])

    def test_env_quoted_values_support_comments_without_execution(self):
        path = self.work/'.env'
        path.write_text('VOLCENGINE_API_KEY="fixture#value" # comment\nBYTEPLUS_API_KEY=\'$(touch /invalid)\'\t# comment\nUSD_CNY=7.1\t# comment\n')
        values = read_config(self.work)
        self.assertEqual(values['VOLCENGINE_API_KEY'], 'fixture#value')
        self.assertEqual(values['BYTEPLUS_API_KEY'], '$(touch /invalid)')
        self.assertEqual(values['USD_CNY'], '7.1')

    def test_historical_video_query_errors_are_sanitized_before_persisting(self):
        record = {'execution': {'state': 'running', 'task_id': 'task',
                               'compiled': {'provider': 'volcengine', 'kind': 'video', 'prompt': 'private prompt'}},
                  'response': {'id': 'task'}}
        path = self.work/'submit-001.json'
        store.write(path, record)
        response = {'id': 'task', 'status': 'failed', 'error': {'message': 'private prompt https://private.example/x?token=sentinel'}}
        with patch.object(volcengine, 'status', return_value=response):
            status.status(path)
        self.assertNotIn('sentinel', path.read_text())
        self.assertNotIn('private prompt', store.read(path)['queries'][0]['response']['error']['message'])

    def test_provider_cannot_override_confirmed_png_format(self):
        record = {'response': {'data': [{'url': 'https://example.com/out.jpeg', 'output_format': 'jpeg'}]},
                  'execution': {'state': 'succeeded', 'compiled': compile_request(self.spec)}}
        path = self.work/'submit-001.json'
        store.write(path, record)
        with patch.object(download, 'download_url') as get:
            with self.assertRaisesRegex(ValueError, 'differs from confirmed format'):
                download._download(path)
            get.assert_not_called()
        self.assertFalse(store.read(path)['execution']['download_complete'])
