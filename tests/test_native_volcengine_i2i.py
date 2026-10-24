"""Volcengine reference images: real local probes, mocked paid POST and media GET."""
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
from commands import init, estimate_cost, submit, status, download
from core.request import compile_request
from core.cost_quote import consume_quote
from core.media_probe import calculate_asset_inputs
from core import submission_store as store
from providers import volcengine, byteplus, transport
from test_document_contract import image
from test_runtime import png
from config_fixture import config_fixture


class VolcengineImageToImage(unittest.TestCase):
    provider = 'volcengine'
    adapter = volcengine
    other_adapter = byteplus
    model_prefix = 'doubao'
    key_env = 'VOLCENGINE_API_KEY'
    pro_rates = (.3, .02)
    flash_rates = (.12, 0)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.local = self.root/'source.png'
        self.local.write_bytes(png())
        self.sources = [str(self.local)]

    def prepare(self, sources=None, model='flash', placeholder=False, prompt=None):
        sources = self.sources if sources is None else sources
        spec = image()
        spec['provider'] = self.provider
        spec['operation'] = 'image-to-image'
        spec['payload']['model'] = (self.model_prefix + '-seedream-5-0-pro-260628' if model == 'pro'
                                    else self.model_prefix + '-seedream-5-0-flash-260915')
        if placeholder:
            spec['payload']['image'] = []
        if prompt is not None:
            spec['original_prompt'] = spec['payload']['prompt'] = prompt
        assets = [{'id': str(i), 'kind': 'image', 'source': src} for i, src in enumerate(sources)]
        spec['assets'] = [{**a, 'purpose': '参考图片'} for a in assets]
        record = {'original_prompt': spec['original_prompt'], 'optimized_prompt': spec['payload']['prompt'],
                  'intent': {'operation': 'image-to-image'},
                  'assets': [{**a, 'purpose': '参考图片'} for a in assets],
                  'providers': {self.provider: {'model': spec['payload']['model'], 'operation': 'image-to-image',
                                 'parameters': {'size': '1K'}, 'assets': [{'id': a['id']} for a in assets]}}}
        with patch.object(init, 'WORK_ROOT', self.root):
            work = Path(init.initialize(json.dumps(record))['workdir'])
        cost_input = {'provider': self.provider, 'model': spec['payload']['model'],
                      'operation': 'image-to-image', 'size': '1K', 'assets': assets}
        with patch('sys.stdin', io.StringIO(json.dumps(cost_input))):
            estimate_cost.run(SimpleNamespace(workdir=str(work)))
        return work, spec

    def post(self, work, spec, response=None):
        response = response or {'data': [{'url': 'https://example.com/result.png'}]}
        with config_fixture({self.key_env: 'fixture-only'}), \
                patch.object(self.adapter, 'request', return_value=response) as post, \
                patch.object(self.other_adapter, 'request') as other:
            state = submit.submit(work, spec, 'TEST CONFIRMATION')
            other.assert_not_called()
            post.assert_called_once()
            return state, post.call_args.args[2]

    def assert_blocked(self, work, spec):
        with config_fixture({self.key_env: 'fixture-only'}), patch.object(self.adapter, 'request') as post:
            with self.assertRaises(ValueError):
                submit.submit(work, spec, 'TEST CONFIRMATION')
            post.assert_not_called()
        self.assertFalse((work/'submit-001.json').exists())

    def test_local_cli_lifecycle_encodes_only_in_memory_for_both_models(self):
        for model in ('pro', 'flash'):
            with self.subTest(model=model):
                work, spec = self.prepare(model=model)
                before = copy.deepcopy(spec)
                state, body = self.post(work, spec)
                self.assertEqual(body['prompt'], spec['payload']['prompt'])
                self.assertTrue(body['image'][0].startswith('data:image/png;base64,'))
                self.assertEqual(spec, before)
                self.assertEqual(store.read(work/'payload.json'), spec)
                self.assertNotIn('data:image', (work/'submit-001.json').read_text())
                with patch.object(self.adapter, 'status') as query:
                    self.assertTrue(status.run(SimpleNamespace(submission=state['submission'], wait=0))['success'])
                    query.assert_not_called()
                with patch.object(download, 'download_url', side_effect=lambda url, path: path.write_bytes(png())) as get:
                    result = download.download(state['submission'])
                    download.download(state['submission'])
                    get.assert_called_once()
                self.assertEqual(Path(result['files'][0]['path']).read_bytes(), png())
                self.assertTrue(store.read(state['submission'])['execution']['download_complete'])

    def test_mixed_remote_local_order_and_optional_placeholder(self):
        for placeholder, sources in ((True, self.sources), (False, ['https://example.com/a.png', str(self.local)])):
            real_probe = __import__('core.media_probe', fromlist=['probe_asset']).probe_asset
            def probe(asset):
                if asset['source'].startswith('https:'):
                    return {**asset, 'metadata': {'width': 400, 'height': 400}}
                return real_probe(asset)
            with patch('core.media_probe.probe_asset', side_effect=probe):
                work, spec = self.prepare(sources, placeholder=placeholder)
            _, body = self.post(work, spec)
            if placeholder:
                self.assertIsInstance(body['image'], list)
                self.assertTrue(body['image'][0].startswith('data:image/png;base64,'))
            else:
                self.assertEqual(body['image'][0], sources[0])
                self.assertTrue(body['image'][1].startswith('data:image/png;base64,'))

    def test_one_two_ten_images_use_saved_input_rates(self):
        for model, base, extra in (('pro', *self.pro_rates), ('flash', *self.flash_rates)):
            for count in (1, 2, 10):
                work, spec = self.prepare(self.sources*count, model=model)
                quote = store.read(work/(self.provider + '-priceing.json'))
                expected = round(base + (count-1)*extra, 6)
                self.assertEqual(quote['result']['amount'], {'min': expected, 'max': expected})
                with patch('core.cost_quote.estimate', side_effect=AssertionError('No repricing')):
                    self.assertEqual(len(consume_quote(spec, quote)[1]['assets']), count)

    def test_local_change_after_quote_is_blocked(self):
        work, spec = self.prepare()
        self.local.write_bytes(png()+b'changed')
        self.assert_blocked(work, spec)

    def test_local_change_between_compile_and_materialize_is_blocked(self):
        work, spec = self.prepare()
        compiled = consume_quote(spec, store.read(work/(self.provider + '-priceing.json')))[1]
        self.local.write_bytes(png()+b'changed')
        with self.assertRaisesRegex(ValueError, 'changed'):
            transport.payload({'compiled': compiled})

    def test_source_substitution_order_and_ids_are_bound(self):
        second = self.root/'second.png'; second.write_bytes(png())
        for mutation in ('swap', 'replace', 'id', 'catalog', 'reference'):
            work, spec = self.prepare([str(self.local), str(second)])
            if mutation == 'swap':
                spec['assets'].reverse()
            elif mutation == 'replace':
                spec['assets'][0]['source'] = 'https://example.com/replaced.png'
            else:
                record = store.read(work/'request.json')
                if mutation == 'id':
                    record['assets'][0]['id'] = 'changed'
                elif mutation == 'catalog':
                    record['assets'][0]['source'] = str(second)
                else:
                    record['providers'][self.provider]['assets'].reverse()
                store.write(work/'request.json', record)
            self.assert_blocked(work, spec)

    def test_no_optimization_preserves_every_original_character(self):
        prompt = '把背景改成蓝色\n保留产品。 不要优化！'
        work, spec = self.prepare(prompt=prompt)
        _, body = self.post(work, spec)
        self.assertEqual(body['prompt'], prompt)
        self.assertNotIn('optimize_prompt_options', body)

    def test_invalid_images_and_unsupported_supplier_do_not_probe(self):
        for assets in ([], self.sources*11, [{'kind': 'audio', 'source': str(self.local)}]):
            cost = {'provider': self.provider, 'model': 'seedream-5.0-flash', 'operation': 'image-to-image',
                    'size': '1K', 'assets': assets}
            with patch('core.media_probe.probe_asset') as probe, self.assertRaises(ValueError):
                calculate_asset_inputs(cost)
            probe.assert_not_called()
        with patch('core.media_probe.probe_asset') as probe, patch('sys.stdin', io.StringIO(json.dumps({**cost, 'provider': 'unknown'}))):
            with self.assertRaisesRegex(ValueError, 'Only basic text-to-image'):
                estimate_cost.run(SimpleNamespace(workdir=str(self.root)))
            probe.assert_not_called()

    def test_invalid_sources_and_coordinates_rejected(self):
        for value in (None, [], ['x']*11, [3], 'data:image/png;base64,AAAA', 'asset://image', 'http://example.com/a.png'):
            spec = image();spec['operation'] = 'image-to-image'
            spec['provider'] = self.provider
            spec['payload']['model'] = self.model_prefix + '-seedream-5-0-flash-260915'
            spec['assets'] = [{'id': 'source', 'kind': 'image', 'source': value, 'purpose': '参考图片'}]
            with self.subTest(value=value), self.assertRaises((ValueError, FileNotFoundError)):
                compile_request(spec)
        for coords in ('0 0 1000 999', '900 0 100 999', '1 2 3', 'a b c d'):
            work, spec = self.prepare(prompt='<bbox>'+coords+'</bbox> 改背景')
            self.assert_blocked(work, spec)
        work, spec = self.prepare(prompt='<point>100 200</point> 改颜色 <bbox>0 0 999 999</bbox>')
        self.post(work, spec)

    def test_invalid_reference_dimensions_are_rejected(self):
        for width, height in ((14, 100), (100, 2000), (6001, 6000)):
            with patch('core.media_probe.probe_asset', return_value={
                    'kind': 'image', 'source': str(self.local), 'metadata': {'width': width, 'height': height}}):
                with self.assertRaisesRegex(ValueError, 'dimensions'):
                    self.prepare()

    def test_unknown_submission_is_not_retried(self):
        work, spec = self.prepare()
        with config_fixture({self.key_env: 'fixture-only'}), \
                patch.object(self.adapter, 'request', side_effect=self.adapter.ProviderError('timeout', True)) as post:
            with self.assertRaises(self.adapter.ProviderError):
                submit.submit(work, spec, 'TEST CONFIRMATION')
            with self.assertRaisesRegex(ValueError, 'already attempted'):
                submit.submit(work, spec, 'TEST CONFIRMATION')
            post.assert_called_once()
        self.assertEqual(store.read(work/'submit-001.json')['execution']['state'], 'submission_unknown')


    def test_outer_asset_schema_and_purpose_are_enforced_before_post(self):
        work, original = self.prepare()
        invalid = []
        for field in ('id', 'kind', 'source', 'purpose'):
            spec = copy.deepcopy(original)
            spec['assets'][0].pop(field)
            invalid.append(spec)
        for field, value in (('id', ''), ('kind', 'audio'), ('purpose', ''), ('purpose', 'changed')):
            spec = copy.deepcopy(original)
            spec['assets'][0][field] = value
            invalid.append(spec)
        spec = copy.deepcopy(original)
        spec['assets'] *= 2
        invalid.append(spec)
        for spec in invalid:
            self.assert_blocked(work, spec)

    def test_payload_image_cannot_override_outer_assets(self):
        work, original = self.prepare()
        for value in (self.sources, self.sources[0], ['https://example.com/other.png'], None):
            spec = copy.deepcopy(original)
            spec['payload']['image'] = value
            self.assert_blocked(work, spec)

    def test_outer_asset_metadata_never_reaches_provider(self):
        work, spec = self.prepare()
        _, body = self.post(work, spec)
        for key in ('assets', 'id', 'kind', 'source', 'purpose'):
            self.assertNotIn(key, body)
        compiled = store.read(work/'submit-001.json')['execution']['compiled']
        self.assertEqual(compiled['assets'][0]['purpose'], '参考图片')
        self.assertEqual(compiled['assets'][0]['id'], '0')
