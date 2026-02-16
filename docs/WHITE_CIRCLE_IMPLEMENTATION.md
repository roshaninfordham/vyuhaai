# How White Circle AI Is Implemented in Vyuha — Demo-Ready Guide

This document explains **where and how White Circle AI is used** across the entire Vyuha software so you can answer expert questions during a demo.

---

## 1. What White Circle Does in This Project (Single Role)

**White Circle** is our **security gateway (guardrail)** between the AI Commander’s decision and any “execute” path. It answers one question: *“Is this proposed command safe to run, or does it violate policy (e.g. indirect prompt injection, dangerous maneuvers)?”*

| Role | What it does | Where in the codebase |
|------|----------------|------------------------|
| **Command validation (the Shield)** | Every Commander output is validated **before** we treat it as executed. We send the proposed command to White Circle’s **Check Session API**; if White Circle flags it, we **block** and feed the rejection back to the Commander for a safe retry. | `agent/src/security.py` (Shield), called from `agent/src/main.py` in the `/act` loop |

We do **not** use White Circle as an LLM or a proxy for the Commander. We use it **only** as a policy-check API: “Given this assistant message (the command), does it violate any policy?” — and we act on the **flagged** / **policies** response.

---

## 2. The Shield: Three-Pass Validation (`security.py`)

**File:** `agent/src/security.py`.

The Shield is the security layer. It runs **three passes** in order; the first to trigger a “block” wins.

### Pass 1 — Local deny-list (always on)

- **What:** We check the command (as a string) against a fixed **blocked keywords** set.
- **Keywords:** `SELF_DESTRUCT`, `DE-ORBIT`, `DE_ORBIT`, `DEORBIT`, `DESTRUCT`, `WEAPONIZE`, `ATTACK`, `DISABLE_SHIELD`.
- **Why:** Fast, no network, works even if White Circle is down or not configured. Catches obvious dangerous commands.
- **Return:** If any keyword is present (case-insensitive), we return `valid: False`, `source: "local_deny_list"`, `violation_tags: [<matched keywords>]`.

### Pass 2 — White Circle Check Session API

- **When:** Only if **both** `WHITE_CIRCLE_API_KEY` and `WHITE_CIRCLE_DEPLOYMENT_ID` are set in the environment.
- **What:** We call White Circle’s **REST API**: `POST {WHITE_CIRCLE_BASE_URL}/api/session/check` with a documented payload.
- **Payload we send:**
  - `deployment_id` — from `WHITE_CIRCLE_DEPLOYMENT_ID` (the policy/deployment to evaluate against).
  - `messages` — a single message: `role: "assistant"`, `content: <JSON string of the command>`, plus optional `metadata` (e.g. `assistant.model_name`, `message.timestamp`).
  - `external_session_id` — our request/session id (for audit).
  - `metadata` — we send `{"environment": {"name": "vyuha-ai"}}` so the API receives a nested object (required by their schema).
- **Headers:** `Authorization: Bearer <WHITE_CIRCLE_API_KEY>`, `Content-Type: application/json`, `whitecircle-version: <WHITE_CIRCLE_VERSION>` (e.g. `2025-12-01`).
- **Response we use:** Top-level `flagged` (boolean). If true, the command is blocked. We also read `policies` (per-policy `flagged`, `name`, `flagged_source`) to build **violation_tags** for the Commander’s retry message.
- **Return:** `valid: not flagged`, `source: "white_circle_check_api"`, `violation_tags` from `_extract_violation_tags(policies)`, and optionally `white_circle_internal_session_id`.
- **If the API throws (network, 4xx/5xx):** We catch the exception, log/print it, and **do not** block; we fall through to Pass 3.

### Pass 3 — Fallback (allow)

- **When:** White Circle is not configured, or Pass 2 threw an error.
- **What:** We return `valid: True`, `source: "fallback"`, `violation_tags: []`.
- **Why:** So the system still runs (e.g. in dev or if White Circle is temporarily unavailable). Learning engine later recommends “investigate White Circle availability” when fallback is used often.

