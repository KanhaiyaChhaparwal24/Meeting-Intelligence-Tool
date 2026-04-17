# Meeting Intelligence Tool

Turn meeting **text or audio** into:
- a clean **summary**
- **action items** (task, owner, deadline, priority)
- **decisions**
- **open questions**

…and automatically log everything to a Google Sheet.

![Flowchart](flowchart_update.png)

## What you get (in plain words)

- You paste a meeting transcript (or give an audio file).
- The tool extracts the useful parts.
- Input can be English, Hindi, or mixed Hinglish — the saved output is always in English.
- It appends the results to your Google Sheet: **Meeting Intelligence → Logs**.
- Optional: you can email action items to owners **from inside the sheet** using a checkbox + a confirmation prompt.

## Quick example

### Example input

"David will fix the bug by Friday. Greg will define the UI. We decided to delay the launch. What about testing timelines?"

### Example output (in Google Sheets)

Your `Logs` sheet gets rows like:
- **Summary**: meeting recap (shown once per meeting block for readability)
- **Task / Owner / Deadline / Priority**: one row per action item
- **Decision** and **Open Question**: shown once per meeting block

## Setup (one-time)

### 1) Create your Google Sheet

Create a Google Sheet named **Meeting Intelligence** with 2 tabs:
- `Logs`
- `Team Directory`

In `Team Directory`, keep headers exactly:
- `Name` | `Email`

### 2) Put your Google credentials in the project

This project reads/writes Sheets using a **Google service account**.
- Place your service account file as: `credentials.json` (project root)
- Share your Google Sheet with the service account email (Editor access)

### 3) Add your Gemini key

Create a file named `.env` in the project root and add:

```text
GEMINI_API_KEY=your_key_here
```

### 4) Install & run (Windows PowerShell)

```powershell
cd "e:\Coding\Meeting Intelligence Tool"

python -m venv .venv
.\.venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

## Using the tool

### Option A — Paste text

```powershell
.\.venv\Scripts\python.exe main.py --text "David will fix bug by Friday. Greg will define UI."
```

### Option B — Audio file

Audio works for common formats (anything `ffmpeg` can decode), for example:
- `.wav`, `.mp3`, `.m4a`, `.mp4`, `.webm`, `.ogg`, `.flac`

Examples:

```powershell
.\.venv\Scripts\python.exe main.py --audio "data/sample_short.wav"
.\.venv\Scripts\python.exe main.py --audio "data/test.m4a"
```

#### ffmpeg (required for audio)

Whisper needs `ffmpeg` installed and available on PATH.

```powershell
winget install --id Gyan.FFmpeg
```

Restart VS Code after installing so PATH updates apply.

## Email action items from the Google Sheet (recommended)

This is the “optional toggle + confirmation” flow.

### What it looks like

In `Logs`, you’ll have these extra columns:
- `Email` (optional)
- `Send?` (checkbox)
- `Sent At` (date **and** time)
- `Send Status`

New rows appended from the terminal will automatically keep these columns working (checkbox + formatting).

### How to enable the sheet menu/button

1) Open your Google Sheet → **Extensions → Apps Script**
2) Paste the file: [integrations/google_sheets_apps_script.gs](integrations/google_sheets_apps_script.gs)
3) Save, reload the sheet
4) Use the menu: **Meeting Intelligence → Send Checked Emails**

How sending works:
- Tick `Send?` on the rows you want to email
- Click **Send Checked Emails**
- You will get a **Yes/No confirmation** before anything is sent
- On success:
  - `Send Status` becomes `SENT`
  - `Sent At` is filled with **date + time**

Email content includes:
- Task
- Priority
- Deadline
- Decision made (if present)
- Open question (if present)
- Meeting summary (if present)
- Meeting ID (if present)

Important: emails are sent from the Google account that authorizes the Apps Script.

## What columns are stored in `Logs`

Main columns:
- `Timestamp`
- `Meeting_ID` (same for all rows created in a single run)
- `Summary`
- `Task`
- `Owner`
- `Deadline`
- `Priority`
- `Decision`
- `Open Question`

For readability, the tool merges the meeting-level cells (`Summary`, `Decision`, `Open Question`) across the action-item rows for the same meeting block.

## Troubleshooting

- **Audio works for .wav but not .m4a (or vice versa)**
  - Confirm `ffmpeg` is installed and `ffmpeg -version` works in your terminal.
- **Google Sheet not found / permission errors**
  - Ensure the sheet name is exactly **Meeting Intelligence**
  - Share it with the service account email inside `credentials.json`
- **Gemini errors / rate limits**
  - Re-run after a short wait, or set `GEMINI_DELAY_SECONDS` in `.env` (example: `2.0`).

## Project files (optional)

- [main.py](main.py) — main command you run
- [audio/transcriber.py](audio/transcriber.py) — audio → text (supports `.m4a` and other formats)
- [integrations/google_sheets.py](integrations/google_sheets.py) — appends to Google Sheets + keeps Send columns working
- [integrations/google_sheets_apps_script.gs](integrations/google_sheets_apps_script.gs) — checkbox + confirmation email sending inside the sheet
- [llm/gemini_extractor.py](llm/gemini_extractor.py) — Gemini call
- [utils/parser.py](utils/parser.py) — converts Gemini JSON into clean fields
