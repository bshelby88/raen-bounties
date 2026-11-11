"""Unit tests for BOUNTY-04 x402 manifest drift watcher."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import watch_x402_drift as W  # noqa: E402


def test_clean_manifest_passes() -> None:
    expected = [
        {
            "service": "raen-law-lookup",
            "url": "https://law.raen.ai",
            "scheme": "exact",
            "network": "base",
            "payTo": "0x971b573b47357c22a67FcE8c56Aaeb478356C942",
        }
    ]
    ok, reports = W.check_fleet(
        expected,
        fetcher=lambda _u, _t: {
            "accepts": [
                {
                    "scheme": "exact",
                    "network": "base",
                    "payTo": "0x971b573b47357c22a67FcE8c56Aaeb478356C942",
                }
            ]
        },
    )
    assert ok is True
    assert len(reports) == 1
    assert reports[0].drifts == []


def test_drifted_payto_is_caught_and_diffed() -> None:
    expected = [
        {
            "service": "raen-dispute-letter",
            "url": "https://dispute.raen.ai",
            "scheme": "exact",
            "network": "base",
            "payTo": "0x971b573b47357c22a67FcE8c56Aaeb478356C942",
        }
    ]
    ok, reports = W.check_fleet(
        expected,
        fetcher=lambda _u, _t: {
            "scheme": "exact",
            "network": "base",
            "payTo": "0x000000000000000000000000000000000000dEaD",
        },
    )
    assert ok is False
    assert len(reports[0].drifts) == 1
    assert reports[0].drifts[0].field == "payTo"
    comment = W.render_diff_comment(reports)
    assert "DRIFT DETECTED" in comment
    assert "0x000000000000000000000000000000000000dEaD" in comment
