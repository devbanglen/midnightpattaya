// Locate raceways east of Pattaya (OpenStreetMap, ODbL: "(c) OpenStreetMap contributors").
[out:json][timeout:60][bbox:12.85,100.93,13.00,101.08];
(
  way["highway"="raceway"];
  way["leisure"~"track|sports_centre"]["name"];
  relation["leisure"~"track|sports_centre"];
);
out tags center;
