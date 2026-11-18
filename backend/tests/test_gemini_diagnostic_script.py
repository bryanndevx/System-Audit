import os
import secrets
import unittest
from unittest.mock import patch

from app.ai_diagnostics import GeminiError
from scripts import check_gemini


@patch("scripts.check_gemini.load_local_gemini_environment", new=lambda: None)
@patch("app.ai_diagnostics.load_local_gemini_environment", new=lambda: None)
class GeminiDiagnosticScriptTests(unittest.TestCase):
    @patch("scripts.check_gemini.request_gemini", side_effect=GeminiError(
        "Gemini (HTTP 400): esquema rechazado.", diagnostic_detail="Unknown name responseJsonSchema.",
    ))
    @patch("builtins.print")
    def test_error_shows_the_sanitized_local_detail(self, output, request):
        with patch.dict(os.environ, {"GEMINI_API_KEY": secrets.token_urlsafe(25)}, clear=True):
            self.assertEqual(check_gemini.main(), 1)
        self.assertIn("Unknown name responseJsonSchema", str(output.call_args_list))

    @patch("scripts.check_gemini.request_gemini")
    @patch("builtins.print")
    def test_success_uses_one_synthetic_request_without_printing_key(self, output, request):
        key = secrets.token_urlsafe(25)
        with patch.dict(os.environ, {"GEMINI_API_KEY": key}, clear=True):
            self.assertEqual(check_gemini.main(), 0)
        request.assert_called_once()
        contexts = request.call_args.args[1]
        self.assertEqual(contexts[0]["evidencias"][0]["agregados"], {"total_tablas": 0})
        self.assertIn("ficticia", contexts[0]["tema"])
        self.assertNotIn(key, str(output.call_args_list))

    @patch("scripts.check_gemini.request_gemini", side_effect=GeminiError("Gemini (HTTP 404): modelo no disponible."))
    @patch("builtins.print")
    def test_provider_error_returns_failure_without_a_traceback(self, output, request):
        with patch.dict(os.environ, {"GEMINI_API_KEY": secrets.token_urlsafe(25)}, clear=True):
            self.assertEqual(check_gemini.main(), 1)
        self.assertIn("HTTP 404", str(output.call_args_list))

    @patch("scripts.check_gemini.has_interactive_terminal", return_value=False)
    @patch("scripts.check_gemini.request_gemini")
    @patch("scripts.check_gemini.getpass")
    @patch("builtins.print")
    def test_missing_key_without_terminal_never_prompts_or_calls_provider(self, output, prompt, request, terminal):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(check_gemini.main(), 2)
        prompt.assert_not_called()
        request.assert_not_called()
