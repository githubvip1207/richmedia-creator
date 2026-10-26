"""规格核验、交付缓存恢复与可选估价 ID 的离线回归。"""
import copy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from commands import deliver
from core import submission_store as store
from core.file_hash import sha256_file
from core.media_validate import verify_spec
from core.output_files import retrieve_outputs
from providers import compile_request, calculate_asset_inputs, consume_quote
from test_document_contract import image
from test_native_video import request, measured
from test_native_reference_video import request as reference_request, quote_for, metadata
from test_native_volcengine_layers import png


class DeliverySpecRegressions(unittest.TestCase):
    def frame_compiled(self, provider='volcengine', model='seedance-2.5'):
        spec = request(provider, model, 'first-frame')
        assets = [{**{k: v for k, v in a.items() if k != 'metadata'}, **a['metadata']}
                  for a in measured(spec)]
        return compile_request(spec, assets)

    def test_adaptive_rejects_square_output_for_wide_first_frame(self):
        for provider in ('volcengine', 'byteplus'):
            for model in ('seedance-2.5', 'seedance-2.0-mini'):
                with self.subTest(provider=provider, model=model):
                    compiled = self.frame_compiled(provider, model)
                    actual = {'width': 640, 'height': 640, 'duration': 4, 'has_audio': False}
                    self.assertEqual(verify_spec(None, 'video', compiled, actual)['status'], 'mismatch')
                    actual.update(width=854 if model == 'seedance-2.5' else 864,
                                  height=480 if model == 'seedance-2.5' else 496)
                    self.assertEqual(verify_spec(None, 'video', compiled, actual)['status'], 'matched')

    def test_adaptive_uses_source_display_dimensions_and_allows_rounding(self):
        compiled = self.frame_compiled()
        compiled['assets'][0]['metadata'].update(display_width=720, display_height=1280)
        actual = {'width': 480, 'height': 854, 'duration': 4.04, 'has_audio': False}
        self.assertEqual(verify_spec(None, 'video', compiled, actual)['status'], 'matched')
        actual.update(width=854, height=480)
        self.assertEqual(verify_spec(None, 'video', compiled, actual)['status'], 'mismatch')

    def test_auto_duration_enforces_each_model_range(self):
        for provider in ('volcengine', 'byteplus'):
            for model, maximum in (('seedance-2.5', 30), ('seedance-2.0-mini', 15)):
                spec = request(provider, model); spec['payload']['duration'] = -1
                compiled = compile_request(spec)
                dims = (854, 480) if model == 'seedance-2.5' else (864, 496)
                for seconds, expected in ((1, 'mismatch'), (maximum + 2, 'mismatch'),
                                          (4.04, 'matched'), (maximum + .04, 'matched')):
                    with self.subTest(provider=provider, model=model, seconds=seconds):
                        actual = dict(width=dims[0], height=dims[1], duration=seconds, has_audio=False)
                        self.assertEqual(verify_spec(None, 'video', compiled, actual)['status'], expected)

    def test_edit_uses_selected_video_for_aspect_and_duration(self):
        for provider in ('volcengine', 'byteplus'):
            spec = reference_request(provider, mode='edit')
            spec['assets'].append(dict(spec['assets'][0], id='target', source='https://example.com/target.mp4'))
            spec['estimate_context'] = {'target_asset_index': 1}
            quote = quote_for(spec, {1: {'width': 720, 'height': 1280, 'duration': 8}})
            _, compiled, _, _ = consume_quote(spec, quote)
            context = spec['estimate_context']
            for seconds, expected in ((7.6, 'matched'), (4, 'mismatch')):
                actual = dict(width=480, height=854, duration=seconds, has_audio=False)
                self.assertEqual(verify_spec(None, 'video', compiled, actual, context)['status'], expected)
            # 确保交付链路把保存的目标下标传入核验。
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / 'submit-001.json'
                record = {'estimate_context': context,
                          'execution': {'state': 'succeeded', 'compiled': compiled}}
                store.write(path, record)
                actual = dict(width=480, height=854, duration=7.6, has_audio=False)
                with patch('core.download.download_url', side_effect=lambda url, p: p.write_bytes(b'video fixture')), \
                        patch('core.media_validate.video_metadata', return_value=actual):
                    result = retrieve_outputs(record, path, {}, [({'url': 'https://example.com/out.mp4'}, 'video')], 'CNY')
                self.assertEqual(result['files'][0]['verification']['status'], 'matched')

    def test_exact_image_mismatch_is_delivered_with_original_and_difference(self):
        for provider in ('volcengine', 'byteplus'):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); work = root / 'task'; work.mkdir(); target = root / 'user'; target.mkdir()
                spec = image(provider); spec['payload']['size'] = '1024x1024'
                compiled = compile_request(spec)
                record = {'execution': {'state': 'succeeded', 'compiled': compiled},
                          'response': {'data': [{'url': 'https://example.com/out.png'}]}}
                path = work / 'submit-001.json'; store.write(path, record)
                original = png(512, 512)
                with patch('core.download.download_url', side_effect=lambda url, p: p.write_bytes(original)):
                    result = deliver.deliver(path, target)
                output = result['files'][0]
                self.assertEqual(Path(output['path']).read_bytes(), original)
                self.assertEqual(output['verification']['status'], 'mismatch')
                self.assertEqual(output['verification']['differences'][0]['field'], 'dimensions')
                self.assertTrue(store.read(path)['execution']['delivery_complete'])

    def completed_delivery(self, root):
        work = root / 'task'; work.mkdir(); target = root / 'user'; target.mkdir()
        path = work / 'submit-001.json'
        media = work / '00-image.png'; media.write_bytes(png())
        sidecar = work / 'layers.json'; sidecar.write_text('{"layers": []}')
        result = {'files': [{'path': str(media), 'sha256': sha256_file(media), 'kind': 'image'}],
                  'metadata': {'path': str(sidecar), 'sha256': sha256_file(sidecar)}}
        store.write(path, {'execution': {'state': 'succeeded', 'download_complete': True}, 'result': result})
        first = deliver.deliver(path, target)
        media.unlink(); sidecar.unlink()
        return path, target, first

    def test_missing_cache_reuses_complete_delivery_without_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, target, first = self.completed_delivery(Path(tmp))
            with patch('commands.status.status', side_effect=AssertionError('network')):
                self.assertEqual(deliver.deliver(path, target), first)
            self.assertTrue(store.read(path)['execution']['delivery_complete'])

    def test_missing_cache_can_publish_to_new_directory_from_verified_delivery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); path, target, first = self.completed_delivery(root)
            other = root / 'other'; other.mkdir()
            with patch('commands.status.status', side_effect=AssertionError('network')):
                second = deliver.deliver(path, other)
                third = deliver.deliver(path, target)
            self.assertEqual(Path(second['directory']).parent, other.resolve())
            for result in (second, third):
                self.assertEqual(Path(result['metadata']['path']).read_text(), '{"layers": []}')
                self.assertEqual(Path(result['files'][0]['path']).read_bytes(), png())
            self.assertTrue(Path(first['files'][0]['path']).exists())

    def test_copy_interruption_recovers_from_history_when_cache_is_gone(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); path, target, first = self.completed_delivery(root)
            other = root / 'other'; other.mkdir()
            def interrupted(source, output):
                output.write(b'incomplete')
                raise OSError('copy interrupted')
            with patch('commands.status.status', side_effect=AssertionError('network')):
                with patch('core.delivery_files.shutil.copyfileobj', side_effect=interrupted):
                    with self.assertRaisesRegex(OSError, 'copy interrupted'):
                        deliver.deliver(path, other)
                second = deliver.deliver(path, other)
            self.assertEqual(Path(second['files'][0]['path']).read_bytes(), png())
            self.assertTrue(store.read(path)['execution']['delivery_complete'])
            self.assertTrue(Path(first['metadata']['path']).exists())

    def test_changed_delivery_or_missing_sidecar_is_not_reused_without_cache(self):
        for change in ('media', 'metadata'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as tmp:
                path, target, first = self.completed_delivery(Path(tmp))
                if change == 'media':
                    Path(first['files'][0]['path']).write_bytes(b'user edit')
                else:
                    Path(first['metadata']['path']).unlink()
                with patch('commands.status.status', side_effect=OSError('offline')):
                    with self.assertRaisesRegex(OSError, 'offline'):
                        deliver.deliver(path, target)
                self.assertFalse(store.read(path)['execution']['delivery_complete'])

    def test_optional_quote_ids_work_for_all_asset_capabilities(self):
        for provider in ('volcengine', 'byteplus'):
            with tempfile.TemporaryDirectory() as tmp:
                source = Path(tmp) / 'source.png'; source.write_bytes(png())
                specs = []
                for operation in ('image-to-image', 'decompose-layers'):
                    spec = image(provider); spec['operation'] = operation
                    spec['payload']['layer_decomposition'] = operation == 'decompose-layers'
                    spec['assets'] = [dict(id='source', kind='image', source=str(source), purpose='输入素材')]
                    specs.append(spec)
                specs.append(request(provider, mode='first-frame'))
                specs.extend(reference_request(provider, operation=op, mode=mode) for op, mode in
                             [('reference-to-video', 'reference'), ('reference-to-video', 'edit'), ('extend-video', 'after')])
                for spec in specs:
                    with self.subTest(provider=provider, operation=spec['operation'], mode=spec.get('mode')):
                        inputs = dict(provider=provider, model=spec['payload']['model'], operation=spec['operation'],
                                      assets=[{k: a[k] for k in ('kind', 'source')} for a in spec['assets']])
                        inputs.update({k: v for k, v in spec['payload'].items() if k in ('size', 'resolution', 'ratio', 'duration')})
                        if 'mode' in spec: inputs['mode'] = spec['mode']
                        if spec['operation'] in ('image-to-image', 'decompose-layers'):
                            quote = calculate_asset_inputs(inputs)
                        else:
                            with patch('core.media_probe.probe_asset', side_effect=lambda a: {**a, 'metadata': metadata(a['kind'])}):
                                quote = calculate_asset_inputs(inputs)
                        _, compiled, _, _ = consume_quote(spec, quote)
                        self.assertEqual([a['id'] for a in compiled['assets']], [a['id'] for a in spec['assets']])
                        for field, value in (('id', 'wrong'), ('source', 'https://example.com/wrong'), ('kind', 'audio')):
                            changed = copy.deepcopy(quote); changed['calculation']['assets'][0][field] = value
                            with self.assertRaises(ValueError): consume_quote(spec, changed)
