<!-- copied from ~/.claude/skills/sprite-pipeline/references/common (ced2f55) on 2026-10-17; ayothaya owns this copy now -->
# The code kit (sprite-kit) and how projects use it

Origin: aroa A114 (2026-10-13). Three layers, nothing shared live:
1. **This skill** = shared knowledge only (its own git repo: `~/.claude/skills/sprite-pipeline`). (aroa A114)
2. **Kit** = versioned code template, `~/projects/templates/sprite-kit`, one git tag per release. v1 = extracted from aroa on 2026-10-13; v2 = crowd-bench back-ports; v3 = aroa A116 release back-ports (pose_v2_5_2 core, anchor-equality gate, pose_compat, release/fleet tools); v4 = item back layers get the per-rig head drop; v5 = game-pack source rule (published wins on pose mismatch) + shared `attackClipOf`. `CHANGELOG.md` lists each tag's contents and upgrade notes.
3. **Project** = a copy of one kit tag, renamed, owned and changed freely. Project rules live in that project's `DECISIONS.md` / `MANIFEST.md`, never in the kit or the skill. (aroa A114)

aroa (`/home/whoami/projects/active/aroa`) is the source of v1 and the example/reference implementation; never point a new project at aroa's files, and never depend on aroa staying unchanged.

## Start a project
```bash
~/projects/templates/sprite-kit/kit/init_project.sh <target_dir> <name> --route 3d-sprite|2d|3d-realtime|redesign [--tag v3] [--host <ssh alias>] [--git]
cd <target_dir> && bash tools/kit_smoke.sh      # SMOKE OK (py_compile, imports, bash -n, check_edges on the example set, studio npm ci/test/validate/build)
```
It copies the **tag** (git archive), renames `aroa`/`AROA`/`Aroa` and the aroa host aliases, writes `CLAUDE.md` with `kit: sprite-kit <tag>, route: <route>`, `docs/DECISIONS.md`, `studio/MANIFEST.md`, `.env.example` (names only), `kit.env`, a tiny example dataset, and creates the output dirs outside the project with symlinks back ([generated-output.md](generated-output.md)). Then work through the project's `docs/PORTING.md` (hard-coded lane roots, Blender pin, reference-game numbers, one-off drivers).

## The kit is a snapshot
- **Improvements made in a project are back-ported into the kit on purpose, as a new tag** (`vN+1`, entry in `CHANGELOG.md`, generic names, no data, no keys, smoke test from a fresh init). Tags are never moved or reused. The lesson behind the change goes into the matching reference here, with an origin tag. (aroa A114)
- **Projects upgrade deliberately, never automatically:** read the changelog, make renamed copies of the old and new tags with `init_project.sh` into `/tmp`, diff them, apply the chosen hunks to the project, smoke-test, bump `KIT_VERSION` in `kit.env`, log a decision. Never copy whole directories over a project. (kit README "Upgrading a project") (aroa A114)
- **Before committing a kit release, grep for secrets** ([secrets.md](secrets.md)) and check that no art, `reference/` material or project content slipped in. (aroa A114)

## Which kit parts each route uses
| Kit path | 3d-sprite | 2d | 3d-realtime | redesign |
|---|---|---|---|---|
| `tools/pipeline/` (Blender render, poses, anims, layers, release) | core | gates, `frames.py`, `layout/` pack, `head2d/` 2D-head tools, `items/{split_sheet,icon2d,card_frame}.py` | rig/fit/skin code as a starting point | core (after import) |
| `tools/pipeline/monsters/`, `items/` | core | catalog + icon tooling | fit/rig code | core |
| `tools/fleet/`, `tools/art-models/gpu/` | core | only if a GPU step exists | Hunyuan meshing | core |
| `tools/release/` (asset release, game pack) | core | core | release/plan logic only | core |
| `tools/map/` | core | ground painting, cell flags, pack, gate | logic grid, cell flags, gate ideas | as needed |
| `game/shared/`, `studio/` | core | core | timing/types only; renderer differs | core |
| `templates/`, `tools/notify`, `tools/guard_symlinks.*` | all | all | all | all |

## Reusable subagent
- `~/.claude/agents/sprite-visual-qa.md` (user scope): first-pass visual QA for character/item/mount/animation batches at game scale; read-only, routes issues to owning lanes. Spawn it for every render batch before the owner review. (aroa A116)
