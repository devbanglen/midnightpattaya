"""Offline HUD layout audit (team12/quality, 2026-10-20): which on-screen rectangles overlap on phone / tablet / desktop?

  .venv\\Scripts\\python tools\\qa\\ui_layout_audit.py                   # all viewports, touch + mouse
  .venv\\Scripts\\python tools\\qa\\ui_layout_audit.py --json build\\qa\\ui_layout.json

Read-only. Re-implements the layout rules of the HUD scripts in Python and reads their layout constants from the Luau
sources (regex; the script stops if a constant is not found, so a renamed constant cannot pass silently):
  MidnightHUD.client.luau          ANCHORS, COMPACT, MARGIN, CM, COMPACT_BIG_BOTTOM, COMPACT_JOB_H, layout(),
                                   layoutCompact(), placeAvoiding() (speedometer slide-left loop, job strip width)
  MidnightUI/Responsive.luau       REFERENCE, MIN_SCALE, MAX_SCALE, TOUCH_MIN_SCALE, COMPACT_WIDTH, TOUCH_RESERVE
  MidnightUI/TouchControls.luau    SLOTS, GRID_H, GAP, MIN_BUTTON, anchorPoint() (grid above the jump button)
  PattayaMinimapClient.client.luau compact card 150 x 120 screen px + 36 px control column, CARD_W / CARD_H
  MidnightSpeedo.client.luau       desktop panel 480 x 330 (bottom-right of the BottomRight anchor), compact 242 x 113
  PattayaPerfTelemetry.client.luau owner-only overlay 250 x 34 at (0.5, -125, 1, -40)
  CarController.client.luau        (read only) the NOS / DRIFT / R actions are registered into TouchControls slots
Roblox's own UI (approximations of the CoreScripts, stated so they can be checked in Studio):
  top bar     GuiInset 58 px (new UI): the HUD ScreenGuis have IgnoreGuiInset = false, so their space is
              W x (H - 58) starting under the bar; the camera ViewportSize (used for the scale) is the full screen
  jump        TouchJump: 70 px at (W-95, H-90) when min(W, H) <= 500, else 120 px at (W-170, H-210) (gui space)
  thumbstick  DynamicThumbstick start zone: left 40 % x bottom 2/3 of the screen (landscape); a touch that begins on
              an interactive GuiObject there goes to that object, not to the stick (TouchGui assumed to share the
              HUD's inset space). Rest graphic ~ bottom-left
              (0, H-200, 200, 200) on small screens, (0, H-280, 280, 280) otherwise (approximation)
Scenarios per viewport: touch (always the compact HUD + touch buttons) and mouse (compact when W < 1100).
Transient widgets (activity strip, toasts, job strip, context buttons) are included and marked transient.
Output: overlaps between visible widget rectangles (excluding a widget and its own parts), widgets in Roblox's touch
zones, widgets outside the screen. Exit code 0 always (it is a report).
"""
import argparse, json, math, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
SRC = os.path.join(REPO, 'roblox', 'src')
F = {
    'hud': os.path.join(SRC, 'StarterPlayer', 'StarterPlayerScripts', 'MidnightHUD.client.luau'),
    'speedo': os.path.join(SRC, 'StarterPlayer', 'StarterPlayerScripts', 'MidnightSpeedo.client.luau'),
    'minimap': os.path.join(SRC, 'StarterPlayer', 'StarterPlayerScripts', 'PattayaMinimapClient.client.luau'),
    'perf': os.path.join(SRC, 'StarterPlayer', 'StarterPlayerScripts', 'PattayaPerfTelemetry.client.luau'),
    'car': os.path.join(SRC, 'StarterPlayer', 'StarterPlayerScripts', 'CarController.client.luau'),
    'resp': os.path.join(SRC, 'ReplicatedStorage', 'MidnightUI', 'Responsive.luau'),
    'touch': os.path.join(SRC, 'ReplicatedStorage', 'MidnightUI', 'TouchControls.luau'),
}
VIEWPORTS = [(830, 439), (1334, 750), (2340, 1080), (1024, 768)]
INSET = 58


