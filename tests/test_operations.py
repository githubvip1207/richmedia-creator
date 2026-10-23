"""The public API exposes exactly seven capabilities and explicit modes."""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from commands import submit as submit_command
from core.operations import OPERATIONS, internal_operation
from core.request import CATALOGS
from core.legacy_request import compile_request
from core.cost_quote import consume_quote
from cost_fixture import calculate, as_native, save_with_cost
from core.media_probe import calculate_asset_inputs
from test_runtime import video, asset


class SevenOperations(unittest.TestCase):
    def test_catalogs_expose_only_seven_capabilities(self):
        expected={'text-to-image','image-to-image','decompose-layers','text-to-video',
                  'image-to-video','reference-to-video','extend-video'}
        self.assertEqual(set(OPERATIONS),expected)
        for catalog in CATALOGS.values():
            union=set()
            for model in catalog['models'].values():
                union.update(model['operations'])
                for operation,modes in model['modes'].items():
                    self.assertEqual(modes,list(OPERATIONS[operation]))
            self.assertEqual(union,expected)

    def test_old_fine_grained_operations_are_rejected(self):
        for old in ('edit-image','fuse-images','region-edit','first-frame','first-last-frame','edit-video'):
            with self.subTest(old=old):
                with self.assertRaisesRegex(ValueError,'operation must be one of'):
                    internal_operation({'operation':old})
                with self.assertRaisesRegex(ValueError,'operation must be one of'):
                    calculate_asset_inputs({'provider':'volcengine','model':'seedream-5.0-flash',
                                            'operation':old,'size':'1K'})

    def test_invalid_or_missing_mode_is_rejected(self):
        for operation,modes in OPERATIONS.items():
            invalid=[None,'bad',[]] if modes else ['edit']
            for mode in invalid:
                with self.subTest(operation=operation,mode=mode), self.assertRaises(ValueError):
                    internal_operation({'operation':operation,'mode':mode})

    def test_image_compilation_and_cost_record_need_no_mode(self):
        spec={'provider':'volcengine','model':'seedream-5.0-flash','operation':'image-to-image',
              'prompt':'修改背景','parameters':{'ratio':'1:1'},'assets':[asset('image')]}
        compiled=compile_request(spec)
        self.assertEqual(compiled['operation'],'image-to-image')
        self.assertNotIn('mode',compiled)
        quote=calculate(spec)
        self.assertEqual(quote['calculation']['operation'],'image-to-image')
        self.assertNotIn('mode',quote['calculation'])
        changed=copy.deepcopy(spec);changed['parameters']['size']='2K'
        with self.assertRaisesRegex(ValueError,'differs'):
            consume_quote(as_native(changed),quote)

    def test_reference_modes_control_native_video_task_type(self):
        for mode,task_type in [('reference','reference'),('edit','edit')]:
            compiled=compile_request(video(operation='reference-to-video',mode=mode,assets=[asset()],
                                           parameters={'ratio':'adaptive','duration':-1}))
            self.assertEqual(compiled['payload_template']['omni_reference_task_type'],task_type)
            self.assertEqual(compiled['operation'],'reference-to-video')
            self.assertEqual(compiled['mode'],mode)
        for mode in ('before','after'):
            compiled=compile_request(video(operation='extend-video',mode=mode,assets=[asset()],
                                           parameters={'resolution':'480p','duration':4}))
            self.assertEqual(compiled['payload_template']['omni_reference_task_type'],'extend')
            self.assertEqual(compiled['mode'],mode)

    def test_image_to_image_counts_and_prices_without_mode(self):
        for count in (1, 2, 10):
            with self.subTest(count=count):
                spec={'provider':'volcengine','model':'seedream-5.0-pro','operation':'image-to-image',
                      'prompt':'参考输入图片修改背景或融合主体','parameters':{'size':'1K','ratio':'1:1'},
                      'assets':[asset('image') for _ in range(count)]}
                compiled=compile_request(spec)
                self.assertNotIn('mode',compiled)
                self.assertNotIn('mode',compiled['payload_template'])
                self.assertEqual(len(compiled['payload_template']['image']),count)
                expected=round(0.3+max(count-1,0)*0.02,6)
                quote=calculate(spec)
                self.assertEqual(list(quote['result']['amount'].values()),[expected,expected])
                self.assertNotIn('mode',quote['calculation'])
        for count in (0,11):
            with self.subTest(count=count), self.assertRaises(ValueError):
                compile_request({**spec,'assets':[asset('image') for _ in range(count)]})

    def test_image_to_image_no_mode_reaches_provider_unchanged(self):
        import tempfile
        from unittest.mock import patch
        from core import submission_store as store
        from config_fixture import config_fixture
        from providers import volcengine
        spec={'provider':'volcengine','model':'seedream-5.0-flash','operation':'image-to-image',
              'prompt':'保留产品，换成灰色背景','parameters':{'size':'1K','ratio':'1:1'},
              'assets':[asset('image')]}
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp);(work/'volcengine').mkdir()
            spec = save_with_cost(spec, work)
            with config_fixture({'VOLCENGINE_API_KEY':'fixture-only'}), \
                    patch.object(volcengine,'request',return_value={'data':[{'url':'https://example.com/result.png'}]}) as post:
                submit_command.submit(work,spec,'TEST CONFIRMATION')
            payload=post.call_args.args[2]
            self.assertEqual(payload['image'],spec['payload']['image'])
            self.assertNotIn('mode',payload)
            self.assertEqual(payload['prompt'],spec['payload']['prompt'])
