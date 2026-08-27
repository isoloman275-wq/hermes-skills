---
name: hermes-desktop-wsl
description: Run Hermes desktop from WSL and build desktop plugins.
version: 1.1.0
author: NZ1Labs
license: MIT
metadata:
  hermes:
    tags: [hermes, desktop, electron, wsl, vcxsrv, plugins, preview]
    related_skills: [hermes-agent]
---

# Hermes Desktop App under WSL (VcXsrv)

The user runs the Hermes desktop (Electron) app from WSL, painting its window onto
the Windows desktop through VcXsrv. Recurring non-trivial launch with two gotchas:
(1) WSL2's X display is the Windows host IP, not localhost; (2) the app's saved window
position drifts off-screen on a single monitor, and (3) frameless windows do NOT honor
cross-display positioning under VcXsrv multiwindow — they need a Windows HWND nudge.

## STEP 0 — ALWAYS check the X server FIRST (most common "app is broken" cause)
Before diagnosing Electron, plugins, window state, or crashes: **is VcXsrv even running?**
If it died (or the box rebooted), the app has no X server, dies on launch, and stays dead.
This looks like "the desktop app is broken" but is one layer below the app entirely.

```
/<home>/bin/xprobe.sh          # X OK / X DOWN, exit 0/1
```

**Do NOT probe with `xdpyinfo`.** It is not installed on this box and `apt install x11-utils`
needs a sudo password the agent cannot supply. A bare `xdpyinfo` call exits **127**
("command not found") which reads as "X server unreachable" — a FALSE NEGATIVE that sent one
session chasing a nonexistent Windows Firewall problem while VcXsrv was perfectly healthy.
Use the dependency-free `/dev/tcp` port test (port 6000 + display N) instead:

```
timeout 4 bash -c 'cat < /dev/null > /dev/tcp/<wsl-gateway-ip>/6000' && echo "X OK" || echo "X DOWN"
```

Generalised probe discipline (bit hard here, applies everywhere): a failing health check may
mean the **probe tool** is missing, not that the service is down. Check `which <tool>` and the
raw `${PIPESTATUS[0]}` before declaring an outage, and never pipe a first-pass probe through
`grep` — a no-match is indistinguishable from a missing binary (both print nothing).

Start VcXsrv if down (see `references/vcxsrv-startup.md` for the autostart setup):
```
'/mnt/c/Program Files/VcXsrv/vcxsrv.exe' :0 -multiwindow -clipboard -wgl -ac
```
**FLAG TRAP:** `-nodecoration` is INVALID with `-multiwindow`/`-rootless`. VcXsrv exits 1
immediately with `winValidateArgs - -nodecoration is invalid with -multiwindow or -rootless.`
Read the process's own stderr — it names the bad flag precisely.

## When to use
- Open/use the Hermes desktop app from WSL; the user reports a missing/off-screen/unmoveable window.
- Park the window on a specific monitor (multi-monitor rigs).
- Author or modify a desktop plugin (pane, statusbar chip, command).

## Prerequisites
- VcXsrv on Windows (`C:\\Program Files\\VcXsrv\\vcxsrv.exe`). If absent: latest installer
  from `github.com/marchaesen/vcxsrv` releases, run on the WINDOWS side `/VERYSILENT /NORESTART`,
  then launch X server: `vcxsrv.exe :0 -multiwindow -ac -clipboard -wgl`.
- Built app: `~/.hermes/hermes-agent/apps/desktop/release/linux-unpacked/Hermes`. Build once
  with `hermes desktop` from the hermes-agent repo root; `hermes desktop --skip-build` FAILS if
  `release/` doesn't exist.

## Launch (verified working)
1. Windows host IP WSL sees (NOT localhost under WSL2):
   `powershell.exe -NoProfile -Command \"(Get-NetIPAddress -InterfaceAlias 'vEthernet*' -AddressFamily IPv4).IPAddress\"` → e.g. `<wsl-gateway-ip>`.
