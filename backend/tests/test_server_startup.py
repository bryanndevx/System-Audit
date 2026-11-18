import asyncio
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import uvicorn

import run_backend
from app.event_loop import create_psycopg_compatible_event_loop

CONFIGURED_ENVIRONMENT = {
    "APP_ENV": "development",
    "APP_ORIGIN": "http://localhost:5173",
    "SESSION_TTL_MINUTES": "480",
    "DB_HOST": "127.0.0.1",
    "DB_PORT": "5432",
    "DB_NAME": "sistema_auditoria",
    "DB_USER": "postgres",
    "DB_PASSWORD": "temporary-test-value",
}


class EventLoopFactoryTests(unittest.TestCase):
    def test_uses_selector_event_loop_on_windows(self):
        with patch("app.event_loop.sys", SimpleNamespace(platform="win32")):
            loop = create_psycopg_compatible_event_loop()

        try:
            self.assertIsInstance(loop, asyncio.SelectorEventLoop)
        finally:
            loop.close()

    def test_uses_default_event_loop_outside_windows(self):
        expected_loop = object()
        with (
            patch("app.event_loop.sys", SimpleNamespace(platform="linux")),
            patch("app.event_loop.asyncio.new_event_loop", return_value=expected_loop),
        ):
            loop = create_psycopg_compatible_event_loop()

        self.assertIs(loop, expected_loop)

    def test_uvicorn_resolves_the_custom_event_loop_factory(self):
        config = uvicorn.Config(
            run_backend.APP_IMPORT_PATH,
            loop=run_backend.EVENT_LOOP_FACTORY,
        )

        self.assertIs(
            config.get_loop_factory(),
            create_psycopg_compatible_event_loop,
        )


@patch("run_backend.load_local_gemini_environment", new=lambda: None)
class BackendRunnerTests(unittest.TestCase):
    @patch("run_backend.check_internal_database_connection")
    @patch("run_backend.uvicorn.run")
    def test_starts_uvicorn_with_the_compatible_event_loop(self, run, check):
        with patch.dict(os.environ, CONFIGURED_ENVIRONMENT, clear=True):
            run_backend.main()

        run.assert_called_once_with(
            run_backend.APP_IMPORT_PATH,
            host="127.0.0.1",
            port=8000,
            loop=run_backend.EVENT_LOOP_FACTORY,
        )
        check.assert_called_once()

    @patch("run_backend.check_internal_database_connection")
    @patch("run_backend.has_interactive_terminal", return_value=True)
    @patch("run_backend.getpass", return_value="temporary-test-value")
    def test_prepares_safe_local_defaults_and_prompts_for_password(
        self,
        prompt,
        isatty,
        check,
    ):
        with patch.dict(os.environ, {}, clear=True):
            run_backend.prepare_runtime_configuration()

            self.assertEqual(os.environ["APP_ENV"], "development")
            self.assertEqual(os.environ["APP_ORIGIN"], "http://localhost:5173")
            self.assertEqual(os.environ["DB_NAME"], "sistema_auditoria")
            self.assertEqual(os.environ["DB_USER"], "postgres")
            self.assertEqual(os.environ["DB_PASSWORD"], "temporary-test-value")
            self.assertEqual(os.environ["AUDITED_DB_SSL_MODE"], "disable")

        prompt.assert_called_once()
        check.assert_called_once()

    @patch("run_backend.check_internal_database_connection")
    @patch("run_backend.getpass")
    @patch("run_backend.has_interactive_terminal", return_value=False)
    def test_missing_password_without_terminal_fails_before_prompting(
        self, isatty, prompt, check,
    ):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "terminal interactiva"):
                run_backend.prepare_runtime_configuration()
        prompt.assert_not_called()
        check.assert_not_called()

    @patch("run_backend.check_internal_database_connection")
    def test_normalizes_development_environment(self, check):
        for environment in ("", "  DEVELOPMENT  "):
            with self.subTest(environment=environment):
                with patch.dict(
                    os.environ,
                    {**CONFIGURED_ENVIRONMENT, "APP_ENV": environment},
                    clear=True,
                ):
                    run_backend.prepare_runtime_configuration()
                    self.assertEqual(os.environ["APP_ENV"], "development")

    @patch("run_backend.check_internal_database_connection")
    def test_invalid_external_policy_is_detected_before_database_connection(self, check):
        with patch.dict(
            os.environ,
            {**CONFIGURED_ENVIRONMENT, "AUDITED_DB_ALLOWED_PORTS": "invalid"},
            clear=True,
        ):
            with self.assertRaisesRegex(ValueError, "allowlist"):
                run_backend.prepare_runtime_configuration()
        check.assert_not_called()

    @patch("run_backend.prepare_runtime_configuration", side_effect=EOFError)
    @patch("run_backend.uvicorn.run")
    @patch("run_backend.sys.stderr")
    def test_cancelled_password_input_does_not_start_server(self, stderr, run, prepare):
        with self.assertRaises(SystemExit) as raised:
            run_backend.main()
        self.assertEqual(raised.exception.code, 130)
        run.assert_not_called()

    @patch("run_backend.check_internal_database_connection")
    @patch("run_backend.getpass")
    def test_production_does_not_receive_local_defaults(self, prompt, check):
        with patch.dict(os.environ, {"APP_ENV": "production"}, clear=True):
            with self.assertRaisesRegex(
                ValueError,
                "Faltan variables de entorno requeridas",
            ):
                run_backend.prepare_runtime_configuration()

            self.assertNotIn("DB_HOST", os.environ)

        prompt.assert_not_called()
        check.assert_not_called()


if __name__ == "__main__":
    unittest.main()
