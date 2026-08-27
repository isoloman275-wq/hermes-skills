# VcXsrv setup for Hermes desktop app on WSL → Windows

Verified commands used 2026-08-09 (WSL2, Windows 11, Hermes v0.20.0).

## 1. Download installer (from WSL, write to Windows Downloads)
```bash
curl -sL -o "/mnt/c/Users/Admin/Downloads/vcxsrv-64.21.1.16.1.installer.exe" \
  "https://github.com/marchaesen/vcxsrv/releases/download/21.1.16.1/vcxsrv-64.21.1.16.1.installer.exe"
# Check latest tag: https://api.github.com/repos/marchaesen/vcxsrv/releases/latest
```

## 2. Install silently (run from Windows side via powershell.exe)
```powershell
powershell.exe -NoProfile -Command "Start-Process -FilePath 'C:\Users\<win-user>\Downloads\vcxsrv-64.21.1.16.1.installer.exe' -ArgumentList '/VERYSILENT','/NORESTART' -Wait; Write-Host INSTALL_DONE"
# Verify: Test-Path 'C:\Program Files\VcXsrv\vcxsrv.exe'
```

## 3. Launch X server (Windows side)
```powershell
powershell.exe -NoProfile -Command "Start-Process -FilePath 'C:\Program Files\VcXsrv\vcxsrv.exe' -ArgumentList ':0','-multiwindow','-ac','-clipboard','-wgl'"
```

## 4. Find the Windows host IP WSL must use for DISPLAY (NOT localhost)
```powershell
powershell.exe -NoProfile -Command "(Get-NetIPAddress -InterfaceAlias 'vEthernet*' -AddressFamily IPv4).IPAddress"
# e.g. <wsl-gateway-ip>
```
WSL2: `localhost:6000` does NOT reach the Windows X server. Use the IP above:
```bash
export DISPLAY=<wsl-gateway-ip>:0
```

## 5. Launch Hermes desktop
```bash
# Build once (packs Electron):
hermes desktop
# Then launch the binary directly with the right DISPLAY:
cd /<home>/.hermes/hermes-agent/apps/desktop/release/linux-unpacked
DISPLAY=<wsl-gateway-ip>:0 ./Hermes --no-sandbox
# --no-sandbox required: the Linux sandbox helper needs sudo (unavailable non-interactively)
```

## Notes
- X server reachable test from WSL: `timeout 3 bash -c 'echo > /dev/tcp/<IP>/6000'`
- The window appears on the Windows desktop (VcXsrv multiwindow mode).
- `hermes desktop` first run builds electron 40.x (~1-3 min); subsequent runs are fast.
