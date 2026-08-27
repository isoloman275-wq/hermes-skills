#!/usr/bin/env python3
"""Fleet verification gate: after a worker completes, run independent verifier
on its output before allowing kanban_complete."""

import subprocess
import os
import sqlite3
from datetime import datetime

KANBAN_DB = os.path.expanduser("~/.hermes/kanban/boards/overnight-build/kanban.db")
VERIFIER_PROFILE = "independent-verifier"

def get_recent_done_cards():
    if not os.path.exists(KANBAN_DB):
        return []
    conn = sqlite3.connect(KANBAN_DB)
    c = conn.cursor()
    c.execute("SELECT id, title, assignee, updated_at FROM cards WHERE status='done' AND updated_at > datetime('now','-30 minutes') ORDER BY updated_at DESC")
    cards = [{'id':r[0],'title':r[1],'assignee':r[2]} for r in c.fetchall()]
    conn.close()
    return cards

def check_verification(card_id):
    if not os.path.exists(KANBAN_DB): return False
    conn = sqlite3.connect(KANBAN_DB)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM comments WHERE card_id=? AND content LIKE '%VERIFIED%'", (card_id,))
    count = c.fetchone()[0]
    conn.close()
    return count > 0

def run_verification(card_id, title):
    print(f"  Verifying {card_id}: {title[:60]}...")
    conn = sqlite3.connect(KANBAN_DB)
    c = conn.cursor()
    c.execute("SELECT workspace_path FROM cards WHERE id=?", (card_id,))
    row = c.fetchone()
    conn.close()
    if not row or not row[0] or not os.path.exists(row[0]):
        print(f"    No workspace"); return False
    files = [f for f in os.listdir(row[0]) if os.path.isfile(os.path.join(row[0], f))]
    if not files: print(f"    No output files"); return False
    try:
        with open(os.path.join(row[0], files[0])) as f: content = f.read(1000)
    except: print(f"    Can't read"); return False
    prompt = f"You are an independent verifier. Worker completed: {title}\nOutput: {', '.join(files[:5])}\nSample: {content}\nDoes this meet requirements? PASS or FAIL with one-line reason."
    result = subprocess.run(["hermes","-p",VERIFIER_PROFILE,"--cli","chat","-q",prompt], capture_output=True, text=True, timeout=120)
    response = result.stdout.strip()
    is_pass = "PASS" in response.upper() and "FAIL" not in response.upper()
    conn = sqlite3.connect(KANBAN_DB)
    c = conn.cursor()
    c.execute("INSERT INTO comments (card_id,author,content,created_at) VALUES (?,?,?,?)",
              (card_id, 'verifier', f"{'VERIFIED PASS' if is_pass else 'VERIFIED FAIL'}: {response[:200]}", datetime.now().isoformat()))
    conn.commit(); conn.close()
    print(f"    {'PASS' if is_pass else 'FAIL'}: {response[:80]}")
    return is_pass

def main():
    cards = get_recent_done_cards()
    if not cards: print("No recent done cards"); return
    print(f"Checking {len(cards)} recent done cards...")
    v=f=s=0
    for card in cards:
        if check_verification(card['id']): s+=1; continue
        if card['assignee'] in ['default'] or card['assignee'] not in ['builder','coder']: s+=1; continue
        try:
            if run_verification(card['id'], card['title']): v+=1
            else: f+=1
        except Exception as e: print(f"    Error: {e}"); f+=1
    print(f"\nResults: {v} verified, {f} failed, {s} skipped")

if __name__ == "__main__": main()
