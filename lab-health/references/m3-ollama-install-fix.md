# M3 Ollama Install Fix (verified 2026-08-21)

## Root cause of all M3 Ollama flakiness this session
1. **Incomplete install** — only `ollama.exe` was copied to
   `C:\Program Files\Ollama\`. Ollama needs the backend at
   `C:\Program Files\Ollama\lib\ollama\llama-server.exe`. Without it, the
   service starts, `/api/tags` lists models, but GPU discovery fails:
   `failure during llama-server GPU discovery: llama-server binary not found`
   → falls back to CPU (0 B VRAM) or dies on load.
2. **Session-bound launch** — `Start-Process` / `cmd /c start` from an SSH
   session ties Ollama to the SSH process tree. When the session ends, the
   process is killed → "Ollama disappeared between checks."

## Fix (run on M3 via `ssh m3`)
```powershell
# 1. stop any broken instance
Get-Process ollama -ErrorAction SilentlyContinue | Stop-Process -Force

# 2. copy the FULL lib tree (has llama-server.exe)
Copy-Item 'C:\ollama_tmp\lib' 'C:\Program Files\Ollama\lib' -Recurse -Force
Test-Path 'C:\Program Files\Ollama\lib\ollama\llama-server.exe'   # must be True

# 3. write the launch wrapper .bat (cd /d matters)
#    content of C:\ollama_serve.bat:
#      @echo off
#      cd /d "C:\Program Files\Ollama"
#      "C:\Program Files\Ollama\ollama.exe" serve

# 4. scheduled task as SYSTEM, 5-min watchdog (survives reboot + disconnect)
schtasks /Delete /TN 'OllamaServe' /F
schtasks /Create /TN 'OllamaServe' /TR 'C:\ollama_serve.bat' /SC MINUTE /MO 5 /RU SYSTEM /F

# 5. launch via the task (NOT Start-Process)
schtasks /Run /TN 'OllamaServe'
Start-Sleep 8

# 6. verify — from M3 itself (localhost is reliable; WSL cross-node is best-effort)
(Invoke-RestMethod http://localhost:11434/api/tags).models.name
# expect: <your-model>  <your-model>

# 7. real inference test (tool-calling works)
$body = @{model='<your-model> messages=@(@{role='user';content='What is 17 times 23? Answer with only the number.'}); think=$false; stream=$false} | ConvertTo-Json -Depth 5
$r = Invoke-RestMethod -Uri http://localhost:11434/api/chat -Method Post -ContentType 'application/json' -Body $body
$r.message.content.Trim()   # -> "391"
$r.message.tool_calls       # -> proper function-call object if tools passed
```

## WSL → M3 reachability note
WSL curl to `http://<lab-host>:11434` is unreliable even after the
`Ollama-In-11434` firewall rule — WSL's NAT (172.x) may not match M3's
Windows Firewall scoping (allows <lab-host>). Always verify M3 Ollama
FROM M3 (SSH + localhost), never conclude "M3 down" from an empty WSL curl.

## Watchdog behaviour
If Ollama dies (crash/disconnect), the 5-min SYSTEM task relaunches it.
Max gap = 5 min. M3 is a real worker node once this is in place.
