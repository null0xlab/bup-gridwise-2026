# GridWise: LLM-Assisted Smart Campus Energy Optimizer
**BUP CSE Fest 2026 Hackathon · Preliminary Round**

GridWise is an automated microgrid energy scheduling service that interprets natural-language campus operator directives using a Large Language Model, validates them with strict deterministic guardrails, and solves a 24-hour Linear Programming (LP) optimization problem using PuLP and the CBC solver.

---

## 1. Problem Statement & Overview

Bangladesh University of Professionals (BUP) operates a smart microgrid powered by:
- **Grid Import:** Variable hourly electricity tariffs (BDT/kWh).
- **Rooftop Solar PV Generation:** Forecasted generation with curtailment (no export).
- **Battery Energy Storage System (BESS):** Shifts energy across hours, subject to capacity, rate limits, and end-of-day neutrality.

Campus operators supply **1 to 3 natural-language notes** per 24-hour scenario describing temporary conditions (e.g., panel washing, feeder caps, maintenance outages) or distractor announcements. The service converts notes into structured operational constraints, applies them to the mathematical dispatch model, and returns an optimal 24-hour hourly schedule that minimizes total grid electricity cost in BDT.

---

## 2. End-to-End Architecture

GridWise implements a strict three-tier processing pipeline:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      Human Operator Notes (1–3)                         │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                 1. LLM Directive Interpretation Layer                   │
│   • Model: google/gemini-2.5-flash via OpenRouter                       │
│   • Structured zero-shot prompt with strict JSON schema                 │
│   • High-availability deterministic rule-based fallback                 │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │ Raw JSON Directives
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                   2. Deterministic Guardrails Layer                     │
│   • Enforces Problem Statement Section 08 rules                         │
│   • Validates allowed directive types & applies semantics               │
│   • Normalizes hours into unique ascending ints [0..23]                 │
│   • Clamps factors (0.0..1.0) and reserves (0.0..capacity)              │
│   • Converts unsupported or invalid directives safely to no_op          │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │ Validated Active Directives
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                   3. Mathematical Optimization (LP)                     │
│   • Formulated using PuLP and solved with CBC                           │
│   • Exact 24-hour energy balance: Grid + Solar + Discharge = Demand + Charge│
│   • Battery state transitions, charge/discharge limits, neutrality      │
│   • Multi-objective regularizers: peak grid load smoothing              │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│               Valid 24-Hour Energy Plan & Cost Summary                  │
│       GET /health (HTTP 200) · POST /optimize-energy (HTTP 200)         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Supported Directive Types

The service recognizes and processes the 6 canonical directive types:

| Directive Type | Meaning | `structured_adjustment` Shape | `applies` |
| :--- | :--- | :--- | :--- |
| `solar_reduction` | Reduces usable rooftop solar during specific hours | `{"hours": [int, ...], "factor": float}` | `true` |
| `minimum_battery_reserve` | Raises battery reserve energy floor (kWh) | `{"hours": [int, ...], "minimum_energy_kwh": float}` | `true` |
| `no_charge_window` | Disables battery charging during specified hours | `{"hours": [int, ...]}` | `true` |
| `no_discharge_window` | Disables battery discharging during specified hours | `{"hours": [int, ...]}` | `true` |
| `max_grid_window` | Caps grid import (kWh) during specified hours | `{"hours": [int, ...], "max_grid_kwh": float}` | `true` |
| `no_op` | Distractor or irrelevant note with no schedule effect | `null` | `false` |

*Convention:* Whole-hour intervals are start-inclusive and end-exclusive (e.g., 1 PM to 3 PM maps to `[13, 14]`).

---

## 4. Environment Variables

| Variable | Description | Default Value | Required? |
| :--- | :--- | :--- | :--- |
| `OPENROUTER_API_KEY` | API key for OpenRouter LLM gateway | `""` | Yes (for live LLM) |
| `LLM_MODEL` | Target language model | `inclusionai/ling-3.0-flash-sante:free` | No |
| `LLM_BASE_URL` | OpenRouter OpenAI-compatible endpoint | `https://openrouter.ai/api/v1` | No |
| `HOST` | Server bind interface | `0.0.0.0` | No |
| `PORT` | Server listening port | `8000` | No |

A template is provided in `.env.example`.

---

## 5. Local Setup & Quickstart

### Prerequisites
- Python 3.10+ (Tested on Python 3.11)
- Git

### Installation
```bash
# 1. Clone the repository
git clone https://github.com/null0xlab/bup-gridwise-2026.git
cd bup-gridwise-2026

# 2. Create and activate a virtual environment
python -m venv venv
# Windows:
.\venv\Scripts\activate
# Linux / macOS:
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables
# Linux / macOS:
cp .env.example .env
# Windows PowerShell:
Copy-Item .env.example .env
# Edit .env and paste your OPENROUTER_API_KEY
```

### Running the API
```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```
The server will start at `http://localhost:8000`.

---

