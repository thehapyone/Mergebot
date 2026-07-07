"""Symbol cache: stable keying across reviews, corrupt-entry tolerance, pruning."""

import json
import os
import time

from mergebot.context.symbols import CACHE_ENTRY_TTL_SECONDS, SymbolCache


def write_module(path, body="def fetch_user(user_id):\n    return user_id\n"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


class TestStableKeying:
    def test_hits_across_different_checkout_paths(self, tmp_path):
        """Two reviews clone into different temp dirs; a stable project key must let
        the second review hit entries the first one wrote."""
        cache_dir = tmp_path / "cache"
        review_a = write_module(tmp_path / "checkout-a" / "mod.py")
        review_b = write_module(tmp_path / "checkout-b" / "mod.py")

        cache_first = SymbolCache(cache_dir, cache_key="acme/project")
        _, hit_first = cache_first.get_or_parse(review_a)
        cache_second = SymbolCache(cache_dir, cache_key="acme/project")
        symbols, hit_second = cache_second.get_or_parse(review_b)

        assert hit_first is False
        assert hit_second is True
        assert symbols[0].name == "fetch_user"

    def test_distinct_projects_do_not_share_entries(self, tmp_path):
        module = write_module(tmp_path / "mod.py")
        SymbolCache(tmp_path / "cache", cache_key="acme/one").get_or_parse(module)
        _, hit = SymbolCache(tmp_path / "cache", cache_key="acme/two").get_or_parse(module)
        assert hit is False


class TestRobustness:
    def test_corrupt_entry_is_treated_as_miss_and_repaired(self, tmp_path):
        module = write_module(tmp_path / "mod.py")
        cache = SymbolCache(tmp_path / "cache", cache_key="acme/project")
        cache.get_or_parse(module)
        entry = next(cache.cache_dir.glob("*.json"))
        entry.write_text("{ truncated", encoding="utf-8")  # crash mid-write

        symbols, hit = cache.get_or_parse(module)
        assert hit is False
        assert symbols[0].name == "fetch_user"
        # the corrupt entry was overwritten with a valid one
        assert json.loads(entry.read_text(encoding="utf-8"))["version"]

    def test_prune_drops_only_expired_entries(self, tmp_path):
        module = write_module(tmp_path / "mod.py")
        cache = SymbolCache(tmp_path / "cache", cache_key="acme/project")
        cache.get_or_parse(module)
        fresh_entry = next(cache.cache_dir.glob("*.json"))
        expired_entry = cache.cache_dir / "deadbeef.json"
        expired_entry.write_text("{}", encoding="utf-8")
        old = time.time() - CACHE_ENTRY_TTL_SECONDS - 60
        os.utime(expired_entry, (old, old))
        # force the next construction to prune
        (cache.cache_dir / ".last-prune").unlink()

        SymbolCache(tmp_path / "cache", cache_key="acme/project")

        assert fresh_entry.exists()
        assert not expired_entry.exists()
