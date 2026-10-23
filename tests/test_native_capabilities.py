"""Native capability bodies are posted unchanged and bound to measured quote assets."""
import copy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from commands import submit as submit_command, status as status_command, download as download_command
from core.request import compile_request
from core.cost_quote import calculate_inputs, consume_quote
from core import submission_store as store
from providers import volcengine, transport
from config_fixture import config_fixture
from cost_fixture import save_requirement

IMAGE = 'doubao-seedream-5-0-flash-260915'
VIDEO = 'doubao-seedance-2-0-260128'
VIDEO25 = 'doubao-seedance-2-5-260628'
PIC = 'https://example.com/product.png'
CLIP = 'https://example.com/source.mp4'


def fixture(operation, mode=None, model=None):
    image = operation in ('image-to-image', 'decompose-layers')
    model = model or (IMAGE if image else VIDEO)
    spec = {'provider': 'volcengine', 'operation': operation, 'original_prompt': 'fixture request'}
    if mode:
        spec['mode'] = mode
    if image:
        spec['payload'] = {'model': model, 'prompt': 'Edit image 1 exactly as requested.',
                           'image': PIC, 'size': 'auto' if operation == 'decompose-layers' else '1K',
                           'output_format': 'png', 'watermark': False,
                           'layer_decomposition': operation == 'decompose-layers'}
    else:
        body = {'model': model, 'content': [{'type': 'text', 'text': 'Continue video 1 before its opening.'}],
                'resolution': '480p', 'ratio': '16:9', 'duration': 4,
                'generate_audio': False, 'watermark': False}
        if operation == 'image-to-video':
            body['content'].append({'type': 'image_url', 'image_url': {'url': PIC}, 'role': 'first_frame'})
            if mode == 'first-last-frame':
                body['content'].append({'type': 'image_url', 'image_url': {'url': 'https://example.com/last.png'}, 'role': 'last_frame'})
        elif operation in ('reference-to-video', 'extend-video'):
            body['content'].append({'type': 'video_url', 'video_url': {'url': CLIP}, 'role': 'reference_video'})
        if model == VIDEO25:
            spec['optimizer'] = {'skill': 'sd25-pe', 'status': 'applied'}
            body['output_format'] = 'mov'
            if operation in ('reference-to-video', 'extend-video'):
                body['omni_reference_task_type'] = 'extend' if operation == 'extend-video' else mode
            if mode == 'edit':
                body.update(ratio='adaptive', duration=-1)
        spec['payload'] = body
    return spec


def quote_for(spec):
    body = spec['payload']
    image = spec['operation'] in ('image-to-image', 'decompose-layers')
    facts = []
    if image:
        sources = body['image'] if isinstance(body['image'], list) else [body['image']]
        facts = [{'kind': 'image', 'source': url, 'metadata': {'width': 1024, 'height': 1024, 'has_alpha': True}} for url in sources]
    else:
        for item in body['content']:
            if item['type'] != 'text':
                kind = item['type'].split('_')[0]
                facts.append({'kind': kind, 'source': item[item['type']]['url'],
                              'metadata': {'width': 1280, 'height': 720, **({'duration': 8.0} if kind in ('video', 'audio') else {})}})
    inputs = {'provider': 'volcengine', 'model': body['model'], 'operation': spec['operation'],
              'input_images': sum(a['kind'] == 'image' for a in facts),
              'input_video_seconds': [a['metadata']['duration'] for a in facts if a['kind'] == 'video'],
              'input_audio_seconds': [a['metadata']['duration'] for a in facts if a['kind'] == 'audio']}
    if spec.get('mode'):
        inputs['mode'] = spec['mode']
    inputs.update({'size': body['size']} if image else {k: body[k] for k in ('resolution', 'ratio', 'duration')})
    return calculate_inputs(inputs, measured_assets=facts)


