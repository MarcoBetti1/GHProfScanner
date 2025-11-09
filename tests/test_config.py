from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from github_scanner.config import AppConfig, load_config


class ConfigTests(unittest.TestCase):
    def test_load_default_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = load_config(Path(tmp) / "missing.yaml")
        self.assertIsInstance(config, AppConfig)
        self.assertTrue(config.modes.docs_only)
        self.assertTrue(config.modes.owned_repos_only)
        self.assertEqual(config.llm.provider, "openai")

    def test_load_custom_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_file = Path(tmp) / "settings.yaml"
            config_file.write_text(
                """
                modes:
                  docs_only: false
                  owned_repos_only: false
                llm:
                  provider: openai
                  model: gpt-4o
                  temperature: 0.5
                  max_output_tokens: 800
                  api_key_env: ALT_KEY
                output:
                  directory: custom_reports
                  format: markdown
                """,
                encoding="utf-8",
            )

            config = load_config(config_file)

        self.assertFalse(config.modes.docs_only)
        self.assertFalse(config.modes.owned_repos_only)
        self.assertEqual(config.llm.model, "gpt-4o")
        self.assertEqual(config.llm.api_key_env, "ALT_KEY")
        self.assertEqual(config.output.directory, Path("custom_reports"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
