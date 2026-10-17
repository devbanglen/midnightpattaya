# Procedural buildings

Not started (Phase 5). Source available: 8,106 OSM building footprints in the normalised layer (kind, levels,
height, names, tourism/amenity/shop tags).

Planned approach:
- Transform footprints with the same compression as roads, then push them out of widened road corridors (no
  building may overlap a road or sidewalk) and merge tiny footprints per block.
- Height from `height` / `building:levels`, else district defaults (Beach Road hotels tall, sois low shophouses).
- Modular facades: few reusable textured meshes/decals per category instead of per-window Parts.
- LOD: far chunks get boxes only.
