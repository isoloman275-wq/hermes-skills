# Desktop Shortcut Catalog (user: Admin, Windows host, verified 2026-08-09)

Snapshot of `C:\Users\<win-user>\Desktop\` `.lnk` shortcuts and their resolved
targets. Update this file only when you have actually enumerated the Desktop
(`ls /mnt/c/Users/Admin/Desktop/`) — do not guess new entries.

## Resolved (UTF-16 method)
| Shortcut (.lnk)        | Target                                    | Notes
|------------------------|-------------------------------------------|------
| voice-agent-b          | C:\voice-agent-b                          | voice agent dir
| ExampleGame           | (Start Menu / game client)               | game client
| <content-pipeline>                 | n/a (regex)                               | <content-pipeline> pipeline app
| pipeline - Shortcut    | (no parseable target — folder shortcut)   |
| Admin - Shortcut       | (no parseable target — folder shortcut)   |
| <user> - Shortcut      | (no parseable target — folder shortcut)   |
| Electrum / Fightcade2 / RustDesk | (not resolved this session)      |

## How the coach launches (from LAUNCH.bat, verified)
1. Loads `.env` vars (relative path → needs cwd = C:\<project-dir>).
2. Activates `.venv\Scripts\activate.bat`.
3. Detects <project-dir> PostgreSQL listener on 5432 (falls back to 5433) via `netstat`.
   WARNs (non-fatal) if <project-dir> not running.
4. `python app.py` → Flask on http://localhost:5000, auto-opens browser.
