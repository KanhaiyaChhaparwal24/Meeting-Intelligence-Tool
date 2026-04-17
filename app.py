from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

from pipeline import process_input


st.set_page_config(page_title="Meeting Intelligence Tool")


def _save_upload_to_temp(upload, *, suffix: str) -> str:
    with tempfile.NamedTemporaryFile(prefix="meeting_input_", suffix=suffix, delete=False) as f:
        f.write(upload.getbuffer())
        return f.name


st.title("Meeting Intelligence Tool")

mode_label = st.radio("Choose input type", ["Text", "Audio", "Text File"], horizontal=True)

input_source = None
transcript_text = ""
audio_temp_path: str | None = None

if mode_label == "Text":
    input_source = "text"
    transcript_text = st.text_area("Paste transcript", height=220, placeholder="Paste your meeting transcript here...")

elif mode_label == "Audio":
    input_source = "audio"
    upload = st.file_uploader("Upload audio", type=["wav", "mp3", "m4a"])
    if upload is not None:
        suffix = "." + upload.name.split(".")[-1].lower() if "." in upload.name else ".audio"
        audio_temp_path = _save_upload_to_temp(upload, suffix=suffix)
        st.caption(f"Uploaded: {upload.name}")

else:
    input_source = "file"
    upload = st.file_uploader("Upload .txt file", type=["txt"])
    if upload is not None:
        try:
            transcript_text = upload.getvalue().decode("utf-8", errors="replace")
        except Exception:
            transcript_text = str(upload.getvalue())
        st.caption(f"Loaded: {upload.name}")


process_clicked = st.button("Process", type="primary")

if process_clicked:
    try:
        if mode_label == "Text":
            if not transcript_text.strip():
                st.error("Please paste some text first.")
                st.stop()

            with st.spinner("Processing..."):
                result, transcript = process_input("text", transcript_text, return_transcript=True)

        elif mode_label == "Audio":
            if not audio_temp_path:
                st.error("Please upload an audio file first.")
                st.stop()

            with st.spinner("Processing..."):
                result, transcript = process_input("audio", audio_temp_path, return_transcript=True)

        else:
            if not transcript_text.strip():
                st.error("Please upload a .txt file with transcript text.")
                st.stop()

            with st.spinner("Processing..."):
                result, transcript = process_input("text", transcript_text, return_transcript=True)

        st.subheader("Processing Details")
        st.write(f"Input source: {input_source}")
        st.write(f"Transcript length: {len(transcript)} characters")

        st.subheader("Meeting Summary")
        st.write(result.get("summary", ""))

        st.success("✔ Appended results to Google Sheets: 'Meeting Intelligence' → 'Logs'")

        with st.expander("Show full structured JSON"):
            st.json(result)

    except Exception as e:
        st.error(f"Something went wrong: {e}")

    finally:
        # Best-effort cleanup for uploaded audio.
        if audio_temp_path:
            try:
                Path(audio_temp_path).unlink(missing_ok=True)
            except Exception:
                pass
