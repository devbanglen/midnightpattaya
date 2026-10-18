// Pattaya street furniture source nodes (OpenStreetMap, ODbL: "© OpenStreetMap contributors").
// Same bbox as the wide world (tools/mapgen/config/pattaya_wide.json slice_bbox_s_w_n_e), which contains the central slice.
// Used by tools/mapgen/furniture.py: traffic signals, crossings, bus stops / platforms / shelters, taxi and
// motorcycle-taxi stands, power poles (for the "no poles yet" check only).
[out:json][timeout:180][bbox:12.858,100.855,12.985,100.922];
(
  node["highway"~"^(traffic_signals|crossing|bus_stop)$"];
  node["crossing"];
  node["public_transport"~"^(platform|stop_position)$"];
  node["amenity"~"^(taxi|motorcycle_taxi|shelter)$"];
  way["amenity"~"^(taxi|motorcycle_taxi)$"];
  node["power"~"^(pole|tower)$"];
);
out body center;
