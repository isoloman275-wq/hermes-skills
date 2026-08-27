# Create a Windows desktop .lnk shortcut from WSL

Give the user a one-double-click way to relaunch the Hermes desktop app (with the
GPU-guarded, auto-relaunch, auto-park launcher) without asking the agent. VERIFIED
2026-08-10: shortcut lands as `C:\Users\<win-user>\Desktop\Hermes Desktop.lnk`.

## Key gotchas (both cost attempts in one session)

1. **`powershell.exe -File <wsl-path>.ps1` FAILS.** The Windows-side PowerShell process
   cannot resolve a WSL filesystem path like `/<home>/x.ps1`; it errors with
   "The argument ... does not exist." WSL2 mounts are NOT visible to `-File` resolution
   the way you'd expect.
   **Fix: pipe the script body in via `-Command -` (reads the script from stdin):**
   ```
   powershell.exe -NoProfile -ExecutionPolicy Bypass -Command - < /<home>/create-shortcut.ps1
   ```
   This works and the script's own `[Environment]::GetFolderPath('Desktop')` resolves
   the real Windows desktop (`C:\Users\<win-user>\Desktop` on this rig).

2. **The shortcut's TARGET must go through `wsl.exe`, and must invoke the LAUNCHER, not
   the bare binary.** Bare `./Hermes` omits the GPU-disable flags and SIGTRAPs. Point the
   target at the watchdog launcher so it gets GPU guards + auto-restart + monitor parking:
   - TargetPath: `C:\Windows\System32\wsl.exe`
   - Arguments: `--exec bash -lc "/<home>/launch-hermes-right.sh"`
   - WorkingDirectory: `C:\Windows\System32`
   - IconLocation: `C:\Windows\System32\wsl.exe,0`

## Known-good script body

```powershell
$ErrorActionPreference = 'Stop'
$desktop = [Environment]::GetFolderPath('Desktop')
$lnkPath = Join-Path $desktop 'Hermes Desktop.lnk'

$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut($lnkPath)

$sc.TargetPath = 'C:\Windows\System32\wsl.exe'
$sc.Arguments  = '--exec bash -lc "/<home>/launch-hermes-right.sh"'
$sc.WorkingDirectory = 'C:\Windows\System32'
$sc.Description = 'Launch Hermes desktop app parked on the far-right monitor'
$sc.IconLocation = 'C:\Windows\System32\wsl.exe,0'
$sc.Save()
Write-Output "Created: $lnkPath"
```

## Verify
- `ls /mnt/c/Users/Admin/Desktop/ | grep -i hermes` → `.lnk` present.
- The shortcut file is storable as a template for reuse:
  `templates/hermes-shortcut.ps1` (substitute the correct Desktop folder if the Windows
  username differs).

## Notes
- The `.lnk` itself is just a launcher shim; the heavy lifting (GPU flags, window-state,
  HWND nudge) stays in `/<home>/launch-hermes-right.sh`, which the shortcut calls.
- Double-clicking opens no console of its own — wsl.exe runs the launcher which keeps the
  app + watchdog alive. Perfect for "relaunch app" without a visible terminal window.
