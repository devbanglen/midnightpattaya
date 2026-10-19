"""Traffic-vehicle conventions shared by gen_traffic.py, validate_traffic.py and qa_traffic.py (pure Python).

The kit's shared files (common/materials.py, common/naming.py, validate.py) are not edited: this module EXTENDS the
shared material dict at run time with four car materials and supplies a TRF_ naming rule, and the traffic scripts
patch those into export.py / validate.py when they run. Nothing outside tools/blender/traffic + gen_traffic.py sees it.

Parts per vehicle (one material = one MeshPart <Asset>_<Short>):
  Paint  body colour, tinted by the client from a Thai-street palette (TrafficVehicles.PALETTES)
  Dark   glass, tyres, bumpers, grille, mirrors, seats, rails, rider clothes (one near-black: tinted glass at night
         reads the same as trim, and it frees a part for the second lamp colour)
  Head   head lamps (warm white), Neon in Roblox
  Tail   tail lamps (red), Neon in Roblox
"""
import re

# name: (short, base RGBA, metallic, roughness, emissive RGB or None)  -- same tuple layout as common/materials.py
TRF_MATERIALS = {
    'MP_CarPaint': ('Paint', (0.86, 0.86, 0.86, 1), 0.3, 0.35, None),
    'MP_CarDark':  ('Dark',  (0.05, 0.06, 0.08, 1), 0.4, 0.30, None),
    'MP_CarHead':  ('Head',  (1.00, 0.95, 0.82, 1), 0.0, 0.30, (1.0, 0.92, 0.75)),
    'MP_CarTail':  ('Tail',  (0.85, 0.05, 0.04, 1), 0.0, 0.30, (1.0, 0.05, 0.03)),
}

GROUPS = ('Car', 'Pickup', 'Songthaew', 'TukTuk', 'Scooter', 'Van')
ASSET_RE = re.compile(r'^TRF_(' + '|'.join(GROUPS) + r')_([A-Z][A-Za-z0-9]*)$')
CHILD_RE = re.compile(r'^TRF_[A-Za-z]+_[A-Z][A-Za-z0-9]*_[A-Z][A-Za-z]*$')
FORBIDDEN = ('_Att', '_InnerCage', '_OuterCage')

# collision footprints = the box Body of PattayaTraffic.client.luau makeCar (SHAPES), Roblox axes, studs
KIND_BOX = {0: (6.6, 2.4, 14.0), 1: (7.0, 2.6, 16.0), 2: (7.2, 6.0, 16.0)}
TRI_MAX = 2500
PARTS_MAX = 4


def check(name):
    if not ASSET_RE.match(name):
        return f'{name}: does not match {ASSET_RE.pattern}'
    if any(name.endswith(s) for s in FORBIDDEN):
        return f'{name}: forbidden importer suffix'
    return None


def install_materials():
    from common import materials
    materials.MATERIALS.update(TRF_MATERIALS)
