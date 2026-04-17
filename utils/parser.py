import json
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple


def _strip_code_fences(text: str) -> str:
    # Handles outputs like:
    # ```json
    # {...}
    # ```
    fenced = re.sub(r"^\s*```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
    fenced = re.sub(r"\s*```\s*$", "", fenced.strip())
    return fenced.strip()


def _extract_first_json_object(text: str) -> Optional[str]:
    """Best-effort extraction of the first top-level JSON object from text."""
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape = False

    for i in range(start, len(text)):
        ch = text[i]

        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue

        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]

    return None


def parse_gemini_json(raw_output: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Parse Gemini output into JSON. Returns (data, error_message)."""
    candidates = [raw_output, _strip_code_fences(raw_output)]

    for candidate in candidates:
        candidate = candidate.strip()
        if not candidate:
            continue
        try:
            return json.loads(candidate), None
        except Exception:
            pass

        extracted = _extract_first_json_object(candidate)
        if extracted:
            try:
                return json.loads(extracted), None
            except Exception as e:
                return None, f"Failed to parse extracted JSON: {e}"

    return None, "Failed to parse JSON from model output"


def _normalize_priority(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"high", "h"}:
        return "High"
    if text in {"medium", "med", "m"}:
        return "Medium"
    if text in {"low", "l"}:
        return "Low"
    # Default if missing/unknown
    return "Low"


def _normalize_deadline(text: Any, *, today: Optional[datetime] = None) -> str:
    """Normalize deadline into ISO date (YYYY-MM-DD) when possible.

    - Weekday names like "Friday" -> next occurrence date
    - "None" -> "" (empty)
    - Otherwise returns the original string trimmed
    """
    raw = str(text or "").strip()
    if not raw:
        return ""

    low = raw.lower()
    if low == "none":
        return ""

    # Already ISO-like YYYY-MM-DD
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        return raw

    weekday_to_index = {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
        "sunday": 6,
    }
    if low in weekday_to_index:
        base = today or datetime.now()
        target = weekday_to_index[low]
        days_ahead = (target - base.weekday()) % 7
        return (base + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

    return raw


def _priority_rank(priority: str) -> int:
    p = str(priority or "").strip().lower()
    if p == "high":
        return 3
    if p == "medium":
        return 2
    if p == "low":
        return 1
    return 0


def _improve_priority(task: str, deadline: str, current_priority: str) -> str:
    """Upgrade priority using a lightweight rule layer.

    Rules (quick win):
    - If task mentions "bug" => High
    - If a (normalized) deadline exists => High
    - Else keep current or default to Medium

    Never downgrades High/Medium/Low.
    """
    task_low = (task or "").lower()

    suggested = "Medium"
    if "bug" in task_low:
        suggested = "High"
    elif deadline:
        suggested = "High"

    current = _normalize_priority(current_priority)
    return suggested if _priority_rank(suggested) > _priority_rank(current) else current


def normalize_meeting_json(data: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """Normalize expected meeting JSON shape.

    Returns (normalized_data, warnings).
    """
    warnings: List[str] = []
    normalized: Dict[str, Any] = {}

    summary = data.get("summary", "")
    if not isinstance(summary, str):
        warnings.append("summary was not a string; coerced to string")
    normalized["summary"] = str(summary).strip()

    action_items = data.get("action_items", [])
    if not isinstance(action_items, list):
        warnings.append("action_items was not a list; replaced with []")
        action_items = []

    normalized_items: List[Dict[str, str]] = []
    for idx, item in enumerate(action_items):
        if not isinstance(item, dict):
            warnings.append(f"action_items[{idx}] was not an object; skipped")
            continue

        task = str(item.get("task", "")).strip()
        if not task:
            warnings.append(f"action_items[{idx}].task was empty")

        owner = str(item.get("owner", "Unassigned")).strip() or "Unassigned"
        deadline_raw = str(item.get("deadline", "None")).strip() or "None"
        deadline = _normalize_deadline(deadline_raw)

        priority_raw = item.get("priority")
        priority = _improve_priority(task, deadline, str(priority_raw or ""))

        normalized_items.append(
            {
                "task": task,
                "owner": owner,
                "deadline": deadline,
                "priority": priority,
            }
        )

    normalized["action_items"] = normalized_items

    decisions = data.get("decisions", [])
    if isinstance(decisions, str):
        decisions = [decisions]
        warnings.append("decisions was a string; wrapped into a list")
    if not isinstance(decisions, list):
        warnings.append("decisions was not a list; replaced with []")
        decisions = []
    normalized["decisions"] = [str(x).strip() for x in decisions if str(x).strip()]

    open_questions = data.get("open_questions", [])
    if isinstance(open_questions, str):
        open_questions = [open_questions]
        warnings.append("open_questions was a string; wrapped into a list")
    if not isinstance(open_questions, list):
        warnings.append("open_questions was not a list; replaced with []")
        open_questions = []
    normalized["open_questions"] = [str(x).strip() for x in open_questions if str(x).strip()]

    # Optional: keep a simple detected_language field if present.
    detected_language = data.get("detected_language")
    if detected_language is not None:
        if isinstance(detected_language, str):
            value = detected_language.strip()
            if value in {"Hindi", "English"}:
                normalized["detected_language"] = value
            else:
                warnings.append("detected_language had unexpected value; ignored")
        else:
            warnings.append("detected_language was not a string; ignored")

    # Detect unexpected keys (useful in debug)
    expected = {"summary", "action_items", "decisions", "open_questions", "detected_language"}
    extra_keys = sorted([k for k in data.keys() if k not in expected])
    if extra_keys:
        warnings.append(f"extra keys present: {', '.join(extra_keys)}")

    return normalized, warnings
