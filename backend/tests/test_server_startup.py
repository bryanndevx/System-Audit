import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import uvicorn

import run_backend
from app.event_loop import create_psycopg_compatible_event_loop


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


class BackendRunnerTests(unittest.TestCase):
    @patch("run_backend.uvicorn.run")
    def test_starts_uvicorn_with_the_compatible_event_loop(self, run):
        run_backend.main()

        run.assert_called_once_with(
            run_backend.APP_IMPORT_PATH,
            host="127.0.0.1",
            port=8000,
            loop=run_backend.EVENT_LOOP_FACTORY,
        )


if __name__ == "__main__":
    unittest.main()
