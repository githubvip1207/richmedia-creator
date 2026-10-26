"""最终交付只发布验证通过的输出，并支持安全复制和中断恢复。"""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
import test_native_volcengine_layers as fixtures
from commands import deliver
from core import submission_store as store


class Delivery(unittest.TestCase):
    provider = fixtures.LayerLifecycle.provider
    adapter = fixtures.LayerLifecycle.adapter
    other_adapter = fixtures.LayerLifecycle.other_adapter
    model_prefix = fixtures.LayerLifecycle.model_prefix
    key_env = fixtures.LayerLifecycle.key_env

    setUp = fixtures.LayerLifecycle.setUp
    prepare = fixtures.LayerLifecycle.prepare
    post = fixtures.LayerLifecycle.post

    def output_directory(self, name='user'):
        target = self.root/name; target.mkdir(exist_ok=True)
        return target.resolve()

    def ready(self):
        work, spec = self.prepare()
        state, _ = self.post(work, spec, {'data': fixtures.outputs()})
        return work, state['submission']

    def media_get(self, url, path):
        path.write_bytes(fixtures.png())

    def test_complete_delivery_contains_only_media_and_portable_metadata(self):
        work, submission = self.ready(); target = self.output_directory()
        with patch('core.download.download_url', side_effect=self.media_get):
            result = deliver.deliver(submission, target)
        directory = Path(result['directory'])
        self.assertEqual(directory.parent, target)
        self.assertEqual({p.name for p in directory.iterdir()}, {'00-base.png','01-layer.png','layers.json'})
        self.assertEqual(store.read(submission)['delivery'], result)
        self.assertTrue(store.read(submission)['execution']['delivery_complete'])
        self.assertTrue(all(Path(f['path']).parent == directory for f in result['files']))
        metadata = store.read(result['metadata']['path'])
        self.assertEqual([e['file'] for e in metadata['layers']], ['00-base.png','01-layer.png'])
        self.assertNotIn('https:', json.dumps(result))
        self.assertTrue(Path(store.read(submission)['result']['files'][0]['path']).is_relative_to(work.resolve()))

    def test_repeated_delivery_reuses_files_and_cache_without_get(self):
        _, submission = self.ready(); target = self.output_directory()
        with patch('core.download.download_url', side_effect=self.media_get) as get:
            first = deliver.deliver(submission, target)
            second = deliver.deliver(submission, target)
            self.assertEqual(get.call_count, 2)
        self.assertEqual(first['directory'], second['directory'])
        self.assertEqual(first['files'], second['files'])
        self.assertEqual(len(list(target.iterdir())), 1)

    def test_user_edit_and_existing_directory_are_preserved(self):
        work, submission = self.ready(); target = self.output_directory()
        occupied = target/('richmedia-'+work.name+'-submit-001'); occupied.mkdir()
        (occupied/'keep.txt').write_text('keep')
        with patch('core.download.download_url', side_effect=self.media_get):
            first = deliver.deliver(submission, target)
            Path(first['files'][0]['path']).write_bytes(b'user edited')
            second = deliver.deliver(submission, target)
        self.assertNotEqual(first['directory'], second['directory'])
        self.assertEqual(Path(first['files'][0]['path']).read_bytes(), b'user edited')
        self.assertEqual((occupied/'keep.txt').read_text(), 'keep')

    def test_copy_failure_never_marks_complete_and_retry_never_regenerates(self):
        _, submission = self.ready(); target = self.output_directory()
        copy = deliver.shutil.copyfileobj
        calls = [0]
        def interrupted(source, output):
            calls[0] += 1
            if calls[0] == 2:
                output.write(b'incomplete')
                raise OSError('copy interrupted')
            return copy(source, output)
        with patch('core.download.download_url', side_effect=self.media_get) as get:
            with patch.object(deliver.shutil, 'copyfileobj', side_effect=interrupted):
                with self.assertRaisesRegex(OSError,'interrupted'):deliver.deliver(submission, target)
            self.assertFalse(store.read(submission)['execution']['delivery_complete'])
            result = deliver.deliver(submission, target)
            self.assertEqual(get.call_count,2)
        self.assertTrue(store.read(submission)['execution']['delivery_complete'])
        self.assertEqual(Path(result['files'][1]['path']).read_bytes(),fixtures.png())

    def test_current_directory_is_default_and_new_target_gets_new_delivery(self):
        _, submission = self.ready(); first_target=self.output_directory(); second_target=self.output_directory('other')
        with patch('core.download.download_url', side_effect=self.media_get):
            with patch.object(deliver.Path, 'cwd', return_value=first_target):
                first = deliver.run(SimpleNamespace(submission=submission))
            second = deliver.deliver(submission,second_target)
        self.assertEqual(Path(first['directory']).parent,first_target)
        self.assertEqual(Path(second['directory']).parent,second_target)
        self.assertTrue(Path(first['files'][0]['path']).is_file())

    def test_failed_or_partial_generation_cannot_be_delivered(self):
        for state in ('failed', 'partial_failed', 'submission_unknown'):
            _, submission = self.ready(); target=self.output_directory()
            record=store.read(submission);record['execution']['state']=state
            if state != 'submission_unknown':record['response']['data'][1]={'error':{'message':'failed'}}
            store.write(submission,record)
            with patch('core.download.download_url') as get:
                with self.assertRaises(ValueError):deliver.deliver(submission,target)
                get.assert_not_called()
            self.assertFalse(store.read(submission)['execution']['delivery_complete'])
            self.assertEqual(list(target.iterdir()),[])
