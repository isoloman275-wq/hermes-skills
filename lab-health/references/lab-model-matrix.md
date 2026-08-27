# Lab Model Matrix (canonical, verified live 2026-08-04)

The hand-picked models and their exact baked settings. These ALL FIT their boxes — do
not "re-fit" or re-derive them. Treat this as authoritative.

| Machine | Model | num_ctx | num_gpu | temp | Notes |
|---------|-------|---------|---------|------|-------|
| M1 (<lab-host>) | <your-model> | 131,072 (128K) | 34 | 0.6 | reachable from WSL at http://<wsl-gateway-ip>:11434 |
| M2 (<lab-host>) | <your-model> | 135,168 (132K) | 66 | 1.0 | 27B, q4_0 KV, 0-spill, spans both 3060s, reasoning off (think:false) |
| M2 (<lab-host>) | <your-model> | 232,000 | 41 | 0.6 | 35B MoE, 0-spill |
| M3 (<lab-host>) | <your-model> | 64,000 | 34 | 1.0 | 4B max this 4GB GTX 960 fits |
| M3 (<lab-host>) | <your-model> | 64,000 | 40 | 1.0 | aux slots (title/approval/triage etc.) |

## Key facts
- M2 = 2 × RTX 3060, 24GB total. Models SPAN BOTH GPUs (pooled), never one card.
- ComfyUI runs on GPU0 (`CUDA_VISIBLE_DEVICES=0`), not always active. LLMs unload from
  VRAM before a render; 10-min buffer before each ch1 slot (06:50/11:20/17:50 cutoffs).
- M1 WSL has NO local Ollama — the Windows-host Ollama (<your-model> is at <wsl-gateway-ip>:11434.
- M3 SSH is firewalled (port 22 fails); use the HTTP API :11434 to probe models.
