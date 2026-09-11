---
name: session-recovery
description: Resume a crashed/interrupted Hermes session — reconstruct "where we were" by querying the local session store via session_search, then cross-check live disk/process state before acting. Use when the user says "you crashed", "where were we", "pick up where we left off", or after any unexpected agent restart / loss of context mid-task.
category: software-development
---

# Session Recovery (crash resumption)

When the agent crashes, the session is truncated, or the user says "where were we", do NOT reconstruct from memory. The local session store is durable — read it back.

## FAST PATH — the explicit SESSION_STATE.md handoff file (this lab)
This lab ALSO keeps a deliberate human-readable handoff checkpoint at
`<home>/income-work/SESSION_STATE.md`. A bare command like `session_state.md`,
`where are we`, `resume`, or `pick up` should read THIS FILE FIRST — it is the
authoritative cross-session handoff and is faster + more reliable than grepping the
session DB. Conventions:
- It grows APPEND-ONLY: each session appends a `## SESSION UPDATE <N> (<date>, <topic>)`
  block. The LATEST (highest-numbered) UPDATE is the current state; earlier updates are
  superseded history. Read the file and report from the newest block, not the header.
- The newest block also lists OPEN/NEXT items — those are the actionable candidates to
  offer the user, so a paper "resume" ends with 1-2 concrete next-actions, not just a recap.
- File was last touched at the end of the previous session (check `ls -la` mtime); if it's
  much older than "today", flag that the checkpoint may be stale and re-verify live state.
- Always anchor to the CURRENT DATE first (`date +%Y-%m-%d`) — the file is a point-in-time
  snapshot and its numbers (stream counts, build statuses) can drift from live sources.
  For any live count you report from it, prefer re-verifying against the live source per
  lab-interaction-rules Rule 30 (never report live stream numbers from a stale note).

## SOP
1. **List recent sessions** — call `session_search()` with no args (browse mode). Returns the 3 most recent sessions with title + `last_active` timestamp. Identify the latest by `last_active` (the list order is not guaranteed sorted).
2. **Get the tail of the right session** — call `session_search(session_id=<id>, around_message_id=<n>, window=12)` (scroll mode). Returns messages around message `n`.
3. **But you usually don't know `n`.** Scroll requires an `around_message_id` that actually exists IN that session, or it errors `not in session_id`. Probe candidate IDs:
   - Message ids are globally sequential across sessions. Find a known anchor from a discovery hit (its `match_message_id`), then walk up/down from there.
   - Try the latest session's likely range. If a session from 6 days ago ended near id ~15665, a session today is much higher — try 23620, 23635, then widen.
4. **Discovery (finding WHICH session)** — `session_search(query=...)` is FTS5 with AND semantics: a multi-word query like `"mission control buttons links"` returns ZERO results even when matches exist. Use a SINGLE distinctive word (`sleeping`, `buttons`, `filename_prefix`) to surface the session, then read its bookend/anchor blocks.
5. **Child / rebound sessions** — the `session_id` from browse mode may differ from the id accepted by scroll (a "rebound" child). The scroll error may say `around_message_id X lives in YYYY (child of ZZZZ); rebound transparently` — just re-issue the scroll with that corrected `session_id`.
6. **Cross-check live state** — session text is what we SAID we did, not necessarily what's on disk/running. Verify before acting: `curl http://127.0.0.1:8777/api/state`, `grep` the actual files for the fix, `pgrep`/`ss -ltnp` for the running process. Standing user rule: "don't rely on memory; verify live."
7. **Report, then wait** — state exactly where we stopped (last in-flight action, what's verified vs unverified) and the single unfinished step. Do NOT barrel ahead "fixing" things that are already fixed.

## Gotchas
- Scroll `around_message_id` must be a real message id inside that exact session. Wrong id → `not in session_id`. Probe.
- FTS5 AND-mode: multi-word queries silently return nothing. Single words only.
- A traceback the user pastes may be a false alarm (e.g. a 2nd `server.py` failing to bind an already-held port `OSError: [Errno 98] Address already in use`). Always check which process actually owns the port before concluding the site is down.
- The live server you think crashed may still be the OLD process serving the NEW code — confirm the live PID is the one you edited by checking `built_at` / a feature flag in `/api/state`, not just that the port responds.
- RE-VERIFY DELIVERED/CACHED FILE IDENTITIES on resume. A prior session's mapping of a
  downloaded/cached file to a project can be WRONG (real case: files.zip was recorded as
  "Prism" but actually contained BentaBook; Prism was a separate workspace project). Before
  acting on a resumed assumption of what a zip/app contains, re-extract it (Python zipfile —
  `unzip` is absent on WSL) and inspect the real entry list / top-level layout. Trust live
  disk, not the prior summary.

## Worked example (Mission Control crash, 2026-07-26)
User: "you crashed where were we exactly." Browse found the latest session "Mission Control Fixes". Tail showed the last in-flight action was patching 3 files to fix a ComfyUI `filename_prefix` validation error (`no prompt_id in response … Required input is missing: filename_prefix`), then the crash. Cross-checked live: server still UP (`memory_facts=47`), all 3 fixes present on disk. The only unfinished step was end-to-end verification of the text-to-image GEN button (blocked because ComfyUI lives on M2, unreachable from WSL/LAN). Reported that precisely and asked the user whether to run a structural check or leave it for an in-browser test — did not re-apply already-applied fixes.