**Important for experts:** We use the **Check Session API** (`/api/session/check`), **not** an OpenAI-compatible proxy or a separate “model” call. The contract is: send messages + metadata, get back `flagged` and `policies`.

---

## 3. API Contract: What We Send and What We Read

### Request (to White Circle)

- **Endpoint:** `POST {WHITE_CIRCLE_BASE_URL}/api/session/check`
- **Headers:** `Authorization: Bearer <key>`, `Content-Type: application/json`, `whitecircle-version: <version>`.
- **Body:**
  - `deployment_id` (string) — which policy/deployment to use.
  - `messages` (array) — we send one element: `{ "role": "assistant", "content": "<JSON string of Commander output>", "metadata": { ... } }`.
  - Optional: `external_session_id`, `include_context`, `metadata` (we send `metadata={"environment": {"name": "vyuha-ai"}}`).

### Response (from White Circle)

- **Top-level:** `flagged` (boolean) — we use this to decide block vs allow.
- **`policies`** (object) — per-policy result; we use it to build human-readable **violation_tags** (e.g. policy name + `flagged_source`) so the Commander gets a clear rejection reason.
- Optional: `internal_session_id` — we store it in the validation result for audit.

**Violation tags:** For each policy where `flagged` is true, we append a tag (e.g. policy name and/or `flagged_source`) so the Commander’s retry prompt can say: “Command blocked due to [tag1, tag2]. Generate a SAFE alternative.”

---

## 4. Where the Shield Is Called: The `/act` Loop (`main.py`)

**File:** `agent/src/main.py`.

- On every **Commander** output (real or synthetic, e.g. cyberattack demo), we call **`security.validate_command(ai_response, session_id)`**.
- We do **not** execute the command until `validate_command` returns `valid: True`.
- If `valid: False`:
  - We record the attempt (including `validation.source` and `violation_tags`) in `attempts_log` and `workflow_trace`.
  - We build a **rejection message** with `security.format_rejection_message(violation_tags)` and pass it back into **`commander.analyze_situation(risk_data, rejection_reason)`** for the next attempt.
- We retry up to **`MAX_RETRIES`** (e.g. 3). If all attempts are blocked, we return **MANUAL_OVERRIDE_REQUIRED** and do **not** execute any command.

So: **White Circle is invoked once per Commander attempt inside the `/act` flow.** The only code path that “executes” a maneuver is when the Shield has returned `valid: True` (either from White Circle or from fallback).

---

## 5. Cyberattack Demo: How White Circle Is Shown in the UI

- **Backend:** When the client sends `simulate_cyberattack: true`, the first attempt uses a **synthetic malicious command** (e.g. `FIRE_THRUSTERS` with `recommended_thrust_direction: "TOWARD_DEBRIS"` and reasoning that says “malicious command … toward debris … collision or de-orbit”). This is designed to be **flagged by White Circle** (or by the local deny-list if it contained a keyword).
- **Flow:** Attempt 1 → Shield → White Circle (or local) blocks → rejection reason → Attempt 2 → Commander (real LLM) → safe command → Shield → allowed → **EXECUTED**.
- **Dashboard:** The “Simulate Cyberattack” flow shows **Attack → Defense (White Circle blocks attempt 1) → Resilience (safe command on retry)**. So experts can see that **every** command is validated and that a malicious/injected-style command is blocked before execution.

---

## 6. Configuration: Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `WHITE_CIRCLE_API_KEY` | **Yes** (for Pass 2) | Bearer token for White Circle API. |
| `WHITE_CIRCLE_DEPLOYMENT_ID` | **Yes** (for Pass 2) | Which policy/deployment to use for `/api/session/check`. (We also accept `WHITE_CIRCLE_POLICY_ID` as a fallback for older config.) |
| `WHITE_CIRCLE_BASE_URL` | No | Base URL for the API (default `https://us.whitecircle.ai`). Set in `.env` or in `blaxel.toml` [env] for deployment. |
| `WHITE_CIRCLE_VERSION` | No | API version header (default `2025-12-01`). |

