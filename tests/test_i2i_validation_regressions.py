"""共用图片编辑校验：使用真实文件，不发起付费 API 请求。"""
import base64
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from core import asset_inspect, media_base64, payload_size
from providers import calculate_asset_inputs
from providers import compile_request
from providers.volcengine.image_to_image import validate_edit_coordinates
from test_document_contract import image
from test_runtime import png


class ImageEditingValidation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def cost_input(self, provider, source, count=1):
        return {'provider': provider, 'model': 'seedream-5.0-flash', 'operation': 'image-to-image',
                'size': '1K', 'assets': [{'id': str(i), 'kind': 'image', 'source': str(source)} for i in range(count)]}

    def test_renamed_png_uses_content_mime_for_quote_and_post_body(self):
        source = self.root/'source.jpg';source.write_bytes(png())
        for provider, prefix in (('volcengine', 'doubao'), ('byteplus', 'dola')):
            with self.subTest(provider=provider):
                quote = calculate_asset_inputs(self.cost_input(provider, source))
                self.assertEqual(quote['calculation']['assets'][0]['mime'], 'image/png')
                spec = image();spec.update(provider=provider, operation='image-to-image', assets=[{
                    'id': '0', 'kind': 'image', 'source': str(source), 'purpose': 'reference'}])
                spec['payload']['model'] = prefix+'-seedream-5-0-flash-260915'
                compiled = compile_request(spec, quote['calculation']['assets'])
                value = media_base64.materialize(compiled['assets'][0])
                self.assertTrue(value.startswith('data:image/png;base64,'))
                self.assertEqual(base64.b64decode(value.split(',', 1)[1]), png())

    @unittest.skipUnless(shutil.which('ffmpeg'), 'ffmpeg needed to create real video fixture')
    def test_video_renamed_as_png_is_rejected_by_both_entrypoints(self):
        source = self.root/'video.png'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=size=64x64:rate=1',
                        '-t', '1', '-c:v', 'mpeg4', '-f', 'mp4', str(source)], check=True)
        for provider in ('volcengine', 'byteplus'):
            with self.subTest(provider=provider), self.assertRaisesRegex(ValueError, 'Unsupported input image format'):
                calculate_asset_inputs(self.cost_input(provider, source))
        with self.assertRaisesRegex(ValueError, 'Unsupported input image format'):
            asset_inspect.inspect_asset({'kind': 'image', 'source': str(source), 'purpose': 'reference'})

    def test_materialize_hashes_and_encodes_same_bytes(self):
        source = self.root/'source.png';source.write_bytes(png())
        asset = asset_inspect.inspect_asset({'kind': 'image', 'source': str(source), 'purpose': 'reference'})
        real_sha256 = hashlib.sha256
        def change_after_hash(data):
            digest = real_sha256(data)
            source.write_bytes(png()+b'changed during submission')
            return digest
        with patch.object(media_base64.hashlib, 'sha256', side_effect=change_after_hash):
            encoded = media_base64.materialize(asset)
        self.assertEqual(base64.b64decode(encoded.split(',', 1)[1]), png())
        self.assertNotEqual(source.read_bytes(), png())

    def test_oversized_base64_batch_is_rejected_before_quote(self):
        source = self.root/'source.png';source.write_bytes(png()+bytes(25*1024*1024))
        for provider in ('volcengine', 'byteplus'):
            with self.subTest(provider=provider), patch('providers.'+provider+'.image_to_image.calculate_inputs') as price:
                with self.assertRaisesRegex(ValueError, '64 MB after Base64'):
                    calculate_asset_inputs(self.cost_input(provider, source, 2))
                price.assert_not_called()
        # 同样的素材改用 URL 传递时，请求总大小符合限制。
        payload_size.validate_image_request_size([{'source': 'https://example.com/a.png'},
                                            {'source': 'https://example.com/b.png'}])

    def test_preflight_matches_actual_json_size_with_mixed_sources(self):
        items = [{'source': '/source.png', 'metadata': {'mime': 'image/png', 'bytes': 11}},
                 {'source': 'https://example.com/图.png?x="quoted"'}]
        template = {'prompt': '中文提示词', 'image': []}
        actual = {**template, 'image': ['data:image/png;base64,'+base64.b64encode(bytes(11)).decode(), items[1]['source']]}
        expected = len(json.dumps(actual, ensure_ascii=False).encode())
        with patch.object(payload_size.json, 'dumps', wraps=json.dumps) as dumps:
            payload_size.validate_image_request_size(items, template)
        skeleton = dumps.call_args.args[0]
        self.assertEqual(len(json.dumps(skeleton, ensure_ascii=False).encode())+16, expected)
        self.assertEqual(template['image'], [])

    def test_incomplete_mismatched_and_nested_coordinate_tags_are_rejected(self):
        prompts = ['<bbox>0 0 1000 999 改背景', '<point>1000 100</bbox>', '</point>',
                   '<bbox>0 0 999 999</bbox><point>1 2', '<point><point>1 2</point></point>',
                   '<bbox x="1">0 0 1 1</bbox>', '<point/>']
        for prompt in prompts:
            with self.subTest(prompt=prompt), self.assertRaises(ValueError):
                validate_edit_coordinates(prompt)
        validate_edit_coordinates('改背景 <point>100 200</point> 保留 <bbox>0 0 999 999</bbox>')
        validate_edit_coordinates('自然语言修改左上角，不使用坐标')
