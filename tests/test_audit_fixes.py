"""中断恢复、离线交付、确认绑定和规格差异的回归测试；不调用付费接口。"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from test_native_video import request, prepare
from providers import compile_request
from commands import status, deliver
from commands.submit import validate_requirement
from core import submission_store as store
from core.file_hash import sha256_file
from core.media_validate import verify_spec


class AuditFixes(unittest.TestCase):
    def test_video_saved_post_response_recovers_before_get_without_post(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'submit-001.json'
            compiled = compile_request(request())
            store.write(path, {'response': {'id': 'paid-task'}, 'execution': {
                'state': 'submitting', 'task_id': None, 'compiled': compiled}})
            with patch('commands.status.query_submission', return_value={
                'id': 'paid-task', 'status': 'running'}) as query:
                actual = status.status(path)
            self.assertEqual(actual['task_id'], 'paid-task')
            self.assertEqual(actual['state'], 'running')
            query.assert_called_once()
            self.assertEqual(store.read(path)['response'], {'id': 'paid-task'})

    def test_image_saved_response_recovers_from_submitting(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'submit-001.json'
            compiled = {'provider': 'volcengine', 'operation': 'text-to-image',
                        'kind': 'image', 'model': 'seedream-5.0-flash', 'quantity': 1}
            store.write(path, {'response': {'data': [{'url': 'https://example.com/out.png'}]},
                              'execution': {'state': 'submitting', 'compiled': compiled}})
            self.assertEqual(status.status(path)['state'], 'succeeded')

    def test_response_missing_id_stays_unresolved(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'submit-001.json'
            store.write(path, {'response': {}, 'execution': {'state': 'submitting',
                        'task_id': None, 'compiled': compile_request(request())}})
            with patch('commands.status.query_submission') as query:
                self.assertEqual(status.status(path)['state'], 'submitting')
            query.assert_not_called()

    def test_cached_delivery_needs_no_network_and_preserves_completed_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); work = root / 'task'; work.mkdir()
            target = root / 'user'; target.mkdir()
            media = work / '00-video.mp4'; media.write_bytes(b'verified fixture')
            path = work / 'submit-001.json'
            store.write(path, {'execution': {'state': 'succeeded', 'download_complete': True},
                'result': {'files': [{'path': str(media), 'sha256': sha256_file(media), 'kind': 'video'}]}})
            with patch('commands.status.status', side_effect=OSError('offline')) as network:
                first = deliver.deliver(path, target)
                second = deliver.deliver(path, target)
            network.assert_not_called()
            self.assertEqual(first['files'], second['files'])
            self.assertTrue(store.read(path)['execution']['delivery_complete'])

    def test_text_video_context_cannot_differ_from_confirmed_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp); spec = request(); prepare(work, spec)
            record = store.read(work / 'request.json')
            record['providers']['volcengine']['estimate_context'] = {'preferred_duration': 15}
            store.write(work / 'request.json', record)
            with self.assertRaisesRegex(ValueError, 'estimate_context'):
                validate_requirement(work, spec, compile_request(spec))

    def test_video_mismatch_lists_dimensions_duration_and_audio(self):
        compiled = compile_request(request())
        actual = {'width': 320, 'height': 320, 'duration': .25, 'has_audio': True}
        result = verify_spec(None, 'video', compiled, actual)
        self.assertEqual(result['status'], 'mismatch')
        self.assertEqual({d['field'] for d in result['differences']}, {'dimensions', 'duration', 'has_audio'})
        expected = {'width': 854, 'height': 480, 'duration': 4.04, 'has_audio': False}
        self.assertEqual(verify_spec(None, 'video', compiled, expected)['status'], 'matched')

    def test_tiny_image_does_not_match_any_k_preset(self):
        for size in ('1K', '1.5K', '2K'):
            compiled = {'kind': 'image', 'operation': 'text-to-image', 'parameters': {'size': size}}
            with patch('core.cost_reconcile.image_dimensions', return_value=[16, 16]):
                result = verify_spec(None, 'image', compiled)
            self.assertEqual(result['status'], 'mismatch')

    def test_scaled_floor_discloses_unquantified_error_in_quote_result(self):
        from test_cost_accuracy import quote
        from core.cost_record import build_record
        result = quote(duration=10)
        self.assertEqual(result['estimate_quality'], 'extrapolated')
        evidence = result['minimum_tokens_evidence']
        self.assertEqual(evidence['extrapolation_error'], 'uncalibrated')
        self.assertEqual(evidence['interval_covers'], ['published_price_rounding'])
        self.assertGreater(result['amount'][0], 0)
        self.assertGreaterEqual(result['amount'][1], result['amount'][0])