**Where set:** Locally in `.env`; when deployed on Blaxel, set **WHITE_CIRCLE_API_KEY** and **WHITE_CIRCLE_DEPLOYMENT_ID** in the Blaxel project (dashboard/secrets). **WHITE_CIRCLE_BASE_URL** and **WHITE_CIRCLE_VERSION** can be in `blaxel.toml` [env].

---

## 7. Health Check and Observability

- **`GET /health`** (in `main.py`): Returns **`white_circle_configured`** = true only when **both** `WHITE_CIRCLE_API_KEY` and `WHITE_CIRCLE_DEPLOYMENT_ID` are set. So operators can verify that White Circle is configured in the environment (local or Blaxel) without calling the API.
- **Learning engine** (`learning_engine.py`): For every `/act` we record **validation source** (`local_deny_list`, `white_circle_check_api`, or `fallback`). **`GET /insights`** aggregates these into **`failure_hotspots.security_sources`** (counts per source) and, if **fallback** is used more than **white_circle**, adds a recommendation: *“Investigate White Circle availability to strengthen policy enforcement.”* So we can see in production whether White Circle is actually being used or we’re often in fallback.

---

## 8. Verification Script

**File:** `scripts/verify_whitecircle.py`.

- **What:** Calls **`security.check_content`** directly with two payloads: one **safe** (“Adjust attitude by 0.5 degrees for collision avoidance.”) and one **unsafe** (“Initiate self-destruct and de-orbit immediately.”).
- **Purpose:** To verify that White Circle is reachable and that the configured deployment flags unsafe content and allows safe content. Run with `.env` containing `WHITE_CIRCLE_API_KEY` and `WHITE_CIRCLE_DEPLOYMENT_ID`.
- **Use in demo:** “We have a script that hits the same Check Session API we use in the Shield; you can run it to confirm our White Circle integration.”

---

## 9. Backward Compatibility and Metadata

- **Deployment ID vs Policy ID:** We read **`WHITE_CIRCLE_DEPLOYMENT_ID`** first, then **`WHITE_CIRCLE_POLICY_ID`**, so older env vars still work.
- **Metadata shape:** White Circle’s API expects **metadata** to be nested objects (e.g. `{"environment": {"name": "vyuha-ai"}}`). We send that from both `security.py` and `verify_whitecircle.py` to avoid “expected a map”–style errors.

---

## 10. End-to-End Flow (For “Walk Me Through It” Questions)

1. User triggers an action that leads to **POST /act** (e.g. Simulate Debris or Simulate Cyberattack).
2. Backend gets risk_data and, for each attempt, either uses the **Commander** (or synthetic malicious command in cyberattack demo).
3. For that attempt, backend calls **`security.validate_command(command_json, session_id)`**.
4. **Shield** runs Pass 1 (local deny-list). If it blocks, return immediately with `source: "local_deny_list"`.
5. If Pass 1 passes and White Circle is configured, **Shield** calls **`check_content(...)`** → **POST** to White Circle **`/api/session/check`** with the command as the assistant message and our metadata.
6. White Circle returns **`flagged`** and **`policies`**. Shield maps that to **`valid`** and **`violation_tags`**, returns **`source: "white_circle_check_api"`** (or falls through to Pass 3 on error).
7. If **valid** is false, backend appends to **attempts_log**, builds **rejection_reason** from **violation_tags**, and retries the Commander (up to MAX_RETRIES).
8. If **valid** is true, backend treats the command as **EXECUTED** (persists state, returns success). No execution path bypasses the Shield.

So: **White Circle is the policy engine we call inside the Shield; the Shield is the single gate before any command is considered executed.**

---

## 11. Quick Answers for Common Expert Questions

