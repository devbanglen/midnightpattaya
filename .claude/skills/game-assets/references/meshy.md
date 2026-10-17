# Meshy image-to-3D (rigid props) and the GPU fallback

## When
Hats, circlets, bands, weapons, shields, small props: rigid pieces whose shape comes from one concept image.
Never for clothes (they must be the template mesh) and not for hair (looked wrong every time in ayothaya).

## Call
`api3d.py meshy <name> <concept.png> --faces <N>` (key from `.env`, never printed; every job logged with its credits).
- `--faces` = slot budget − ~5 %: cap 480, weapon 760, head_mid 380, head_low 190, shield 570.
- One job ≈ 30 credits, ~1–3 min. Run a batch as parallel background jobs, one log each.
- `402 Insufficient funds` = out of credit: tell the owner, rerun the failed names after the top-up.
- Output GLB is textured (one image). Headgear goes through the OBJ converter (project.md) before the fit;
  weapons go straight into weapon_fit (it converts itself).

## What Meshy gets wrong (check every result)
- Drops glowing / transparent parts (an orb drawn as light): add our own orb (weapons.md `--orb`).
- Thin flat parts (blade edges, feathers) can come back with holes; low-poly shells have big flat faces that cut into
  the head (the headgear fit pushes twice for that).
- Render the fitted results with their texture (a Blender workbench shot of all of them side by side) and look.
