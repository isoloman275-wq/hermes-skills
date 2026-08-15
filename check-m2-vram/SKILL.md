> Published from NZ1Labs internal tooling. Private LAN details replaced with `<lab-host>` / `<home>` placeholders.

---
name: check-m2-vram
description: Check current VRAM usage and loaded models on M2 (<lab-host>). Use whenever the user asks about GPU state, VRAM headroom, whether ComfyUI can run, whether the TikTok pipeline is active, or which models are currently loaded on the inference server.
---

# Check M2 VRAM State

Run this command via the terminal tool:

\`\`\`bash
ssh <ssh-user>@<lab-host> "ollama ps && echo '---' && nvidia-smi --query-gpu=index,name,memory.used,memory.total,utilization.gpu --format=csv"
\`\`\`

Report back:
1. Which models are loaded and their VRAM footprint
2. GPU 0 and GPU 1 utilization and free VRAM
3. Whether there is headroom for a ComfyUI job (need ~8GB free on at least one GPU)
4. Whether the TikTok pipeline appears to be running (ComfyUI process visible in ollama ps output or high GPU util with no LLM loaded)
5. **Tips & Caveats**
   - If VRAM usage > 90 % you should stop or unload current models (e.g., `ollama stop <model>`).
   - For ComfyUI jobs requiring >8 GB, prefer the GPU with the most free memory.
   - Use `nvidia-smi` to confirm real‑time memory usage versus `ollama ps` estimates.
