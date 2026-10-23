"""图片终态、下载恢复和查询超时的离线回归测试。"""
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from commands import submit as submit_command, download as download_command
from core import submission_store as store, media_probe as cost_assets
from cost_fixture import save_with_cost
from providers import volcengine, byteplus, transport


class ImageLifecycle(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)
        (self.work/'volcengine').mkdir()
        cost = cost_assets.calculate_asset_inputs({'provider':'volcengine','model':'seedream-5.0-flash',
                                                   'operation':'text-to-image','size':'1K'})
        store.write(self.work/'volcengine-priceing.json', cost)
        self.spec = {'provider':'volcengine','operation':'text-to-image',
                     'payload':{'model':'doubao-seedream-5-0-flash-260915','prompt':'熊猫',
                                'size':'1K','output_format':'png','response_format':'url','watermark':False,
                                'background':'opaque','layer_decomposition':False}}
        self.spec['original_prompt'] = '熊猫'
        save_with_cost(self.spec, self.work)

    def submit(self, entries):
        with patch('commands.submit.require_dependencies'), patch.object(submit_command, 'config_value',return_value='fixture-only'), \
                patch.object(volcengine,'request',return_value={'data':entries}) as post:
            state = submit_command.submit(self.work,self.spec,'TEST ONLY')
        post.assert_called_once()
        return state

    def test_all_image_errors_are_failed_and_cannot_download(self):
        state = self.submit([{'error':{'message':'第一张失败'}},{'error':{'message':'第二张失败'}}])
        self.assertEqual(state['state'],'failed')
        record = store.read(state['submission'])
        self.assertEqual(record['execution']['state'],'failed')
        self.assertEqual(len(record['execution']['errors']),2)
        with patch.object(download_command, 'download_url') as get:
            with self.assertRaises(ValueError):
                download_command.download(state['submission'])
        get.assert_not_called()

    def test_mixed_image_results_remain_partial_failed(self):
        state = self.submit([{'url':'https://example.com/one.png'},{'error':{'message':'第二张失败'}}])
        self.assertEqual(state['state'],'partial_failed')

    def test_failed_redownload_clears_previous_completion_then_can_recover(self):
        state = self.submit([{'url':'https://example.com/one.png'}])
        record_path = state['submission']
        def save(url,path):
            from test_runtime import png
            path.write_bytes(png())
        with patch.object(download_command, 'download_url',side_effect=save):
            result = download_command.download(record_path)
        path = Path(result['files'][0]['path'])
        self.assertTrue(store.read(record_path)['execution']['download_complete'])
        path.write_bytes(b'damaged')
        with patch.object(download_command, 'download_url',side_effect=RuntimeError('fixture failure')):
            with self.assertRaises(RuntimeError):
                download_command.download(record_path)
        record = store.read(record_path)
        self.assertFalse(record['execution']['download_complete'])
        self.assertEqual(record['result']['files'],result['files'])
        self.assertEqual(record['execution']['state'],'succeeded')
        with patch.object(download_command, 'download_url',side_effect=save):
            download_command.download(record_path)
        self.assertTrue(store.read(record_path)['execution']['download_complete'])
        with patch.object(download_command, 'download_url') as get:
            download_command.download(record_path)
        get.assert_not_called()


class QueryTimeout(unittest.TestCase):
    def test_both_suppliers_forward_remaining_timeout_to_http(self):
        for adapter in (volcengine,byteplus):
            with self.subTest(provider=adapter.KEY_ENV), \
                    patch.object(transport,'config_value',return_value='fixture-only'), \
                    patch.object(transport.urllib.request,'build_opener') as build:
                build.return_value.open.return_value = io.BytesIO(b'{"status":"running"}')
                self.assertEqual(adapter.status('fixture',timeout=0.5),{'status':'running'})
                self.assertEqual(build.return_value.open.call_args.kwargs['timeout'],0.5)

    def test_default_get_and_post_timeouts_are_unchanged(self):
        for method, expected in (('GET',25),('POST',180)):
            with self.subTest(method=method), \
                    patch.object(transport,'config_value',return_value='fixture-only'), \
                    patch.object(transport.urllib.request,'build_opener') as build:
                build.return_value.open.return_value = io.BytesIO(b'{}')
                transport.request('https://example.com','FIXTURE_KEY','fixture',method,'/fixture')
                self.assertEqual(build.return_value.open.call_args.kwargs['timeout'],expected)
