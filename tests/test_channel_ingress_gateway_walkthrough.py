from __future__ import annotations

import asyncio
from pathlib import Path

import scripts.channel_ingress_gateway_walkthrough as walkthrough


def test_channel_ingress_gateway_walkthrough_run_all_passes(tmp_path: Path) -> None:
    results = asyncio.run(walkthrough._run_all(tmp_path / "channel-ingress"))

    assert [item.name for item in results] == [
        "channel-reuse-and-continue",
        "channel-activity-and-takeover",
    ]
    assert all(item.ok for item in results)

    reuse_step = next(item for item in results if item.name == "channel-reuse-and-continue")
    assert "origin=qq active=qq" in reuse_step.excerpts["detail"]
    assert "continue from qq" in reuse_step.excerpts["recent_messages"]

    activity_step = next(item for item in results if item.name == "channel-activity-and-takeover")
    assert "origin=qq active=qq" in activity_step.excerpts["detail_before_takeover"]
    assert "origin=qq active=tui" in activity_step.excerpts["detail_after_takeover"]
