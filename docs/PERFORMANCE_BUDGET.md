# Performance budget

## Measurements (2026-10-18, Roblox Studio Play on the owner's Windows PC, desktop only)
Method: fresh Play session; server test-autopilot moves the seated car along the race path at 160 studs/s (top
speed without nitro) for a full lap (~41 s) while the client records RenderStepped frame times. Studio caps at 60.

| Scenario | Avg FPS | 1% low | Worst frame |
|---|---|---|---|
| Idle at spawn | 60.0 | 54.4 | — |
| Camera over the sea, facing away from the city | 60.0 | 55.0 | — |
| Full lap at 160 studs/s, day | 60.0 | 44.0 | 31 ms |
| Full lap at 160 studs/s, night (lit windows, 291 spotlights) | 60.0 | 45.2 | 32 ms |

World size: 16,027 Parts, 11,116 facade Textures, 291 SpotLights (night only), terrain ground/sea. With instance
streaming (template setting) a client had 3,700–6,500 Pattaya parts loaded at a time.

Caveats:
- Earlier runs in a session that had already run several test autopilots showed 15–21 FPS; a fresh session gave the
  numbers above. Long sessions should be re-measured (possible leak in test scripts or Studio itself).
- Studio Play runs server and client on one machine; a real client may differ.
- Mobile 30 FPS target: NOT measured (needs the device emulator or a phone).
- Studio screenshots are unreliable when the Studio window is not in front; FPS may also drop when unfocused.

## Budget rules used so far
- Windows as Textures, not Parts. One box per building. Roof slab only above 30 studs.
- Real lights only on every second street lamp, no shadows, enabled only at night.
- Markings/props don't collide and are excluded from queries.
- Chunks are Atomic streaming models (512 studs); race gates/grid are Persistent.
