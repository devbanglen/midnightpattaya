// Pattaya wide world, part 'north': Naklua / Wong Amat / Sanctuary of Truth (north of the central download). OpenStreetMap, ODbL: "© OpenStreetMap contributors".
// Same filters as central_pattaya.overpassql; merged with data/osm/raw/central_pattaya_2026-10-18.json by element id.
[out:json][timeout:240][bbox:12.960,100.855,12.985,100.922];
(
  way["highway"];
  way["natural"="coastline"];
  way["natural"~"beach|water|wood|scrub"];
  way["building"];
  way["landuse"];
  way["leisure"~"park|pitch|stadium"];
  way["man_made"="pier"];
  node["tourism"]["name"];
  node["amenity"]["name"];
  node["place"];
  way["tourism"]["name"];
  way["amenity"]["name"];
);
out body geom;
