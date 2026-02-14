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
import logging
import random
from datetime import datetime, timezone

import numpy as np
import requests
from mcp.server.fastmcp import FastMCP
from skyfield.api import EarthSatellite, load

# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------
mcp = FastMCP("vyuha-orbital-tools")

# Skyfield time-scale (loaded once, cached by skyfield internally)
ts = load.timescale()

logger = logging.getLogger("vyuha.orbit")

# ---------------------------------------------------------------------------
# CelesTrak live TLE source
# ---------------------------------------------------------------------------
CELESTRAK_URL = (
    "https://celestrak.org/NORAD/elements/gp.php?GROUP=stations&FORMAT=tle"
)

# Hardcoded fallback TLE — used when CelesTrak is unreachable
_FALLBACK_TLE = (
    "1 25544U 98067A   24100.50000000  .00016717  00000-0  10270-3 0  9002",
    "2 25544  51.6400 208.9163 0002894 121.1600 239.0100 15.49999029999990",
)


def fetch_live_tle(
    satellite_name: str = "ISS (ZARYA)",
) -> tuple[str, str]:
    """Fetch the latest TLE for a satellite from CelesTrak.

    Parameters
    ----------
    satellite_name : str
        Exact name line as it appears in the CelesTrak TLE file.
        Defaults to ``"ISS (ZARYA)"``.

    Returns
    -------
    tuple[str, str]
        ``(tle_line1, tle_line2)`` stripped of whitespace.

    Raises
    ------
    ValueError
        If the satellite name is not found in the response.
    requests.RequestException
        On network / HTTP errors.
    """
    resp = requests.get(CELESTRAK_URL, timeout=15)
    resp.raise_for_status()

    lines = [line.strip() for line in resp.text.strip().splitlines() if line.strip()]

    # TLE format: name, line1, line2 — repeating in groups of 3
    for i, line in enumerate(lines):
        if line.upper() == satellite_name.upper():
            if i + 2 < len(lines):
                tle1 = lines[i + 1]
                tle2 = lines[i + 2]
                logger.info(
                    "Live TLE fetched for '%s' — epoch in line1: %s",
                    satellite_name,
                    tle1[18:32],
                )
                return tle1, tle2

    raise ValueError(
        f"Satellite '{satellite_name}' not found in CelesTrak response "
        f"({len(lines)} lines parsed)"
    )


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
    satellite_tle_line1: str = "",
    satellite_tle_line2: str = "",
    force_critical: bool = False,
) -> dict:
    """Propagate a satellite TLE to the current epoch and assess conjunction
    risk against a simulated debris catalogue.

    If TLE lines are omitted (empty strings), the function automatically
    fetches the latest ISS TLE from CelesTrak in real time.

    Parameters
    ----------
    satellite_tle_line1 : str, optional
        First line of the two-line element set (TLE).
    satellite_tle_line2 : str, optional
        Second line of the two-line element set (TLE).
    force_critical : bool, optional
        **Hybrid Demo Mode** — when ``True``, the real satellite position is
        kept but collision probability is overridden to 0.95 and distance to
        debris to 0.5 km, guaranteeing a CRITICAL status.  The response is
        tagged with ``scenario_mode="SYNTHETIC_DEBRIS_INJECTION"``.

    Returns
    -------
    dict
        Conjunction risk report including geocentric position, simulated
        collision probability, data source, and an actionable status label.
    """
    # --- Resolve TLE: live fetch → fallback --------------------------------
    data_source: str
    if not satellite_tle_line1.strip() or not satellite_tle_line2.strip():
        try:
            satellite_tle_line1, satellite_tle_line2 = fetch_live_tle()
            data_source = "CelesTrak (Live)"
        except Exception as exc:
            logger.warning("Live TLE fetch failed (%s) — using fallback", exc)
            satellite_tle_line1, satellite_tle_line2 = _FALLBACK_TLE
            data_source = "Hardcoded Fallback"
    else:
        data_source = "User-Provided"

    # --- Propagate the orbit -----------------------------------------------
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

    # --- Debris encounter --------------------------------------------------
    utc_now = datetime.now(timezone.utc)

    if force_critical:
        # Synthetic debris injection — position is REAL, threat is FORCED
        collision_probability = 0.95
        distance_to_debris_km = 0.5
        status = "CRITICAL"
        scenario_mode = "SYNTHETIC_DEBRIS_INJECTION"
        logger.info("Force-critical mode: injecting synthetic debris threat")
    else:
        seed = _deterministic_seed(
            satellite_tle_line1, satellite_tle_line2, utc_now.minute,
        )
        collision_probability, distance_to_debris_km = _simulate_debris_encounter(seed)
        scenario_mode = "LIVE_OBSERVATION"

        if collision_probability > 0.7:
            status = "CRITICAL"
        elif collision_probability > 0.4:
            status = "WARNING"
        else:
            status = "SAFE"

    result: dict = {
        "timestamp": utc_now.isoformat(),
        "latitude": latitude,
        "longitude": longitude,
        "altitude_km": altitude_km,
        "distance_to_debris_km": distance_to_debris_km,
        "collision_probability": collision_probability,
        "status": status,
        "scenario_mode": scenario_mode,
        "data_source": f"{data_source} (Live Fetch: {utc_now.strftime('%Y-%m-%d %H:%M:%S UTC')})",
    }

    return result


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
