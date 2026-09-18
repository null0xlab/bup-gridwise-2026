import json
import logging
import re
from typing import List, Dict, Any
import requests
from config import OPENROUTER_API_KEY, LLM_BASE_URL, LLM_MODEL


logger = logging.getLogger("gridwise.llm")


SYSTEM_PROMPT = """You are an expert energy management AI assistant for the BUP Smart Campus Energy System.
Your job is to read 1 to 3 natural-language operator notes and convert each note into a strictly formatted machine-checkable directive.

Supported directive types and their required structured_adjustment shapes:
1. "solar_reduction":
   - Used when rooftop solar/PV generation is reduced due to cleaning, clouds, inverter work, maintenance, etc.
   - structured_adjustment: {"hours": [int, ...], "factor": float}
   - NOTE ON FACTOR: factor is the USABLE FRACTION REMAINING (0.0 to 1.0).
     Example: "usable solar roughly 25% of forecast" -> factor = 0.25
     Example: "drop to about 20%" -> factor = 0.2
     Example: "80% reduction" means 20% remains -> factor = 0.2
     Example: "about half of forecast" -> factor = 0.5
2. "minimum_battery_reserve":
   - Used when the battery must maintain an emergency reserve energy level during certain hours.
   - structured_adjustment: {"hours": [int, ...], "minimum_energy_kwh": float}
   - If stated as a percentage of battery capacity (e.g. 50%), calculate: capacity_kwh * (percentage / 100.0).
     Example: 50% reserve for 200 kWh capacity battery -> minimum_energy_kwh = 100.0.
3. "no_charge_window":
   - Used when battery charging is prohibited or charger is isolated/disabled/under maintenance.
   - structured_adjustment: {"hours": [int, ...]}
4. "no_discharge_window":
   - Used when battery discharging is prohibited, relay testing, protection testing, etc.
   - structured_adjustment: {"hours": [int, ...]}
5. "max_grid_window":
   - Used when campus grid import/intake/power is capped or limited by transformer/substation/feeder.
   - structured_adjustment: {"hours": [int, ...], "max_grid_kwh": float}
6. "no_op":
   - Used for any irrelevant notes: campus cafeteria menu, library hours, sports office notices, club announcements, events tomorrow or next week, unrelated facility notices.
   - structured_adjustment: null
   - applies: false (NOTE: no_op is the ONLY directive where applies is false. For all other directives, applies MUST be true).

TIME WINDOW CONVENTION (CRITICAL):
- Use 24-hour integers (0 to 23).
- Whole-hour intervals: start hour is INCLUDED, end hour is EXCLUDED.
  "noon until 2 PM" -> [12, 13]
  "1 PM to 3 PM" -> [13, 14]
  "2 AM until 5 AM" -> [2, 3, 4]
  "2 PM and 4 PM" -> [14, 15]
  "6 PM until 9 PM" -> [18, 19, 20]
  "6 PM until 10 PM" -> [18, 19, 20, 21]
  "7 PM until 9 PM" -> [19, 20]
  "7 PM until 10 PM" -> [19, 20, 21]
  "11 AM and 2 PM" -> [11, 12, 13]
  "11 AM until 1 PM" -> [11, 12]
  "5 PM until 7 PM" -> [17, 18]
  "13:00 and 15:00" -> [13, 14]
  "18:00 to 21:00" -> [18, 19, 20]

OUTPUT FORMAT:
Return a JSON array containing exactly one entry for each operator note in exact note_index order (0 to N-1).
Do not return markdown fences or explanation outside the JSON.
Example output:
[
  {
    "note_index": 0,
    "applies": true,
    "directive_type": "solar_reduction",
    "structured_adjustment": {"hours": [12, 13], "factor": 0.25},
    "explanation": "Solar availability is reduced to 25% during the panel-cleaning window."
  },
  {
    "note_index": 1,
    "applies": false,
    "directive_type": "no_op",
    "structured_adjustment": null,
    "explanation": "This note does not affect today's 24-hour energy schedule."
  }
]
"""


def extract_hours_from_text(text: str) -> List[int]:
    """Helper for fallback regex parser to extract time windows."""
    # Look for patterns like "from X until Y", "between X and Y", "X to Y"
    # Matches: noon, midnight, 1 PM, 2:00 PM, 14:00, etc.
    def parse_time_str(s: str) -> int:
        s = s.strip().lower()
        if "noon" in s or "12 pm" in s:
            return 12
        if "midnight" in s or "12 am" in s:
            return 0
        m = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", s)
        if not m:
            return 0
        hr = int(m.group(1))
        meridiem = m.group(3)
        if meridiem == "pm" and hr != 12:
            hr += 12
        elif meridiem == "am" and hr == 12:
            hr = 0
        return hr

    # Common range patterns
    range_patterns = [
        r"(?:from|between)\s+([a-zA-Z0-9:\s]+?)\s+(?:until|to|and)\s+([a-zA-Z0-9:\s]+?)(?:\.|\s+for|\s+while|\s+during|\s+because|$)",
        r"(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\s*(?:-|–|until|to)\s*(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)"
    ]
    for pat in range_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            start_str, end_str = m.group(1), m.group(2)
            try:
                start_h = parse_time_str(start_str)
                end_h = parse_time_str(end_str)
                if 0 <= start_h < end_h <= 24:
                    return list(range(start_h, end_h))
            except Exception:
                pass
    return []


