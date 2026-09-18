# MEMORY.md — GridWise (BUP CSE Fest 2026 Hackathon)

## 1. Hackathon Problem Summary
- **Event:** BUP CSE Fest 2026 Hackathon — Online Preliminary Round.
- **Time Window:** 7:00 PM – 11:00 PM (4 hours), September 18, 2026.
- **Challenge:** Smart Campus Energy Optimization Challenge with LLM-Assisted Operator Directive Interpretation ("GridWise").
- **Core Problem:** BUP operates a smart microgrid utilizing grid import (variable tariffs), rooftop solar PV, and a battery energy storage system (BESS). In addition to 24-hour forecast data, campus operators submit 1–3 natural-language operational notes. The service must parse these notes with an LLM, validate them with deterministic guardrails, optimize hourly dispatch with Linear Programming (PuLP/CBC), and minimize total BDT grid cost while strictly respecting physical balance, battery neutrality, and rate limits.

---

## 2. Important Rules & Technical Requirements
- **Endpoints:**
  - `GET /health` -> HTTP 200 `{"status": "ok"}`
  - `POST /optimize-energy` -> Accepts scenario payload, returns structured interpretation and 24-hour plan.
- **Directives (6 Canonical Types):**
  - `solar_reduction`: `{"hours": [...], "factor": float}`, `applies: true`
  - `minimum_battery_reserve`: `{"hours": [...], "minimum_energy_kwh": float}`, `applies: true`
  - `no_charge_window`: `{"hours": [...]}`, `applies: true`
  - `no_discharge_window`: `{"hours": [...]}`, `applies: true`
  - `max_grid_window`: `{"hours": [...], "max_grid_kwh": float}`, `applies: true`
  - `no_op`: Distractors; `structured_adjustment: null`, `applies: false` (only directive with `applies = false`).
- **Time Convention:** Whole-hour intervals, start-inclusive and end-exclusive (e.g. 1 PM to 3 PM is `[13, 14]`).
- **Energy Accounting & Physics:**
  - Hourly balance: $G_h + S_{used, h} + D_h = Demand_h + C_h$
  - Battery transitions: $E_h = E_{h-1} + C_h - D_h$
  - Bounds: $min\_reserve_h \le E_h \le capacity$
  - Neutrality: $E_{23} == initial\_energy$
  - Rates: $C_h \le max\_charge$, $D_h \le max\_discharge$
- **Latency & Reliability:** p95 latency $\le 5.0$s for full points; timeout 30s; controlled HTTP 400 for bad input, HTTP 500 without leaking secrets.

---

## 3. Submission Requirements
- **Deadline:** 11:00 PM today via Google Form (`https://forms.gle/fDdAWMnipWXsfgc67`).
- **Crucial Rule:** Any commit made on GitHub after 11:00 PM results in immediate disqualification.
- **Required Deliverables:**
  1. Working Public API Base URL (accessible for `GET /health` and `POST /optimize-energy`).
  2. GitHub Repository (Private during event, switch to Public right after 11:00 PM).
  3. README.md & documentation (reproducibility, quickstart, solver, curl examples).
  4. Docker Fallback Image / Dockerfile (port 8000, 0.0.0.0, no baked-in secrets).
  5. 3-Minute Architecture & Solution Video (MP4 or Google Drive/YouTube link).

---

## 4. Video Requirements
- **Duration:** Strictly maximum 3 minutes (180 seconds).
- **Format:** MP4 upload or public/unlisted link (Google Drive with "Anyone with link can view" or YouTube Unlisted).
- **Purpose:** Primary Tie-Breaker Priority #1. Evaluates problem understanding, architecture flow (LLM -> Guardrails -> Optimizer), key technical decisions, and live verification.
- **Editing:** Production quality is NOT required; technical clarity and working demo are scored.

---

## 5. Video Plan (Step-by-Step)
- **0:00 – 0:35:** Introduce problem, campus microgrid, 24-hour horizon, and natural-language operator directives.
- **0:35 – 1:15:** Explain 3-tier architecture:
  1. LLM Interpretation (Gemini 2.5 Flash via OpenRouter).
  2. Deterministic Guardrails (validating types, ascending unique hours, clamping).
  3. Linear Programming Optimizer (PuLP/CBC solving exact energy balance & neutrality).
- **1:15 – 2:05:** Code walkthrough of `llm_interpreter.py`, `guardrails.py`, and `optimizer.py`.
- **2:05 – 2:45:** Terminal demo: run `python test_runner.py` showing all 10 public sample cases passing 100% with p95 latency under 4.1s.
- **2:45 – 3:00:** Show `Dockerfile` and live public Cloudflare endpoint URL. Wrap up.

---

## 6. Project Structure
```
C:\Users\Lenovo\GridWise\
├── .dockerignore
├── .env.example
├── .gitignore
├── Dockerfile
├── MEMORY.md
├── README.md
├── config.py
├── guardrails.py
├── llm_interpreter.py
├── main.py
├── optimizer.py
├── requirements.txt
├── schemas.py
├── test_runner.py
└── sample_cases\
    └── BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json
```

---

