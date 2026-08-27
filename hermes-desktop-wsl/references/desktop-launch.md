# Desktop Launch — full command sequences (WSL → VcXsrv)

## Install VcXsrv (one-time, Windows side)
```powershell
# from WSL, download + install on Windows
curl -sL -o "/mnt/c/Users/Admin/Downloads/vcxsrv-installer.exe" \
  "https://github.com/marchaesen/vcxsrv/releases/download/21.1.16.1/vcxsrv-64.21.1.16.1.installer.exe"
powershell.exe -NoProfile -Command "Start-Process -FilePath 'C:\Users\<win-user>\Downloads\vcxsrv-installer.exe' -ArgumentList '/VERYSILENT','/NORESTART' -Wait"
```
Verify: `powershell.exe -NoProfile -Command "Test-Path 'C:\Program Files\VcXsrv\vcxsrv.exe'"`

## Start the X server (Windows side) — VERIFIED 2026-08-13
Known-good arg set:
```
vcxsrv.exe :0 -multiwindow -clipboard -wgl -ac
```
`-ac` = no access control (so WSL can connect). Multiwindow = each X window is a separate
Windows window.

**Launch it DIRECTLY as a background process, not via `cmd.exe /c start`.** From a WSL cwd,
`cmd.exe /c start "" "C:\Program Files\VcXsrv\vcxsrv.exe" ...` returns success silently but the
server never actually appears. Direct launch also captures VcXsrv's own stderr, which is the
only place arg-validation fatals are visible:
```bash
# background=true
"/mnt/c/Program Files/VcXsrv/vcxsrv.exe" :0 -multiwindow -clipboard -wgl -ac
```

### Flag incompatibility that kills the server outright
`-nodecoration` is **INVALID** with `-multiwindow` (and with `-rootless`). VcXsrv exits 1
before it ever binds:
```
winValidateArgs - -nodecoration is invalid with -multiwindow or -rootless.
Fatal server error:
(EE) Server terminated with error (1). Closing log file.
```
Do not add `-nodecoration` trying to strip window borders.

### Confirm it came up
VcXsrv needs a few seconds to bind — `sleep` before probing, and don't declare failure on the
first miss.
```bash
/mnt/c/Windows/System32/tasklist.exe /FI "IMAGENAME eq vcxsrv.exe"   # Windows-side proof
timeout 4 bash -c 'cat < /dev/null > /dev/tcp/<wsl-gateway-ip>/6000' && echo "6000 OPEN"
```

## Find the DISPLAY value (WSL side)
```bash
WINIP=$(powershell.exe -NoProfile -Command "(Get-NetIPAddress -InterfaceAlias 'vEthernet*' -AddressFamily IPv4).IPAddress" | tr -d '\r')
: "${WINIP:=<wsl-gateway-ip>}"
echo "DISPLAY=$WINIP:0"
```
Fallback also available from `ip route | grep default` (the WSL default gateway IS the Windows
host IP).

## Launch the app — use the guarded launcher, NOT a bare `./Hermes`
```bash
/<home>/launch-hermes-right.sh    # background=true
```
This applies the GPU guards, writes `/tmp/hermes_desktop.log`, holds the
`/tmp/launch-hermes-right.lock` single-instance guard, and auto-parks the window on the
far-right monitor. A bare `./Hermes --no-sandbox` omits the GPU flags and invites the SIGTRAP
crash — see `references/crash-diagnosis.md`.

Manual equivalent if you need it:
```bash
export DISPLAY=$WINIP:0
cd ~/.hermes/hermes-agent/apps/desktop/release/linux-unpacked
./Hermes --no-sandbox --disable-gpu --disable-gpu-sandbox --disable-software-rasterizer \
         --window-position=1920,0 --window-size=1050,1680
```

## Verify — and the two traps that produce FALSE negatives

### Trap 1: probing with a tool that isn't installed
`xdpyinfo` is NOT installed in this WSL env. The common check
`DISPLAY=$WINIP:0 xdpyinfo >/dev/null 2>&1 && echo OK || echo UNREACHABLE`
prints **UNREACHABLE** purely because the binary is missing (exit 127) — it says nothing about
the X server. VERIFIED 2026-08-13: this one-liner sent a session chasing a firewall ghost while
VcXsrv was fine.

Ground truth is the dependency-free TCP probe:
```bash
timeout 4 bash -c 'cat < /dev/null > /dev/tcp/'"$WINIP"'/6000' && echo "6000 OPEN"
```
Port 6000 OPEN = X server listening, full stop. If any probe reports failure, run
`which <tool>` and check the RAW exit (`${PIPESTATUS[0]}`) before believing it. Never pipe a
first-pass probe through `grep` — grep matching nothing looks identical to the tool being
absent. Print raw output first, filter second.

### Trap 2: looking for a Windows process named "Hermes"
`Get-Process -Name Hermes` returns **EMPTY even when the app is running and visible**. The
Electron app is an X CLIENT in WSL; it has no Windows process. The on-screen window is owned by
**vcxsrv.exe**. Correct Windows-side check:
```bash
powershell.exe -NoProfile -Command "Get-Process -Name vcxsrv -ErrorAction SilentlyContinue | ForEach-Object { 'PID=' + \$_.Id + ' MainTitle=[' + \$_.MainWindowTitle + ']' }"
# → PID=15908 MainTitle=[Hermes]   ← window is real and titled
```

### Healthy-state checklist
```bash
ps aux | grep "[l]inux-unpacked/Hermes"   # ~4 procs; renderer at high %CPU = actively painting
cat /tmp/hermes_desktop.log               # expect the GPU-disable line + install stamp
```
`ERR_CONNECTION_REFUSED` on `http://127.0.0.1:8788/` in that log is **BENIGN** — a stale probe
from older builds. The desktop spawns its own backend on an ephemeral port.

## Park the window on a monitor
```bash
powershell.exe -NoProfile -ExecutionPolicy Bypass \
  -File "$(wslpath -w ~/.hermes/skills/devops/hermes-desktop-wsl/scripts/move-hermes.ps1)" \
  -X 1920 -Y 0 -W 1050 -H 1680
# → MOVED Hermes HWND=1575336 -> x=1920 y=0 1050x1680
```
Note `wslpath -w` — `-File` with a raw WSL path fails. Always pass explicit W/H.

## Stop (prefer NOT killing — it triggers approval + may kill shell)
If you must: `pkill -x Hermes` then `rm -f ~/.config/Hermes/SingletonLock`.
