# VcXsrv: reachability probing + Windows autostart (VERIFIED 2026-08-13)

Solves the "desktop app is broken" class of report where the real cause is **no X server**.
VcXsrv does not survive a Windows reboot unless wired into startup, so the app can get
stranded with no window and no obvious explanation.

---

## 1. Probe reachability (no root, no packages)

`xdpyinfo` is NOT installed on this box, and `sudo apt-get install -y x11-utils` fails —
sudo prompts for a password the agent cannot supply. Calling `xdpyinfo` anyway exits **127**,
which looks identical to "X server unreachable".

**This false negative cost a real session:** the agent reported "X SERVER UNREACHABLE",
then went hunting a Windows Firewall block, while VcXsrv was fine the whole time. The honest
signal was the TCP probe: port 6000 OPEN.

Dependency-free probe — `/<home>/bin/xprobe.sh`:

```bash
#!/usr/bin/env bash
# X server reachability probe. No x11-utils, no root.
# Usage: xprobe.sh [host] [display]   default: <wsl-gateway-ip> :0 (port 6000)
# Exit 0 = reachable, 1 = not.
HOST="${1:-<wsl-gateway-ip>}"
DISP="${2:-0}"
PORT=$((6000 + DISP))
if timeout 4 bash -c "cat < /dev/null > /dev/tcp/$HOST/$PORT" 2>/dev/null; then
  echo "X OK  - $HOST:$DISP (tcp $PORT open)"; exit 0
else
  echo "X DOWN - $HOST:$DISP (tcp $PORT refused) -- VcXsrv not running?"; exit 1
fi
```

**Test any probe in BOTH directions before trusting it.** An untested probe is the same bug
wearing a different hat. Verified here:

```
$ xprobe.sh              -> X OK  - <wsl-gateway-ip>:0 (tcp 6000 open)     exit 0
$ xprobe.sh <wsl-gateway-ip> 9 -> X DOWN - <wsl-gateway-ip>:9 (tcp 6009 refused) exit 1
```

Positive control AND negative control. A probe that only ever returns OK proves nothing.

---

## 2. Start VcXsrv manually

```
'/mnt/c/Program Files/VcXsrv/vcxsrv.exe' :0 -multiwindow -clipboard -wgl -ac
```

**FLAG TRAP:** `-nodecoration` is invalid with `-multiwindow` / `-rootless`. VcXsrv prints
`winValidateArgs - -nodecoration is invalid with -multiwindow or -rootless.` then
`Fatal server error: (EE) Server terminated with error (1)` and exits instantly.
If VcXsrv "won't start", read its own stderr first — it names the offending flag.

Launching via `cmd.exe /c start ""` from a WSL cwd proved unreliable (silent no-op).
Direct exec of the `.exe` path works.

---

## 3. Windows autostart (survives reboot)

Placed in the **Startup folder**, not a registry Run key, so it's visible and the user can
disable it by deleting one file:

`C:\Users\<User>\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\vcxsrv-autostart.bat`

```bat
@echo off
REM VcXsrv autostart - X server for the Hermes desktop app (WSL).
REM IDEMPOTENT: exits quietly if already running, so a manual start is never duplicated.
REM FLAG TRAP: -nodecoration is INVALID with -multiwindow (winValidateArgs -> exit 1). Don't add it.

tasklist /FI "IMAGENAME eq vcxsrv.exe" 2>NUL | find /I "vcxsrv.exe" >NUL
if not errorlevel 1 goto :already

REM /B + explicit exit keeps this detached so nothing ever blocks on it.
start "VcXsrv" /B "C:\Program Files\VcXsrv\vcxsrv.exe" :0 -multiwindow -clipboard -wgl -ac
exit /b 0

:already
exit /b 0
```

### Pitfall: `start ""` blocks (bug introduced AND caught in-session)
The first version used `start "" "...vcxsrv.exe"`. Invoked through WSL, cmd.exe stayed
attached to the child and the call **hung for 180s (exit 124)**. Windows fires Startup items
detached so it likely would have been fine at boot — but "likely fine" is not acceptable in a
boot path. Fixed with `start "VcXsrv" /B` + explicit `exit /b 0`; re-tested cold, `rc=0`.

**Always re-verify a fix you just made.** An unverified fix is a hope, not a fix.

### Check for existing entries before adding
```
ls -la "/mnt/c/Users/Admin/AppData/Roaming/Microsoft/Windows/Start Menu/Programs/Startup/"
powershell.exe -NoProfile -Command "Get-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' -ErrorAction SilentlyContinue | Select-Object * -ExcludeProperty PS* | Format-List"
```
(This rig already has Ollama.lnk, jarvis_ear.bat, jarvis_mouth.bat — leave them alone.)

---

## 4. Verify autostart in BOTH states

Testing only the warm path is a half-test. Do both:

**Warm (already running) → must be a no-op:**
```
cmd.exe /c "C:\...\Startup\vcxsrv-autostart.bat"
tasklist.exe /FI "IMAGENAME eq vcxsrv.exe"     # same single PID, no duplicate
```

**Cold (genuinely down) → must start it:**
```
powershell.exe -NoProfile -Command "Stop-Process -Name vcxsrv -Force"
sleep 3; xprobe.sh                              # expect X DOWN
cd /mnt/c && timeout 25 cmd.exe /c "C:\...\vcxsrv-autostart.bat"
sleep 6; xprobe.sh                              # expect X OK, new PID
```

⚠️ **Killing VcXsrv kills the desktop app too** (X connection lost → `rc=133`,
`FATAL:electron_browser_main_parts.cc:504 Failed to shutdown`). The launcher's restart loop
recovers automatically, but the app's uptime counter resets. **Warn the user before running a
cold test**, and re-park the window afterwards:

```
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$(wslpath -w ~/.hermes/skills/devops/hermes-desktop-wsl/scripts/move-hermes.ps1)" -X 1920 -Y 0 -W 1050 -H 1680
```

If you reset the app's uptime with your own test, **say so** — don't let the user read the
short uptime as a crash.

---

## 5. Confirming the app is up (counters, not vibes)

The desktop app is an **X client**: Windows `Get-Process -Name Hermes` is **EMPTY even when
it's running**. The window belongs to vcxsrv.exe:

```
powershell.exe -NoProfile -Command "Get-Process -Name vcxsrv | ForEach-Object { 'PID=' + $_.Id + ' title=[' + $_.MainWindowTitle + ']' }"
# -> PID=18344 title=[Hermes]
```

Crash counters beat impressions — the auto-restart loop silently papers over crashes, so a
running app does NOT mean a healthy one:
```
grep -c "starting Hermes desktop" /tmp/launch-hermes-right.out   # starts
grep -c "exited rc="             /tmp/launch-hermes-right.out   # crashes
ps -o pid,etime,pcpu --no-headers -p $(cat /tmp/hermes_desktop.pid)
```
`starts: 1  crashes: 0` with a long etime = genuinely healthy.

---

## 6. Terminal gotcha

Long compound one-liners chaining `echo` + `powershell.exe` + `grep` can trip the agent's
command parser (`BLOCKED (hardline): command parser limit or malformed executable payload`).
Split verification into separate small calls rather than one mega-command.
