"""标准命令通过 curl 传输媒体的离线测试。"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from core import download


class CurlDownload(unittest.TestCase):
    def run_download(self, replies, check=None):
        calls = []
        def transport(args, **kwargs):
            calls.append((args, kwargs))
            if check:
                check(args, kwargs)
            reply = replies.pop(0)
            if isinstance(reply, Exception):
                raise reply
            code, status, body = reply
            Path(args[args.index('--output') + 1]).write_bytes(body)
            return subprocess.CompletedProcess(args, code, status, 'private signed URL must stay hidden')
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / 'image.part'
            with patch.object(download.shutil, 'which', return_value='/usr/bin/curl'), patch.object(download.subprocess, 'run', side_effect=transport), patch.object(download.time, 'sleep') as sleep:
                download.download_url('https://example.com/image?secret=access-token', target)
                return target.read_bytes(), calls, [c.args[0] for c in sleep.call_args_list]

    def test_complete_transfer_uses_https_and_keeps_signed_url_out_of_argv(self):
        def check(args, kwargs):
            self.assertEqual(args[1], '-q')
            self.assertNotIn('access-token', ' '.join(args))
            self.assertIn('access-token', kwargs['input'])
            self.assertEqual(args[args.index('--proto') + 1], '=https')
            self.assertEqual(args[args.index('--proto-redir') + 1], '=https')
            self.assertEqual(args[args.index('--connect-timeout') + 1], '15')
            self.assertEqual(args[args.index('--speed-time') + 1], '20')
        body, calls, sleeps = self.run_download([(0, '200', b'complete')], check)
        self.assertEqual(body, b'complete')
        self.assertEqual(len(calls), 1)
        self.assertEqual(sleeps, [])

    def test_stall_and_truncated_body_are_replaced_then_complete(self):
        body, calls, sleeps = self.run_download([(28, '200', b'stall'), (18, '200', b'short'), (0, '200', b'whole image')])
        self.assertEqual(body, b'whole image')
        self.assertEqual(len(calls), 3)
        self.assertEqual(sleeps, [2, 4])

    def test_http_404_stops_once_without_exposing_signed_url(self):
        with patch.object(download.time, 'sleep') as sleep, patch.object(download.shutil, 'which', return_value='/usr/bin/curl'), patch.object(download.subprocess, 'run', return_value=subprocess.CompletedProcess([], 22, '404', 'secret access-token')) as run:
            with self.assertRaisesRegex(RuntimeError, 'HTTP 404') as caught:
                download.download_url('https://example.com/?secret=access-token', '/unused')
            self.assertNotIn('access-token', str(caught.exception))
            self.assertEqual(run.call_count, 1)
            sleep.assert_not_called()

    def test_http_503_retries_same_media_only(self):
        body, calls, sleeps = self.run_download([(22, '503', b''), (0, '200', b'whole')])
        self.assertEqual(body, b'whole')
        self.assertEqual(len(calls), 2)
        self.assertEqual(sleeps, [2])

    def test_subprocess_timeout_retries_with_bounded_wait(self):
        body, calls, sleeps = self.run_download([subprocess.TimeoutExpired('curl', 915), (0, '200', b'whole')])
        self.assertEqual(body, b'whole')
        self.assertEqual(calls[0][1]['timeout'], 915)
        self.assertEqual(sleeps, [2])

    def test_exhausted_transport_error_hides_stderr(self):
        with patch.object(download.time, 'sleep'), patch.object(download.shutil, 'which', return_value='/usr/bin/curl'), patch.object(download.subprocess, 'run', return_value=subprocess.CompletedProcess([], 28, '200', 'https://secret.invalid/token')) as run:
            with self.assertRaisesRegex(RuntimeError, 'after 3 attempt') as caught:
                download.download_url('https://example.com/?secret=access-token', '/unused')
            self.assertNotIn('secret', str(caught.exception))
            self.assertIn('curl exit 28', str(caught.exception))
            self.assertEqual(run.call_count, 3)
