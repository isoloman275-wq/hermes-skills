#!/usr/bin/env python3
"""
Post-tool-call hook: verify-before-claim enforcement.

This script is invoked by Hermes via the hooks mechanism after tool calls
complete. It checks the tool result / response for factual claims about
lab state and redacts any that fail verification.

Wire it in config.yaml:
    hooks:
      post_tool_call:
        - command: python3 /<home>/.hermes/skills/devops/verify-before-claim/verify_guard_hook.py
          description: "Verify-before-claim enforcement"
          fail_closed: false
"""

from __future__ import annotations

import json
import os
import sys

# Add skill dir to path so verify_guard can be imported
SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SKILL_DIR)

from verify_guard import guard


def main():
    """Read JSON from stdin (hook payload), check for unverified claims."""
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        # No JSON input — nothing to check
        print(json.dumps({"status": "skip", "reason": "no_json_input"}))
        return

    # Extract the response text to check
    # Hook payload may come from different tool result shapes
    response_text = ""
    if isinstance(payload, dict):
        response_text = (
            payload.get("content", "")
            or payload.get("result", "")
            or payload.get("text", "")
            or payload.get("message", "")
        )
        if isinstance(response_text, list):
            # Handle multimodal content
            parts = []
            for block in response_text:
                if isinstance(block, str):
                    parts.append(block)
                elif isinstance(block, dict):
                    parts.append(block.get("text", ""))
            response_text = " ".join(parts)
    elif isinstance(payload, str):
        response_text = payload

    if not response_text or len(response_text.strip()) < 5:
        print(json.dumps({"status": "skip", "reason": "empty_or_too_short"}))
        return

    # Run verification
    result = guard(response_text, run_probes=True)

    output = {
        "status": result.verdict.lower(),  # "pass" | "fail" | "clean" | "unverified"
        "verdict": result.verdict,
        "summary": result.summary,
        "claims_found": result.claims_found,
        "probes": [
            {
                "claim": p.claim,
                "category": p.category,
                "verified": p.verified,
                "evidence": p.evidence[:500],
                "severity": p.severity,
            }
            for p in (result.probes or [])
        ],
        "blocked_text": result.blocked_text[:2000],
        "claims_count": len(result.claims_found),
        "failed_count": sum(1 for p in (result.probes or []) if not p.verified),
    }

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()