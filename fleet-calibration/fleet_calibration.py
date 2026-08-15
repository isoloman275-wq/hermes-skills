#!/usr/bin/env python3
"""
FLEET CALIBRATION HARNESS
=========================
Measures what each kanban worker profile can *accurately reproduce* on a
regular basis. Builds a ladder of task types from trivial to deep-build,
spawns each on a calibration board through the real gateway dispatch, then
scores the outcome against a deterministic, verifiable deliverable.

Scoring model (what "accurate" means):
  PASS       = status done AND the expected artifact exists with correct content
  NO_FILE    = done but artifact missing (the classic "worker faked done" bug)
  WRONG      = artifact present but wrong content
  STALE      = task never completed within timeout
  NO_CREATE  = could not create the task

Deterministic deliverable: each task must WRITE a known file into its workspace
(`<workspace>/calibration_output.txt`) with a known marker string. Verifying the
file bytes on disk = ground truth (never trust the task's self-reported status).

Works with any kanban board (default "calibration") and any worker profile set.
Edit PROFILES and LADDER below to match your fleet.
"""
import subprocess, sqlite3, time, os, sys, csv, datetime

BOARD = os.environ.get("CALIBRATION_BOARD", "calibration")
DB_PATH = os.path.expanduser(f"~/.hermes/kanban/boards/{BOARD}/kanban.db")
KANBAN = ["hermes", "kanban", "--board", BOARD]

# Edit these for your fleet:
PROFILES = ["architect", "builder", "coding-assistant", "marketing", "qa-reviewer"]

# Complexity ladder — each entry: (level, title, instruction)
# Instruction MUST be self-contained (workers have no session context) and MUST
# end with "write a file named calibration_output.txt containing <marker>".
LADDER = [
    ("S1-trivial",  "cal_triv_1",   "Write a file named calibration_output.txt in your workspace containing exactly the text: TRIVIAL_OK. Do nothing else."),
    ("S2-simple",   "cal_simple_1", "Write a file named calibration_output.txt in your workspace. First line: SIMPLE_OK. Second line: 2+2=4. Do nothing else."),
    ("S3-moderate", "cal_mod_1",    "Write a file named calibration_output.txt in your workspace. First line: MODERATE_OK. Then compute the sum of the numbers 1 through 10 and write it as the second line (just the integer). Then write a third line that is the lowercase word for the color of the sky."),
    ("S4-deep",     "cal_deep_1",   "Write a file named calibration_output.txt in your workspace. First line: DEEP_OK. Then write a valid 3-line python function named greet(name) that returns 'Hello, ' + name, and include it verbatim. Then write a one-sentence product description for a language-learning app, neutral in tone, not marketing-flavoured."),
    ("S5-build",    "cal_build_1",  "Write a file named calibration_output.txt in your workspace. First line: BUILD_OK. Then write a complete, syntactically-valid python script that defines a function fib(n) returning the nth fibonacci number using a loop, and a __main__ block that prints fib(10). Include the full script verbatim in the file. Then a one-line list of 3 tools you would use to build a web dashboard that reads a SQLite db."),
]

def run(args, timeout=90):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except subprocess.TimeoutExpired:
        return -9, "", "timeout"
    except Exception as e:
        return -1, "", str(e)

def board_exists():
    rc, out, err = run(["hermes", "kanban", "boards", "list"])
    return BOARD in out

def ensure_board():
    if not board_exists():
        run(["hermes", "kanban", "boards", "create", BOARD], timeout=30)
        return "created"
    return "exists"

def create_task(title, body, assignee):
    rc, out, err = run(["hermes", "kanban", "--board", BOARD, "create", title, "--assignee", assignee, "--body", body])
    for tok in out.split():
        if tok.startswith("t_"):
            return tok
    return None

def verify_deliverable(task_id):
    ws = os.path.expanduser(f"~/.hermes/kanban/boards/{BOARD}/workspaces/{task_id}/calibration_output.txt")
    if not os.path.exists(ws):
        return "NO_FILE"
    try:
        return open(ws).read().strip()
    except Exception:
        return "NO_FILE"

def query_task(task_id):
    if not os.path.exists(DB_PATH):
        return None
    db = sqlite3.connect(DB_PATH)
    cur = db.cursor()
    cur.execute("SELECT status, completed_at, created_at FROM tasks WHERE id=?", (task_id,))
    row = cur.fetchone()
    db.close()
    return row

def wait_for_terminal(task_id, timeout_s=720, poll=40):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        row = query_task(task_id)
        if row is None:
            return "NO_TASK", None
        if row[0] in ("done", "blocked", "archived"):
            return row[0], row
        time.sleep(poll)
    return "STALE", None

def score(task_id, expected_marker):
    content = verify_deliverable(task_id)
    if content == "NO_FILE":
        return "FAIL_NO_FILE", "no calibration_output.txt in workspace"
    if expected_marker in content:
        return "PASS", f"marker OK ({len(content)} chars)"
    return "WRONG", f"got '{content[:40]}' expected '{expected_marker}'"

def main():
    import argparse
    ap = argparse.ArgumentParser(description="Fleet calibration harness")
    ap.add_argument("--dry-run", action="store_true", help="validate matrix, DO NOT spawn")
    ap.add_argument("--levels", nargs="*", default=None)
    ap.add_argument("--profiles", nargs="*", default=None)
    args = ap.parse_args()

    ensure_board()
    if args.dry_run:
        for profile in PROFILES:
            if args.profiles and profile not in args.profiles:
                continue
            for level, title, body in LADDER:
                if args.levels and level not in args.levels:
                    continue
                print(f"  [{profile}] {level}")
        print("\nNo tasks created. Re-run without --dry-run to spawn.")
        return

    results = []
    print("FLEET CALIBRATION — spawning test ladder")
    for profile in PROFILES:
        if args.profiles and profile not in args.profiles:
            continue
        for level, title, body in LADDER:
            if args.levels and level not in args.levels:
                continue
            marker = level.split("-")[1].upper() + "_OK"
            print(f"[{profile}] {level} ...", flush=True)
            tid = create_task(title, body, profile)
            if not tid:
                results.append([profile, level, "NO_CREATE", "", ""])
                print("   !! could not create task", flush=True)
                continue
            status, row = wait_for_terminal(tid)
            result, note = score(tid, marker)
            dur = ""
            if row and row[2]:
                try:
                    dur = str(int((row[1] or time.time()) - row[2]))
                except Exception:
                    pass
            results.append([profile, level, result, note, dur])
            print(f"   RESULT: {result} | {note} | dur={dur}s", flush=True)
            time.sleep(2)

    out = os.path.expanduser("~/fleet-calibration-report.csv")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    import csv
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["profile", "level", "result", "detail", "dur_s"])
        w.writerows(results)
    from collections import Counter
    print("REPORT:", out)
    print("SUMMARY:", dict(Counter(r[2] for r in results)))

if __name__ == "__main__":
    main()