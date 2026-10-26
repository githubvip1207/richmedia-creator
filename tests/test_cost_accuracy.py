"""覆盖真实估价缺口，不调用生成 API；以官方公开价格示例作外部数值校验。"""
import copy
import datetime as dt
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from providers import get_capability
from core.catalogs import ROOT
from core.media_probe import display_dimensions, media_duration
from core.pricing import freshness, refresh, parse_markdown
from core.cost_reconcile import reconcile


def quote(provider='volcengine', model='seedance-2.5', operation='reference-to-video',
          resolution='480p', ratio='16:9', duration=5, width=1280, height=720, context=None):
    video = operation == 'reference-to-video'
    compiled = {'provider': provider, 'model': model, 'operation': operation, 'kind': 'video',
                'parameters': {'resolution': resolution, 'ratio': ratio, 'duration': duration},
                'assets': [{'kind': 'video' if video else 'image',
                            'metadata': {'width': width, 'height': height, 'duration': 2}}]}
    if video:
        compiled['mode'] = 'reference'
    return get_capability(provider, operation).calculate_cost(compiled, context)


class Accuracy(unittest.TestCase):
    def test_public_same_spec_price_examples_are_reproduced(self):
        # 与定价文档的四舍五入价格独立比较：2秒输入、5秒输出。
        for provider, expected in [('volcengine', [3.63, 8.16, 20.12]),
                                   ('byteplus', [.553, 1.244, 3.062])]:
            for resolution, price in zip(('480p', '720p', '1080p'), expected):
                with self.subTest(provider=provider, resolution=resolution):
                    result = quote(provider, resolution=resolution)
                    self.assertLessEqual(result['amount'][0], price)
                    self.assertGreaterEqual(result['amount'][1], price)
                    self.assertEqual(result['minimum_tokens_evidence']['method'], 'public_example_rounded')
                    self.assertFalse(result['range_is_guaranteed'])

    def test_every_supported_model_gets_nonzero_finite_adaptive_video_estimate(self):
        for provider in ('volcengine', 'byteplus'):
            pricing = json.loads((ROOT / 'models' / (provider + '-pricing.json')).read_text())
            for model, resolutions in pricing['video'].items():
                for resolution in resolutions:
                    for duration in (4, 5, 15, -1):
                        q = quote(provider, model, resolution=resolution, ratio='adaptive', duration=duration)
                        self.assertGreater(q['amount'][0], 0)
                        self.assertGreaterEqual(q['amount'][1], q['amount'][0])
                        self.assertTrue(math.isfinite(q['amount'][1]))
                        self.assertTrue(q['uncertainties'])

    def test_near_portrait_ratio_and_arbitrary_ratio_do_not_return_unknown(self):
        for provider in ('volcengine', 'byteplus'):
            q = quote(provider, operation='image-to-video', ratio='adaptive', width=800, height=1424)
            self.assertEqual(q['assumed_output_dimensions'], [480, 854])
            arbitrary = quote(provider, operation='image-to-video', ratio='adaptive', width=1300, height=1000)
            self.assertEqual(arbitrary['status'], 'estimate')
            self.assertEqual(arbitrary['output_dimensions_basis'], 'source_ratio_area_estimate')
            self.assertTrue(arbitrary['uncertainties'])

    def test_auto_duration_shows_scenarios_and_respects_preferred_scenario(self):
        q = quote(duration=-1, context={'preferred_duration': 10})
        self.assertEqual(q['assumed_output_duration'], [4, 30])
        self.assertEqual([s['output_seconds'] for s in q['scenarios'] if s['preferred']], [10])
        self.assertEqual(q['minimum_tokens_evidence']['method'], 'public_example_scaled')
        with self.assertRaises(ValueError):
            quote(duration=-1, context={'preferred_duration': 31})

    def test_invalid_floor_source_scope_and_dimensions_are_rejected(self):
        for context in (
            {'minimum_billable_tokens': 1, 'minimum_tokens_source': 'https://example.com/false'},
            {'minimum_billable_tokens': 1, 'minimum_tokens_source': 'https://docs.volcengine.com.evil.test/'},
            {'minimum_billable_tokens': 1, 'minimum_tokens_source': 'https://docs.volcengine.com/docs/ark/model-pricing'},
            {'minimum_billable_tokens': 100000, 'minimum_tokens_source': 'https://docs.volcengine.com/docs/ark/model-pricing',
             'minimum_tokens_spec': {'model': 'seedance-2.0'}},
            {'output_dimensions': [3840, 2160]}, {'output_dimensions': [640, 640]},
        ):
            with self.subTest(context=context), self.assertRaises(ValueError):
                quote(context=context)

    def test_rotation_and_pixel_aspect_are_used_for_display_dimensions(self):
        self.assertEqual(display_dimensions({'width': 1920, 'height': 1080,
                                             'side_data_list': [{'rotation': -90}]}), (1080, 1920))
        self.assertEqual(display_dimensions({'width': 720, 'height': 576,
                                             'sample_aspect_ratio': '16:15'}), (768, 576))

    def test_duration_uses_time_base_then_vfr_packet_timestamps(self):
        stream = {'duration': 'N/A', 'duration_ts': 240000, 'time_base': '1/48000'}
        self.assertEqual(media_duration(stream, {}, 'test', 'ffprobe'), (5, 'duration_ts_time_base'))
        result = subprocess.CompletedProcess([], 0, json.dumps({'packets':
            [{'pts_time': '10', 'duration_time': '.1'}, {'pts_time': '12.4', 'duration_time': '.1'}]}), '')
        with patch('core.media_probe.process.run', return_value=result):
            self.assertEqual(media_duration({}, {}, 'test', 'ffprobe'), (2.5, 'packet_timestamps'))

    def test_failed_price_refresh_preserves_verified_date_and_values(self):
        price = json.loads((ROOT / 'models/byteplus-pricing.json').read_text())
        stale = copy.deepcopy(price); stale['verified_on'] = '2000-01-01'
        with patch('core.pricing.urllib.request.urlopen', side_effect=OSError('offline')):
            q = refresh('byteplus', stale, None)
        self.assertEqual(q['verified_on'], '2000-01-01')
        self.assertEqual(q['video'], price['video'])
        self.assertEqual(freshness(q)['status'], 'stale')
        with self.assertRaises(ValueError):
            parse_markdown('incomplete page', 'byteplus', stale)

    def test_remote_cost_properties_are_rechecked_before_quote_is_consumed(self):
        from core.cost_quote import consume_quote, billing_inputs
        from core.submission_store import now
        compiled = {'provider': 'volcengine', 'model': 'seedance-2.5', 'kind': 'video',
                    'operation': 'reference-to-video', 'mode': 'reference',
                    'parameters': {'resolution': '480p', 'ratio': '16:9', 'duration': 5},
                    'assets': [{'kind': 'video', 'metadata': {'duration': 2}}]}
        asset = {'id': 'clip', 'kind': 'video', 'source': 'https://example.com/clip.mp4',
                 'duration': 2, 'width': 1280, 'height': 720, 'cost_probe_version': 2}
        cost = {'input': {}, 'calculation': {**billing_inputs(compiled), 'schema_version': 3,
                'created_at': now(), 'assets': [asset], 'estimate_context': None,
                'fx': None, 'pricing': {}},
                'result': {'currency': 'CNY', 'amount': {'min': 3.62, 'max': 3.64}}}
        spec = {'payload': {}, 'provider': 'volcengine'}
        compiler = lambda s, measured_assets=None: compiled
        changed = {'metadata': {**asset, 'duration': 20}}
        with patch('core.media_probe.probe_asset', return_value=changed) as probe:
            with self.assertRaisesRegex(ValueError, 'Remote asset billing properties changed'):
                consume_quote(spec, cost, compiler, 'CNY')
            probe.assert_called_once()
        with patch('core.media_probe.probe_asset', return_value={'metadata': asset}):
            consume_quote(spec, cost, compiler, 'CNY')

    def test_complete_official_markdown_can_refresh_all_supported_prices(self):
        from core.catalogs import CATALOGS
        original = json.loads((ROOT / 'models/byteplus-pricing.json').read_text())
        lines = ['minimum 2.61']
        for mode, heading in [(0, 'without'), (1, 'with')]:
            lines.append('**Tab: Input ' + heading + ' video**')
            for alias, rows in original['video'].items():
                model = CATALOGS['byteplus']['models'][alias]['id']
                values = [rows['480p'][mode]] + [rows.get(r, [None, None])[mode] for r in ('1080p', '4k')]
                lines.append('| ' + model + ' | ' + ' | '.join(
                    '$' + str(v) if v is not None else 'Not supported' for v in values) + ' | Not supported |')
        pro = CATALOGS['byteplus']['models']['seedream-5.0-pro']['id']
        flash = CATALOGS['byteplus']['models']['seedream-5.0-flash']['id']
        lines.extend(['## Image generation', '| ' + pro + ' | $0.003 | $0.045 | $0.09 | $0.0225 | $0.045 |',
                      '| ' + flash + ' | Free | $0.018 |'])
        markdown = '\n'.join(lines)
        updated = parse_markdown(markdown, 'byteplus', original)
        self.assertEqual(updated['video'], original['video'])
        self.assertEqual(updated['image'], original['image'])
        # 少一行时必须整体失败，不能沿用旧值却把整张表标记为新核实。
        with self.assertRaises(ValueError):
            parse_markdown(markdown.replace(lines[2], ''), 'byteplus', original)

    def test_actual_image_layers_use_each_output_pixel_tier(self):
        import struct
        with tempfile.TemporaryDirectory() as directory:
            files = []
            for index, size in enumerate((1024, 2048)):
                p = Path(directory) / (str(index) + '.png')
                p.write_bytes(b'\x89PNG\r\n\x1a\n' + b'\x00\x00\x00\x0dIHDR' + struct.pack('>II', size, size))
                files.append({'kind': 'image', 'path': str(p)})
            record = {'execution': {'compiled': {'kind': 'image', 'operation': 'decompose-layers'},
                'cost_record': {'calculation': {'extra_input_cost': 0, 'pricing': {'rates': {
                    'layer': [.15, .3], 'threshold_pixels': 2610000}}},
                    'result': {'currency': 'CNY', 'amount': {'min': .15, 'max': 5.1}}}}}
            q = reconcile(record, {}, files)
            self.assertEqual(q['output_count'], 2)
            self.assertEqual(q['observed_output_cost_at_list_price'], {'min': .45, 'max': .45})

    def test_actual_usage_comparison_does_not_claim_real_billing(self):
        record = {'execution': {'compiled': {'kind': 'video'}, 'cost_record': {
            'calculation': {'unit_price_per_million_tokens': 42, 'tokens': [80000, 90000]},
            'result': {'currency': 'CNY', 'amount': {'min': 3.36, 'max': 3.78}}}}}
        q = reconcile(record, {'completion_tokens': 100000}, [])
        self.assertEqual(q['usage_cost_at_list_price'], 4.2)
        self.assertAlmostEqual(q['difference_percent_outside_estimate'], 11.111)
        self.assertIsNone(q['actual_billed_amount'])
        self.assertEqual(reconcile(record, {}, [])['status'], 'partial')

    def test_price_parser_cannot_accept_wrong_currency_or_partial_model_table(self):
        # 防止把美元网页数值写进人民币价目表。
        price = json.loads((ROOT / 'models/volcengine-pricing.json').read_text())
        with self.assertRaises(ValueError):
            parse_markdown('minimum 2.61\n**Tab: Input with video**\n| model | $6.4 |', 'volcengine', price)


