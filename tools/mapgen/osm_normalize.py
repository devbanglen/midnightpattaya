"""Stage 1 - raw Overpass JSON -> normalised source layer (still geographic truth: lat/lon, original OSM ids).

  .venv\\Scripts\\python tools\\mapgen\\osm_normalize.py tools\\mapgen\\config\\central_pattaya.json

Writes data/osm/normalized/<name>.json with roads, coastline, buildings, landuse/water/beach areas and named POIs.
Nothing is moved or simplified here; gameplay changes happen later in road_graph.py on a separate layer.
"""
import json, os, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))


def main(cfg_path):
    cfg = json.load(open(cfg_path, encoding='utf-8'))
    raw = json.load(open(os.path.join(ROOT, cfg['source']), encoding='utf-8'))
    out = {'name': cfg['name'], 'attribution': cfg['attribution'], 'source': cfg['source'],
           'osm_base': raw.get('osm3s', {}).get('timestamp_osm_base'),
           'roads': [], 'coastline': [], 'buildings': [], 'areas': [], 'pois': []}
    for e in raw['elements']:
        t = e.get('tags', {})
        if e['type'] == 'way':
            if 'geometry' not in e:
                continue
            coords = [[p['lat'], p['lon']] for p in e['geometry']]
            base = {'id': e['id'], 'nodes': e.get('nodes', []), 'coords': coords}
            if 'highway' in t:
                out['roads'].append({**base, 'class': t['highway'], 'name': t.get('name'), 'name_en': t.get('name:en'),
                                     'oneway': t.get('oneway') in ('yes', '1', 'true'), 'lanes': t.get('lanes'),
                                     'junction': t.get('junction'), 'bridge': t.get('bridge') == 'yes',
                                     'tunnel': t.get('tunnel') == 'yes', 'layer': t.get('layer')})
            elif t.get('natural') == 'coastline':
                out['coastline'].append(base)
            elif 'building' in t:
                out['buildings'].append({**base, 'kind': t['building'], 'levels': t.get('building:levels'),
                                         'height': t.get('height'), 'name': t.get('name'), 'name_en': t.get('name:en'),
                                         'tourism': t.get('tourism'), 'amenity': t.get('amenity'), 'shop': t.get('shop')})
            elif any(k in t for k in ('landuse', 'natural', 'leisure', 'man_made')):
                kind = t.get('landuse') or t.get('natural') or t.get('leisure') or t.get('man_made')
                out['areas'].append({**base, 'kind': kind, 'name': t.get('name')})
            if t.get('name') and ('tourism' in t or 'amenity' in t):
                lat = sum(c[0] for c in coords) / len(coords); lon = sum(c[1] for c in coords) / len(coords)
                out['pois'].append({'id': e['id'], 'type': 'way', 'lat': lat, 'lon': lon, 'name': t.get('name'),
                                    'name_en': t.get('name:en'), 'tourism': t.get('tourism'), 'amenity': t.get('amenity')})
        elif e['type'] == 'node' and t.get('name'):
            out['pois'].append({'id': e['id'], 'type': 'node', 'lat': e['lat'], 'lon': e['lon'], 'name': t.get('name'),
                                'name_en': t.get('name:en'), 'tourism': t.get('tourism'), 'amenity': t.get('amenity'),
                                'place': t.get('place')})
    dst = os.path.join(ROOT, 'data', 'osm', 'normalized', cfg['name'] + '.json')
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    json.dump(out, open(dst, 'w', encoding='utf-8'), ensure_ascii=False)
    print(f"{cfg['name']}: {len(out['roads'])} roads, {len(out['coastline'])} coastline ways, "
          f"{len(out['buildings'])} buildings, {len(out['areas'])} areas, {len(out['pois'])} pois -> {os.path.relpath(dst, ROOT)}")


if __name__ == '__main__':
    main(sys.argv[1])