def src(k):
    return open(F[k], encoding='utf-8').read()


def num(text, pattern, what):
    m = re.search(pattern, text)
    if not m:
        sys.exit(f'constant not found: {what} ({pattern})')
    return float(m.group(1))


def vec_table(text, block_name):
    """{Name = Vector2.new(x, y)} or {Name = {anchor = ..., size = Vector2.new(x, y)}} entries of `local <block> = {`"""
    i = text.index(f'local {block_name} = {{')
    j = text.index('\n}', i)
    out = {}
    for m in re.finditer(r'(\w+) = (?:\{anchor = Vector2\.new\(([\d.]+), ([\d.]+)\), size = )?Vector2\.new\((\d+), (\d+)\)',
                         text[i:j]):
        out[m.group(1)] = (float(m.group(4)), float(m.group(5)))
    return out


def load():
    hud, resp, touch, mm, sp, perf, car = (src(k) for k in ('hud', 'resp', 'touch', 'minimap', 'speedo', 'perf', 'car'))
    c = {
        'ANCHORS': vec_table(hud, 'ANCHORS'), 'COMPACT': vec_table(hud, 'COMPACT'),
        'MARGIN': num(hud, r'local MARGIN = (\d+)', 'MARGIN'), 'CM': num(hud, r'local CM = (\d+)', 'CM'),
        'BIG_BOTTOM': num(hud, r'local COMPACT_BIG_BOTTOM = (\d+)', 'COMPACT_BIG_BOTTOM'),
        'JOB_H': num(hud, r'local COMPACT_JOB_H = (\d+)', 'COMPACT_JOB_H'),
        'MENU': num(hud, r'name = "MenuButton".*?\n\s*size = UDim2\.fromOffset\((\d+)', 'menu button size'),
        'CARD': (num(hud, r'name = "PlayerCard", size = UDim2\.fromOffset\((\d+)', 'card w'),
                 num(hud, r'name = "PlayerCard", size = UDim2\.fromOffset\(\d+, (\d+)', 'card h')),
        'REF': (num(resp, r'REFERENCE = Vector2\.new\((\d+)', 'REFERENCE x'), num(resp, r'REFERENCE = Vector2\.new\(\d+, (\d+)', 'REFERENCE y')),
        'MIN_SCALE': num(resp, r'MIN_SCALE = ([\d.]+)', 'MIN_SCALE'), 'MAX_SCALE': num(resp, r'MAX_SCALE = ([\d.]+)', 'MAX_SCALE'),
        'TOUCH_MIN': num(resp, r'TOUCH_MIN_SCALE = ([\d.]+)', 'TOUCH_MIN_SCALE'),
        'COMPACT_WIDTH': num(resp, r'COMPACT_WIDTH = (\d+)', 'COMPACT_WIDTH'),
        'TOUCH_RESERVE': num(resp, r'TOUCH_RESERVE = (\d+)', 'TOUCH_RESERVE'),
        'GAP': num(touch, r'TouchControls\.GAP = (\d+)', 'GAP'), 'GRID_H': num(touch, r'GRID_H = (\d+)', 'GRID_H'),
        'MIN_BUTTON': num(touch, r'MIN_BUTTON = (\d+)', 'MIN_BUTTON'),
        'SLOTS': {m.group(1): tuple(float(v) for v in m.group(2, 3, 4)) for m in
                  re.finditer(r'(\w+) = \{dx = (\d+), dy = (\d+), size = (\d+)\}', touch)},
        'MM_COMPACT': (num(mm, r'w, h, hh, pad = (\d+), \d+', 'compact card w'), num(mm, r'w, h, hh, pad = \d+, (\d+)', 'compact card h')),
        'MM_CTRL': num(mm, r'b\.Size = UDim2\.fromOffset\((\d+), \d+\)\n\s*b\.TextSize = Theme\.size\.body', 'compact control size'),
        'MM_CTRL_GAP': num(mm, r'b\.Position = UDim2\.new\(1, (\d+), 0, \(i - 1\)', 'compact control gap'),
        'MM_CTRL_STEP': num(mm, r'\(i - 1\) \* (\d+)\)', 'compact control step'),
        'SPEEDO_PANEL': (num(sp, r'panel\.Size = UDim2\.fromOffset\((\d+)', 'speedo w'), num(sp, r'panel\.Size = UDim2\.fromOffset\(\d+, (\d+)', 'speedo h')),
        'PERF': (num(perf, r'label\.Size = UDim2\.fromOffset\((\d+), \d+\)\n', 'perf w'), num(perf, r'label\.Size = UDim2\.fromOffset\(\d+, (\d+)\)\n', 'perf h'),
                 num(perf, r'label\.Position = UDim2\.new\(0\.5, (-?\d+), 1, -?\d+\)\n', 'perf x'),
                 num(perf, r'label\.Position = UDim2\.new\(0\.5, -?\d+, 1, (-?\d+)\)\n', 'perf y')),
        'CAR_SLOTS': re.findall(r'touchRegister\("(\w+)", \{slot = "(\w+)"', car),
    }
    return c


