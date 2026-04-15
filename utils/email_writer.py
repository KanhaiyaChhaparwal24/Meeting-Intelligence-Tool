from __future__ import annotations

import os
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional


def preview_emails(action_items: Iterable[Dict[str, Any]]) -> None:
    print("\n--- EMAIL PREVIEW ---\n")

    shown = 0
    for item in action_items:
        email = item.get("email")
        if not email:
            continue

        shown += 1
        print(f"To: {email}")
        print(f"Task: {item.get('task', '')}")
        print(f"Deadline: {item.get('deadline', '')}")
        print(f"Priority: {item.get('priority', '')}")
        print("-" * 30)

    if shown == 0:
        print("(No mappable owner emails found; nothing to send.)")


def confirm_send() -> bool:
    # Safe default is NO.
    try:
        choice = input("\nSend emails? (yes/no): ")
    except Exception:
        return False
    return choice.strip().lower() == "yes"


def _build_owner_email_files(action_items: Iterable[Dict[str, Any]]) -> Dict[str, str]:
    """Return filename -> file content, one file per owner."""
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    for item in action_items:
        email = item.get("email")
        owner = str(item.get("owner", "")).strip()
        if not email or not owner:
            continue
        grouped[owner].append(item)

    files: Dict[str, str] = {}
    for owner, items in grouped.items():
        # Filename format requested: emails/email_<owner>.txt
        owner_slug = owner.lower().replace(" ", "_")
        filename = os.path.join("emails", f"email_{owner_slug}.txt")

        lines: List[str] = []
        # Using the email from the first item; mapping should be consistent.
        email = str(items[0].get("email") or "").strip()

        lines.append(f"To: {email}")
        lines.append("Subject: Meeting Action Item")
        lines.append("")
        lines.append(f"Hello {owner},")
        lines.append("")
        lines.append("You have new action items from the recent meeting:\n")

        for idx, item in enumerate(items, start=1):
            task = str(item.get("task", "")).strip()
            deadline = str(item.get("deadline", "")).strip()
            priority = str(item.get("priority", "")).strip()

            lines.append(f"{idx}. Task: {task}")
            lines.append(f"   Deadline: {deadline}")
            lines.append(f"   Priority: {priority}")
            lines.append("")

        lines.append("Please take necessary action.")
        lines.append("")
        lines.append("Regards,")
        lines.append("Meeting Intelligence Tool")

        files[filename] = "\n".join(lines).strip() + "\n"

    return files


def write_emails(action_items: Iterable[Dict[str, Any]]) -> None:
    os.makedirs("emails", exist_ok=True)

    files = _build_owner_email_files(action_items)
    for filename, content in files.items():
        with open(filename, "w", encoding="utf-8") as f:
            f.write(content)

    if files:
        print("Email files generated in /emails folder")
    else:
        print("No email files generated (no matching owner emails)")
