"""Submission records remain self-contained through polling and downloads."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from core import jobs
from core.costing import calculate
from providers import volcengine
from config_fixture import config_fixture
from test_media import video


class SubmissionRecord(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)
        (self.work/'volcengine').mkdir()
        self.spec = video()
        jobs.write(self.work/'volcengine/cost.json', calculate(self.spec))
        with config_fixture({'VOLCENGINE_API_KEY':'fixture-only'}), \
                patch('core.preflight.skill_status', return_value={'status':'ok'}), \
                patch.object(volcengine, 'request', return_value={'id':'task-fixture'}):
            state = jobs.submit(self.work, self.spec, 'TEST CONFIRMATION')
        self.record = Path(state['submission'])

    def test_polling_keeps_post_response_and_each_get_then_downloads_from_record(self):
        running = {'id':'task-fixture','status':'running'}
        success = {'id':'task-fixture','status':'succeeded',
                   'content':{'video_url':'https://example.com/video.mp4'}}
        with patch.object(volcengine, 'status', side_effect=[running, success]), patch.object(jobs.time, 'sleep'):
            state = jobs.status(self.record, wait=45)
        self.assertEqual(state['state'], 'succeeded')
        record = jobs.read(self.record)
        self.assertEqual(record['response'], {'id':'task-fixture'})
        self.assertEqual([q['response'] for q in record['queries']], [running, success])
        self.assertTrue(all(q['request']['method'] == 'GET' for q in record['queries']))
        def download(url, path):
            path.write_bytes(b'\x00\x00\x00\x18ftypisom' + bytes(20))
        with patch.object(jobs, 'download_url', side_effect=download) as get:
            result = jobs.download(self.record)
            result = jobs.download(self.record)
            get.assert_called_once()
        self.assertTrue(Path(result['files'][0]['path']).is_file())
        record = jobs.read(self.record)
        self.assertTrue(record['execution']['download_complete'])
        self.assertEqual(record['result'], result)
        for name in ('job.json','response.json','result.json'):
            self.assertFalse((self.work/name).exists())

    def test_failed_query_is_retained_without_losing_original_response(self):
        with patch.object(volcengine, 'status', side_effect=volcengine.ProviderError('fixture timeout')):
            with self.assertRaises(volcengine.ProviderError):
                jobs.status(self.record)
        record = jobs.read(self.record)
        self.assertEqual(record['response'], {'id':'task-fixture'})
        self.assertIsNone(record['queries'][0]['response'])
        self.assertIn('fixture timeout', record['queries'][0]['error'])
        with patch.object(volcengine, 'request') as post:
            with self.assertRaises(ValueError):
                jobs.submit(self.work, self.spec, 'TEST NEW CONFIRMATION')
            post.assert_not_called()