class NativeCapabilities(unittest.TestCase):
    def test_each_capability_posts_the_exact_native_body_once(self):
        cases = [('image-to-image', None), ('decompose-layers', None), ('text-to-video', None),
                 ('image-to-video', 'first-frame'), ('image-to-video', 'first-last-frame'),
                 ('reference-to-video', 'reference'), ('reference-to-video', 'edit'),
                 ('extend-video', 'before'), ('extend-video', 'after')]
        for operation, mode in cases:
            with self.subTest(operation=operation, mode=mode), tempfile.TemporaryDirectory() as tmp:
                spec = fixture(operation, mode, VIDEO25 if mode == 'edit' else None)
                before = copy.deepcopy(spec)
                work = Path(tmp)
                (work/'volcengine').mkdir()
                store.write(work/'volcengine-priceing.json', quote_for(spec))
                save_requirement(spec, work, consume_quote(spec, quote_for(spec))[1])
                response = {'data': [{'url': PIC}]} if 'image' in operation or operation == 'decompose-layers' else {'id': 'fixture-task'}
                # image-to-video is a video operation despite containing the word image.
                if operation == 'image-to-video':
                    response = {'id': 'fixture-task'}
                with config_fixture({'VOLCENGINE_API_KEY': 'fixture-only'}), \
                        patch('core.dependencies.skill_status', return_value={'status': 'ok'}), \
                        patch.object(volcengine, 'request', return_value=response) as post:
                    submit_command.submit(work, spec, 'TEST CONFIRMATION', accept_uncertain=True)
                endpoint = '/images/generations' if operation in ('image-to-image', 'decompose-layers') else '/contents/generations/tasks'
                post.assert_called_once_with('POST', endpoint, before['payload'])
                self.assertEqual(spec, before)

    def test_reordered_or_replaced_media_cannot_reuse_a_quote(self):
        spec = fixture('image-to-video', 'first-last-frame')
        quote = quote_for(spec)
        for change in ('replace', 'reverse'):
            changed = copy.deepcopy(spec)
            if change == 'replace':
                changed['payload']['content'][1]['image_url']['url'] = 'https://example.com/replaced.png'
            else:
                changed['payload']['content'][1:] = reversed(changed['payload']['content'][1:])
            with self.assertRaisesRegex(ValueError, 'differs'):
                consume_quote(changed, quote)

    def test_video_modes_and_native_fields_are_validated(self):
        spec = fixture('reference-to-video', 'edit', VIDEO25)
        for key, value in [('duration', 4), ('ratio', '16:9'), ('omni_reference_task_type', 'reference'), ('seed', 123)]:
            changed = copy.deepcopy(spec)
            changed['payload'][key] = value
            with self.subTest(field=key), self.assertRaises(ValueError):
                consume_quote(changed, quote_for(spec))
        changed = fixture('image-to-video', 'first-frame')
        changed['payload']['content'][1]['role'] = 'reference_image'
        with self.assertRaises(ValueError):
            consume_quote(changed, quote_for(changed))

    def test_image_prompt_and_string_image_are_not_rewritten(self):
        spec = fixture('image-to-image')
        compiled = consume_quote(spec, quote_for(spec))[1]
        self.assertEqual(transport.payload({'compiled': compiled}), spec['payload'])
        self.assertNotIn('ratio', compiled['parameters'])
        self.assertEqual(compiled['prompt'], spec['payload']['prompt'])

    def test_native_body_rejects_persisted_base64(self):
        spec = fixture('image-to-image')
        spec['payload']['image'] = 'data:image/png;base64,fixture'
        with self.assertRaises(ValueError):
            compile_request(spec)

    def test_video_status_and_download_keep_original_post_body(self):
        spec = fixture('extend-video', 'after')
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp); (work/'volcengine').mkdir()
            store.write(work/'volcengine-priceing.json', quote_for(spec))
            save_requirement(spec, work, consume_quote(spec, quote_for(spec))[1])
            with config_fixture({'VOLCENGINE_API_KEY': 'fixture-only'}), \
                    patch.object(volcengine, 'request', return_value={'id': 'fixture-task'}):
                result = submit_command.submit(work, spec, 'TEST CONFIRMATION', accept_uncertain=True)
            submission = result['submission']
            response = {'id': 'fixture-task', 'status': 'succeeded', 'content': {'video_url': 'https://example.com/out.mp4'}}
            with patch.object(volcengine, 'status', return_value=response):
                status_command.status(submission)
            with patch.object(download_command, 'download_url', side_effect=lambda url, path: path.write_bytes(b'\0\0\0\x18ftypisom' + b'\0'*24)):
                downloaded = download_command.download(submission)
            record = store.read(submission)
            self.assertTrue(record['execution']['download_complete'])
            self.assertEqual(record['payload'], spec['payload'])
            self.assertEqual(record['response'], {'id': 'fixture-task'})
            self.assertTrue(Path(downloaded['files'][0]['path']).is_file())

    def test_transparent_image_requires_measured_alpha(self):
        spec = fixture('image-to-image')
        spec['payload']['background'] = 'transparent'
        quote = quote_for(spec)
        self.assertEqual(consume_quote(spec, quote)[1]['payload_template'], spec['payload'])
        quote['calculation']['assets'][0]['has_alpha'] = False
        with self.assertRaisesRegex(ValueError, 'alpha-channel'):
            consume_quote(spec, quote)

    def test_unknown_native_submission_is_not_reposted(self):
        spec = fixture('image-to-image')
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp); (work/'volcengine').mkdir()
            store.write(work/'volcengine-priceing.json', quote_for(spec))
            save_requirement(spec, work, consume_quote(spec, quote_for(spec))[1])
            with config_fixture({'VOLCENGINE_API_KEY': 'fixture-only'}), \
                    patch.object(volcengine, 'request', side_effect=TimeoutError()) as post:
                with self.assertRaises(TimeoutError):
                    submit_command.submit(work, spec, 'TEST CONFIRMATION')
                with self.assertRaises(ValueError):
                    submit_command.submit(work, spec, 'TEST CONFIRMATION AGAIN')
                self.assertEqual(post.call_count, 1)
            self.assertEqual(store.read(work/'submit-001.json')['execution']['state'], 'submission_unknown')