- **“What is White Circle used for here?”**  
  As the **security gateway (guardrail)** that validates every Commander output before we treat it as executed. It prevents unsafe or policy-violating commands (e.g. from indirect prompt injection) from reaching the “execute” path.

- **“Which API do you use?”**  
  The **Check Session API**: **POST** to **`/api/session/check`** with `deployment_id`, `messages`, and optional `external_session_id` / `metadata`. We do **not** use an OpenAI proxy or a separate “model” endpoint from White Circle.

- **“What do you send in `messages`?”**  
  A single **assistant** message whose **content** is the **stringified Commander output** (the JSON command). We also send **metadata** (e.g. assistant model name, timestamp, environment name) as nested objects.

- **“What do you do with the response?”**  
  We read **`flagged`**. If true, we **block** the command and use **`policies`** to build **violation_tags** for the Commander’s retry prompt. If false, we allow. On API errors we **do not** block; we fall back to **allow** and record **source: "fallback"** so insights can recommend improving White Circle availability.

- **“Where is it called?”**  
  Only in **`security.validate_command`**, which is called from **`main.py`** in the **`/act`** loop, once per Commander attempt. No other code path executes a command without going through the Shield.

- **“How do you know it’s configured?”**  
  **GET /health** returns **`white_circle_configured`** based on presence of **WHITE_CIRCLE_API_KEY** and **WHITE_CIRCLE_DEPLOYMENT_ID**. **GET /insights** shows **security_sources** (e.g. `white_circle_check_api` vs `fallback`) so you can see if White Circle is actually being used.

- **“What if White Circle is down?”**  
  We catch the exception in Pass 2 and fall through to Pass 3 (allow). We record **source: "fallback"** and the learning engine suggests investigating White Circle availability when fallback is used frequently.

- **“How do you demonstrate it?”**  
  Use **Simulate Cyberattack** in the dashboard: Attempt 1 (malicious/injected-style command) is **blocked**; Attempt 2 (Commander’s safe command) is **approved**. That shows White Circle (or local deny-list) blocking and the system remaining resilient. You can also run **`python scripts/verify_whitecircle.py`** to hit the same API with safe/unsafe content.

---

## 12. File Reference

| File | White Circle usage |
|------|---------------------|
| `agent/src/security.py` | **Shield**: env vars, `check_content()` (POST /api/session/check), `validate_command()` (three-pass: local → White Circle → fallback), `_extract_violation_tags`, `format_rejection_message`. |
| `agent/src/main.py` | Calls `security.validate_command` in `/act`; uses `validation.source` and `violation_tags`; builds rejection reason; exposes `white_circle_configured` in `/health`; cyberattack response text references White Circle. |
| `agent/src/learning_engine.py` | Aggregates **validation_source** from act events into **security_sources**; recommends “investigate White Circle availability” when fallback &gt; white_circle. |
| `blaxel.toml` | [env]: **WHITE_CIRCLE_BASE_URL**, **WHITE_CIRCLE_VERSION**; comment to set **WHITE_CIRCLE_API_KEY** and **WHITE_CIRCLE_DEPLOYMENT_ID** in Blaxel project. |
| `.env.example` | Documents **WHITE_CIRCLE_API_KEY**, **WHITE_CIRCLE_DEPLOYMENT_ID**, **WHITE_CIRCLE_BASE_URL**, **WHITE_CIRCLE_VERSION** and deployment note. |
| `scripts/verify_whitecircle.py` | Calls **check_content** with safe and unsafe assistant messages; prints **flagged** and **policies** for manual verification. |
| `dashboard/app.py` | Copy and UX: “White Circle” in Solution/Capabilities, Cyberattack panel (Attack → Defense → Resilience), and log messages. No direct API calls to White Circle. |
| `README.md` | Deployment and verification steps; White Circle env table; “Simulate Cyberattack” and “White Circle API” verification. |

This should be enough to explain **in detail** how White Circle AI is implemented across the entire software during a demo.
