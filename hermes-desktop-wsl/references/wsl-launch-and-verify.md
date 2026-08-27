# Running the Hermes desktop app under WSL2 (VcXsrv + DISPLAY playbook)

Verified end-to-end 2026-08-09. The desktop app is Electron; WSL2 has no
display by default. Without this, the app "runs" but paints no window — you
can't see or verify any plugin you build.

## 1. Install VcXsrv (Windows side)
- Source: github.com/marchaesen/vcxsrv (latest ~21.1.16.1).
- Download the `vcxsrv-64.*.installer.exe` to Windows, run silently:
  `vcxsrv-64.21.1.16.1.installer.exe /VERYSILENT /NORESTART`
- Verify: `C:\Program Files\VcXsrv\vcxsrv.exe` exists.

## 2. Launch the X server (Windows side, PowerShell)
```powershell
Start-Process 'C:\Program Files\VcXsrv\vcxsrv.exe' -ArgumentList ':0','-multiwindow','-ac','-clipboard','-wgl'
```
It listens on the **Windows host IP** on `:0` (X port 6000). Find that IP:
```powershell
(Get-NetIPAddress -InterfaceAlias 'vEthernet*' -AddressFamily IPv4).IPAddress
# e.g. <wsl-gateway-ip>  (NOT 127.0.0.1, NOT the WSL guest IP)
```

## 3. Launch the app (WSL side)
```bash
export DISPLAY=<wsl-gateway-ip>:0          # the Windows host IP from step 2, NOT localhost
cd ~/hermes-agent/apps/desktop/release/linux-unpacked
./Hermes --no-sandbox                  # binary is 'Hermes' (capital H)
# or: hermes desktop   (wraps build + launch)
```
`--no-sandbox` is REQUIRED: the Electron Linux sandbox helper can't be
configured without sudo; the build's "Failed to configure Electron's Linux
sandbox helper" is non-fatal but blocks launch without the flag.

## 4. Verify the X server is reachable (from WSL)
```bash
timeout 3 bash -c 'echo > /dev/tcp/<wsl-gateway-ip>/6000' && echo "X server reachable"
```
If "not reachable", the X server isn't running or DISPLAY points at the wrong
IP. `localhost:6000` will NOT work — WSL2 NAT hides the Windows host loopback.

## 5. Build layout facts
- First `hermes desktop` builds Electron → `apps/desktop/release/linux-unpacked/`.
- The executable is **`Hermes`** (capital H). `./hermes: not found` = wrong case.
- The desktop app boot log: `~/.hermes/logs/desktop.log`.

## 6. Headless-backend degradation (don't panic)
If the desktop app's backend is the headless `hermes serve` variant, the
renderer logs:
`Error invoking remote method 'hermes:api': Timed out connecting to Hermes backend after 60000ms`
The WINDOW still paints, but in-app chat/API is degraded. Fix: run the normal
gateway (`hermes gateway run`) so the desktop app's backend is the full one,
not the `serve` headless variant. The plugin-loading path is unaffected — a
plugin with no load-error toast is loaded regardless.

## 7. Verify a plugin (no screenshot tool in WSL)
- `node --check ~/.hermes/desktop-plugins/<id>/plugin.js` — catches syntax
  errors the app would throw on load.
- The app hot-reloads on save; ⌘K → "Reload desktop plugins" forces it.
- NO "Plugin <name> failed to load" toast in desktop.log/gui.log = loaded.
- Visual confirmation needs the real display (your Windows desktop via VcXsrv).

## In-memory artifacts gotcha (plugin design constraint)
Artifacts (generated HTML/SVG/code, sandboxed right-rail preview) live in the
desktop app's in-memory nanostore (`$artifactRegistry`,
`apps/desktop/src/store/artifacts.ts`). There is **NO gateway RPC and NO
dashboard endpoint** exposing them — confirmed by grepping `hermes_cli/` and
`web_server.py` (zero artifact APIs). A plugin CANNOT read the registry from
outside the app's JS context.

Therefore a "render Hermes artifacts" plugin must NAVIGATE to the native page
(`host.navigate('/artifacts')`) rather than read `$artifactRegistry` or
reimplement the sandbox renderer. The built-in Artifacts page IS the canonical
sandboxed renderer. See `templates/preview-pane-plugin.js` for the hybrid
URL-preview + Artifacts-navigator pattern that respects this constraint.
