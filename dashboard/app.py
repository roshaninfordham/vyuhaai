"""
Vyuha AI — Mission Control Dashboard (Task 5 / Hybrid Demo)
=============================================================
Streamlit command center with real-time ISS tracking from CelesTrak
and a "Simulate Attack" button that forces a collision scenario to
demo the autonomous agent loop.

Run:
    streamlit run dashboard/app.py
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np
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
# Custom CSS
# ═══════════════════════════════════════════════════════════════════════════

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Orbitron:wght@500;700;900&display=swap');

    .stApp { background-color: #0a0e14; color: #c5cdd9; }

    /* ── Header ──────────────────────────────────────────────────────── */
    .main-title {
        font-family: 'Orbitron', monospace; font-size: 2.2rem; font-weight: 900;
        letter-spacing: 0.25em; color: #00ff41; text-align: center;
        padding: 0.4rem 0 0.1rem 0; text-shadow: 0 0 20px rgba(0,255,65,0.4);
    }
    .sub-title {
        font-family: 'JetBrains Mono', monospace; font-size: 0.75rem;
        color: #3a5f3a; text-align: center; letter-spacing: 0.5em;
        padding-bottom: 0.6rem;
    }

    /* ── Badges ──────────────────────────────────────────────────────── */
    .badge {
        display: inline-block; font-family: 'JetBrains Mono', monospace;
        font-size: 0.65rem; font-weight: 700; letter-spacing: 0.1em;
        padding: 3px 10px; border-radius: 4px; margin: 2px 4px;
    }
    .badge-live { background: #0a2a0a; border: 1px solid #00ff41; color: #00ff41; }
    .badge-sim  { background: #2a1a0a; border: 1px solid #ffaa00; color: #ffaa00; }
    .badge-danger { background: #2a0a0a; border: 1px solid #ff3333; color: #ff3333; }

    /* ── Section labels ──────────────────────────────────────────────── */
    .section-label {
        font-family: 'Orbitron', monospace; font-size: 0.7rem; font-weight: 700;
        letter-spacing: 0.3em; color: #00ff41;
        border-bottom: 1px solid #1a3a1a; padding-bottom: 4px; margin-bottom: 10px;
        text-shadow: 0 0 8px rgba(0,255,65,0.3);
    }

    /* ── Metric cards ────────────────────────────────────────────────── */
    .metric-card {
        background: linear-gradient(135deg, #0d1520 0%, #111b26 100%);
        border: 1px solid #1a3a1a; border-radius: 8px;
        padding: 14px 16px; margin-bottom: 8px;
    }
    .metric-label {
        font-family: 'JetBrains Mono', monospace; font-size: 0.6rem;
        color: #3a7a3a; letter-spacing: 0.15em; text-transform: uppercase;
    }
    .metric-value {
        font-family: 'Orbitron', monospace; font-size: 1.35rem; font-weight: 700;
        color: #00ff41; text-shadow: 0 0 12px rgba(0,255,65,0.3);
    }
    .metric-value.danger  { color: #ff3333; text-shadow: 0 0 12px rgba(255,51,51,0.4); }
    .metric-value.warning { color: #ffaa00; text-shadow: 0 0 12px rgba(255,170,0,0.3); }
    .metric-value.safe    { color: #00ff41; }

    /* ── Mission log ─────────────────────────────────────────────────── */
    .log-container {
        background: #070b10; border: 1px solid #1a2a1a; border-radius: 6px;
        padding: 12px; max-height: 560px; overflow-y: auto;
        font-family: 'JetBrains Mono', monospace; font-size: 0.72rem; line-height: 1.7;
    }
    .log-entry  { padding: 2px 0; border-bottom: 1px solid #0d140d; }
    .log-ts     { color: #2a4a2a; }
    .log-info   { color: #4a8a4a; }
    .log-warn   { color: #ffaa00; }
    .log-error  { color: #ff3333; }
    .log-success{ color: #00ff41; font-weight: 700; }

    /* ── Result banners ──────────────────────────────────────────────── */
    .result-banner {
        border-radius: 8px; padding: 18px 22px; margin: 12px 0;
        font-family: 'Orbitron', monospace; text-align: center;
    }
    .result-banner.success {
        background: linear-gradient(135deg, #0a2a0a 0%, #0d3d0d 100%);
        border: 2px solid #00ff41; color: #00ff41;
        box-shadow: 0 0 30px rgba(0,255,65,0.15);
    }
    .result-banner.failure {
        background: linear-gradient(135deg, #2a0a0a 0%, #3d0d0d 100%);
        border: 2px solid #ff3333; color: #ff3333;
        box-shadow: 0 0 30px rgba(255,51,51,0.15);
    }

    /* ── Buttons ─────────────────────────────────────────────────────── */
    .stButton > button {
        font-family: 'Orbitron', monospace !important; font-weight: 700 !important;
        letter-spacing: 0.12em !important; border-radius: 6px !important;
        padding: 0.55rem 1.2rem !important; transition: all 0.3s ease !important;
        width: 100% !important;
    }
    /* green scan button (default) */
    .stButton > button {
        background: linear-gradient(135deg, #0a2a0a 0%, #0d3d0d 100%) !important;
        border: 2px solid #00ff41 !important; color: #00ff41 !important;
    }
    .stButton > button:hover {
        background: #00ff41 !important; color: #0a0e14 !important;
        box-shadow: 0 0 25px rgba(0,255,65,0.4) !important;
    }

    /* ── Chain-of-thought expander ────────────────────────────────────── */
    .cot-blocked {
        background: #1a0808; border-left: 3px solid #ff3333;
        padding: 8px 12px; margin: 6px 0; border-radius: 0 4px 4px 0;
        font-family: 'JetBrains Mono', monospace; font-size: 0.75rem; color: #ff6666;
    }
    .cot-approved {
        background: #081a08; border-left: 3px solid #00ff41;
        padding: 8px 12px; margin: 6px 0; border-radius: 0 4px 4px 0;
        font-family: 'JetBrains Mono', monospace; font-size: 0.75rem; color: #00ff41;
    }
    .cot-retry {
        background: #1a1508; border-left: 3px solid #ffaa00;
        padding: 8px 12px; margin: 6px 0; border-radius: 0 4px 4px 0;
        font-family: 'JetBrains Mono', monospace; font-size: 0.75rem; color: #ffaa00;
    }

    /* ── Data source footer ──────────────────────────────────────────── */
    .data-source-bar {
        font-family: 'JetBrains Mono', monospace; font-size: 0.62rem;
        color: #2a4a2a; text-align: center; padding: 8px 0;
        border-top: 1px solid #1a2a1a; letter-spacing: 0.08em; margin-top: 12px;
    }

    /* ── Hide defaults ───────────────────────────────────────────────── */
    #MainMenu, footer, header { visibility: hidden; }
    .block-container { padding-top: 1.5rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ═══════════════════════════════════════════════════════════════════════════
# Session state
# ═══════════════════════════════════════════════════════════════════════════

if "mission_log" not in st.session_state:
    st.session_state.mission_log = []
if "last_scan" not in st.session_state:
    st.session_state.last_scan = None
if "scan_count" not in st.session_state:
    st.session_state.scan_count = 0
if "last_act" not in st.session_state:
    st.session_state.last_act = None


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")

def add_log(msg: str, level: str = "info") -> None:
    st.session_state.mission_log.append({"ts": _ts(), "msg": msg, "level": level})

def render_log() -> None:
    level_class = {"info": "log-info", "warn": "log-warn",
                   "error": "log-error", "success": "log-success"}
    html = ""
    for e in reversed(st.session_state.mission_log[-100:]):
        cls = level_class.get(e["level"], "log-info")
        html += (f'<div class="log-entry"><span class="log-ts">[{e["ts"]}]</span> '
                 f'<span class="{cls}">{e["msg"]}</span></div>')
    st.markdown(f'<div class="log-container">{html}</div>', unsafe_allow_html=True)

def metric_card(label: str, value: str, style: str = "") -> None:
    st.markdown(
        f'<div class="metric-card">'
        f'<div class="metric-label">{label}</div>'
        f'<div class="metric-value {style}">{value}</div></div>',
        unsafe_allow_html=True,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 3D Globe
# ═══════════════════════════════════════════════════════════════════════════

def render_globe(lat: float, lon: float, is_critical: bool,
                 altitude_km: float = 400.0,
                 debris_dist_km: float | None = None) -> go.Figure:

    # Satellite
    traces = [go.Scattergeo(
        lat=[lat], lon=[lon], mode="markers+text",
        marker=dict(size=14, color="#00ff41", symbol="diamond",
                    line=dict(width=1, color="#00ff41")),
        text=["ISS"], textposition="top center",
        textfont=dict(color="#00ff41", size=11, family="JetBrains Mono"),
        name="ISS (ZARYA)",
        hovertemplate=(f"<b>ISS (ZARYA)</b><br>Lat: {lat:.2f}°<br>"
                       f"Lon: {lon:.2f}°<br>Alt: {altitude_km:.1f} km<extra></extra>"),
    )]

    if is_critical:
        # Debris — 1° offset
        dlat, dlon = lat + 0.7, lon + 0.9
        dist_label = f"{debris_dist_km:.1f}" if debris_dist_km else "?"
        traces.append(go.Scattergeo(
            lat=[dlat], lon=[dlon], mode="markers+text",
            marker=dict(size=13, color="#ff3333", symbol="x",
                        line=dict(width=2, color="#ff3333")),
            text=["DEBRIS"], textposition="bottom center",
            textfont=dict(color="#ff3333", size=10, family="JetBrains Mono"),
            name="Debris Object",
            hovertemplate=f"<b>Debris</b><br>Distance: {dist_label} km<extra></extra>",
        ))

        # Threat ring
        angles = np.linspace(0, 2 * np.pi, 60)
        r = 2.0
        traces.append(go.Scattergeo(
            lat=(lat + r * np.cos(angles)).tolist(),
            lon=(lon + r * np.sin(angles)).tolist(),
            mode="lines",
            line=dict(color="rgba(255,51,51,0.4)", width=1.5, dash="dot"),
            showlegend=False, hoverinfo="skip", name="Threat Zone",
        ))

        # Collision vector line
        traces.append(go.Scattergeo(
            lat=[lat, dlat], lon=[lon, dlon], mode="lines",
            line=dict(color="#ff3333", width=2, dash="dash"),
            showlegend=False, hoverinfo="skip",
        ))

    # Orbit arc
    arc_lons = np.linspace(lon - 60, lon + 60, 120)
    arc_lats = lat + 8 * np.sin(np.radians(arc_lons - lon) * 2)
    traces.append(go.Scattergeo(
        lat=arc_lats.tolist(), lon=arc_lons.tolist(), mode="lines",
        line=dict(color="rgba(0,255,65,0.12)", width=1),
        showlegend=False, hoverinfo="skip",
    ))

    fig = go.Figure(data=traces)
    fig.update_geos(
        projection_type="orthographic",
        projection_rotation=dict(lon=lon, lat=lat * 0.6),
        showland=True, landcolor="#0d1a0d",
        showocean=True, oceancolor="#060c10",
        showlakes=False, showcountries=True,
        countrycolor="#1a3a1a", coastlinecolor="#1a3a1a",
        showframe=False, bgcolor="rgba(0,0,0,0)",
    )
    fig.update_layout(
        height=480, margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(font=dict(family="JetBrains Mono", size=10, color="#4a8a4a"),
                    bgcolor="rgba(0,0,0,0)", x=0.01, y=0.99),
        hoverlabel=dict(bgcolor="#111b26",
                        font=dict(family="JetBrains Mono", size=11, color="#00ff41")),
    )
    return fig


# ═══════════════════════════════════════════════════════════════════════════
# API helpers
# ═══════════════════════════════════════════════════════════════════════════

def api_scan(simulate: bool) -> dict | None:
    try:
        r = requests.post(f"{API_URL}/scan?simulate_danger={str(simulate).lower()}",
                          json={"satellite_id": "ISS"}, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        add_log(f"SCAN FAILED: {exc}", "error")
        return None

def api_act(risk_data: dict, session_id: str) -> dict | None:
    try:
        r = requests.post(f"{API_URL}/act",
                          json={"risk_data": risk_data, "session_id": session_id},
                          timeout=60)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        add_log(f"AGENT COMMS FAILED: {exc}", "error")
        return None


# ═══════════════════════════════════════════════════════════════════════════
# Header
# ═══════════════════════════════════════════════════════════════════════════

st.markdown('<div class="main-title">VYUHA AI // ORBITAL DEFENSE SYSTEM</div>',
            unsafe_allow_html=True)
st.markdown('<div class="sub-title">AUTONOMOUS SATELLITE COLLISION AVOIDANCE  ·  HYBRID DEMO MODE</div>',
            unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════
# Live-data badge row
# ═══════════════════════════════════════════════════════════════════════════

scan = st.session_state.last_scan
rd = scan["risk_data"] if scan else None

badge_html = '<div style="text-align:center;margin-bottom:8px;">'
if rd:
    src = rd.get("data_source", "")
    mode = rd.get("scenario_mode", "")
    if "CelesTrak" in src:
        badge_html += '<span class="badge badge-live">● CELESTRAK LIVE FEED</span>'
    else:
        badge_html += '<span class="badge badge-sim">● FALLBACK DATA</span>'
    if mode == "SYNTHETIC_DEBRIS_INJECTION":
        badge_html += '<span class="badge badge-danger">⚠ SYNTHETIC DEBRIS ACTIVE</span>'
    elif rd["status"] == "SAFE":
        badge_html += '<span class="badge badge-live">● SECTOR CLEAR</span>'
    elif rd["status"] == "CRITICAL":
        badge_html += '<span class="badge badge-danger">● COLLISION ALERT</span>'
else:
    badge_html += '<span class="badge badge-sim">● AWAITING FIRST SCAN</span>'
badge_html += '</div>'
st.markdown(badge_html, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════
# Layout
# ═══════════════════════════════════════════════════════════════════════════

col_main, col_log = st.columns([2, 1], gap="large")

# ───────────────────────────────────────────────────────────────────────────
# LEFT COLUMN
# ───────────────────────────────────────────────────────────────────────────
with col_main:
    st.markdown('<div class="section-label">WATCHTOWER // ORBITAL VIEW</div>',
                unsafe_allow_html=True)

    globe_slot = st.empty()
    if rd:
        globe_slot.plotly_chart(
            render_globe(rd["latitude"], rd["longitude"],
                         rd["status"] == "CRITICAL",
                         rd.get("altitude_km", 400),
                         rd.get("distance_to_debris_km")),
            use_container_width=True, key="globe_idle",
        )
    else:
        globe_slot.plotly_chart(
            render_globe(0, 0, False), use_container_width=True, key="globe_default",
        )

    # ── Telemetry metrics ─────────────────────────────────────────────
    st.markdown('<div class="section-label">TELEMETRY</div>', unsafe_allow_html=True)
    m1, m2, m3, m4, m5 = st.columns(5)
    if rd:
        prob = rd["collision_probability"]
        ps = "danger" if prob > 0.7 else ("warning" if prob > 0.4 else "safe")
        status_style = "danger" if rd["status"] == "CRITICAL" else (
            "warning" if rd["status"] == "WARNING" else "safe")
        with m1: metric_card("ALTITUDE", f'{rd["altitude_km"]:.1f} km')
        with m2: metric_card("LATITUDE", f'{rd["latitude"]:.4f}°')
        with m3: metric_card("LONGITUDE", f'{rd["longitude"]:.4f}°')
        with m4: metric_card("COLLISION PROB", f'{prob:.4f}', ps)
        with m5: metric_card("STATUS", rd["status"], status_style)
    else:
        with m1: metric_card("ALTITUDE", "—")
        with m2: metric_card("LATITUDE", "—")
        with m3: metric_card("LONGITUDE", "—")
        with m4: metric_card("COLLISION PROB", "—")
        with m5: metric_card("STATUS", "IDLE")

    # ── Control buttons ───────────────────────────────────────────────
    st.markdown('<div class="section-label">COMMAND INTERFACE</div>',
                unsafe_allow_html=True)
    btn_col1, btn_col2 = st.columns(2)
    with btn_col1:
        live_clicked = st.button("📡  SCAN SECTOR  (LIVE)", key="btn_live")
    with btn_col2:
        sim_clicked = st.button("⚠️  SIMULATE ATTACK  (DEMO)", key="btn_sim")

    # ── Result / Chain-of-thought area ────────────────────────────────
    result_slot = st.empty()
    cot_slot = st.container()

# ───────────────────────────────────────────────────────────────────────────
# RIGHT COLUMN — Mission Log
# ───────────────────────────────────────────────────────────────────────────
with col_log:
    st.markdown('<div class="section-label">MISSION LOG // LIVE FEED</div>',
                unsafe_allow_html=True)
    log_slot = st.empty()
    with log_slot.container():
        render_log()

    st.markdown(
        f'<div class="data-source-bar">'
        f"SCANS: {st.session_state.scan_count}  ·  "
        f"LOG ENTRIES: {len(st.session_state.mission_log)}  ·  "
        f"BACKEND: {API_URL}</div>",
        unsafe_allow_html=True,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Scan + Act logic
# ═══════════════════════════════════════════════════════════════════════════

triggered = live_clicked or sim_clicked
simulate = sim_clicked

if triggered:
    mode_label = "SIMULATE ATTACK" if simulate else "LIVE SCAN"
    add_log(f"Initiating {mode_label}...", "info")

    # ── Step 1: Scan ──────────────────────────────────────────────────
    scan_data = api_scan(simulate)
    if not scan_data:
        with log_slot.container():
            render_log()
        st.stop()

    st.session_state.last_scan = scan_data
    st.session_state.scan_count += 1
    rd = scan_data["risk_data"]

    scenario = rd.get("scenario_mode", "LIVE_OBSERVATION")
    add_log(
        f"Telemetry — Alt: {rd['altitude_km']:.1f} km | "
        f"Prob: {rd['collision_probability']:.4f} | "
        f"Status: {rd['status']} | Mode: {scenario}",
        "info",
    )

    # Update globe
    globe_slot.plotly_chart(
        render_globe(rd["latitude"], rd["longitude"],
                     rd["status"] == "CRITICAL",
                     rd.get("altitude_km", 400),
                     rd.get("distance_to_debris_km")),
        use_container_width=True,
        key=f"globe_{st.session_state.scan_count}",
    )

    # ── Step 2: Agent loop (if CRITICAL) ──────────────────────────────
    if rd["status"] == "CRITICAL":
        add_log("🚨 COLLISION PROBABILITY EXCEEDS THRESHOLD", "error")
        add_log("Activating Vyuha Commander AI...", "warn")
        with log_slot.container():
            render_log()

        with st.spinner("🚨  DEBRIS DETECTED — ACTIVATING VYUHA AGENT..."):
            session_id = f"dash-{st.session_state.scan_count:04d}"
            act_data = api_act(rd, session_id)

        if not act_data:
            with log_slot.container():
                render_log()
            st.stop()

        st.session_state.last_act = act_data

        # ── Chain-of-thought expander ─────────────────────────────────
        with cot_slot:
            with st.expander("🧠  AGENT CHAIN OF THOUGHT", expanded=True):
                for entry in act_data.get("attempts_log", []):
                    n = entry["attempt"]
                    cmd = entry["command"]
                    val = entry["validation"]
                    action = cmd.get("action", "?")
                    reasoning = cmd.get("reasoning", "")

                    if val["valid"]:
                        st.markdown(
                            f'<div class="cot-approved">'
                            f'<b>ATTEMPT {n}</b> → <b>{action}</b> ✅ APPROVED '
                            f'(source: {val["source"]})<br>'
                            f'<span style="opacity:0.7">{reasoning}</span></div>',
                            unsafe_allow_html=True,
                        )
                        add_log(
                            f"🟢 ATTEMPT {n}: [{action}] — Approved ({val['source']})",
                            "success",
                        )
                    else:
                        tags = ", ".join(val.get("violation_tags", []))
                        st.markdown(
                            f'<div class="cot-blocked">'
                            f'<b>ATTEMPT {n}</b> → <b>{action}</b> 🔴 BLOCKED<br>'
                            f'Policy Violation: [{tags}]</div>',
                            unsafe_allow_html=True,
                        )
                        add_log(
                            f"🔴 ATTEMPT {n}: [{action}] — BLOCKED [{tags}]",
                            "error",
                        )
                        st.markdown(
                            f'<div class="cot-retry">'
                            f'↳ Commander self-correcting via feedback loop...</div>',
                            unsafe_allow_html=True,
                        )
                        add_log("   ↳ Commander self-correcting (feedback loop)...", "warn")

        # ── Result banner ─────────────────────────────────────────────
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
                    <div style="font-size:1.5rem;font-weight:900;margin-bottom:8px;">
                        ✅ MANEUVER EXECUTED
                    </div>
                    <div style="font-size:0.85rem;font-family:'JetBrains Mono';opacity:0.9;">
                        Action: <b>{fc['action']}</b> &nbsp;·&nbsp;
                        Thrust: <b>{fc['recommended_thrust_direction']}</b> &nbsp;·&nbsp;
                        Confidence: <b>{fc.get('confidence_score', 0):.0%}</b>
                    </div>
                    <div style="font-size:0.7rem;font-family:'JetBrains Mono';opacity:0.6;margin-top:8px;">
                        {fc.get('reasoning', '')}
                    </div>
                    <div style="font-size:0.6rem;margin-top:6px;opacity:0.35;">
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
                    <div style="font-size:1.5rem;font-weight:900;margin-bottom:8px;">
                        🚨 AGENT FAILED — SECURITY LOCKOUT
                    </div>
                    <div style="font-size:0.85rem;font-family:'JetBrains Mono';opacity:0.85;">
                        MANUAL OVERRIDE REQUIRED
                    </div>
                    <div style="font-size:0.7rem;font-family:'JetBrains Mono';opacity:0.6;margin-top:8px;">
                        {reason}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    elif rd["status"] == "WARNING":
        add_log("⚠️  Elevated risk — monitoring. No action required.", "warn")
    else:
        add_log("✅ Sector clear — no threats detected.", "success")

    # ── Refresh log ───────────────────────────────────────────────────
    with log_slot.container():
        render_log()


# ═══════════════════════════════════════════════════════════════════════════
# Data Source Transparency Footer
# ═══════════════════════════════════════════════════════════════════════════

st.markdown("---")
scan = st.session_state.last_scan
if scan:
    rd = scan["risk_data"]
    ds = rd.get("data_source", "N/A")
    sm = rd.get("scenario_mode", "N/A")

    fc1, fc2 = st.columns(2)
    with fc1:
        st.markdown(
            f'<div class="data-source-bar" style="text-align:left">'
            f'📡 DATA SOURCE: <b style="color:#4a8a4a">{ds}</b></div>',
            unsafe_allow_html=True,
        )
    with fc2:
        mode_color = "#ff3333" if sm == "SYNTHETIC_DEBRIS_INJECTION" else "#00ff41"
        st.markdown(
            f'<div class="data-source-bar" style="text-align:right">'
            f'🔬 SCENARIO MODE: <b style="color:{mode_color}">{sm}</b></div>',
            unsafe_allow_html=True,
        )

    with st.expander("📄 RAW API RESPONSE", expanded=False):
        st.json(scan)
else:
    st.markdown(
        '<div class="data-source-bar">No scan data yet — click a button above to begin.</div>',
        unsafe_allow_html=True,
    )
