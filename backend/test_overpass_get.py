import urllib.request
import urllib.parse
import json

q = '[out:json][timeout:15];way["building"](13.045,80.245,13.055,80.255);out center;'
servers = [
    'https://overpass.kumi.systems/api/interpreter',
    'https://overpass.private.coffee/api/interpreter',
    'https://overpass-api.de/api/interpreter',
]
for s in servers:
    url = s + '?' + urllib.parse.urlencode({'data': q})
    req = urllib.request.Request(url, headers={'User-Agent': 'ResQ-Disaster-Response-Student-Project/1.0'})
    try:
        print("Testing", s, flush=True)
        with urllib.request.urlopen(req, timeout=12) as resp:
            d = json.loads(resp.read().decode())
            print('GET Overpass success on', s, '! Count:', len(d.get('elements', [])))
            break
    except Exception as e:
        print('Failed on', s, ':', e)
