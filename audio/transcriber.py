from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
import shutil


def transcribe_audio(audio_path: str, *, whisper_model: str = "base") -> str:
    """Transcribe an audio file to text using Whisper.

    Supports common formats like .wav, .mp3, .m4a, .mp4, .webm, .ogg, .flac — anything ffmpeg can decode.
    Note: Whisper requires ffmpeg available on PATH.
    """

    path = Path(audio_path)
    if not path.exists():
        raise FileNotFoundError(f"Audio file not found: {path}")

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError(
            "ffmpeg was not found on PATH. Whisper requires ffmpeg. "
            "Install ffmpeg and restart your terminal/VS Code so PATH updates take effect."
        )

    # Convert non-wav inputs to a temporary wav for consistent decoding.
    to_transcribe = path
    tmp_wav: Path | None = None
    if path.suffix.lower() != ".wav":
        with tempfile.NamedTemporaryFile(prefix="meeting_audio_", suffix=".wav", delete=False) as f:
            tmp_wav = Path(f.name)

        try:
            proc = subprocess.run(
                [
                    ffmpeg,
                    "-y",
                    "-i",
                    str(path),
                    "-vn",
                    "-ac",
                    "1",
                    "-ar",
                    "16000",
                    str(tmp_wav),
                ],
                capture_output=True,
                text=True,
            )
            if proc.returncode != 0:
                stderr = (proc.stderr or "").strip()
                if len(stderr) > 2000:
                    stderr = stderr[-2000:]
                raise RuntimeError(f"ffmpeg failed to decode '{path.name}'.\n{stderr}")

            to_transcribe = tmp_wav
        except Exception:
            try:
                tmp_wav.unlink()
            except Exception:
                pass
            raise

    try:
        try:
            import whisper  # type: ignore
        except Exception as e:
            raise RuntimeError(
                "Whisper is not installed. Install with: pip install -U openai-whisper\n"
                "Also ensure ffmpeg is installed and on PATH."
            ) from e

        model = whisper.load_model(whisper_model)
        result = model.transcribe(str(to_transcribe))
        transcript = result.get("text", "") if isinstance(result, dict) else ""

        if not transcript.strip():
            raise RuntimeError("Whisper transcription returned empty text")

        return transcript.strip()
    finally:
        if tmp_wav is not None:
            try:
                tmp_wav.unlink()
            except Exception:
                pass
