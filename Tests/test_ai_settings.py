import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'Content/Python'))
from asset_pack_pipeline import ai_settings


class AISettingsTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).resolve().parents[3]/'Saved'/'AISettingsTests'
        scratch.mkdir(parents=True, exist_ok=True)
        self.folder = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name)/'ai.json'
        self.patcher = patch.object(ai_settings, 'location', return_value=self.path)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.old_key = ai_settings._session_key
        ai_settings._session_key = ''
        self.addCleanup(setattr, ai_settings, '_session_key', self.old_key)

    def test_session_secret_is_not_written(self):
        ai_settings.save('gpt-6-luna', 'unit-test-secret')
        self.assertEqual(ai_settings.get_key(), 'unit-test-secret')
        self.assertNotIn('unit-test-secret', self.path.read_text())
        ai_settings._session_key = ''
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(ai_settings.get_key(), '')

    @unittest.skipUnless(os.name == 'nt', 'Windows DPAPI')
    def test_dpapi_roundtrip_and_forget(self):
        ai_settings.save('gpt-6.1-sol', 'unit-test-secret', remember=True)
        self.assertNotIn('unit-test-secret', self.path.read_text())
        ai_settings._session_key = ''
        self.assertEqual(ai_settings.get_key(), 'unit-test-secret')
        ai_settings.save('gpt-6.1-sol', forget=True)
        self.assertNotIn('protected_key', ai_settings.load())

    def test_environment_fallback(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY':'unit-test-environment'}):
            self.assertEqual(ai_settings.get_key(), 'unit-test-environment')

    def test_models_filter_specialized_models(self):
        self.assertEqual(ai_settings.model_options(['gpt-6-luna','gpt-image-2','gpt-6.1-sol','embedding']),
                         ['gpt-6.1-sol','gpt-6-luna'])