def rect(name, x, y, w, h, group, interactive=False, transient=False):
    return {'name': name, 'x': round(x, 1), 'y': round(y, 1), 'w': round(w, 1), 'h': round(h, 1), 'group': group,
            'interactive': interactive, 'transient': transient}


def inter(a, b, pad=0.0):
    return a['x'] < b['x'] + b['w'] + pad and a['x'] + a['w'] + pad > b['x'] and a['y'] < b['y'] + b['h'] + pad and a['y'] + a['h'] + pad > b['y']


def area(a, b):
    w = min(a['x'] + a['w'], b['x'] + b['w']) - max(a['x'], b['x'])
    h = min(a['y'] + a['h'], b['y'] + b['h']) - max(a['y'], b['y'])
    return max(w, 0) * max(h, 0)


def simulate(c, vp, touch):
    VX, VY = vp
    W, H = VX, VY - INSET                       # gui space of IgnoreGuiInset = false
    lo = c['TOUCH_MIN'] if touch else c['MIN_SCALE']
    s = min(max(min(VX / c['REF'][0], VY / c['REF'][1]), lo), c['MAX_SCALE'])
    compact = touch or VX < c['COMPACT_WIDTH']
    R = []
    roblox = []
    # Roblox touch UI
    jump = None
    if touch:
        small = min(W, H) <= 500
        jump = rect('Roblox JumpButton', W - 95, H - 90, 70, 70, 'roblox', True) if small else rect('Roblox JumpButton', W - 170, H - 210, 120, 120, 'roblox', True)
        roblox.append(jump)
        roblox.append(rect('Roblox thumbstick start zone (left 40% x bottom 2/3)', 0, H / 3, W * 0.4, H * 2 / 3, 'zone'))
        g = 200 if small else 280
        roblox.append(rect('Roblox thumbstick rest graphic (approx.)', 0, H - g, g, g, 'roblox'))
    CM, M = c['CM'], c['MARGIN']
    if compact:
        tl = c['COMPACT']['TopLeft']
        R.append(rect('PlayerCard (TopLeft)', CM, CM, tl[0] * s, tl[1] * s, 'TopLeft'))
        mb = c['MENU'] * s
        R.append(rect('MenuButton (TopRight)', W - CM - mb, CM, mb, mb, 'TopRight', True))
        tc = c['COMPACT']['TopCenter']
        R.append(rect('Activity strip (TopCenter)', W / 2 - tc[0] * s / 2, CM, tc[0] * s, tc[1] * s, 'TopCenter', transient=True))
        # minimap: card in screen px at the BottomLeft anchor (moved under the player card), controls column right of it
        y0 = CM + math.floor(tl[1] * s) + 8
        mw, mh = c['MM_COMPACT']
        R.append(rect('Minimap card', CM, y0, mw, mh, 'Minimap', True))
        cs, cg, st = c['MM_CTRL'], c['MM_CTRL_GAP'], c['MM_CTRL_STEP']
        for i, nm in enumerate(('zoom in', 'zoom out', 'expand')):
            R.append(rect(f'Minimap {nm}', CM + mw + cg, y0 + i * st, cs, cs, 'Minimap', True))
        # touch grid (TouchControls.anchorPoint / rectFor)
        grid = []
        if touch:
            Rr = jump['x'] + jump['w']
            B = jump['y'] - c['GAP']
            top = CM + mb + c['GAP']
            k = min(max((B - top) / c['GRID_H'], c['MIN_BUTTON'] / 56), 1)
            used = {slot for _, slot in c['CAR_SLOTS']}
            for slot, (dx, dy, size) in c['SLOTS'].items():
                tr = slot not in used                 # race / sprint / circuit / ctx: only near their event
                sz = math.floor(size * k + 0.5)
                grid.append(rect(f'Touch button {slot}', math.floor(Rr - dx * k + 0.5), math.floor(B - dy * k + 0.5), sz, sz,
                                 'TouchGrid', True, tr))
            R += grid
        # placeAvoiding: toasts + speedometer
        sw, sh = c['COMPACT']['BottomRight'][0] * s, c['COMPACT']['BottomRight'][1] * s
        toastTop = CM + c['BIG_BOTTOM'] * s + 6
        maxTop = H - CM - c['JOB_H'] * s - 8 - sh
        fit = min(max(math.floor((maxTop - 6 - toastTop + 8 * s) / (72 * s)), 1), 2)
        toastH = fit * 64 + (fit - 1) * 8
        R.append(rect(f'Toasts ({fit})', W / 2 - c['COMPACT']['Toasts'][0] * s / 2, toastTop, c['COMPACT']['Toasts'][0] * s, toastH * s, 'Toasts', True, True))
        toastBottom = toastTop + toastH * s
        stop = min(max(toastBottom + 6, H - 90 - sh), maxTop)
        x = W / 2 - sw / 2
        obstacles = grid + ([jump] if jump else [])
        while x > CM and any(inter(rect('', x, stop, sw, sh, ''), o, 8) for o in obstacles):
            x -= 8
        R.append(rect('Speedometer (compact)', math.floor(x), math.floor(stop), sw, sh, 'Speedo'))
        bcH = c['COMPACT']['BottomCenter'][1] * s
        bcTop = H - CM - bcH
        half = W / 2 - CM
        for o in obstacles:
            if o['y'] < bcTop + bcH + 8 and o['y'] + o['h'] + 8 > bcTop:
                if o['x'] >= W / 2:
                    half = min(half, o['x'] - 8 - W / 2)
                elif o['x'] + o['w'] <= W / 2:
                    half = min(half, W / 2 - (o['x'] + o['w']) - 8)
                else:
                    half = 0
        jw = min(max(2 * half / s, 120), 620) * s
        R.append(rect('Job strip (BottomCenter)', W / 2 - jw / 2, H - CM - c['JOB_H'] * s, jw, c['JOB_H'] * s, 'BottomCenter', True, True))
    else:
        A = c['ANCHORS']
        R.append(rect('PlayerCard (TopLeft)', M, M, c['CARD'][0] * s, c['CARD'][1] * s, 'TopLeft'))
        R.append(rect('Quick menu tiles (TopRight)', W - M - A['TopRight'][0] * s, M, A['TopRight'][0] * s, A['TopRight'][1] * s, 'TopRight', True))
        R.append(rect('Activity strip (TopCenter)', W / 2 - A['TopCenter'][0] * s / 2, M, A['TopCenter'][0] * s, A['TopCenter'][1] * s, 'TopCenter', transient=True))
        bl = A['BottomLeft']
        R.append(rect('Minimap card', M, H - M - bl[1] * s, bl[0] * s, bl[1] * s, 'Minimap', True))
        bc = A['BottomCenter']
        R.append(rect('Chips + job strip (BottomCenter)', W / 2 - bc[0] * s / 2, H - M - bc[1] * s, bc[0] * s, bc[1] * s, 'BottomCenter', True, True))
        pw, ph = c['SPEEDO_PANEL']
        R.append(rect('Speedometer panel', W - M - pw * s, H - M - ph * s, pw * s, ph * s, 'Speedo'))
        ts = A['Toasts']
        R.append(rect('Toasts (3)', W - M - ts[0] * s, H - M - A['BottomRight'][1] * s - 12 - ts[1] * s, ts[0] * s, ts[1] * s, 'Toasts', True, True))
    pw, ph, px_, py_ = c['PERF']
    R.append(rect('PerfTelemetry overlay (owner only)', W / 2 + px_, H + py_, pw, ph, 'Perf', True))
    # findings
    out = []
    for i in range(len(R)):
        for j in range(i + 1, len(R)):
            a, b = R[i], R[j]
            if a['group'] == b['group']:
                continue
            if inter(a, b):
                out.append({'kind': 'overlap', 'a': a['name'], 'b': b['name'], 'area': round(area(a, b)),
                            'transient': a['transient'] or b['transient'], 'a_rect': a, 'b_rect': b})
    for a in R:
        for z in roblox:
            if z['group'] == 'zone':
                if a['interactive'] and a['group'] not in ('TouchGrid',) and inter(a, z):
                    out.append({'kind': 'in_thumbstick_zone', 'a': a['name'], 'b': z['name'], 'area': round(area(a, z)),
                                'transient': a['transient'], 'a_rect': a, 'b_rect': z})
            elif a['group'] != 'TouchGrid' and inter(a, z):
                out.append({'kind': 'overlap_roblox', 'a': a['name'], 'b': z['name'], 'area': round(area(a, z)),
                            'transient': a['transient'], 'a_rect': a, 'b_rect': z})
        if a['x'] < -0.5 or a['y'] < -0.5 or a['x'] + a['w'] > W + 0.5 or a['y'] + a['h'] > H + 0.5:
            out.append({'kind': 'off_screen', 'a': a['name'], 'b': f'gui {W}x{H}', 'area': 0, 'transient': a['transient'], 'a_rect': a})
    return {'viewport': f'{VX}x{VY}', 'input': 'touch' if touch else 'mouse', 'gui': [W, H], 'scale': round(s, 3),
            'compact': compact, 'rects': R + roblox, 'findings': out}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--json', help='write the full report here (default <build>/qa/ui_layout.json when build/ exists)')
    a = ap.parse_args()
    c = load()
    runs = [simulate(c, vp, t) for vp in VIEWPORTS for t in (True, False)]
    for r in runs:
        print(f"\n== {r['viewport']} {r['input']}: gui {r['gui'][0]}x{r['gui'][1]}, scale {r['scale']}, "
              f"{'compact' if r['compact'] else 'desktop'}")
        if not r['findings']:
            print('   no overlaps')
        for f in sorted(r['findings'], key=lambda f: (f['transient'], -f['area'])):
            print(f"   {f['kind']:18s} {'(transient) ' if f['transient'] else ''}{f['a']}  x  {f['b']}  ({f['area']} px²)")
    out = a.json
    if not out:
        p = REPO
        for _ in range(6):
            if os.path.isdir(os.path.join(p, 'build')):
                out = os.path.join(p, 'build', 'qa', 'ui_layout.json')
                break
            p = os.path.dirname(p)
    if out:
        os.makedirs(os.path.dirname(out), exist_ok=True)
        json.dump({'constants': {k: v for k, v in c.items()}, 'runs': runs}, open(out, 'w', encoding='utf-8'), indent=1, default=str)
        print('\nwrote', out)


if __name__ == '__main__':
    main()
