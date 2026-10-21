"""Run a Blender script with the `bpy` Python module instead of the Blender binary (fallback when the GPU box is not
usable; team22 2026-10-21: the box's cgroup CPU quota was 1 % of a core, so every Blender job waited forever).

  <venv with bpy>/python tools/blender/bpy_local.py <script.py> -- <script args...>

Equivalent to `blender -b --factory-startup --python-exit-code 1 -P <script.py> -- <args...>`. The bpy wheel (PyPI
`bpy`, e.g. 5.1.2 for Python 3.13) goes in a throwaway venv outside the repo; nothing else is installed.
"""
import runpy
import sys
import traceback

if __name__ == '__main__':
    script = sys.argv[1]
    sys.argv = [script] + sys.argv[2:]
    try:
        runpy.run_path(script, run_name='__main__')
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        sys.exit(1)
