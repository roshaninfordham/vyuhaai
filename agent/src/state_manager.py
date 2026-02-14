"""
Vyuha AI — Spacecraft State Manager
====================================
File-based persistent state for position, trajectory, and maneuver history.
Works with Blaxel agent deployment (writable filesystem in container).
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LOCK = threading.Lock()
_DATA_DIR = Path(__file__).resolve().parents[1] / "data"
_STATE_FILE = _DATA_DIR / "spacecraft_state.json"

_DEFAULT_STATE: dict[str, Any] = {
    "position": {"lat": 0.0, "lon": 0.0, "alt_km": 400.0},
    "velocity": {"x": 0.0, "y": 7800.0, "z": 0.0},
    "original_trajectory": None,
    "last_maneuver": None,
    "maneuver_history": [],
    "updated_at": None,
}


def _ensure_dir() -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_state() -> dict[str, Any]:
    """Load spacecraft state from disk. Returns default if missing or invalid."""
    _ensure_dir()
    if not _STATE_FILE.exists():
        state = _DEFAULT_STATE.copy()
        state["updated_at"] = _now_iso()
        return state
    with _LOCK:
        try:
            raw = _STATE_FILE.read_text(encoding="utf-8")
            data = json.loads(raw)
            if isinstance(data, dict):
                data.setdefault("maneuver_history", [])
                data.setdefault("original_trajectory", None)
                data.setdefault("last_maneuver", None)
                data.setdefault("position", _DEFAULT_STATE["position"])
                data.setdefault("velocity", _DEFAULT_STATE["velocity"])
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return _DEFAULT_STATE.copy()


def save_state(state: dict[str, Any]) -> None:
    """Persist spacecraft state to disk."""
    _ensure_dir()
    state = dict(state)
    state["updated_at"] = _now_iso()
    with _LOCK:
        _STATE_FILE.write_text(
            json.dumps(state, indent=2),
            encoding="utf-8",
        )


def apply_maneuver(
    current_state: dict[str, Any],
    risk_data: dict[str, Any],
    final_command: dict[str, Any],
) -> dict[str, Any]:
    """
    Update in-memory state after an executed maneuver.
    Does not write to disk; caller should call save_state() after.
    """
    state = dict(current_state)
    lat = risk_data.get("latitude", state["position"].get("lat", 0))
    lon = risk_data.get("longitude", state["position"].get("lon", 0))
    alt = risk_data.get("altitude_km", state["position"].get("alt_km", 400))

    if not state.get("original_trajectory"):
        state["original_trajectory"] = {
            "position": dict(state["position"]),
            "velocity": dict(state["velocity"]),
            "timestamp": _now_iso(),
        }

    state["position"] = {"lat": lat, "lon": lon, "alt_km": alt}
    state["last_maneuver"] = {
        "timestamp": _now_iso(),
        "reason": "collision_avoidance",
        "action": final_command.get("action"),
        "thrust_direction": final_command.get("recommended_thrust_direction"),
        "confidence": final_command.get("confidence_score"),
    }
    state["maneuver_history"] = state.get("maneuver_history", []) + [
        state["last_maneuver"],
    ]
    return state


def restore_original_trajectory(current_state: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """
    Restore state to original_trajectory and clear original.
    Returns (updated_state, restored).
    """
    state = dict(current_state)
    orig = state.get("original_trajectory")
    if not orig:
        return state, False
    state["position"] = dict(orig.get("position", state["position"]))
    state["velocity"] = dict(orig.get("velocity", state["velocity"]))
    state["original_trajectory"] = None
    state["last_maneuver"] = {
        "timestamp": _now_iso(),
        "reason": "trajectory_restoration",
        "action": "HOLD_POSITION",
    }
    return state, True


# Module-level state instance for FastAPI to use
_state: dict[str, Any] = {}


def get_state() -> dict[str, Any]:
    global _state
    if not _state:
        _state = load_state()
    return _state


def set_state(state: dict[str, Any], persist: bool = True) -> None:
    global _state
    _state = state
    if persist:
        save_state(state)


def reset_state_to_default() -> dict[str, Any]:
    global _state
    _state = _DEFAULT_STATE.copy()
    _state["updated_at"] = _now_iso()
    save_state(_state)
    return _state
