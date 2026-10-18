// Koh Larn and the small islands off Pattaya (Koh Sak, Koh Krok): coastline only, for the distant horizon
// silhouette (tools/mapgen/coast.py). OpenStreetMap, ODbL: "(c) OpenStreetMap contributors".
// bbox = south, west, north, east; the east edge (100.83) stays west of the mainland coast (~100.86).
[out:json][timeout:120][bbox:12.880,100.700,12.970,100.830];
(
  way["natural"="coastline"];
  way["place"~"island|islet"];
  relation["place"~"island|islet"];
);
out body geom;
