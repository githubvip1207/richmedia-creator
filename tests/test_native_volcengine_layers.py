"""使用真实 PNG 探测和模拟生成、下载请求验证图层完整流程。"""
import base64
import copy
import io
import json
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from commands import init, cost as cost_command, submit, status, deliver as download
from core import submission_store as store
from providers import compile_request
from providers.volcengine.decompose_layers import validate_layer_metadata
from providers import calculate_asset_inputs
from core.layers import validate_layer_outputs
from providers.volcengine import client as volcengine
from providers.byteplus import client as byteplus
from config_fixture import config_fixture


def png(width=512, height=512, alpha=True):
    def chunk(kind, data):
        return struct.pack('!I', len(data))+kind+data+struct.pack('!I', zlib.crc32(kind+data)&0xffffffff)
    pixel = b'\xff\0\0\x80' if alpha else b'\xff\0\0'
    return (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR', struct.pack('!2I5B',width,height,8,6 if alpha else 2,0,0,0))
            +chunk(b'IDAT',zlib.compress((b'\0'+pixel*width)*height))+chunk(b'IEND',b''))


def outputs(count=2):
    return [{'url': 'https://example.com/output.png', 'size': '512x512', 'output_format':'png',
             'z_index': i, **({'name': '标题', 'description': '标题文字',
                'bounding_box': {'absolute':[0,0,512,512], 'normalized':[0,0,1000,1000]}} if i else {})}
            for i in range(count)]


