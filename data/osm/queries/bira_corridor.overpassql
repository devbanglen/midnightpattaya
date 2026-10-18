// Road corridor central Pattaya -> Bira Circuit (OpenStreetMap, ODbL: "(c) OpenStreetMap contributors").
// bbox = south, west, north, east : east edge of the central slice (100.885) .. the circuit (101.02),
// Pattaya Tai latitude .. north of the Sukhumvit / Highway 36 interchange. Driveable classes only.
[out:json][timeout:180][bbox:12.900,100.880,12.990,101.022];
(
  way["highway"~"^(motorway|motorway_link|trunk|trunk_link|primary|primary_link|secondary|secondary_link|tertiary|tertiary_link|unclassified)$"];
);
out geom qt;
