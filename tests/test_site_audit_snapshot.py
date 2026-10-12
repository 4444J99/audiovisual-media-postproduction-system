"""Snapshot URL identity must match the bytes in each receipt's local file."""
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import site_audit_snapshot as audit


class SiteAuditSnapshotTests(unittest.TestCase):
    def test_query_variants_capture_distinct_reproducible_paths(self):
        urls=[audit.MAIN+'metadata.json?edition=one',audit.MAIN+'metadata.json?edition=two']
        bodies={url:json.dumps({'edition':number}).encode() for number,url in enumerate(urls)}
        class Response:
            headers={'content-type':'application/json'}
            status=200
            def __init__(self,url):self.url=url
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def read(self,limit):return bodies[self.url]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);prior=None
            for repeat in range(2):
                with patch.object(audit,'OUT',root),patch.object(audit,'ROUTES',list(enumerate(urls))), \
                     patch.object(audit,'urlopen',side_effect=lambda request,timeout:Response(request.full_url)), \
                     patch.object(audit.time,'time',return_value=12345),redirect_stdout(io.StringIO()):
                    audit.capture_sources()
                records=json.loads((root/'source-capture.json').read_text())['records']
                paths=[row['local_path'] for row in records]
                self.assertEqual(len(set(paths)),2)
                for row in records:
                    data=(root/row['local_path']).read_bytes()
                    self.assertEqual(data,bodies[row['url']])
                    self.assertEqual(hashlib.sha256(data).hexdigest(),row['sha256'])
                    self.assertEqual(Path(row['local_path']).suffix,'.json')
                if prior is not None:self.assertEqual(records,prior)
                prior=records
        self.assertNotEqual(audit.relative_path(urls[0]),audit.relative_path(audit.MAIN+'metadata.json'))
        self.assertEqual(audit.relative_path(urls[0]+'#section'),audit.relative_path(urls[0]))
        self.assertEqual(audit.relative_path(audit.MAIN).name,'index.html')

