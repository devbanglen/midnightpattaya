# Studio backup and recovery — MIDNIGHT PATTAYA

Written 2026-10-19 after the owner enabled Team Create and saved a local `.rbxl` copy. Facts below were read from
Studio with the MCP tool (place id 117826785726076, game id 10771583260, owner type User 11827127344).

## Three different things called "saving"
| | What it protects | Who does it | Notes |
|---|---|---|---|
| **Git** (`devbanglen/midnightpattaya`, branch `main`) | source: Luau scripts, Python tools, docs, configs | the leader, after every verified step (`git log`) | **A commit is NOT a Studio save.** The place file holds the built world (parts, terrain, data ModuleScripts); Git holds only what can rebuild it. |
| **Roblox Cloud / Team Create** | the live place (everything in the DataModel) | Studio, automatically while Team Create is on | Edits made through the MCP tool count as edits in Team Create and are synced like any other. Play-mode changes are never saved. |
| **Local `.rbxl` file** | a frozen copy of the place at that moment | the owner, `File → Save to File As…` | the only backup that survives a cloud-side mistake (e.g. a bad publish or a wrong version restore) |

## Current status (checked 2026-10-19)
- Place is cloud-connected (PlaceId ≠ 0, owner = the user account that runs Studio).
- `TeamCreateService` is present; the owner reported Team Create ON and a local `.rbxl` backup saved. The tool cannot
  read the Team Create toggle itself: confirm by the **Team Create** window (View → Team Create) showing you connected.
- Auto-Recovery: the Studio setting could not be read through the tool (see the Studio Settings dialog: File → Studio
  Settings → search "Auto-Recovery": Enabled = true, Interval = 5 minutes recommended). Auto-Recovery files land in
  `%LOCALAPPDATA%\Roblox\AutoSaves\`; after a crash, Studio offers them on the next start (this happened once in this
  project on 2026-10-18 and restored the place).
- With Team Create on, Ctrl+S is still useful: it forces a sync/publish-to-cloud point.

## Rules (owner, 2026-10-19)
1. Before any large rebuild (roads, buildings, terrain, extension layers): a Git checkpoint **and** a fresh `.rbxl`
   backup saved by the owner, named with the date (`midnightpattaya_backup_YYYY-MM-DD[_n].rbxl`).
2. Never overwrite or delete an existing backup file; always a new name.
3. Never Publish, Save As over another place, or change ownership/collaborators without the owner's explicit OK.
4. Module-level backups the leader keeps inside the place before replacing generated data: `_prev_*` folders in
   `ServerStorage.PattayaData*` (old chunk/joints modules), `PattayaDataFurniture_prev_*`, removed procedural buildings in
   `ServerStorage.PattayaLandmarksRemoved` / `PattayaVisSliceRemoved`. `build/*_prev_*` folders on disk hold the
   previous generated outputs.

## How to recover
### A. Studio crashed / PC lost power
1. Start Studio. If an Auto-Recovery dialog appears, open the recovered copy, check it (world present, scripts present),
   then **Save As a new `.rbxl`** before anything else.
2. If Team Create was on, open the place from the cloud: it holds every synced edit up to the crash.

### B. A bad change was synced to the cloud (Team Create)
1. Creator Dashboard → the experience → **Places → (place) → Version History**: every save/publish is a version;
   pick one and **Restore** (this creates a new version, nothing is lost).
2. Or open the latest good local `.rbxl` and publish it **only with the owner's OK**.

### C. Generated data went wrong (roads, furniture, slice …) but the place is fine
- Roads/chunks: copy the module back from `_prev_*` and run `PattayaBuilder.RebuildChunks({ids})` (fresh).
- Furniture / coast / landmarks / visual slice: the builders have `Remove()` / `RestoreReplaced()`; re-run the exporter
  from Git and `Build()` again. Git history gives any earlier generator version.

### D. Open Cloud assets (Blender models)
- Asset ids are recorded in `roblox/src/ServerStorage/VisAssetsManifest.luau` (Git) and `build/vis_assets/upload_ids.json`.
  The assets live in the owner's inventory; a lost place does not lose them.

## Checklist the leader runs before a big rebuild
- [ ] `git status` clean, `git log -1` noted in the task
- [ ] owner confirmed "saved" (Ctrl+S / Team Create synced) **and** a dated `.rbxl` exists
- [ ] `_prev_*` module backups created inside the place
- [ ] rebuild in batches ≤ 8 chunks; probes after; drive regression after
