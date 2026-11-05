"""配置与模型工厂测试（不发起网络请求）。"""

from __future__ import annotations

import os
import unittest

from langchain_deepseek import ChatDeepSeek

from app.agent import NotConfiguredError, build_model
from app.config import Settings, get_settings, sync_langsmith_env


class SettingsTests(unittest.TestCase):
    def test_blank_key_means_not_configured(self) -> None:
        settings = Settings(deepseek_api_key="   ")
        self.assertFalse(settings.is_configured)

    def test_placeholder_key_rejected(self) -> None:
        self.assertFalse(Settings(deepseek_api_key="your-api-key").is_configured)
        self.assertTrue(Settings(deepseek_api_key="sk-abc123").is_configured)

    def test_cors_parsing(self) -> None:
        settings = Settings(cors_origins="http://a.com, http://b.com")
        self.assertEqual(settings.cors_origin_list, ["http://a.com", "http://b.com"])

    def test_summary_model_fallback(self) -> None:
        settings = Settings(deepseek_model="deepseek-v4-flash", deepseek_summary_model="")
        self.assertEqual(settings.summary_model_name, "deepseek-v4-flash")
        settings = Settings(deepseek_model="m1", deepseek_summary_model="m2")
        self.assertEqual(settings.summary_model_name, "m2")

    def test_singleton_cached(self) -> None:
        self.assertIs(get_settings(), get_settings())


class ModelFactoryTests(unittest.TestCase):
    def test_build_model_with_fake_key(self) -> None:
        settings = Settings(
            deepseek_api_key="sk-unit-test",
            deepseek_base_url="https://example.com/v1",
            deepseek_model="deepseek-v4-pro",
            temperature=0.0,
            max_tokens=512,
        )
        model = build_model(settings)
        self.assertIsInstance(model, ChatDeepSeek)
        self.assertEqual(model.model_name, "deepseek-v4-pro")
        self.assertEqual(model.api_base, "https://example.com/v1")
        self.assertEqual(model.temperature, 0.0)

    def test_build_model_without_key_raises(self) -> None:
        with self.assertRaises(NotConfiguredError) as ctx:
            build_model(Settings(deepseek_api_key=None))
        self.assertIn("DEEPSEEK_API_KEY", str(ctx.exception))

    def test_langsmith_env_sync(self) -> None:
        settings = Settings(
            deepseek_api_key="sk-x",
            langsmith_tracing=True,
            langsmith_api_key="ls-key",
            langsmith_project="unit-project",
        )
        backup = {key: os.environ.get(key) for key in ("LANGSMITH_TRACING", "LANGSMITH_API_KEY", "LANGSMITH_PROJECT")}
        try:
            sync_langsmith_env(settings)
            self.assertEqual(os.environ["LANGSMITH_TRACING"], "true")
            self.assertEqual(os.environ["LANGSMITH_API_KEY"], "ls-key")
            self.assertEqual(os.environ["LANGSMITH_PROJECT"], "unit-project")
        finally:
            for key, value in backup.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_tracing_without_key_disabled(self) -> None:
        settings = Settings(deepseek_api_key="sk-x", langsmith_tracing=True, langsmith_api_key=None)
        backup = os.environ.get("LANGSMITH_TRACING")
        try:
            sync_langsmith_env(settings)
            self.assertEqual(os.environ["LANGSMITH_TRACING"], "false")
        finally:
            if backup is None:
                os.environ.pop("LANGSMITH_TRACING", None)
            else:
                os.environ["LANGSMITH_TRACING"] = backup


if __name__ == "__main__":
    unittest.main()
