"""Persist enough evidence to reconstruct costs without current prices or media."""
import copy
import datetime as dt
import math
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from core.media_probe import calculate_asset_inputs


class CostAudit(unittest.TestCase):
    def quote(self, data, fx=None):
        def measure(asset):
            metadata = {'width': 1200, 'height': 900}
            if data['operation'] == 'decompose-layers':
                metadata['mime'] = 'image/png'
            if asset['kind'] == 'video':
                metadata.update(width=1280, height=720, duration=8.0)
            return {**asset, 'metadata': metadata}
        with patch('core.media_probe.probe_asset', side_effect=measure):
            return calculate_asset_inputs(data, fx=fx)

    def test_image_audit_reconstructs_exact_pixel_and_extra_input_cost(self):
        data = {'provider': 'volcengine', 'model': 'seedream-5.0-pro',
                'operation': 'image-to-image', 'size': '2048x2048',
                'assets': [{'id': str(i), 'kind': 'image', 'source': f'https://example.com/{i}.png'} for i in range(3)]}
        original = copy.deepcopy(data)
        record = self.quote(data)
        self.assertEqual(set(record), {'input', 'calculation', 'result'})
        self.assertEqual(record['input'], original)
        self.assertEqual(data, original)
        c, result = record['calculation'], record['result']
        self.assertEqual(c['assets'][0], {**data['assets'][0], 'width': 1200, 'height': 900})
        rates = c['pricing']['rates']
        pixels = math.prod(c['output_dimensions'])
        unit = rates['single'][int(pixels > rates['threshold_pixels'])]
        total = round(unit + max(c['input_images'] - 1, 0) * rates['input_after_first'], 6)
        self.assertEqual(c['output_pixels'], pixels)
        self.assertEqual(result['amount'], {'min': total, 'max': total})
        self.assertEqual(c['steps'][-1]['value'], result['amount'])
        self.assertTrue(c['pricing']['source'])
        self.assertTrue(c['notes'])

    def test_layer_audit_reconstructs_quantity_and_rate_bounds(self):
        record = self.quote({'provider': 'volcengine', 'model': 'seedream-5.0-pro',
                             'operation': 'decompose-layers', 'size': 'auto',
                             'assets': [{'id': 'product', 'kind': 'image', 'source': 'https://example.com/p.png'}]})
        c = record['calculation']
        totals = [round(n * rate + c['extra_input_cost'], 6)
                  for n, rate in zip(c['output_count_range'], c['pricing']['rates']['layer'])]
        self.assertEqual(record['result']['amount'], dict(zip(('min', 'max'), totals)))
        self.assertEqual(record['result']['uncertainties'][0]['field'], 'output_layers')

    def test_video_floor_and_fx_reconstruct_from_saved_evidence(self):
        data = {'provider': 'volcengine', 'model': 'seedance-2.5', 'operation': 'extend-video',
                'mode': 'after', 'resolution': '480p', 'ratio': 'adaptive', 'duration': 4,
                'assets': [{'id': 'clip', 'kind': 'video', 'source': 'https://example.com/clip.mp4'}],
                'estimate_context': {'minimum_billable_tokens': 200000,
                                     'minimum_tokens_source': 'https://docs.volcengine.com/test-fixture'}}
        fx = {'usd_cny': 7.0,
              'expires_at': (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)).isoformat()}
        record = self.quote(data, fx)
        c, result = record['calculation'], record['result']
        seconds = sum(a['duration'] for a in c['assets'] if a['kind'] == 'video')
        formula = [math.ceil((seconds + duration) * math.prod(c['assumed_output_dimensions'])
                             * c['frames_per_second'] / 1024) for duration in c['assumed_output_duration']]
        tokens = [max(t, math.ceil(c['minimum_billable_tokens'])) for t in formula]
        rate = c['pricing']['rates'][c['resolution']][int(bool(seconds))]
        amounts = [round(t * rate / 1000000, 6) for t in tokens]
        self.assertEqual(c['formula_tokens'], formula)
        self.assertEqual(c['tokens'], tokens)
        self.assertEqual(result['amount'], dict(zip(('min', 'max'), amounts)))
        self.assertEqual(result['conversion']['amount'],
                         dict(zip(('min', 'max'), [round(v / c['fx']['usd_cny'], 6) for v in amounts])))
        self.assertEqual(c['steps'][-1]['value'], result['conversion'])

    def test_unverified_floor_retains_raw_tokens_but_unknown_upper_cost(self):
        record = self.quote({'provider': 'volcengine', 'model': 'seedance-2.5',
                             'operation': 'reference-to-video', 'mode': 'reference',
                             'resolution': '480p', 'ratio': '16:9', 'duration': 4,
                             'assets': [{'id': 'clip', 'kind': 'video', 'source': 'https://example.com/c.mp4'}]})
        c, result = record['calculation'], record['result']
        self.assertEqual(c['formula_tokens'][0], c['formula_tokens'][1])
        self.assertIsNone(c['tokens'][1])
        self.assertIsNone(result['amount']['max'])
        self.assertEqual(result['status'], 'lower_bound')
        self.assertTrue(all(u['field'] and u['reason'] for u in result['uncertainties']))
