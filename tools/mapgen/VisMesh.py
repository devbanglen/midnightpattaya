"""VIS-7.1 VisMesh - kit MeshParts for a sample block of the Beach Road slice, and mesh palms. Called by vis_slice.py.

Sample block (config vismesh.sample_block): the slice buildings whose centre lies within `radius` of `centre`
(map-local studs). For each of them the Part modules of the slots in vismesh.slots are replaced by the uploaded
Blender kit (build/vis_assets/manifest.json: names, MeshPart sizes and centres; asset ids come from
ServerStorage.VisAssetsManifest at build time). The box never changes: same VisHull, the VisCore is only inset deeper
on the decorated faces so that the kit modules (mount origin on the core face, module at local z <= 0) end inside
the original box face.

Rules
- Grid: modules are placed at their exact kit size (scale 1): n = floor(run / 7.1429) per row, centred on the run;
  the leftover (< 1 module) shows the VisCore wall. Mesh rows need the box's floor grid: ground floor 11.571, mid
  floors 8.571 (+- grid_tol); otherwise that row keeps its Parts. A scale field is exported per row (always 1 here).
- Inset per face = max(Part inset, depth of the deepest kit module on that face + inset_pad), at most
  min(max_inset, max_inset_frac x the box side across the face); a module deeper than that is replaced by its
  `alt` (lobby -> commercial bays, awning -> shutter, ...) or the row keeps its Parts.
- Tops (parapet / cornice / crown) and the corner top stand ON the roof (y = h ..), like the roof items, inside the
  box footprint; everything else stays inside the box.
- Every mesh instance gets the same footprint checks as the Parts (own box, road + sidewalk, discs, furniture, coast,
  landmarks, city props, other boxes). A failing instance makes its whole Part row stay Parts (no holes).
- Groups: every Part row has a group (its own index, or the first mid band's index for the full-height glass/fin rows
  the meshes make redundant). The builder skips a Part row when every mesh row of its group loaded; when an asset
  fails to load, the group falls back to the Part row (the row was exported with the deeper mesh inset).
Palms: every city palm (central chunk rows, PattayaBuilder Props: PalmTrunk + 5 PalmFrond) inside the slice bbox gets
an RSD_Palm_A/B/C mesh at the trunk foot with the Part palm's yaw (no lean), a 2-part impostor (PalmTrunk + flat
PalmFrond card) and an invisible collider; the Parts go to ServerStorage.VisMeshRemoved.
"""
import json, math, os
from collections import Counter, defaultdict

MW = 7.1429                                                   # kit module width (docs/BLENDER_PIPELINE.md)


def asset_table(path):
    m = json.load(open(path, encoding='utf-8'))
    return {a['name']: a for a in m['assets']}


def depth(a):
    """how far a mount module stands out of its mount plane (local -z)"""
    return -a['bbox_min'][2]


