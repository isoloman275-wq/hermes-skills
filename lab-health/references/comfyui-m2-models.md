# ComfyUI on M2 — Video-Only (no SDXL/image models)

Verified 2026-07-18 via the ComfyUI HTTP API (`/object_info/CheckpointLoaderSimple`
returned an EMPTY model list; UNETLoader/VAELoader/LoraLoader also empty).

## Fact
- M2 ComfyUI (native process, `start_comfyui.sh`, port 8188, GPU0) is configured
  for **Wan2.2 text-to-video only** (<content-pipeline> pipeline).
- It has **NO SDXL / SD1.5 / art image checkpoint installed**. The checkpoint dir
  ComfyUI scans returns 0 files.
- All SDXL-class nodes exist (CheckpointLoaderSimple, CLIPTextEncode, KSampler,
  VAEDecode, EmptyLatentImage, SaveImage) — they just have nothing to load.

## Implication
Any task that needs a static image from ComfyUI (<store> POD artwork, thumbnails,
posters) CANNOT run until an image model is installed. The <content-pipeline> video path works;
the image path does not.

## To enable image gen (requires SSH + download — consent-gated)
1. Download an SDXL (or SD1.5 art) checkpoint to M2, e.g.:
   - `Juggernaut-XL` / `dreamshaper-xl` (SDXL, ~6.5GB)
   - or a POD-friendly art model (`animaPencilXL`, `counterfeitXL`)
2. Place in `/<home>/ComfyUI/models/checkpoints/` via SSH.
3. Build an SDXL text-to-image workflow JSON (KSampler + EmptyLatentImage at the
   target print resolution, e.g. 1024x1024 or 1216x1664 for 4500x5400 @ 300dpi
   upscaled later).
4. Submit via `/prompt` exactly like the Wan2.2 path (see <content-pipeline> visual_gen.py
   client pattern: POST workflow, poll `/history/{id}`, copy from shared storage).

## Do NOT
- Do not assume SDXL is available just because Wan2.2 video works — they use
  different model files and the image ones are absent.
- Do not try to coerce Wan2.2 into "image mode" as a print-ready substitute —
  resolution control and quality are poor for POD. Install a real image model.

## Quick check before any image task
```bash
curl -s http://<lab-host>:8188/object_info/CheckpointLoaderSimple \
  | python3 -c "import json,sys; d=json.load(sys.stdin); \
  m=d['CheckpointLoaderSimple']['input']['required']['ckpt_name'][0]; \
  print('checkpoints:', len(m), m[:5])"
```
If it prints `checkpoints: 0`, image gen is blocked — install a model first.
