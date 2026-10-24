# 媒体 GET 重试测试：用内存响应模拟超时、HTTP 错误与不完整下载。
# 只验证取回已有媒体，不执行生成；测试中的 sleep 被替换，避免真实等待。
"""Offline media GET retries; no supplier generation requests."""
import io
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from commands import status as status_command, download as download_command
from core import submission_store as store
from cost_fixture import save_with_cost


# 内存中的 HTTP 响应替身，支持上下文管理、读取、Content-Length 和最终 URL。
class Response(io.BytesIO):
    # 初始化内存响应，并允许指定与真实数据长度不同的 Content-Length 来模拟截断。
    def __init__(self, body, length=None):
        super().__init__(body)
        self.headers = {'Content-Length': str(len(body) if length is None else length)}

    # 模拟最终 HTTPS 地址，以通过下载器的协议检查，不执行真实网络访问。
    def geturl(self):
        return 'https://example.com/result.png'


# 覆盖媒体下载的重试范围、停止条件、隐私摘要和清单复用行为。
class DownloadRetry(unittest.TestCase):
    def setUp(self):
        # Existing cases exercise the portable urllib path; curl cases opt in.
        original = download_command.shutil.which
        mock = patch.object(download_command.shutil, 'which',
                            side_effect=lambda name: None if name == 'curl' else original(name))
        mock.start()
        self.addCleanup(mock.stop)

    # 模拟首次读取一部分后超时、第二次成功；断言临时文件被完整替换、超时值为 30 秒且只等待 2 秒。
    def test_timeout_then_success_replaces_partial_file(self):
        # 首次返回少量字节，随后抛出超时，用于模拟中途断流。
        class Broken(Response):
            # 首次只交付部分字节，后续读取抛出 TimeoutError，验证重新下载能覆盖残留内容。
            def read(self, size):
                if self.tell():
                    raise TimeoutError('read timed out')
                return super().read(3)
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / 'image.part'
            with patch.object(download_command.urllib.request, 'urlopen', side_effect=[Broken(b'partial'), Response(b'complete')]) as get, patch.object(status_command.time, 'sleep') as sleep:
                download_command.download_url('https://example.com/result.png', target)
                self.assertEqual(target.read_bytes(), b'complete')
                self.assertEqual(get.call_count, 2)
                self.assertEqual(get.call_args.kwargs['timeout'], 30)
                sleep.assert_called_once_with(2)

    def test_cdn_stalling_default_python_agent_downloads_in_one_attempt(self):
        # Reproduce the observed CDN behavior: default urllib requests receive
        # only a partial body, while an explicitly identified client completes.
        class Stalled(Response):
            def read(self, size):
                if self.tell():
                    raise TimeoutError('CDN stopped sending the body')
                return super().read(3)

        def cdn(request, **kwargs):
            headers = dict(request.header_items()) if isinstance(request, urllib.request.Request) else {}
            agent = headers.get('User-agent', 'Python-urllib/3.14')
            self.assertFalse(any(k.lower() in ('authorization', 'x-api-key') for k in headers))
            if agent.startswith('Python-urllib/'):
                return Stalled(b'partial')
            return Response(b'complete media')

        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / 'image.part'
            with patch.object(download_command.urllib.request, 'urlopen', side_effect=cdn) as get, patch.object(download_command.time, 'sleep') as sleep:
                download_command.download_url('https://example.com/result.png', target)
                self.assertEqual(target.read_bytes(), b'complete media')
                self.assertEqual(get.call_count, 1)
                sleep.assert_not_called()

    # 连续抛出传输错误，验证最多三次 GET、2/4 秒退避，并确保异常摘要不泄露签名 URL。
    def test_exhaustion_stops_after_three_attempts_and_hides_url(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(download_command.urllib.request, 'urlopen', side_effect=urllib.error.URLError('https://secret.invalid/signed')) as get, patch.object(status_command.time, 'sleep') as sleep:
                with self.assertRaisesRegex(RuntimeError, 'after 3 attempt') as caught:
                    download_command.download_url('https://example.com/result.png', Path(d) / 'image.part')
                self.assertNotIn('secret', str(caught.exception))
                self.assertEqual(get.call_count, 3)
                self.assertEqual([c.args[0] for c in sleep.call_args_list], [2, 4])

    # 404 表示资源不可用；验证只请求一次且不等待，避免对不可重试错误反复下载。
    def test_http_404_stops_without_retry(self):
        error = urllib.error.HTTPError('https://example.com/result.png', 404, 'missing', {}, None)
        with patch.object(download_command.urllib.request, 'urlopen', side_effect=error) as get, patch.object(status_command.time, 'sleep') as sleep:
            with self.assertRaisesRegex(RuntimeError, 'HTTP 404'):
                download_command.download_url('https://example.com/result.png', '/unused')
            self.assertEqual(get.call_count, 1)
            sleep.assert_not_called()

    # 模拟 503 后成功，验证媒体 GET 可重试并保存后续完整字节。
    def test_http_503_retries(self):
        error = urllib.error.HTTPError('https://example.com/result.png', 503, 'busy', {}, None)
        with tempfile.TemporaryDirectory() as d:
            with patch.object(download_command.urllib.request, 'urlopen', side_effect=[error, Response(b'ok')]), patch.object(status_command.time, 'sleep'):
                target = Path(d) / 'image.part'
                download_command.download_url('https://example.com/result.png', target)
                self.assertEqual(target.read_bytes(), b'ok')

    # 响应体短于声明 Content-Length 时视为不完整下载，验证重新取回完整内容。
    def test_short_body_is_retried(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(download_command.urllib.request, 'urlopen', side_effect=[Response(b'short', 100), Response(b'whole')]) as get, patch.object(status_command.time, 'sleep'):
                target = Path(d) / 'image.part'
                download_command.download_url('https://example.com/result.png', target)
                self.assertEqual(get.call_count, 2)
                self.assertEqual(target.read_bytes(), b'whole')

    # 在完整下载流程中模拟超时恢复，验证文件内容与完成标记；再次下载应复用哈希匹配的文件。
    def test_download_pipeline_records_complete_media_after_retry(self):
        from test_runtime import png
        data = png()
        with tempfile.TemporaryDirectory() as d:
            job = Path(d) / 'job'
            spec=save_with_cost({'provider':'volcengine', 'model':'seedream-5.0-flash',
                          'operation':'text-to-image', 'prompt':'小猫',
                          'parameters':{'ratio':'9:16'}}, job)
            from core.request import compile_request
            store.write(job / 'submit-001.json', {**spec,
                       'execution': {'state':'succeeded','compiled':compile_request(spec)},
                       'response': {'data':[{'url':'https://example.com/result.png'}]}})
            with patch.object(download_command.urllib.request, 'urlopen', side_effect=[TimeoutError(), Response(data)]) as get, patch.object(status_command.time, 'sleep'):
                result = download_command.download(job)
                self.assertEqual(Path(result['files'][0]['path']).read_bytes(), data)
                self.assertTrue(store.read(job / 'submit-001.json')['execution']['download_complete'])
                download_command.download(job)
                self.assertEqual(get.call_count, 2)
