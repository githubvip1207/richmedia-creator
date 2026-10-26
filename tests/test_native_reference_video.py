"""多模态接口约定及完整流程的离线测试；全部付费请求均使用模拟对象。"""
import base64
import copy
import json
import io
import shutil
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from providers import compile_request
from core.catalogs import CATALOGS, ROOT
from providers import consume_quote
from providers import calculate_asset_inputs
from core import submission_store as store
from commands import cost as cost_command, submit, status, deliver
from providers.volcengine import client as volcengine
from providers.byteplus import client as byteplus
from core.payload import payload
from core.http import ProviderError
from config_fixture import config_fixture
from test_runtime import png

MODES = [('reference-to-video', 'reference'), ('reference-to-video', 'edit'),
         ('extend-video', 'before'), ('extend-video', 'after')]


def request(provider='volcengine', model='seedance-2.5', operation='reference-to-video', mode='reference'):
    text = {'reference': '参考视频1的动作生成熊猫挥手的新视频。',
            'edit': '编辑视频1，将背景替换为雪山，保留熊猫的动作与镜头。',
            'before': '向前延长视频1，在原视频开始之前让熊猫从草地走入画面。',
            'after': '向后延长视频1，熊猫接着挥手并转身离开。'}[mode]
    body = {'model': CATALOGS[provider]['models'][model]['id'],
            'content': [{'type': 'text', 'text': text}], 'resolution': '480p',
            'ratio': '16:9' if mode == 'reference' else 'adaptive',
            'duration': -1 if model == 'seedance-2.5' and mode == 'edit' else 4,
            'generate_audio': False, 'watermark': False, 'return_last_frame': False}
    if model == 'seedance-2.5':
        body.update(output_format='mp4', omni_reference_task_type='extend' if operation == 'extend-video' else mode)
    return {'provider': provider, 'operation': operation, 'mode': mode, 'original_prompt': text,
            'payload': body, 'assets': [{'id': 'source', 'kind': 'video',
                 'source': 'https://example.com/source.mp4', 'purpose': text}]}


def metadata(kind):
    if kind == 'image':
        return {'width': 1280, 'height': 720, 'bytes': 200, 'mime': 'image/png'}
    result = {'duration': 4, 'bytes': 200, 'format_name': 'mov,mp4' if kind == 'video' else 'wav',
              'codec_name': 'h264' if kind == 'video' else 'pcm_s16le'}
    if kind == 'video':
        result.update(width=1280, height=720, frame_rate=24)
    return result


def cost_input(spec):
    return {'provider': spec['provider'], 'model': spec['payload']['model'],
            'operation': spec['operation'], 'mode': spec['mode'],
            **{k: spec['payload'][k] for k in ('resolution', 'ratio', 'duration')},
            'assets': [{k: a[k] for k in ('id', 'kind', 'source')} for a in spec['assets']],
            **({'estimate_context': spec['estimate_context']} if 'estimate_context' in spec else {}),
            **({'target_asset_id': spec['target_asset_id']} if 'target_asset_id' in spec else {})}


def quote_for(spec, overrides=None):
    measured = [{**{k: a[k] for k in ('id', 'kind', 'source')},
                 'metadata': metadata(a['kind'])} for a in spec['assets']]
    for index, changes in (overrides or {}).items():
        measured[index]['metadata'].update(changes)
    with patch('core.media_probe.probe_asset', side_effect=measured):
        return calculate_asset_inputs(cost_input(spec))


def prepare(work, spec):
    quote = quote_for(spec)
    store.write(work / (spec['provider'] + '-priceing.json'), quote)
    selected = {'model': spec['payload']['model'], 'operation': spec['operation'], 'mode': spec['mode'],
                'parameters': {k: spec['payload'][k] for k in ('resolution', 'ratio', 'duration', 'generate_audio')},
                'assets': [{'id': a['id']} for a in spec['assets']]}
    if 'target_asset_id' in spec:
        selected['target_asset_id'] = spec['target_asset_id']
    if 'estimate_context' in spec:
        selected['estimate_context'] = spec['estimate_context']
    store.write(work / 'request.json', {'original_prompt': spec['original_prompt'],
                'optimized_prompt': spec['payload']['content'][0]['text'],
                'intent': {'operation': spec['operation']}, 'assets': spec['assets'],
                'providers': {spec['provider']: selected}})
    return quote


