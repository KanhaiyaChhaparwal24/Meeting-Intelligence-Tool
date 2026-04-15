from __future__ import annotations

from typing import Dict

import pandas as pd


def load_team_directory(file_path: str = "meeting_log.xlsx") -> Dict[str, str]:
    """Load name -> email mapping from the Excel sheet "Team Directory".

    Keys are normalized to lowercase for matching.
    """
    try:
        df = pd.read_excel(file_path, sheet_name="Team Directory")
    except Exception:
        return {}

    if df is None or df.empty:
        return {}

    # Normalize expected columns.
    if "Name" not in df.columns or "Email" not in df.columns:
        return {}

    mapping: Dict[str, str] = {}
    for _, row in df.iterrows():
        name_cell = row.get("Name")
        email_cell = row.get("Email")

        if pd.isna(name_cell) or pd.isna(email_cell):
            continue

        name = str(name_cell).strip().lower()
        email = str(email_cell).strip()

        if not name or not email:
            continue

        mapping[name] = email

    return mapping