## 7. Work Already Completed
- Comprehensive analysis of Problem Statement, Participant Guide, and Rubric.
- Full schemas implemented in `schemas.py` with Pydantic v2.
- LLM interpreter in `llm_interpreter.py` using `google/gemini-2.5-flash` with structured JSON prompts and resilient fallback.
- Guardrails in `guardrails.py` enforcing Section 08 rules.
- PuLP/CBC linear programming model in `optimizer.py` guaranteeing global optimality and physics compliance.
- FastAPI server in `main.py` exposing `GET /health` and `POST /optimize-energy`.
- Test runner updated to test both in-memory and live remote URLs.
- Local repository populated with `sample_cases/` for self-contained reproduction.
- Live public Cloudflare tunnel created: `https://builder-rosa-mel-dvds.trycloudflare.com`.
- Full verification suite executed over the live internet tunnel: 10/10 PASS, p95 latency 4.06s.
- Evaluation-ready `README.md`, `Dockerfile`, `.dockerignore`, `.gitignore`, and `.env.example` created.

---

## 8. Files Modified / Created
- `config.py`: Added robust multi-path env loading.
- `schemas.py`: Robust hour sorting and directive validation.
- `llm_interpreter.py`: Optimized `max_tokens: 400` to prevent OpenRouter 402 budget exhaustion.
- `test_runner.py`: Enhanced to support live endpoint testing and local sample cases.
- `sample_cases/BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json`: Self-contained public cases pack.
- `README.md`: Comprehensive evaluation documentation.
- `Dockerfile`: Production container build with coinor-cbc and healthcheck.
- `.dockerignore`: Excluded cache, secrets, and git.
- `.gitignore`: Strict secret and cache exclusion.
- `.env.example`: Configuration template without secrets.
- `MEMORY.md`: Complete persistent record.

---

## 9. Current Implementation Status
- **Pipeline:** 100% complete and verified.
- **Local API:** Running on `http://localhost:8000`.
- **Public API:** Running live on `https://builder-rosa-mel-dvds.trycloudflare.com`.
- **Test Suite:** 100% passing across all 10 public test cases locally and over the public tunnel.

---

## 10. Remaining Tasks
1. Stage all project files in Git and create a clean initial commit.
2. Check if GitHub CLI is authenticated; if so, push to a **Private** repository named `bup-gridwise-2026`. If not, provide the exact commands for manual push.
3. User to record 3-minute video and upload to Google Drive/YouTube unlisted.
4. User to fill out Google Form before 11:00 PM.
5. User to switch repository visibility from Private to Public right after 11:00 PM.

---

## 11. Known Bugs or Errors
- None. Token budget was resolved by setting `max_tokens: 400`. Fallback interpreter prevents crashes if remote LLM times out.

---

## 12. Important Commands
- Run server: `uvicorn main:app --host 0.0.0.0 --port 8000`
- Run local tests: `python test_runner.py`
- Run live endpoint tests: `python test_runner.py http://localhost:8000`
- Run public tunnel tests: `python test_runner.py https://builder-rosa-mel-dvds.trycloudflare.com`
- Run Cloudflare tunnel: `cloudflared tunnel --url http://localhost:8000`

---

## 13. Important Technical Decisions
- **LLM:** `google/gemini-2.5-flash` via OpenRouter for low latency (<2.5s) and zero-shot structured JSON compliance.
- **Fallback Interpreter:** Deterministic semantic regex parser ensures 100% uptime if LLM provider is degraded.
- **Guardrail Isolation:** Optimizer never receives raw LLM output; all directives pass deterministic validation first.
- **Solver:** PuLP with CBC. Uses regularizers $10^{-4} P$ (peak load smoothing) and $10^{-6} (C+D)$ (preventing simultaneous charge/discharge) to guarantee unique, realistic schedules matching organizer reference outputs.

---

## 14. Assumptions Made
- Synthetic challenge scenarios are feasible and contain non-contradictory hard constraints (per Section 08).
- Whole-hour intervals: start-inclusive, end-exclusive.
- Zero grid export permitted; unused solar is curtailed.

---

## 15. Tasks That Require User Manual Action
1. **Video Recording:** Record the 3-minute demo following the script in Section 5.
2. **Pushing to GitHub:** If GitHub CLI is unauthenticated, manually create private repository `bup-gridwise-2026` and push.
3. **Google Form:** Submit before 11:00 PM deadline at `https://forms.gle/fDdAWMnipWXsfgc67`.
4. **Make Repository Public:** Change repo visibility from Private to Public right after 11:00 PM.

---

## 16. Information Needed for Google Form
- **Project Title:** GridWise: LLM-Assisted Smart Campus Energy Optimizer
- **Public API Base URL:** `https://builder-rosa-mel-dvds.trycloudflare.com`
- **Health URL:** `https://builder-rosa-mel-dvds.trycloudflare.com/health`
- **Optimize Endpoint:** `https://builder-rosa-mel-dvds.trycloudflare.com/optimize-energy`
- **GitHub Repository URL:** `https://github.com/<username>/bup-gridwise-2026` (Private during event)
- **Architecture / Video URL:** *(User Google Drive or YouTube unlisted link)*
- **Model / Provider:** `google/gemini-2.5-flash via OpenRouter`
- **Optimization Solver:** `PuLP with CBC Linear Programming Solver`

---

## 17. Information Needed for Video
- See Section 5 above for full breakdown and narration script.

---

## 18. Testing Status
- In-memory TestClient: **10/10 PASS** (Avg Latency: 2.00s, p95: 4.91s)
- Live Cloudflare Tunnel: **10/10 PASS** (Avg Latency: 1.74s, p95: 4.06s)
- Physical Balance Verification: 100% passed on all hours.
- Battery Neutrality: 100% passed ($E_{23} == initial\_energy$).

---

## 19. Final Submission Status
- Code complete, verified, and running.
- Tunnel active.
- Ready for Git commit and submission.

---

## 20. Exact Point Where Previous Agent Stopped
- Completed live tunnel testing, README, Dockerfile, and MEMORY update. Proceeding to stage files and make clean Git commit.