class ReferenceVideo(unittest.TestCase):
    def test_all_models_modes_and_suppliers_consume_quotes_and_preserve_payloads(self):
        for provider in ('volcengine', 'byteplus'):
            for model in ('seedance-2.5', 'seedance-2.0', 'seedance-2.0-fast', 'seedance-2.0-mini'):
                for operation, mode in MODES:
                    with self.subTest(provider=provider, model=model, mode=mode):
                        spec = request(provider, model, operation, mode)
                        spec['assets'] += [{'id': k, 'kind': k, 'source': 'https://example.com/' + k,
                                            'purpose': '参考外观' if k == 'image' else '参考声音'} for k in ('image', 'audio')]
                        original = copy.deepcopy(spec)
                        quote = quote_for(spec)
                        _, compiled, _, _ = consume_quote(spec, quote)
                        actual = payload({'compiled': compiled})
                        self.assertEqual([c['role'] for c in actual['content'][1:]],
                                         ['reference_video', 'reference_image', 'reference_audio'])
                        self.assertEqual(actual['content'][0], spec['payload']['content'][0])
                        self.assertEqual(compiled['mode'], mode)
                        self.assertNotIn('service_tier', actual)
                        self.assertNotIn('mode', actual)
                        if model == 'seedance-2.5':
                            self.assertEqual(actual['omni_reference_task_type'], 'extend' if operation == 'extend-video' else mode)
                        else:
                            self.assertNotIn('omni_reference_task_type', actual)
                            self.assertNotIn('output_format', actual)
                        self.assertEqual(quote['calculation']['input_video_seconds'], [4])
                        self.assertEqual(quote['result']['currency'], 'CNY' if provider == 'volcengine' else 'USD')
                        self.assertEqual(spec, original)

    def test_audio_only_is_supported_only_on_25(self):
        for provider in ('volcengine', 'byteplus'):
            for model in ('seedance-2.5', 'seedance-2.0', 'seedance-2.0-mini'):
                with self.subTest(provider=provider, model=model):
                    spec = request(provider, model)
                    spec['assets'] = [{'id': 'voice', 'kind': 'audio', 'source': 'https://example.com/voice.wav', 'purpose': '参考声音'}]
                    if model == 'seedance-2.5':
                        quote = quote_for(spec)
                        _, compiled, _, _ = consume_quote(spec, quote)
                        self.assertEqual(payload({'compiled': compiled})['content'][1]['role'], 'reference_audio')
                        self.assertEqual(quote['result']['status'], 'estimate')
                    else:
                        with self.assertRaisesRegex(ValueError, 'audio-only'):
                            quote_for(spec)

    def test_task_type_mode_and_locked_settings_are_checked(self):
        for operation, mode in MODES:
            spec = request(operation=operation, mode=mode)
            quote = quote_for(spec)
            for change in ({'omni_reference_task_type': 'auto'}, {'omni_reference_task_type': 'wrong'},
                           {'service_tier': 'default'}, {'duration': True}, {'seed': 1}):
                with self.subTest(mode=mode, change=change), self.assertRaises(ValueError):
                    bad = copy.deepcopy(spec); bad['payload'].update(change)
                    compile_request(bad, quote['calculation']['assets'])
            if mode in ('edit', 'before', 'after'):
                bad = copy.deepcopy(spec); bad['payload']['ratio'] = '16:9'
                with self.assertRaisesRegex(ValueError, 'ratio'):
                    quote_for(bad)
            if mode == 'edit':
                bad = copy.deepcopy(spec); bad['payload']['duration'] = 4
                with self.assertRaisesRegex(ValueError, 'duration=-1'):
                    quote_for(bad)
            for key in ('mode',):
                bad = copy.deepcopy(spec); bad.pop(key)
                with self.assertRaises(ValueError):
                    compile_request(bad, quote['calculation']['assets'])
        spec = request(model='seedance-2.0'); spec['payload']['omni_reference_task_type'] = 'reference'
        with self.assertRaisesRegex(ValueError, 'only supported'):
            compile_request(spec, quote_for(spec)['calculation']['assets'])

    def test_local_video_and_asset_ids_stop_before_media_access(self):
        for source in ('/tmp/source.mp4', 'asset://source', 'http://example.com/source.mp4'):
            spec = request(); spec['assets'][0]['source'] = source
            with patch('core.media_probe.probe_asset') as probe, self.assertRaisesRegex(ValueError, 'HTTPS'):
                calculate_asset_inputs(cost_input(spec))
            probe.assert_not_called()

    def test_measured_media_limits_and_formats_are_enforced(self):
        changes = [{'duration': 1}, {'duration': 31}, {'bytes': 201 * 1024 * 1024}, {'bytes': None},
                   {'width': 100}, {'height': 100}, {'frame_rate': 23}, {'frame_rate': 61},
                   {'codec_name': 'av1'}, {'format_name': 'matroska,webm'}]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ValueError):
                quote_for(request(), {0: change})
        spec = request(mode='edit')
        with self.assertRaises(ValueError): quote_for(spec, {0: {'duration': 3}})
        for kind in ('image', 'video', 'audio'):
            spec = request()
            spec['assets'] = [{'id': str(i), 'kind': kind, 'source': 'https://example.com/' + str(i), 'purpose': '参考'}
                              for i in range(CATALOGS['volcengine']['models']['seedance-2.5']['limits'][kind] + 1)]
            with self.subTest(kind=kind), self.assertRaises(ValueError): quote_for(spec)
        for kind, change in [('audio', {'format_name': 'ogg'}), ('audio', {'bytes': 16 * 1024 * 1024}),
                             ('image', {'width': 200}), ('image', {'bytes': 30 * 1024 * 1024})]:
            spec = request(); spec['assets'] = [{'id': 'ref', 'kind': kind, 'source': 'https://example.com/ref', 'purpose': '参考'}]
            with self.subTest(kind=kind, change=change), self.assertRaises(ValueError): quote_for(spec, {0: change})

    def test_edit_and_extension_need_video_and_unambiguous_target(self):
        for operation, mode in MODES[1:]:
            spec = request(operation=operation, mode=mode)
            spec['assets'][0]['kind'] = 'image'
            with self.assertRaisesRegex(ValueError, 'needs a video'): quote_for(spec)
            spec = request(operation=operation, mode=mode)
            spec['assets'].append(dict(spec['assets'][0], id='second', source='https://example.com/second.mp4'))
            ambiguous = quote_for(spec)
            self.assertEqual(ambiguous['result']['status'], 'estimate')
            with self.assertRaisesRegex(ValueError, 'Multiple videos'):
                consume_quote(spec, ambiguous)
            for index in (True, -1, 2):
                spec['estimate_context'] = {'target_asset_index': index}
                with self.subTest(mode=mode, index=index), self.assertRaises(ValueError): quote_for(spec)
            spec['estimate_context'] = {'target_asset_index': 1}
            quote = quote_for(spec)
            self.assertEqual(quote['calculation']['target_asset_index'], 1)
            consume_quote(spec, quote)

    def test_source_order_and_identity_are_bound_to_quote(self):
        spec = request(); quote = quote_for(spec)
        for key, value in [('id', 'other'), ('source', 'https://example.com/other.mp4'), ('kind', 'image')]:
            bad = copy.deepcopy(spec); bad['assets'][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): consume_quote(bad, quote)
        bad = copy.deepcopy(spec); bad['assets'][0]['role'] = 'first_frame'
        with self.assertRaisesRegex(ValueError, 'outer reference'): consume_quote(bad, quote)

    def test_mode_and_target_changes_require_new_confirmation(self):
        for change in ('mode', 'target', 'context', 'purpose', 'ratio'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as tmp:
                work = Path(tmp)
                spec = request(operation='extend-video', mode='after')
                prepare(work, spec)
                record = store.read(work / 'request.json')
                selected = record['providers']['volcengine']
                if change == 'mode': selected['mode'] = 'before'
                if change == 'target': selected['assets'] = []
                if change == 'context': selected['estimate_context'] = {'target_asset_index': 0}
                if change == 'purpose': record['assets'][0]['purpose'] = 'another role'
                if change == 'ratio': selected['parameters']['ratio'] = '16:9'
                store.write(work / 'request.json', record)
                with patch.object(volcengine, 'request') as post, self.assertRaises(ValueError):
                    submit.submit(work, spec, 'TEST', accept_uncertain=True)
                post.assert_not_called()

    def test_unknown_cost_acceptance_and_unknown_submission_never_repost(self):
        for provider, adapter in [('volcengine', volcengine), ('byteplus', byteplus)]:
            with self.subTest(provider=provider), tempfile.TemporaryDirectory() as tmp:
                work = Path(tmp); spec = request(provider); quote = prepare(work, spec)
                quote = store.read(work / (provider + '-priceing.json'))
                quote['result'].update(status='unknown', amount={'min':None,'max':None})
                store.write(work / (provider + '-priceing.json'), quote)
                with config_fixture({adapter.KEY_ENV: 'fixture'}), patch.object(adapter, 'request', side_effect=ProviderError('timeout', True)) as post:
                    with self.assertRaisesRegex(ValueError, 'unknown'):
                        submit.submit(work, spec, 'TEST')
                    post.assert_not_called()
                    with self.assertRaises(ProviderError): submit.submit(work, spec, 'TEST ACCEPT UNKNOWN', accept_uncertain=True)
                    with self.assertRaises(ValueError): submit.submit(work, spec, 'TEST AGAIN', accept_uncertain=True)
                    post.assert_called_once()
                    self.assertEqual(store.read(work / 'submit-001.json')['execution']['state'], 'submission_unknown')

    def test_local_images_and_audio_encode_only_on_submission_and_changed_bytes_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / 'image.png'; image.write_bytes(png())
            audio = Path(tmp) / 'audio.wav'
            with wave.open(str(audio), 'wb') as out:
                out.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
                out.writeframes(b'\0' * 64000)
            spec = request()
            spec['assets'] = [{'id': 'image', 'kind': 'image', 'source': str(image), 'purpose': '参考外观'},
                              {'id': 'audio', 'kind': 'audio', 'source': str(audio), 'purpose': '参考声音'}]
            quote = calculate_asset_inputs(cost_input(spec))
            _, compiled, _, _ = consume_quote(spec, quote)
            body = payload({'compiled': compiled})
            self.assertEqual(base64.b64decode(body['content'][1]['image_url']['url'].split(',')[1]), png())
            self.assertEqual(base64.b64decode(body['content'][2]['audio_url']['url'].split(',')[1]), audio.read_bytes())
            self.assertNotIn('base64,', json.dumps(compiled))
            audio.write_bytes(audio.read_bytes() + b'changed')
            with self.assertRaisesRegex(ValueError, 'changed after'): consume_quote(spec, quote)
            with self.assertRaisesRegex(ValueError, 'changed after'): payload({'compiled': compiled})

    def test_documented_examples_compile_for_their_supplier_and_mode(self):
        for provider in ('volcengine', 'byteplus'):
            for operation in ('reference-to-video', 'extend-video'):
                with self.subTest(provider=provider, operation=operation):
                    guide = (ROOT / 'references' / provider / (operation + '.md')).read_text()
                    example = guide.split('```jsonc\n', 1)[1].split('```', 1)[0]
                    spec = json.loads('\n'.join(line.split(' //', 1)[0] for line in example.splitlines()))
                    for asset in spec['assets']:
                        asset['source'] = 'https://example.com/' + asset['id']
                    quote = quote_for(spec)
                    _, compiled, _, _ = consume_quote(spec, quote)
                    self.assertEqual(compiled['provider'], provider)
                    self.assertEqual(compiled['operation'], operation)
                    self.assertEqual(compiled['mode'], spec['mode'])

    def test_estimate_command_accepts_new_capabilities(self):
        for operation, mode in MODES:
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                spec = request(operation=operation, mode=mode)
                measured = [{**cost_input(spec)['assets'][0], 'metadata': metadata('video')}]
                with patch('sys.stdin', io.StringIO(json.dumps(cost_input(spec)))), \
                        patch('commands.cost.fx_from_env', return_value=None), \
                        patch('core.media_probe.probe_asset', side_effect=measured):
                    result = cost_command.run(SimpleNamespace(workdir=tmp))
                self.assertEqual(result['calculation']['mode'], mode)
                self.assertTrue(Path(result['cost_file']).is_file())

    @unittest.skipUnless(shutil.which('ffmpeg'), 'ffmpeg fixture generator unavailable')
    def test_full_async_delivery_for_both_suppliers_and_every_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp); video = base / 'fixture.mp4'
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=blue:s=320x320:r=24',
                            '-t', '4', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(video)], check=True)
            for provider, adapter in [('volcengine', volcengine), ('byteplus', byteplus)]:
                for operation, mode in MODES:
                    with self.subTest(provider=provider, mode=mode):
                        work = base / (provider + mode); work.mkdir()
                        spec = request(provider, operation=operation, mode=mode); prepare(work, spec)
                        with config_fixture({adapter.KEY_ENV: 'fixture'}), patch.object(adapter, 'request', return_value={'id': 'task'}) as post:
                            state = submit.submit(work, spec, 'TEST ACCEPT UNKNOWN', accept_uncertain=True)
                        post.assert_called_once()
                        self.assertEqual(post.call_args.args[1], '/contents/generations/tasks')
                        with patch.object(adapter, 'status', return_value={'id': 'task', 'status': 'running'}):
                            self.assertEqual(status.status(state['submission'])['state'], 'running')
                        reply = {'id': 'task', 'status': 'succeeded', 'content': {'video_url': 'https://example.com/result.mp4'}}
                        dest = base / ('delivered-' + provider + mode); dest.mkdir()
                        with patch.object(adapter, 'status', return_value=reply), \
                                patch('core.download.download_url', side_effect=lambda url, path: shutil.copyfile(video, path)) as download:
                            result = deliver.deliver(state['submission'], dest)
                            self.assertEqual(deliver.deliver(state['submission'], dest)['files'], result['files'])
                        download.assert_called_once()
                        self.assertEqual(result['files'][0]['metadata']['duration'], 4)
                        self.assertTrue(store.read(state['submission'])['execution']['delivery_complete'])
