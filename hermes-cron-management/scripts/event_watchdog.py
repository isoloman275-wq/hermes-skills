#!/usr/bin/env python3
"""EVENT-BASED WATCHDOG TEMPLATE (Hermes cron, no_agent).

Pattern: a cron runs this every N minutes. It fetches a live metric, compares
against thresholds, and PRINTS ONLY ON EVENTS. On quiet ticks it prints nothing
-> the cron delivers nothing (silent watchdog). On an event it prints the alert,
which the cron delivers to the `deliver` target (e.g. telegram:<operator> (dm)).

ADAPT THIS for any "ping me when X, then tell me when to exit" job:
  - replace get_metric() with your data source
  - replace the two event checks (cross + exit) with your own logic
  - keep state in STATE_PATH so it survives across ticks
Verified live 2026-08-18 as the ETH profit-line + trailing-stop monitor.
"""
import json, subprocess, datetime, os, sys

STATE_PATH = "/<home>/signals/watchdog_state.json"
LOG_PATH   = "/<home>/signals/watchdog.log"

# --- YOUR CONFIG (edit per job) ---
ENTRY       = 1900.0        # reference baseline (e.g. buy price)
PROFIT_LINE = ENTRY * 1.017 # event-1 threshold (e.g. break-even w/ fee buffer)
TRAIL_PCT   = 0.03          # event-2 trailing stop (e.g. 3% off peak)
# --------------------------------

def get_metric():
    # RETURN A FLOAT. Template fetches ETH/USD via public API (curl, stdlib only).
    for url in [
        "https://api.binance.com/api/v3/ticker/price?symbol=ETHUSDT",
        "https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd",
    ]:
        try:
            out = subprocess.run(["curl", "-s", "--max-time", "12", url],
                                 capture_output=True, text=True, timeout=20)
            if out.returncode == 0 and out.stdout.strip():
                d = json.loads(out.stdout)
                if "price" in d:
                    return float(d["price"])
                if "ethereum" in d:
                    return float(d["ethereum"]["usd"])
        except Exception:
            continue
    return None

def load_state():
    try:
        with open(STATE_PATH) as f:
            return json.load(f)
    except Exception:
        return {"event1": False, "peak": ENTRY, "done": False}

def save_state(s):
    with open(STATE_PATH, "w") as f:
        json.dump(s, f)

def log(line):
    try:
        with open(LOG_PATH, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass

now = datetime.datetime.now(datetime.timezone.utc).isoformat()
val = get_metric()
if val is None:
    log(f"[{now}] FETCH_FAIL")
    sys.exit(0)

s = load_state()
s["peak"] = max(s.get("peak", ENTRY), val)

event = None
if not s.get("done"):
    if not s.get("event1"):
        if val >= PROFIT_LINE:
            s["event1"] = True
            event = f"EVENT 1: metric {val:.2f} cleared {PROFIT_LINE:.2f}. Armed exit stop."
    else:
        stop = max(PROFIT_LINE, s["peak"] * (1 - TRAIL_PCT))
        if val <= stop:
            s["done"] = True
            event = (f"EVENT 2 (EXIT): metric {val:.2f} hit stop {stop:.2f} "
                     f"(peak {s['peak']:.2f}).")

save_state(s)
if event:
    log(f"[{now}] EVENT: {event}")
    print(event)           # <-- delivered to cron `deliver` target
else:
    log(f"[{now}] tick val={val:.2f} e1={s.get('event1')} peak={s['peak']:.2f}")
    # no print -> silent tick, no delivery
