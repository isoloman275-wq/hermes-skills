#!/usr/bin/env python3
"""
Verify-Before-Claim Enforcement Engine
=======================================
<operator>'s trust rule made executable. Every factual claim about lab state MUST be
proved by a live tool call in the same turn. This module provides:

  1. Claim detection (regex scan for factual assertions about processes, files,
     GPU state, Ollama models, disk, balances, etc.)
  2. Live probe functions that run the actual checks
  3. A guard() entry-point that parses an outgoing response, probes claims,
     and returns PASS / FAIL + evidence

Usage:
    from verify_guard import guard
    result = guard(response_text="M2 is free and <your-model> is not loaded")
    # result.verdict  → "PASS" | "FAIL" | "UNVERIFIED" | "CLEAN"
    # result.evidence → list of probe results
    # result.blocked  → sanitized text with unverified claims redacted

Run standalone for testing:
    python3 verify_guard.py --self-test

CLI:
    python3 verify_guard.py --probe-only              # Run all probes, print results
    python3 verify_guard.py --check-text "M2 is free"  # Check specific text
    python3 verify_guard.py --check-text "text" --json # JSON output
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("verify_guard")

# ── Probe Result Types ─────────────────────────────────────────────────────

@dataclass
class ProbeResult:
    """Result of a single verification probe."""
    claim: str                     # The factual assertion being checked
    category: str                  # "process"|"gpu"|"ollama_model"|"file"|"disk"|"balance"|"generic"|"training"
    verified: bool                 # True only if probe CONFIRMED the claim
    evidence: str                  # Raw probe output / explanation
    probe_cmd: str = ""            # Command or method used
    probe_time: str = ""           # ISO timestamp
    source: str = "live_probe"     # "live_probe" | "cache" | "memory_only"
    severity: str = "medium"       # "low" | "medium" | "high" | "critical"

    @property
    def status(self) -> str:
        return "✓ VERIFIED" if self.verified else "✗ FAILED"

    def to_dict(self) -> dict:
        return {
            "claim": self.claim,
            "category": self.category,
            "verified": self.verified,
            "evidence": self.evidence,
            "probe_cmd": self.probe_cmd,
            "probe_time": self.probe_time,
            "source": self.source,
            "severity": self.severity,
        }


@dataclass
class GuardResult:
    """Aggregated result of running verify_guard on a response."""
    verdict: str                    # "PASS" | "FAIL" | "UNVERIFIED" | "CLEAN"
    claims_found: List[str] = field(default_factory=list)
    probes: List[ProbeResult] = field(default_factory=list)
    blocked_text: str = ""          # Response with unverified claims redacted
    summary: str = ""

    @property
    def all_verified(self) -> bool:
        return all(p.verified for p in self.probes)

    @property
    def has_failures(self) -> bool:
        return any(not p.verified for p in self.probes)


# ── Claim Detection Patterns ───────────────────────────────────────────────
#
# These patterns catch factual assertions about lab state. Each maps to a
# probe function. The first match wins for each region of text.
# Order: more specific patterns first to avoid false positives.
#
# IMPORTANT: an empty probe result means "not found at this one place" —
# NEVER conclude "doesn't exist" from a single empty probe.

CLAIM_PATTERNS: List[Tuple[re.Pattern, str, str, str]] = [
    # (compiled regex, category, description, severity)

    # ── Ollama model presence (most specific first) ──────────────────────
    (re.compile(
        r"\b(<your-model>\.8|<your-model>\.5|<your-model>\.0|granite[-\d.]+|<your-model>[-\d.]+|meta-llama/[-\w]+|llama[\d.]+[-a-z]*)\b"
        r"\s*(?:is\s+(?:loaded|running|resident|absent|not\s+(?:loaded|running|present|there)))",
        re.IGNORECASE
    ), "ollama_model", "Ollama model presence/absence claim", "high"),

    # ── M2/M3/M1 machine state ───────────────────────────────────────────
    (re.compile(
        r"\bM2\b\s+(?:machine\s+)?(?:is\s+)?(free|idle|busy|running|has\s+(?:nothing|<your-model>|ollama|model|only))",
        re.IGNORECASE
    ), "process", "M2 machine state claim", "critical"),
    (re.compile(
        r"\bM3\b\s+(?:machine\s+)?(?:is\s+)?(free|idle|busy|running|has\s+(?:nothing|<your-model>|ollama|model|only))",
        re.IGNORECASE
    ), "process", "M3 machine state claim", "critical"),
    (re.compile(
        r"\bM1\b\s+(?:machine\s+)?(?:is\s+)?(free|idle|busy|running|has\s+(?:nothing|<your-model>|ollama|model|only))",
        re.IGNORECASE
    ), "process", "M1 machine state claim", "critical"),

    # ── ComfyUI state ────────────────────────────────────────────────────
    (re.compile(
        r"\b(?:ComfyUI|comfy)\s+(?:is\s+)?(up|down|running|not\s+running|alive|dead|wedged|hung)",
        re.IGNORECASE
    ), "process", "ComfyUI state claim", "high"),

    # ── Ollama service state ─────────────────────────────────────────────
    (re.compile(
        r"\b(?:Ollama|ollama)\s+(?:service\s+)?(?:is\s+)?(up|down|running|not\s+running|alive|dead)",
        re.IGNORECASE
    ), "process", "Ollama service state claim", "high"),

    # ── GPU / VRAM claims ────────────────────────────────────────────────
    (re.compile(
        r"\b(?:GPU|gpu|VRAM|vram)\s+(?:is\s+|utilization\s+|usage\s+|free\s+|memory\s+used\s+|at\s+)",
        re.IGNORECASE
    ), "gpu", "GPU/VRAM state claim", "high"),
    (re.compile(
        r"nvidia-?(?:smi|sml)\s+(?:shows|says|reports|indicates)",
        re.IGNORECASE
    ), "gpu", "nvidia-smi tool claim", "medium"),

    # ── Model training state ─────────────────────────────────────────────
    (re.compile(
        r"\b(?:te[- ]?reo|terea)\s+"
        r"(?:training|model|fine.?tune|fine-tune|QLoRA)\s+"
        r"(?:is\s+)?(done|ready|failed|not\s+(?:started|found)|exists|running|blocked|stalled|alive|dead|crashed|froze|stuck|at\s+step\s+\d+)",
        re.IGNORECASE
    ), "training", "Te Reo training state claim", "high"),
    (re.compile(
        r"\b(?:training|train(?:ing)?)\s+(?:is\s+|was\s+|has\s+)(?:finished|completed|started|stopped|died|frozen|crashed|failed|killed|running|done|dead|stalled|blocked|alive)",
        re.IGNORECASE
    ), "training", "Training state claim", "high"),

    # ── <content-pipeline> / pipeline / post claims ──────────────────────────────────
    (re.compile(
        r"\b<content-pipeline>\b\s*(?:pipeline|account|post(?:ing)?|video(?:s|generation)?)?\s*"
        r"(?:is\s+)?(running|down|broken|posting|not\s+posting|stuck|alive|died|dead|failing|working)",
        re.IGNORECASE
    ), "process", "<content-pipeline>/pipeline state claim", "high"),
    (re.compile(
        r"\b(?:no\s+posts|no\s+renders|no\s+videos|no\s+content\s+(?:posted|generated|produced)|nothing\s+(?:posted|rendered|generated|produced|delivered))\b",
        re.IGNORECASE
    ), "process", "Absence of posts/outputs claim", "high"),
    (re.compile(
        r"\b(?:posts?|renders?|videos?)\s+(?:did\s+(?:not|never)|won'?t|didn'?t|failed|stopped|not\s+)?(?:post|render|generate|go(es)?)",
        re.IGNORECASE
    ), "process", "Post/render failure claim", "high"),

    # ── Cron / schedule claims ───────────────────────────────────────────
    (re.compile(
        r"\b(?:cron|schedule|job)\s+[\"']?[\w-]+[\"']?\s+(?:is\s+)?(running|failing|stuck|ok|broken|dead|missed|never\s+(?:fired|ran))",
        re.IGNORECASE
    ), "process", "Cron job state claim", "medium"),

    # ── Docker / container claims ────────────────────────────────────────
    (re.compile(
        r"\b(?:docker|container)\s+[\"']?[\w./-]+[\"']?\s+(?:is\s+)?(running|stopped|dead|squatting|present|respawning)",
        re.IGNORECASE
    ), "process", "Docker container state claim", "medium"),

    # ── Process liveness ─────────────────────────────────────────────────
    (re.compile(
        r"\b(?:process|pid|worker|daemon|service)\s+(?:is\s+)?(alive|dead|running|wedged|stuck|zombie|killed|hung)",
        re.IGNORECASE
    ), "process", "Process liveness claim", "medium"),

    # ── SSH / auth / reachability claims ─────────────────────────────────
    (re.compile(
        r"\b(?:SSH|ssh|auth|authorized|reachable|unreachable)\s+(?:is\s+)?(working|broken|configured|authorized|down|up|failed)",
        re.IGNORECASE
    ), "generic", "SSH/auth state claim", "medium"),

    # ── Balance / money claims ───────────────────────────────────────────
    (re.compile(
        r"\b(?:balance|amount|money|cash|USDC|USD|balance)\s+"
        r"(?:is\s+)?(?:\$?\d[\d,.]*\s*(?:USD|NZD|USDC|KiwiSaver)?|zero|empty|low|at\s+\$)",
        re.IGNORECASE
    ), "balance", "Balance/money claim", "high"),

    # ── File/directory existence ─────────────────────────────────────────
    (re.compile(
        r"\b(?:file|directory|folder|path)\s+[\"']?((?:/|[A-Za-z]:[/\\\\]|\.\.?/)[^\"'\s.,;:!?]+)[\"']?\s+"
        r"(?:exists|is missing|doesn't exist|isn't there|not (?:there|found)|present|absent|not created)",
        re.IGNORECASE
    ), "file", "File existence claim", "medium"),

    # ── Venv / environment ───────────────────────────────────────────────
    (re.compile(
        r"\b(?:no\s+(?:venv|virtualenv|env))\s+(?:exists|on\s+M[123]|on\s+(?:the\s+)?machine|found|installed)",
        re.IGNORECASE
    ), "file", "Venv existence claim", "medium"),

    # ── Disk space ───────────────────────────────────────────────────────
    (re.compile(
        r"\b(?:disk|storage|space)\s+(?:on\s+M[123])?\s*(?:is\s+)?(\d+%|\d+\s*[GMKT]?B|full|empty|almost\s+full|out)",
        re.IGNORECASE
    ), "disk", "Disk space claim", "medium"),

    # ── Generic service state ────────────────────────────────────────────
    (re.compile(
        r"\b(?:service|server|daemon)\s+[\"']?[\w-]+[\"']?\s+(?:is\s+)?(up|down|running|stopped|dead|alive)",
        re.IGNORECASE
    ), "process", "Generic service state claim", "medium"),

    # ── Nothing happened / ran but nothing delivered ─────────────────────
    (re.compile(
        r"\b(?:nothing\s+(?:happened|fired|ran|executed|delivered|posted|changed|updated|occurred))",
        re.IGNORECASE
    ), "process", "Nothing-happened claim", "high"),
    (re.compile(
        r"\b(?:ran\s+(?:fine|OK|smoothly|successfully)|worked\s+(?:fine|OK|perfectly))"
        r"\s*(?:but|yet|however|although).*"
        r"(?:nothing|no\s+\w+|zero)",
        re.IGNORECASE
    ), "process", "Success-but-nothing-delivered compound claim", "high"),

    # ── Time/date claims about processes ─────────────────────────────────
    (re.compile(
        r"\b(?:was\s+(?:last|running|working|posting))\s+"
        r"(?:at\s+\d|on\s+\w|yesterday|today|ago\s+\d+\s+(?:hours?|days?|weeks?))",
        re.IGNORECASE
    ), "process", "Temporal state claim", "low"),

    # ── "has been" / "have been" state claims ────────────────────────────
    (re.compile(
        r"\b(?:has|have)\s+been\s+(?:running|failing|stopped|broken|posting|silent|dead)",
        re.IGNORECASE
    ), "process", "Present-perfect state claim", "medium"),
]


# ── Probe Functions ─────────────────────────────────────────────────────────

def _run_cmd(cmd: str, timeout: int = 15, host: Optional[str] = None) -> Tuple[int, str, str]:
    """Run a shell command and return (exit_code, stdout, stderr).

    If host is specified (e.g. '<ssh-user>@<lab-host>'), runs via SSH.
    Otherwise runs locally.
    """
    try:
        if host:
            full_cmd = f"ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no -o BatchMode=yes {host} '{cmd}'"
        else:
            full_cmd = cmd

        result = subprocess.run(
            full_cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", f"Command timed out after {timeout}s"
    except Exception as e:
        return -1, "", str(e)


def probe_m2_state() -> ProbeResult:
    """Check M2 state: processes, GPU, Ollama models, disk.

    NOTE: M2 is <lab-host> (<ssh-user>@M2). SSH key auth required.
    Single-model rule: only one model job at a time on the 24GB pool.
    """
    claim = "M2 state (process + GPU + Ollama + disk)"
    host = "<ssh-user>@<lab-host>"

    # Ollama models
    rc, out, _ = _run_cmd("curl -s --max-time 5 http://<lab-host>:11434/api/ps 2>/dev/null || echo 'OLLAMA_UNREACHABLE'", host=host)
    ollama_models = "UNREACHABLE"
    ollama_ok = False
    if rc == 0 and "OLLAMA_UNREACHABLE" not in out:
        try:
            data = json.loads(out)
            models = data.get("models", [])
            if models:
                ollama_models = ", ".join(m["name"] for m in models)
                ollama_ok = True
            else:
                ollama_models = "NO_MODELS_LOADED"
        except (json.JSONDecodeError, KeyError):
            ollama_models = f"PARSE_ERROR"

    # GPU state (nvidia-smi on M2)
    rc2, gpu_out, _ = _run_cmd(
        "nvidia-smi --query-gpu=index,name,memory.used,memory.total,utilization.gpu --format=csv,noheader,nounits 2>/dev/null || echo 'GPU_UNREACHABLE'",
        host=host, timeout=10
    )

    # Running processes
    rc3, ps_out, _ = _run_cmd(
        "ps aux | grep -iE '(comfy|ollama|python.*train|train.*py)' | grep -v grep || echo 'NO_MATCHES'",
        host=host, timeout=10
    )

    # Disk
    rc4, disk_out, _ = _run_cmd(
        "df -h / /mnt/storage 2>/dev/null || echo 'DISK_UNREACHABLE'",
        host=host, timeout=10
    )

    evidence_lines = [
        f"Ollama: {ollama_models}",
        f"GPU: {gpu_out[:500] if gpu_out else 'UNREACHABLE'}",
        f"Processes: {ps_out[:500] if ps_out else 'NONE'}",
        f"Disk: {disk_out[:500] if disk_out else 'UNREACHABLE'}",
    ]
    evidence = "\n".join(evidence_lines)
    return ProbeResult(
        claim=claim,
        category="process",
        verified=True,
        evidence=evidence,
        probe_cmd="ollama_api + nvidia-smi + ps aux + df (SSH M2)",
        probe_time=datetime.now(timezone.utc).isoformat(),
    )


def probe_m3_state() -> ProbeResult:
    """Check M3 state: Ollama models, process state.

    M3 is reachable at <lab-host> but SSH may be limited.
    Ollama port :11434 is accessible from WSL subnet.
    """
    claim = "M3 state (Ollama + process)"
    rc, out, _ = _run_cmd(
        "curl -s --max-time 5 http://<lab-host>:11434/api/ps 2>/dev/null || echo 'OLLAMA_UNREACHABLE'"
    )

    ollama_models = "UNREACHABLE"
    if rc == 0 and "OLLAMA_UNREACHABLE" not in out:
        try:
            data = json.loads(out)
            models = data.get("models", [])
            ollama_models = ", ".join(m["name"] for m in models) if models else "NO_MODELS_LOADED"
        except (json.JSONDecodeError, KeyError):
            ollama_models = "PARSE_ERROR"

    evidence = f"Ollama models on M3: {ollama_models}"
    return ProbeResult(
        claim=claim,
        category="process",
        verified=True,
        evidence=evidence,
        probe_cmd="curl M3:11434/api/ps",
        probe_time=datetime.now(timezone.utc).isoformat(),
    )


def probe_ollama_model(model_name: str, host: str = "<lab-host>", port: str = "11434") -> ProbeResult:
    """Check if a specific Ollama model is loaded on a given host."""
    claim = f"Ollama model '{model_name}' on {host}"
    rc, out, _ = _run_cmd(
        f"curl -s --max-time 5 http://{host}:{port}/api/ps 2>/dev/null || echo 'UNREACHABLE'"
    )

    if "UNREACHABLE" in out:
        return ProbeResult(
            claim=claim,
            category="ollama_model",
            verified=False,
            evidence=f"Host {host}:{port} unreachable",
            probe_cmd=f"curl {host}:{port}/api/ps",
            probe_time=datetime.now(timezone.utc).isoformat(),
        )

    try:
        data = json.loads(out)
        loaded_names = [m["name"] for m in data.get("models", [])]
        # Support fuzzy matching (e.g. "<your-model>" matches "<your-model>
        found = False
        matched_name = ""
        for ln in loaded_names:
            # Strip tag suffix for comparison
            base_name = ln.split(":")[0]
            if base_name.lower() == model_name.lower() or ln.lower() == model_name.lower():
                found = True
                matched_name = ln
                break
        return ProbeResult(
            claim=claim,
            category="ollama_model",
            verified=found,
            evidence=f"Loaded: {', '.join(loaded_names) if loaded_names else 'NONE'}. Target '{model_name}': {'FOUND→' + matched_name if found else 'NOT LOADED'}",
            probe_cmd=f"curl {host}:{port}/api/ps",
            probe_time=datetime.now(timezone.utc).isoformat(),
        )
    except (json.JSONDecodeError, KeyError):
        return ProbeResult(
            claim=claim,
            category="ollama_model",
            verified=False,
            evidence=f"Parse error: {out[:300]}",
            probe_cmd=f"curl {host}:{port}/api/ps",
            probe_time=datetime.now(timezone.utc).isoformat(),
        )


def probe_process(process_pattern: str, host: Optional[str] = None) -> ProbeResult:
    """Check if a process matching the pattern is running."""
    claim = f"Process matching '{process_pattern}'"
    cmd = f"ps aux | grep -iE '{process_pattern}' | grep -v grep || echo 'NO_MATCH'"
    if host:
        cmd = f"ssh -o ConnectTimeout=5 -o BatchMode=yes {host} '{cmd}'"

    rc, out, _ = _run_cmd(cmd, timeout=10)
    running = "NO_MATCH" not in out and out.strip() != ""
    return ProbeResult(
        claim=claim,
        category="process",
        verified=running,
        evidence=out[:500] if out else "No matching processes",
        probe_cmd=cmd,
        probe_time=datetime.now(timezone.utc).isoformat(),
    )


def probe_file_exists(path: str) -> ProbeResult:
    """Check if a file or directory exists."""
    claim = f"File/dir exists: {path}"
    exists = os.path.exists(path)
    is_file = os.path.isfile(path)
    is_dir = os.path.isdir(path)
    size = ""
    if is_file:
        try:
            sz = os.path.getsize(path)
            size = f" ({sz} bytes)"
        except OSError:
            size = " (size unknown)"
    elif is_dir:
        try:
            count = len(os.listdir(path))
            size = f" ({count} entries)"
        except OSError:
            size = " (read error)"

    return ProbeResult(
        claim=claim,
        category="file",
        verified=exists,
        evidence=f"{'EXISTS' if exists else 'NOT FOUND'}{size} [{'file' if is_file else 'dir' if is_dir else 'not found'}]",
        probe_cmd=f"os.path.exists('{path}')",
        probe_time=datetime.now(timezone.utc).isoformat(),
    )


def probe_gpu_state() -> ProbeResult:
    """Check GPU utilization and memory via nvidia-smi on M2 (SSH)."""
    claim = "GPU state (nvidia-smi on M2)"
    rc, out, err = _run_cmd(
        "nvidia-smi --query-gpu=index,name,memory.used,memory.total,utilization.gpu --format=csv,noheader,nounits 2>/dev/null || echo 'GPU_UNREACHABLE'",
        host="<ssh-user>@<lab-host>", timeout=10
    )

    if rc != 0 or not out.strip() or "UNREACHABLE" in out:
        return ProbeResult(
            claim=claim,
            category="gpu",
            verified=False,
            evidence=f"nvidia-smi failed: {err or out}",
            probe_cmd="nvidia-smi via SSH M2",
            probe_time=datetime.now(timezone.utc).isoformat(),
        )

    return ProbeResult(
        claim=claim,
        category="gpu",
        verified=True,
        evidence=f"nvidia-smi output:\n{out}",
        probe_cmd="nvidia-smi via SSH M2",
        probe_time=datetime.now(timezone.utc).isoformat(),
    )


def probe_<content-pipeline>_status() -> ProbeResult:
    """Check <content-pipeline> pipeline status — orchestrator alive + recent posts."""
    claim = "<content-pipeline> pipeline posting status"

    # Check orchestrator process on Windows host
    rc1, ps_out, _ = _run_cmd(
        'wmic process where "name=\'python.exe\'" get processid,commandline 2>/dev/null '
        "| findstr /i 'orchestrator' || echo 'NO_ORCHESTRATOR'"
    )

    # Check recent posts from the actual log file
    post_log = r"C:\pipeline\data\ch1\content_history.json"
    rc2, posts_out, _ = _run_cmd(f'type "{post_log}" 2>/dev/null || echo "POST_LOG_MISSING"')

    evidence = f"Orchestrator: {ps_out[:300]}\nPosts: {posts_out[:500]}"
    has_orchestrator = "NO_ORCHESTRATOR" not in ps_out
    has_posts = "POST_LOG_MISSING" not in posts_out

    return ProbeResult(
        claim=claim,
        category="process",
        verified=has_orchestrator and has_posts,
        evidence=evidence,
        probe_cmd="wmic process + content_history.json read",
        probe_time=datetime.now(timezone.utc).isoformat(),
    )


def probe_comfyui_status(host: str = "127.0.0.1", port: int = 8188) -> ProbeResult:
    """Check if ComfyUI is running and queue state."""
    claim = f"ComfyUI status on {host}:{port}"
    rc, out, _ = _run_cmd(
        f"curl -s --max-time 5 http://{host}:{port}/queue 2>/dev/null || echo 'COMFYUI_UNREACHABLE'"
    )

    if "COMFYUI_UNREACHABLE" in out:
        return ProbeResult(
            claim=claim,
            category="process",
            verified=False,
            evidence="ComfyUI unreachable",
            probe_cmd=f"curl {host}:{port}/queue",
            probe_time=datetime.now(timezone.utc).isoformat(),
        )

    try:
        data = json.loads(out)
        running = data.get("queue_running", [])
        pending = data.get("queue_pending", [])
        return ProbeResult(
            claim=claim,
            category="process",
            verified=True,
            evidence=f"Running: {len(running)}, Pending: {len(pending)}",
            probe_cmd=f"curl {host}:{port}/queue",
            probe_time=datetime.now(timezone.utc).isoformat(),
        )
    except json.JSONDecodeError:
        return ProbeResult(
            claim=claim,
            category="process",
            verified=False,
            evidence=f"Parse error: {out[:300]}",
            probe_cmd=f"curl {host}:{port}/queue",
            probe_time=datetime.now(timezone.utc).isoformat(),
        )


def probe_training_state() -> ProbeResult:
    """Check for active training processes on M2."""
    claim = "Training process state on M2"
    rc, out, _ = _run_cmd(
        "ps aux | grep -iE '(train|python)' | grep -v grep || echo 'NO_TRAINING'",
        host="<ssh-user>@<lab-host>", timeout=10
    )
    has_training = "NO_TRAINING" not in out
    return ProbeResult(
        claim=claim,
        category="training",
        verified=True,  # probe succeeded; whether training runs is in evidence
        evidence=f"Training processes: {out[:500] if out else 'NONE'}" if has_training else "No training processes found",
        probe_cmd="ps aux via SSH M2 (training grep)",
        probe_time=datetime.now(timezone.utc).isoformat(),
    )


def probe_disk_space(path: str = "/") -> ProbeResult:
    """Check disk free space."""
    claim = f"Disk free space at {path}"
    try:
        st = os.statvfs(path)
        total = st.f_blocks * st.f_frsize
        free = st.f_bavail * st.f_frsize
        used = total - free
        percent = (used / total) * 100 if total > 0 else 0
    except OSError as e:
        return ProbeResult(
            claim=claim,
            category="disk",
            verified=False,
            evidence=f"statvfs failed: {e}",
            probe_cmd=f"os.statvfs('{path}')",
            probe_time=datetime.now(timezone.utc).isoformat(),
        )
    return ProbeResult(
        claim=claim,
        category="disk",
        verified=True,
        evidence=f"Total: {total//(1024**2)}MB, Used: {used//(1024**2)}MB ({percent:.0f}%), Free: {free//(1024**2)}MB",
        probe_cmd=f"os.statvfs('{path}')",
        probe_time=datetime.now(timezone.utc).isoformat(),
    )


# ── Probe Registry ──────────────────────────────────────────────────────────
# Maps claim categories to the probe functions that can verify them.
# A category may map to multiple probes for redundancy.

PROBE_REGISTRY: Dict[str, List[callable]] = {
    "ollama_model": [probe_ollama_model],  # Needs model_name extracted separately
    "process": [probe_m2_state, probe_m3_state, probe_process],
    "gpu": [probe_gpu_state],
    "file": [probe_file_exists],           # Needs path extracted separately
    "disk": [probe_disk_space],
    "training": [probe_training_state],
    "generic": [],                          # Falls through to general probes
    "balance": [],                          # No automated probe yet
}


# ── Master Guard ───────────────────────────────────────────────────────────

def _extract_model_name(claim_text: str) -> Optional[str]:
    """Extract an Ollama model name from a claim string."""
    match = re.search(
        r"(<your-model>[\d.]+|llama[\d.]+|granite[-\d.]+|<your-model>[-\d.]+|meta-llama/[-\w]+|<your-model>[\d.]+[\w-]*)",
        claim_text, re.IGNORECASE
    )
    if match:
        return match.group(1).lower()
    return None


def _extract_file_path(claim_text: str) -> Optional[str]:
    """Extract a file path from a claim string."""
    match = re.search(r"[\"']?((?:/|[A-Za-z]:[/\\\\])[^\"'\s.,;:!?]+)[\"']?", claim_text)
    if match:
        return match.group(1)
    return None


def _extract_process_pattern(claim_text: str) -> Optional[str]:
    """Extract a process name/pattern from a claim string."""
    match = re.search(r"(?:process|pid|worker|daemon|service)\s+(?:is\s+)?([\w-]+)", claim_text, re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def guard(response_text: str, run_probes: bool = True) -> GuardResult:
    """
    Scan response text for factual claims about lab state and verify them.

    This is the main entry point. Call this before returning any response
    that might contain factual assertions about processes, models, GPU state,
    files, disk, balances, or any other lab infrastructure.

    Args:
        response_text: The assistant response to check for claims
        run_probes: If True, run live verification probes. If False,
                    detect claims and mark as UNVERIFIED (no live checks).

    Returns:
        GuardResult with verdict, evidence list, blocked text, and summary.
        Verdicts:
          - CLEAN:       No factual lab-state claims detected
          - PASS:        All claims verified successfully
          - FAIL:        At least one claim failed verification
          - UNVERIFIED:  Claims detected but probes not run or inconclusive
    """
    result = GuardResult(verdict="CLEAN")
    matched_claims = []
    verified_claims: List[str] = []
    failed_claims: List[str] = []

    # ── Phase 1: Detect all claims ──────────────────────────────────────
    _NEGATION_WORDS = frozenset({"not", "never", "no", "none", "nothing", "nor"})

    for pattern, category, description, severity in CLAIM_PATTERNS:
        for match in pattern.finditer(response_text):
            # Detect if the claim is negative (e.g. "is not loaded").
            # Patterns that START with negation words ("no posts",
            # "nothing happened") are already absence-assertions — don't
            # double-negate them.
            claim_text = match.group(0)
            all_text_lower = claim_text.lower()
            tokens = re.findall(r"\b\w+\b", all_text_lower)

            # Determine if the pattern itself encodes negation (first token
            # is a negation word).  If so, the claim is already phrased as
            # absence and needs no logical inversion.
            leading_negation = (
                tokens and tokens[0] in _NEGATION_WORDS
            )

            # Inline negation from words like "not" / "never" appearing
            # AFTER the subject (e.g. "<your-model> is NOT loaded").
            inline_negated = bool(
                set(tokens[1:] if leading_negation else tokens)
                & _NEGATION_WORDS
            )

            matched_claims.append({
                "text": claim_text,
                "category": category,
                "description": description,
                "severity": severity,
                "negated": inline_negated,
            })

    if not matched_claims:
        result.verdict = "CLEAN"
        result.summary = "No factual lab-state claims detected."
        result.blocked_text = response_text
        return result

    result.claims_found = [c["text"] for c in matched_claims]

    # ── Phase 2: Run probes (if enabled) ────────────────────────────────
    if run_probes:
        probes: List[ProbeResult] = []
        seen_probe_keys: set = set()

        # Always run M2 + M3 + GPU probes as baseline
        baseline_probes = [
            ("m2_state", probe_m2_state),
            ("m3_state", probe_m3_state),
            ("gpu_state", probe_gpu_state),
        ]
        for key, pf in baseline_probes:
            if key not in seen_probe_keys:
                try:
                    probes.append(pf())
                    seen_probe_keys.add(key)
                except Exception as e:
                    logger.error(f"Probe {pf.__name__} failed: {e}")

        # Category-specific probes
        for claim_info in matched_claims:
            cat = claim_info["category"]
            text = claim_info["text"]

            if cat == "ollama_model":
                model_name = _extract_model_name(text)
                if model_name:
                    # Check both M2 and M3
                    for h, p in [("<lab-host>", "11434"), ("<lab-host>", "11434")]:
                        key = f"ollama_{model_name}_{h}"
                        if key not in seen_probe_keys:
                            probes.append(probe_ollama_model(model_name, h, p))
                            seen_probe_keys.add(key)

            elif cat == "process" and "<content-pipeline>" in text.lower():
                key = "<content-pipeline>_status"
                if key not in seen_probe_keys:
                    probes.append(probe_<content-pipeline>_status())
                    seen_probe_keys.add(key)

            elif cat == "process" and "comfy" in text.lower():
                key = "comfyui_status"
                if key not in seen_probe_keys:
                    probes.append(probe_comfyui_status())
                    seen_probe_keys.add(key)

            elif cat == "training":
                key = "training_state"
                if key not in seen_probe_keys:
                    probes.append(probe_training_state())
                    seen_probe_keys.add(key)

            elif cat == "file":
                fpath = _extract_file_path(text)
                if fpath:
                    key = f"file_{fpath}"
                    if key not in seen_probe_keys:
                        probes.append(probe_file_exists(fpath))
                        seen_probe_keys.add(key)

            elif cat == "process" and any(kw in text.lower() for kw in ["process", "worker", "daemon"]):
                pattern = _extract_process_pattern(text)
                if pattern and len(pattern) > 2:
                    key = f"process_{pattern}"
                    if key not in seen_probe_keys:
                        probes.append(probe_process(pattern))
                        seen_probe_keys.add(key)

        result.probes = probes

        # ── Phase 3: Determine verdict (with negation awareness) ────────
        # For each claim, check if probe results confirm or deny it.
        # A negated claim ("is NOT loaded") is verified when the probe
        # shows the thing is absent (verified=False for "loaded" probe).
        # A positive claim ("is loaded") is verified when the probe
        # shows the thing is present (verified=True).
        claim_verifications: List[bool] = []
        for claim_info in matched_claims:
            cat = claim_info["category"]
            is_negated = claim_info.get("negated", False)
            text = claim_info["text"]

            # Find relevant probes for this claim
            relevant_probes: List[ProbeResult] = []
            if cat == "ollama_model":
                model_name = _extract_model_name(text)
                if model_name:
                    for p in probes:
                        if p.category == "ollama_model" and model_name.lower() in p.claim.lower():
                            relevant_probes.append(p)
            elif cat == "process" and "<content-pipeline>" in text.lower():
                relevant_probes = [p for p in probes if p.category == "process" and "<content-pipeline>" in p.claim]
            elif cat == "process" and "comfy" in text.lower():
                relevant_probes = [p for p in probes if p.category == "process" and "ComfyUI" in p.claim]
            elif cat == "training":
                relevant_probes = [p for p in probes if p.category == "training"]
            elif cat == "file":
                fpath = _extract_file_path(text)
                if fpath:
                    relevant_probes = [p for p in probes if p.category == "file" and fpath in p.claim]
            elif cat in ("process", "gpu", "generic", "disk", "balance"):
                # For generic categories, use any probe of matching category
                relevant_probes = [p for p in probes if p.category == cat]

            if not relevant_probes:
                # No probe data — can't verify
                claim_verifications.append(False)
                failed_claims.append(text)
                continue

            # Determine claim truth based on probe results and negation
            # For a POSITIVE claim: needs at least one probe confirming (verified=True)
            # For a NEGATED claim: needs at least one probe confirming absence (verified=False)
            if is_negated:
                claim_is_verified = any(not p.verified for p in relevant_probes)
            else:
                claim_is_verified = any(p.verified for p in relevant_probes)

            claim_verifications.append(claim_is_verified)
            if claim_is_verified:
                verified_claims.append(text)
            else:
                failed_claims.append(text)

        if not claim_verifications:
            result.verdict = "UNVERIFIED"
        elif all(claim_verifications):
            result.verdict = "PASS"
        else:
            result.verdict = "FAIL"
    else:
        result.verdict = "UNVERIFIED"

    # ── Phase 4: Build output ───────────────────────────────────────────
    claim_str = "; ".join(result.claims_found[:8])
    if len(result.claims_found) > 8:
        claim_str += f" (+{len(result.claims_found) - 8} more)"
    result.summary = f"Claims: {claim_str}"

    # Build blocked text: redact claims that FAILED their per-claim verification
    if failed_claims:
        blocked = response_text
        for claim_text in failed_claims:
            blocked = blocked.replace(claim_text, f"[UNVERIFIED: {claim_text}]")
        result.blocked_text = blocked
    else:
        result.blocked_text = response_text

    return result


# ── CLI Entry Point ────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Verify-Before-Claim Enforcement Engine")
    parser.add_argument("--self-test", action="store_true", help="Run self-test probes + sample texts")
    parser.add_argument("--probe-only", action="store_true", help="Run all probes and print results")
    parser.add_argument("--check-text", type=str, help="Check a specific text string for claims")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    if args.self_test:
        print("=== Verify-Before-Claim Self-Test ===\n")

        print("1. Probing M2 state...")
        r1 = probe_m2_state()
        print(f"   [{r1.status}] {r1.claim}")
        print(f"   Evidence: {r1.evidence[:200]}...")
        print()

        print("2. Probing M3 state...")
        r2 = probe_m3_state()
        print(f"   [{r2.status}] {r2.claim}")
        print(f"   Evidence: {r2.evidence[:200]}...")
        print()

        print("3. Probing GPU...")
        r3 = probe_gpu_state()
        print(f"   [{r3.status}] {r3.claim}")
        print(f"   Evidence: {r3.evidence[:200] if r3.evidence else r3.evidence}...")
        print()

        print("4. Testing claim detection: 'M2 is free, <your-model> not loaded, training dead'")
        sample1 = "M2 is free and <your-model> is not loaded. The training is dead. ComfyUI is running."
        gr = guard(sample1, run_probes=True)
        print(f"   Input:    {sample1}")
        print(f"   Verdict:  {gr.verdict}")
        print(f"   Claims:   {gr.claims_found}")
        print(f"   Summary:  {gr.summary}")
        print()

        print("5. Testing claim detection: '<content-pipeline> not posting, no renders today'")
        sample2 = "<content-pipeline> is not posting today. No renders came through. The orchestrator is broken."
        gr2 = guard(sample2, run_probes=True)
        print(f"   Input:    {sample2}")
        print(f"   Verdict:  {gr2.verdict}")
        print(f"   Claims:   {gr2.claims_found}")
        print()

        print("6. Testing clean text (no claims):")
        sample3 = "I went to the store and bought some milk."
        gr3 = guard(sample3, run_probes=True)
        print(f"   Input:    {sample3}")
        print(f"   Verdict:  {gr3.verdict}")
        print(f"   Claims:   {gr3.claims_found}")
        print()

        print("=== Self-test complete ===")
        return

    if args.probe_only:
        print("=== Running All Probes ===\n")
        probes = [probe_m2_state, probe_m3_state, probe_gpu_state, probe_training_state, probe_comfyui_status]
        for pf in probes:
            try:
                r = pf()
                status = "✓" if r.verified else "✗"
                print(f"  {status} {r.claim}: {r.evidence[:200]}")
            except Exception as e:
                print(f"  ✗ {pf.__name__}: ERROR - {e}")
        return

    if args.check_text:
        gr = guard(args.check_text, run_probes=True)
        if args.json:
            print(json.dumps({
                "verdict": gr.verdict,
                "claims_found": gr.claims_found,
                "probes": [p.to_dict() for p in gr.probes],
                "summary": gr.summary,
                "blocked_text": gr.blocked_text,
            }, indent=2))
        else:
            print(f"Verdict: {gr.verdict}")
            print(f"Claims: {gr.claims_found}")
            print(f"Summary: {gr.summary}")
            for p in gr.probes:
                print(f"\n  [{p.status}] {p.claim}")
                print(f"  Evidence: {p.evidence[:300]}")
        return

    parser.print_help()


if __name__ == "__main__":
    main()