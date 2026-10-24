"""BytePlus uses the shared image-to-image contract with its own account and USD rates."""
import copy
import io
import json
from unittest.mock import patch

import test_native_volcengine_i2i as shared
from core import submission_store as store
from commands import submit
from providers import byteplus, volcengine
from config_fixture import config_fixture


class BytePlusImageToImage(shared.VolcengineImageToImage):
    provider = 'byteplus'
    adapter = byteplus
    other_adapter = volcengine
    model_prefix = 'dola'
    key_env = 'BYTEPLUS_API_KEY'
    pro_rates = (.045, .003)
    flash_rates = (.018, 0)

    def test_domestic_key_cannot_enable_byteplus_image_to_image(self):
        work, spec = self.prepare()
        with config_fixture({'VOLCENGINE_API_KEY': 'fixture-domestic'}), patch.object(byteplus, 'request') as post:
            with self.assertRaisesRegex(ValueError, 'BYTEPLUS_API_KEY'):
                submit.submit(work, spec, 'TEST CONFIRMATION')
            post.assert_not_called()
        self.assertFalse((work/'submit-001.json').exists())

    def test_byteplus_quote_uses_usd_and_rejects_domestic_model_or_quote(self):
        work, spec = self.prepare(self.sources*2, model='pro')
        path = work/'byteplus-priceing.json'
        quote = store.read(path)
        self.assertEqual(quote['result']['currency'], 'USD')
        self.assertEqual(quote['result']['amount'], {'min': .048, 'max': .048})
        self.assertIn('docs.byteplus.com', quote['calculation']['pricing']['source'])
        changed = copy.deepcopy(spec)
        changed['payload']['model'] = 'doubao-seedream-5-0-pro-260628'
        self.assert_blocked(work, changed)
        quote['calculation']['provider'] = 'volcengine'
        quote['result']['currency'] = 'CNY'
        store.write(path, quote)
        self.assert_blocked(work, spec)

    def test_actual_transport_posts_materialized_images_to_byteplus_only(self):
        work, spec = self.prepare()
        response = {'data': [{'url': 'https://example.com/result.png'}]}
        with config_fixture({'BYTEPLUS_API_KEY': 'fixture-overseas', 'VOLCENGINE_API_KEY': 'fixture-domestic'}), \
                patch('urllib.request.build_opener') as opener, patch.object(volcengine, 'request') as domestic:
            opener.return_value.open.return_value = io.BytesIO(json.dumps(response).encode())
            state = submit.submit(work, spec, 'TEST CONFIRMATION')
            request = opener.return_value.open.call_args.args[0]
            self.assertEqual(request.full_url, byteplus.BASE+'/images/generations')
            self.assertEqual(request.get_header('Authorization'), 'Bearer fixture-overseas')
            body = json.loads(request.data)
            self.assertEqual(body['model'], spec['payload']['model'])
            self.assertTrue(body['image'][0].startswith('data:image/png;base64,'))
            self.assertNotIn('assets', body)
            opener.return_value.open.assert_called_once()
            domestic.assert_not_called()
        self.assertEqual(state['state'], 'succeeded')
