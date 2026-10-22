import urllib.request
import json

lat, lon = 31.987, -103.29
d = 0.05
south, west, north, east = lat - d, lon - d, lat + d, lon + d
query = f"""
[out:json][timeout:25];
way["building"]({south},{west},{north},{east});
out center;
"""
print("Querying Overpass with bbox:", south, west, north, east)
servers = [
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
    "https://z.overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
]
import urllib.parse
post_data = urllib.parse.urlencode({'data': query}).encode('utf-8')
for server in servers:
    try:
        print("Trying", server, flush=True)
        req = urllib.request.Request(
            server,
            data=post_data,
            headers={
                'Content-Type': 'application/x-www-form-urlencoded; charset=utf-8',
                'User-Agent': 'ResQ-Disaster-Response-Project/1.0'
            },
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            print("Success! Found elements:", len(data.get('elements', [])), flush=True)
            break
    except Exception as e:
        print(f"Failed {server}: {e}", flush=True)

