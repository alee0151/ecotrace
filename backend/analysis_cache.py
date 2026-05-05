"""
Disk-backed cache for expensive analysis pipeline results.

The news and uploaded-report evidence steps call external APIs and LLMs. This
cache keeps those results reusable across backend restarts without requiring a
database migration in local/demo environments.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional


CACHE_DIR = Path(__file__).resolve().parent / "cache" / "analysis"


def analysis_cache_enabled() -> bool:
    value = os.getenv("ANALYSIS_CACHE_ENABLED", "true").strip().lower()
    return value not in {"0", "false", "no", "off"}


def analysis_cache_ttl_hours(cache_type: str) -> int:
    env_name = f"{cache_type.upper()}_ANALYSIS_CACHE_TTL_HOURS"
    default = "24" if cache_type == "news" else "168"
    try:
        return max(0, int(os.getenv(env_name, default)))
    except ValueError:
        return int(default)


def analysis_model_fingerprint() -> Dict[str, str]:
    provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    return {
        "provider": provider,
        "openrouter_model": os.getenv("OPENROUTER_MODEL", "").strip(),
        "nvidia_model": os.getenv("NVIDIA_NIM_MODEL", "").strip(),
    }


def stable_cache_key(cache_type: str, params: Dict[str, Any]) -> str:
    payload = {"cache_type": cache_type, "params": params}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _cache_path(cache_type: str, cache_key: str) -> Path:
    return CACHE_DIR / cache_type / f"{cache_key}.json"


def get_analysis_cache(cache_type: str, cache_key: str) -> Optional[Dict[str, Any]]:
    if not analysis_cache_enabled():
        return None

    path = _cache_path(cache_type, cache_key)
    if not path.exists():
        return None

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        expires_at = datetime.fromisoformat(payload["expires_at"])
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None

    if expires_at <= datetime.now(timezone.utc):
        return None
    data = payload.get("payload")
    return data if isinstance(data, dict) else None


def set_analysis_cache(cache_type: str, cache_key: str, payload: Dict[str, Any]) -> None:
    if not analysis_cache_enabled():
        return

    ttl_hours = analysis_cache_ttl_hours(cache_type)
    if ttl_hours <= 0:
        return

    now = datetime.now(timezone.utc)
    record = {
        "cache_type": cache_type,
        "cache_key": cache_key,
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=ttl_hours)).isoformat(),
        "payload": payload,
    }

    path = _cache_path(cache_type, cache_key)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(record, ensure_ascii=True, indent=2), encoding="utf-8")
        tmp_path.replace(path)
    except OSError:
        pass
