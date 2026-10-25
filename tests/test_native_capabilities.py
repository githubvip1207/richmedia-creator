"""Capability boundaries stay supplier-specific."""
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
from commands import estimate_cost, submit
from core.request import compile_request
from core.operations import OPERATIONS
from providers import volcengine, byteplus
from test_native_byteplus import request


class NativeCapabilities(unittest.TestCase):
    def test_both_suppliers_reject_other_capabilities_before_post_or_media_access(self):
        for provider in ('volcengine', 'byteplus'):
            supported = {'text-to-image', 'image-to-image', 'decompose-layers'}
            for operation in set(OPERATIONS) - supported:
                with self.subTest(provider=provider, operation=operation), tempfile.TemporaryDirectory() as tmp:
                    spec = {'provider': provider, 'operation': operation, 'payload': {}}
                    with self.assertRaisesRegex(ValueError, 'Only basic text-to-image'):
                        compile_request(spec)
                    with patch.object(volcengine, 'request') as domestic, patch.object(byteplus, 'request') as overseas:
                        with self.assertRaisesRegex(ValueError, 'Only basic text-to-image'):
                            submit.submit(tmp, spec, 'TEST CONFIRMATION')
                        domestic.assert_not_called()
                        overseas.assert_not_called()
                    with patch('sys.stdin', io.StringIO(json.dumps(spec))), patch.object(estimate_cost, 'calculate_asset_inputs') as probe:
                        with self.assertRaisesRegex(ValueError, 'Only basic text-to-image'):
                            estimate_cost.run(SimpleNamespace(workdir=tmp))
                        probe.assert_not_called()
                    self.assertEqual(list(Path(tmp).glob('submit-*.json')), [])
                    self.assertEqual(list(Path(tmp).glob('*-priceing.json')), [])

    def test_text_to_image_cannot_silently_ignore_reference_assets(self):
        for provider in ('volcengine', 'byteplus'):
            with self.subTest(provider=provider), tempfile.TemporaryDirectory() as tmp:
                inputs = {'provider': provider, 'operation': 'text-to-image', 'model': 'seedream-5.0-flash',
                          'size': '1K', 'assets': [{'kind': 'image', 'source': '/input.png'}]}
                with patch('sys.stdin', io.StringIO(json.dumps(inputs))), patch.object(estimate_cost, 'calculate_asset_inputs') as probe:
                    with self.assertRaisesRegex(ValueError, 'input assets'):
                        estimate_cost.run(SimpleNamespace(workdir=tmp))
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
