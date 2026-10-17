# Animations (clips for new weapon types and actions)

## Why
A weapon type is more than a mesh: it needs its own clips (stand, walk, run, attack 1–3, pickup, stun) with the grip
and the swing of that weapon. A template that has no clips for a type (spear, staff, katar…) cannot show it well; the
clips come from a clip pack retargeted onto our rig, or are made by us.

## Retarget a humanoid pack (proven on the Explosive RPG pack, Biped-style B_* bones)
- Intake first: the pack is third-party (licence row in the intake table, internal folder, never shipped as-is until the
  owner decides). Copy only the data files (GLB/FBX); never run scripts that come with a pack.
- Use the **in-place** versions (no root motion); the game moves the actor.
- Per mapped bone: world rotation change from the source rest pose, applied to our rest pose, after (1) turning the
  source round if it faces the other way (check where its left arm is), (2) aligning each bone's rest direction
  (their T-pose vs our A-pose; directions from the next joint's head, not Blender bone tails, which the glTF importer
  invents). Pelvis position × hip-height ratio. Unmapped bones (hair, cape, skirt, weapon, sheaths) follow their parent.
- Export the rig + one NLA track per clip (`export_animation_mode='NLA_TRACKS'`, all bones, no skin) so each clip is one
  glTF animation; clip names `<type>_atk1..3`, `_combatstand`, `_combatwalk`, `_combatrun`, `_pickup`, `_stun`,
  plus extras (`_cast_aoe`, `_special`…). A hit event at ~45 % of attack clips until someone times them.
- Check: front + side shots next to a template clip (same facing, feet on the ground, hands where the weapon is),
  both genders. Skirts/capes don't follow the legs (they follow their parent) — acceptable in Labs, fix before shipping.
- Until the type has its own meshes, show it with a stand-in weapon of the same grip (greatsword for spear, rod for staff).
- A style can mix pack files (`STYLES[...] = ('Armed|1Hand', '', {...full clip names})`; `bl_retarget.py` imports every
  file, keeps only the first armature, the others' actions apply because the skeleton is the same) (A087).
- Explosive pack map used here: dual wield = `Armed` (AttackDual1–3, RunAttackDual, BlockDual) + `1Hand` Dagger L/R;
  fists = `Unarmed` (AttackL/R1–3, kicks; it has no plain walk, take `ArmedWalk`); pistol = `1Hand` PistolAttackR1–3 /
  Dual1 / Reload + `Armed` IdlePistolR; puppet = no clips, use `Unarmed` CastR* + `1Hand` ItemAttackR1 (A087).
- Off hand: our rig's `weapon_l` rest is already the mirror of `weapon_r`, so the right-hand mesh goes there unrotated.
  Fist axes for stand-ins and new weapon meshes: +Y = grip / blade line, +X = along the fingers (a pistol barrel, the
  knuckle spikes). Front views foreshorten weapons that point forward: check the side view too (A087).
- A type can borrow another type's clips (Labs `WEAPONS[type].clips = 'spear'` for halberd / lance). Rifle =
  `2Hand Shooting` (FireRifle*, Aiming, ReloadRifle); book = `Armed` CastL* (book in the right hand, left hand casts) (A092).
- Every pack type also needs its own stand / walk / run: the template `stand` holds a sword, so a polearm hangs head-down.
  Labs plays `<prefix>_combatstand|walk|run` for the base stand / walk / run of any `rpg_*` type (A092).
- Shield (A096): rig node `shield` on forearm_l. Mesh frame: origin = grip at the back centre, +Y = face (out from the
  forearm), -X = top (toward the elbow), Z = width. Clips: pack `Armed-Shield` (ShieldIdle/Walk/RunForward as stand/walk/run
  while carried, ShieldAttack1–3 bash, Block, WalkBlock, RunForwardCharge).