class Mesh:
    def __init__(self, cfg, env):
        self.cfg = cfg
        self.vc = cfg['vismesh']
        self.env = env
        self.assets = asset_table(os.path.join(env['root'], self.vc['assets_manifest']))
        self.used = []                                        # asset names in export order (manifest.meshAssets)
        self.slots = self.vc['slots']

    def aidx(self, name):
        if name not in self.used:
            self.used.append(name)
        return self.used.index(name) + 1

    def fits(self, name, limit):
        return name in self.assets and depth(self.assets[name]) + self.vc['inset_pad'] <= limit

    def pick(self, name, limit):
        """name or its alt chain, the first one that fits the face's inset limit (None: none fits)"""
        seen = set()
        while name and name not in seen:
            seen.add(name)
            if self.fits(name, limit):
                return name
            name = self.vc['alt'].get(name)
        return None

    # ---------------------------------------------------------------------------------------------------------------
    def building(self, B):
        env, vc, kit = self.env, self.vc, self.env['kit']
        FACES, ADJ = env['FACES'], env['ADJ']
        b = B['b']
        osm = b['osm']
        st = self.cfg['styles'][B['style']]
        G, fl = B['G'], B['fl']
        L, G0 = env['L'], env['G0']
        tol = vc['grid_tol']
        g_ok = abs(G - G0) < tol
        mid_ok = b['levels'] > 1 and abs(fl - L) < tol
        pls = [list(pl) for pl in B['pls']]
        faces = B['faces']
        why = Counter()

        # 1. inset per face from the deepest module that fits -------------------------------------------------------
        def perp(f):
            return b[FACES[f][2]]
        limit = {f: min(vc['max_inset'], vc['max_inset_frac'] * perp(f)) for f in faces}
        need = {f: B['ins'][f - 1] for f in faces}
        for pl in pls:
            f, mi = pl[0], pl[1]
            sl = self.slots.get(kit.mods[mi - 1])
            if not sl or sl.get('drop_with_mesh'):
                continue
            for role in ('cols', 'centre', 'wide', 'ac_alt', 'neon_alt', 'top'):
                names = sl.get(role)
                if names is None:
                    continue
                for n in (names if isinstance(names, list) else [names]):
                    p = self.pick(n, limit[f])
                    if p:
                        need[f] = max(need[f], depth(self.assets[p]) + vc['inset_pad'])
        ins_m = list(B['ins'])
        for f in faces:
            ins_m[f - 1] = round(need[f], 3)
        # corners need >= corner depth on both faces
        bd = dict(b, ins=ins_m)

        # 2. Part rows adjusted to the deeper core (u range) ----------------------------------------------------------
        for pl in pls:
            f = pl[0]
            a_, b_ = ADJ[f]
            span = b[FACES[f][3]]
            pl[2] = round(max(pl[2], -span / 2 + ins_m[a_ - 1]), 3)
            pl[3] = round(min(pl[3], span / 2 - ins_m[b_ - 1]), 3)
        groups = list(range(1, len(pls) + 1))                 # Part row i -> group id

        # 3. mesh rows per Part row ----------------------------------------------------------------------------------
        rows = []                                             # dict(face, asset, uc, v0, nv, dv, group, flags, j)
        first_mid = {}
        for i, pl in enumerate(pls):
            f, mi, u0, u1, nb, v0, vh, nv, dv, flags = pl
            mname = kit.mods[mi - 1]
            sl = self.slots.get(mname)
            if not sl:
                why[f'kept Parts: no kit asset for {mname}'] += 1
                continue
            if sl.get('drop_with_mesh'):
                continue
            kind = sl['kind']
            lim = limit[f]
            if kind == 'ground' and not g_ok:
                why['kept Parts: ground floor not on the 11.571 grid'] += 1
                continue
            if kind == 'mid' and not mid_ok:
                why['kept Parts: floors not on the 8.571 grid'] += 1
                continue
            if kind == 'whole_floors' and not mid_ok:
                why['kept Parts: floors not on the 8.571 grid'] += 1
                continue
            n = int(math.floor((u1 - u0) / MW + 1e-6))
            if n < 1:
                why['kept Parts: run shorter than one module'] += 1
                continue
            start = (u0 + u1) / 2 - n * MW / 2
            uc = [start + (j + 0.5) * MW for j in range(n)]
            g = i + 1
            if kind == 'top':
                name = self.pick(sl['top'], lim)
                if not name:
                    why['kept Parts: top module deeper than the inset limit'] += 1
                    continue
                vt = b['h']
                for j in range(n):
                    rows.append(dict(face=f, asset=name, uc=uc[j], v0=vt, nv=1, dv=0.0, group=g, flags=16, j=j))
                continue
            if kind == 'ground':
                v_0, v_n, v_d = 0.0, 1, 0.0
                litf = 2
            elif kind == 'whole_floors':                      # a full-height Part module -> one mesh per floor
                v_0, v_n, v_d = v0, b['levels'] - 1, fl
                litf = 1
            else:
                v_0, v_n, v_d = v0, nv, dv
                litf = 1
            cols = [self.pick(c, lim) for c in sl['cols']]
            cols = [c for c in cols if c]
            if not cols:
                why[f'kept Parts: {mname} modules deeper than the inset limit'] += 1
                continue
            taken = {}                                        # column j -> asset
            wide = self.pick(sl['wide'], lim) if sl.get('wide') else None
            if wide:
                wn = sl['wide_modules']
                for j0 in range(0, n - n % wn, wn):
                    taken[j0] = (wide, sum(uc[j0:j0 + wn]) / wn, wn)
                    for jj in range(j0 + 1, j0 + wn):
                        taken[jj] = None
            centre = self.pick(sl['centre'], lim) if sl.get('centre') else None
            if centre and n >= sl['centre_modules']:
                cm = sl['centre_modules']
                c0 = (n - cm) // 2
                taken = {c0: (centre, sum(uc[c0:c0 + cm]) / cm, cm)}
                for jj in range(c0 + 1, c0 + cm):
                    taken[jj] = None
            ac_alt = self.pick(sl['ac_alt'], lim) if sl.get('ac_alt') else None
            neon_alt = self.pick(sl['neon_alt'], lim) if sl.get('neon_alt') and B['neon'] else None
            sign_j = env['seeded'](osm, 30 + i, n)
            cur = []
            for j in range(n):
                if j in taken:
                    if taken[j] is None:
                        continue
                    name, u, _ = taken[j]
                else:
                    u = uc[j]
                    name = cols[env['seeded'](osm, 100 + 7 * i + j, len(cols))]
                    if ac_alt and env['lit_hash'](osm, f, mi, 0, j, 99, env['lit_cfg']['hash_mod']) % 100 >= b['acp']:
                        name = ac_alt                         # seeded AC density: no condenser on this column
                    if neon_alt and j == 0:
                        name = neon_alt
                cur.append(dict(face=f, asset=name, uc=u, v0=v_0, nv=v_n, dv=v_d, group=g, flags=litf, j=j))
            # signboard text (seeded density, as the Part SignFrame): the first column from sign_j whose asset has a sign
            if kind == 'ground' and sl.get('sign') and not (flags & 2) and B['txt'] and \
                    env['lit_hash'](osm, f, mi, 0, 0, 50, env['lit_cfg']['hash_mod']) % 100 < b['sgp']:
                for r in sorted(cur, key=lambda r: (r['j'] - sign_j) % n):
                    if any(p['material'] == 'MP_Signboard' for p in self.assets[r['asset']]['parts']):
                        r['flags'] |= 4
                        break
            rows += cur
            if kind in ('mid', 'whole_floors') and f not in first_mid:
                first_mid[f] = g
        # full-height glass bands / fins / curtain wall Parts are redundant when the face's floors are meshes
        for i, pl in enumerate(pls):
            sl = self.slots.get(kit.mods[pl[1] - 1])
            if sl and sl.get('drop_with_mesh') and pl[0] in first_mid:
                groups[i] = first_mid[pl[0]]

        # corners: the +U end of a mesh face whose neighbour there is a mesh face too
        mesh_faces = {r['face'] for r in rows}
        cn = vc['corners']
        for f in sorted(mesh_faces):
            gface = ADJ[f][1]
            if gface not in mesh_faces or ins_m[f - 1] < cn['min_inset'] or ins_m[gface - 1] < cn['min_inset']:
                continue
            span = b[FACES[f][3]]
            ucn = span / 2 - ins_m[gface - 1]
            glass = B['style'] in cn['glass_styles']
            if g_ok:
                rows.append(dict(face=f, asset=cn['ground'], uc=ucn, v0=0.0, nv=1, dv=0.0, group=0, flags=32, j=0))
            if mid_ok:
                rows.append(dict(face=f, asset=cn['glass_mid'] if glass else cn['mid'], uc=ucn, v0=G, nv=b['levels'] - 1,
                                 dv=fl, group=0, flags=32, j=0))
            if B.get('top') in cn['top_for']:
                rows.append(dict(face=f, asset=cn['top'], uc=ucn, v0=b['h'], nv=1, dv=0.0, group=0, flags=48, j=0))

        # 4. roof items ------------------------------------------------------------------------------------------------
        roof_rows = []
        cw = b['w'] - ins_m[0] - ins_m[1]
        cd = b['d'] - ins_m[2] - ins_m[3]
        ccx = (ins_m[1] - ins_m[0]) / 2
        ccz = (ins_m[3] - ins_m[2]) / 2
        for ri, rr in enumerate(B['roofs']):
            name = vc['roof_slots'].get(kit.roof_mods[rr[0] - 1])
            if not name:
                continue
            a = self.assets[name]
            sx, sz = a['size_studs'][0], a['size_studs'][2]
            m = vc['roof_margin']
            placed = None
            for yaw in (0, 90):
                ex, ez = (sx, sz) if yaw == 0 else (sz, sx)
                for fx, fz in ((rr[1], rr[2]), (ccx, ccz)):
                    if abs(fx - ccx) + ex / 2 <= cw / 2 - m and abs(fz - ccz) + ez / 2 <= cd / 2 - m:
                        placed = (fx, fz, yaw)
                        break
                if placed:
                    break
            if not placed or len(B['roofs']) > 1 and placed[:2] == (ccx, ccz) and (rr[1], rr[2]) != (ccx, ccz):
                why['kept Parts: roof item does not fit the core top'] += 1
                continue
            roof_rows.append(dict(asset=name, x=round(placed[0], 3), z=round(placed[1], 3), yaw=placed[2],
                                  group=1001 + ri))

        # 5. footprint checks per instance -----------------------------------------------------------------------------
        bad_groups, fails = set(), Counter()
        keep_rows = []
        for r in rows:
            ok = True
            for inst in self.instances(bd, r):
                res = env['check'](bd, inst)
                if res:
                    ok = False
                    fails[res] += 1
                    break
            if ok:
                keep_rows.append(r)
            elif r['group']:
                bad_groups.add(r['group'])
        keep_roof = []
        for r in roof_rows:
            res = env['check'](bd, self.roof_instance(bd, r))
            if res:
                fails[res] += 1
                bad_groups.add(r['group'])
            else:
                keep_roof.append(r)
        rows = [r for r in keep_rows if r['group'] not in bad_groups]
        roof_rows = [r for r in keep_roof if r['group'] not in bad_groups]
        for k, v in fails.items():
            why[f'kept Parts: mesh instance fails check "{k}"'] += v
        meshed = {r['group'] for r in rows if r['group']} | {r['group'] for r in roof_rows}
        for i in range(len(groups)):
            if groups[i] not in meshed and groups[i] != i + 1:
                groups[i] = i + 1                             # its mid band did not mesh: the glass band stays

        # 6. counts (everything loads) ---------------------------------------------------------------------------------
        st_cfg = st
        part_parts = []
        for i, pl in enumerate(pls):
            if groups[i] in meshed:
                continue
            part_parts += kit.face_parts(bd, pl, st_cfg)
        roof_part_rows = [rr for ri, rr in enumerate(B['roofs']) if 1001 + ri not in meshed]
        for rr in roof_part_rows:
            part_parts += kit.roof_parts(bd, rr)
        n_mesh, by_asset, slots_swapped, lit = 0, Counter(), Counter(), 0
        for r in rows:
            a = self.assets[r['asset']]
            n_mesh += r['nv'] * len(a['parts'])
            by_asset[r['asset']] += r['nv']
            slot = kit.mods[pls[r['group'] - 1][1] - 1] if r['group'] else 'corner'
            slots_swapped[f"{slot} -> {r['asset']}"] += r['nv']
            if r['flags'] & 3 and any(p['material'] == 'MP_Glass' for p in a['parts']):
                pct = st['lit_win'] if r['flags'] & 1 else st['lit_shop']
                spread = env['lit_cfg']['spread']
                pct = max(0, min(100, pct + osm % (2 * spread + 1) - spread))
                for k in range(r['nv']):
                    if self.mesh_lit_hash(osm, r, k) % 100 < pct:
                        lit += 1
        for r in roof_rows:
            n_mesh += len(self.assets[r['asset']]['parts'])
            by_asset[r['asset']] += 1
            slots_swapped[f"{kit.roof_mods[B['roofs'][r['group'] - 1001][0] - 1]} -> {r['asset']}"] += 1
        n_part = 2 + len(part_parts)
        rep = {'osm': osm, 'cat': b['cat'], 'style': B['style'], 'levels': b['levels'], 'h': b['h'],
               'centre_world_xz': [round(b['x'] + 20000, 1), round(b['z'], 1)], 'size_wdh': [b['w'], b['d'], b['h']],
               'yaw': b['yaw'], 'faces': B['faces'], 'inset_part': B['ins'], 'inset_mesh': ins_m,
               'before': {'parts': B['n'], 'meshparts': 0},
               'after': {'parts': n_part, 'meshparts': n_mesh, 'total': n_part + n_mesh},
               'slots_swapped_instances': dict(sorted(slots_swapped.items())), 'asset_instances': dict(sorted(by_asset.items())),
               'lit_glass_meshparts': lit, 'kept_parts_reasons': dict(why),
               'signboard_meshparts_with_text': sum(1 for r in rows if r['flags'] & 4),
               'neon_meshparts': sum(r['nv'] for r in rows for p in self.assets[r['asset']]['parts']
                                     if p['material'] in ('MP_NeonCyan', 'MP_NeonMagenta')),
               'part_rows_meshed': sum(1 for gid in groups if gid in meshed), 'part_rows': len(pls)}
        out = {'ins': ins_m, 'p': [v for pl in pls for v in pl], 'pg': groups,
               'rg': [1001 + ri for ri in range(len(B['roofs']))],
               'm': [v for r in rows for v in (r['face'], self.aidx(r['asset']), round(r['uc'], 3), round(r['v0'], 3), r['nv'],
                                               round(r['dv'], 3), 1, r['group'], r['flags'], r['j'])],
               'q': [v for r in roof_rows for v in (self.aidx(r['asset']), r['x'], r['z'], r['yaw'], 1, r['group'])],
               'parts': n_part, 'meshParts': n_mesh}
        return out, rep

    def mesh_lit_hash(self, osm, r, k):
        """twin of PattayaVisSliceBuilder's mesh pane hash: litHash(osm, face, 900 + asset, floor, column, 0)"""
        return (osm % self.env['lit_cfg']['hash_mod']) * 7919 + r['face'] * 104729 + (900 + r['aidx']) * 1009 + k * 131 + r['j'] * 31

    def instances(self, bd, r):
        """pseudo parts (vis_slice part dicts) for every instance of a mesh row: the asset bbox in the face frame"""
        a = self.assets[r['asset']]
        r['aidx'] = self.aidx(r['asset'])
        (x0, y0, z0), (x1, y1, z1) = a['bbox_min'], a['bbox_max']
        ins = bd['ins'][r['face'] - 1]
        for k in range(r['nv']):
            vb = r['v0'] + k * r['dv']
            yield {'k': r['asset'], 'face': r['face'], 'u': (r['uc'] + x0, r['uc'] + x1), 'v': (vb + y0, vb + y1),
                   'n': (-ins - z1, -ins - z0), 'above': bool(r['flags'] & 16),
                   'tol': self.vc['grid_tol']}       # a 2-level box is 20.1 tall, its kit rows 20.142

    def roof_instance(self, bd, r):
        a = self.assets[r['asset']]
        (x0, y0, z0), (x1, y1, z1) = a['bbox_min'], a['bbox_max']
        cx, cz = (x0 + x1) / 2, (z0 + z1) / 2
        sx, sz = x1 - x0, z1 - z0
        if r['yaw'] == 90:                                    # CFrame.Angles(0, pi/2, 0): local (x, z) -> (z, -x)
            cx, cz, sx, sz = cz, -cx, sz, sx
        return {'k': r['asset'], 'roof': True, 'c': (r['x'] + cx, bd['h'] + (y0 + y1) / 2, r['z'] + cz), 's': (sx, y1 - y0, sz)}

    # ---------------------------------------------------------------------------------------------------------------
    def assets_out(self):
        mat = self.vc['mat_map']
        out = []
        for name in self.used:
            a = self.assets[name]
            parts = []
            for p in a['parts']:
                short = p['name'][len(name) + 1:]
                col, mname = mat[p['material']]
                parts.append({'name': p['name'], 'short': short, 'mp': p['material'], 'col': col, 'mat': mname,
                              'size': p['size'], 'centre': p['centre']})
            out.append({'name': name, 'kind': a['kind'], 'bmin': a['bbox_min'], 'bmax': a['bbox_max'], 'parts': parts})
        return out


