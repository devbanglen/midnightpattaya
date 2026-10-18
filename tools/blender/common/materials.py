"""The shared material list. Every asset may only use names from MATERIALS (max 4 per asset).

Each material becomes one child mesh (one MeshPart in Roblox) named <Asset>_<Short>, so a MeshPart has exactly one
material and can be tinted in Studio with MeshPart.Color / a SurfaceAppearance later (palettes from
buildings_game.json). Colours are glTF baseColorFactor only: no textures are embedded in VIS-1/VIS-2.
"""

# name: (short, base RGBA linear-ish sRGB, metallic, roughness, emissive RGB or None)
MATERIALS = {
    'MP_Wall':       ('Wall',    (0.82, 0.80, 0.74, 1), 0.0, 0.85, None),   # painted render / concrete
    'MP_WallAccent': ('Accent',  (0.36, 0.38, 0.42, 1), 0.0, 0.70, None),   # bands, pilasters, cornices, frames
    'MP_Glass':      ('Glass',   (0.10, 0.16, 0.24, 1), 0.6, 0.12, None),   # windows, curtain wall (opaque dark)
    'MP_Metal':      ('Metal',   (0.62, 0.64, 0.66, 1), 0.9, 0.35, None),   # railings, mullions, guardrail, AC
    'MP_MetalDark':  ('Steel',   (0.17, 0.18, 0.20, 1), 0.8, 0.45, None),   # poles, housings, frames
    'MP_Shutter':    ('Shutter', (0.55, 0.57, 0.58, 1), 0.7, 0.50, None),   # roller shutters, louvres
    'MP_Awning':     ('Awning',  (0.70, 0.12, 0.12, 1), 0.0, 0.90, None),   # fabric / sheet awnings (tint in Studio)
    'MP_Signboard':  ('Sign',    (0.95, 0.95, 0.95, 1), 0.0, 0.60, None),   # PLAIN placeholder panel, UV 0..1
    'MP_NeonCyan':   ('NeonC',   (0.00, 0.85, 1.00, 1), 0.0, 0.30, (0.0, 0.85, 1.0)),
    'MP_NeonMagenta': ('NeonM',  (1.00, 0.10, 0.70, 1), 0.0, 0.30, (1.0, 0.1, 0.7)),
    'MP_LampWarm':   ('Lamp',    (1.00, 0.86, 0.62, 1), 0.0, 0.30, (1.0, 0.82, 0.55)),
    'MP_SignalLens': ('Lens',    (0.12, 0.12, 0.10, 1), 0.0, 0.20, None),   # traffic-signal lenses (lit by script)
    'MP_Foliage':    ('Leaf',    (0.20, 0.48, 0.18, 1), 0.0, 0.80, None),   # palm fronds: alpha-ready cards, UV 0..1
    'MP_Bark':       ('Bark',    (0.43, 0.33, 0.24, 1), 0.0, 0.95, None),
    'MP_Wood':       ('Wood',    (0.55, 0.38, 0.22, 1), 0.0, 0.80, None),   # benches, utility poles
    'MP_Concrete':   ('Concrete', (0.60, 0.60, 0.58, 1), 0.0, 0.95, None),  # bases, kerbs, footings
    'MP_Stripe':     ('Stripe',  (0.92, 0.80, 0.10, 1), 0.0, 0.60, None),   # barrier arms, hazard paint
    'MP_Rubber':     ('Rubber',  (0.05, 0.05, 0.06, 1), 0.0, 0.95, None),
}


def short(name):
    return MATERIALS[name][0]


def make_bpy_materials():
    """Create every shared material in the current .blend (Principled BSDF; glTF exporter reads it)."""
    import bpy
    out = {}
    for name, (_s, rgba, metal, rough, emit) in MATERIALS.items():
        m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
        m.use_nodes = True
        bsdf = next(n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
        bsdf.inputs['Base Color'].default_value = rgba
        bsdf.inputs['Metallic'].default_value = metal
        bsdf.inputs['Roughness'].default_value = rough
        if emit:
            bsdf.inputs['Emission Color'].default_value = (*emit, 1)
            bsdf.inputs['Emission Strength'].default_value = 3.0
        m.use_backface_culling = True     # glTF doubleSided=false: two-sided cards are real geometry
        m.diffuse_color = rgba            # Workbench (QA renders) shows this colour
        out[name] = m
    return out
