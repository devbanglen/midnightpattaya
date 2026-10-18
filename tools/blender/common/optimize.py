"""Mesh clean-up applied to every asset before export (bmesh, in place):
merge by distance (not two-sided sheets) -> dissolve degenerate -> limited dissolve (planar faces, never across materials or custom UV
cards) -> triangulate (beauty) -> sharp edges from angle (flat-shaded boxes, smooth poles/trunks)."""
import math
import bmesh

MERGE_DIST = 0.001          # studs
DISSOLVE_ANGLE = math.radians(0.5)
SHARP_ANGLE = math.radians(35)


def optimise(bm):
    nm = bm.faces.layers.int.get('nomerge')
    if nm is None:
        verts = bm.verts[:]
    else:       # two-sided sheets keep their coincident back verts (merging them collapsed the back faces)
        verts = [v for v in bm.verts if not any(f[nm] for f in v.link_faces)]
    bmesh.ops.remove_doubles(bm, verts=verts, dist=MERGE_DIST)
    bmesh.ops.dissolve_degenerate(bm, edges=bm.edges[:], dist=1e-5)
    keep = bm.faces.layers.int.get('uvkeep')
    # limited dissolve only over the box-projected faces: cards keep their 0..1 UVs untouched
    faces = [f for f in bm.faces if keep is None or f[keep] == 0]
    edges = list({e for f in faces for e in f.edges if all((keep is None or g[keep] == 0) for g in e.link_faces)})
    verts = list({v for e in edges for v in e.verts})
    bmesh.ops.dissolve_limit(bm, angle_limit=DISSOLVE_ANGLE, use_dissolve_boundaries=False,
                             verts=verts, edges=edges, delimit={'MATERIAL', 'NORMAL'})
    bmesh.ops.triangulate(bm, faces=bm.faces[:], quad_method='BEAUTY', ngon_method='BEAUTY')
    bmesh.ops.dissolve_degenerate(bm, edges=bm.edges[:], dist=1e-5)
    bm.normal_update()
    for e in bm.edges:
        if len(e.link_faces) != 2:
            e.smooth = False
            continue
        f0, f1 = e.link_faces
        if not (f0.smooth and f1.smooth) or e.calc_face_angle(0.0) > SHARP_ANGLE or f0.material_index != f1.material_index:
            e.smooth = False
    return len(bm.faces)
