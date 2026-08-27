#!/usr/bin/env python3
"""Serial model benchmark for one Ollama model — 20 verifiable tasks, deterministic oracle.
Usage: python3 model_bench.py <model_name> [num_gpu]
Requires verify_bench.py (TASKS list) in the same directory.
BEFORE TRUSTING RESULTS: GET /api/ps and confirm the resident model's
context_length matches what you intended to test."""
import json, time, urllib.request, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify_bench import TASKS

MODEL = sys.argv[1] if len(sys.argv) > 1 else "<your-model>
NUM_GPU = int(sys.argv[2]) if len(sys.argv) > 2 else 41
BASE = "http://<wsl-gateway-ip>:11434/api/generate"

def gen(prompt, timeout=240):
    body = json.dumps({"model": MODEL, "prompt": prompt, "stream": False,
                       "options": {"temperature": 0.1, "num_ctx": 65536,
                                   "num_gpu": NUM_GPU}}).encode()
    req = urllib.request.Request(BASE, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())["response"]

passed = 0
for tid, prompt, oracle in TASKS:
    t0 = time.time()
    try:
        ans = gen(prompt).strip()
        ok = oracle(ans)
        dt = time.time() - t0
        if ok: passed += 1
        print(f"{tid}: {'PASS' if ok else 'FAIL'} ({dt:.1f}s) {ans[:50]}", flush=True)
    except Exception as e:
        print(f"{tid}: FAIL ({time.time()-t0:.0f}s) ERR {str(e)[:60]}", flush=True)
print(f"\n=== {MODEL} @64K: {passed}/{len(TASKS)} ===")
