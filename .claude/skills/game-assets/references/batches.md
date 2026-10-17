# Batches (many sets / many weapons at once)

- Write all design files and prompt files first; start the runs in the background with unbuffered output
  (`PYTHONUNBUFFERED=1`), one log per set, a few seconds apart.
- Watch the logs with a filter on `error`, `Traceback`, `FAIL`, `WARN`, `credits`, `sheet` (a silent log is not success).
- Outfit runs: `--jobs 1` or `2` each when several run at once (Blender fit launches add up).
- Meshy: all jobs in parallel; one log per job.
- Parallel subagents are good for the visual naming of new templates (one template each, separate output files).
- After the runs: list every non-PASS line, fix (shape op, redraw, fit mode), rerun only that slot/gender.
- One lab build at the end (it is locked anyway), then the preview screenshots for the owner.
- Report: per set PASS/FAIL with numbers, GPT image count, Meshy jobs and credits, links.
- Many Blender launches at once (7 outfit runs + Meshy conversions) drop launches even after 3 retries: a `spec ... FAILED`
  line then makes the concept step skip that piece (`ref ... not found`, no API call). Rerun that slot alone at the end.
- In zsh scripts arrays are 1-based; in `sh -c` a `#colour` argument starts a comment: pass colours from Python, not a shell string.
- Disk: `spec/*_geo.npz` and `spec/idmap/*.npz` (~25 MB each, ~12 GB after 28 sets) are caches; the spec step rebuilds
  them when missing. Delete them after a batch is done (A077 cleanup: 15 GB → 3.3 GB).
