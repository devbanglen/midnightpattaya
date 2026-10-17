# This project: ROBLOXRACE (rewrite this file when the skill is copied to another project)

Arcade street-racing game on Roblox, RayCity-like: open city, drift, nitro, car classes. Engine: Roblox Studio
(Roblox Studio MCP is connected). Dev machine: Windows 11 + PowerShell (no WSL assumed).

## What applies from the general skill
- Concepts: gpt-image (own style reference only, no real car brands/logos: no Porsche/Nissan/etc. shapes or badges).
- 3D: **GPU server (Hunyuan3D) first, instead of Meshy** (owner decision 2026-10-18). Meshy only as fallback, and
  MESHY_API_KEY is still empty. GPU box = `vast-rtx6000-1` (shared with ayothaya/aroa agents: own folder
  `/root/robloxrace/hy` only, ayothaya's hyenv/Hunyuan3D-2.1/hf used read-only, Hunyuan through `gslot.sh --hy`).
  Run: `tools/gpu/run_hy.sh` (in/ + faces.json → out/), previews `tools/gpu/render_qa.sh` (Blender `/root/w/blender`).
  ~30 s per car (shape 15 s + texture 15 s). Results pulled to `art/cars3d/hy/<round>/`, previews `art/cars3d/hy/qa/`.
- Windows OpenSSH strips double quotes inside the remote command: put anything with quotes/pipes in a script file,
  scp it, then run it (a mangled `grep -E "a|b"` once hung waiting on stdin).
- Hunyuan 2.1 is single-image: the side it can't see in the 3/4 concept (rear) comes out messy; wheels come fused.
- Views for every car (owner: the game has a top-down camera, so the roof must be right): front/back/left from the
  turnaround (`tools/pipeline/split_turn.ps1`), right = mirrored left, top + new 3/4 from GPT with the turnaround as
  ref → `art/concepts/cars/views/<id>_{front,back,left,right,top,34}.png`.
- Exact colours: `tools/gpu/project_views.py` projects all 5 ortho views onto the Hunyuan mesh (orientation found by
  silhouette IoU, z-buffer visibility, cos^4 weights; unseen texels keep Hunyuan's paint) → `out_proj/<id>_proj.obj`.
  First test fixed the JDM rear (stripes, tail lights, no fake plate). 2.1 paint can't take a list of refs
  (unbound variable) and squashes refs to 512², so it only gets one square-padded 3/4 view.
- Hunyuan3D-2mv installed by owner's choice at `/root/Hunyuan3D-2` (code) + `/root/Hunyuan3D-2mv` (weights), run with
  ayothaya's hyenv read-only. Default car route now: `run_mv.sh <id>...` = 2mv shape from front/back/left/right
  (~56 s) + 2.1 paint from the 3/4 (~28 s) + project_views → `out_mvp/<id>_proj.obj`, previews in qa/. Supercar test:
  rear and side fixed compared with the single-image route. Outfits, headgear, weapons, animation retarget: not used here.
- Blender for clean-up (separate wheels, decimate, pivots), then FBX into Roblox Studio.

## Paths (tools not built yet: the ayothaya tools were not copied, write Windows-friendly ones when first needed)
| What | Where |
|---|---|
| keys | `.env` (OPENAI_API_KEY, MESHY_API_KEY), gitignored, never printed |
| concept script (PowerShell, no Python on this machine) | `powershell -ExecutionPolicy Bypass -File tools/pipeline/gen_concepts.ps1 <prompts.json> <out dir>`; model from `.env` `OPENAI_IMAGE_MODEL` |
| concept prompts | `art/concepts/cars/<set>_concepts.json` |
| concept images + call log | `art/concepts/cars/` + `log.jsonl` |
| style reference (our own, once locked) | `art/concepts/style_lock/` |
| Meshy output | `art/cars3d/meshy/<name>.glb`, log `log.jsonl` |
| Blender-cleaned, Roblox-ready | `art/cars3d/ready/<name>_body.fbx`, `<name>_wheel.fbx` |

## Car spec (Roblox)
- Body ≤ 20k triangles per MeshPart (target 5k–15k); wheel one mesh ≤ 2k, reused for all 4.
- Wheels never baked into the body: remove them from the Meshy result, wheel arches stay empty.
- Front faces -Z, pivot at the chassis centre, real size (~4.5 m long ≈ 16 studs).
- Separate pieces that recolour: body paint, glass, lights, rims (for the tuning shop later).
- Concepts: stylized semi-realistic arcade racer, slightly exaggerated (wide body, big wheels, low stance), clean
  surfaces, plain white/light-grey background, no text, no logos. Turnaround: front, side, rear, 3/4 for multi-view.

## Rules that are project decisions
- Gameplay chassis: raycast arcade chassis (decided in chat 2026-10-18); body mesh is visual only.
- Map: modular road kit + modular buildings; Meshy only for small props. StreamingEnabled, Box collision on props.
- Answer the owner in Thai, short. Don't commit or push unless asked.