2. `export DISPLAY=<WINIP>:0 && cd ~/.hermes/hermes-agent/apps/desktop/release/linux-unpacked && ./Hermes --no-sandbox` (background=true to persist).
3. Fix single-monitor OFF-SCREEN DRIFT — the app RESTORES its saved
   `~/.config/Hermes/window-state.json` on launch and OVERRIDES the `--window-position` /
   `--window-size` CLI flags. So edit the json BEFORE launching: set `x`/`y` inside the visible
   region of the target monitor, a sane `width`/`height`, and `\"isMaximized\": false`. VERIFIED
   2026-08-09: a state of `x:1600, width:1920` on a 1920-wide primary hid the titlebar (window
   looked "stuck / locked in fullscreen" but was NOT maximized); rewriting to
   `x:60, y:40, width:1280, height:800, isMaximized:false` + relaunch made it draggable again.
4. Move/resize/fullscreen are NATIVE Electron: drag title bar = move, drag edges = resize,
   F11 = fullscreen, double-click title = maximize. No code needed.
5. Verify: `pgrep -x Hermes` (main has no `--type=` in cmdline); X reachable via
   `timeout 3 bash -c 'echo > /dev/tcp/<WINIP>/6000'`.

## ★ PREFERRED AS OF 2026-08-13 — RUN UNDER WSLg, NOT VcXsrv (permanent fix)
The "stuck / can't drag the window" problem is SOLVED by running the app under **WSLg**
instead of VcXsrv. Diagnosis done by Claude Opus 5 AND Fable 5 (independent, identical
verdict): VcXsrv's `-multiwindow` internal WM does NOT implement `_NET_WM_MOVERESIZE` /\
`_NET_WM_STATE_FULLSCREEN`, and the frameless Electron HWND is created without
`WS_CAPTION`/`WS_THICKFRAME`, so NEITHER native Win32 drag NOR Electron's
`-webkit-app-region:drag` can move it. `--window-position`, window-state.json, and asar
patching are ALL useless for cross-display under VcXsrv.

WSLg (Weston compositor) fixes everything at once:
- **Native dragging works** — Weston implements `_NET_WM_MOVERESIZE`, so frameless drag and
  Win+Arrow / Win+Shift+Arrow across all monitors work out of the box.
- **GPU crash gone** — the forced `--disable-gpu` hack was needed only because VcXsrv's
  `-wgl` GLX-over-WGL path crashes Chromium's GPU process. WSLg uses `/dev/dxg` + Mesa
  d3d12 (DirectX passthrough); Electron handles it fine, log confirms `WSL GPU passthrough
  (/dev/dxg) detected; enabling GPU acceleration`.\
⚠️ **CORRECTION 2026-08-23:** `--disable-gpu` IS STILL REQUIRED under WSLg. Without it,
  the renderer hits a `render-process-gone` loop (~90s) and the app becomes unresponsive.
  The WSLg GPU path works WITH `--disable-gpu`, not without it. The launch script has
  been updated accordingly — do NOT remove the flag.
