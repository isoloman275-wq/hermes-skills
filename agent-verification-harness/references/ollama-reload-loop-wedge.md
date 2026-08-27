# Ollama reload-loop wedge (M1 Windows, 2026-08-24) — diagnosis + fix

## Symptom

Generate calls to a model on M1's Windows Ollama hang/timeout indefinitely even
for trivial prompts ("17*23"), while `/api/tags` stays healthy. Killing
llama-server.exe spawns a fresh one that re-wedges. `keep_alive:0` unload
attempts appear to succeed but the model reappears in `/api/ps` seconds later.

## Root cause (verified via Get-CimInstance + TCP connection sampling)

NOT simple VRAM starvation:
1. Timed-out/abandoned client jobs remain in Ollama's scheduler queue.
2. Each llama-server kill → the next queued job re-requests the SAME model →
   reload-loop, with the model loading at its FULL default context
   (`-c 131072` seen: 128K KV cache on an 8GB RX 5700XT).
3. Unload attempts that include any prompt text actually GENERATE and refresh
   keep-alive — making the wedge worse.

## Reliable fix sequence (PowerShell from WSL)

```
Get-CimInstance Win32_Process -Filter "Name='llama-server.exe'"   # confirm wedge
Stop-Process -Name llama-server -Force
Stop-Process -Id <ollama serve pid> -Force        # wipes the request queue
Start-Process 'C:\Users\<win-user>\AppData\Local\Programs\Ollama\ollama.exe' -ArgumentList 'serve' -WindowStyle Hidden
# verify /api/ps shows NONE resident, THEN immediately load the capped variant:
curl /api/generate -d '{"model":"<capped-variant>","prompt":"...","options":{"num_ctx":8192},"keep_alive":1800}'
```
Post-fix measured: 44.5 tok/s, ~2.3s per short verification (was 240s+ timeouts).

## Prevention conventions (user-set)

- Agent-grade variants cap context at ~64K (Hermes tool-use floor), not native max.
- Special-purpose sub-64K variants (e.g. 8K verifier) are raw-API-only; they can
  never back a Hermes profile.
- After any restart, load the variant you WANT resident first — don't leave the
  default full-ctx model as the thing that auto-loads.
