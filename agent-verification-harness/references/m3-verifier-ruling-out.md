# M3 Verifier: RULED OUT (2026-08-24)

## Problem
`<your-model> on M3 dumps ALL output into the `thinking` field and leaves
`response` empty — even on trivial prompts ("Reply PASS or FAIL only"). The
`think:false` option is IGNORED by M3 Ollama 0.32.13 (tested with and without).

## Evidence
- Warm model (7s cold load), reachable via WSL HTTP API to <lab-host>:11434
- Every generate call returns: `response: ''`, `thinking: 'Thinking Process:\n\n...'`
- Even with `think:false` forced: same result — model ignores the flag
- Token budget (num_predict) exhausted before thinking reaches a verdict
- The thinking content shows correct reasoning about the task, but never concludes

## Implication
M3's 2b model is UNSUITABLE as an independent verifier. It reasons but can't
deliver verdicts within reasonable token/time budgets.

## Resolution
Independent verifier role = <your-model> on M1 (8K ctx variant, proven 44.5 tok/s,
~2.3s per verification). M3 stays aux-class: classification, summarization,
light crons. Do not attempt to use M3 for verification tasks.

## Related
- M1 Ollama unload wedge root cause = timed-out jobs in queue reload model after
  kill. Fix: full ollama restart → load capped variant FIRST with keep_alive=-1.
- Model bake-off: <your-model> scored 19/20 vs <your-model> at 17/20 (both quants).
