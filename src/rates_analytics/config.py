"""Environment-driven configuration.

A single place where external inputs (API keys, model choices, paths) enter
the library. Nothing here reads the environment at import time; call
``Settings.from_env`` so tests can inject explicit mappings.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

#: Task names understood by the model router in
#: :mod:`rates_analytics.llm.router`.
TASKS = ("research", "code", "fast")


@dataclass(frozen=True)
class Settings:
    """Runtime settings, defaults aimed at the OpenRouter API.

    Attributes
    ----------
    openrouter_api_key : str
        Secret key from https://openrouter.ai/keys. Empty string when unset.
    research_model : str
        Model routed to long-context reasoning tasks.
    code_model : str
        Model routed to code generation and review tasks.
    fast_model : str
        Model routed to cheap, low-latency tasks.
    data_dir : Path
        Default location for cached market data.

    """

    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_app_url: str = "https://github.com/amritchachadi/ficc-lab"
    openrouter_app_title: str = "ficc-lab"
    research_model: str = "anthropic/claude-sonnet-5"
    code_model: str = "moonshotai/kimi-k2.7-code"
    fast_model: str = "google/gemini-3.8-flash"
    data_dir: Path = Path("data")

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        """Build settings from the environment.

        Loads ``.env`` from the working directory first (no override of
        existing variables), then reads the process environment -- unless an
        explicit ``env`` mapping is given, which tests use for hermetic setup.

        Parameters
        ----------
        env : Mapping[str, str] | None
            Explicit environment; ``None`` means the real one.

        Returns
        -------
        Settings
            Populated settings object.

        """
        source: Mapping[str, str] = os.environ if env is None else env
        if env is None:
            load_dotenv(override=False)
            source = os.environ
        return cls(
            openrouter_api_key=source.get("OPENROUTER_API_KEY", ""),
            openrouter_base_url=source.get("OPENROUTER_BASE_URL", cls.openrouter_base_url),
            openrouter_app_url=source.get("OPENROUTER_APP_URL", cls.openrouter_app_url),
            openrouter_app_title=source.get("OPENROUTER_APP_TITLE", cls.openrouter_app_title),
            research_model=source.get("FICC_LAB_RESEARCH_MODEL", cls.research_model),
            code_model=source.get("FICC_LAB_CODE_MODEL", cls.code_model),
            fast_model=source.get("FICC_LAB_FAST_MODEL", cls.fast_model),
            data_dir=Path(source.get("FICC_LAB_DATA_DIR", str(cls.data_dir))),
        )

    @property
    def has_openrouter(self) -> bool:
        """Whether an OpenRouter key is configured."""
        return bool(self.openrouter_api_key)
