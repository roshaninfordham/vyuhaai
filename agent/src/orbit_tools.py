"""
Vyuha AI — Orbit Engine (Task 1)
================================
MCP tool-server that exposes orbital-mechanics utilities to the
autonomous space-safety agent.

Tools
-----
* check_conjunction_risk   – propagates a TLE, returns position + simulated
                             collision probability against a synthetic debris
                             catalogue.
* calculate_avoidance_maneuver – computes a prograde burn to dodge debris when
                                  the collision probability exceeds threshold.

Run standalone for local testing:
    python -m agent.src.orbit_tools
"""

from __future__ import annotations

import hashlib
import random
from datetime import datetime, timezone

import numpy as np
from mcp.server.fastmcp import FastMCP
from skyfield.api import EarthSatellite, load

# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------
mcp = FastMCP("vyuha-orbital-tools")

# Skyfield time-scale (loaded once, cached by skyfield internally)
ts = load.timescale()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _deterministic_seed(tle_line1: str, tle_line2: str, minute: int) -> int:
    """Return a seed derived from TLE content and the current UTC minute.

    This keeps the simulated values stable within the same minute for a given
    TLE pair (useful for demos) while still varying across satellites and
    across time.
    """
    payload = f"{tle_line1.strip()}|{tle_line2.strip()}|{minute}"
    return int(hashlib.sha256(payload.encode()).hexdigest()[:8], 16)


def _simulate_debris_encounter(seed: int) -> tuple[float, float]:
    """Return (collision_probability, distance_to_debris_km).

    Uses a seeded RNG so repeated calls within the same minute are
    deterministic — handy when the LLM retries or the UI polls.
    """
    rng = random.Random(seed)
    distance_km = rng.uniform(1.0, 50.0)
    # Closer debris → higher probability (inverse-square-ish relationship)
    raw_prob = 1.0 / (1.0 + (distance_km / 5.0) ** 2)
    # Add a small stochastic nudge so it isn't perfectly monotonic
    collision_probability = round(min(max(raw_prob + rng.gauss(0, 0.05), 0.0), 1.0), 4)
    return collision_probability, round(distance_km, 3)


# ---------------------------------------------------------------------------
# Tool 1 — Conjunction Risk Assessment
# ---------------------------------------------------------------------------

@mcp.tool()
def check_conjunction_risk(
    satellite_tle_line1: str,
    satellite_tle_line2: str,
) -> dict:
    """Propagate a satellite TLE to the current epoch and assess conjunction
    risk against a simulated debris catalogue.

    Parameters
    ----------
    satellite_tle_line1 : str
        First line of the two-line element set (TLE).
    satellite_tle_line2 : str
        Second line of the two-line element set (TLE).

    Returns
    -------
    dict
        Conjunction risk report including geocentric position, simulated
        collision probability, and an actionable status label.
    """
    # --- Propagate the orbit ---
    satellite = EarthSatellite(
        satellite_tle_line1.strip(),
        satellite_tle_line2.strip(),
        "TARGET",
        ts,
    )
    now = ts.now()
    geocentric = satellite.at(now)

    # Sub-satellite point (geodetic lat/lon/alt)
    subpoint = geocentric.subpoint()
    latitude = round(subpoint.latitude.degrees, 6)
    longitude = round(subpoint.longitude.degrees, 6)
    altitude_km = round(subpoint.elevation.km, 3)

    # --- Simulated debris encounter ---
    utc_now = datetime.now(timezone.utc)
    seed = _deterministic_seed(
        satellite_tle_line1, satellite_tle_line2, utc_now.minute,
    )
    collision_probability, distance_to_debris_km = _simulate_debris_encounter(seed)

    # --- Status classification ---
    if collision_probability > 0.7:
        status = "CRITICAL"
    elif collision_probability > 0.4:
        status = "WARNING"
    else:
        status = "SAFE"

    return {
        "timestamp": utc_now.isoformat(),
        "latitude": latitude,
        "longitude": longitude,
        "altitude_km": altitude_km,
        "distance_to_debris_km": distance_to_debris_km,
        "collision_probability": collision_probability,
        "status": status,
    }


# ---------------------------------------------------------------------------
# Tool 2 — Avoidance Maneuver Calculation
# ---------------------------------------------------------------------------

@mcp.tool()
def calculate_avoidance_maneuver(
    risk_probability: float,
    fuel_level: float,
) -> dict:
    """Compute an avoidance maneuver for a satellite under conjunction risk.

    Parameters
    ----------
    risk_probability : float
        Collision probability (0.0 – 1.0) as reported by
        ``check_conjunction_risk``.
    fuel_level : float
        Remaining fuel as a percentage (0.0 – 100.0).

    Returns
    -------
    dict
        Maneuver plan, or a status message if no burn is required / possible.
    """
    # --- Guard: risk below action threshold ---
    if risk_probability < 0.7:
        return {
            "action": "NO_ACTION",
            "reason": "Collision probability below threshold (< 0.7). No maneuver required.",
        }

    # --- Guard: insufficient fuel ---
    if fuel_level < 10.0:
        return {
            "action": "ALERT",
            "reason": (
                "WARNING: Fuel level critically low "
                f"({fuel_level:.1f}%). Unable to execute avoidance burn. "
                "Recommend ground-station contingency protocol."
            ),
        }

    # --- Compute burn parameters ---
    # Delta-v scales with risk; baseline ~0.5 m/s at p=0.7, up to ~2.5 m/s
    # at p=1.0.  Uses a quadratic ramp for a slightly conservative profile.
    normalised_risk = (risk_probability - 0.7) / 0.3          # 0 → 1
    delta_v_ms = round(0.5 + 2.0 * (normalised_risk ** 1.5), 4)

    # Burn duration assuming a small monopropellant thruster (~0.1 m/s² accel)
    thruster_accel = 0.1  # m/s²
    burn_duration_sec = round(delta_v_ms / thruster_accel, 2)

    # Fuel cost estimate (rough: 0.8 % per m/s of delta-v)
    fuel_cost_pct = round(delta_v_ms * 0.8, 2)

    return {
        "action": "FIRE_THRUSTERS",
        "direction": "PROGRADE",
        "delta_v_ms": delta_v_ms,
        "burn_duration_sec": burn_duration_sec,
        "estimated_fuel_cost_pct": fuel_cost_pct,
        "post_burn_fuel_pct": round(fuel_level - fuel_cost_pct, 2),
        "risk_probability_input": risk_probability,
    }


# ---------------------------------------------------------------------------
# Entry-point — local testing
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
