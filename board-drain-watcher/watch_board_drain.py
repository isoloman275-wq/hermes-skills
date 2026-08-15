#!/usr/bin/env python3
"""Watch a kanban board until its active (running/ready/todo) tasks drain, then
exit 0. Useful to gate a follow-up step (e.g. a calibration run, a build, a
cleanup) so it doesn't contend with real in-flight work on the same board.

Exits non-zero if the board still has active tasks when the timeout expires.
Run as a background process; poll or await its completion.
"""
import sqlite3, os, sys, time, datetime

BOARD = os.environ.get("WATCH_BOARD", "overnight-build")
DB = os.path.expanduser(f"~/.hermes/kanban/boards/{BOARD}/kanban.db")

def active():
    if not os.path.exists(DB):
        return ["NO_DB"]
    db = sqlite3.connect(DB)
    cur = db.cursor()
    cur.execute("SELECT id, substr(title,1,40), status FROM tasks "
                "WHERE status IN ('running','ready','todo') ORDER BY status")
    rows = cur.fetchall()
    db.close()
    return rows

def main():
    check_interval = int(os.environ.get("INTERVAL", "60"))
    timeout = int(os.environ.get("TIMEOUT", "7200"))
    start = time.time()
    print(f"WATCHING board '{BOARD}' until active tasks drain "
          f"(interval={check_interval}s, timeout={timeout}s)", flush=True)
    while time.time() - start < timeout:
        act = active()
        if not act:
            print("BOARD CLEAR — no active (running/ready/todo) tasks", flush=True)
            return 0
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {len(act)} active:", flush=True)
        for a in act:
            print(f"   {a[2]:7s} {a[0]} {a[1]}", flush=True)
        time.sleep(check_interval)
    print(f"TIMEOUT after {timeout}s — still {len(active())} active", flush=True)
    return 1

if __name__ == "__main__":
    sys.exit(main())