"""视频原生接口约定及完整流程的离线测试；供应商调用全部使用模拟对象。"""
import copy
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from providers import compile_request
from core.catalogs import CATALOGS
from providers import consume_quote
from providers import calculate_asset_inputs
from core import media_validate
from core import submission_store as store
from commands import submit, status, deliver
from providers.volcengine import client as volcengine
from providers.byteplus import client as byteplus
from core.payload import payload
from core.http import ProviderError
from config_fixture import config_fixture


def request(provider='volcengine', model='seedance-2.5', mode=None):
    spec = {'provider': provider, 'operation': 'image-to-video' if mode else 'text-to-video',
            'original_prompt': '熊猫向镜头挥手',
            'payload': {'model': CATALOGS[provider]['models'][model]['id'],
                        'content': [{'type': 'text', 'text': '熊猫向镜头挥手'}],
                        'resolution': '480p', 'ratio': 'adaptive' if mode else '16:9',
                        'duration': 4, 'generate_audio': False, 'watermark': False,
                        'return_last_frame': False, 'service_tier': 'default'}}
    if provider == 'volcengine':
        spec['payload'].pop('service_tier')
    if model == 'seedance-2.5':
        spec['payload']['output_format'] = 'mp4'
    if mode:
        spec['assets'] = [{'id': str(i), 'kind': 'image', 'source': 'https://example.com/' + str(i) + '.png',
                           'purpose': '首帧' if i == 0 else '尾帧'}
                          for i in range(1 if mode == 'first-frame' else 2)]
    return spec


def measured(spec):
    return [{'id': a['id'], 'kind': 'image', 'source': a['source'],
             'metadata': {'width': 1280, 'height': 720, 'mime': 'image/png', 'bytes': 200}}
            for a in spec.get('assets', [])]


def prepare(work, spec):
    assets = measured(spec)
    with patch('core.media_probe.probe_asset', side_effect=assets):
        quote = calculate_asset_inputs({'provider': spec['provider'], 'model': spec['payload']['model'],
                'operation': spec['operation'],
                **{k: spec['payload'][k] for k in ('resolution', 'ratio', 'duration')},
                'assets': [{k: a[k] for k in ('id', 'kind', 'source')} for a in spec.get('assets', [])]})
    compiled = compile_request(spec, quote['calculation']['assets'])
    store.write(work/(spec['provider']+'-priceing.json'), quote)
    store.write(work/'request.json', {'original_prompt': spec['original_prompt'], 'optimized_prompt': compiled['prompt'],
                'intent': {'operation': spec['operation']}, 'assets': spec.get('assets', []),
                'providers': {spec['provider']: {'model': spec['payload']['model'], 'operation': spec['operation'],
                    'parameters': compiled['parameters'], 'assets': [{'id': a['id']} for a in spec.get('assets', [])]}}})
    return quote


