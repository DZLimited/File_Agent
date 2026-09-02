# File Manager Agent

A desktop GUI that manages folders on your PC using **typed commands, voice commands, or natural language** — powered by an optional free Gemini API integration, with a built-in rule-based parser as a safety fallback.

> "Create a folder on my desktop called Reports" → done. No clicking through File Explorer.

![Python](https://img.shields.io/badge/python-3.9+-blue)
![Platform](https://img.shields.io/badge/platform-Windows-lightgrey)
![License](https://img.shields.io/badge/license-MIT-green)

---

## Features

- **Create, rename, delete, and read folders** through a simple GUI
- **Voice input** — speak your command, it transcribes and can auto-run it
- **Natural language understanding** via Google Gemini (free tier) — handles messy phrasing, not just rigid command syntax
- **Automatic fallback** — if Gemini is unavailable (no key, no internet, rate limit), it silently falls back to a built-in rule-based parser so the app never fully breaks
- **Safety guardrails** — blocks operations on bare drive roots (`C:\`) and system-critical folders (Windows, Program Files, System32, etc.)
- **Confirmation prompts** before any delete or rename
- **Known Windows locations** — understands "Desktop", "Documents", "Downloads", "Pictures", "Videos", "Music" as well as drive letters
- **Configurable auto-suffix** — e.g. automatically turn "CBFEWS" into "CBFEWS_AI" on creation

---

## Demo commands

```
create folder in E drive in BIS with name CBFEWS
create a folder on desktop called ABC
rename folder E:\BIS\CBFEWS_AI to CBFEWS_FINAL
delete folder E:\BIS\OldStuff
read folder E:\BIS
```

With Gemini enabled, messier phrasing works too:

```
hey can you put a new folder called Reports somewhere on my desktop
make another one just like CBFEWS_AI but call it CBFEWS_V2
```

---

## Installation

### 1. Requirements
- Windows
- Python 3.9+

### 2. Install dependencies

```bash
pip install SpeechRecognition pyaudio google-genai
```

If `pyaudio` fails to install (common on Windows, since it needs to compile):

```bash
pip install pipwin
pipwin install pyaudio
```

### 3. Run it

```bash
python file_agent.py
```

---

## Enabling AI-powered understanding (optional, free)

By default the app works with a built-in rule-based parser — no API key needed. To enable smarter natural-language understanding via Google Gemini:

1. Go to [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)
2. Sign in with a Google account and click **Create API key** (no credit card required for the free tier)
3. Paste the key into the app's **Gemini API Key** field and click **Save**

The key is stored locally in `gemini_key.txt` next to the script — it is never uploaded anywhere by this app. Add `gemini_key.txt` to your `.gitignore` before pushing to a public repo.

---

## How it works

```
Voice (optional) → Speech-to-text → Command text
                                          │
                                          ▼
                        ┌─────────────────────────────────┐
                        │   Gemini (if key set + online)   │──fails──┐
                        └─────────────────────────────────┘         │
                                          │ succeeds                │
                                          ▼                         ▼
                                  Structured action        Rule-based parser
                                  (name + arguments)          (regex, offline)
                                          │                         │
                                          └───────────┬─────────────┘
                                                       ▼
                                          Argument validation
                                                       ▼
                                            Safety check (blocks
                                          system/drive-root paths)
                                                       ▼
                                     Confirmation (delete/rename only)
                                                       ▼
                                          Actual file system action
```

Only the local app touches your file system — the AI layer (when used) just decides *what* to do; your machine decides whether it's safe and then does it.

---

## Safety

This tool will refuse to operate on:
- Bare drive roots (e.g. `C:\`, `E:\`)
- Known system-critical folders (Windows, Program Files, ProgramData, System32, Recycle Bin, Recovery)

Delete and rename actions always show a confirmation dialog before executing.

**This tool can still permanently delete real folders and their contents outside the blocked list.** Use it carefully, especially with voice input and auto-run enabled.

---

## Roadmap

- [ ] Offline speech recognition option (e.g. Vosk) for fully offline use
- [ ] File-level (not just folder-level) operations
- [ ] Undo / action history log
- [ ] Cross-platform support (macOS / Linux path handling)
- [ ] Configurable custom safety blocklist

---

## Contributing

Issues and pull requests welcome. If you hit a phrasing the parser or Gemini mishandles, please include the exact command text (and whether it was typed or spoken) in your issue.

## License

MIT
