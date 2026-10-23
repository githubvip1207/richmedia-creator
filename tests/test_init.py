"""Run initialization is local, atomic, private and does not invent task content."""
import datetime as dt
import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from commands import init as init_command


class FrozenDateTime(dt.datetime):
    @classmethod
    def now(cls, tz=None):
        return dt.datetime(2026, 10, 22, 16, 30, 45)


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for patcher in (patch.object(init_command, 'WORK_ROOT', self.root),
                        patch.object(init_command.dt, 'datetime', FrozenDateTime)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_private_directory_and_request_use_local_clock(self):
        with patch('urllib.request.OpenerDirector.open') as network, patch('subprocess.run') as command:
            result = init_command.initialize('{"original_prompt":"测试需求"}')
        directory = Path(result['workdir'])
        self.assertEqual(directory.name, 'richmedia-20261022163045')
        self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)
        request = directory / 'request.json'
        self.assertEqual(list(directory.iterdir()), [request])
        self.assertEqual(request.read_text(), '{"original_prompt":"测试需求"}')
        self.assertEqual(stat.S_IMODE(request.stat().st_mode), 0o600)
        self.assertEqual(result, {'workdir': str(directory)})
        network.assert_not_called()
        command.assert_not_called()

    def test_collision_keeps_existing_run_and_uses_new_timestamp(self):
        first = init_command.initialize('{"original_prompt":"测试需求"}')
        request = Path(first['workdir']) / 'request.json'
        request.write_text('existing user requirements')
        # A symlink collision must also be skipped without following it.
        (self.root / 'richmedia-20261022163046').symlink_to(Path(first['workdir']), target_is_directory=True)
        second = init_command.initialize('{"original_prompt":"测试需求"}')
        self.assertEqual(Path(second['workdir']).name, 'richmedia-20261022163047')
        self.assertEqual(request.read_text(), 'existing user requirements')
        self.assertEqual(json.loads((Path(second['workdir']) / 'request.json').read_text()), {'original_prompt':'测试需求'})

    def test_invalid_input_does_not_create_directory(self):
        for content in ('', 'not json', '[]', 'null', '{"amount":NaN}'):
            with self.assertRaises(ValueError):
                init_command.initialize(content)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_failed_write_removes_incomplete_run(self):
        with patch.object(init_command.os, 'open', side_effect=PermissionError('denied')):
            with self.assertRaises(PermissionError):
                init_command.initialize('{}')
        self.assertEqual(list(self.root.iterdir()), [])

    def test_filesystem_failure_is_reported_without_creating_request(self):
        with patch.object(Path, 'mkdir', side_effect=PermissionError('denied')):
            with self.assertRaises(PermissionError):
                init_command.initialize('{"original_prompt":"测试需求"}')
        self.assertEqual(list(self.root.iterdir()), [])


class InitCommandTests(unittest.TestCase):
    def test_cli_saves_stdin_without_credentials(self):
        cli = Path(__file__).resolve().parents[1] / 'scripts' / 'main.py'
        with tempfile.TemporaryDirectory() as project:
            result = subprocess.run([sys.executable, str(cli), 'init'],
                                    cwd=project, input='{"original_prompt":"测试\n需求"}'.replace("\n", "\\n"), capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            info = json.loads(result.stdout)
            directory = Path(info['workdir'])
            try:
                self.assertEqual(directory.parent, Path('/tmp'))
                self.assertTrue(directory.name.startswith('richmedia-'))
                self.assertEqual(set(info), {'workdir'})
                self.assertEqual(json.loads((directory / 'request.json').read_text()), {'original_prompt':'测试\n需求'})
                self.assertEqual(list(directory.iterdir()), [directory / 'request.json'])
                self.assertEqual(list(Path(project).iterdir()), [])
            finally:
                (directory / 'request.json').unlink()
                directory.rmdir()



if __name__ == '__main__':
    unittest.main()
