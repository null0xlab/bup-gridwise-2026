import json
import time
import sys
import os
from pathlib import Path
import requests
from fastapi.testclient import TestClient
from main import app

# Target base URL (if testing a live running server or tunnel)
target_base_url = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else os.environ.get("TEST_SERVER_URL", "").rstrip("/")

client = TestClient(app) if not target_base_url else None

# Locate public sample cases JSON
potential_paths = [
    Path(__file__).parent / "sample_cases" / "BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json",
    Path(r"E:\BUP_CSE_FEST_2026_Participant_Docs\BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json")
]
SAMPLE_FILE = None
for p in potential_paths:
    if p.exists():
        SAMPLE_FILE = str(p)
        break

if not SAMPLE_FILE:
    raise FileNotFoundError("Could not find BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json in local sample_cases or E: drive.")


def call_get(path: str):
    if target_base_url:
        return requests.get(f"{target_base_url}{path}", timeout=15)
    return client.get(path)


def call_post(path: str, payload: dict):
    if target_base_url:
        return requests.post(f"{target_base_url}{path}", json=payload, timeout=30)
    return client.post(path, json=payload)


def run_all_tests():
    print("================================================================")
    print("  GRIDWISE END-TO-END AUTOMATED VERIFICATION SUITE")
    if target_base_url:
        print(f"  Target Server: {target_base_url}")
    else:
        print("  Target Server: In-Memory FastAPI TestClient")
    print("================================================================\n")

    # 1. Health endpoint check
    t0 = time.time()
    resp = call_get("/health")
    assert resp.status_code == 200, f"/health failed with status {resp.status_code}: {resp.text}"
    assert resp.json() == {"status": "ok"}, f"Unexpected health body: {resp.json()}"
    print(f"[PASS] GET /health (latency: {(time.time() - t0)*1000:.1f} ms) -> {resp.json()}\n")

    # 2. Malformed request check
    resp = call_post("/optimize-energy", {"scenario_id": "bad", "operator_notes": []})
    assert resp.status_code == 400, f"Expected 400 for bad request, got {resp.status_code}"
    print("[PASS] Controlled 400 error handling for invalid input.\n")

    # 3. Load sample cases
    with open(SAMPLE_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    cases = data["cases"]
    all_passed = True
    latencies = []

    print(f"Running {len(cases)} End-to-End Test Cases against POST /optimize-energy:\n")

    for case in cases:
        cid = case["id"]
        label = case["label"]
        inp = case["input"]
        exp = case["expected_output"]

        start_t = time.time()
        res = call_post("/optimize-energy", inp)
        elapsed = time.time() - start_t
        latencies.append(elapsed)

        if res.status_code != 200:
            print(f"[{cid}] FAIL - HTTP {res.status_code}: {res.text}")
            all_passed = False
            continue

        body = res.json()

        # Schema & echo checks
        assert body["scenario_id"] == inp["scenario_id"]
        assert len(body["directive_interpretation"]) == len(inp["operator_notes"])
        assert len(body["hourly_plan"]) == 24

        # Physical sanity checks
        battery = inp["battery"]
        cap = battery["capacity_kwh"]
        e_init = battery["initial_energy_kwh"]
        base_min = battery["minimum_energy_kwh"]
        max_ch = battery["max_charge_kwh_per_hour"]
        max_dis = battery["max_discharge_kwh_per_hour"]

        plan = body["hourly_plan"]
        directives = body["directive_interpretation"]

        # Track active directives
        eff_solar_factor = {}
        min_res_map = {}
        no_ch_hours = set()
        no_dis_hours = set()
        max_gr_map = {}

        for d in directives:
            if not d["applies"]:
                continue
            dtype = d["directive_type"]
            adj = d["structured_adjustment"] or {}
            hrs = adj.get("hours", [])
            if dtype == "solar_reduction":
                for h in hrs:
                    eff_solar_factor[h] = adj["factor"]
            elif dtype == "minimum_battery_reserve":
                for h in hrs:
                    min_res_map[h] = max(min_res_map.get(h, base_min), adj["minimum_energy_kwh"])
            elif dtype == "no_charge_window":
                no_ch_hours.update(hrs)
            elif dtype == "no_discharge_window":
                no_dis_hours.update(hrs)
            elif dtype == "max_grid_window":
                for h in hrs:
                    max_gr_map[h] = adj["max_grid_kwh"]

        # Hourly physical verification
        prev_e = e_init
        for h, item in enumerate(plan):
            h_inp = inp["hours"][h]
            demand = h_inp["demand_kwh"]
            base_solar = h_inp["solar_kwh"]
            eff_s = base_solar * eff_solar_factor.get(h, 1.0)

            g = item["grid_kwh"]
            s = item["solar_used_kwh"]
            act = item["battery_action"]
            b_kwh = item["battery_kwh"]
            e_after = item["battery_energy_after_kwh"]

            # Solar check
            assert s <= eff_s + 0.01, f"Hour {h}: solar_used {s} exceeds effective solar {eff_s}"
            assert s >= -0.01, f"Hour {h}: negative solar used {s}"

            # Battery action check
            if act == "charge":
                assert h not in no_ch_hours, f"Hour {h}: charged during no_charge_window"
                assert b_kwh <= max_ch + 0.01, f"Hour {h}: charge exceeds max rate"
                calc_e = prev_e + b_kwh
            elif act == "discharge":
                assert h not in no_dis_hours, f"Hour {h}: discharged during no_discharge_window"
                assert b_kwh <= max_dis + 0.01, f"Hour {h}: discharge exceeds max rate"
                calc_e = prev_e - b_kwh
            else:
                assert act == "idle"
                assert b_kwh == 0.0, f"Hour {h}: idle but battery_kwh > 0"
                calc_e = prev_e

            assert abs(calc_e - e_after) <= 0.01, f"Hour {h}: battery state transition mismatch ({calc_e} vs {e_after})"

            # Battery limits
            active_min = min_res_map.get(h, base_min)
            assert e_after >= active_min - 0.01, f"Hour {h}: battery {e_after} below minimum reserve {active_min}"
            assert e_after <= cap + 0.01, f"Hour {h}: battery {e_after} exceeds capacity {cap}"

            # Grid cap check
            if h in max_gr_map:
                assert g <= max_gr_map[h] + 0.01, f"Hour {h}: grid {g} exceeds cap {max_gr_map[h]}"

            # Energy balance
            inflow = g + s + (b_kwh if act == "discharge" else 0.0)
            outflow = demand + (b_kwh if act == "charge" else 0.0)
            assert abs(inflow - outflow) <= 0.05, f"Hour {h}: Energy balance violation: Inflow={inflow}, Outflow={outflow}"

            prev_e = e_after

        # End of day neutrality
        assert abs(prev_e - e_init) <= 0.01, f"End-of-day battery neutrality failed: {prev_e} vs initial {e_init}"

        # Recalculated cost check
        recalc_cost = round(sum(item["grid_kwh"] * inp["hours"][i]["tariff_bdt_per_kwh"] for i, item in enumerate(plan)), 2)
        assert abs(recalc_cost - body["total_cost_bdt"]) <= 0.05, "total_cost_bdt mismatch with recalculated hourly plan"

        cost_diff = abs(body["total_cost_bdt"] - exp["total_cost_bdt"])
        grid_diff = abs(body["total_grid_kwh"] - exp["total_grid_kwh"])
        peak_diff = abs(body["peak_grid_kwh"] - exp["peak_grid_kwh"])

        passed = (cost_diff <= 0.05 and grid_diff <= 0.05 and peak_diff <= 0.05)
        status_tag = "PASS" if passed else "FAIL"
        if not passed:
            all_passed = False

        print(f"[{status_tag}] {cid} ({label}): Latency: {elapsed:.2f}s | Cost: {body['total_cost_bdt']} (Ref: {exp['total_cost_bdt']}) | Grid: {body['total_grid_kwh']} (Ref: {exp['total_grid_kwh']}) | Peak: {body['peak_grid_kwh']} (Ref: {exp['peak_grid_kwh']})")

    avg_lat = sum(latencies) / len(latencies)
    p95_lat = sorted(latencies)[int(len(latencies) * 0.95)]
    print("\n----------------------------------------------------------------")
    print(f"Performance Metrics: Avg Latency = {avg_lat:.2f}s | p95 Latency = {p95_lat:.2f}s (Rubric Threshold <= 5.0s)")
    print(f"Overall Test Result: {'ALL 10 PUBLIC CASES PASSED 100% PERFECTLY!' if all_passed else 'TEST SUITE FAILED'}")
    print("----------------------------------------------------------------")
    if not all_passed:
        sys.exit(1)
    return all_passed


if __name__ == "__main__":
    run_all_tests()
