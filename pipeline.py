from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any, Dict, Tuple

from dotenv import load_dotenv

from audio.transcriber import transcribe_audio
from llm.gemini_extractor import extract_with_gemini
from utils.parser import normalize_meeting_json, parse_gemini_json


def process_input(
    mode: str,
    input_data: str,
    *,
    return_transcript: bool = False,
    gemini_model: str | None = None,
) -> Dict[str, Any] | Tuple[Dict[str, Any], str]:
    """Run the existing pipeline for Streamlit/other callers.

    Parameters
    - mode: "text" or "audio"
    - input_data:
        - if mode == "text": raw transcript string
        - if mode == "audio": path to an audio file
    - return_transcript: when True, also returns transcript text
    - gemini_model: optional explicit Gemini model name

    Returns
    - result dict that is appended to Google Sheets (includes meeting_id)
    - optionally the transcript when return_transcript=True
    """

    load_dotenv()

    mode = str(mode or "").strip().lower()
    if mode not in {"text", "audio"}:
        raise ValueError("mode must be 'text' or 'audio'")

    if mode == "text":
        transcript = str(input_data or "")
    else:
        audio_path = Path(str(input_data or "")).expanduser()
        transcript = transcribe_audio(str(audio_path), whisper_model="base")

    if not transcript.strip():
        raise ValueError("Empty transcript")

    # Keep the same timeout-mitigation behavior as CLI: shrink long audio transcripts.
    transcript_for_llm = transcript
    if mode == "audio":
        try:
            max_chars_audio = int(os.environ.get("TRANSCRIPT_MAX_CHARS_AUDIO", "8000"))
        except Exception:
            max_chars_audio = 8000
        if max_chars_audio > 0 and len(transcript_for_llm) > max_chars_audio:
            marker = "\n\n[... transcript truncated for length ...]\n\n"
            head_len = int(max_chars_audio * 0.65)
            tail_len = max(0, max_chars_audio - head_len - len(marker))
            if tail_len <= 0:
                transcript_for_llm = transcript_for_llm[: max_chars_audio - 1] + "…"
            else:
                head = transcript_for_llm[:head_len].rstrip()
                tail = transcript_for_llm[-tail_len:].lstrip()
                transcript_for_llm = head + marker + tail

    raw = extract_with_gemini(transcript_for_llm, model_name=gemini_model)

    data, err = parse_gemini_json(raw)
    if err or data is None:
        raise RuntimeError(f"Failed to parse Gemini JSON output: {err}")

    normalized, _warnings = normalize_meeting_json(data)
    meeting_id = str(uuid.uuid4())[:8]
    normalized["meeting_id"] = meeting_id

    # Append to Google Sheets (same behavior as CLI)
    from integrations.google_sheets import append_logs

    append_logs(normalized)

    if return_transcript:
        return normalized, transcript
    return normalized
