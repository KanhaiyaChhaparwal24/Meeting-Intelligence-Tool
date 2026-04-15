import argparse
import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

from audio.transcriber import transcribe_audio
from llm.gemini_extractor import extract_with_gemini, list_models
from utils.email_writer import confirm_send, preview_emails
from utils.parser import normalize_meeting_json, parse_gemini_json


def _load_hf_sample_transcript() -> str:
    # Required dataset usage for text pipeline testing.
    from datasets import load_dataset

    dataset = load_dataset("edinburghcstr/ami", "ihm")
    transcript = dataset["train"][0]["text"]
    return str(transcript)


def _shrink_transcript(transcript: str, max_chars: int) -> str:
    """Shrink transcript to <= max_chars while keeping start + end context."""

    t = str(transcript or "")
    if max_chars <= 0 or len(t) <= max_chars:
        return t

    marker = "\n\n[... transcript truncated for length ...]\n\n"
    # Keep more of the beginning since speakers/task framing is often there.
    head_len = int(max_chars * 0.65)
    tail_len = max(0, max_chars - head_len - len(marker))
    if tail_len <= 0:
        return t[: max_chars - 1] + "…"

    head = t[:head_len].rstrip()
    tail = t[-tail_len:].lstrip()
    return head + marker + tail


def _is_gemini_deadline_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return ("504" in msg) or ("deadline exceeded" in msg)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Meeting Intelligence Tool: summarize transcripts, extract actions/decisions/questions, log to Google Sheets."
    )

    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument(
        "--audio",
        type=str,
        help="Path to an audio file (e.g., .wav, .mp3, .m4a, .mp4, .webm, .ogg, .flac). Requires ffmpeg.",
    )
    group.add_argument("--text", type=str, help="Raw transcript text")

    parser.add_argument(
        "--excel",
        type=str,
        default="meeting_log.xlsx",
        help="(Deprecated) Previously used for Excel output. Logging now goes to Google Sheets.",
    )
    parser.add_argument(
        "--gemini-model",
        type=str,
        default=None,
        help="Gemini model name (default: env GEMINI_MODEL or auto-select from --list-models)",
    )

    parser.add_argument(
        "--raw-response-file",
        type=str,
        default=None,
        help="Path to a file containing a raw Gemini response (skips API call; useful for parser validation)",
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print raw Gemini response and JSON normalization warnings",
    )

    parser.add_argument(
        "--list-models",
        action="store_true",
        help="List Gemini models available for your API key and exit",
    )

    parser.add_argument(
        "--generate-emails",
        action="store_true",
        help="Preview and send emails via Gmail using the Google Sheets 'Team Directory' worksheet (asks for confirmation)",
    )

    return parser


