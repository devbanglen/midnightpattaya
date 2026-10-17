# World chunks

- Chunk size: 512 studs (`chunk_size_studs`). Chunk id = `floor(x/512)_floor(z/512)` in gameplay coordinates;
  an edge belongs to the chunk of its middle point (stable while the source data and config are unchanged).
- Each chunk is a Model `workspace.PattayaWorld.Chunks.Chunk_<id>` with `ModelStreamingMode = Atomic`, ready for
  instance streaming. `Workspace.StreamingEnabled` is NOT switched on yet (it affects the whole place; decide in
  Phase 8 with measurements).
- Data modules: `ServerStorage.PattayaData.chunk_<id>` (generated), `manifest` (chunk list, junctions, sea mask,
  coastline, bounds, attribution).
- First slice: 72 chunks, largest data module 44 KB.
