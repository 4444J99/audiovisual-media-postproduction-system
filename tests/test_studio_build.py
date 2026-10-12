"""Public fixture tests. No owner media or network needed."""
import importlib.util
import hashlib
import json
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
    def review_fixture(self, module, root):
        work=root/'review';work.mkdir()
        module.SOURCE_SHA=hashlib.sha256(b'original source film').hexdigest()
        ids=[f'E{i:03}' for i in range(174)]
        timeline={'metadata':{'source_video_sha256':module.SOURCE_SHA},
                  'master_events':[{'event_id':identifier} for identifier in ids],
                  'dialogue':[{} for _ in range(35)],'performance':[{} for _ in range(139)]}
        files={
            'god-here-review-workbench.html':b'<html>retained workbench</html>',
            'source/original-film.mp4':b'original source film',
            'source/god-here-character-timeline.xlsx':b'retained workbook bytes',
            'source/workbook-values.json':json.dumps({'Timeline':[[]]*6+[[identifier] for identifier in ids]}).encode(),
            'source/god-here-character-timeline.json':json.dumps(timeline).encode(),
            'source/god-here-character-timeline.csv':('event_id\n'+'\n'.join(ids)+'\n').encode(),
            'source/god-here-character-timeline.md':b'retained timeline notes',
        }
        for name,data in files.items():
            path=work/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        catalog=root/'catalog.json'
        self.refresh_review_catalog(work,catalog)
        return work,catalog
    def refresh_review_catalog(self,work,catalog):
        catalog.write_text(json.dumps({'objects':[
            {'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size,
             'logical_names':[path.name]} for path in work.rglob('*') if path.is_file()]}))
    def layout_fixture(self,module,root):
        files={name:('retained '+name).encode() for name in module.LAYOUT_FILENAMES}
        package_sha='a'*64
        objects=[{'sha256':package_sha,'logical_names':['god-here-eight-suggestions-package.zip']}]
        origins=[]
        for index,(name,data) in enumerate(sorted(files.items())):
            origin=f'early-{index}'
            objects.append({'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),
                            'logical_names':[name],'origin_ids':[origin]})
            origins.append({'origin_id':origin,'kind':'archive_member','container_sha256':package_sha,
                            'member_path':name,'member_path_safe':True,'container_identity_verified':True})
            # Later editions deliberately share basenames, but not package lineage.
            objects.append({'sha256':hashlib.sha256(b'later '+data).hexdigest(),'bytes':len(data)+6,
                            'logical_names':[name],'origin_ids':[f'later-{index}']})
            origins.append({'origin_id':f'later-{index}','kind':'archive_member','container_sha256':'b'*64,
                            'member_path':name,'member_path_safe':True,'container_identity_verified':True})
        catalog=root/'catalog.json';catalog.write_text(json.dumps({'objects':objects,'origins':origins}))
        return files,catalog
    def write_zip(self,path,entries):
        with zipfile.ZipFile(path,'w') as archive:
            for name,data in entries:archive.writestr(name,data)
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
    def test_complete_retained_review_package_is_accepted(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as d:
            work,catalog=self.review_fixture(m,Path(d))
            identities=m.validate_review_package(work,catalog)
            self.assertEqual(set(identities),set(m.REVIEW_ASSETS))
    def test_each_review_asset_requires_retained_bytes(self):
        m=self.module()
        for relative in m.REVIEW_ASSETS:
            with self.subTest(asset=relative),tempfile.TemporaryDirectory() as d:
                work,catalog=self.review_fixture(m,Path(d));path=work/relative
                original=path.read_bytes()
                path.write_bytes(bytes([original[0]^1])+original[1:])
                with self.assertRaisesRegex(ValueError,'Identity mismatch'):
                    m.validate_review_package(work,catalog)
    def test_each_review_asset_is_required(self):
        m=self.module()
        for relative in m.REVIEW_ASSETS:
            with self.subTest(asset=relative),tempfile.TemporaryDirectory() as d:
                work,catalog=self.review_fixture(m,Path(d));(work/relative).unlink()
                with self.assertRaisesRegex(ValueError,'missing or unsupported'):
                    m.validate_review_package(work,catalog)
    def test_unknown_or_ambiguous_review_identity_is_rejected(self):
        m=self.module()
        for ambiguous in [False,True]:
            with self.subTest(ambiguous=ambiguous),tempfile.TemporaryDirectory() as d:
                work,catalog=self.review_fixture(m,Path(d));data=json.loads(catalog.read_text())
                row=next(row for row in data['objects'] if row['logical_names']==['workbook-values.json'])
                if ambiguous:data['objects'].append(dict(row,sha256='0'*64))
                else:data['objects'].remove(row)
                catalog.write_text(json.dumps(data))
                with self.assertRaisesRegex(ValueError,'Missing or ambiguous retained identity'):
                    m.validate_review_package(work,catalog)
    def test_review_timeline_requires_174_records_even_if_catalog_changes(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as d:
            work,catalog=self.review_fixture(m,Path(d));path=work/'source/god-here-character-timeline.json'
            data=json.loads(path.read_text());data['master_events'].pop();path.write_text(json.dumps(data))
            self.refresh_review_catalog(work,catalog)
            with self.assertRaisesRegex(ValueError,'174-record'):
                m.validate_review_package(work,catalog)
    def test_review_rejects_changed_cross_file_alignment_even_if_catalog_changes(self):
        m=self.module()
        for relative in ['source/workbook-values.json','source/god-here-character-timeline.csv']:
            with self.subTest(asset=relative),tempfile.TemporaryDirectory() as d:
                work,catalog=self.review_fixture(m,Path(d));path=work/relative
                path.write_text(path.read_text().replace('E000','different-ID'))
                self.refresh_review_catalog(work,catalog)
                with self.assertRaisesRegex(ValueError,'same 174 timeline IDs'):
                    m.validate_review_package(work,catalog)
    def test_review_copy_rejects_mutation_after_preflight(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);work,catalog=self.review_fixture(m,root)
            identities=m.validate_review_package(work,catalog)
            (work/'god-here-review-workbench.html').write_text('replacement')
            with self.assertRaisesRegex(ValueError,'Identity mismatch'):
                m.copy_review_asset(work,'god-here-review-workbench.html',root/'out/index.html',identities)
    def test_layouts_require_the_exact_early_package_member_bytes(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);files,catalog=self.layout_fixture(m,root);archive=root/'layouts.zip'
            self.write_zip(archive,[(f'folder/{name}',data) for name,data in files.items()])
            result=m.extract_layouts(archive,root/'out',catalog)
            self.assertEqual({p.name for p in result},m.LAYOUT_FILENAMES)
            for path in result:self.assertEqual(path.read_bytes(),files[path.name])
    def test_layouts_reject_missing_or_wrong_filenames(self):
        m=self.module()
        for replace in [False,True]:
            with self.subTest(replace=replace),tempfile.TemporaryDirectory() as d:
                root=Path(d);files,catalog=self.layout_fixture(m,root);files.pop(sorted(files)[0])
                if replace:files['unrelated.mp4']=b'wrong clip'
                archive=root/'layouts.zip';self.write_zip(archive,files.items())
                with self.assertRaisesRegex(ValueError,'exact 16 unique'):
                    m.extract_layouts(archive,root/'out',catalog)
                self.assertFalse((root/'out').exists())
    def test_layouts_reject_duplicate_basenames_in_different_folders(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);files,catalog=self.layout_fixture(m,root);names=sorted(files)
            entries=[(f'folder/{name}',data) for name,data in files.items() if name!=names[-1]]
            entries.append((f'other/{names[0]}',files[names[0]]))
            self.assertEqual(len(entries),16)
            archive=root/'layouts.zip';self.write_zip(archive,entries)
            with self.assertRaisesRegex(ValueError,'Duplicate layout basename'):
                m.extract_layouts(archive,root/'out',catalog)
            self.assertFalse((root/'out').exists())
    def test_layouts_reject_same_name_replacement_or_later_edition(self):
        m=self.module()
        for later in [False,True]:
            with self.subTest(later=later),tempfile.TemporaryDirectory() as d:
                root=Path(d);files,catalog=self.layout_fixture(m,root);name=sorted(files)[-1]
                data=files[name];files[name]=b'later '+data if later else bytes([data[0]^1])+data[1:]
                archive=root/'layouts.zip';self.write_zip(archive,files.items())
                with self.assertRaisesRegex(ValueError,'Layout identity mismatch'):
                    m.extract_layouts(archive,root/'out',catalog)
                self.assertFalse((root/'out').exists())
    def test_layouts_reject_incomplete_retained_member_evidence(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);files,catalog=self.layout_fixture(m,root);data=json.loads(catalog.read_text())
            data['origins'].pop(0);catalog.write_text(json.dumps(data))
            archive=root/'layouts.zip';self.write_zip(archive,files.items())
            with self.assertRaisesRegex(ValueError,'Retained layout package must identify'):
                m.extract_layouts(archive,root/'out',catalog)
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
