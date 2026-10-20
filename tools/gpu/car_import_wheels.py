"""Imported (single fused mesh) car GLB -> front direction + wheel cylinders, in the pipeline's Roblox axes.

  python car_import_wheels.py <in.glb> <out_detect.json> [--length 4.5] [--front +z|-z|auto] [--views DIR]
  python car_import_wheels.py --luau <id>_wheels.json [id]     # prints the Studio install snippet

Pure numpy + Pillow (no trimesh), so it runs locally and on the GPU box. Used by tools/blender/import_car.py, which
does the cutting / decimation / export; this step only measures.

Frames:
  source   the GLB as delivered (glTF Y-up). Length must be along Z (checked).
  N        the pipeline frame: X right, Y up, front toward -Z, metres, car length = --length, centred on the bounding
           box of the WHOLE source mesh (wheels included). import_car.py re-centres on the final body later.
  N = (R @ source) * scale - centre, R = identity (front already -Z) or a 180 deg yaw (front was +Z).

Front: decided from the texture colour at each end of the car (both ends 6 % of the length, mid-height band):
  headlights/grille read as light grey-white highlights, taillights as saturated red lamps. Not reliable on a red car
  alone, so the side profile is printed too (bonnet slope vs. rear deck height) and --views writes end-on point
  splats for a human check. --front overrides the vote.

Wheels (per axle, as in export_car.py: lowest-point profile -> ground contact run -> radius from the arc), then
refined per wheel from the tyre itself:
  centre z/y   from the contact run and the arc radius
  radius       median radial distance of the tread points under the axle (below the centre, |dz| < 0.6 r)
  x_out, x_in  outermost / innermost |x| of those tread points (the tyre's width)
"""
import argparse, io, json, struct, sys
import numpy as np
from PIL import Image


