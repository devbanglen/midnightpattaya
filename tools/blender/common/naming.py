"""Asset naming rule (checked by validate.py too; pure Python):
  <FAMILY>_<Group>_<Variant>   FAMILY = BLD | RSD | RAC, groups below, parts CamelCase letters/digits only.
  Child meshes (one per material): <Asset>_<MaterialShort>, e.g. BLD_GF_ShophouseShutter_Wall.
  Avoid Roblox importer suffixes (_Att, _InnerCage, _OuterCage) which create other instance types."""
import re

GROUPS = {
    'BLD': ('GF', 'MF', 'TP', 'CN', 'RF'),       # ground floor, mid floor, top/parapet, corner, roof item
    'RSD': ('Light', 'Signal', 'Pole', 'Sign', 'Shelter', 'Barrier', 'Bench', 'Rail', 'Palm', 'Awning'),
    'RAC': ('Garage', 'Gantry', 'Guardrail', 'Pit', 'Banner'),
}
ASSET_RE = re.compile(r'^(BLD|RSD|RAC)_([A-Za-z]+)_([A-Z][A-Za-z0-9]*)$')
CHILD_RE = re.compile(r'^(BLD|RSD|RAC)_[A-Za-z]+_[A-Z][A-Za-z0-9]*_[A-Z][A-Za-z]*$')
FORBIDDEN = ('_Att', '_InnerCage', '_OuterCage')


def check(name):
    m = ASSET_RE.match(name)
    if not m:
        return f'{name}: does not match {ASSET_RE.pattern}'
    if m.group(2) not in GROUPS[m.group(1)]:
        return f'{name}: group {m.group(2)} not in {GROUPS[m.group(1)]}'
    if any(name.endswith(s) for s in FORBIDDEN):
        return f'{name}: forbidden importer suffix'
    return None
