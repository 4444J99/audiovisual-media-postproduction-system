"""Public fixture tests. No owner media or network needed."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile

MODULE = Path(__file__).resolve().parents[1] / 'tools/studio/build_site.py'

class StudioBuild(unittest.TestCase):
    def module(self):
        self.assertTrue(MODULE.exists(), 'Build implementation must exist')
        spec = importlib.util.spec_from_file_location('studio_build', MODULE)
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        return module
    def test_font_cannot_enter_bundle(self):
        m=self.module()
        for name in ['a.ttf','a.woff2','assets/private.OTF']: self.assertFalse(m.allowed_asset(Path(name)))
        self.assertTrue(m.allowed_asset(Path('source.json')))
    def test_extract_rejects_traversal(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); z=p/'test.zip'
            with zipfile.ZipFile(z,'w') as f:f.writestr('../escape.mp4',b'bad')
            with self.assertRaises(ValueError):m.extract_layouts(z,p/'out')
            self.assertFalse((p/'escape.mp4').exists())
    def test_source_identity_checked(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'a';p.write_bytes(b'test')
            self.assertEqual(m.sha256(p),'9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08')
            with self.assertRaises(ValueError):m.require_hash(p,'0'*64)
    def test_copy_does_not_mutate_source(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);src=p/'a.html';src.write_bytes(b'<h1>Original</h1>'); m.copy_exact(src,p/'site'/'b.html')
            self.assertEqual(src.read_bytes(),(p/'site'/'b.html').read_bytes())
    def test_catalog_mount_metadata_is_not_artistic_acceptance(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'study.html';p.write_text('A')
            row=m.mount_record(p,'/studies/a.html','code','study-03')
            self.assertEqual(row['artistic_acceptance'],'pending')
            self.assertEqual(row['links'][0]['href'],'/studies/a.html')
            self.assertEqual(row['workspace'],'study-03')

    def test_recovered_players_do_not_share_review_storage(self):
        m=self.module()
        sample="localStorage.getItem('god-here-study-04-reviews');localStorage.setItem('god-here-study-04-reviews','{}');localStorage.setItem('god-here-evaluation-05-last',JSON.stringify(report));"
        result=m.patch_player(sample,'evaluation')
        self.assertNotIn("'god-here-study-04-reviews'",result)
        self.assertIn('god-here-studio-evaluation-reviews',result)
        self.assertIn('try{localStorage.setItem',result)
        self.assertIn('catch',result)
    def test_unknown_player_revision_is_not_silently_rewritten(self):
        m=self.module()
        with self.assertRaises(ValueError):m.patch_player('<html>unknown</html>','evaluation')