def fallback_rule_based_interpretation(operator_notes: List[str], battery_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Deterministic fallback interpreter if LLM is unreachable or errors."""
    capacity = float(battery_data.get("capacity_kwh", 200.0))
    results = []

    for idx, note in enumerate(operator_notes):
        lower = note.lower()

        # Check for distractor keywords
        distractor_keywords = ["sports", "cafeteria", "menu", "library", "book", "registration", "student affairs", "club", "seminar", "next week", "next month", "tomorrow"]
        if any(dk in lower for dk in distractor_keywords) and not any(k in lower for k in ["solar", "battery", "charger", "grid import", "kwh"]):
            results.append({
                "note_index": idx,
                "applies": False,
                "directive_type": "no_op",
                "structured_adjustment": None,
                "explanation": "Unrelated campus announcement."
            })
            continue

        hours = extract_hours_from_text(note)

        # Solar reduction
        if any(w in lower for w in ["solar", "pv", "panel", "sun"]):
            factor = 0.5
            if "25%" in lower or "one-quarter" in lower or "one quarter" in lower:
                factor = 0.25
            elif "20%" in lower or "one-fifth" in lower or "one fifth" in lower:
                factor = 0.2
            elif "80% reduction" in lower:
                factor = 0.2
            elif "75% reduction" in lower:
                factor = 0.25
            elif "half" in lower or "50%" in lower:
                factor = 0.5
            elif "reduction" in lower:
                m = re.search(r"(\d+)%", lower)
                if m:
                    pct = float(m.group(1))
                    factor = max(0.0, min(1.0, 1.0 - (pct / 100.0)))

            results.append({
                "note_index": idx,
                "applies": True,
                "directive_type": "solar_reduction",
                "structured_adjustment": {"hours": hours, "factor": factor},
                "explanation": f"Solar reduced during maintenance window {hours}."
            })

        # Reserve
        elif any(w in lower for w in ["reserve", "stored in the battery", "remain in the battery", "in the battery", "battery energy", "emergency"]):
            min_kwh = float(battery_data.get("minimum_energy_kwh", 40.0))
            m_pct = re.search(r"(\d+)\s*%", lower)
            m_kwh = re.search(r"(\d+(?:\.\d+)?)\s*kwh", lower)
            if m_pct:
                min_kwh = capacity * (float(m_pct.group(1)) / 100.0)
            elif m_kwh:
                min_kwh = float(m_kwh.group(1))

            results.append({
                "note_index": idx,
                "applies": True,
                "directive_type": "minimum_battery_reserve",
                "structured_adjustment": {"hours": hours, "minimum_energy_kwh": min_kwh},
                "explanation": f"Maintain battery reserve of {min_kwh} kWh."
            })

        # No charge
        elif any(w in lower for w in ["do not charge", "charging will be unavailable", "charging circuit", "battery charger will be isolated", "charging is disabled", "not charge"]):
            results.append({
                "note_index": idx,
                "applies": True,
                "directive_type": "no_charge_window",
                "structured_adjustment": {"hours": hours},
                "explanation": "Battery charging is disabled."
            })

        # No discharge
        elif any(w in lower for w in ["do not discharge", "must not discharge", "discharging is disabled"]):
            results.append({
                "note_index": idx,
                "applies": True,
                "directive_type": "no_discharge_window",
                "structured_adjustment": {"hours": hours},
                "explanation": "Battery discharging is disabled."
            })

        # Max grid
        elif any(w in lower for w in ["grid import", "grid intake", "transformer limit", "feeder"]):
            m_kwh = re.search(r"(\d+(?:\.\d+)?)\s*kwh", lower)
            mg = float(m_kwh.group(1)) if m_kwh else 150.0
            results.append({
                "note_index": idx,
                "applies": True,
                "directive_type": "max_grid_window",
                "structured_adjustment": {"hours": hours, "max_grid_kwh": mg},
                "explanation": f"Grid import limited to {mg} kWh."
            })

        else:
            results.append({
                "note_index": idx,
                "applies": False,
                "directive_type": "no_op",
                "structured_adjustment": None,
                "explanation": "Note does not affect today's energy schedule."
            })

    return results


def interpret_operator_notes(operator_notes: List[str], battery_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Interprets operator notes using LLM generative model as required by challenge.
    Falls back gracefully if LLM provider fails.
    """
    user_prompt = f"""Battery Specifications:
- Capacity: {battery_data.get('capacity_kwh')} kWh
- Initial Energy: {battery_data.get('initial_energy_kwh')} kWh
- Minimum Energy Reserve: {battery_data.get('minimum_energy_kwh')} kWh

Operator Notes:
"""
    for idx, note in enumerate(operator_notes):
        user_prompt += f"Note {idx}: \"{note}\"\n"

    user_prompt += "\nOutput the JSON array of interpretations now:"

    # Call LLM
    if OPENROUTER_API_KEY:
        try:
            headers = {
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": LLM_MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 0.0,
                "max_tokens": 400
            }
            resp = requests.post(
                f"{LLM_BASE_URL.rstrip('/')}/chat/completions",
                headers=headers,
                json=payload,
                timeout=12.0
            )
            if resp.status_code == 200:
                content = resp.json()["choices"][0]["message"]["content"]
                # Parse JSON array from content
                m = re.search(r"\[\s*\{.*\}\s*\]", content, re.DOTALL)
                if m:
                    parsed = json.loads(m.group(0))
                    if isinstance(parsed, list) and len(parsed) > 0:
                        return parsed
                else:
                    logger.warning("LLM response did not contain a JSON array; using fallback interpreter.")
            else:
                logger.warning("LLM request returned HTTP %s; using fallback interpreter.", resp.status_code)
        except Exception as e:
            logger.warning("LLM request failed; using fallback interpreter: %s", e)

    # Resilient fallback
    return fallback_rule_based_interpretation(operator_notes, battery_data)
