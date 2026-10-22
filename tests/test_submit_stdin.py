"""Submit accepts inline JSON without requiring an intermediate request file."""
import importlib.util
import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from core.request import ROOT


class SubmitStdin(unittest.TestCase):
    def setUp(self):
        module = importlib.util.spec_from_file_location('stdin_cli', ROOT/'scripts/media.py')
        self.cli = importlib.util.module_from_spec(module)
        module.loader.exec_module(self.cli)
        self.argv = ['media.py', 'submit', '--workdir', '/tmp/task', '--approval-text', 'TEST CONFIRMATION']

    def test_inline_request_reaches_submit_unchanged(self):
        request = {'provider': 'volcengine', 'operation': 'text-to-image',
                   'payload': {'model': 'doubao-seedream-5-0-flash-260915', 'prompt': '熊猫'}}
        with patch.object(sys, 'argv', self.argv), patch.object(sys, 'stdin', io.StringIO(json.dumps(request))), \
                patch.object(self.cli.jobs, 'submit', return_value={'state': 'succeeded', 'submission': '/tmp/task/submit-001.json'}) as submit, \
                patch.object(self.cli, 'emit') as emit:
            self.cli.main()
        submit.assert_called_once_with('/tmp/task', request, 'TEST CONFIRMATION', False)
        emit.assert_called_once_with({'submission': '/tmp/task/submit-001.json'})

    def test_invalid_input_never_submits(self):
        for text in ('', '{broken', '[]', '{"amount": NaN}'):
            with self.subTest(text=text), patch.object(sys, 'argv', self.argv), \
                    patch.object(sys, 'stdin', io.StringIO(text)), patch.object(self.cli.jobs, 'submit') as submit:
                with self.assertRaises(ValueError):
                    self.cli.main()
                submit.assert_not_called()
