import json
import os
import copy

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CONFIG_PATH = os.path.join(APP_DIR, "data", "config.json")

DEFAULT_CONFIG = {
    "journal_dir": os.path.join(os.path.dirname(APP_DIR), "OpenCode", "journal"),
    "ai": {
        "enabled": False,
        "provider": "deepseek",
        "base_url": "https://api.deepseek.com/v1",
        "api_key": "",
        "model": "deepseek-chat",
        "temperature": 0.7,
        "timeout": 180,
    },
    "monitor": {
        "enabled": True,
        "poll_interval": 5,
        "idle_threshold": 180,
        "flush_interval": 60,
    },
}


def default_config() -> dict:
    return copy.deepcopy(DEFAULT_CONFIG)


def load_config(path: str = None) -> dict:
    path = path or DEFAULT_CONFIG_PATH
    cfg = default_config()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                user_cfg = json.load(f)
            _deep_merge(cfg, user_cfg)
        except Exception:
            pass
    return cfg


def _deep_merge(base: dict, override: dict) -> None:
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v


def save_config(cfg: dict, path: str = None) -> str:
    path = path or DEFAULT_CONFIG_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    return path
