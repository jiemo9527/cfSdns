import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


playwright_module = types.ModuleType("playwright")
async_api_module = types.ModuleType("playwright.async_api")
setattr(async_api_module, "async_playwright", lambda: None)
sys.modules.setdefault("playwright", playwright_module)
sys.modules.setdefault("playwright.async_api", async_api_module)

from src import webTestUnion


class FakePlaywrightManager:
    async def __aenter__(self):
        return types.SimpleNamespace(chromium=object())

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeContext:
    async def add_init_script(self, script):
        return None

    async def close(self):
        return None


class WebTestUnionTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_itdog_test_retries_and_then_succeeds(self):
        fake_context = FakeContext()
        fake_page = object()

        async def fake_open_page(context, event):
            return fake_page

        async def fake_run_workflow(page, event, target_host, custom_dns):
            event.set()
            return '{"ok": true}'

        with patch.object(webTestUnion, "async_playwright", return_value=FakePlaywrightManager()), \
             patch.object(webTestUnion, "_prepare_itdog_user_data_dir", side_effect=[("base", False), ("retry", True)]), \
             patch.object(webTestUnion, "_cleanup_chromium_singleton_files"), \
             patch.object(webTestUnion, "_cleanup_temporary_user_data_dir"), \
             patch.object(webTestUnion, "_launch_persistent_context", new=AsyncMock(side_effect=[RuntimeError("boom"), fake_context])), \
             patch.object(webTestUnion, "_open_itdog_page", new=AsyncMock(side_effect=fake_open_page)), \
             patch.object(webTestUnion, "_run_itdog_workflow", new=AsyncMock(side_effect=fake_run_workflow)), \
             patch.object(webTestUnion, "_save_debug_screenshot", new=AsyncMock()), \
             patch.object(webTestUnion.asyncio, "sleep", new=AsyncMock()):
            result = await webTestUnion.run_itdog_test("temp.example.com", "119.29.29.29")

        self.assertEqual(result, '{"ok": true}')

    async def test_run_itdog_test_returns_none_after_all_attempts_fail(self):
        with patch.object(webTestUnion, "async_playwright", return_value=FakePlaywrightManager()), \
             patch.object(webTestUnion, "_prepare_itdog_user_data_dir", side_effect=[("base", False), ("retry1", True), ("retry2", True)]), \
             patch.object(webTestUnion, "_cleanup_chromium_singleton_files"), \
             patch.object(webTestUnion, "_cleanup_temporary_user_data_dir"), \
             patch.object(webTestUnion, "_launch_persistent_context", new=AsyncMock(side_effect=RuntimeError("boom"))), \
             patch.object(webTestUnion, "_save_debug_screenshot", new=AsyncMock()), \
             patch.object(webTestUnion.asyncio, "sleep", new=AsyncMock()):
            result = await webTestUnion.run_itdog_test("temp.example.com", "119.29.29.29")

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
