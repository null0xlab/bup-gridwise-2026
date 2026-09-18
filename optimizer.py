from typing import List, Dict, Any, Tuple
import pulp


def solve_optimization(
    hours_data: List[Dict[str, Any]],
    battery_data: Dict[str, Any],
    valid_directives: List[Dict[str, Any]],
    ignored_count: int = 0
) -> Tuple[List[Dict[str, Any]], float, float, float, str]:
    """
    Optimizes 24-hour campus energy schedule with exact directive integration.
    Guarantees global cost optimality, physics compliance, and end-of-day battery neutrality.
    """
    prob = pulp.LpProblem("GridWise_Optimization", pulp.LpMinimize)

    # 1. Initialize profiles and constraints
    eff_solar = [float(h["solar_kwh"]) for h in hours_data]
    min_reserve = [float(battery_data["minimum_energy_kwh"])] * 24
    max_charge = [float(battery_data["max_charge_kwh_per_hour"])] * 24
    max_discharge = [float(battery_data["max_discharge_kwh_per_hour"])] * 24
    max_grid = [None] * 24

    directive_descriptions = []

    # 2. Apply valid directives deterministically
    for d in valid_directives:
        if not d.get("applies", False):
            continue
        dtype = d.get("directive_type")
        adj = d.get("structured_adjustment") or {}
        hours = adj.get("hours", [])

        if dtype == "solar_reduction":
            factor = float(adj["factor"])
            for h in hours:
                eff_solar[h] = eff_solar[h] * factor
            pct_red = int(round((1.0 - factor) * 100))
            directive_descriptions.append(f"solar reduction of {pct_red}% during hours {hours}")

        elif dtype == "minimum_battery_reserve":
            min_kwh = float(adj["minimum_energy_kwh"])
            for h in hours:
                min_reserve[h] = max(min_reserve[h], min_kwh)
            directive_descriptions.append(f"minimum reserve of {min_kwh} kWh during hours {hours}")

        elif dtype == "no_charge_window":
            for h in hours:
                max_charge[h] = 0.0
            directive_descriptions.append(f"no charging during hours {hours}")

        elif dtype == "no_discharge_window":
            for h in hours:
                max_discharge[h] = 0.0
            directive_descriptions.append(f"no discharging during hours {hours}")

        elif dtype == "max_grid_window":
            mg = float(adj["max_grid_kwh"])
            for h in hours:
                if max_grid[h] is None:
                    max_grid[h] = mg
                else:
                    max_grid[h] = min(max_grid[h], mg)
            directive_descriptions.append(f"grid cap of {mg} kWh during hours {hours}")

    # 3. Decision variables
    capacity = float(battery_data["capacity_kwh"])
    initial_energy = float(battery_data["initial_energy_kwh"])

    G = [pulp.LpVariable(f"G_{h}", lowBound=0, upBound=max_grid[h]) for h in range(24)]
    S_used = [pulp.LpVariable(f"S_{h}", lowBound=0, upBound=eff_solar[h]) for h in range(24)]
    C = [pulp.LpVariable(f"C_{h}", lowBound=0, upBound=max_charge[h]) for h in range(24)]
    D = [pulp.LpVariable(f"D_{h}", lowBound=0, upBound=max_discharge[h]) for h in range(24)]
    E = [pulp.LpVariable(f"E_{h}", lowBound=min_reserve[h], upBound=capacity) for h in range(24)]
    P = pulp.LpVariable("PeakGrid", lowBound=0)

    # 4. Mathematical constraints
    for h in range(24):
        demand = float(hours_data[h]["demand_kwh"])
        # Hourly energy balance: Grid + SolarUsed + Discharge = Demand + Charge
        prob += G[h] + S_used[h] + D[h] - C[h] == demand, f"EnergyBalance_Hour_{h}"
        # Peak grid tracker
        prob += P >= G[h], f"PeakGrid_Bound_Hour_{h}"

        # Battery state evolution: E_h = E_{h-1} + C_h - D_h
        if h == 0:
            prob += E[h] - C[h] + D[h] == initial_energy, "BatteryTransition_Hour_0"
        else:
            prob += E[h] - E[h-1] - C[h] + D[h] == 0, f"BatteryTransition_Hour_{h}"

    # End-of-day battery neutrality
    prob += E[23] == initial_energy, "EndOfDay_BatteryNeutrality"

    # 5. Objective function: Minimize total grid electricity cost
    # Regularizers: 1e-4 * PeakGrid (smooths grid load across equal-tariff hours)
    #              1e-6 * (C + D) (strictly prevents redundant simultaneous charging & discharging)
    cost_expr = pulp.lpSum([float(hours_data[h]["tariff_bdt_per_kwh"]) * G[h] for h in range(24)])
    prob += cost_expr + 1e-4 * P + 1e-6 * pulp.lpSum([C[h] + D[h] for h in range(24)])

    # Solve with CBC
    solver = pulp.PULP_CBC_CMD(msg=False)
    status = prob.solve(solver)
    if pulp.LpStatus[status] != "Optimal":
        raise ValueError(f"Energy optimization problem is infeasible or unbounded: {pulp.LpStatus[status]}")

    # 6. Build hourly plan & post-process
    hourly_plan = []
    for h in range(24):
        c_val = max(0.0, float(C[h].varValue or 0.0))
        d_val = max(0.0, float(D[h].varValue or 0.0))
        s_val = max(0.0, float(S_used[h].varValue or 0.0))
        e_val = float(E[h].varValue or 0.0)

        # Ensure mutual exclusivity of charge and discharge
        if c_val > 1e-4 and d_val > 1e-4:
            net = c_val - d_val
            if net > 0:
                c_val = net
                d_val = 0.0
            else:
                c_val = 0.0
                d_val = -net

        if c_val > 1e-4:
            action = "charge"
            bkwh = round(c_val, 4)
        elif d_val > 1e-4:
            action = "discharge"
            bkwh = round(d_val, 4)
        else:
            action = "idle"
            bkwh = 0.0

        # Exact energy balance recalculation for grid
        demand = float(hours_data[h]["demand_kwh"])
        g_val = max(0.0, demand + (bkwh if action == "charge" else 0.0) - s_val - (bkwh if action == "discharge" else 0.0))

        hourly_plan.append({
            "hour": h,
            "grid_kwh": round(g_val, 4),
            "solar_used_kwh": round(s_val, 4),
            "battery_action": action,
            "battery_kwh": bkwh,
            "battery_energy_after_kwh": round(e_val, 4)
        })

    total_grid = round(sum(item["grid_kwh"] for item in hourly_plan), 2)
    total_cost = round(sum(item["grid_kwh"] * float(hours_data[i]["tariff_bdt_per_kwh"]) for i, item in enumerate(hourly_plan)), 2)
    peak_grid = round(max(item["grid_kwh"] for item in hourly_plan), 2)

    # 7. Generate summary
    summary_parts = []
    if directive_descriptions:
        summary_parts.append(f"Applies active directives: {'; '.join(directive_descriptions)}.")
    if ignored_count > 0:
        summary_parts.append(f"Ignores {ignored_count} unrelated distractor note(s).")
    summary_parts.append("Optimizes battery charging during low-tariff/solar periods and discharges during peak tariff hours while strictly maintaining end-of-day battery neutrality.")
    plan_summary = " ".join(summary_parts)

    return hourly_plan, total_grid, total_cost, peak_grid, plan_summary
