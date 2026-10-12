"""Tracking destination validation happens before project/media reads."""
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from amp.cli import main


class TrackCliTests(unittest.TestCase):
    def assert_output_rejected(self, arguments):
        error=io.StringIO()
        with patch('sys.argv',['amp','track',*arguments]), \
                patch('amp.revision.track_region') as tracker, \
                patch.object(Path,'read_text',side_effect=AssertionError('project must not be read')), \
                redirect_stderr(error):
            with self.assertRaises(SystemExit) as raised:main()
        self.assertEqual(raised.exception.code,2)
        self.assertIn('--output',error.getvalue())
        tracker.assert_not_called()

    def test_track_requires_explicit_output_before_loading_project(self):
        self.assert_output_rejected(['--project','missing-project'])

    def test_track_rejects_directory_extensionless_and_non_json_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for destination in (root,root/'track',root/'track.mp4',root/'track.json.tmp'):
                with self.subTest(output=destination):
                    self.assert_output_rejected(['--output',str(destination)])
            self.assertEqual(list(root.iterdir()),[])

    def test_track_passes_explicit_json_filename_to_tracker(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'composition.json').write_text(json.dumps({'fps':30}))
            destination=root/'new-track.json'
            arguments=['amp','track','--project',str(root),'--source','source.mp4',
                       '--start','.2','--end','1','--roi','0','0','1','1','--output',str(destination)]
            with patch('sys.argv',arguments),patch('amp.revision.track_region',return_value={'rows':[{}]*24}) as tracker, \
                    redirect_stdout(io.StringIO()) as output:
                main()
            tracker.assert_called_once_with('source.mp4',6,30,[0.,0.,1.,1.],str(destination),30)
            self.assertEqual(json.loads(output.getvalue()),{'tracked_frames':24,'output':str(destination)})
