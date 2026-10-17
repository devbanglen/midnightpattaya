<!-- copied from ~/.claude/skills/sprite-pipeline/references/common (ced2f55) on 2026-10-17; ayothaya owns this copy now -->
# Third-party material and IP (all routes)

## Rules
- **Third-party reference material is numbers and behaviour only:** never copy its code, never ship its assets, never trace its art. Keep it in a gitignored `reference/` dir; the kit never contains it. (aroa A004/A005: rAthena GPL code studied, rules rewritten from scratch; RO client assets internal only)
- **AI-reference use is decided per asset class by the owner and logged** in the project's `DECISIONS.md`. Default: only your own generated images or your own renders go into an image generator. (aroa A029: the reference game's item images allowed as GPT references for items, never for monsters; monsters are our own designs)
- **Outputs must be our own designs:** change at least 2 of 3 (silhouette, main palette, signature motif) against any reference, keep reference-vs-ours comparison sheets internal, rename everything. Wording and checks: [concept-art.md](concept-art.md#reference-images). (aroa A029)
- **No real people** in prompts: describe the look instead (wording in [concept-art.md](concept-art.md#reference-images); aroa A040).
- **Mascot look-alikes:** steer designs away from well-known silhouettes up front; an image model may refuse, and a pass can still read as a famous character. (aroa pets)
- **Downloaded asset packs** (characters, items, monsters bought or found online): record source URL and licence per pack before use, and decide per asset class whether it may be an AI reference. Process: (sprite-pipeline route doc, not copied). (sprite-kit v1, aroa A114 follow-up)
- **Study numbers are fine, data files are not:** timing tables, formulas and measured proportions from a reference game may inform your own numbers (cite them as study notes); copying its data files, sprites or code into the shipped game is not. (aroa A005; kit PORTING lists every place aroa's code carries RO-derived numbers)

## Generator licences
Hunyuan3D-2.1 open weights are licensed with **territory exclusions (EU, UK, South Korea)**. Treat output as test material until the user has decided how to ship (another generator, or a cleared licence), and say so whenever results head toward a release. Paid Meshy/Tripo output is owned by the payer; in the orin bake-off Meshy gave sharper faces/textures, Tripo better animal shapes. (aroa, orin bake-off)
