import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import breakout_panel as bp

ROOT = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 10, 3, 12, tzinfo=timezone.utc)


def _repo(name, stars, days_old):
    created = (NOW - timedelta(days=days_old)).isoformat().replace("+00:00", "Z")
    return {"full_name": name, "stargazers_count": stars, "created_at": created, "description": ""}


class Score(unittest.TestCase):
    # Same three cases as new-term-radar's tests/test_radar.py, so scoring stays identical.
    def test_fast_repo_flagged_slow_repo_skipped(self):
        rows = bp.score([_repo("Niko1221/Strata", 7734, 9), _repo("a/slow", 900, 12)], None, NOW)
        self.assertEqual([r["repo"] for r in rows], ["Niko1221/Strata"])

    def test_jump_since_last_snapshot_flagged(self):
        rows = bp.score([_repo("a/late", 1500, 13)], {"a/late": 900}, NOW)
        self.assertEqual(rows[0]["delta"], 600)

    def test_variants_include_handle_and_display_name(self):
        row = {"owner": "Niko1221", "name": "Strata"}
        self.assertEqual(bp.variants(row, "Niko"), ["strata", "niko1221 strata", "niko strata"])
        self.assertEqual(bp.variants(row, ""), ["strata", "niko1221 strata"])


class Panel(unittest.TestCase):
    def test_panel_config_has_a_box_and_flow_per_repo(self):
        rows = bp.score([_repo("Niko1221/Strata", 7734, 9), _repo("b/fast", 4000, 2)], None, NOW)
        cfg = bp.panel_config(rows)
        boxes = [e for e in cfg["elements"] if e["type"] == "box"]
        flows = [e for e in cfg["elements"] if e["type"] == "flow"]
        self.assertEqual(len(boxes), 3)  # GitHub source box + one per repo
        self.assertEqual(len(flows), 2)
        self.assertIn("Niko1221/Strata", json.dumps(cfg))

    def test_render_upstream_minimal_config_is_self_contained(self):
        cfg = json.loads((ROOT / "fixtures" / "minimal.json").read_text(encoding="utf-8"))
        html = bp.render(cfg)
        self.assertIn('id="live-config"', html)
        self.assertIn("USER -> AGENT -> TOOLS", html)
        self.assertNotIn("<script src", html)

    def test_render_escapes_closing_script_tags(self):
        html = bp.render({"elements": [{"type": "text", "x": 0, "y": 10, "t": "</script><b>x"}]})
        self.assertNotIn("</script><b>", html)


if __name__ == "__main__":
    unittest.main()
