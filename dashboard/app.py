"""
Vyuha AI — Mission Control Dashboard (Task 5)
===============================================
Streamlit-based command center that visualises satellite defence operations
in real time.  Connects to the FastAPI backend at localhost:8000.

Run:
    streamlit run dashboard/app.py
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import plotly.graph_objects as go
import requests
import streamlit as st

# ═══════════════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════════════

API_URL = "http://localhost:8000"

st.set_page_config(
    page_title="Vyuha AI // Orbital Defense",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ═══════════════════════════════════════════════════════════════════════════
# Custom CSS — dark sci-fi aesthetic
# ═══════════════════════════════════════════════════════════════════════════

st.markdown(
    """
    <style>
    /* ── Base ─────────────────────────────────────────────────────────── */
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Orbitron:wght@500;700;900&display=swap');

    .stApp {
        background-color: #0a0e14;
        color: #c5cdd9;
    }

    /* ── Header ──────────────────────────────────────────────────────── */
    .main-title {
        font-family: 'Orbitron', monospace;
        font-size: 2.2rem;
        font-weight: 900;
        letter-spacing: 0.25em;
        color: #00ff41;
        text-align: center;
        padding: 0.4rem 0 0.1rem 0;
        text-shadow: 0 0 20px rgba(0,255,65,0.4);
    }
    .sub-title {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.75rem;
        color: #3a5f3a;
        text-align: center;
        letter-spacing: 0.5em;
        padding-bottom: 0.8rem;
    }

    /* ── Section labels ──────────────────────────────────────────────── */
    .section-label {
        font-family: 'Orbitron', monospace;
        font-size: 0.7rem;
        font-weight: 700;
        letter-spacing: 0.3em;
        color: #00ff41;
        border-bottom: 1px solid #1a3a1a;
        padding-bottom: 4px;
        margin-bottom: 10px;
        text-shadow: 0 0 8px rgba(0,255,65,0.3);
    }

    /* ── Metric cards ────────────────────────────────────────────────── */
    .metric-card {
        background: linear-gradient(135deg, #0d1520 0%, #111b26 100%);
        border: 1px solid #1a3a1a;
        border-radius: 8px;
        padding: 14px 16px;
        margin-bottom: 8px;
    }
    .metric-label {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.65rem;
        color: #3a7a3a;
        letter-spacing: 0.15em;
        text-transform: uppercase;
    }
    .metric-value {
        font-family: 'Orbitron', monospace;
        font-size: 1.4rem;
        font-weight: 700;
        color: #00ff41;
        text-shadow: 0 0 12px rgba(0,255,65,0.3);
    }
    .metric-value.danger { color: #ff3333; text-shadow: 0 0 12px rgba(255,51,51,0.4); }
    .metric-value.warning { color: #ffaa00; text-shadow: 0 0 12px rgba(255,170,0,0.3); }
    .metric-value.safe { color: #00ff41; }

    /* ── Mission log ─────────────────────────────────────────────────── */
    .log-container {
        background: #070b10;
        border: 1px solid #1a2a1a;
        border-radius: 6px;
        padding: 12px;
        max-height: 520px;
        overflow-y: auto;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.72rem;
        line-height: 1.7;
    }
    .log-entry { padding: 2px 0; border-bottom: 1px solid #0d140d; }
    .log-ts { color: #2a4a2a; }
    .log-info { color: #4a8a4a; }
    .log-warn { color: #ffaa00; }
    .log-error { color: #ff3333; }
    .log-success { color: #00ff41; font-weight: 700; }

    /* ── Status bar ──────────────────────────────────────────────────── */
    .status-bar {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.65rem;
        color: #2a4a2a;
        text-align: center;
        padding: 6px 0;
        border-top: 1px solid #1a2a1a;
        letter-spacing: 0.1em;
    }

    /* ── Result banners ──────────────────────────────────────────────── */
    .result-banner {
        border-radius: 8px;
        padding: 18px 22px;
        margin: 12px 0;
        font-family: 'Orbitron', monospace;
        text-align: center;
    }
    .result-banner.success {
        background: linear-gradient(135deg, #0a2a0a 0%, #0d3d0d 100%);
        border: 2px solid #00ff41;
        color: #00ff41;
        box-shadow: 0 0 30px rgba(0,255,65,0.15);
    }
    .result-banner.failure {
        background: linear-gradient(135deg, #2a0a0a 0%, #3d0d0d 100%);
        border: 2px solid #ff3333;
        color: #ff3333;
        box-shadow: 0 0 30px rgba(255,51,51,0.15);
    }

    /* ── Button overrides ────────────────────────────────────────────── */
    .stButton > button {
        font-family: 'Orbitron', monospace !important;
        font-weight: 700 !important;
        letter-spacing: 0.15em !important;
        background: linear-gradient(135deg, #0a2a0a 0%, #0d3d0d 100%) !important;
        border: 2px solid #00ff41 !important;
        color: #00ff41 !important;
        border-radius: 6px !important;
        padding: 0.6rem 1.5rem !important;
        transition: all 0.3s ease !important;
        width: 100% !important;
    }
    .stButton > button:hover {
        background: #00ff41 !important;
        color: #0a0e14 !important;
        box-shadow: 0 0 25px rgba(0,255,65,0.4) !important;
    }

    /* ── Hide Streamlit defaults ─────────────────────────────────────── */
    #MainMenu, footer, header { visibility: hidden; }
    .block-container { padding-top: 1.5rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ═══════════════════════════════════════════════════════════════════════════
# Session state initialisation
# ═══════════════════════════════════════════════════════════════════════════

if "mission_log" not in st.session_state:
    st.session_state.mission_log = []
if "last_scan" not in st.session_state:
    st.session_state.last_scan = None
if "scan_count" not in st.session_state:
    st.session_state.scan_count = 0


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _ts() -> str:
    """Return a compact UTC timestamp for log entries."""
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


def add_log(msg: str, level: str = "info") -> None:
    """Append an entry to the mission log in session state."""
    st.session_state.mission_log.append(
        {"ts": _ts(), "msg": msg, "level": level}
    )


def render_log() -> None:
    """Render the full mission log as a styled HTML block."""
    level_class = {
        "info": "log-info",
        "warn": "log-warn",
        "error": "log-error",
        "success": "log-success",
    }
    entries_html = ""
    for entry in reversed(st.session_state.mission_log[-80:]):
        cls = level_class.get(entry["level"], "log-info")
        entries_html += (
            f'<div class="log-entry">'
            f'<span class="log-ts">[{entry["ts"]}]</span> '
            f'<span class="{cls}">{entry["msg"]}</span>'
            f"</div>"
        )
    st.markdown(
        f'<div class="log-container">{entries_html}</div>',
        unsafe_allow_html=True,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 3D Globe — "The Watchtower"
# ═══════════════════════════════════════════════════════════════════════════

def render_globe(
    lat: float,
    lon: float,
    is_risk: bool,
    altitude_km: float = 400.0,
    debris_dist_km: float | None = None,
) -> go.Figure:
    """Return a Plotly orthographic globe with satellite + optional debris."""

    # -- Satellite marker ---------------------------------------------------
    sat_trace = go.Scattergeo(
        lat=[lat],
        lon=[lon],
        mode="markers+text",
        marker=dict(
            size=14,
            color="#00ff41",
            symbol="diamond",
            line=dict(width=1, color="#00ff41"),
        ),
        text=["ISS"],
        textposition="top center",
        textfont=dict(color="#00ff41", size=11, family="JetBrains Mono"),
        name="Satellite",
        hovertemplate=(
            f"<b>ISS</b><br>"
            f"Lat: {lat:.2f}°<br>"
            f"Lon: {lon:.2f}°<br>"
            f"Alt: {altitude_km:.1f} km"
            "<extra></extra>"
        ),
    )

    traces = [sat_trace]

    # -- Debris marker (if risk) --------------------------------------------
    if is_risk:
        # Offset debris slightly from satellite position
        debris_lat = lat + 1.8
        debris_lon = lon + 2.5
        traces.append(
            go.Scattergeo(
                lat=[debris_lat],
                lon=[debris_lon],
                mode="markers+text",
                marker=dict(
                    size=12,
                    color="#ff3333",
                    symbol="x",
                    line=dict(width=1, color="#ff3333"),
                ),
                text=["DEBRIS"],
                textposition="bottom center",
                textfont=dict(color="#ff3333", size=10, family="JetBrains Mono"),
                name="Debris",
                hovertemplate=(
                    f"<b>Debris Object</b><br>"
                    f"Distance: {debris_dist_km:.1f} km"
                    "<extra></extra>"
                ),
            )
        )

        # Threat radius ring
        import numpy as np

        ring_angles = np.linspace(0, 2 * np.pi, 60)
        ring_radius = 3.0  # degrees
        ring_lats = lat + ring_radius * np.cos(ring_angles)
        ring_lons = lon + ring_radius * np.sin(ring_angles)
        traces.append(
            go.Scattergeo(
                lat=ring_lats.tolist(),
                lon=ring_lons.tolist(),
                mode="lines",
                line=dict(color="rgba(255,51,51,0.35)", width=1.5, dash="dot"),
                name="Threat Radius",
                showlegend=False,
                hoverinfo="skip",
            )
        )

    # -- Orbit track (simple great-circle hint) -----------------------------
    import numpy as np

    orbit_lons = np.linspace(lon - 60, lon + 60, 120)
    orbit_lats = lat + 8 * np.sin(np.radians(orbit_lons - lon) * 2)
    traces.append(
        go.Scattergeo(
            lat=orbit_lats.tolist(),
            lon=orbit_lons.tolist(),
            mode="lines",
            line=dict(color="rgba(0,255,65,0.12)", width=1),
            name="Orbit Track",
            showlegend=False,
            hoverinfo="skip",
        )
    )

    # -- Globe layout -------------------------------------------------------
    fig = go.Figure(data=traces)
    fig.update_geos(
        projection_type="orthographic",
        projection_rotation=dict(lon=lon, lat=lat * 0.6),
        showland=True,
        landcolor="#0d1a0d",
        showocean=True,
        oceancolor="#060c10",
        showlakes=False,
        showcountries=True,
        countrycolor="#1a3a1a",
        coastlinecolor="#1a3a1a",
        showframe=False,
        bgcolor="rgba(0,0,0,0)",
    )
    fig.update_layout(
        height=500,
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(
            font=dict(family="JetBrains Mono", size=10, color="#4a8a4a"),
            bgcolor="rgba(0,0,0,0)",
            x=0.01,
            y=0.99,
        ),
        hoverlabel=dict(
            bgcolor="#111b26",
            font=dict(family="JetBrains Mono", size=11, color="#00ff41"),
        ),
    )
    return fig


# ═══════════════════════════════════════════════════════════════════════════
# Metric card helper
# ═══════════════════════════════════════════════════════════════════════════

def metric_card(label: str, value: str, style: str = "") -> None:
    """Render a single metric card."""
    st.markdown(
        f'<div class="metric-card">'
        f'<div class="metric-label">{label}</div>'
        f'<div class="metric-value {style}">{value}</div>'
        f"</div>",
        unsafe_allow_html=True,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Header
# ═══════════════════════════════════════════════════════════════════════════

st.markdown(
    '<div class="main-title">VYUHA AI // ORBITAL DEFENSE SYSTEM</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="sub-title">AUTONOMOUS SATELLITE COLLISION AVOIDANCE</div>',
    unsafe_allow_html=True,
)

# ═══════════════════════════════════════════════════════════════════════════
# Layout — two columns
# ═══════════════════════════════════════════════════════════════════════════

col_main, col_log = st.columns([2, 1], gap="large")

# ───────────────────────────────────────────────────────────────────────────
# LEFT COLUMN — Globe + Controls + Results
# ───────────────────────────────────────────────────────────────────────────

with col_main:
    st.markdown('<div class="section-label">WATCHTOWER // ORBITAL VIEW</div>',
                unsafe_allow_html=True)

    # -- Globe placeholder (shows last known position or default) -----------
    globe_slot = st.empty()

    scan = st.session_state.last_scan
    if scan:
        rd = scan["risk_data"]
        globe_slot.plotly_chart(
            render_globe(
                rd["latitude"],
                rd["longitude"],
                rd["status"] in ("CRITICAL", "WARNING"),
                rd.get("altitude_km", 400),
                rd.get("distance_to_debris_km"),
            ),
            use_container_width=True,
            key="globe_idle",
        )
    else:
        globe_slot.plotly_chart(
            render_globe(0, 0, False), use_container_width=True, key="globe_default",
        )

    # -- Telemetry metrics row ----------------------------------------------
    st.markdown('<div class="section-label">TELEMETRY</div>',
                unsafe_allow_html=True)

    m1, m2, m3, m4 = st.columns(4)
    if scan:
        rd = scan["risk_data"]
        prob = rd["collision_probability"]
        prob_style = "danger" if prob > 0.7 else ("warning" if prob > 0.4 else "safe")

        with m1:
            metric_card("ALTITUDE", f'{rd["altitude_km"]:.1f} km')
        with m2:
            metric_card("LATITUDE", f'{rd["latitude"]:.4f}°')
        with m3:
            metric_card("LONGITUDE", f'{rd["longitude"]:.4f}°')
        with m4:
            metric_card("COLLISION PROB", f'{prob:.4f}', prob_style)
    else:
        with m1:
            metric_card("ALTITUDE", "—")
        with m2:
            metric_card("LATITUDE", "—")
        with m3:
            metric_card("LONGITUDE", "—")
        with m4:
            metric_card("COLLISION PROB", "—")

    # -- Scan button --------------------------------------------------------
    st.markdown("")  # spacer
    scan_clicked = st.button("📡  SCAN SECTOR  //  SIMULATE TELEMETRY", key="scan_btn")

    # -- Result area --------------------------------------------------------
    result_slot = st.empty()


# ───────────────────────────────────────────────────────────────────────────
# RIGHT COLUMN — Mission Log
# ───────────────────────────────────────────────────────────────────────────

with col_log:
    st.markdown('<div class="section-label">MISSION LOG // LIVE FEED</div>',
                unsafe_allow_html=True)
    log_slot = st.empty()

    with log_slot.container():
        render_log()

    # -- System info at the bottom ------------------------------------------
    st.markdown(
        f'<div class="status-bar">'
        f"SCANS: {st.session_state.scan_count}  ·  "
        f"LOG ENTRIES: {len(st.session_state.mission_log)}  ·  "
        f'BACKEND: {API_URL}'
        f"</div>",
        unsafe_allow_html=True,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Scan + Act logic (runs when button clicked)
# ═══════════════════════════════════════════════════════════════════════════

if scan_clicked:
    # ── Step 1: Scan ──────────────────────────────────────────────────
    add_log("Initiating orbital scan...", "info")

    try:
        resp = requests.post(
            f"{API_URL}/scan",
            json={"satellite_id": "ISS"},
            timeout=10,
        )
        resp.raise_for_status()
        scan_data = resp.json()
    except Exception as exc:
        add_log(f"SCAN FAILED: {exc}", "error")
        with log_slot.container():
            render_log()
        st.stop()

    st.session_state.last_scan = scan_data
    st.session_state.scan_count += 1
    rd = scan_data["risk_data"]

    add_log(
        f"Telemetry acquired — "
        f"Alt: {rd['altitude_km']:.1f} km | "
        f"Prob: {rd['collision_probability']:.4f} | "
        f"Status: {rd['status']}",
        "info",
    )

    # Update globe
    is_risk = rd["status"] in ("CRITICAL", "WARNING")
    globe_slot.plotly_chart(
        render_globe(
            rd["latitude"],
            rd["longitude"],
            is_risk,
            rd.get("altitude_km", 400),
            rd.get("distance_to_debris_km"),
        ),
        use_container_width=True,
        key=f"globe_{st.session_state.scan_count}",
    )

    # ── Step 2: Evaluate threat ───────────────────────────────────────
    if rd["status"] == "CRITICAL":
        add_log("⚠️  COLLISION PROBABILITY EXCEEDS THRESHOLD", "error")
        add_log("Engaging Vyuha Commander AI...", "warn")

        with log_slot.container():
            render_log()

        with st.spinner("⚠️  COLLISION DETECTED — ENGAGING VYUHA AGENT..."):
            try:
                act_resp = requests.post(
                    f"{API_URL}/act",
                    json={
                        "risk_data": rd,
                        "session_id": f"dash-{st.session_state.scan_count:04d}",
                    },
                    timeout=60,
                )
                act_resp.raise_for_status()
                act_data = act_resp.json()
            except Exception as exc:
                add_log(f"AGENT COMMS FAILED: {exc}", "error")
                with log_slot.container():
                    render_log()
                st.stop()

        # ── Log the attempt history ───────────────────────────────────
        for entry in act_data.get("attempts_log", []):
            attempt_n = entry["attempt"]
            cmd = entry["command"]
            val = entry["validation"]

            if val["valid"]:
                add_log(
                    f"🟢 ATTEMPT {attempt_n}: [{cmd.get('action', '?')}] — "
                    f"Approved (source: {val['source']})",
                    "success",
                )
            else:
                tags = ", ".join(val.get("violation_tags", []))
                add_log(
                    f"🔴 ATTEMPT {attempt_n}: [{cmd.get('action', '?')}] — "
                    f"BLOCKED — Policy Violation [{tags}]",
                    "error",
                )
                add_log(
                    f"   ↳ Commander self-correcting (feedback loop)...",
                    "warn",
                )

        # ── Display result banner ─────────────────────────────────────
        if act_data.get("status") == "EXECUTED":
            fc = act_data["final_command"]
            add_log(
                f"✅ MANEUVER CONFIRMED — {fc['action']} "
                f"({fc['recommended_thrust_direction']}) "
                f"confidence={fc.get('confidence_score', 0):.2f}",
                "success",
            )
            result_slot.markdown(
                f"""
                <div class="result-banner success">
                    <div style="font-size:1.6rem;font-weight:900;margin-bottom:8px;">
                        ✅ MANEUVER CONFIRMED
                    </div>
                    <div style="font-size:0.85rem;font-family:'JetBrains Mono';opacity:0.85;">
                        Action: <b>{fc['action']}</b> &nbsp;·&nbsp;
                        Direction: <b>{fc['recommended_thrust_direction']}</b> &nbsp;·&nbsp;
                        Confidence: <b>{fc.get('confidence_score', 0):.0%}</b>
                    </div>
                    <div style="font-size:0.7rem;font-family:'JetBrains Mono';opacity:0.6;margin-top:8px;">
                        {fc.get('reasoning', '')}
                    </div>
                    <div style="font-size:0.65rem;margin-top:6px;opacity:0.4;">
                        Attempts: {act_data['attempts']} &nbsp;·&nbsp;
                        Session: {act_data['session_id']}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            reason = act_data.get("reason", "Unknown failure")
            add_log(f"🚨 AGENT FAILED — {reason}", "error")
            result_slot.markdown(
                f"""
                <div class="result-banner failure">
                    <div style="font-size:1.6rem;font-weight:900;margin-bottom:8px;">
                        🚨 AGENT FAILED — SECURITY LOCKOUT
                    </div>
                    <div style="font-size:0.85rem;font-family:'JetBrains Mono';opacity:0.85;">
                        MANUAL OVERRIDE REQUIRED
                    </div>
                    <div style="font-size:0.7rem;font-family:'JetBrains Mono';opacity:0.6;margin-top:8px;">
                        {reason}
                    </div>
                    <div style="font-size:0.65rem;margin-top:6px;opacity:0.4;">
                        Attempts: {act_data.get('attempts', '?')} &nbsp;·&nbsp;
                        Session: {act_data.get('session_id', '?')}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    elif rd["status"] == "WARNING":
        add_log("⚠️  Elevated risk — monitoring. No action required.", "warn")

    else:
        add_log("✅ Sector clear — no threats detected.", "success")

    # ── Refresh the log ───────────────────────────────────────────────
    with log_slot.container():
        render_log()
