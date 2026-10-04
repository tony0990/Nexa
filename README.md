# Nexa — Member 6 Desktop UI

Independent **Member 6** subsystem from the NEXA team plan:

- PySide6 Windows desktop shell (`Nexa.exe`)
- Arabic / English UI with RTL
- Light / Dark themes
- Full workflow screens using **fake services** (no real ASR, LLM, Gmail, or worker required)
- First-run setup
- Windows packaging script

This package owns only UI, i18n, themes, and packaging. Business logic goes through public service interfaces.

## Run

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python apps/nexa_desktop.py
```

## Tests

```bash
pytest
```

Qt widget tests use the offscreen platform (`tests/conftest.py`). Member 6 coverage lives in `tests/unit/member6` and `tests/integration/member6`.

## Windows package

```bash
python scripts/build_windows.py
```

Output: `dist/Nexa/Nexa.exe`

The production split with `NexaWorker.exe` is Member 5. This script packages the desktop UI and can later include the worker binary when that subsystem is integrated.

## Windows package (updated)

```bash
python scripts/build_windows.py --worker path/to/NexaWorker.exe   # worker optional until Member 5 delivers it
python scripts/build_windows.py --layout-only                     # re-assemble folders without PyInstaller
```

Produces `dist/Nexa/` with `Nexa.exe`, `NexaWorker.exe`, `resources/`, `models/{whisper,llm}`, `data/`, `logs/` (plan section 43) and prints warnings for a missing worker or empty model folders.

## Added in this iteration

- Snooze: 30m / 1h / 3h / tomorrow morning (uses the Settings morning time) / validated custom date-time; only the reminder moves, never the deadline.
- Reschedule validates the date and updates the calendar.
- Calendar mode highlights days with deadlines.
- Email preview: reminder recipients chosen separately from report recipients (assignee, assignee + role, same as report, custom), de-duplicated.
- Audit Trail: text filter and entity history (`action:17`); Email History: status/kind/text filters.
- Dashboard: completed-tasks card.
- Fix: `fakes.py` was missing the `Reminder` import (app crashed on start).