if __name__ == '__main__':
    unittest.main()

class SupplierPricingConfiguration(unittest.TestCase):
    def test_supplier_minimum_rules_override_fallback_without_task_price_inputs(self):
        for provider in ('volcengine', 'byteplus'):
            with self.subTest(provider=provider):
                from core.pricing import load_pricing
                pricing = load_pricing(provider)
                source = pricing['source']
                pricing['minimum_token_estimation']['rules'] = [{
                    'model': 'seedance-2.5', 'resolution': '480p', 'ratio': '16:9',
                    'duration': 5, 'tokens': 200000, 'source': source,
                    'verified_on': '2026-10-26'}]
                with patch('core.pricing.load_pricing', return_value=pricing):
                    result = quote(provider)
                self.assertEqual(result['tokens'], [200000, 200000])
                self.assertEqual(result['minimum_tokens_evidence']['method'], 'configured_official_table')
                self.assertEqual(result['minimum_tokens_source'], source)
                # A different duration must not reuse the five-second minimum row.
                with patch('core.pricing.load_pricing', return_value=pricing):
                    other = quote(provider, duration=10)
                self.assertEqual(other['minimum_tokens_evidence']['method'], 'public_example_scaled')

    def test_task_context_cannot_override_supplier_minimum_pricing(self):
        for provider in ('volcengine', 'byteplus'):
            with self.subTest(provider=provider), self.assertRaisesRegex(ValueError, 'Unknown estimate_context'):
                quote(provider, context={'minimum_billable_tokens': 1,
                                         'minimum_tokens_source': 'https://docs.volcengine.com/example'})

    def test_examples_are_owned_by_each_supplier_and_keep_their_own_date(self):
        for provider in ('volcengine', 'byteplus'):
            pricing = json.loads((ROOT / 'models' / (provider + '-pricing.json')).read_text())
            evidence = pricing['minimum_token_estimation']
            self.assertEqual(evidence['anchor_duration'], 5)
            self.assertEqual(evidence['anchor_ratio'], '16:9')
            for model, resolutions in pricing['video'].items():
                for resolution in resolutions:
                    self.assertGreater(evidence['examples'][model][resolution], 0)
                    self.assertGreater(evidence['rates'][model][resolution], 0)
            with patch('core.pricing.load_pricing', return_value=pricing):
                result = quote(provider)
            self.assertEqual(result['minimum_tokens_evidence']['verified_on'], evidence['verified_on'])

    def test_old_unit_price_cache_gets_current_supplier_minimum_configuration(self):
        from core.pricing import load_pricing, pricing_session
        from core.submission_store import write
        for provider in ('volcengine', 'byteplus'):
            original = load_pricing(provider)
            cached = copy.deepcopy(original)
            cached.pop('minimum_token_estimation')
            cached['verified_on'] = dt.datetime.now(dt.timezone.utc).date().isoformat()
            with tempfile.TemporaryDirectory() as tmp:
                write(Path(tmp) / (provider + '-pricing-cache.json'), cached)
                with pricing_session(tmp):
                    result = load_pricing(provider)
            self.assertEqual(result['minimum_token_estimation'], original['minimum_token_estimation'])
            self.assertEqual(result['video'], cached['video'])

    def test_unit_price_refresh_does_not_reverify_minimum_data(self):
        provider = 'byteplus'
        original = json.loads((ROOT / 'models' / (provider + '-pricing.json')).read_text())
        # Use the same official Markdown layout as the existing parser regression.
        from core.catalogs import CATALOGS
        lines = ['minimum 2.61']
        for mode, heading in [(0, 'without'), (1, 'with')]:
            lines.append('**Tab: Input ' + heading + ' video**')
            for alias, rows in original['video'].items():
                values = [rows['480p'][mode]] + [rows.get(r, [None, None])[mode] for r in ('1080p', '4k')]
                lines.append('| ' + CATALOGS[provider]['models'][alias]['id'] + ' | ' + ' | '.join(
                    '$' + str(v) if v is not None else 'Not supported' for v in values) + ' | Not supported |')
        lines.extend(['## Image generation',
            '| ' + CATALOGS[provider]['models']['seedream-5.0-pro']['id'] + ' | $0.003 | $0.045 | $0.09 | $0.0225 | $0.045 |',
            '| ' + CATALOGS[provider]['models']['seedream-5.0-flash']['id'] + ' | Free | $0.018 |'])
        original['minimum_token_estimation']['verified_on'] = '2020-01-01'
        updated = parse_markdown('\n'.join(lines), provider, original)
        self.assertEqual(updated['minimum_token_estimation'], original['minimum_token_estimation'])
        self.assertEqual(updated['minimum_token_estimation']['verified_on'], '2020-01-01')
