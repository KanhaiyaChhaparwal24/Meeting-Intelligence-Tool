from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import gspread
from gspread.utils import rowcol_to_a1
from oauth2client.service_account import ServiceAccountCredentials


SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

SPREADSHEET_NAME = "Meeting Intelligence"
LOGS_WORKSHEET = "Logs"
MEETINGS_WORKSHEET = "Meetings"
TEAM_WORKSHEET = "Team Directory"

# Email sending UI columns (used by the Google Sheets Apps Script)
_SEND_HEADERS = ["Email", "Send?", "Sent At", "Send Status"]
_BASE_HEADERS = [
    "Timestamp",
    "Meeting_ID",
    "Summary",
    "Task",
    "Owner",
    "Deadline",
    "Priority",
    "Decision",
    "Open Question",
]


def _ensure_send_columns(ws: gspread.Worksheet) -> tuple[int, int]:
    """Ensure send-related columns exist and return (send_col, sent_at_col) 1-based."""

    header = [str(x or "").strip() for x in (ws.row_values(1) or [])]

    if not header:
        header = _BASE_HEADERS + list(_SEND_HEADERS)
        ws.update("A1", [header], value_input_option="RAW")
    else:
        changed = False
        for col_name in _SEND_HEADERS:
            if col_name not in header:
                header.append(col_name)
                changed = True
        if changed:
            ws.update("A1", [header], value_input_option="RAW")

    send_col = header.index("Send?") + 1
    sent_at_col = header.index("Sent At") + 1
    return send_col, sent_at_col


def _apply_send_ui_to_new_rows(
    ws: gspread.Worksheet,
    *,
    start_row: int,
    end_row: int,
    send_col: int,
    sent_at_col: int,
) -> None:
    """Apply checkbox + timestamp formatting to newly appended rows.

    Non-fatal: if formatting/validation fails, rows are still appended.
    """

    if end_row < start_row:
        return

    try:
        # 1) Ensure Send? shows as checkboxes for the new rows
        ws.spreadsheet.batch_update(
            {
                "requests": [
                    {
                        "setDataValidation": {
                            "range": {
                                "sheetId": ws.id,
                                "startRowIndex": start_row - 1,
                                "endRowIndex": end_row,
                                "startColumnIndex": send_col - 1,
                                "endColumnIndex": send_col,
                            },
                            "rule": {
                                "condition": {"type": "BOOLEAN"},
                                "showCustomUi": True,
                            },
                        }
                    },
                    {
                        "repeatCell": {
                            "range": {
                                "sheetId": ws.id,
                                "startRowIndex": start_row - 1,
                                "endRowIndex": end_row,
                                "startColumnIndex": sent_at_col - 1,
                                "endColumnIndex": sent_at_col,
                            },
                            "cell": {
                                "userEnteredFormat": {
                                    "numberFormat": {
                                        "type": "DATE_TIME",
                                        "pattern": "yyyy-mm-dd hh:mm:ss",
                                    }
                                }
                            },
                            "fields": "userEnteredFormat.numberFormat",
                        }
                    },
                ]
            }
        )

        # 2) Default new Send? cells to FALSE (unchecked)
        a1_start = rowcol_to_a1(start_row, send_col)
        a1_end = rowcol_to_a1(end_row, send_col)
        ws.update(
            f"{a1_start}:{a1_end}",
            [[False] for _ in range(end_row - start_row + 1)],
            value_input_option="RAW",
        )
    except Exception:
        return


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _credentials_path() -> Path:
    return _repo_root() / "credentials.json"


def get_client() -> gspread.Client:
    """Return an authorized gspread client.

    Uses a Google service account JSON file located at repo root: credentials.json
    """

    creds_path = _credentials_path()
    if not creds_path.exists():
        raise RuntimeError(
            f"Google Sheets credentials file not found: {creds_path}. "
            "Place your service account credentials.json in the project root."
        )

    credentials = ServiceAccountCredentials.from_json_keyfile_name(str(creds_path), SCOPES)
    return gspread.authorize(credentials)


def _open_spreadsheet(client: gspread.Client) -> gspread.Spreadsheet:
    try:
        return client.open(SPREADSHEET_NAME)
    except gspread.SpreadsheetNotFound as e:
        raise RuntimeError(
            f"Google Sheet not found: '{SPREADSHEET_NAME}'. "
            "Create it in Google Drive and share it with your service account email."
        ) from e


