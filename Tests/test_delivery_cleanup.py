import sys
import tempfile
import unittest
import json
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Content/Python'))
from asset_pack_pipeline import cleanup, delivery
from asset_pack_pipeline.discovery import digest


class DeliveryCleanupTests(unittest.TestCase):
    def test_project_outer_folder_can_have_project_suffix(self):
        with tempfile.TemporaryDirectory() as temp:
            project=Path(temp)/'Pack_Project';(project/'Content/Pack').mkdir(parents=True)
            (project/'Content/Pack/Mesh.uasset').write_bytes(b'mesh')
            descriptor=project/'Pack.uproject';descriptor.write_text(json.dumps({'FileVersion':3}))
            report={'project_directory':str(project),'project_path':str(descriptor),
                    'file_hashes':{str(p.relative_to(project)):digest(p) for p in project.rglob('*') if p.is_file()}}
            self.assertTrue(delivery.verify_files(report))
            (project/'Wrong.uproject').write_text(descriptor.read_text())
            report.update(project_path=str(project/'Wrong.uproject'),file_hashes={})
            with self.assertRaises(RuntimeError):delivery.verify_files(report)
    def test_builtin_interchange_import_metadata_allowed_but_authoring_modules_blocked(self):
        selected,blocked=delivery.dependency_closure(['/Game/Pack/Mesh'],lambda p:
            ['/Script/InterchangeImport','/Script/ModelContextProtocol','/Script/AssetPackPipeline'], '/Game/Pack')
        self.assertEqual(selected,['/Game/Pack/Mesh'])
        self.assertEqual(blocked,['/Script/AssetPackPipeline','/Script/ModelContextProtocol'])
    def test_external_reference_retains_its_dependencies(self):
        active = cleanup.retain_referenced({'mesh','material','texture','free'},
            {'mesh':['outside'], 'material':['mesh'], 'texture':['material'], 'free':[]})
        self.assertEqual(active, {'free'})

    def test_internal_cycle_is_removable_but_foreign_cycle_is_retained(self):
        self.assertEqual(cleanup.retain_referenced({'a','b'}, {'a':['b'],'b':['a']}), {'a','b'})
        self.assertEqual(cleanup.retain_referenced({'a','b'}, {'a':['b','foreign'],'b':['a']}), set())

    def test_delivery_rejects_staging_other_pack_and_custom_module(self):
        selected, blocked = delivery.dependency_closure(['/Game/Pack/Mesh'], lambda p:
            ['/Game/Pack/Material','/Game/AssetPackPipeline_Staging/Temp','/Game/Other/Texture','/Script/MyCode']
            if p.endswith('/Mesh') else ['/Engine/EngineMaterials/DefaultMaterial','/Script/Engine'], '/Game/Pack')
        self.assertEqual(selected, ['/Game/Pack/Material','/Game/Pack/Mesh'])
        self.assertEqual(len(blocked), 3)

    def test_delivery_copies_map_sidecars_and_rejects_missing_packages(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root/'Pack').mkdir()
            (root/'Pack/Overview.umap').write_bytes(b'map')
            (root/'Pack/Overview.uexp').write_bytes(b'sidecar')
            self.assertEqual(len(delivery.package_files(root,['/Game/Pack/Overview'])),2)
            with self.assertRaises(ValueError):
                delivery.package_files(root,['/Game/Pack/Missing'])

    def test_delivery_configuration_is_explicit(self):
        for config in ({'maps':'all'}, {'output_directory':'relative'}):
            with self.assertRaises(ValueError):
                delivery.settings({'delivery':config})