## 6. API Endpoints & Usage

### 1. Health Readiness Check
**Endpoint:** `GET /health`

**cURL:**
```bash
curl -X GET http://localhost:8000/health
```

**Response (HTTP 200):**
```json
{
  "status": "ok"
}
```

### 2. Service Discovery
**Endpoint:** `GET /`

Returns links to the service health and optimization endpoints:
```json
{
  "service": "GridWise",
  "status": "ok",
  "health": "/health",
  "optimize": "/optimize-energy"
}
```

### 3. Energy Optimization Endpoint
**Endpoint:** `POST /optimize-energy`

**cURL:**
```bash
curl -X POST http://localhost:8000/optimize-energy \
  -H "Content-Type: application/json" \
  -d '{
    "scenario_id": "SAMPLE-01",
    "operator_notes": [
      "Facilities will wash the rooftop solar panels from noon until 2 PM. During cleaning, usable solar should be treated as roughly 25% of the forecast.",
      "The sports office moved next months registration deadline."
    ],
    "hours": [
      {"hour": 0, "demand_kwh": 90, "solar_kwh": 0, "tariff_bdt_per_kwh": 6},
      {"hour": 1, "demand_kwh": 85, "solar_kwh": 0, "tariff_bdt_per_kwh": 6},
      {"hour": 2, "demand_kwh": 80, "solar_kwh": 0, "tariff_bdt_per_kwh": 5},
      {"hour": 3, "demand_kwh": 80, "solar_kwh": 0, "tariff_bdt_per_kwh": 5},
      {"hour": 4, "demand_kwh": 85, "solar_kwh": 0, "tariff_bdt_per_kwh": 5},
      {"hour": 5, "demand_kwh": 95, "solar_kwh": 0, "tariff_bdt_per_kwh": 6},
      {"hour": 6, "demand_kwh": 110, "solar_kwh": 5, "tariff_bdt_per_kwh": 8},
      {"hour": 7, "demand_kwh": 130, "solar_kwh": 20, "tariff_bdt_per_kwh": 10},
      {"hour": 8, "demand_kwh": 150, "solar_kwh": 50, "tariff_bdt_per_kwh": 12},
      {"hour": 9, "demand_kwh": 165, "solar_kwh": 90, "tariff_bdt_per_kwh": 14},
      {"hour": 10, "demand_kwh": 175, "solar_kwh": 130, "tariff_bdt_per_kwh": 16},
      {"hour": 11, "demand_kwh": 180, "solar_kwh": 160, "tariff_bdt_per_kwh": 16},
      {"hour": 12, "demand_kwh": 185, "solar_kwh": 180, "tariff_bdt_per_kwh": 15},
      {"hour": 13, "demand_kwh": 180, "solar_kwh": 170, "tariff_bdt_per_kwh": 14},
      {"hour": 14, "demand_kwh": 170, "solar_kwh": 140, "tariff_bdt_per_kwh": 13},
      {"hour": 15, "demand_kwh": 165, "solar_kwh": 90, "tariff_bdt_per_kwh": 14},
      {"hour": 16, "demand_kwh": 170, "solar_kwh": 45, "tariff_bdt_per_kwh": 18},
      {"hour": 17, "demand_kwh": 185, "solar_kwh": 10, "tariff_bdt_per_kwh": 22},
      {"hour": 18, "demand_kwh": 205, "solar_kwh": 0, "tariff_bdt_per_kwh": 28},
      {"hour": 19, "demand_kwh": 215, "solar_kwh": 0, "tariff_bdt_per_kwh": 30},
      {"hour": 20, "demand_kwh": 205, "solar_kwh": 0, "tariff_bdt_per_kwh": 26},
      {"hour": 21, "demand_kwh": 175, "solar_kwh": 0, "tariff_bdt_per_kwh": 18},
      {"hour": 22, "demand_kwh": 135, "solar_kwh": 0, "tariff_bdt_per_kwh": 10},
      {"hour": 23, "demand_kwh": 105, "solar_kwh": 0, "tariff_bdt_per_kwh": 7}
    ],
    "battery": {
      "capacity_kwh": 220,
      "initial_energy_kwh": 110,
      "minimum_energy_kwh": 40,
      "max_charge_kwh_per_hour": 50,
      "max_discharge_kwh_per_hour": 50
    }
  }'
```