def _join_pipe(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return " | ".join(str(x).strip() for x in value if str(x).strip())
    return str(value).strip()


def append_logs(data: Dict[str, Any]) -> None:
    """Append meeting results into the Google Sheet.

    Appends one row per action item to worksheet 'Logs' in spreadsheet 'Meeting Intelligence'.

    Columns:
    Timestamp | Meeting_ID | Summary | Task | Owner | Deadline | Priority | Decision | Open Question

    - decisions are joined with " | "
    - open_questions are joined with " | "
    """

    client = get_client()
    sheet = _open_spreadsheet(client)

    try:
        ws = sheet.worksheet(LOGS_WORKSHEET)
    except gspread.WorksheetNotFound as e:
        raise RuntimeError(
            f"Worksheet not found: '{LOGS_WORKSHEET}' in '{SPREADSHEET_NAME}'. "
            "Create a worksheet tab named 'Logs'."
        ) from e

    timestamp = datetime.now().isoformat(timespec="seconds")
    meeting_id = str(data.get("meeting_id", "")).strip()
    summary = str(data.get("summary", "")).strip()

    decisions_joined = _join_pipe(data.get("decisions"))
    questions_joined = _join_pipe(data.get("open_questions"))

    action_items = data.get("action_items", [])
    if not isinstance(action_items, list):
        action_items = []

    rows: list[list[str]] = []
    if action_items:
        for item in action_items:
            item = item if isinstance(item, dict) else {}
            task = str(item.get("task", "")).strip()
            owner = str(item.get("owner", "Unassigned")).strip() or "Unassigned"
            deadline = str(item.get("deadline", "")).strip()
            priority = str(item.get("priority", "Low")).strip() or "Low"

            # Write meeting-level fields on every row so nothing is blank.
            # We then merge these cells vertically for readability.
            rows.append(
                [
                    timestamp,
                    meeting_id,
                    summary,
                    task,
                    owner,
                    deadline,
                    priority,
                    decisions_joined,
                    questions_joined,
                ]
            )
    else:
        rows.append(
            [
                timestamp,
                meeting_id,
                summary,
                "",
                "Unassigned",
                "",
                "Low",
                decisions_joined,
                questions_joined,
            ]
        )

    send_col, sent_at_col = _ensure_send_columns(ws)

    # Figure out where these rows will be appended so we can merge cells.
    try:
        existing_rows = len(ws.col_values(1))
    except Exception:
        existing_rows = 0
    start_row = existing_rows + 1

    try:
        ws.append_rows(rows, value_input_option="USER_ENTERED")
    except Exception as e:
        raise RuntimeError("Failed to append rows to Google Sheets.") from e

    end_row = start_row + len(rows) - 1

    _apply_send_ui_to_new_rows(ws, start_row=start_row, end_row=end_row, send_col=send_col, sent_at_col=sent_at_col)

    # Merge meeting-level columns so Summary/Decision/Open Question appear once.
    # This keeps the data intact (still one row per action item) but improves readability.
    if len(rows) > 1 and end_row > start_row:
        for col in ("C", "H", "I"):
            try:
                ws.merge_cells(f"{col}{start_row}:{col}{end_row}")
            except Exception:
                # Non-fatal: if merging fails, the values will simply be repeated.
                pass


def append_meeting_rollup(data: Dict[str, Any]) -> None:
    """Append a single 'clubbed' row per meeting into worksheet 'Meetings'.

    Columns:
    Timestamp | Meeting_ID | Summary | Action Items | Decision | Open Question

    Action Items cell is multi-line (one bullet per item).
    """

    client = get_client()
    sheet = _open_spreadsheet(client)

    try:
        ws = sheet.worksheet(MEETINGS_WORKSHEET)
    except gspread.WorksheetNotFound as e:
        raise RuntimeError(
            f"Worksheet not found: '{MEETINGS_WORKSHEET}' in '{SPREADSHEET_NAME}'. "
            "Create a worksheet tab named 'Meetings' to get a one-row-per-meeting view."
        ) from e

    timestamp = datetime.now().isoformat(timespec="seconds")
    meeting_id = str(data.get("meeting_id", "")).strip()
    summary = str(data.get("summary", "")).strip()

    decisions_joined = _join_pipe(data.get("decisions"))
    questions_joined = _join_pipe(data.get("open_questions"))

    action_items = data.get("action_items", [])
    if not isinstance(action_items, list):
        action_items = []

    lines: list[str] = []
    for item in action_items:
        item = item if isinstance(item, dict) else {}
        task = str(item.get("task", "")).strip()
        owner = str(item.get("owner", "Unassigned")).strip() or "Unassigned"
        deadline = str(item.get("deadline", "")).strip() or "-"
        priority = str(item.get("priority", "Low")).strip() or "Low"
        if not task:
            continue
        lines.append(f"- {owner}: {task} (Deadline: {deadline}, Priority: {priority})")

    action_items_cell = "\n".join(lines)

    row = [timestamp, meeting_id, summary, action_items_cell, decisions_joined, questions_joined]

    try:
        ws.append_row(row, value_input_option="USER_ENTERED")
    except Exception as e:
        raise RuntimeError("Failed to append roll-up row to Google Sheets.") from e


def _extract_email(value: str) -> str:
    v = (value or "").strip()
    if not v:
        return ""

    # Accept formats like:
    # - david@test.com
    # - [david@test.com](mailto:david@test.com)
    # - mailto:david@test.com
    lower = v.lower()
    if "mailto:" in lower:
        idx = lower.find("mailto:")
        v2 = v[idx + len("mailto:") :]
        # remove trailing ')' if present
        v2 = v2.strip().rstrip(")").strip()
        return v2

    if "](" in v and v.endswith(")"):
        # Markdown link; prefer inside parentheses if it looks like an email
        inside = v.split("](", 1)[1][:-1]
        if "mailto:" in inside.lower():
            return _extract_email(inside)

    return v


def load_team_directory() -> Dict[str, str]:
    """Load Name->Email mapping from worksheet 'Team Directory'.

    Returns a case-insensitive mapping (keys are lowercased).
    """

    client = get_client()
    sheet = _open_spreadsheet(client)

    try:
        ws = sheet.worksheet(TEAM_WORKSHEET)
    except gspread.WorksheetNotFound as e:
        raise RuntimeError(
            f"Worksheet not found: '{TEAM_WORKSHEET}' in '{SPREADSHEET_NAME}'. "
            "Create a worksheet tab named 'Team Directory' with columns: Name, Email."
        ) from e

    try:
        records = ws.get_all_records()
    except Exception as e:
        raise RuntimeError("Failed to read Team Directory from Google Sheets.") from e

    mapping: Dict[str, str] = {}
    for row in records:
        if not isinstance(row, dict):
            continue

        name = str(row.get("Name", "")).strip()
        email_raw = str(row.get("Email", "")).strip()
        email = _extract_email(email_raw)

        if not name or not email:
            continue

        mapping[name.lower()] = email

    return mapping
