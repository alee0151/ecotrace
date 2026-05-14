import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from backend_clean.app.cache import analysis_cache


class AnalysisCacheTests(unittest.TestCase):
    def test_stable_cache_key_ignores_dict_order(self):
        first = analysis_cache.stable_cache_key("news", {"b": 2, "a": 1})
        second = analysis_cache.stable_cache_key("news", {"a": 1, "b": 2})

        self.assertEqual(first, second)

    def test_set_and_get_analysis_cache_round_trip(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(analysis_cache, "CACHE_DIR", Path(temp_dir)):
                with patch.dict(os.environ, {"NEWS_ANALYSIS_CACHE_TTL_HOURS": "1"}):
                    cache_key = analysis_cache.stable_cache_key("news", {"company": "BHP"})

                    analysis_cache.set_analysis_cache("news", cache_key, {"evidence": [{"id": 1}]})

                    self.assertEqual(
                        analysis_cache.get_analysis_cache("news", cache_key),
                        {"evidence": [{"id": 1}]},
                    )

    def test_expired_analysis_cache_returns_none(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_dir = Path(temp_dir)
            cache_key = "expired"
            target = cache_dir / "news" / f"{cache_key}.json"
            target.parent.mkdir(parents=True)
            target.write_text(
                json.dumps(
                    {
                        "expires_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
                        "payload": {"evidence": [{"id": 1}]},
                    }
                ),
                encoding="utf-8",
            )

            with patch.object(analysis_cache, "CACHE_DIR", cache_dir):
                self.assertIsNone(analysis_cache.get_analysis_cache("news", cache_key))


if __name__ == "__main__":
    unittest.main()
