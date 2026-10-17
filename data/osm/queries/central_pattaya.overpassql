// Central Pattaya vertical-slice source data (OpenStreetMap, ODbL: "© OpenStreetMap contributors").
// bbox = south, west, north, east : Bali Hai / Walking Street (south) .. North Pattaya Rd (north),
// sea west of Beach Road .. Sukhumvit (east). Generous margin: the slice is chosen after inspecting this.
[out:json][timeout:180][bbox:12.912,100.855,12.960,100.910];
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
