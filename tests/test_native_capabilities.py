"""各供应商分别维护自己的能力支持范围。"""
import copy
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from commands import cost as cost_command, submit
from providers import compile_request
from core.operations import OPERATIONS, require_supported_operation
from providers.volcengine import client as volcengine
from providers.byteplus import client as byteplus
from test_native_byteplus import request


class NativeCapabilities(unittest.TestCase):
    def test_both_suppliers_expose_seven_capabilities_and_reject_unknown_before_access(self):
        for provider in ('volcengine', 'byteplus'):
            for operation in OPERATIONS:
                require_supported_operation({'provider': provider, 'operation': operation})
            with tempfile.TemporaryDirectory() as tmp:
                spec = {'provider': provider, 'operation': 'unknown', 'payload': {}}
                with patch.object(volcengine, 'request') as domestic, patch.object(byteplus, 'request') as overseas:
                    with self.assertRaisesRegex(ValueError, 'seven implemented'):
                        submit.submit(tmp, spec, 'TEST CONFIRMATION')
                    domestic.assert_not_called()
                    overseas.assert_not_called()
                with patch('sys.stdin', io.StringIO(json.dumps(spec))), patch.object(cost_command, 'calculate_asset_inputs') as probe:
                    with self.assertRaisesRegex(ValueError, 'seven implemented'):
                        cost_command.run(SimpleNamespace(workdir=tmp))
                    probe.assert_not_called()
                self.assertEqual(list(Path(tmp).glob('submit-*.json')), [])
                self.assertEqual(list(Path(tmp).glob('*-priceing.json')), [])

    def test_text_to_image_cannot_silently_ignore_reference_assets(self):
        for provider in ('volcengine', 'byteplus'):
            with self.subTest(provider=provider), tempfile.TemporaryDirectory() as tmp:
                inputs = {'provider': provider, 'operation': 'text-to-image', 'model': 'seedream-5.0-flash',
                          'size': '1K', 'assets': [{'kind': 'image', 'source': '/input.png'}]}
                with patch('sys.stdin', io.StringIO(json.dumps(inputs))), patch.object(cost_command, 'calculate_asset_inputs') as probe:
                    with self.assertRaisesRegex(ValueError, 'input assets'):
                        cost_command.run(SimpleNamespace(workdir=tmp))
                    probe.assert_not_called()

    def test_both_suppliers_preserve_basic_settings_and_reject_extra_features(self):
        for provider, prefix in (('volcengine', 'doubao'), ('byteplus', 'dola')):
            spec = request()
            spec['provider'] = provider
            spec['payload']['model'] = prefix + '-seedream-5-0-flash-260915'
            self.assertEqual(compile_request(spec)['payload_template'], spec['payload'])
            for fields in ({'image': 'https://example.com/in.png'}, {'n': 2},
                           {'background': 'transparent'}, {'layer_decomposition': True},
                           {'sequential_image_generation': 'auto'}):
                with self.subTest(provider=provider, fields=fields):
                    changed = copy.deepcopy(spec)
                    changed['payload'].update(fields)
                    with self.assertRaises(ValueError):
                        compile_request(changed)
