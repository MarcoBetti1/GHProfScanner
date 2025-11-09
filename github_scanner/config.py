from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


DEFAULT_CONFIG_PATH = Path("config/settings.yaml")


@dataclass(slots=True)
class ModeConfig:
    docs_only: bool = True
    owned_repos_only: bool = True


@dataclass(slots=True)
class LLMConfig:
    provider: str = "openai"
    model: str = "gpt-4o-mini"
    temperature: float = 0.2
    max_output_tokens: int = 1200
    api_key_env: str = "OPENAI_API_KEY"
    organization: Optional[str] = None


@dataclass(slots=True)
class OutputConfig:
    directory: Path = Path("reports")
    format: str = "markdown"
    show_repo_tables: bool = True


@dataclass(slots=True)
class AppConfig:
    modes: ModeConfig = field(default_factory=ModeConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    output: OutputConfig = field(default_factory=OutputConfig)


def load_config(path: Optional[Path] = None) -> AppConfig:
    config_path = path or DEFAULT_CONFIG_PATH
    if not config_path.exists():
        return AppConfig()

    with config_path.open("r", encoding="utf-8") as handle:
        raw: Dict[str, Any] = yaml.safe_load(handle) or {}

    modes_raw = raw.get("modes", {})
    llm_raw = raw.get("llm", {})
    output_raw = raw.get("output", {})

    config = AppConfig(
        modes=ModeConfig(
            docs_only=bool(modes_raw.get("docs_only", True)),
            owned_repos_only=bool(modes_raw.get("owned_repos_only", True)),
        ),
        llm=LLMConfig(
            provider=str(llm_raw.get("provider", "openai")),
            model=str(llm_raw.get("model", "gpt-4o-mini")),
            temperature=float(llm_raw.get("temperature", 0.2)),
            max_output_tokens=int(llm_raw.get("max_output_tokens", 1200)),
            api_key_env=str(llm_raw.get("api_key_env", "OPENAI_API_KEY")),
            organization=llm_raw.get("organization"),
        ),
        output=OutputConfig(
            directory=Path(output_raw.get("directory", "reports")),
            format=str(output_raw.get("format", "markdown")),
            show_repo_tables=bool(output_raw.get("show_repo_tables", True)),
        ),
    )

    return config