class LayerLifecycle(unittest.TestCase):
    provider = 'volcengine'
    adapter = volcengine
    other_adapter = byteplus
    model_prefix = 'doubao'
    key_env = 'VOLCENGINE_API_KEY'
    rate_cases = (('pro', .15, 5.1), ('flash', .12, 2.04))

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root/'input.png'; self.source.write_bytes(png())

    def prepare(self, model='flash', remote=False):
        asset = {'id':'source', 'kind':'image',
                 'source':'https://example.com/input.png' if remote else str(self.source), 'purpose':'待拆分图片'}
        body = {'model': self.model_prefix+'-seedream-5-0-'+model+('-260915' if model == 'flash' else '-260628'),
                'size':'1K','output_format':'png','response_format':'url','watermark':False,
                'background':'opaque','layer_decomposition':True}
        body['prompt'] = '拆出标题与人物'
        spec = {'provider':self.provider,'operation':'decompose-layers','original_prompt':'请拆分图片',
                'assets':[asset], 'payload':body}
        record = {'original_prompt':spec['original_prompt'],
                  'optimized_prompt':body['prompt'],
                  'intent':{'operation':spec['operation']}, 'assets':[asset],
                  'providers':{self.provider:{'model':body['model'],'operation':spec['operation'],
                    'parameters':{'size':'1K'},
                    'assets':[{'id':'source'}]}}}
        with patch.object(init, 'WORK_ROOT', self.root):
            work = Path(init.initialize(json.dumps(record))['workdir'])
        cost = {'provider':self.provider,'model':body['model'],'operation':spec['operation'],'size':'1K',
                'assets':[{k:v for k,v in asset.items() if k != 'purpose'}]}
        with patch('sys.stdin', io.StringIO(json.dumps(cost))):
            if remote:
                with patch('core.media_probe.probe_asset', return_value={**cost['assets'][0],
                        'metadata':{'width':512,'height':512,'mime':'image/png','bytes':1000}}):
                    cost_command.run(SimpleNamespace(workdir=str(work)))
            else:
                cost_command.run(SimpleNamespace(workdir=str(work)))
        return work, spec

    def post(self, work, spec, response):
        with config_fixture({self.key_env:'fixture-only'}), patch.object(self.adapter,'request',return_value=response) as post, patch.object(self.other_adapter,'request') as other:
            state = submit.submit(work,spec,'TEST CONFIRMATION')
            post.assert_called_once(); other.assert_not_called()
            return state, post.call_args.args[2]

    def test_both_models_quote_submit_status_download_sidecar_and_resume(self):
        for model, low, high in self.rate_cases:
            work, spec = self.prepare(model)
            quote = store.read(work/(self.provider+'-priceing.json'))
            self.assertEqual(quote['result']['amount'],{'min':low,'max':high})
            entries = outputs(17); entries.reverse()
            state, body = self.post(work,spec,{'data':entries,'usage':{'generated_images':17}})
            self.assertTrue(body['image'][0].startswith('data:image/png;base64,'))
            self.assertEqual(body['prompt'],spec['payload']['prompt'])
            self.assertNotIn('data:image',Path(state['submission']).read_text())
            self.assertTrue(status.run(SimpleNamespace(submission=state['submission'],wait=0))['success'])
            with patch('core.download.download_url',side_effect=lambda url,path:path.write_bytes(png())) as get:
                result=download._download(state['submission']); download._download(state['submission'])
                self.assertEqual(get.call_count,17)
            meta=store.read(result['metadata']['path'])
            self.assertEqual([e['z_index'] for e in meta['layers']], list(range(17)))
            self.assertNotIn('https:',json.dumps(meta))
            self.assertEqual(meta['layers'][1]['bounding_box']['normalized'],[0,0,1000,1000])
            self.assertTrue(store.read(state['submission'])['execution']['download_complete'])

    def test_remote_passes_url_and_preserves_confirmed_prompt(self):
        work,spec=self.prepare(remote=True)
        _,body=self.post(work,spec,{'data':outputs(1)})
        self.assertEqual(body['prompt'],spec['payload']['prompt'])
        self.assertEqual(body['image'],['https://example.com/input.png'])

    def test_prompt_required_and_auto_marker_cannot_bypass_confirmation(self):
        work, original = self.prepare()
        for value in (None, '', '   ', 3):
            spec = copy.deepcopy(original)
            if value is None: spec['payload'].pop('prompt')
            else: spec['payload']['prompt'] = value
            with config_fixture({self.key_env:'fixture-only'}), patch.object(self.adapter,'request') as post:
                with self.assertRaisesRegex(ValueError,'payload.prompt is required'):
                    submit.submit(work,spec,'TEST CONFIRMATION')
                post.assert_not_called()
        record = store.read(work/'request.json')
        record['providers'][self.provider]['parameters']['prompt'] = 'auto'
        store.write(work/'request.json', record)
        with config_fixture({self.key_env:'fixture-only'}), patch.object(self.adapter,'request') as post:
            with self.assertRaises(ValueError): submit.submit(work,original,'TEST CONFIRMATION')
            post.assert_not_called()

    def test_unoptimized_text_is_preserved_and_changed_prompt_is_blocked(self):
        work, spec = self.prepare()
        text = '拆分图片中的主要元素。\n不要优化，保留所有文字！'
        spec['original_prompt'] = spec['payload']['prompt'] = text
        record = store.read(work/'request.json')
        record['original_prompt'] = record['optimized_prompt'] = text
        store.write(work/'request.json',record)
        changed = copy.deepcopy(spec); changed['payload']['prompt'] += ' changed'
        with config_fixture({self.key_env:'fixture-only'}), patch.object(self.adapter,'request') as post:
            with self.assertRaisesRegex(ValueError,'prompt differs'): submit.submit(work,changed,'TEST CONFIRMATION')
            post.assert_not_called()
        _, body = self.post(work,spec,{'data':outputs(1)})
        self.assertEqual(body['prompt'],text)
        self.assertNotIn('optimize_prompt_options',body)

    def test_bad_inputs_rejected_before_probe(self):
        for assets in ([],[{'kind':'audio','source':'/bad'}],[{'kind':'image','source':'/bad'}]*2):
            with patch('core.media_probe.probe_asset') as probe, self.assertRaises(ValueError):
                calculate_asset_inputs({'provider':self.provider,'model':'seedream-5.0-flash','operation':'decompose-layers','size':'auto','assets':assets})
            probe.assert_not_called()
        for meta in ({'width':511,'height':512,'mime':'image/png'},
                     {'width':512,'height':512,'mime':'image/webp'},
                     {'width':512,'height':512,'mime':'image/png','bytes':31*1024*1024}):
            with self.assertRaises(ValueError): validate_layer_metadata(meta)

    def test_settings_and_changed_sources_block_before_post(self):
        work,original=self.prepare()
        variants=[]
        for key,value in (('size','1024x1024'),('layer_decomposition',False),('background','transparent'),('image',[str(self.source)]),('output_format','jpeg'),('optimize_prompt_options',{'mode':'standard'})):
            spec=copy.deepcopy(original);spec['payload'][key]=value;variants.append(spec)
        for spec in variants:
            with config_fixture({self.key_env:'fixture-only'}),patch.object(self.adapter,'request') as post:
                with self.assertRaises(ValueError):submit.submit(work,spec,'TEST CONFIRMATION')
                post.assert_not_called()
        self.source.write_bytes(png()+b'changed')
        with self.assertRaisesRegex(ValueError,'changed'):
            from providers import consume_quote
            consume_quote(original,store.read(work/(self.provider+'-priceing.json')))

    def test_any_layer_error_fails_whole_task(self):
        work,spec=self.prepare()
        state,_=self.post(work,spec,{'data':[outputs()[0],{'error':{'code':'failed','message':'failed'}}]})
        self.assertEqual(state['state'],'failed')
        with self.assertRaises(ValueError):download._download(state['submission'])

    def test_malformed_metadata_preserves_unknown_and_never_resubmits(self):
        for case in ('missing_base','duplicate','missing_box','bad_box','too_many'):
            work,spec=self.prepare();entries=outputs()
            if case=='missing_base': entries=entries[1:]
            elif case=='duplicate': entries[1]['z_index']=0
            elif case=='missing_box': entries[1].pop('bounding_box')
            elif case=='bad_box': entries[1]['bounding_box']['absolute']=[0,0,900,512]
            else: entries=outputs(18)
            with config_fixture({self.key_env:'fixture-only'}),patch.object(self.adapter,'request',return_value={'data':entries}) as post:
                with self.assertRaises(ValueError):submit.submit(work,spec,'TEST CONFIRMATION')
                with self.assertRaises(ValueError):submit.submit(work,spec,'TEST CONFIRMATION')
                post.assert_called_once()
            self.assertEqual(store.read(work/'submit-001.json')['execution']['state'],'submission_unknown')

    def test_non_alpha_or_wrong_dimensions_cannot_complete_download(self):
        for content in (png(alpha=False),png(400,400)):
            work,spec=self.prepare();state,_=self.post(work,spec,{'data':outputs()})
            with patch('core.download.download_url',side_effect=lambda url,path:path.write_bytes(content)):
                with self.assertRaises(ValueError):download._download(state['submission'])
            self.assertFalse(store.read(state['submission'])['execution']['download_complete'])

    def test_presets_and_coordinate_checks(self):
        work, spec = self.prepare()
        for size in ('auto','1K','1.5K','2K'):
            spec['payload']['size']=size
            self.assertEqual(compile_request(spec)['parameters']['size'],size)
        spec['payload']['prompt']='<bbox>100 200 999 999</bbox> 拆出标题'
        compile_request(spec)
        spec['payload']['prompt']='<bbox>999 200 100 999</bbox>'
        with self.assertRaises(ValueError):compile_request(spec)
        spec['payload']['prompt']='<point>100 200</point> 拆出人物'
        with self.assertRaisesRegex(ValueError,'bbox region tags only'):compile_request(spec)

    def test_remote_codec_is_verified_without_trusting_url_suffix(self):
        from core.media_probe import probe_asset
        for codec, mime in (('png','image/png'),('mjpeg','image/jpeg'),('webp',None)):
            result=SimpleNamespace(returncode=0,stdout=json.dumps({
                'streams':[{'codec_type':'video','codec_name':codec,'width':512,'height':512,'pix_fmt':'rgba'}],
                'format':{'size':'1000'}}))
            with patch('core.media_probe.subprocess.run',return_value=result):
                measured=probe_asset({'kind':'image','source':'https://example.com/misleading.jpg'})
            self.assertEqual(measured['metadata']['mime'],mime)
            if mime:
                validate_layer_metadata(measured['metadata'])
            else:
                with self.assertRaises(ValueError):validate_layer_metadata(measured['metadata'])

    def test_status_rechecks_layers_in_saved_successful_response(self):
        for mutation in ('missing_base', 'missing_box', 'error', 'missing_media'):
            work, spec = self.prepare()
            state, _ = self.post(work, spec, {'data': outputs()})
            record = store.read(state['submission'])
            entries = record['response']['data']
            if mutation == 'missing_base': entries.pop(0)
            elif mutation == 'missing_box': entries[1].pop('bounding_box')
            elif mutation == 'error': entries[1] = {'error': {'message': 'layer failed'}}
            else: entries[1].pop('url')
            store.write(state['submission'], record)
            with patch.object(self.adapter, 'request') as post, patch.object(self.adapter, 'status') as query:
                result = status.run(SimpleNamespace(submission=state['submission'], wait=0))
                self.assertFalse(result['success'])
                self.assertTrue(result['error'])
                post.assert_not_called(); query.assert_not_called()
            saved = store.read(state['submission'])['execution']
            self.assertEqual(saved['state'], 'failed' if mutation == 'error' else 'submission_unknown')

    def test_status_never_promotes_unknown_submission(self):
        work, spec = self.prepare()
        state, _ = self.post(work, spec, {'data': outputs()})
        record = store.read(state['submission'])
        record['execution']['state'] = 'submission_unknown'
        store.write(state['submission'], record)
        self.assertFalse(status.run(SimpleNamespace(submission=state['submission'], wait=0))['success'])
