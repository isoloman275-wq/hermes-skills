# Lab service-integrity monitor (design intent, 2026-08-04)

User asked: "how do we not have a service checking and debugging all our little services
to make sure they are working end to end ALL the time for EVERYTHING ... if something
breaks no one knows till we do deep-diving ... such things need to be brought to light
earlier."

Two concrete findings that motivated it (see lab-health "PITFALL — cron reports ok but
produces nothing"):
1. <pod-cron> <store> cron reported ok for a week while the user thought it was dead; real
   output landed in eta/daily/ and was gated on sign-off ("drafts_pushed":[]).
2. 2b-aux model stayed cold (only 4b resident on M3) = its backing role never fired.

DESIGN: a scheduled job that audits on a cadence and ALERTS on drift:
- For each cron: confirm REAL OUTPUT this period (find workdir newermt this-week; read
  report sidecars). status:ok is not enough.
- For each model: check /api/ps warmth on M1/M2/M3 — a model that should serve a role but
  is never resident = dormant role to investigate.
- Config drift: confirm baked num_ctx/num_gpu/thinking still match the lab-model-matrix.
- Post/quality: no silent failures (posting, cross-post, config backup silently erroring
  for days = data-safety gap).
Alert to a chat (Telegram) so a human only looks at exceptions. This is Phase-5 handover /
daily devops digest intent.
