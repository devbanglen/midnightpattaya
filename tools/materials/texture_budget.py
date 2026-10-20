#!/usr/bin/env python3
"""Offline PBR texture-budget audit for MIDNIGHT PATTAYA.

Reads build/materials/manifest.json and reports the GPU-resident memory of the
PBR MaterialLibraryMaps, separated from the total GraphicsTexture figure that a
client reports (which also includes Roblox UI/terrain/CoreGui and facade decals).

Method matches docs/MATERIAL_LIBRARY.md "Budget (mobile)":
  block-compressed estimate, mips included,
  1.0 byte/px for color and normal maps, 0.5 byte/px for the rest (single-channel),
  uncompressed RGBA8 + mips as the hard upper bound.

This is OFFLINE analysis only. It never builds, publishes, or uploads anything.
It does not open or write any .rbxl. It only reads the manifest and writes a JSON
report next to it. Exit code is non-zero if the resident estimate exceeds the
budget, so it can also run as an automated QA gate.

Usage:
  python tools/materials/texture_budget.py                 # human table
  python tools/materials/texture_budget.py --json          # machine JSON to stdout
  python tools/materials/texture_budget.py --budget 18     # set budget (MiB)
"""
from __future__ import annotations
import argparse, json, os, sys

MIB = 1024 * 1024
MIP = 4.0 / 3.0                      # full mip chain adds ~1/3

# byte/px, matching docs/MATERIAL_LIBRARY.md "Budget (mobile)":
#   normal maps            -> 1.0  (BC5-like, 8 bpp)
#   color with alpha (RGBA) -> 1.0  (BC3/DXT5-like, 8 bpp)
#   color RGB               -> 0.5  (BC1/DXT1-like, 4 bpp)
#   single channel (L: roughness/metalness) -> 0.5 (BC4-like, 4 bpp)
def bpp(maptype: str, mode: str) -> float:
    if maptype == "normal":
        return 1.0
    if maptype == "color":
        return 1.0 if (mode or "").upper() == "RGBA" else 0.5
    return 0.5


def compressed_bytes(w: int, h: int, maptype: str, mode: str) -> float:
    return w * h * bpp(maptype, mode) * MIP


def rgba8_bytes(w: int, h: int) -> float:
    return w * h * 4 * MIP


def resize_bytes(maptype: str, mode: str, size: int) -> float:
    # memory if this map were re-exported at size x size
    return compressed_bytes(size, size, maptype, mode)


def main() -> int:
    ap = argparse.ArgumentParser()
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.abspath(os.path.join(here, "..", ".."))
    ap.add_argument("--manifest", default=os.path.join(root, "build", "materials", "manifest.json"))
    ap.add_argument("--budget", type=float, default=18.0, help="mobile texture budget in MiB")
    ap.add_argument("--json", action="store_true", help="emit JSON report to stdout")
    ap.add_argument("--out", default=os.path.join(root, "build", "materials", "texture_budget.json"))
    args = ap.parse_args()

    with open(args.manifest, encoding="utf-8") as f:
        man = json.load(f)
    sets = man.get("sets", {})

    report = {"budget_mib": args.budget, "method": "block-compressed + mips; color/normal 1.0 B/px, else 0.5 B/px", "sets": {}}
    tot_c = tot_rgba = tot_disk = 0.0
    n_maps = 0
    for name, s in sets.items():
        files = s.get("files", {})
        c = rgba = disk = 0.0
        maps = {}
        for mt, info in files.items():
            if not info:
                continue
            w, h, b = int(info["width"]), int(info["height"]), int(info.get("bytes", 0))
            mode = info.get("mode", "")
            cb = compressed_bytes(w, h, mt, mode)
            c += cb; rgba += rgba8_bytes(w, h); disk += b
            maps[mt] = {"wh": f"{w}x{h}", "mode": mode, "disk_bytes": b, "compressed_mib": round(cb / MIB, 3)}
            n_maps += 1
        report["sets"][name] = {
            "maps": maps,
            "compressed_mib": round(c / MIB, 3),
            "rgba8_mib": round(rgba / MIB, 3),
            "disk_mib": round(disk / MIB, 3),
        }
        tot_c += c; tot_rgba += rgba; tot_disk += disk

    # dry/wet are never both resident: subtract the cheaper of the two
    dry = report["sets"].get("DryAsphalt", {}).get("compressed_mib", 0.0)
    wet = report["sets"].get("WetAsphalt", {}).get("compressed_mib", 0.0)
    resident = tot_c / MIB - min(dry, wet)

    # cut-list deltas: re-export a set at 512 and measure the saving
    def saving_to_512(name: str) -> float:
        s = sets.get(name, {}).get("files", {})
        cur = sum(compressed_bytes(int(i["width"]), int(i["height"]), mt, i.get("mode", "")) for mt, i in s.items() if i)
        new = sum(resize_bytes(mt, i.get("mode", ""), 512) for mt, i in s.items() if i)
        return round((cur - new) / MIB, 3)

    cuts = {n: saving_to_512(n) for n in ("DarkGlassGrid", "Concrete") if n in sets}

    report["totals"] = {
        "n_sets": len(sets), "n_maps": n_maps,
        "upload_disk_mib": round(tot_disk / MIB, 2),
        "all_resident_compressed_mib": round(tot_c / MIB, 2),
        "all_resident_rgba8_upper_mib": round(tot_rgba / MIB, 1),
        "scene_resident_compressed_mib": round(resident, 2),
        "cut_to_512_savings_mib": cuts,
    }
    report["budget_check"] = {
        "budget_mib": args.budget,
        "scene_resident_mib": round(resident, 2),
        "pass": resident <= args.budget,
        "headroom_mib": round(args.budget - resident, 2),
    }

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)

    if args.json:
        print(json.dumps(report, indent=1))
    else:
        t = report["totals"]
        print(f"PBR texture budget audit  ({t['n_sets']} sets, {t['n_maps']} maps)")
        print("-" * 68)
        print(f"{'set':<16}{'compressed':>12}{'rgba8':>12}{'disk(png)':>12}")
        for n, s in report["sets"].items():
            print(f"{n:<16}{s['compressed_mib']:>10.2f}  {s['rgba8_mib']:>10.2f}  {s['disk_mib']:>10.2f}")
        print("-" * 68)
        print(f"{'ALL resident':<16}{t['all_resident_compressed_mib']:>10.2f}  "
              f"{t['all_resident_rgba8_upper_mib']:>10.1f}  {t['upload_disk_mib']:>10.2f}")
        print(f"scene resident (dry XOR wet): {t['scene_resident_compressed_mib']} MiB")
        print(f"cut-to-512 savings: {t['cut_to_512_savings_mib']}")
        bc = report["budget_check"]
        verdict = "PASS" if bc["pass"] else "OVER"
        print(f"budget {bc['budget_mib']} MiB  ->  {verdict}  (headroom {bc['headroom_mib']} MiB)")
        print("-" * 68)
        print("NOTE: this is the PBR-maps share only. A client's GraphicsTexture")
        print("(230-242 MB measured, VISUAL_PERFORMANCE.md §7) also includes Roblox")
        print("UI/terrain/CoreGui and facade decals. True on-device PBR share must")
        print("be confirmed by the fresh-client real-phone A/B (PENDING_OWNER_TEST).")
    return 0 if report["budget_check"]["pass"] else 2


if __name__ == "__main__":
    sys.exit(main())
