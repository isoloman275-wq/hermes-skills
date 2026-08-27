# M2 Ollama Configuration Notes

## Systemd Override Location
`/etc/systemd/system/ollama.service.d/override.conf` on M2 (<lab-host>)

## Current Settings (July 2026)
```ini
[Service]
Environment="OLLAMA_KEEP_ALIVE=-1"
Environment="OLLAMA_HOST=0.0.0.0:11434"
Environment="OLLAMA_CONTEXT_LENGTH=65536"
Environment="OLLAMA_FLASH_ATTENTION=1"
Environment="OLLAMA_KV_CACHE_TYPE=q4_0"
```

### Why Each Setting Matters
- `KEEP_ALIVE=-1`: Models stay in VRAM forever between sessions. Without this, cold-load on first query after idle is 30-60s delay.
- `FLASH_ATTENTION=1`: Huge speedup on RTX 3060 architecture (Volta+ compatible). Required for competitive decode throughput.
- `KV_CACHE_TYPE=q4_0`: **Required** at 65K context — without q4 quantization the KV cache overflows 24GB total VRAM, forcing layers to CPU which destroys performance (~13-14 t/s vs ~40+ t/s).

### Pending Tuning (TODO)
- `OLLAMA_NUM_PARALLEL=3` — handle 3 concurrent agent sessions with proper parallel attention instead of queuing
- `OLLAMA_MAX_LOADED_MODELS=2` — keep hermes + coder warm simultaneously

## Models Loaded
As of July 2026:
- `<your-model> (30.5B params, Q4_K_M, ~18GB) — T2 code model
- `<your-model> (27B params, Q4_K_M, ~17.7GB, 132K ctx, num_gpu 66, reasoning off via think:false) — T1 general model

## Model Choice Rationale
Ollama stays as the inference framework — outperforms vLLM/llama.cpp/TGI for dual 12GB cards where VRAM is tight and workload is concurrency not throughput. No framework churn needed.
