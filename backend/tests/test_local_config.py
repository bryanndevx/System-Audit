import os
import secrets
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.ai_diagnostics import GeminiConfig
from app.local_config import LocalConfigurationError, load_local_gemini_environment
from scripts import check_gemini


class LocalConfigurationTests(unittest.TestCase):
    @patch("scripts.check_gemini.request_gemini")
    @patch("scripts.check_gemini.getpass")
    @patch("builtins.print")
    def test_diagnostic_uses_env_file_without_asking_for_key(self, output, prompt, request):
        key = secrets.token_urlsafe(25)
        self.path.write_text(f"GEMINI_ENABLED=0\nGEMINI_API_KEY={key}\n", encoding="utf-8")
        self.assertEqual(check_gemini.main(), 0)
        prompt.assert_not_called()
        request.assert_called_once()
        self.assertEqual(request.call_args.args[0].api_key, key)
        self.assertNotIn(key, str(output.call_args_list))

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / ".env"
        self.path_patch = patch("app.local_config.GEMINI_ENV_PATH", self.path)
        self.path_patch.start()
        self.addCleanup(self.path_patch.stop)
        self.env_patch = patch.dict(os.environ, {}, clear=True)
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)

    def test_file_loads_key_and_model_with_bom_and_quoted_values(self):
        key = secrets.token_urlsafe(25)
        self.path.write_text(
            f'# Configuración\nGEMINI_ENABLED=1\nGEMINI_API_KEY="{key}"\nGEMINI_MODEL=gemini-test\n',
            encoding="utf-8-sig",
        )
        config = GeminiConfig.from_environment()
        self.assertEqual(config.api_key, key)
        self.assertEqual(config.model, "gemini-test")
        self.assertNotIn(key, repr(config))

    def test_shell_configuration_has_priority(self):
        self.path.write_text("GEMINI_ENABLED=1\nGEMINI_MODEL=gemini-file\n", encoding="utf-8")
        os.environ["GEMINI_MODEL"] = "gemini-shell"
        load_local_gemini_environment()
        self.assertEqual(os.environ["GEMINI_MODEL"], "gemini-shell")

    def test_production_does_not_read_local_file(self):
        self.path.write_text("GEMINI_ENABLED=1\nGEMINI_API_KEY=\"invalid", encoding="utf-8")
        os.environ["APP_ENV"] = "production"
        load_local_gemini_environment()
        self.assertNotIn("GEMINI_API_KEY", os.environ)

    def test_unknown_variables_are_not_loaded_or_executed(self):
        self.path.write_text('DB_PASSWORD=not-loaded\nPATH=not-loaded\nGEMINI_MODEL="$(not-executed)"\n', encoding="utf-8")
        load_local_gemini_environment()
        self.assertNotIn("DB_PASSWORD", os.environ)
        self.assertNotIn("PATH", os.environ)
        self.assertEqual(os.environ["GEMINI_MODEL"], "$(not-executed)")

    def test_invalid_file_reports_line_not_secret_and_does_not_partially_load(self):
        secret = secrets.token_urlsafe(25)
        self.path.write_text(f'GEMINI_ENABLED=1\nGEMINI_API_KEY="{secret}\n', encoding="utf-8")
        with self.assertRaises(LocalConfigurationError) as raised:
            load_local_gemini_environment()
        self.assertIn("línea 2", str(raised.exception))
        self.assertNotIn(secret, str(raised.exception))
        self.assertNotIn("GEMINI_ENABLED", os.environ)

    def test_absent_file_is_optional(self):
        load_local_gemini_environment()
        self.assertNotIn("GEMINI_ENABLED", os.environ)

    def test_oversized_file_is_rejected(self):
        self.path.write_text("#" * (16 * 1024 + 1), encoding="utf-8")
        with self.assertRaisesRegex(LocalConfigurationError, "16 KiB"):
            load_local_gemini_environment()
