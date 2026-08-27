param(
  [int]$X = 1920,
  [int]$Y = 0,
  [int]$W = 1050,
  [int]$H = 1680
)
# Move the Hermes desktop window to a target monitor via the Windows HWND.
# Frameless Electron under VcXsrv ignores --window-position cross-display, so this
# SetWindowPos nudge is the reliable method. ALWAYS pass real W/H.
#
# FIX #1 (2026-08-10): FindWindow(null,"Hermes") fails to locate the window under
#   VcXsrv (returns NULL though the window exists, title "Hermes", class "vcxsrv/x X rl").
#   Replaced with EnumWindows + title match, which provably finds it. This made the
#   launcher's nudge silently no-op (`|| true`) leaving garbage geometry (bottom=65535).
# FIX #2 (2026-08-10): PowerShell variable names are CASE-INSENSITIVE. Using `$h` for both
#   the HWND handle AND the `$H` height param meant Find()'s result OVERWROTE the height
#   (e.g. `1050x1311392` where 1311392 was the HWND). Renamed handle to `$hwnd` throughout.
Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;
public class MoveHermes {
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc c, IntPtr l);
  [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int w, int ht, uint flags);
  const uint SWP_NOZORDER = 0x0004;

  public static IntPtr Find() {
    IntPtr found = IntPtr.Zero;
    EnumProc cb = delegate(IntPtr h, IntPtr l) {
      var t = new StringBuilder(256);
      GetWindowText(h, t, 256);
      if (IsWindowVisible(h) && t.ToString().Equals("Hermes", StringComparison.OrdinalIgnoreCase)) {
        found = h;
      }
      return true;
    };
    EnumWindows(cb, IntPtr.Zero);
    return found;
  }
  public static bool To(IntPtr h, int x, int y, int w, int ht) {
    return SetWindowPos(h, IntPtr.Zero, x, y, w, ht, SWP_NOZORDER);
  }
}
"@
[MoveHermes]::SetProcessDPIAware() | Out-Null
$hwnd = [MoveHermes]::Find()
if ($hwnd -eq [IntPtr]::Zero) { Write-Host "NO Hermes window found"; exit 1 }
$ok = [MoveHermes]::To($hwnd, $X, $Y, $W, $H)
Write-Host $(if ($ok) { "MOVED Hermes HWND=$hwnd -> x=$X y=$Y ${W}x${H}" } else { "SetWindowPos failed" })
