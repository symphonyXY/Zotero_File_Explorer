from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..core.classification import FilterRule, default_rules


def app_data_dir() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local/share")) / "ZoteroFileExplorer"


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


@dataclass
class Settings:
    language: str = "zh_CN"
    api_url: str = "http://127.0.0.1:23119/api/"
    data_directory: str = ""
    attachment_base: str = ""
    poll_seconds: int = 60
    hotkey: str = "Ctrl+Alt+Z"
    close_to_tray: bool = True
    quick_on_top: bool = True
    theme: str = "system"
    motion: str = "full"
    animation_speed: float = 1.0
    rules: list[dict] = field(default_factory=default_rules)
    hidden_columns: list[int] = field(default_factory=lambda: [3, 5, 6, 7])
    window_layouts: dict = field(default_factory=dict)

    def validate(self) -> None:
        from ..api.client import LocalAPI

        LocalAPI(self.api_url)
        if self.language not in {"zh_CN", "en"} or self.theme not in {"system", "light", "dark"}:
            raise ValueError("Invalid language or theme")
        if not 15 <= self.poll_seconds <= 86400:
            raise ValueError("Polling must be between 15 and 86400 seconds")
        if self.motion not in {"full", "reduced", "off"}:
            raise ValueError("Invalid motion mode")
        if not isinstance(self.animation_speed, (int, float)) or not 0.5 <= self.animation_speed <= 2:
            raise ValueError("Animation speed must be between 0.5 and 2")
        for rule in self.rules:
            FilterRule(**rule).validate()


class ConfigStore:
    def __init__(self, directory: Path | None = None):
        self.directory = (directory or app_data_dir()).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "settings.json"
        self.warning = ""

    def load(self) -> Settings:
        if not self.path.exists():
            return Settings()
        try:
            values = json.loads(self.path.read_text(encoding="utf-8"))
            known = {k: v for k, v in values.items() if k in Settings.__dataclass_fields__}
            settings = Settings(**known)
            settings.validate()
            return settings
        except (ValueError, TypeError, OSError):
            self.warning = "config_invalid"
            return Settings()

    def save(self, settings: Settings) -> None:
        settings.validate()
        # Preserve the unreadable user's configuration for diagnosis.
        if self.warning and self.path.exists():
            import time

            self.path.rename(self.path.with_suffix(f".invalid-{time.time_ns()}.json"))
            self.warning = ""
        atomic_json(self.path, asdict(settings))
