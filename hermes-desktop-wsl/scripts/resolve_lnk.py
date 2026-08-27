#!/usr/bin/env python3
"""Resolve a Windows .lnk shortcut's target path from WSL/Linux.
Reads the .lnk binary as UTF-16-LE and extracts path-like strings.
Verified 2026-08-09 on this box: correctly pulled
'C:\\tools\\app_launcher.bat' out of 'Example App.lnk'.

Usage:
  python3 resolve_lnk.py "<win-home>/Desktop/Example App.lnk"
  python3 resolve_lnk.py "/mnt/c/Users/Admin/Desktop/"   # resolves every .lnk
"""
import re, sys, os

PATH_RE = re.compile(r'[ -~]{5,}')


def resolve(lnk_path: str):
    data = open(lnk_path, 'rb').read()
    s = data.decode('utf-16-le', errors='ignore')
    hits = []
    for m in PATH_RE.finditer(s):
        t = m.group(0)
        if any(k in t for k in ('.exe', ':\\', '.bat', '.cmd', '.js', '.ps1',
                                 'node', 'python', 'http', '.app', '.sh')):
            hits.append(t)
    # de-dup, keep order
    seen, out = set(), []
    for h in hits:
        if h not in seen:
            seen.add(h); out.append(h)
    return out


if __name__ == '__main__':
    args = sys.argv[1:]
    if not args:
        print("usage: resolve_lnk.py <file.lnk|dir>")
        sys.exit(2)
    for arg in args:
        if os.path.isdir(arg):
            for f in sorted(os.listdir(arg)):
                if f.lower().endswith('.lnk'):
                    print(f"=== {f} ===")
                    for h in resolve(os.path.join(arg, f)):
                        print("   ", h)
        else:
            print(f"=== {arg} ===")
            for h in resolve(arg):
                print("   ", h)
