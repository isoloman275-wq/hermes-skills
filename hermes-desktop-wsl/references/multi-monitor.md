# Multi-monitor positioning — Hermes desktop under WSL + VcXsrv

## Symptom
Window "stuck" — can't move it, appears on primary or as a tiny box. Root cause: Hermes
is frameless (`titleBarStyle:"hidden"`); under VcXsrv multiwindow, `--window-position`
and saved `window-state.json` are ignored for cross-display placement. The real Electron
X11 window collapses to ~10x10 at (10,10); only the Windows HWND needs moving.

## 1. Detect monitor layout (write to .ps1, don't inline `$_`)
```powershell
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.Screen]::AllScreens | ForEach-Object {
    $b = $_.Bounds
    "$($b.Width)x$($b.Height)@$($b.X),$($b.Y) primary=$($_.Primary)"
}
```
Run: `powershell.exe -NoProfile -ExecutionPolicy Bypass -File screens.ps1`
Example 3-monitor rig:
  PRIMARY  1920x1080@0,0
  RIGHT    1050x1680@1920,0   <- frameless portrait, good for parking Hermes
  LEFT     1600x900@-1600,0

## 2. Verify actual window geometry (Windows API)
```powershell
Add-Type @"
using System;using System.Runtime.InteropServices;
public class Win{ [DllImport("user32.dll")] public static extern IntPtr FindWindow(string c,string t);
[DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h,out RECT r);
[StructLayout(LayoutKind.Sequential)] public struct RECT{public int L,T,R,B;}
public static void Main(){ IntPtr h=FindWindow(null,"Hermes"); if(h==IntPtr.Zero){System.Console.WriteLine("NO Hermes window");return;}
RECT r; GetWindowRect(h,out r); System.Console.WriteLine("LEFT="+r.L+" TOP="+r.T+" RIGHT="+r.R+" BOTTOM="+r.B+" W="+(r.R-r.L)+" H="+(r.B-r.T)); } }
"@
[Win]::Main()
```

## 3. Verify at the X11 layer (python-xlib)
X screen spans ALL monitors (e.g. 4570x1680 for 1600+1920+1050). If `python-xlib` is
missing on WSL: `pip install --break-system-packages python-xlib`.
```python
from Xlib import display
d = display.Display("<wsl-gateway-ip>:0")   # use the REAL WINIP from step 1 of Launch
root = d.screen().root
def walk(w):
    try:
        cls = w.get_wm_class(); name = w.get_wm_name()
    except Exception: return
    if cls and 'Hermes' in str(cls):
        g = w.get_geometry()
        print(cls, name, "X=",g.x,"Y=",g.y,"W=",g.width,"H=",g.height)
    for c in w.query_tree().children: walk(c)
walk(root)
```
A frameless window that "won't move" typically shows as `('Hermes','Hermes')` at X=10 Y=10
size 10x10 — confirm with this probe before assuming it's a position bug.

## 4. Move it — SetWindowPos nudge (the fix)
See `scripts/move-hermes.ps1`. Run after launch:
`powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/move-hermes.ps1 -X 1920 -Y 40 -W 1000 -H 1600`
ALWAYS pass explicit W/H — passing 0 collapses the window to 0x0.

## 5. Permanent "always on monitor X"
`scripts/launch-hermes-right.sh X Y W H` launches Hermes and auto-nudges to x,y after ~5s.

## Gotchas
- `Win+Shift+←/→` does nothing while fullscreened -> F11 first.
- The binary reads `resources/app.asar` + `app.asar.unpacked/dist/electron-main.mjs`,
  NOT `apps/desktop/dist/electron-main.mjs`. Patching asar is futile here; use SetWindowPos.
- Inline PowerShell with `$_` breaks under bash double-quotes — use a `.ps1` file.
- `FindWindow(null,"Hermes")` matches the VcXsrv-managed HWND (title "Hermes"); that is the
  handle SetWindowPos must move.