def node_matrix(n):
    if 'matrix' in n:
        return np.array(n['matrix'], float).reshape(4, 4).T          # glTF stores column-major
    x, y, z, w = n.get('rotation', [0, 0, 0, 1])
    R = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                  [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                  [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    M = np.eye(4)
    M[:3, :3] = R * np.array(n.get('scale', [1, 1, 1]))
    M[:3, 3] = n.get('translation', [0, 0, 0])
    return M


def load_glb(path):
    b = open(path, 'rb').read()
    assert b[:4] == b'glTF', 'not a GLB'
    jl = struct.unpack('<I', b[12:16])[0]
    j = json.loads(b[20:20 + jl])
    B = b[20 + jl + 8:]
    assert len(j['meshes']) == 1 and len(j['meshes'][0]['primitives']) == 1, 'expects one mesh / one primitive'
    prim = j['meshes'][0]['primitives'][0]
    bv = j['bufferViews']

    def acc(i, dt, n):
        a = j['accessors'][i]; v = bv[a['bufferView']]
        o = v.get('byteOffset', 0) + a.get('byteOffset', 0)
        arr = np.frombuffer(B, dt, a['count'] * n, o)
        return arr.reshape(-1, n) if n > 1 else arr
    P = acc(prim['attributes']['POSITION'], np.float32, 3).astype(np.float64)
    UV = acc(prim['attributes']['TEXCOORD_0'], np.float32, 2).astype(np.float64)
    I = acc(prim['indices'], np.uint32, 1).reshape(-1, 3)
    # the mesh's node transform (matrix or TRS) is applied, so P is in glTF world space (parents not handled)
    node = next(n for n in j['nodes'] if n.get('mesh') == 0)
    assert not any(node in [j['nodes'][c] for c in n.get('children', [])] for n in j['nodes']), 'parented mesh node'
    M = node_matrix(node)
    P = P @ M[:3, :3].T + M[:3, 3]
    tex = j['materials'][prim['material']]['pbrMetallicRoughness']['baseColorTexture']['index']
    iv = bv[j['images'][j['textures'][tex]['source']]['bufferView']]
    img = Image.open(io.BytesIO(B[iv.get('byteOffset', 0):iv.get('byteOffset', 0) + iv['byteLength']])).convert('RGB')
    return P, UV, I, img


def vertex_colours(UV, img):
    T = np.asarray(img)
    px = np.clip((UV[:, 0] * (T.shape[1] - 1)).astype(int), 0, T.shape[1] - 1)
    py = np.clip((UV[:, 1] * (T.shape[0] - 1)).astype(int), 0, T.shape[0] - 1)   # glTF: v=0 is the image top
    return T[py, px].astype(float)


def end_scores(P, C):
    """Per end (+z / -z): share of light lamp-like pixels and of saturated red lamp pixels."""
    z, y = P[:, 2], P[:, 1]
    L, H = np.ptp(z), np.ptp(y)
    band = (y > y.min() + 0.25 * H) & (y < y.min() + 0.75 * H)
    out = {}
    for name, m in (('+z', z > z.max() - 0.06 * L), ('-z', z < z.min() + 0.06 * L)):
        c = C[m & band]
        lum = c.mean(1)
        light = (lum > 150) & (np.ptp(c, 1) < 60)
        lamp_red = (c[:, 0] > 170) & (c[:, 1] < 70) & (c[:, 2] < 70) & (lum > 85)
        out[name] = {'light': float(light.mean()), 'red': float(lamp_red.mean()), 'n': int(len(c))}
    return out


def profile(P, NB=40):
    z, y = P[:, 2], P[:, 1]
    e = np.linspace(z.min(), z.max(), NB + 1)
    b = np.clip(np.digitize(z, e) - 1, 0, NB - 1)
    top = np.full(NB, -np.inf)
    np.maximum.at(top, b, y)
    return ((e[:-1] + e[1:]) / 2).round(4).tolist(), top.round(4).tolist()


def splat(P, C, out, name, u, v, depth, S=1400):
    W = int(np.ptp(u) * S) + 20; H = int(np.ptp(v) * S) + 20
    iu = ((u - u.min()) * S + 10).astype(int); iv = (H - 1 - ((v - v.min()) * S + 10)).astype(int)
    o = np.argsort(-depth)
    im = np.full((H, W, 3), 255, np.uint8)
    for du in (0, 1):
        for dv in (0, 1):
            im[np.clip(iv[o] + dv, 0, H - 1), np.clip(iu[o] + du, 0, W - 1)] = C[o]
    Image.fromarray(im).save(f'{out}/{name}.png')


def find_wheels(N):
    """N: vertices in the pipeline frame. Returns {FL,FR,RL,RR: {x,y,z,r,x_out,x_in}}."""
    x, y, z = N.T
    ymin, H = y.min(), np.ptp(y)
    NB = 400
    edges = np.linspace(z.min(), z.max(), NB + 1)
    zc = (edges[:-1] + edges[1:]) / 2
    b = np.clip(np.digitize(z, edges) - 1, 0, NB - 1)
    prof = np.full(NB, np.inf)
    np.minimum.at(prof, b, y)
    d = prof - ymin
    L = np.ptp(z)
    wheels = {}
    for tag, sel in (('F', zc < 0), ('R', zc > 0)):      # front = -Z
        touch = sel & (d < 0.012 * H)
        runs, s0 = [], None
        for i in range(NB + 1):
            if i < NB and touch[i]:
                s0 = i if s0 is None else s0
            elif s0 is not None:
                runs.append((s0, i - 1)); s0 = None
        s, e = max(runs, key=lambda r: r[1] - r[0])
        z0 = (zc[s] + zc[e]) / 2
        est = []
        for step in (1, -1):
            last = d[(s + e) // 2]
            i = (e if step == 1 else s) + step
            while 0 <= i < NB and np.isfinite(d[i]) and d[i] >= last - 1e-4 and d[i] < 0.35 * H:
                dz = abs(zc[i] - z0)
                if d[i] > 0.01 * H:
                    est.append((dz * dz + d[i] * d[i]) / (2 * d[i]))
                last = d[i]; i += step
        r0 = float(np.median(est)) if est else 0.07 * L
        r0 = float(np.clip(r0, 0.05 * L, 0.11 * L))
        for side, sg in (('L', -1), ('R', 1)):
            yc, r = ymin + r0, r0
            for _ in range(3):   # refine centre height + radius from the tread under the axle
                rad = np.hypot(z - z0, y - yc)
                tread = (x * sg > 0) & (y < yc) & (np.abs(z - z0) < 0.6 * r) & (rad > 0.85 * r) & (rad < 1.1 * r)
                r = float(np.percentile(rad[tread], 90))
                yc = ymin + r
            rad = np.hypot(z - z0, y - yc)
            tread = (x * sg > 0) & (y < yc - 0.3 * r) & (np.abs(z - z0) < 0.5 * r) & (rad > 0.9 * r) & (rad < 1.05 * r)
            ax = np.abs(x[tread])
            x_out, x_in = float(np.percentile(ax, 99.5)), float(np.percentile(ax, 0.5))
            wheels[tag + side] = {'x': sg * (x_out + x_in) / 2, 'y': float(yc), 'z': float(z0), 'r': r,
                                  'x_out': x_out, 'x_in': x_in, 'w': x_out - x_in}
    return wheels


def luau_snippet(wheels_json, car_id):
    """Studio install snippet (command bar, edit mode) from import_car.py's <id>_wheels.json."""
    L = json.load(open(wheels_json))
    v = lambda p: f'Vector3.new({p[0]}, {p[1]}, {p[2]})'
    rim = L['rim']
    lines = [
        f'-- {car_id}: generated by tools/gpu/car_import_wheels.py --luau from {car_id}_wheels.json',
        'local SS = game:GetService("ServerStorage")',
        'local bodies = SS:FindFirstChild("CarBodies") or Instance.new("Folder", SS)',
        'bodies.Name = "CarBodies"',
        '-- the imported MeshParts anywhere in workspace: body "<id>", wheels "<id>_wheel_<FL|FR|RL|RR|L|R>"',
        'local parts, models = {}, {}',
        'for _, d in ipairs(workspace:GetDescendants()) do',
        f'	if d:IsA("MeshPart") and (d.Name == "{car_id}" or string.match(d.Name, "^{car_id}_wheel_%u+$")) then',
        '		table.insert(parts, d)',
        '		if d.Parent ~= workspace then models[d.Parent] = true end',
        '	end',
        'end',
        f'assert(#parts > 0, "no imported {car_id} MeshParts in workspace")',
        f'local old = bodies:FindFirstChild("{car_id}")',
        'if old then',
        '	local keep = SS:FindFirstChild("_old") or Instance.new("Folder", SS)',
        '	keep.Name = "_old"',
        '	old.Parent = keep',
        'end',
        'local f = Instance.new("Folder")',
        f'f.Name = "{car_id}"',
        'local found = {}',
        'for _, d in ipairs(parts) do',
        '	local key = string.match(d.Name, "_wheel_(%u+)$")',
        '	d.Anchored = true; d.CanCollide = false; d.CanQuery = false; d.CanTouch = false',
        '	d.Name = if key then "WheelMesh_" .. key else "Body"',
        '	table.insert(found, d.Name .. " " .. tostring(d.Size))',
        '	d.Parent = f',
        'end',
        f'f:SetAttribute("YawFix", 180)',
        f'f:SetAttribute("WheelRadius", {L["radius"]})',
        f'f:SetAttribute("WheelWidth", {L["width"]})',
        f'f:SetAttribute("RimColor", Color3.fromRGB({rim[0]}, {rim[1]}, {rim[2]}))',
    ]
    for k in ('FL', 'FR', 'RL', 'RR'):
        lines.append(f'f:SetAttribute("Wheel{k}", {v(L["wheels"][k])})')
    lines += ['f.Parent = bodies', 'for m in pairs(models) do if #m:GetDescendants() == 0 then m:Destroy() end end', 'print("CarBodies.' + car_id + ':", table.concat(found, ", "))']
    return chr(10).join(lines)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == '--luau':
        print(luau_snippet(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else 'red_sports'))
        return
    ap = argparse.ArgumentParser()
    ap.add_argument('glb'); ap.add_argument('out')
    ap.add_argument('--length', type=float, default=4.5)
    ap.add_argument('--front', default='auto', choices=['auto', '+z', '-z'])
    ap.add_argument('--views')
    a = ap.parse_args()

    P0, UV, I, img = load_glb(a.glb)
    # glTF is Y-up. The car's length is its longest horizontal axis (X or Z). R0 turns that axis onto +Z (a proper
    # rotation about Y), so the +z / -z end tests below work for any source orientation.
    ext0 = np.ptp(P0, 0)
    assert ext0[1] < max(ext0[0], ext0[2]), f'Y is not the up axis? extents {ext0}'
    if ext0[0] > ext0[2]:
        R0 = np.array([[0.0, 0, -1], [0, 1, 0], [1, 0, 0]])      # +X -> +Z, +Z -> -X
        axis = 'x'
    else:
        R0 = np.eye(3)
        axis = 'z'
    P = P0 @ R0.T
    ext = np.ptp(P, 0)
    C = vertex_colours(UV, img)
    sc = end_scores(P, C)
    zs, top = profile(P)
    # headlight end: more light (white/grey-chrome lamp) pixels. The red-lamp share is printed but not voted: on a red
    # car the body paint swamps it (measured on red_sports: +z 13 %, -z 10 %).
    vote = sc['+z']['light'] - sc['-z']['light']
    auto = '+z' if vote > 0 else '-z'
    # second opinion: the nose is the lower end of the roof-line profile (bonnet slopes down, rear deck stays high)
    prof_front = '+z' if top[-1] < top[0] else '-z'
    front = auto if a.front == 'auto' else a.front
    print('end scores', json.dumps(sc), 'light vote', round(vote, 4), '->', auto, '| profile ->', prof_front,
          f'(end heights -z {top[0]:.3f} +z {top[-1]:.3f}) | used', front)
    if auto != prof_front:
        print('WARNING: texture and profile disagree on the front; check the --views splats and pass --front')
    if a.views:
        x, y, z = P.T
        splat(P, C, a.views, 'src_end_plusz', -x, y, -z)
        splat(P, C, a.views, 'src_end_minusz', x, y, z)
        splat(P, C, a.views, 'src_side', -z, y, -x)

    yaw180 = front == '+z'
    R = (np.diag([-1.0, 1.0, -1.0]) if yaw180 else np.eye(3)) @ R0     # source (glTF world) -> N
    P = P0
    scale = a.length / ext[2]
    Q = P @ R.T * scale
    lo, hi = Q.min(0), Q.max(0)
    centre = (lo + hi) / 2
    N = Q - centre
    wheels = find_wheels(N)
    for k, w in wheels.items():
        print(f"{k}: x {w['x']:+.4f} y {w['y']:+.4f} z {w['z']:+.4f} r {w['r']:.4f} w {w['w']:.4f} (x_in {w['x_in']:.3f} x_out {w['x_out']:.3f})")
    json.dump({
        'source': {'tris': int(len(I)), 'verts': int(len(P)), 'bbox_min': P.min(0).tolist(), 'bbox_max': P.max(0).tolist(),
                   'texture': list(img.size)},
        'length_axis': axis, 'front_source_axis': ('+' if front == '+z' else '-') + axis, 'front_auto': auto,
        'R': R.tolist(), 'end_scores': sc, 'profile_top': {'z': zs, 'y': top},
        'yaw180': yaw180, 'scale': scale, 'centre': centre.tolist(), 'length': a.length,
        'size_N': (hi - lo).tolist(), 'wheels': wheels,
    }, open(a.out, 'w'), indent=1)


if __name__ == '__main__':
    main()
