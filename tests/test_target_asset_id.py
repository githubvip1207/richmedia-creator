"""顶层目标素材 ID 的两家供应商回归；所有付费请求均模拟。"""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from providers import consume_quote, compile_request
from commands import submit
from core import submission_store as store
from core.media_validate import verify_spec
from test_native_reference_video import request, quote_for, prepare
from config_fixture import config_fixture


class TargetAssetId(unittest.TestCase):
    def spec(self, provider, operation='reference-to-video', mode='edit'):
        spec = request(provider, operation=operation, mode=mode)
        spec['assets'].insert(0, dict(id='portrait', kind='image', source='https://example.com/person.png', purpose='外观'))
        spec['assets'].append(dict(spec['assets'][1], id='main', source='https://example.com/main.mp4'))
        spec['target_asset_id'] = 'main'
        return spec

    def test_id_controls_quote_and_verification_for_edit_and_extension(self):
        for provider in ('volcengine', 'byteplus'):
            for operation, mode in [('reference-to-video','edit'), ('extend-video','before'), ('extend-video','after')]:
                with self.subTest(provider=provider, mode=mode):
                    spec = self.spec(provider, operation, mode)
                    quote = quote_for(spec, {2: dict(width=720, height=1280, duration=8)})
                    self.assertEqual(quote['calculation']['target_asset_id'], 'main')
                    self.assertEqual(quote['calculation']['assumed_output_dimensions'], [480,854])
                    if mode == 'edit':
                        self.assertEqual(quote['calculation']['assumed_output_duration'], [7.6,8])
                    _, compiled, _, _ = consume_quote(spec, quote)
                    self.assertEqual(compiled['target_asset_id'], 'main')
                    actual = dict(width=480,height=854,duration=7.6 if mode=='edit' else 4,has_audio=False)
                    self.assertEqual(verify_spec(None,'video',compiled,actual)['status'],'matched')
                    self.assertNotIn('target_asset_id', json.dumps(compiled['payload_template']))

    def test_reordering_assets_preserves_named_target(self):
        for provider in ('volcengine','byteplus'):
            spec=self.spec(provider)
            for order in ((0,1,2),(2,0,1)):
                reordered=copy.deepcopy(spec)
                reordered['assets']=[spec['assets'][i] for i in order]
                overrides={i:dict(width=720,height=1280,duration=8) for i,a in enumerate(reordered['assets']) if a['id']=='main'}
                quote=quote_for(reordered,overrides)
                self.assertEqual(quote['calculation']['assumed_output_duration'],[7.6,8])
                consume_quote(reordered,quote)

    def test_missing_unknown_nonvideo_and_conflicting_targets_are_rejected(self):
        for provider in ('volcengine','byteplus'):
            spec=self.spec(provider);quote=quote_for(spec)
            for value in ('missing','portrait','',None,1):
                changed=copy.deepcopy(spec);changed['target_asset_id']=value
                with self.subTest(provider=provider,value=value), self.assertRaises(ValueError):
                    quote_for(changed)
            missing=copy.deepcopy(spec);missing.pop('target_asset_id')
            # 缺少多视频目标的旧估价可以保留区间，但禁止提交。
            with self.assertRaisesRegex(ValueError,'target_asset_id'):
                compile_request(missing,quote['calculation']['assets'])
            conflict=copy.deepcopy(spec);conflict['estimate_context']={'target_asset_index':1}
            with self.assertRaisesRegex(ValueError,'conflicts'):
                quote_for(conflict)

    def test_target_is_bound_to_quote_and_requirement_before_post(self):
        for provider in ('volcengine','byteplus'):
            with tempfile.TemporaryDirectory() as tmp:
                work=Path(tmp);spec=self.spec(provider);quote=prepare(work,spec)
                changed=copy.deepcopy(spec);changed['target_asset_id']='source'
                with self.assertRaisesRegex(ValueError,'differs from cost artifact'):
                    consume_quote(changed,quote)
                removed=copy.deepcopy(spec);removed.pop('target_asset_id')
                with self.assertRaises(ValueError):consume_quote(removed,quote)
                record=store.read(work/'request.json');record['providers'][provider]['target_asset_id']='source'
                store.write(work/'request.json',record)
                from providers import get_capability
                capability=get_capability(provider,spec['operation'])
                with patch.object(capability,'submit') as post, self.assertRaisesRegex(ValueError,'target_asset_id differs'):
                    submit.submit(work,spec,'TEST')
                post.assert_not_called()

    def test_both_suppliers_submit_id_only_as_local_audit_field(self):
        for provider in ('volcengine','byteplus'):
            with tempfile.TemporaryDirectory() as tmp:
                work=Path(tmp);spec=self.spec(provider);prepare(work,spec)
                from providers import get_capability
                capability=get_capability(provider,spec['operation'])
                with config_fixture({provider.upper()+'_API_KEY':'fixture'}), \
                        patch('commands.submit.require_dependencies'), \
                        patch.object(capability,'submit',return_value={'id':'paid-task'}) as post:
                    state=submit.submit(work,spec,'TEST')
                body=post.call_args.args[1]
                self.assertNotIn('target_asset_id',body)
                record=store.read(state['submission'])
                self.assertEqual(record['target_asset_id'],'main')
                self.assertEqual(record['execution']['compiled']['target_asset_id'],'main')

    def test_single_video_omission_and_reference_scope(self):
        for provider in ('volcengine','byteplus'):
            spec=request(provider,mode='edit');quote=quote_for(spec)
            consume_quote(spec,quote)
            spec['target_asset_id']='source';consume_quote(spec,quote_for(spec))
            spec=request(provider);spec['target_asset_id']='source'
            with self.assertRaisesRegex(ValueError,'only supported'):
                quote_for(spec)

    def test_legacy_index_still_resolves_existing_records(self):
        for provider in ('volcengine','byteplus'):
            spec=self.spec(provider);spec.pop('target_asset_id')
            spec['estimate_context']={'target_asset_index':2}
            quote=quote_for(spec,{2:dict(width=720,height=1280,duration=8)})
            _,compiled,_,_=consume_quote(spec,quote)
            actual=dict(width=480,height=854,duration=7.6,has_audio=False)
            self.assertEqual(verify_spec(None,'video',compiled,actual,spec['estimate_context'])['status'],'matched')