**Response (HTTP 200):**
```json
{
  "scenario_id": "SAMPLE-01",
  "directive_interpretation": [
    {
      "note_index": 0,
      "applies": true,
      "directive_type": "solar_reduction",
      "structured_adjustment": {
        "hours": [12, 13],
        "factor": 0.25
      },
      "explanation": "Solar availability is reduced to 25% during the panel-cleaning window."
    },
    {
      "note_index": 1,
      "applies": false,
      "directive_type": "no_op",
      "structured_adjustment": null,
      "explanation": "This note does not affect today's 24-hour energy schedule."
    }
  ],
  "hourly_plan": [
    {
      "hour": 0,
      "grid_kwh": 90.0,
      "solar_used_kwh": 0.0,
      "battery_action": "idle",
      "battery_kwh": 0.0,
      "battery_energy_after_kwh": 110.0
    },
    {
      "hour": 1,
      "grid_kwh": 45.0,
      "solar_used_kwh": 0.0,
      "battery_action": "discharge",
      "battery_kwh": 40.0,
      "battery_energy_after_kwh": 70.0
    }
  ],
  "total_grid_kwh": 2692.5,
  "total_cost_bdt": 38365.0,
  "peak_grid_kwh": 175.0,
  "plan_summary": "Applies active directives: solar reduction of 75% during hours [12, 13]. Ignores 1 unrelated distractor note(s). Optimizes battery charging during low-tariff/solar periods and discharges during peak tariff hours while strictly maintaining end-of-day battery neutrality."
}
```

---

## 7. Deterministic Guardrails & Verification

Raw LLM responses are never fed directly to the optimizer. `guardrails.py` deterministically checks:
1. **Directive Types:** Only allowed types (`solar_reduction`, `minimum_battery_reserve`, `no_charge_window`, `no_discharge_window`, `max_grid_window`, `no_op`) are accepted.
2. **Order & Cardinality:** Exactly one interpretation per operator note, strictly in `note_index` sequence `0..N-1`.
3. **Applies Semantics:** `applies = false` exclusively for `no_op` (which must have `structured_adjustment = null`). All other directives require `applies = true`.
4. **Hour Normalization:** Hours are converted to unique integers in `0..23` and sorted in ascending order.
5. **Value Clamping:** `factor` is clamped between `0.0` and `1.0`. `minimum_energy_kwh` is clamped between `0.0` and `capacity_kwh`.

---

## 8. Mathematical Optimization Model

The optimizer in `optimizer.py` formulates a Linear Program (LP) using PuLP:
- **Decision Variables:**
  - $G_h \ge 0$: Grid import during hour $h$ (capped at $max\_grid\_kwh$ if directive active).
  - $S_{used, h} \in [0, effective\_solar_h]$: Solar utilized in hour $h$.
  - $C_h \in [0, max\_charge_h]$: Battery charging power.
  - $D_h \in [0, max\_discharge_h]$: Battery discharging power.
  - $E_h \in [min\_reserve_h, capacity]$: Battery energy level at end of hour $h$.
  - $P \ge 0$: Peak grid load tracker.
- **Constraints:**
  - **Energy Balance:** $G_h + S_{used, h} + D_h - C_h = demand_h \quad \forall h \in [0, 23]$
  - **Battery State Evolution:** $E_h = E_{h-1} + C_h - D_h$
  - **End-of-Day Neutrality:** $E_{23} = initial\_energy$
- **Objective:**
  $$\min \sum_{h=0}^{23} (\text{tariff}_h \cdot G_h) + 10^{-4} P + 10^{-6} \sum_{h=0}^{23} (C_h + D_h)$$
  *The $10^{-4} P$ term smooths grid load across hours with identical tariffs, avoiding artificial spikes. The $10^{-6} (C_h + D_h)$ term strictly eliminates simultaneous charge and discharge.*

---

## 9. Testing & Automated Verification

A comprehensive test runner is included in `test_runner.py` that verifies:
- `GET /health` readiness
- `POST /optimize-energy` HTTP 400 error handling on invalid requests
- All **10 official public sample test cases** against physical balance, battery neutrality, rate bounds, and cost optimality.

### Run Local In-Memory Tests:
```bash
python test_runner.py
```

### Run Tests Against Live Endpoint / Tunnel:
```bash
python test_runner.py http://localhost:8000
# Or against a public tunnel:
python test_runner.py https://<your-tunnel-subdomain>.trycloudflare.com
```

### Verification Results:
- **Test Pass Rate:** **10/10 (100%)**
- **Average Latency:** **1.74s**
- **p95 Latency:** **4.06s** (Well below the 5.0s threshold for maximum rubric score)

---

## 10. Docker Deployment

### Build Container Image:
```bash
docker build -t gridwise:latest .
```

The GitHub Actions workflow also publishes a registry fallback image on each
push to `main`. Use the immutable commit tag shown in the workflow run, or
the corresponding digest, for evaluation.

### Run Container:
```bash
docker run -d -p 8000:8000 \
  -e OPENROUTER_API_KEY="your_api_key_here" \
  --name gridwise-service \
  gridwise:latest
```

### Verify Container Health:
```bash
curl http://localhost:8000/health
```

---

## 11. Security & Limitations

- **No Committed Secrets:** No `.env` files, API keys, or private tokens are committed to this repository. All credentials are injected via environment variables.
- **Synthetic Data:** The system operates strictly on synthetic scenario data as provided by the challenge harness.
- **Controlled Error Handling:** Malformed requests return structured HTTP 400 responses; internal server exceptions return generic HTTP 500 messages without exposing stack traces or environment secrets.
