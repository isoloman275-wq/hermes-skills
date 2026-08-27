# Hermes desktop app on Windows via WSL2 — verified recipe (2026-08-09, updated 2026-08-13)

## 1. Install VcXsrv (Windows side, from WSL)
```bash
# latest release asset
curl -sL "https://api.github.com/repos/marchaesen/vcxsrv/releases/latest" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('\n'.join(a['browser_download_url'] for a in d['assets'] if a['name'].endswith('.exe')))"
# download into Windows Downloads
curl -sL -o /mnt/c/Users/Admin/Downloads/vcxsrv-installer.exe \
  https://github.com/marchaesen/vcxsrv/releases/download/21.1.16.1/vcxsrv-64.21.1.16.1.installer.exe
# install silently (Windows)
powershell.exe -NoProfile -Command "Start-Process -FilePath 'C:\Users\<win-user>\Downloads\vcxsrv-installer.exe' -ArgumentList '/VERYSILENT','/NORESTART' -Wait"
```

## 2. Launch the X server (Windows) — VERIFIED 2026-08-13
Known-good arg set:
```
vcxsrv.exe :0 -multiwindow -clipboard -wgl -ac
```

**Launch the .exe DIRECTLY as a background process** rather than via `cmd.exe /c start`.
From a WSL cwd, `cmd.exe /c start "" "C:\Program Files\VcXsrv\vcxsrv.exe" ...` reports success
silently but the server never appears. Direct launch also captures VcXsrv's stderr, the only
place arg-validation fatals show:
```bash
# background=true
"/mnt/c/Program Files/VcXsrv/vcxsrv.exe" :0 -multiwindow -clipboard -wgl -ac
```

### Flag incompatibility that kills the server before it binds
`-nodecoration` is INVALID with `-multiwindow` (and `-rootless`). VcXsrv exits 1:
```
winValidateArgs - -nodecoration is invalid with -multiwindow or -rootless.
Fatal server error:
(EE) Server terminated with error (1). Closing log file.
```

### Confirm it actually came up (allow a few seconds to bind)
```bash
/mnt/c/Windows/System32/tasklist.exe /FI "IMAGENAME eq vcxsrv.exe"
timeout 4 bash -c 'cat < /dev/null > /dev/tcp/<wsl-gateway-ip>/6000' && echo "6000 OPEN"
```

## 3. Get the Windows host IP WSL must use for DISPLAY
```bash
WINIP=$(powershell.exe -NoProfile -Command "(Get-NetIPAddress -InterfaceAlias 'vEthernet*' -AddressFamily IPv4).IPAddress" | tr -d '\r')
: "${WINIP:=<wsl-gateway-ip>}"
export DISPLAY=$WINIP:0
```
`ip route | grep default` gives the same address — the WSL default gateway IS the Windows host.

## 4. Launch the Hermes desktop app (WSL)
```bash
cd /<home>/.hermes/hermes-agent/apps/desktop/release/linux-unpacked
./Hermes --no-sandbox
```
(Or just `hermes desktop` — builds-if-needed then launches. Binary is `Hermes`, capital H.)
For the Hermes app specifically prefer the guarded launcher
(`/<home>/launch-hermes-right.sh`), which adds the GPU-disable flags, a single-instance
lock, and monitor parking — see the `hermes-desktop-wsl` skill.

## 5. Off-screen window recovery
window-state.json lives at `~/.config/Hermes/window-state.json`. If `x` > screen width the
window is off-screen right. Fix:
```json
{ "x": 100, "y": 100, "width": 1280, "height": 800, "isMaximized": true }
```
Then relaunch (clear SingletonLock first if needed):
```bash
rm -f /<home>/.config/Hermes/SingletonLock
```

## 6. Verify — and the two FALSE-NEGATIVE traps

### Trap 1: probing with a tool that isn't installed
`xdpyinfo` is NOT installed in this WSL env. The idiom
`DISPLAY=$WINIP:0 xdpyinfo >/dev/null 2>&1 && echo OK || echo UNREACHABLE`
prints **UNREACHABLE** purely from exit 127 (missing binary) and says nothing about the X
server. VERIFIED 2026-08-13: this produced a bogus "X SERVER UNREACHABLE" reading and sent a
session chasing a firewall ghost while VcXsrv was perfectly fine.

Ground truth:
```bash
timeout 4 bash -c 'cat < /dev/null > /dev/tcp/'"$WINIP"'/6000' && echo "6000 OPEN"
```
On ANY probe failure: run `which <tool>` and inspect the raw exit (`${PIPESTATUS[0]}`) before
believing the service is down. Never pipe a first-pass probe through `grep` — grep matching
nothing is indistinguishable from the tool being absent. Print raw output first, filter second.
(`sudo apt install x11-utils` supplies `xdpyinfo`, but ASK the user before installing.)

### Trap 2: an X client has NO Windows process
`Get-Process -Name Hermes` on the Windows side returns EMPTY even while the app runs and is
visible — the window is owned by `vcxsrv.exe`. Correct check:
```bash
powershell.exe -NoProfile -Command "Get-Process -Name vcxsrv -ErrorAction SilentlyContinue | ForEach-Object { 'PID=' + \$_.Id + ' MainTitle=[' + \$_.MainWindowTitle + ']' }"
# → PID=15908 MainTitle=[Hermes]
```
Never conclude "the app isn't running" from an empty Windows process list.

### Remaining checks
- App proc: `ps aux | grep "[l]inux-unpacked/Hermes"` — renderer at high %CPU = actively painting.
- Plugin loads clean: grep logs for `preview-pane` + `fail`; silence = OK.
- `node --check ~/.hermes/desktop-plugins/preview-pane/plugin.js` → SYNTAX OK.

## Notes
- "Headless backend (hermes serve): web UI disabled" log line is BENIGN — not a crash.
- `ERR_CONNECTION_REFUSED` on `127.0.0.1:8788` is a stale probe from older builds — also benign.
- No screenshot tool in WSL; confirm visually from the Windows desktop.
- Build once: `hermes desktop` packages to `apps/desktop/release/linux-unpacked/Hermes`.
