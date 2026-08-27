# Windows conhost → parent process trace (find rogue terminal owners)

Use this when the user reports "terminals pop out of nowhere" on the Windows desktop and you
need to find which process owns each visible console window. Every visible console window has a
`conhost.exe`; its `ParentProcessId` is the process that opened it. Kill the parent → the window dies.

## WSL → PowerShell quoting GOTCHAS (burned us twice)
- Backslashes in `-File 'C:\Users\<win-user>\x.ps1'` get STRIPPED by the shell if not single-quoted.
  Always single-quote the Windows path: `powershell.exe -File 'C:\Users\<win-user>\x.ps1'`.
- Do NOT inline a multi-line `Get-CimInstance` pipeline through `powershell.exe -Command "..."` —
  `$($_.ParentProcessId)` subexpressions and backticks get mangled by the shell. Write a `.ps1`
  file to a WINDOWS path (PowerShell can't see `/home/...` via `-File`), then run it.
- `Start-Sleep -2` errors ("less than minimum allowed range 0") — negative seconds are invalid.
  Use `Start-Sleep -Seconds 2` (positive) or just omit the sleep.

## The reliable one-shot probe
1. Write a `.ps1` to a Windows path: `cp /<home>/x.ps1 /mnt/c/Users/Admin/x.ps1`
2. Run it: `powershell.exe -NoProfile -ExecutionPolicy Bypass -File 'C:\Users\<win-user>\x.ps1'`

## Probe script (maps conhost → parent → command line)
```powershell
$conhosts = Get-CimInstance Win32_Process -Filter "Name='conhost.exe'"
foreach ($c in $conhosts) {
    $pp = Get-CimInstance Win32_Process -Filter "ProcessId=$($c.ParentProcessId)" -ErrorAction SilentlyContinue
    $pname = if ($pp) { $pp.Name } else { 'EXPIRED' }
    $pcmd  = if ($pp) { $pp.CommandLine } else { '' }
    "$($c.ProcessId) -> parent $($c.ParentProcessId) [$($pname)] $($pcmd)"
}
```

## Deciding what is benign vs rogue
Kill only conhosts whose parent is an orchestrator/listener. Benign parents seen in this lab:
- `postgres.exe`, `ollama.exe`, `wslhost.exe`, `WindowsTerminal.exe` (your own terminal), AMD `cmd.exe`

Rogue parents (kill their python process — BOTH `python.exe` AND `pythonw.exe`):
- `... orchestrator.py`
- `... jarvis_ear.py`  (OLD TTS listener — confirmed OBSOLETE 2026-07-18, safe to keep off)
- `... jarvis_mouth.py` (same — obsolete)

## Killing the owner — and the SELF-RESPAWN gotcha
```powershell
Stop-Process -Id <PARENT_PID> -Force -ErrorAction SilentlyContinue
```
- `jarvis_ear.py` ran as `pythonw.exe` (windowless) with a SELF-RESPAWN loop:
  `pythonw 10964` spawned child `pythonw 19412`. Killing only the visible `python.exe` instance
  left the `pythonw` orphan alive → pop-ups CONTINUED. Match `pythonw` too.
- Kill parent AND child. Then VERIFY nothing remains:
  `Get-Process -Name python,pythonw | Where-Object { $_.Path -match 'jarvis_ear|orchestrator' }`
  If anything is left, kill it. Re-run the conhost probe to confirm no rogue conhosts remain.

## Making it survive reboot (permanent)
Enumerate: `Get-ScheduledTask | Where-Object { $_.TaskName -match '<content-pipeline>|Pipeline|Orchestrat|Jarvis' }`
Disable each (keeps config for later relaunch — matches "pause crons till launch" intent):
```powershell
Disable-ScheduledTask -TaskName '<content-pipeline>PipelineOrchestrator'
```
Only use `Unregister-ScheduledTask -TaskName X -Confirm:$false` if the user wants it GONE permanently.
**CRITICAL:** disabling the task does NOT kill the already-running process. Kill the live PIDs
(above) AFTER disabling, then re-verify with `Get-Process`. The `<content-pipeline>DaemonWatchdog` task will
relaunch `orchestrator.py` if it dies — disable that too or the orchestrator returns.

## Worked example (2026-07-18, corrected)
1. Paused all 14 Hermes crons — pop-ups CONTINUED (crons were not the source).
2. conhost 7356 -> parent 7008 [python.exe] jarvis_ear.py ; conhost 15740 -> parent 15632 [python.exe] orchestrator.py
3. Killed 7008, 10492 (jarvis_ear x2 as python.exe), 15632 (orchestrator). Pop-ups kept coming.
4. SECOND pass found orphan: `pythonw 10964` (jarvis_ear.py) + child `pythonw 19412`, parent EXPIRED
   (self-respawned). Killing both stopped it.
5. Disabled 8 Windows tasks: Jarvis Ear, Jarvis Mouth, <content-pipeline>Pipeline, <content-pipeline>PipelineOrchestrator,
   <content-pipeline>DayPost, <content-pipeline>NightRender, <content-pipeline>DaemonWatchdog, DryCh2v2. (UIEOrchestrator = Windows system, left alone.)
6. Re-verified: no python/pythonw running jarvis_ear/orchestrator. Clean.

Lesson: pausing crons + killing the visible python.exe is NOT enough. Hunt `pythonw`, kill parent+child,
disable the watchdog task, and re-verify until zero rogue PIDs remain.
