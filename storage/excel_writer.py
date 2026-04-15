from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd


LOGS_SHEET = "Logs"
TEAM_SHEET = "Team Directory"

LOGS_COLUMNS = [
    "Meeting_ID",
    "Timestamp",
    "Summary",
    "Task",
    "Owner",
    "Deadline",
    "Priority",
    "Decision",
    "Open Question",
]

TEAM_COLUMNS = ["Name", "Email"]


def _safe_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str):
        v = value.strip()
        return [v] if v else []
    return [str(value).strip()]


def _ensure_workbook(excel_path: Path) -> None:
    if excel_path.exists():
        return

    empty_logs = pd.DataFrame(columns=LOGS_COLUMNS)
    empty_team = pd.DataFrame(columns=TEAM_COLUMNS)

    with pd.ExcelWriter(excel_path, engine="openpyxl", mode="w") as writer:
        empty_logs.to_excel(writer, sheet_name=LOGS_SHEET, index=False)
        empty_team.to_excel(writer, sheet_name=TEAM_SHEET, index=False)


def append_meeting_log(structured: Dict[str, Any], *, excel_path: str = "meeting_log.xlsx") -> Path:
    """Append structured meeting data into a local Excel file."""
    path = Path(excel_path)
    _ensure_workbook(path)

    # Read existing sheets (best-effort)
    try:
        existing_logs = pd.read_excel(path, sheet_name=LOGS_SHEET)
    except Exception:
        existing_logs = pd.DataFrame(columns=LOGS_COLUMNS)

    # Ensure we have the expected columns even if the workbook was created
    # before new columns (like Meeting_ID) were introduced.
    if list(existing_logs.columns) != LOGS_COLUMNS:
        existing_logs = existing_logs.reindex(columns=LOGS_COLUMNS)

    if "Meeting_ID" in existing_logs.columns:
        existing_logs["Meeting_ID"] = existing_logs["Meeting_ID"].fillna("")

    try:
        existing_team = pd.read_excel(path, sheet_name=TEAM_SHEET)
        if list(existing_team.columns) != TEAM_COLUMNS:
            existing_team = existing_team.reindex(columns=TEAM_COLUMNS)
    except Exception:
        existing_team = pd.DataFrame(columns=TEAM_COLUMNS)

    timestamp = datetime.now().isoformat(timespec="seconds")
    meeting_id = str(structured.get("meeting_id", "")).strip()

    summary = str(structured.get("summary", "")).strip()
    action_items = structured.get("action_items", [])
    if not isinstance(action_items, list):
        action_items = []

    decisions = _safe_list(structured.get("decisions"))
    open_questions = _safe_list(structured.get("open_questions"))

    decisions_joined = " | ".join(decisions)
    questions_joined = " | ".join(open_questions)

    rows: List[Dict[str, Any]] = []

    if action_items:
        for item in action_items:
            item = item if isinstance(item, dict) else {}
            rows.append(
                {
                    "Meeting_ID": meeting_id,
                    "Timestamp": timestamp,
                    "Summary": summary,
                    "Task": str(item.get("task", "")).strip(),
                    "Owner": str(item.get("owner", "Unassigned")).strip() or "Unassigned",
                    "Deadline": str(item.get("deadline", "")).strip(),
                    "Priority": str(item.get("priority", "Low")).strip() or "Low",
                    "Decision": decisions_joined,
                    "Open Question": questions_joined,
                }
            )
    else:
        # No action items: still log the meeting summary once.
        rows.append(
            {
                "Meeting_ID": meeting_id,
                "Timestamp": timestamp,
                "Summary": summary,
                "Task": "",
                "Owner": "Unassigned",
                "Deadline": "",
                "Priority": "Low",
                "Decision": decisions_joined,
                "Open Question": questions_joined,
            }
        )

    new_logs = pd.DataFrame(rows, columns=LOGS_COLUMNS)
    combined = pd.concat([existing_logs, new_logs], ignore_index=True)

    # Write back (replace sheets to keep logic simple and reliable).
    try:
        with pd.ExcelWriter(path, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
            combined.to_excel(writer, sheet_name=LOGS_SHEET, index=False)
            existing_team.to_excel(writer, sheet_name=TEAM_SHEET, index=False)
    except PermissionError as e:
        raise RuntimeError(
            f"Permission denied writing '{path.name}'. If it's open in Excel, close it and try again."
        ) from e

    return path
