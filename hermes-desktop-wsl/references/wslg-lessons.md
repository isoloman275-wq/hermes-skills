# WSLg session lessons (2026-08-23 "desktop crashed" incident)

## 1. The renderer crash loop came BACK under WSLg — --disable-gpu is REQUIRED again
The skill previously claimed WSLg's /dev/dxg path made `--disable-gpu` unnecessary.
DISPROVEN 2026-08-23: under WSLg the Electron renderer died in a
`render-process-gone reason=clean-exit` loop (~every 90s, desktop.log) while the
main process + launcher loop stayed alive — the app "runs" but the window keeps
dying/reloading. Fix (applied to /<home>/launch-hermes-wslg.sh):
```
HERMES_ARGS="--no-sandbox --disable-gpu"
```
After the flag: crash counter frozen, zero new render-process-gone over 100s+.
LESSON: "GPU passthrough detected; enabling GPU acceleration" in the log is the app's
own claim, not proof the GPU path is stable. If a user says "it keeps crashing",
grep -c 'render-process-gone' ~/.hermes/logs/desktop.log FIRST and watch whether the
count GROWS across two probes ~60-100s apart.

## 2. "Process alive" ≠ window on screen — RAIL surfaces can be invisible
Even with a healthy process, the msrdc RAIL window reported visible=True,
non-iconic, sane GetWindowRect — yet screenshots of every monitor showed only
wallpaper. Windows-side geometry probes LIE about what's painted. Ground truth =
CopyFromScreen screenshot + vision check, not ShowWindow/GetWindowRect return values.
Also: SetWindowPos/MoveWindow from Windows clamps height to 1080 (primary monitor
height?) even though the portrait monitor is 1680 tall; xdotool resize INSIDE WSLg
(`DISPLAY=:0 xdotool windowsize <id> 1050 1632`) DOES take effect at the X layer but
the Windows-reported rect may still disagree. Don't burn an hour reconciling the two
coordinate systems — verify with pixels on screen.

## 3. Diagnosis-order discipline for "desktop app broken/crashed"
1. `pgrep -x Hermes` — process alive?
2. `grep -c render-process-gone ~/.hermes/logs/desktop.log` twice, 60s apart — growing = renderer crash loop → relaunch with --disable-gpu.
3. `tail ~/.hermes/logs/desktop.log` — backend READY line present? (the headless
   "web UI disabled — use hermes dashboard" 404 is BENIGN, not the fault).
4. Only then touch window placement. Never mix crash triage with geometry fiddling —
   this session lost an hour interleaving them while the user watched nothing work.

## 4. Kill sequence that works (pgrep self-match trap)
```
pgrep -x Hermes | xargs -r kill -9     # NOT pkill -f 'Hermes' (self-match)
rm -f ~/.config/Hermes/window-state.json /tmp/launch-hermes-wslg.lock
# relaunch via background terminal: /<home>/launch-hermes-wslg.sh
```
Killing by exact PID or pgrep -x only. A bare `pkill -f launch-hermes-wslg` SIGTERMs
your own shell (exit -15).

## 5. Fallback if WSLg window refuses to paint: browser dashboard
`hermes dashboard` gives the same UI in the user's browser with zero window-manager
involvement. Offer it early instead of grinding on the native window past ~30min —
the user's patience budget for "fixing the desktop" is well under an hour.

## 6. User-communication lesson (<operator>)
During a long interactive fix he sent repeated interrupts ("stop", "come back",
"how many more hours"). Rules:
- Give a status + ETA estimate EARLY, after the first failed fix attempt, not after an hour.
- When interrupted with "stop", actually stop and answer in plain text — do not fire more tool calls.
- One question to the user ("do you see it in your taskbar? what happens when you click it?")
  beats ten blind probes when the failure is on-screen and only he can see it.
