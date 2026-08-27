# Sparse core-dump RIP extraction (Electron/V8 crash triage)

When the Hermes desktop (or any Electron app) SIGSEGVs, the fastest way to confirm
the crash and find the faulting address is to capture a core dump and parse
`NT_PRSTATUS`. This works WITHOUT gdb (which often isn't installed and needs sudo).
It's what proved the 2026-08-13 crash was `si_signo=11` (SIGSEGV) in V8 JIT code.

## Capture
```bash
# The core lands in the process's cwd. Set ulimit in that shell + cwd to the app dir.
ulimit -c unlimited
cd ~/.hermes/hermes-agent/apps/desktop/release/linux-unpacked
exec ./Hermes --no-sandbox --disable-gpu --disable-gpu-sandbox --disable-software-rasterizer
# wait past the crash -> core.<pid> appears (can be 1.4TB apparent but only ~22MB real on disk)
```
`ls -lh core.*` shows the huge apparent size; `du -h` shows the real blocks — it is
SPARSE, so never `open().read()` it whole (MemoryError). Always `seek()` to the note.

## Parse (Python, stdlib only)
```python
import struct, subprocess

core = "core.<pid>"
out = subprocess.run(["readelf","-l",core],capture_output=True,text=True).stdout
note_off = next(int(s[1],16) for s in (l.split() for l in out.splitlines())
                if s and s[0]=="NOTE")          # NOTE segment file offset

with open(core,"rb") as f:
    f.seek(note_off)
    while True:
        hdr = f.read(12)
        if len(hdr) < 12: break
        namesz, descsz, ntype = struct.unpack("<III", hdr)
        f.read((namesz+3)//4*4)                 # skip note name
        if ntype == 1:                          # NT_PRSTATUS
            h = f.read(112)                      # elf_prstatus header (si_signo at 0)
            print("si_signo =", struct.unpack_from("<i", h, 0)[0])   # 11 = SIGSEGV
            regs = struct.unpack("<27Q", f.read(216))
            print("RIP = 0x%x" % regs[16])       # x86_64: rip is the 16th of 27 regs
            break
        f.read(descsz)
```
- The `elf_prstatus` reg block is NOT at the note-descriptor start: there is a ~112-byte
  header (`elf_siginfo`, cursig, sigpend/sighold, pids, four timevals) before `pr_reg`.
  Getting this offset wrong makes RIP/cs/eflags read as garbage (e.g. cs holding a stack
  address) — a reliable sign your offset is off by a few bytes.
- Registers order (x86_64): r15,r14,r13,r12,rbp,rbx,r11,r10,r9,r8,rax,rcx,rdx,rsi,rdi,
  orig_rax,rip,cs,eflags,rsp,ss,fs_base,gs_base,ds,es,fs,gs.

## Interpreting RIP
- `addr2line -f -e Hermes <rip>` → `??:0` AND rip not inside any file-backed PT_LOAD
  segment → the fault is in **V8 JIT code** (high VM addresses like `0x5dc8...a83b`,
  ASLR-randomized base per process). That means a JS/renderer bug, not a native lib or GPU
  driver fault. Don't chase the GPU flags for signal 11 if the GPU guards are already on.
- `dmesg | grep -i "fatal signal"` shows `Hermes: potentially unexpected fatal signal 11`
  at a very regular cadence → deterministic recurring JS op, not a one-off.
- The stack near RSP is often NOT dumped (the sparse core has holes) → manual stack
  unwinding fails; rely on RIP + cadence + process-tree evidence instead.

## Triage checklist (what to rule out before blaming the app renderer)
1. Duplicate monitor loops? `ps aux | grep launch-hermes` — two loops fight the Electron
   single-instance lock and churn rc=137. Fix: single-instance lockfile guard (see the
   launcher). Rule this out FIRST — it looks identical to a renderer crash.
2. Plugin? temporarily `mv` the `~/.hermes/desktop-plugins/*/` dir aside, relaunch, watch
   past the crash cadence. (2026-08-13: k8s preview-pane plugin was NOT the cause.)
3. OS memory? `free -h` (WSL) + Windows `Get-CimInstance Win32_OperatingSystem` — the
   1.4TB sparse core is virtual address space, NOT RAM pressure.
4. Only then: app renderer/JIT bug → capture core, confirm si_signo, report cadence.

## Housekeeping
Delete the sparse core after analysis (`rm core.*`). A 1.4TB-apparent file on a
shared/home FS is a footgun even though it only occupies ~22MB.