class NativeVideo(unittest.TestCase):
    def test_all_models_modes_and_suppliers_compile_and_consume_real_quote(self):
        for provider in ('volcengine', 'byteplus'):
            for model in ('seedance-2.5', 'seedance-2.0', 'seedance-2.0-fast', 'seedance-2.0-mini'):
                for mode in (None, 'first-frame', 'first-last-frame'):
                    with self.subTest(provider=provider, model=model, mode=mode), tempfile.TemporaryDirectory() as tmp:
                        spec = request(provider, model, mode)
                        quote = prepare(Path(tmp), spec)
                        _, compiled, _, _ = consume_quote(spec, quote)
                        self.assertEqual(compiled['prompt'], spec['original_prompt'])
                        body = payload({'compiled': compiled})
                        self.assertEqual([x['role'] for x in body['content'][1:]],
                                         [] if not mode else ['first_frame'] if mode == 'first-frame' else ['first_frame', 'last_frame'])
                        self.assertEqual([x['image_url']['url'] for x in body['content'][1:]],
                                         [a['source'] for a in spec.get('assets', [])])

    def test_volcengine_mini_omits_service_tier_in_submitted_text_and_keyframe_video(self):
        for mode in (None, 'first-frame', 'first-last-frame'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                work = Path(tmp)
                spec = request('volcengine', 'seedance-2.0-mini', mode)
                prepare(work, spec)
                with config_fixture({volcengine.KEY_ENV: 'fixture'}), \
                        patch('commands.submit.require_dependencies'), \
                        patch.object(volcengine, 'request', return_value={'id': 'mini-task'}) as post:
                    state = submit.submit(work, spec, 'TEST CONFIRMATION ACCEPT UNKNOWN COST', accept_uncertain=True)
                self.assertEqual(state['state'], 'queued')
                post.assert_called_once()
                self.assertNotIn('service_tier', post.call_args.args[2])
                expected_roles = ([] if mode is None else ['first_frame'] if mode == 'first-frame'
                                  else ['first_frame', 'last_frame'])
                self.assertEqual([item['role'] for item in post.call_args.args[2]['content'][1:]], expected_roles)
                for value in ('default', 'flex', None):
                    invalid = copy.deepcopy(spec)
                    invalid['payload']['service_tier'] = value
                    with self.subTest(service_tier=value), self.assertRaisesRegex(ValueError, 'must omit service_tier'):
                        compile_request(invalid)

    def test_service_tier_matches_supplier_rules_for_all_models(self):
        for provider in ('volcengine', 'byteplus'):
            for model in ('seedance-2.5', 'seedance-2.0', 'seedance-2.0-fast', 'seedance-2.0-mini'):
                for mode in (None, 'first-frame', 'first-last-frame'):
                    with self.subTest(provider=provider, model=model, mode=mode):
                        spec = request(provider, model, mode)
                        assets = [{**{k: v for k, v in a.items() if k != 'metadata'}, **a['metadata']}
                                  for a in measured(spec)]
                        spec['payload'].pop('service_tier', None)
                        self.assertNotIn('service_tier', payload({'compiled': compile_request(spec, assets)}))
                        spec['payload']['service_tier'] = 'default'
                        if provider == 'volcengine':
                            with self.assertRaisesRegex(ValueError, 'must omit service_tier'):
                                compile_request(spec, assets)
                        else:
                            self.assertEqual(payload({'compiled': compile_request(spec, assets)})['service_tier'], 'default')

    def test_constraints_reject_wrong_models_fields_and_parameter_types(self):
        for changes in ({'duration': True}, {'duration': 3}, {'duration': 31}, {'resolution': '4k'},
                        {'generate_audio': 1}, {'ratio': '3:2'}, {'seed': 1}, {'camera_fixed': True},
                        {'frames': 97}, {'draft': True}, {'service_tier': 'flex'}, {'priority': True},
                        {'execution_expires_after': 20}, {'callback_url': 'http://example.com'},
                        {'output_format': 'avi'}, {'model': CATALOGS['byteplus']['models']['seedance-2.5']['id']}):
            with self.subTest(changes=changes):
                spec = request(); spec['payload'].update(changes)
                with self.assertRaises(ValueError): compile_request(spec)
        for model in ('seedance-2.0-fast', 'seedance-2.0-mini'):
            spec = request(model=model); spec['payload']['resolution'] = '1080p'
            with self.assertRaises(ValueError): compile_request(spec)
        spec = request(model='seedance-2.0'); spec['payload']['resolution'] = '4k'
        self.assertEqual(compile_request(spec)['parameters']['resolution'], '4k')
        spec['payload']['output_format'] = 'mp4'
        with self.assertRaises(ValueError): compile_request(spec)

    def test_audio_and_model_duration_limits(self):
        spec = request()
        spec['payload'].update(duration=30, generate_audio=True)
        compiled = compile_request(spec)
        self.assertTrue(compiled['parameters']['generate_audio'])
        self.assertFalse(compiled['parameters']['return_last_frame'])
        self.assertEqual(compiled['parameters']['output_format'], 'mp4')
        for model in ('seedance-2.0', 'seedance-2.0-fast', 'seedance-2.0-mini'):
            spec = request(model=model); spec['payload']['duration'] = 15
            compile_request(spec)
            spec['payload']['duration'] = 16
            with self.assertRaises(ValueError): compile_request(spec)

    def test_fixed_output_settings_and_internal_options_cannot_be_overridden(self):
        for provider in ('volcengine', 'byteplus'):
            for fields in ({'priority': 0}, {'execution_expires_after': 172800}, {'draft': False}):
                with self.subTest(provider=provider,fields=fields):
                    spec = request(provider); spec['payload'].update(fields)
                    with self.assertRaises(ValueError): compile_request(spec)

    def test_requirement_only_needs_user_decision_parameters(self):
        for provider, adapter in (('volcengine',volcengine),('byteplus',byteplus)):
            with self.subTest(provider=provider), tempfile.TemporaryDirectory() as tmp:
                work=Path(tmp); spec=request(provider,mode='first-frame'); prepare(work,spec)
                record=store.read(work/'request.json')
                parameters=record['providers'][provider]['parameters']
                for key in ('watermark','return_last_frame','output_format','service_tier'):
                    parameters.pop(key, None)
                store.write(work/'request.json',record)
                with config_fixture({adapter.KEY_ENV:'fixture'}), patch('commands.submit.require_dependencies'), \
                        patch.object(adapter,'request',return_value={'id':'task'}) as post:
                    state=submit.submit(work,spec,'TEST')
                self.assertEqual(state['state'],'queued')
                post.assert_called_once()

    def test_missing_settings_and_content_bypass_are_rejected(self):
        for key in set(request()['payload']) - {'output_format', 'service_tier'}:
            spec = request(); spec['payload'].pop(key)
            with self.subTest(missing=key), self.assertRaises(ValueError): compile_request(spec)
        for content in ([], [{'type':'text', 'text':'hi --dur 30'}],
                        [{'type':'image_url','image_url':{'url':'https://example.com/a.png'}}],
                        [{'type':'text','text':'a'},{'type':'text','text':'b'}]):
            spec = request(); spec['payload']['content'] = content
            with self.assertRaises(ValueError): compile_request(spec)

    def test_image_count_ratio_size_and_cost_measurements_are_checked(self):
        spec = request(mode='first-frame')
        for mutate in ('count', 'ratio', 'dimensions', 'size', 'order'):
            changed = copy.deepcopy(spec); assets = measured(spec)
            if mutate == 'count': changed['assets'] = []
            if mutate == 'ratio': changed['payload']['ratio'] = '16:9'
            if mutate == 'dimensions': assets[0]['metadata']['width'] = 200
            if mutate == 'size': assets[0]['metadata']['bytes'] = 30*1024*1024
            if mutate == 'order': assets[0]['id'] = 'other'
            with self.subTest(mutate=mutate), self.assertRaises(ValueError): compile_request(changed, [{**{k:v for k,v in a.items() if k != 'metadata'}, **a['metadata']} for a in assets])
        spec = request(); spec['assets'] = request(mode='first-frame')['assets']
        with self.assertRaises(ValueError): compile_request(spec)

    def test_byteplus_adaptive_25_quote_is_known_and_arbitrary_ratio_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec = request('byteplus', mode='first-frame')
            quote = prepare(Path(tmp), spec)
            self.assertEqual(quote['result']['status'], 'estimate')
            spec['payload']['duration'] = -1
            quote = prepare(Path(tmp), spec)
            self.assertLess(quote['result']['amount']['min'], quote['result']['amount']['max'])
            assets = measured(spec); assets[0]['metadata']['width'] = 1234
            from providers import calculate_inputs
            quote = calculate_inputs({'provider':'byteplus','model':'seedance-2.5','operation':'image-to-video',
                    'resolution':'480p','ratio':'adaptive','duration':4,'input_images':1}, measured_assets=assets)
            self.assertEqual(quote['result']['status'], 'estimate')

    def test_frame_count_infers_roles_without_mode_and_ratio_is_fixed(self):
        for provider in ('volcengine','byteplus'):
            for model in ('seedance-2.5','seedance-2.0','seedance-2.0-fast','seedance-2.0-mini'):
                for count in (1,2):
                    with self.subTest(provider=provider,model=model,count=count), tempfile.TemporaryDirectory() as tmp:
                        spec=request(provider,model,'first-frame' if count==1 else 'first-last-frame')
                        quote=prepare(Path(tmp),spec)
                        compiled=compile_request(spec,quote['calculation']['assets'])
                        self.assertNotIn('mode',spec)
                        self.assertNotIn('mode',compiled)
                        self.assertNotIn('mode',compiled['parameters'])
                        self.assertNotIn('mode',quote['input'])
                        self.assertNotIn('mode',quote['calculation'])
                        self.assertEqual([a['role'] for a in compiled['payload_template']['content'][1:]],
                                         ['first_frame'] if count==1 else ['first_frame','last_frame'])
                        spec['payload']['ratio']='16:9'
                        with self.assertRaisesRegex(ValueError,'ratio=adaptive'):
                            compile_request(spec,quote['calculation']['assets'])

    def test_image_requirement_needs_neither_ratio_nor_mode(self):
        for provider,adapter in (('volcengine',volcengine),('byteplus',byteplus)):
            with self.subTest(provider=provider), tempfile.TemporaryDirectory() as tmp:
                work=Path(tmp);spec=request(provider,mode='first-frame');prepare(work,spec)
                record=store.read(work/'request.json')
                record['providers'][provider]['parameters'].pop('ratio')
                store.write(work/'request.json',record)
                with config_fixture({adapter.KEY_ENV:'fixture'}),patch('commands.submit.require_dependencies'), \
                        patch.object(adapter,'request',return_value={'id':'task'}) as post:
                    state=submit.submit(work,spec,'TEST')
                self.assertEqual(state['state'],'queued')
                self.assertEqual(post.call_args.args[2]['ratio'],'adaptive')
                self.assertNotIn('mode',post.call_args.args[2])

    def test_obsolete_mode_is_rejected_for_submit_and_estimate(self):
        for count in (0,3):
            spec=request(mode='first-last-frame')
            spec['assets']=[] if count==0 else spec['assets']+[dict(spec['assets'][0],id='extra')]
            with self.assertRaises(ValueError):compile_request(spec)
        with tempfile.TemporaryDirectory() as tmp:
            spec=request(mode='first-frame');quote=prepare(Path(tmp),spec)
            spec['mode']='first-frame'
            with self.assertRaises(ValueError):compile_request(spec,quote['calculation']['assets'])
            inputs=dict(quote['input'],mode='first-frame')
            with patch('core.media_probe.probe_asset') as probe, self.assertRaisesRegex(ValueError,'does not accept mode'):
                calculate_asset_inputs(inputs)
            probe.assert_not_called()

    def test_requirement_changes_block_post(self):
        for change in ('audio', 'mode', 'purpose', 'missing-setting'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as tmp:
                work = Path(tmp); spec = request(mode='first-frame'); prepare(work, spec)
                record = store.read(work/'request.json')
                if change == 'audio': spec['payload']['generate_audio'] = True
                if change == 'mode': record['providers']['volcengine']['parameters']['mode'] = 'first-last-frame'
                if change == 'purpose': record['assets'][0]['purpose'] = '别的用途'
                if change == 'missing-setting': record['providers']['volcengine']['parameters'].pop('generate_audio')
                store.write(work/'request.json', record)
                with patch.object(volcengine, 'request') as post, self.assertRaises(ValueError):
                    submit.submit(work, spec, 'TEST')
                post.assert_not_called()

    def test_mocked_async_lifecycle_both_suppliers_and_unknown_submission_never_reposts(self):
        for provider, adapter in (('volcengine', volcengine), ('byteplus', byteplus)):
            with self.subTest(provider=provider), tempfile.TemporaryDirectory() as tmp:
                work = Path(tmp); spec = request(provider, mode='first-last-frame'); prepare(work, spec)
                with config_fixture({adapter.KEY_ENV:'fixture-only'}), patch('commands.submit.require_dependencies'), \
                        patch.object(adapter, 'request', return_value={'id':'video-task'}) as post:
                    state = submit.submit(work, spec, 'TEST')
                self.assertEqual(state['state'], 'queued'); post.assert_called_once()
                self.assertEqual(post.call_args.args[1], '/contents/generations/tasks')
                with patch.object(adapter, 'status', side_effect=[{'id':'video-task','status':'running'},
                      {'id':'video-task','status':'succeeded','content':{'video_url':'https://example.com/a.mp4'},'usage':{'completion_tokens':100}}]):
                    self.assertEqual(status.status(state['submission'])['state'], 'running')
                    self.assertTrue(status.status_result(status.status(state['submission']))['success'])
                saved = store.read(state['submission'])
                self.assertEqual(saved['response'], {'id':'video-task'})
                self.assertEqual(len(saved['queries']), 2)
            with tempfile.TemporaryDirectory() as tmp:
                work = Path(tmp); spec = request(provider); prepare(work, spec)
                with config_fixture({adapter.KEY_ENV:'fixture-only'}), patch('commands.submit.require_dependencies'), \
                        patch.object(adapter, 'request', side_effect=ProviderError('timeout', uncertain=True)) as post:
                    with self.assertRaises(ProviderError): submit.submit(work, spec, 'TEST')
                    with self.assertRaises(ValueError): submit.submit(work, spec, 'TEST AGAIN')
                post.assert_called_once()
                self.assertEqual(store.read(work/'submit-001.json')['execution']['state'], 'submission_unknown')

    def test_local_frame_is_base64_and_changed_bytes_invalidate_quote(self):
        import base64
        from test_runtime import png
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)/'frame.png'; source.write_bytes(png())
            spec = request(mode='first-frame'); spec['assets'][0]['source'] = str(source)
            inputs = {'provider':'volcengine','model':'seedance-2.5','operation':'image-to-video',
                      'resolution':'480p','ratio':'adaptive','duration':4,
                      'assets':[{k: spec['assets'][0][k] for k in ('id','kind','source')}]}
            quote = calculate_asset_inputs(inputs)
            _, compiled, _, _ = consume_quote(spec, quote)
            body = payload({'compiled':compiled})
            uri = body['content'][1]['image_url']['url']
            self.assertEqual(base64.b64decode(uri.split(',')[1]), png())
            self.assertNotIn('base64,', json.dumps(compiled))
            source.write_bytes(png()+b'changed')
            with self.assertRaisesRegex(ValueError, 'changed after'):
                consume_quote(spec, quote)
            with self.assertRaisesRegex(ValueError, 'changed after'):
                payload({'compiled':compiled})

    def test_unknown_cost_requires_explicit_acceptance_before_post(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp); spec = request(model='seedance-2.0',mode='first-frame')
            quote = prepare(work,spec)
            self.assertEqual(quote['result']['status'], 'estimate')
            quote['result'].update(status='unknown', amount={'min':None,'max':None})
            store.write(work / 'volcengine-priceing.json', quote)
            with config_fixture({'VOLCENGINE_API_KEY':'fixture'}), patch('commands.submit.require_dependencies'), \
                    patch.object(volcengine,'request',return_value={'id':'task'}) as post:
                with self.assertRaisesRegex(ValueError, 'unknown'):
                    submit.submit(work,spec,'TEST')
                post.assert_not_called()
                state = submit.submit(work,spec,'TEST ACCEPT UNKNOWN',accept_uncertain=True)
            self.assertEqual(state['state'],'queued'); post.assert_called_once()

    @unittest.skipUnless(shutil.which('ffmpeg'), 'ffmpeg fixture generator unavailable')
    def test_deliver_decodes_actual_video_and_rejects_header_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)/'task'; work.mkdir(); video = work/'fixture.mp4'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=blue:s=320x320:r=24',
                            '-t','0.25','-c:v','libx264','-pix_fmt','yuv420p',str(video)], check=True)
            self.assertTrue(media_validate.valid_media(video, 'video'))
            bad = work/'bad.mp4'; bad.write_bytes(b'\x00\x00\x00\x18ftypisom' + b'\0'*30)
            self.assertFalse(media_validate.valid_media(bad, 'video'))
            spec = request(); prepare(work, spec)
            with config_fixture({'VOLCENGINE_API_KEY':'fixture'}), patch('commands.submit.require_dependencies'), \
                    patch.object(volcengine,'request',return_value={'id':'task'}):
                state = submit.submit(work,spec,'TEST')
            reply = {'id':'task','status':'succeeded','content':{'video_url':'https://example.com/a.mp4'}}
            dest = Path(tmp)/'delivered'; dest.mkdir()
            with patch.object(volcengine,'status',return_value=reply), \
                    patch('core.download.download_url',side_effect=lambda url,path:shutil.copyfile(video,path)) as download:
                result = deliver.deliver(state['submission'], dest)
                again = deliver.deliver(state['submission'], dest)
            self.assertEqual(result['files'], again['files']); download.assert_called_once()
            self.assertEqual(result['files'][0]['metadata']['width'], 320)
            self.assertFalse(result['files'][0]['metadata']['has_audio'])
