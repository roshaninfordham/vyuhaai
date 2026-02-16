"""
Vyuha AI — Visual Threat Detection (Multimodal)
================================================
Optical sensor module: analyzes video feed for debris using Overshoot AI's
Vision Language Model (Qwen3-VL-8B-Instruct).

Overshoot API base: https://api.overshoot.ai/v1
Fallback: simulated visual report when the API is unavailable.
"""

from __future__ import annotations

import logging
import os
import time

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("vyuha.vision")

OVERSHOOT_API_KEY: str = os.getenv("OVERSHOOT_API_KEY", "")
OVERSHOOT_BASE_URL: str = os.getenv(
    "OVERSHOOT_BASE_URL", "https://cluster1.overshoot.ai/api/v0.2"
)
OVERSHOOT_MODEL: str = "Qwen/Qwen3-VL-8B-Instruct"

DEFAULT_VIDEO_URL: str = (
    "https://cdn.pixabay.com/video/2019/04/20/22906-331767667_large.mp4"
)

VISION_PROMPT: str = (
    "You are an onboard satellite optical sensor AI. "
    "Analyze this video clip from the spacecraft camera. "
    "Describe any space debris, asteroids, or satellite fragments you observe. "
    "Assess whether there is a collision risk. "
    "Be specific about object size, velocity direction, and distance if visible."
)

SIMULATED_REPORT: str = (
    "[SIMULATION] Camera sensor active. Object detected in Sector 4. "
    "Visual signature matches localized debris field — estimated 3 fragments, "
    "largest ~12 cm, tumbling at high angular velocity. "
    "Relative velocity vector indicates closing trajectory. "
    "High collision risk confirmed by optical analysis."
)


def analyze_visual_feed(video_url: str | None = None) -> dict:
    """Analyze a video feed for space debris using Overshoot AI.

    Parameters
    ----------
    video_url : str, optional
        URL of the video to analyze. Falls back to a default space video.

    Returns
    -------
    dict
        Keys: ``description`` (str), ``source`` (str), ``video_url`` (str),
        ``latency_ms`` (float).
    """
    url = video_url or DEFAULT_VIDEO_URL
    started = time.perf_counter()

    if not OVERSHOOT_API_KEY:
        logger.warning("OVERSHOOT_API_KEY not set — returning simulated visual report")
        return {
            "description": SIMULATED_REPORT,
            "source": "simulation",
            "video_url": url,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        }

    try:
        payload = {
            "model": OVERSHOOT_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": VISION_PROMPT},
                        {
                            "type": "video_url",
                            "video_url": {"url": url},
                        },
                    ],
                }
            ],
            "max_tokens": 512,
            "temperature": 0.3,
        }

        resp = requests.post(
            f"{OVERSHOOT_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {OVERSHOOT_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=30,
        )

        if resp.ok:
            data = resp.json()
            content = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )
            if content.strip():
                logger.info(
                    "Overshoot visual analysis complete (%d chars)",
                    len(content),
                )
                return {
                    "description": content.strip(),
                    "source": "overshoot_ai",
                    "video_url": url,
                    "latency_ms": round(
                        (time.perf_counter() - started) * 1000, 2
                    ),
                }

        logger.warning(
            "Overshoot API returned %s — falling back to simulation",
            resp.status_code,
        )

    except Exception as exc:
        logger.warning("Overshoot API error: %s — falling back to simulation", exc)

    return {
        "description": SIMULATED_REPORT,
        "source": "simulation",
        "video_url": url,
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("=" * 60)
    print("  Vyuha Vision — Optical Sensor Test")
    print("=" * 60)
    result = analyze_visual_feed()
    print(f"\nSource: {result['source']}")
    print(f"Video:  {result['video_url']}")
    print(f"Latency: {result['latency_ms']} ms")
    print(f"\nVisual Report:\n{result['description']}")