def main(argv: list[str]) -> int:
    # Load GEMINI_API_KEY and other settings from .env if present.
    load_dotenv()

    args = build_arg_parser().parse_args(argv)

    if args.list_models:
        models = list_models()
        if not models:
            print("No models found (generateContent). Check your GEMINI_API_KEY.")
            return 1
        print("Available Gemini models (generateContent):")
        for m in models:
            print(f"- {m}")
        return 0

    # 1) Detect input type
    if args.text:
        transcript = args.text
        source = "text"
    elif args.audio:
        # 2) If audio → transcribe using Whisper
        transcript = transcribe_audio(args.audio, whisper_model="base")
        source = "audio"
    else:
        transcript = _load_hf_sample_transcript()
        source = "hf-dataset"

    if not transcript.strip():
        print("ERROR: Empty transcript")
        return 2

    print(f"Input source: {source}")
    print(f"Transcript length: {len(transcript)} characters")

    transcript_for_llm = transcript

    # Audio transcripts can be long; shrink by default to reduce timeouts.
    if source == "audio":
        try:
            max_chars_audio = int(os.environ.get("TRANSCRIPT_MAX_CHARS_AUDIO", "8000"))
        except Exception:
            max_chars_audio = 8000
        transcript_for_llm = _shrink_transcript(transcript_for_llm, max_chars_audio)

    # 3) Send transcript to Gemini
    if args.raw_response_file:
        raw = Path(args.raw_response_file).read_text(encoding="utf-8")
    else:
        try:
            raw = extract_with_gemini(transcript_for_llm, model_name=args.gemini_model)
        except Exception as e:
            # Retry once with a shorter transcript when Gemini times out.
            if _is_gemini_deadline_error(e) and len(transcript_for_llm) > 4500:
                try:
                    retry_max = int(os.environ.get("TRANSCRIPT_MAX_CHARS_RETRY", "5000"))
                except Exception:
                    retry_max = 5000
                print("Gemini request timed out (504). Retrying with a shorter transcript...")
                try:
                    raw = extract_with_gemini(_shrink_transcript(transcript_for_llm, retry_max), model_name=args.gemini_model)
                except Exception as e2:
                    print("ERROR: Gemini request failed")
                    print(str(e2))
                    return 4
            else:
                print("ERROR: Gemini request failed")
                print(str(e))
                return 4

    if args.debug:
        print("--- RAW GEMINI OUTPUT START ---")
        print(raw)
        print("--- RAW GEMINI OUTPUT END ---")

    # 4) Parse structured JSON
    data, err = parse_gemini_json(raw)
    if err or data is None:
        print("ERROR: Failed to parse Gemini JSON output")
        print(f"Reason: {err}")
        if not args.debug:
            print("--- RAW MODEL OUTPUT START ---")
            print(raw)
            print("--- RAW MODEL OUTPUT END ---")
        return 3

    normalized, warnings = normalize_meeting_json(data)
    meeting_id = str(uuid.uuid4())[:8]
    normalized["meeting_id"] = meeting_id

    # 5) Append results to Google Sheets (always)
    try:
        from integrations.google_sheets import append_logs
    except ModuleNotFoundError as e:
        print("ERROR: Missing dependency for Google Sheets integration.")
        print(str(e))
        print(
            "Fix: use the project venv and install requirements. For example:\n"
            "  .\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt\n"
            "  .\\.venv\\Scripts\\python.exe main.py --text \"...\""
        )
        return 6

    try:
        append_logs(normalized)
        print("Appended results to Google Sheets: 'Meeting Intelligence' → 'Logs'")
    except Exception as e:
        print("ERROR: Failed to write to Google Sheets")
        print(str(e))
        return 5


    # Optional: enrich action items with owner emails and send emails.
    if args.generate_emails:
        try:
            from integrations.gmail_smtp import check_email_config, send_all_emails
            from integrations.google_sheets import load_team_directory
        except ModuleNotFoundError as e:
            print("ERROR: Missing dependency for email sending / Google Sheets.")
            print(str(e))
            print(
                "Fix: use the project venv and install requirements. For example:\n"
                "  .\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt\n"
                "  .\\.venv\\Scripts\\python.exe main.py --text \"...\" --generate-emails"
            )
            return 6

        try:
            mapping = load_team_directory()
        except Exception as e:
            print("ERROR: Failed to load Team Directory from Google Sheets")
            print(str(e))
            mapping = {}

        for item in normalized.get("action_items", []):
            owner = str(item.get("owner", "")).strip().lower()
            item["email"] = mapping.get(owner)

        preview_emails(normalized.get("action_items", []))

        try:
            check_email_config()
        except Exception as e:
            print("ERROR: Email sending is not configured.")
            print(str(e))
            print("Set EMAIL_ADDRESS and EMAIL_APP_PASSWORD in your .env, then retry.")
            return 0

        if confirm_send():
            send_all_emails(normalized.get("action_items", []), mapping)
        else:
            print("Email sending skipped.")
    if args.debug and warnings:
        print("--- JSON NORMALIZATION WARNINGS ---")
        for w in warnings:
            print(f"- {w}")

    if args.debug:
        import json

        print("--- NORMALIZED JSON (WRITTEN TO EXCEL) ---")
        print(json.dumps(normalized, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
