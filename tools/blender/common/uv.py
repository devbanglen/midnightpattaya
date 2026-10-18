"""Box-projected UVs in world studs (1 UV unit = UV_STUDS_PER_TILE studs) for every face whose UVs were not set by
its primitive (cards and sign panels keep their 0..1 layout). Lets tileable textures / SurfaceAppearance be added
later without unwrapping."""
from .units import UV_STUDS_PER_TILE


def box_project(bm):
    uv = bm.loops.layers.uv.active
    keep = bm.faces.layers.int.get('uvkeep')
    s = 1.0 / UV_STUDS_PER_TILE
    for f in bm.faces:
        if keep is not None and f[keep]:
            continue
        n = f.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        for loop in f.loops:
            x, y, z = loop.vert.co
            if ax == 0:
                u, v = (y if n.x > 0 else -y), z
            elif ax == 1:
                u, v = (-x if n.y > 0 else x), z
            else:
                u, v = x, (y if n.z > 0 else -y)
            loop[uv].uv = (u * s, v * s)