def palms(cfg, env, mesh):
    """palm rows for the builder: map-local x, z, variant (1..3 into vismesh.palms.assets), yaw (rad), old trunk h"""
    pc = cfg['vismesh']['palms']
    x0, z0, x1, z1 = env['area_bounds']
    rows, by_src, by_var = [], Counter(), Counter()
    for (x, z), src in zip(env['props']['palms'], env['props']['palm_src']):
        if not (x0 <= x <= x1 and z0 <= z <= z1):
            continue
        h_old = 26 + ((x * 7 + z * 13) % 9)                   # PattayaBuilder.buildProps (Luau % == Python % on floats)
        yaw = (x * 3) % 6.28
        var = int(math.floor(abs(x * 7 + z * 13))) % len(pc['assets'])
        rows.append({'src': src, 'x': x, 'z': z, 'v': var + 1, 'yaw': round(yaw, 4), 'h': round(h_old, 3)})
        by_src[src] += 1
        by_var[pc['assets'][var]] += 1
    for a in pc['assets']:
        mesh.aidx(a)
    n_mesh_parts = sum(len(mesh.assets[pc['assets'][r['v'] - 1]]['parts']) for r in rows)
    rep = {'palms': len(rows), 'by_variant': dict(sorted(by_var.items())), 'by_city_chunk': dict(sorted(by_src.items())),
           'before': {'parts': 6 * len(rows), 'note': 'PattayaBuilder: PalmTrunk cylinder + 5 PalmFrond per palm'},
           'after': {'meshparts': n_mesh_parts, 'impostor_parts': 2 * len(rows), 'collider_parts': len(rows),
                     'parts': 3 * len(rows)},
           'lod': f"full mesh within {pc['full_range']} studs, impostor beyond (client VisMeshPalmLOD); all palm parts are named "
                  'PalmTrunk / PalmFrond so PattayaLOD still hides them beyond LOD_PropRange'}
    return rows, rep
