# M3 Windows OpenSSH Setup — Troubleshooting Reference

Machine: <lab-host>, Windows 10 LTSC IoT, user `admin`

## Common failures encountered

### 1. PubkeyAuthentication is commented out by default
Win32-OpenSSH ships with `#PubkeyAuthentication yes`. Must uncomment:
```powershell
(Get-Content "C:\ProgramData\ssh\sshd_config") -replace "^#PubkeyAuthentication yes", "PubkeyAuthentication yes" | Set-Content "C:\ProgramData\ssh\sshd_config"
Restart-Service sshd
```

### 2. Key corrupted by terminal line wrapping
Both PowerShell and CMD wrap long SSH keys at column ~80, inserting newlines that break the key format. Two reliable methods to write a clean key:

**Method A — String concatenation (PowerShell):**
```powershell
$key = "AAAAC3NzaC1lZDI1NTE5" + "AAAAIGYR5so04BLWNs+VKGNWptsKPgXGbNVR/JAg/8qOVjRY"
$k = "ssh-ed25519 " + "$key" + " <user>@<win-host>"
Set-Content "$env:USERPROFILE\.ssh\authorized_keys" -Value $k -NoNewline
```

**Method B — base64 tunnel (most reliable, avoids all CRLF/wrap issues):**
```bash
# On M1 (WSL), get base64 of the public key:
base64 -w0 ~/.ssh/id_ed25519.pub
```
```powershell
# On M3 (PowerShell), decode and write atomically:
$key = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String("c3NoLWVkMjU...base64data...")).Trim()
[System.IO.File]::WriteAllText("$env:USERPROFILE\.ssh\authorized_keys", $key)
```
Critical: use `[System.Text.Encoding]::UTF8.GetString()` around `FromBase64String()` — raw bytes don't have `.Trim()` and will fail.

**Method C — CMD echo (no wrapping issues):**
```cmd
echo ssh-ed25519 AAAAC3NzaC...keydata... <user>@<win-host> >"%USERPROFILE%\.ssh\authorized_keys"
```

### 3. Truncated key — partial base64 decode failure
If you paste the full key into PowerShell without concatenation, it wraps mid-base64 and produces a DIFFERENT key value (e.g., prefix characters dropped). Always verify with:
```powershell
Get-Content "$env:USERPROFILE\.ssh\authorized_keys" -Raw
```
The output must be exactly one line with no embedded newlines.

### 4. Debugging — use verbose SSH from client side to see what key is being offered:
```bash
ssh -vv admin@<lab-host> whoami 2>&1 | grep "Offering\|Server accepts"
```
The SHA256 fingerprint after "Offering public key:" must match `sha256sum ~/.ssh/id_ed25519.pub`.

## Current working credentials
- SSH key: `/<home>/.ssh/id_ed25519` on M1 → authorized_keys on M3
- Host aliases in `~/.ssh/config`: `m3` resolves to <lab-host>:user=admin
