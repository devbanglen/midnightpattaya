"""Road visual analysis + offline junction pilot (team20/road-visual).

Modules:
  world.py      load the BUILT road layers (slabs, fills, discs, aprons, corner fills, shoulders, sidewalks, markings,
                crossings, buildings) exactly as the Studio builders build them, from build/ (read only)
  analyze.py    defect metrics for one area and citywide (overlaps, disc overhang, meaningless asphalt, crossings vs
                legs, lane-line continuity, proportions) -> build/roadvis/analysis.json
  junction.py   offline generator: new junction geometry for ONE area from the road graph (collision + visual +
                markings + crossings + sidewalks / kerbs) -> build/roadvis/pilot_<name>.json
  raster.py     top-down classification images (before = current chunk data, after = pilot), same renderer
  scene.py      exports both states as a triangle scene (JSON) for the Blender preview
  blender_preview.py  runs inside Blender on the GPU box (aerial / street / driver views, day light)
  cli.py        one command for everything: python -m tools.roadvis.cli (or python tools/roadvis/cli.py)

Everything here is OFFLINE. Nothing writes to build/ outside build/roadvis, nothing touches Studio. Map data (c)
OpenStreetMap contributors, ODbL 1.0.
"""
