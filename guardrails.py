from typing import List, Dict, Any, Optional
from schemas import DirectiveInterpretationEntry


VALID_DIRECTIVE_TYPES = {
    "solar_reduction",
    "minimum_battery_reserve",
    "no_charge_window",
    "no_discharge_window",
    "max_grid_window",
    "no_op"
}


def sanitize_hours(raw_hours: Any) -> List[int]:
    """Sanitize, deduplicate, filter, and sort hours array into unique ints 0..23."""
    if not isinstance(raw_hours, list):
        return []
    valid = set()
    for h in raw_hours:
        try:
            h_int = int(h)
            if 0 <= h_int <= 23:
                valid.add(h_int)
        except (ValueError, TypeError):
            continue
    return sorted(list(valid))


def validate_and_guardrail_interpretations(
    raw_interpretations: List[Dict[str, Any]],
    operator_notes: List[str],
    battery_data: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Deterministically validates, sanitizes, and normalizes raw LLM output against
    GridWise Section 08 Guardrail rules.
    """
    total_notes = len(operator_notes)
    cleaned_entries = []

    # Map raw entries by note_index if possible
    raw_by_index = {}
    for idx, item in enumerate(raw_interpretations):
        note_idx = item.get("note_index", idx)
        if isinstance(note_idx, int) and 0 <= note_idx < total_notes:
            raw_by_index[note_idx] = item
        elif idx < total_notes and idx not in raw_by_index:
            raw_by_index[idx] = item

    capacity_kwh = float(battery_data.get("capacity_kwh", 0.0))

    for note_idx in range(total_notes):
        raw = raw_by_index.get(note_idx, {})
        raw_type = str(raw.get("directive_type", "no_op")).strip().lower()

        if raw_type not in VALID_DIRECTIVE_TYPES:
            raw_type = "no_op"

        explanation = str(raw.get("explanation", "")).strip()
        if not explanation:
            explanation = "Interpreted operator note."

        raw_adj = raw.get("structured_adjustment")

        if raw_type == "no_op" or raw_adj is None:
            cleaned_entries.append({
                "note_index": note_idx,
                "applies": False,
                "directive_type": "no_op",
                "structured_adjustment": None,
                "explanation": explanation or "This note does not affect today's energy schedule."
            })
            continue

        # Active directive
        hours = sanitize_hours(raw_adj.get("hours", []))
        if not hours:
            # If an active directive has no valid hours, convert to no_op safely
            cleaned_entries.append({
                "note_index": note_idx,
                "applies": False,
                "directive_type": "no_op",
                "structured_adjustment": None,
                "explanation": explanation
            })
            continue

        if raw_type == "solar_reduction":
            factor = raw_adj.get("factor", 1.0)
            try:
                factor = float(factor)
            except (ValueError, TypeError):
                factor = 1.0
            # If factor > 1.0, could be given as percentage e.g. 25 or 80
            if factor > 1.0:
                factor = factor / 100.0
            factor = max(0.0, min(1.0, factor))

            cleaned_entries.append({
                "note_index": note_idx,
                "applies": True,
                "directive_type": "solar_reduction",
                "structured_adjustment": {
                    "hours": hours,
                    "factor": round(factor, 4)
                },
                "explanation": explanation
            })

        elif raw_type == "minimum_battery_reserve":
            min_kwh = raw_adj.get("minimum_energy_kwh")
            if min_kwh is None:
                # Check if percentage was supplied
                pct = raw_adj.get("percentage") or raw_adj.get("percent")
                if pct is not None:
                    try:
                        p_val = float(pct)
                        if p_val > 1.0:
                            p_val = p_val / 100.0
                        min_kwh = capacity_kwh * p_val
                    except Exception:
                        min_kwh = float(battery_data.get("minimum_energy_kwh", 0.0))
                else:
                    min_kwh = float(battery_data.get("minimum_energy_kwh", 0.0))
            else:
                try:
                    min_kwh = float(min_kwh)
                except (ValueError, TypeError):
                    min_kwh = float(battery_data.get("minimum_energy_kwh", 0.0))

            # Clamp reserve between 0 and capacity
            min_kwh = max(0.0, min(capacity_kwh, min_kwh))

            cleaned_entries.append({
                "note_index": note_idx,
                "applies": True,
                "directive_type": "minimum_battery_reserve",
                "structured_adjustment": {
                    "hours": hours,
                    "minimum_energy_kwh": round(min_kwh, 2)
                },
                "explanation": explanation
            })

        elif raw_type == "no_charge_window":
            cleaned_entries.append({
                "note_index": note_idx,
                "applies": True,
                "directive_type": "no_charge_window",
                "structured_adjustment": {
                    "hours": hours
                },
                "explanation": explanation
            })

        elif raw_type == "no_discharge_window":
            cleaned_entries.append({
                "note_index": note_idx,
                "applies": True,
                "directive_type": "no_discharge_window",
                "structured_adjustment": {
                    "hours": hours
                },
                "explanation": explanation
            })

        elif raw_type == "max_grid_window":
            mg = raw_adj.get("max_grid_kwh", 0.0)
            try:
                mg = float(mg)
            except (ValueError, TypeError):
                mg = 0.0
            mg = max(0.0, mg)

            cleaned_entries.append({
                "note_index": note_idx,
                "applies": True,
                "directive_type": "max_grid_window",
                "structured_adjustment": {
                    "hours": hours,
                    "max_grid_kwh": round(mg, 2)
                },
                "explanation": explanation
            })

    return cleaned_entries
