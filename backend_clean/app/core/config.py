from pathlib import Path
import os


BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def frontend_base_url() -> str:
    return (os.getenv("FRONTEND_BASE_URL") or "http://127.0.0.1:5173").rstrip("/")
