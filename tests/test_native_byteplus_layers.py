"""BytePlus 图层拆分复用校验规则，使用独立凭证和美元报价。"""
import copy
import io
import json
from pathlib import Path
from unittest.mock import patch
import test_native_volcengine_layers as shared
import test_deliver as delivery_tests
from commands import submit, deliver
from core import submission_store as store
from providers import compile_request
from core.catalogs import ROOT
from providers.byteplus import client as byteplus
from providers.volcengine import client as volcengine
from config_fixture import config_fixture


class BytePlusLayers(shared.LayerLifecycle):
    provider = 'byteplus'
    adapter = byteplus
    other_adapter = volcengine
    model_prefix = 'dola'
    key_env = 'BYTEPLUS_API_KEY'
    rate_cases = (('pro', .0225, .765), ('flash', .018, .306))

    def test_domestic_key_cannot_enable_byteplus_layers(self):
        work, spec = self.prepare()
        with config_fixture({'VOLCENGINE_API_KEY':'fixture-domestic'}), patch.object(byteplus,'request') as post:
            with self.assertRaisesRegex(ValueError,'BYTEPLUS_API_KEY'):
                submit.submit(work,spec,'TEST CONFIRMATION')
            post.assert_not_called()
        self.assertFalse((work/'submit-001.json').exists())

    def test_byteplus_usd_quote_rejects_domestic_model_or_cost(self):
        for mutation in ('model', 'quote'):
            work, spec = self.prepare(model='pro')
            quote = store.read(work/'byteplus-priceing.json')
            self.assertEqual(quote['result']['currency'],'USD')
            self.assertIn('docs.byteplus.com',quote['calculation']['pricing']['source'])
            if mutation == 'model':
                spec['payload']['model']='doubao-seedream-5-0-pro-260628'
            else:
                quote['calculation']['provider']='volcengine'
                quote['result']['currency']='CNY'
                store.write(work/'byteplus-priceing.json',quote)
            with config_fixture({'BYTEPLUS_API_KEY':'fixture-only'}), patch.object(byteplus,'request') as post:
                with self.assertRaises(ValueError): submit.submit(work,spec,'TEST CONFIRMATION')
                post.assert_not_called()

    def test_transport_uses_only_byteplus_endpoint_and_credential(self):
        work, spec = self.prepare()
        response = {'data':shared.outputs()}
        with config_fixture({'BYTEPLUS_API_KEY':'fixture-overseas','VOLCENGINE_API_KEY':'fixture-domestic'}), patch('urllib.request.build_opener') as opener, patch.object(volcengine,'request') as domestic:
            opener.return_value.open.return_value=io.BytesIO(json.dumps(response).encode())
            state=submit.submit(work,spec,'TEST CONFIRMATION')
            request=opener.return_value.open.call_args.args[0]
            self.assertEqual(request.full_url,byteplus.BASE+'/images/generations')
            self.assertEqual(request.get_header('Authorization'),'Bearer fixture-overseas')
            body=json.loads(request.data)
            self.assertEqual(body['model'],spec['payload']['model'])
            self.assertTrue(body['layer_decomposition'])
            self.assertTrue(body['image'][0].startswith('data:image/png;base64,'))
            opener.return_value.open.assert_called_once(); domestic.assert_not_called()
        self.assertEqual(state['state'],'succeeded')

    def test_timeout_never_retries_paid_submission(self):
        work,spec=self.prepare()
        with config_fixture({'BYTEPLUS_API_KEY':'fixture-only'}), patch.object(byteplus,'request',side_effect=byteplus.ProviderError('timeout',True)) as post:
            with self.assertRaises(byteplus.ProviderError):submit.submit(work,spec,'TEST CONFIRMATION')
            with self.assertRaisesRegex(ValueError,'already attempted'):submit.submit(work,spec,'TEST CONFIRMATION')
            post.assert_called_once()
        self.assertEqual(store.read(work/'submit-001.json')['execution']['state'],'submission_unknown')

    def test_documented_layer_example_compiles_for_byteplus(self):
        document=(ROOT/'references/byteplus/decompose-layers.md').read_text()
        example=document.split('```jsonc\n',1)[1].split('```',1)[0]
        spec=json.loads('\n'.join(line.split(' //',1)[0] for line in example.splitlines()))
        spec['assets'][0]['source']=str(self.source)
        compiled=compile_request(spec)
        self.assertEqual(compiled['provider'],'byteplus')
        self.assertEqual(compiled['parameters']['size'],'1K')
        self.assertEqual(compiled['quantity'],17)


class BytePlusDelivery(delivery_tests.Delivery):
    provider = 'byteplus'
    adapter = byteplus
    other_adapter = volcengine
    model_prefix = 'dola'
    key_env = 'BYTEPLUS_API_KEY'

    def test_delivered_manifest_identifies_byteplus(self):
        _,submission=self.ready();target=self.output_directory()
        with patch('core.download.download_url',side_effect=self.media_get):
            result=deliver.deliver(submission,target)
        self.assertTrue(all(f['provider']=='byteplus' and f['model'].startswith('dola-') for f in result['files']))
        self.assertEqual(store.read(result['metadata']['path'])['provider'],'byteplus')
        self.assertTrue(store.read(submission)['execution']['delivery_complete'])
