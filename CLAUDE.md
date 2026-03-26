# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup & Run

**First-time and subsequent launches** — double-click the launcher for your platform:
- Windows: `launch.bat`
- macOS: `launch.command` (may need `chmod +x launch.command` once)

Or from a terminal: `python launch.py`

`launch.py` uses only stdlib and handles everything automatically:
1. Creates `.venv` if missing
2. Installs `requirements.txt` into the venv
3. Checks Ollama and pulls `llama3.2` if Ollama is running but the model isn't present
4. Re-execs into the venv Python and launches `main.py`

On subsequent runs when setup is already complete, the setup window is skipped and the app launches immediately.

To run `main.py` directly (after setup is done): `.venv/Scripts/python main.py` (Windows) or `.venv/bin/python main.py` (macOS).

## Architecture

The app is a **hold-to-dictate** desktop tool: hold a global hotkey → mic records → faster-whisper transcribes → optional Ollama LLM rewrites for formality → pynput types the text at the active cursor.

**Dependency injection pattern**: `main.py` instantiates all components and passes them into `AppWindow`. No globals or singletons.

**Threading model** (4 threads at peak):
- UI thread — Tk event loop; all widget updates must go through `self.after(0, ...)`
- pynput daemon — global hotkey listener; fires callbacks → `after()` into UI thread
- sounddevice audio thread — runs during recording only; appends to `_frames` list
- Worker thread (transient) — created per dictation; runs transcription → LLM → injection

**State machine** in `ui/app_window.py`: `_processing` bool guards against overlapping dictations. States: Idle → Recording → Transcribing → (Processing) → Done → Idle.

## Key Design Decisions

- **Whisper model** is lazy-loaded in a background thread on startup (`_load_whisper_async`). `WhisperEngine.transcribe()` will block-load if called before the background load completes.
- **Formality = Neutral** skips the Ollama call entirely — zero latency overhead.
- **Text injection delay** (`injection_delay_ms`, default 175ms) gives the target window time to regain focus after the hotkey listener releases. User-configurable in `settings.json`.
- **Clipboard fallback** in `TextInjector`: if pynput `.type()` raises, falls back to clipboard paste. Also selectable via `use_clipboard_fallback` setting.
- **macOS**: Accessibility permissions required for both hotkey listening and text injection. `AppWindow._check_macos_permissions()` detects and shows a dialog on launch.
- **CUDA**: auto-detected via `torch.cuda.is_available()`; falls back to CPU int8 silently. Active device shown in status bar.

## Settings

Persisted to `%APPDATA%\DictatorShipping\settings.json` (Windows) or `~/Library/Application Support/DictatorShipping/settings.json` (macOS). Written atomically (`.tmp` → `os.replace`). Key settings:

| Key | Default | Notes |
|---|---|---|
| `hotkey` | `<ctrl>+<space>` | pynput format string |
| `language` | `auto` | ISO 639-1 code or `"auto"` |
| `formality` | `Neutral` | `Neutral` / `Formal` / `Casual` |
| `auto_punctuation` | `true` | false strips all punctuation via regex |
| `whisper_model` | `small` | any faster-whisper model size |
| `ollama_model` | `llama3.2` | any model name pulled in Ollama |
| `injection_delay_ms` | `175` | ms to wait before typing |

## Component Responsibilities

- `config/settings.py` — thread-safe (`RLock`) JSON store; shared by all components
- `audio/recorder.py` — `sounddevice.InputStream` at 16kHz mono float32; `stop()` returns `np.ndarray`
- `transcription/whisper_engine.py` — wraps `faster_whisper.WhisperModel`; handles device/compute resolution and punctuation stripping
- `llm/ollama_client.py` — plain `requests` calls to `/api/chat`; `rewrite()` returns original text on any failure
- `output/text_injector.py` — `pynput.keyboard.Controller.type()` with clipboard fallback
- `hotkey/hotkey_manager.py` — `pynput.keyboard.Listener` with press/release hold detection; `_parse_hotkey()` converts settings string to modifier set + trigger key
- `ui/app_window.py` — CustomTkinter window; owns all threading coordination
