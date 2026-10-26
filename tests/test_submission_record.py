"""提交记录在轮询和下载过程中始终保留完整信息。"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from commands import submit as submit_command, status as status_command, deliver as download_command
from core import submission_store as store
from cost_fixture import save_with_cost
from providers.volcengine import client as volcengine
from test_runtime import video


class SubmissionRecord(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)
        spec = video()
        from cost_fixture import compile_request
        self.spec = save_with_cost(spec, self.work)
        self.record = self.work/'submit-001.json'
        store.write(self.record, {**self.spec, 'response': {'id': 'task-fixture'},
                                 'execution': {'state': 'queued', 'task_id': 'task-fixture',
                                               'compiled': compile_request(spec)}})

    def test_polling_keeps_post_response_and_each_get_then_downloads_from_record(self):
        running = {'id':'task-fixture','status':'running'}
        success = {'id':'task-fixture','status':'succeeded',
                   'content':{'video_url':'https://example.com/video.mp4'}}
        with patch.object(volcengine, 'status', side_effect=[running, success]), patch.object(status_command.time, 'sleep'):
            state = status_command.status(self.record, wait=45)
        self.assertEqual(state['state'], 'succeeded')
        record = store.read(self.record)
        self.assertEqual(record['response'], {'id':'task-fixture'})
        self.assertEqual([q['response'] for q in record['queries']], [running, success])
        self.assertTrue(all(q['request']['method'] == 'GET' for q in record['queries']))
        def download(url, path):
            path.write_bytes(b'\x00\x00\x00\x18ftypisom' + bytes(20))
        with patch('core.download.download_url', side_effect=download) as get, \
                patch('core.media_validate.video_metadata', return_value={'width':1280,'height':720,'duration':4,'has_audio':False}):
            result = download_command._download(self.record)
            result = download_command._download(self.record)
            get.assert_called_once()
        self.assertTrue(Path(result['files'][0]['path']).is_file())
        record = store.read(self.record)
        self.assertTrue(record['execution']['download_complete'])
        self.assertEqual(record['result'], result)
        for name in ('job.json','response.json','result.json'):
            self.assertFalse((self.work/name).exists())

    def test_failed_query_is_retained_without_losing_original_response(self):
        with patch.object(volcengine, 'status', side_effect=volcengine.ProviderError('fixture timeout')):
            with self.assertRaises(volcengine.ProviderError):
                status_command.status(self.record)
        record = store.read(self.record)
        self.assertEqual(record['response'], {'id':'task-fixture'})
        self.assertIsNone(record['queries'][0]['response'])
        self.assertIn('fixture timeout', record['queries'][0]['error'])
        with patch.object(volcengine, 'request') as post:
            with self.assertRaises(ValueError):
                submit_command.submit(self.work, self.spec, 'TEST NEW CONFIRMATION')
            post.assert_not_called()