- The window is a **first-class Windows window** owned by `msrdc` (WSLg's RAIL/RDP client),
  title `Hermes (Ubuntu)`, NOT by `vcxsrv.exe`. It can be dragged/parked anywhere.

WSLg is already present on this box (verified): `/mnt/wslg` mounted, `DISPLAY=:0` and
`WAYLAND_DISPLAY=wayland-0` auto-provided at login, `/tmp/.X11-unix/X0` live, X screen
4570x1680 (spans all 3 monitors).

**Launch:** `scripts/launch-hermes-wslg.sh` (or `/<home>/launch-hermes-wslg.sh`).
It uses the inherited WSLg `DISPLAY` (does NOT override to a VcXsrv host IP) and drops
`--disable-gpu`. Single-instance lock + crash-capture loop retained.

**Disable the old VcXsrv path:** don't launch VcXsrv's launcher (`launch-hermes-right.sh`)
and remove any `export DISPLAY=<winip>:0` from `~/.bashrc`. VcXsrv can stay installed as a
fallback, but running BOTH launch loops fights over the Electron single-instance lock.

Fallback if WSLg ever misbehaves: Option 1c — patch `app.asar` (extract, sed
`titleBarStyle:"hidden"` → `frame:true` on X11) so VcXsrv creates the HWND with
`WS_CAPTION|WS_THICKFRAME` and native drag works even under VcXsrv. Full plan in
`/<home>/<income-work-dir>/desktop_fix_plan.md`.

## Multi-monitor positioning (VcXsrv path — KEEP as reference/fallback)
Hermes is a **frameless** Electron window (`titleBarStyle: "hidden"`). Under VcXsrv
multiwindow this has a nasty consequence: `--window-position`, the saved
`window-state.json`, AND even patching `computeWindowOptions` in the bundled
`app.asar`/`app.asar.unpacked/dist/electron-main.mjs` are ALL ignored for cross-display
placement. Verified root cause (Xlib probe): the real Electron X11 window collapses to a
~10x10 px box at (10,10); the Windows HWND (title "Hermes") is what actually needs moving.

The ONLY reliable fix is to nudge the real Windows HWND after launch via `SetWindowPos`
—— this is exactly what `Win+Shift+←/→` does, done programmatically. See
`references/multi-monitor.md` and `scripts/move-hermes.ps1`.

Pitfall (caused a long "stuck window" session): `Win+Shift+←/→` does NOTHING while the
window is in **fullscreen**. Press **F11** to exit fullscreen FIRST, then the arrow shortcut
works. When you tell the user to move it, give the F11 step too — don't assume it's already
windowed.

Steps (far-right monitor example; monitor bounds e.g. x=1920, 1050x1680 portrait):
1. Detect layout — `references/multi-monitor.md` (PowerShell one-liner lists every display's
   WidthxHeight@X,Y; avoid `$_` in inline bash — write a `.ps1` file and run `-File`).
2. Launch Hermes (see above).
3. Run `scripts/move-hermes.ps1 -X 1920 -Y 40 -W 1000 -H 1600` — finds the HWND titled
   "Hermes" and SetWindowPos to the target. ALWAYS pass explicit W/H (passing 0 collapses the
   window to 0x0).
4. For a permanent "always on monitor X" setup, use `scripts/launch-hermes-right.sh X Y W H`
   — it launches AND auto-nudges after ~5s.

## Desktop plugins
- Location: `~/.hermes/desktop-plugins/<id>/plugin.js` (folder name == id). Hot-reloaded;
  also ⌘K → "Reload desktop plugins".
- ONLY imports that resolve: `@hermes/plugin-sdk`, `react`, `react/jsx-runtime`. UI is `jsx()`
  calls (NOT JSX syntax). State via `atom()`/`useValue()` from the SDK.
- Panes: `ctx.register({ id, area:'panes', title, data:{ placement:'right', width:'420px' }, render })`.
  Moveable + collapsible by default.
- **Artifacts caveat (verified):** artifacts are an IN-MEMORY desktop feature (`$artifactRegistry`
  nanostore, from the rendered transcript). NO gateway RPC / dashboard endpoint exposes them, so
  a plugin CANNOT read the registry. To surface artifacts, `host.navigate('/artifacts')`. Do NOT
  re-implement the sandbox renderer in a plugin.
- Verify: `node --check plugin.js`, then launch + `grep -riE \"preview-pane.*fail|failed to load.*preview\" ~/.hermes/logs/`. SDK logs ONLY on failure → no error = loaded. The headless `hermes serve` log "web UI disabled — use `hermes dashboard`" is BENIGN, not a crash.

## Standing user requirement
Every preview/terminal pane MUST be moveable + collapsible + resizable (windowed). Never ship a fixed-position pane.

## Crash capture — use core dumps + rc>=128 evidence, NOT --enable-crash-reporter
The launcher (`/<home>/launch-hermes-right.sh`, GPU-guarded + restart loop) now carries a
**crash-evidence block**: `ulimit -c unlimited`, and on any signal-death (`rc >= 128`, the
SIGSEGV/SIGTRAP class) it preserves a timestamped bundle to
`/tmp/hermes-crash-dumps/<stamp>_sig<sig>_*.{log,core,bt}` and appends `/tmp/hermes_crashes.log`.
This is HOW to capture the next real crash instead of having the auto-restart loop mask it.
Report `grep -c "starting Hermes desktop" .../launch-hermes-right.out` (starts) vs
`grep -c "exited rc=" ...` (crashes) AND `cat /tmp/hermes_crashes.log` to the user.

**DO NOT add `--enable-crash-reporter --crash-dumps-dir=...` to HERMES_ARGS.** VERIFIED 2026-08-13:
Electron/Chromium then tries to register a *systemd user transient unit* scope and the app starts
exiting `rc=0` every ~7s (an infinite "clean exit" relaunch loop) once it collides with a stale
leftover scope. Capture relies on core dumps + the rc>=128 block, not crashpad. This flag has been
removed and a warning comment added to the launcher.

## NEW crash signature — rc=0 infinite relaunch loop (stale systemd scope)
Distinct from SIGTRAP/SIGSEGV: if the launcher shows `Hermes exited rc=0` repeating every ~7s
(not a signal, and it keeps going), that is NOT a renderer crash — it is Chromium hitting a
**stale systemd user transient scope** left over from a prior hard kill/relaunch. The app starts,
tries to register `app-org.chromium.Chromium-<pid>.scope`, collides with the leftover scope, and
bails out cleanly (so the rc>=128 evidence block never fires, which is why it loops silently).

Diagnosis + fix (VERIFIED 2026-08-13):
```
systemctl --user list-units --type=scope 'app-org.chromium.Chromium-*.scope' --all --no-legend
# a stale scope shows 'loaded active running' for a PID you already killed
kill <launcher pid> <its bash wrapper>            # stop the loop (ps aux | grep launch-hermes-right.sh)
kill -9 all 'linux-unpacked/Hermes' PIDs          # NOT pkill -f (that self-matches your own shell)
systemctl --user kill 'app-org.chromium.Chromium-*.scope'
rm -f /<home>/.config/Hermes/SingletonLock /tmp/launch-hermes-right.lock
# then relaunch via the patched launcher; verify with grep -c "exited rc=" == 0 over ~30s
```
Getting this wrong wastes a session: I first blamed `--enable-crash-reporter` (the smoke), reverted
just that flag, and the loop persisted — the stale scope was the real cause. Always check stale
scopes before touching args.

## Crashes (SIGTRAP / GPU-process abort under VcXsrv) — VERIFIED 2026-08-10
The app can die with a **hard Chromium CHECK() abort** (kernel logs it as
`Hermes: ThreadPoolSingleThreadForeground: potentially unexpected fatal signal 5 (SIGTRAP)`,
RIP at a `ud2`/`0f 0b` trap instruction). Do NOT chase the "web UI disabled — use
`hermes dashboard`" 404 in `desktop.log` — that is BENIGN and the app continues past it.
The real killer is the GPU process: Chromium tries to init a GPU stack on VcXsrv and aborts.

- Root cause: app launched **without** the GPU-disable flags. The flags live ONLY in the
  launch args (`--no-sandbox --disable-gpu --disable-gpu-sandbox --disable-software-rasterizer`),
  NOT in `window-state.json`. Launching `./Hermes --no-sandbox` bare (or via a launcher that
  omits the GPU flags) is what lets it SIGTRAP.
- Diagnosis recipe: `dmesg | grep -i "fatal signal\|trap int3\|out of memory"` — the SIGTRAP is
  definitive; rule out OOM with `free -h`. Confirm the GPU guard was applied by checking
  `/tmp/hermes_desktop.log` exists (guarded launcher writes it) or the app log shows
  "disabling GPU hardware acceleration to prevent flicker".
- Fix: relaunch via a launcher that always applies the GPU flags (see below), not bare.
- Survive future crashes: use a launcher with a real `while :; do ... wait $PID; done` restart
  loop so a SIGTRAP auto-relaunches instead of staying dead. VERIFIED 2026-08-10: GPU-guarded
  launch survived past the ~60s point where the bare launch had died, 8 healthy processes,
  zero crash markers.
- Pitfall about the launcher's own claims: a comment saying "auto-relaunch if it dies" is not
  proof a loop exists — READ the script body. The pre-2026-08-10 `/<home>/launch-hermes-right.sh`
  claimed auto-relaunch but had NO loop (launched once, slept, exited), and referenced a
  non-existent `/tmp/fill-hermes.ps1`. The correct nudger is `scripts/move-hermes.ps1`.

Full diagnosis + the fixed launcher are in `references/crash-diagnosis.md`.

## SECOND crash signature — ~137s SIGSEGV in V8 JIT (NOT deterministic — see correction)

> **CORRECTION 2026-08-13 (later same day): the "deterministic" claim below is DISPROVEN.**
> The same build <job-id>, launched against a **freshly started VcXsrv**, ran
> **56+ minutes clean: 1 start, 0 crashes** (`grep -c 'starting Hermes desktop'` = 1,
> `grep -c 'exited rc='` = 0 in the launcher log). So the ~137s cadence is **state-dependent,
> not unconditional**. The fresh-VcXsrv correlation is UNPROVEN — one clean run is not a
> root cause. **Do NOT tell the user "this build deterministically segfaults" without a live
> repro in the current session.** Report crash counters from the launcher log instead of
> reciting this section as fact.
>
> Meta-lesson: this section was written confidently from one session's evidence and became a
> false "fact" the agent repeated to the user. When you write a crash signature, state the
> conditions it was observed under, not just the symptom.

The documented SIGTRAP (signal 5) is NOT the only way this app dies. On build <job-id> the
app has been seen to SIGSEGV (signal 11) on a **~137s cadence**, EVEN with all GPU guards applied (`--no-sandbox --disable-gpu
--disable-gpu-sandbox --disable-software-rasterizer`). dmesg shows
`Hermes: Hermes: potentially unexpected fatal signal 11.` at perfectly regular ~137s
intervals. The launcher reports rc=137 (SIGKILL-ish) because each instance dies ~137s in.

- The fault address is in **V8 JIT code** (addr2line → `??`; RIP not in any file-backed
  LOAD segment, e.g. 0x5dc8...a83b — high VM range, ASLR-randomized per process). It is a
  renderer/main-process JS memory bug, NOT a native lib or GPU issue.
- NOT caused by: missing GPU guards (they were applied), the preview-pane plugin (killed
  it → still crashed ~140s), the two-monitor conflict (see above), or OS memory pressure
  (21GB free in WSL, 18GB free on Windows host — verify with `free -h` + Windows
  `Get-CimInstance Win32_OperatingSystem`).
- **RULE OUT the two-launcher conflict FIRST**: two `launch-hermes-right.sh` loops each
  spawn `./Hermes` and fight over the Electron single-instance lock — one instance's
  `wait` misattributes the kill, both loops churn, endless rc=137. Fix: the launcher now
  has a `/tmp/launch-hermes-right.lock` single-instance guard (a 2nd copy exits 0
  immediately). Check `ps aux | grep launch-hermes` for duplicates before assuming a
  renderer bug.
- Capture the crash for analysis: `ulimit -c unlimited` + launch from the
  `release/linux-unpacked/` dir → a huge sparse `core.<pid>` (1.4TB apparent / ~22MB real).
  Parse NT_PRSTATUS for si_signo=11 + RIP (see `references/sparse-core-rip-extraction.md`
  for the no-gdb Python recipe). Delete the core after.
- The binary worked 2026-08-10/12 for long sessions (desktop.log shows hours), so this is
  a regression-triggered / state-dependent renderer bug, not baseline. No clean fix at the
  launcher layer yet; the auto-restart loop masks it (app reloads every ~137s). Real fix
  is in the app source (the ~137s recurring JS op). Do NOT re-pull/rebuild expecting the
  current HEAD (56dc01d9, Aug 10) to fix it — desktop source is effectively unchanged vs
  the running build <job-id>.

## Backend is self-spawned — do NOT chase port 8788
The desktop spawns its OWN backend: `hermes serve --host 127.0.0.1 --port 0` (ephemeral port,
announced as `HERMES_BACKEND_READY port=<N>` in `desktop.log`), and the Electron renderer
connects to it directly over WebSocket. A hardcoded 8788 "dev server" port is a STALE artifact
of older builds — it exists in NEITHER the current source nor the packaged bundle
(`grep 8788` on `apps/desktop/**` and `release/.../app.asar.unpacked/dist/electron-main.mjs`
returns nothing). So an `ERR_CONNECTION_REFUSED` / `http://127.0.0.1:8788/` line in the log is
a leftover probe, NOT a real break — do not waste time "self-starting a backend on 8788".
To confirm the desktop is truly functional end-to-end, find the live backend port and hit its
API: `ss -tlnp | grep "serve"` (or parse `HERMES_BACKEND_READY port=` from `desktop.log`),
then `curl http://127.0.0.1:<PORT>/api/status` — a JSON with `gateway_state:"running"` and the
messaging platforms connected means the app + gateway are fully wired. The root
`/` returns the benign headless "web UI disabled" 404.

## Pitfalls
- **The app is an X CLIENT — Windows `Get-Process -Name Hermes` returns EMPTY even when it is
  running perfectly.** The window is owned by `vcxsrv.exe`; check its `MainWindowTitle` for
  "Hermes" instead. Do not conclude the app failed to launch from an empty Get-Process.
- **Killing VcXsrv kills the desktop app** (X connection lost → `rc=133` +
  `FATAL:electron_browser_main_parts.cc:504 Failed to shutdown`). The launcher's restart loop
  recovers it, but uptime resets. Warn the user before any test that restarts the X server,
  re-park the window afterwards, and if YOUR test caused the short uptime, SAY SO — don't let
  it be misread as a crash.
- **The auto-restart loop hides crashes.** A running app is not evidence of a healthy one.
  Judge health by counters, not by "it's up":
  `grep -c "starting Hermes desktop" /tmp/launch-hermes-right.out` (starts) vs
  `grep -c "exited rc=" ...` (crashes). Report those numbers to the user. And a `rc=0` loop is
  NOT a crash — it's the stale-systemd-scope signature (see the crash section): check
  `systemctl --user list-units --type=scope 'app-org.chromium.Chromium-*.scope'` before
  assuming a renderer bug or touching args.
- Long compound one-liners (`echo` + `powershell.exe` + `grep` chained with `;`) can trip the
  agent command parser: `BLOCKED (hardline): command parser limit or malformed executable
  payload`. Split verification into several small calls.
- `localhost:0` won't reach VcXsrv under WSL2 — use the Windows host vEthernet IP.
- Killing Electron from WSL may hit an approval gate and kill the calling shell (exit -15).
  Prefer background=true launches; let the process persist.
- `hermes config set hooks.outbound \"[...]\"` coerces a nested list to a STRING (breaks parsing).
  Use a minimal targeted text edit or yaml round-trip.
- A frameless Electron window does NOT honor `--window-position` cross-display under VcXsrv
  multiwindow — use the SetWindowPos nudge in `references/multi-monitor.md`, NOT flags or
  window-state.json. Editing the asar (`resources/app.asar` / `app.asar.unpacked/dist/electron-main.mjs`)\n  is also futile — the Windows-HWND layer overrides it.
- **UI scale lives in `~/.config/Hermes/zoom-state.json` (`zoomLevel`).** A negative value
  (e.g. -0.577) shrinks the ENTIRE UI incl. the chat box (verified: user reported "chat box
  very small" → file had -0.577). Reset to `0` for normal size; it is read at window creation,
  so a RESTART is required for it to take effect. The app may re-write it on close — if the UI
  shrinks again, `chmod 444` the file to pin it. Do NOT try to fix chat-box size from the
  renderer/plugin side; it's the global zoom level.
- **"Fullscreen" on a secondary monitor via F11 does NOT work** under VcXsrv multiwindow
  (verified: F11 PostMessage produced zero geometry change). The equivalent is to FILL the
  monitor bounds (e.g. 1050x1680 @ 1920,0 for this rig) with the SetWindowPos nudge — see
  `references/multi-monitor.md`. Tell the user this is the fullscreen equivalent; don't promise
  native F11 fullscreen.
- `Win+Shift+←/→` is dead while the Hermes window is fullscreened — press F11 first.
- When editing inline PowerShell that contains `$_` or `$($_.X)`, write it to a `.ps1` file
  and run `powershell.exe -File` — bash mangles `$_` inside double-quoted `-Command` strings.
- The running binary reads `resources/app.asar` + `app.asar.unpacked/dist/electron-main.mjs`,
  NOT `apps/desktop/dist/electron-main.mjs`. Editing the source-tree file changes nothing.
- **`$h`/`$H` ARE THE SAME VARIABLE in PowerShell (case-insensitive).** `move-hermes.ps1` used
  `$h` for the HWND handle AND `$H` for the height param — Find()'s result OVERWROTE the
  height (e.g. `1050x1311392` where 1311392 is the HWND). This is what produced the
  `bottom=65535` / `1050x4391324` garbage the old skill blamed vaguely on "param mangling".
  Fixed 2026-08-10: handle renamed to `$hwnd`. If the nudge output shows a crazy width/height
  equal to the HWND value, suspect a `$x`/`$X`-style case collision first.
- **`FindWindow(null,"Hermes")` does NOT find the VcXsrv Hermes window** (returns NULL even
  though `EnumWindows` sees it, title "Hermes", class `vcxsrv/x X rl`). `move-hermes.ps1` used
  FindWindow → the launcher's nudge silently no-op'd (`|| true`), leaving garbage geometry.
  Fixed 2026-08-10: now enumerates windows and matches title. New position scripts should use
  EnumWindows + title match, NOT FindWindow.

## Absorbed siblings (merged into this umbrella)
This skill is the umbrella for the WSL2 ↔ Windows **desktop/GUI interop** cluster. Three
formerly-separate skills were absorbed here; their full content lives in the references below.
- **Linux GUI apps on Windows (generic VcXsrv)** — running ANY X11/Electron app from WSL2 on
  the Windows desktop, not just Hermes: install the X server, the `DISPLAY`-must-be-Windows-IP
  gotcha, and the off-screen-window fix. See `references/hermes-desktop-recipe.md` and the
  dependency-free X probe `scripts/xprobe.sh`. (From the old `wsl-linux-gui-on-windows` skill.)
- **Plugin SDK development** — the full `@hermes/plugin-sdk` surface (`host.state.*`,
  `host.request/onEvent/notify/navigate/logs/status`, `ctx.register` areas incl.
  `PALETTE_AREA`/`ROUTES_AREA`/`SIDEBAR_NAV_AREA`, `ctx.storage`/`ctx.i18n`, `atom/useValue`,
  UI primitives). See `references/wsl-launch-and-verify.md`, `references/vcxsrv-setup.md`, and
  `templates/preview-pane-plugin.js`. (From the old `hermes-desktop-plugin-dev` skill.)
- **Windows desktop shortcuts from WSL** — locate + resolve `.lnk` targets (UTF-16 decode or
  PowerShell COM) and the WSL→Windows-desktop launch limitation. See
  `references/desktop-shortcuts-catalog.md` + `scripts/resolve_lnk.py`, and the Hermes-specific
  shortcut launcher in `references/create-desktop-shortcut.md`. (From the old
  `windows-desktop-shortcuts` skill.)

## References
- `references/vcxsrv-startup.md` — **START HERE if the app "won't start"**: dependency-free X
  probe (xprobe.sh, no x11-utils/root), the `-nodecoration`+`-multiwindow` fatal-flag trap, and
  the idempotent Windows Startup-folder autostart .bat (+ how to test it cold AND warm).
- `references/crash-diagnosis.md` — SIGTRAP/GPU-process crash diagnosis + the GPU-guarded,
  auto-restart launcher (replaces the broken `/<home>/launch-hermes-right.sh`).
- `references/sparse-core-rip-extraction.md` — no-gdb Python recipe to pull si_signo+RIP from
  a huge sparse `core.<pid>` (NT_PRSTATUS parsing) + crash-triage checklist (2026-08-13).
- `references/desktop-launch.md` — full VcXsrv install + launch sequences.
- `references/plugin-dev.md` — SDK surface, artifacts caveat, verification steps.
- `references/multi-monitor.md` — 3-monitor layout detection, geometry probe (PowerShell +
  python-xlib), and the SetWindowPos fix recipe.
- `scripts/move-hermes.ps1` — move Hermes HWND to a target monitor (params -X -Y -W -H).
- `scripts/launch-hermes-right.sh` — launch + auto-park on a given monitor (args X Y W H).
- `references/create-desktop-shortcut.md` — create a Windows desktop `.lnk` so the user can
  relaunch by double-click (VERIFIED 2026-08-10; gotcha: `-File <wsl-path>` FAILS — pipe the
  PS1 via `-Command -`; target must be `wsl.exe --exec bash -lc ".../launch-hermes-right.sh"`).
  Template: `templates/hermes-shortcut.ps1`.
- `templates/preview-pane.plugin.js` — working hybrid pane (URL iframe + Artifacts tab).
