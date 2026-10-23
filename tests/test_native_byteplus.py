"""BytePlus native text-to-image uses its own models, USD quote and credentials."""
import base64
import copy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from commands import submit as submit_command, download as download_command
from core.request import compile_request
from core.cost_quote import consume_quote
from cost_fixture import calculate, save_with_cost
from core import submission_store as store
from providers import byteplus, volcengine, transport
from config_fixture import config_fixture
from test_runtime import png


def request(model='dola-seedream-5-0-flash-260915'):
    return {'provider': 'byteplus', 'operation': 'text-to-image', 'original_prompt': '正方形熊猫图片',
            'payload': {'model': model, 'prompt': '熊猫坐在草地上。构图比例偏好：1:1。',
                        'size': '1K', 'output_format': 'png', 'response_format': 'url',
                        'watermark': False, 'background': 'opaque',
                        'layer_decomposition': False}}


class NativeBytePlus(unittest.TestCase):
    def test_pro_and_flash_preserve_the_native_body(self):
        for model in ('dola-seedream-5-0-pro-260628', 'dola-seedream-5-0-flash-260915'):
            with self.subTest(model=model):
                spec=request(model);before=copy.deepcopy(spec)
                compiled=compile_request(spec)
                self.assertEqual(compiled['provider'], 'byteplus')
                self.assertEqual(transport.payload({'compiled': compiled}), before['payload'])
                self.assertEqual(spec, before)

    def test_usd_quote_is_reused_without_repricing(self):
        spec=request();quote=calculate(spec)
        self.assertEqual(quote['result']['currency'], 'USD')
        self.assertEqual(quote['result']['amount'], {'min': 0.018, 'max': 0.018})
        self.assertIn('docs.byteplus.com', quote['calculation']['pricing']['source'])
        with patch('core.cost_quote.estimate', side_effect=AssertionError('Unexpected repricing')):
            self.assertEqual(consume_quote(spec,quote)[3], quote['result'])

    def test_submit_and_download_use_byteplus_only(self):
        for model in ('dola-seedream-5-0-pro-260628', 'dola-seedream-5-0-flash-260915'):
            with self.subTest(model=model), tempfile.TemporaryDirectory() as tmp:
                work=Path(tmp);(work/'byteplus').mkdir()
                spec=request(model);save_with_cost(spec, work)
                response={'data':[{'b64_json':base64.b64encode(png()).decode()}], 'usage':{'generated_images':1}}
                with config_fixture({'BYTEPLUS_API_KEY':'fixture-only'}), \
                        patch.object(byteplus,'request',return_value=response) as post, \
                        patch.object(volcengine,'request') as other:
                    state=submit_command.submit(work,spec,'TEST CONFIRMATION')
                post.assert_called_once_with('POST','/images/generations',spec['payload'])
                other.assert_not_called()
                result=download_command.download(state['submission'])
                record=store.read(state['submission'])
                self.assertEqual(record['payload'],spec['payload'])
                self.assertTrue(record['execution']['download_complete'])
                self.assertEqual(result['billing_currency'],'USD')
                self.assertIsNone(result['actual_billed_amount'])
                self.assertEqual(Path(result['files'][0]['path']).read_bytes(),png())

    def test_missing_required_settings_are_rejected(self):
        spec=request()
        spec['payload'] = {k:spec['payload'][k] for k in ('model','prompt')}
        with self.assertRaisesRegex(ValueError, 'size'):
            compile_request(spec)

    def test_cross_supplier_models_and_aliases_are_rejected(self):
        for provider,model in [('byteplus','doubao-seedream-5-0-flash-260915'),
                               ('volcengine','dola-seedream-5-0-flash-260915'),
                               ('byteplus','seedream-5.0-flash')]:
            spec=request(model);spec['provider']=provider
            with self.subTest(provider=provider,model=model),self.assertRaises(ValueError):
                compile_request(spec)

    def test_volcengine_key_cannot_enable_byteplus(self):
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp);(work/'byteplus').mkdir();spec=request()
            save_with_cost(spec, work)
            with config_fixture({'VOLCENGINE_API_KEY':'fixture-only'}),patch.object(byteplus,'request') as post:
                with self.assertRaisesRegex(ValueError,'BYTEPLUS_API_KEY'):
                    submit_command.submit(work,spec,'TEST CONFIRMATION')
                post.assert_not_called()
            self.assertFalse((work/'submit-001.json').exists())

    def test_cost_change_never_posts(self):
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp);(work/'byteplus').mkdir();spec=request()
            save_with_cost(spec, work);spec['payload']['size']='2K'
            with patch.object(byteplus,'request') as post:
                with self.assertRaisesRegex(ValueError,'differs'):
                    submit_command.submit(work,spec,'TEST CONFIRMATION')
                post.assert_not_called()

    def test_invalid_or_unsupported_payloads_are_rejected(self):
        for fields in ({'n':2},{'size':'1024x768'},{'layer_decomposition':True},
                       {'background':'transparent'},{'optimize_prompt_options':{'mode':'fast'}}):
            spec=request();spec['payload'].update(fields)
            with self.subTest(fields=fields),self.assertRaises(ValueError):compile_request(spec)
        spec=request();spec['operation']='image-to-image'
        with self.assertRaisesRegex(ValueError,'Volcengine'):compile_request(spec)
