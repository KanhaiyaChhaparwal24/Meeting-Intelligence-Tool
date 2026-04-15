from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from typing import Any, Dict, Iterable, Optional


SMTP_HOST = "smtp.gmail.com"
SMTP_PORT_SSL = 465


def _get_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def check_email_config() -> None:
    """Validate required environment variables for Gmail SMTP are present."""

    _get_env("EMAIL_ADDRESS")
    _get_env("EMAIL_APP_PASSWORD")


def send_email(to_email: str, subject: str, body: str) -> None:
    """Send a single email via Gmail SMTP over SSL.

    Requires environment variables:
    - EMAIL_ADDRESS
    - EMAIL_APP_PASSWORD
    """

    from_email = _get_env("EMAIL_ADDRESS")
    app_password = _get_env("EMAIL_APP_PASSWORD")

    msg = EmailMessage()
    msg["From"] = from_email
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)

    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT_SSL) as server:
        server.login(from_email, app_password)
        server.send_message(msg)


def _format_deadline(value: Any) -> str:
    deadline = str(value or "").strip()
    return deadline if deadline else "(no deadline)"


def send_all_emails(
    action_items: Iterable[Dict[str, Any]],
    mapping: Dict[str, str],
    *,
    subject: str = "Meeting Action Item",
) -> None:
    """Send one email per action item.

    - If owner email is missing: skips safely.
    - If an email fails: prints the error and continues.
    """

    sent = 0
    skipped = 0
    failed = 0

    for item in action_items:
        item = item if isinstance(item, dict) else {}

        owner = str(item.get("owner", "")).strip().lower()
        to_email = mapping.get(owner) or str(item.get("email") or "").strip()

        if not owner or not to_email:
            skipped += 1
            continue

        task = str(item.get("task", "")).strip()
        deadline = _format_deadline(item.get("deadline"))
        priority = str(item.get("priority", "")).strip() or "Medium"

        body = "\n".join(
            [
                f"Hello {item.get('owner', '').strip() or 'there'},",
                "",
                "You have a new meeting action item:",
                "",
                f"Task: {task}",
                f"Deadline: {deadline}",
                f"Priority: {priority}",
                "",
                "Regards,",
                "Meeting Intelligence Tool",
                "",
            ]
        )

        try:
            send_email(to_email=to_email, subject=subject, body=body)
            sent += 1
            print(f"Sent to {to_email}: {task}")
        except Exception as e:
            failed += 1
            print(f"ERROR: Failed sending to {to_email} (owner: {owner}).")
            print(str(e))

    print(f"Email sending done. Sent={sent}, Skipped={skipped}, Failed={failed}")
