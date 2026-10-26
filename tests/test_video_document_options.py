"""视频文档参数的请求、确认绑定和尾帧交付回归；供应商调用全部模拟。"""

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from providers import compile_request, get_capability, get_provider, consume_quote
from core import submission_store as store
from core.payload import payload
from commands import submit, deliver
from config_fixture import config_fixture
from test_native_video import request as video_request, measured, prepare as prepare_video
from test_native_reference_video import request as reference_request, quote_for, prepare as prepare_reference


class VideoDocumentOptions(unittest.TestCase):
    def cases(self, provider, model='seedance-2.5'):
        for mode in (None, 'first-frame', 'first-last-frame'):
            yield video_request(provider, model, mode)
        for operation, mode in (('reference-to-video', 'reference'), ('reference-to-video', 'edit'),
                                ('extend-video', 'before'), ('extend-video', 'after')):
            yield reference_request(provider, model, operation, mode)

    def compile(self, spec):
        if spec['operation'] in ('reference-to-video', 'extend-video'):
            quote = quote_for(spec)
            return consume_quote(spec, quote)[1]
        assets = [{**{k: v for k, v in a.items() if k != 'metadata'}, **a['metadata']}
                  for a in measured(spec)]
        return compile_request(spec, assets)

    def test_documented_options_reach_native_payload_for_all_video_modes(self):
        options = dict(watermark=True, return_last_frame=True, output_format='mov',
                       callback_url='https://example.com/video-callback', safety_identifier='user-hash-123')
        for provider in ('volcengine', 'byteplus'):
            for spec in self.cases(provider):
                with self.subTest(provider=provider, operation=spec['operation'], mode=spec.get('mode')):
                    spec['payload'].pop('service_tier', None)
                    spec['payload'].update(options)
                    compiled = self.compile(spec)
                    body = payload({'compiled': compiled})
                    for key, value in options.items():
                        self.assertEqual(body[key], value)
                        self.assertEqual(compiled['parameters'][key], value)
                    self.assertEqual(body['content'][0], spec['payload']['content'][0])
                    self.assertNotIn('service_tier', body)

    def test_service_tier_is_optional_only_for_byteplus_in_every_model_and_mode(self):
        for provider in ('volcengine', 'byteplus'):
            for model in ('seedance-2.5', 'seedance-2.0', 'seedance-2.0-fast', 'seedance-2.0-mini'):
                for spec in self.cases(provider, model):
                    with self.subTest(provider=provider, model=model, operation=spec['operation'], mode=spec.get('mode')):
                        spec['payload'].pop('service_tier', None)
                        self.assertNotIn('service_tier', payload({'compiled': self.compile(spec)}))
                        spec['payload']['service_tier'] = 'default'
                        if provider == 'volcengine':
                            with self.assertRaisesRegex(ValueError, 'must omit service_tier'):
                                self.compile(spec)
                        else:
                            self.assertEqual(payload({'compiled': self.compile(spec)})['service_tier'], 'default')

    def test_optional_output_format_defaults_to_mp4_without_changing_api_body(self):
        for provider in ('volcengine', 'byteplus'):
            for spec in self.cases(provider):
                with self.subTest(provider=provider, operation=spec['operation'], mode=spec.get('mode')):
                    spec['payload'].pop('output_format')
                    compiled = self.compile(spec)
                    self.assertEqual(compiled['parameters']['output_format'], 'mp4')
                    self.assertNotIn('output_format', payload({'compiled': compiled}))

    def test_invalid_options_fail_for_every_video_capability(self):
        invalid = [('watermark', 1), ('return_last_frame', 0), ('output_format', 'avi'),
                   ('output_format', None), ('callback_url', 'http://example.com/callback'),
                   ('callback_url', 'https://'), ('callback_url', 'https://user:pass@example.com/callback'),
                   ('callback_url', None), ('safety_identifier', ''), ('safety_identifier', '中文'),
                   ('safety_identifier', 'x' * 65), ('safety_identifier', 123), ('service_tier', 'flex')]
        for provider in ('volcengine', 'byteplus'):
            for spec in self.cases(provider):
                for key, value in invalid:
                    with self.subTest(provider=provider, operation=spec['operation'], mode=spec.get('mode'), field=key, value=value):
                        bad = copy.deepcopy(spec)
                        bad['payload'][key] = value
                        with self.assertRaises(ValueError):
                            self.compile(bad)

    def test_changed_options_require_confirmation_before_post(self):
        options = dict(watermark=True, return_last_frame=True, output_format='mov',
                       callback_url='https://example.com/callback', safety_identifier='user-1')
        for provider in ('volcengine', 'byteplus'):
            for operation in ('text-to-video', 'image-to-video', 'reference-to-video', 'extend-video'):
                for key, value in options.items():
                    with self.subTest(provider=provider, operation=operation, field=key), tempfile.TemporaryDirectory() as tmp:
                        work = Path(tmp)
                        if operation in ('text-to-video', 'image-to-video'):
                            spec = video_request(provider, mode='first-frame' if operation == 'image-to-video' else None)
                            prepare_video(work, spec)
                        else:
                            spec = reference_request(provider, operation=operation, mode='after' if operation == 'extend-video' else 'reference')
                            prepare_reference(work, spec)
                        record = store.read(work / 'request.json')
                        record['providers'][provider]['parameters'].pop(key, None)
                        store.write(work / 'request.json', record)
                        spec['payload'][key] = value
                        capability = get_capability(provider, operation)
                        with patch.object(capability, 'submit') as post, self.assertRaisesRegex(ValueError, 'missing from request.json'):
                            submit.submit(work, spec, 'TEST')
                        post.assert_not_called()
                        record['providers'][provider]['parameters'][key] = value
                        store.write(work / 'request.json', record)
                        with config_fixture({provider.upper() + '_API_KEY': 'fixture'}), \
                                patch('commands.submit.require_dependencies'), \
                                patch.object(capability, 'submit', return_value={'id': 'video-task'}) as post:
                            submit.submit(work, spec, 'TEST')
                        self.assertEqual(post.call_args.args[1][key], value)
                        post.assert_called_once()

    def test_mov_and_requested_jpeg_tail_are_delivered_without_new_generation(self):
        for provider in ('volcengine', 'byteplus'):
            with self.subTest(provider=provider), tempfile.TemporaryDirectory() as tmp:
                work = Path(tmp) / 'task'
                work.mkdir()
                destination = Path(tmp) / 'project'
                destination.mkdir()
                spec = video_request(provider)
                spec['payload'].update(output_format='mov', return_last_frame=True)
                compiled = self.compile(spec)
                response = {'id': 'task', 'status': 'succeeded', 'content':
                            {'video_url': 'https://example.com/result.mov', 'last_frame_url': 'https://example.com/tail.jpg'}}
                record = dict(spec, response={'id': 'task'}, queries=[{'response': response}],
                              execution={'state': 'succeeded', 'compiled': compiled, 'task_id': 'task'})
                record_path = work / 'submit-001.json'
                store.write(record_path, record)
                capability = get_capability(provider, 'text-to-video')
                def download(url, path):
                    path.write_bytes(b'\xff\xd8\xffjpeg' if url.endswith('.jpg') else b'0000ftypmov-data')
                metadata = dict(width=854, height=480, duration=4, has_audio=False)
                with patch('core.download.download_url', side_effect=download), \
                        patch('core.media_validate.video_metadata', return_value=metadata), \
                        patch('core.media_validate.valid_media', return_value=True), \
                        patch('core.cost_reconcile.image_dimensions', return_value=[854, 480]):
                    result = capability.deliver(record, record_path)
                self.assertEqual([Path(f['path']).suffix for f in result['files']], ['.mov', '.jpeg'])
                with patch.object(get_provider(provider)['adapter'], 'request') as network:
                    delivered = deliver.deliver(record_path, destination)
                network.assert_not_called()
                self.assertEqual([Path(f['path']).suffix for f in delivered['files']], ['.mov', '.jpeg'])
                self.assertTrue(store.read(record_path)['execution']['delivery_complete'])
