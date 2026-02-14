"""
Vyuha AI — Learning Engine
==========================
Lightweight persistent event store + analytics for autonomous improvement.

Stores runtime events as JSON Lines and produces:
  - failure hotspots
  - latency summaries
  - actionable recommendations
"""

from __future__ import annotations

import json
import threading
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LOCK = threading.Lock()
_DATA_DIR = Path(__file__).resolve().parents[1] / "data"
_EVENTS_FILE = _DATA_DIR / "agent_events.jsonl"
_MAX_RECENT_EVENTS = 80


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_store() -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not _EVENTS_FILE.exists():
        _EVENTS_FILE.touch()


def record_event(event_type: str, payload: dict[str, Any]) -> None:
    """Persist one event to JSONL storage."""
    _ensure_store()
    event = {
        "timestamp": _now_iso(),
        "event_type": event_type,
        "payload": payload,
    }
    line = json.dumps(event, separators=(",", ":"))
    with _LOCK:
        with _EVENTS_FILE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


def _load_events(limit: int = 500) -> list[dict[str, Any]]:
    _ensure_store()
    with _LOCK:
        lines = _EVENTS_FILE.read_text(encoding="utf-8").splitlines()
    selected = lines[-limit:] if limit > 0 else lines
    events: list[dict[str, Any]] = []
    for line in selected:
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def _build_recommendations(
    blocked_count: int,
    guard_sources: Counter,
    avg_act_ms: float,
    avg_scan_ms: float,
) -> list[str]:
    recs: list[str] = []
    if blocked_count > 0:
        recs.append(
            "Commander prompts should explicitly avoid deny-listed commands "
            "when proposing emergency maneuvers."
        )
    if guard_sources.get("fallback", 0) > guard_sources.get("white_circle", 0):
        recs.append(
            "Security validation frequently uses fallback mode. Investigate "
            "White Circle availability to strengthen policy enforcement."
        )
    if avg_act_ms > 3500:
        recs.append(
            "Agent loop latency is elevated. Cache model/system prompt context "
            "and reduce response token budget for faster decisions."
        )
    if avg_scan_ms > 1800:
        recs.append(
            "Scan latency is elevated. Consider caching TLE responses for short "
            "intervals during demo bursts."
        )
    if not recs:
        recs.append(
            "System health is stable. Continue collecting traces and expand "
            "edge-case simulations to harden autonomous behavior."
        )
    return recs


def get_insights() -> dict[str, Any]:
    """Return aggregated learning metrics + recent events."""
    events = _load_events(limit=800)
    if not events:
        return {
            "summary": {
                "total_events": 0,
                "scan_events": 0,
                "act_events": 0,
                "blocked_attempts": 0,
                "execution_success_rate": 0.0,
            },
            "latency_ms": {"scan_avg": 0.0, "act_avg": 0.0},
            "failure_hotspots": {"violation_tags": {}, "security_sources": {}},
            "recommendations": [
                "No runtime data yet. Run scans and maneuvers to build insights.",
            ],
            "recent_events": [],
        }

    scan_count = 0
    act_count = 0
    successful_exec = 0
    blocked_attempts = 0
    scan_latencies: list[float] = []
    act_latencies: list[float] = []
    tag_counter: Counter = Counter()
    source_counter: Counter = Counter()
    scenario_counter: Counter = Counter()
    endpoint_errors: defaultdict[str, int] = defaultdict(int)

    for event in events:
        etype = event.get("event_type", "")
        payload = event.get("payload", {})

        if etype == "scan":
            scan_count += 1
            scan_latencies.append(float(payload.get("latency_ms", 0)))
            scenario_counter.update([payload.get("scenario_mode", "UNKNOWN")])
            if payload.get("status") == "ERROR":
                endpoint_errors["scan"] += 1

        elif etype == "act":
            act_count += 1
            act_latencies.append(float(payload.get("latency_ms", 0)))
            if payload.get("status") == "EXECUTED":
                successful_exec += 1
            if payload.get("status", "").startswith("MANUAL_"):
                endpoint_errors["act"] += 1

            for attempt in payload.get("attempts_log", []):
                validation = attempt.get("validation", {})
                source = validation.get("source", "unknown")
                source_counter.update([source])
                tags = validation.get("violation_tags", [])
                if validation.get("valid") is False:
                    blocked_attempts += 1
                    tag_counter.update(tags if tags else ["UNKNOWN"])

    avg_scan_ms = round(sum(scan_latencies) / len(scan_latencies), 2) if scan_latencies else 0.0
    avg_act_ms = round(sum(act_latencies) / len(act_latencies), 2) if act_latencies else 0.0
    success_rate = round((successful_exec / act_count) * 100, 2) if act_count else 0.0

    recommendations = _build_recommendations(
        blocked_count=blocked_attempts,
        guard_sources=source_counter,
        avg_act_ms=avg_act_ms,
        avg_scan_ms=avg_scan_ms,
    )

    recent = events[-_MAX_RECENT_EVENTS:]
    return {
        "summary": {
            "total_events": len(events),
            "scan_events": scan_count,
            "act_events": act_count,
            "blocked_attempts": blocked_attempts,
            "execution_success_rate": success_rate,
            "endpoint_errors": dict(endpoint_errors),
            "scenario_distribution": dict(scenario_counter),
        },
        "latency_ms": {
            "scan_avg": avg_scan_ms,
            "act_avg": avg_act_ms,
        },
        "failure_hotspots": {
            "violation_tags": dict(tag_counter),
            "security_sources": dict(source_counter),
        },
        "recommendations": recommendations,
        "recent_events": recent,
    }

