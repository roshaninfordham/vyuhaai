"""
Vyuha AI — State Management Demo
================================
Demonstrates persistent spacecraft state: /state, /act, /restore, /history.

Run (API must be running, e.g. uvicorn agent.src.main:app --port 8000):
    python scripts/demo_state_management.py

Or against a deployed Blaxel agent:
    BASE_URL=https://agt-vyuha-ai-xxxx.bl.run python scripts/demo_state_management.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    import requests
except ImportError:
    print("Install requests: pip install requests")
    sys.exit(1)

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
HEADERS = {"Content-Type": "application/json"}


def demo_state_management() -> None:
    print("Vyuha AI — State Management Demo")
    print("=" * 50)

    # 1. Initial state
    print("\n1. GET /state (initial)")
    r = requests.get(f"{BASE_URL}/state", headers=HEADERS, timeout=10)
    r.raise_for_status()
    state = r.json()
    print(f"   has_original_trajectory: {state.get('has_original_trajectory')}")
    print(f"   maneuver_count: {state.get('maneuver_count')}")

    # 2. Scan to get risk_data (optional; use minimal payload if scan fails)
    risk_data = {
        "status": "CRITICAL",
        "collision_probability": 0.95,
        "distance_to_debris_km": 0.5,
        "scenario_mode": "hybrid_demo",
    }
    try:
        scan_r = requests.post(
            f"{BASE_URL}/scan",
            json={"satellite_id": "ISS"},
            params={"simulate_danger": True},
            headers=HEADERS,
            timeout=15,
        )
        if scan_r.ok:
            risk_data = scan_r.json().get("risk_data", risk_data)
    except Exception as e:
        print(f"   (scan skipped: {e})")

    # 3. Execute maneuver
    print("\n2. POST /act (collision avoidance)")
    act_r = requests.post(
        f"{BASE_URL}/act",
        json={"risk_data": risk_data},
        headers=HEADERS,
        timeout=30,
    )
    act_r.raise_for_status()
    act_result = act_r.json()
    print(f"   status: {act_result.get('status')}")
    print(f"   state_saved: {act_result.get('state_saved', 'N/A')}")

    # 4. State after maneuver
    print("\n3. GET /state (after maneuver)")
    r = requests.get(f"{BASE_URL}/state", headers=HEADERS, timeout=10)
    r.raise_for_status()
    state = r.json()
    print(f"   has_original_trajectory: {state.get('has_original_trajectory')}")
    print(f"   maneuver_count: {state.get('maneuver_count')}")
    if state.get("current_state", {}).get("last_maneuver"):
        print(f"   last_maneuver.action: {state['current_state']['last_maneuver'].get('action')}")

    # 5. Restore original trajectory
    time.sleep(1)
    print("\n4. POST /restore (return to original trajectory)")
    restore_r = requests.post(f"{BASE_URL}/restore", headers=HEADERS, timeout=10)
    restore_r.raise_for_status()
    restore_result = restore_r.json()
    print(f"   status: {restore_result.get('status')}")
    print(f"   message: {restore_result.get('message')}")

    # 6. History
    print("\n5. GET /history")
    hist_r = requests.get(f"{BASE_URL}/history", headers=HEADERS, timeout=10)
    hist_r.raise_for_status()
    history = hist_r.json()
    print(f"   total_maneuvers: {history.get('total_maneuvers')}")
    print(f"   original_trajectory: {history.get('original_trajectory') is None} (cleared after restore)")

    print("\n" + "=" * 50)
    print("Demo complete.")


if __name__ == "__main__":
    try:
        demo_state_management()
    except requests.RequestException as e:
        print(f"Request failed: {e}")
        if hasattr(e, "response") and e.response is not None:
            print(f"Response: {e.response.status_code} — {e.response.text[:200]}")
        sys.exit(1)
