import json
import urllib.request
import urllib.error
import sys

BASE_URL = "http://127.0.0.1:8000"

def request(method, path, data=None):
    url = f"{BASE_URL}{path}"
    headers = {"Content-Type": "application/json"}
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            code = resp.getcode()
            content = resp.read().decode("utf-8")
            return code, json.loads(content) if content else {}
    except urllib.error.HTTPError as e:
        content = e.read().decode("utf-8")
        try:
            parsed = json.loads(content)
        except Exception:
            parsed = {"raw": content}
        return e.code, parsed

def run_tests():
    print("=== STARTING ZERO-MOCK DATA & VERIFIED SOURCE TEST SUITE ===")
    passed = 0
    failed = 0

    def assert_eq(actual, expected, message):
        nonlocal passed, failed
        if actual == expected:
            print(f"  [PASS] {message}")
            passed += 1
        else:
            print(f"  [FAIL] {message}: expected {expected}, got {actual}")
            failed += 1

    # 1. Health & Home
    code, res = request("GET", "/health")
    assert_eq(code, 200, "GET /health returns 200")
    assert_eq(res.get("status"), "ok", "Database status is ok")

    code, res = request("GET", "/sources")
    assert_eq(code, 200, "GET /sources returns 200")
    assert_eq("live_external_feeds" in res, True, "Sources breakdown has live_external_feeds")
    assert_eq("stored_database_records" in res, True, "Sources breakdown has stored_database_records")

    # 2. Verify Live Feeds are clearly identified as LIVE
    code, res = request("GET", "/live-earthquakes")
    assert_eq(code, 200, "GET /live-earthquakes returns 200")
    assert_eq(res.get("is_live"), True, "USGS feed is marked is_live=True")
    assert_eq(res.get("source_type"), "live_external_feed", "USGS feed source_type is live_external_feed")

    code, res = request("GET", "/live-disasters")
    assert_eq(code, 200, "GET /live-disasters returns 200")
    assert_eq(res.get("is_live"), True, "GDACS feed is marked is_live=True")
    assert_eq(res.get("source_type"), "live_external_feed", "GDACS feed source_type is live_external_feed")

    # 3. Verify Stored Tables are EMPTY by default (No dummy / mock seeds)
    code, res = request("GET", "/depots")
    assert_eq(code, 200, "GET /depots returns 200")
    assert_eq(res.get("count"), 0, "No dummy depots seeded; table is empty (count=0)")
    assert_eq(res.get("is_live"), False, "Depots are marked is_live=False (stored database records)")
    assert_eq(res.get("source_type"), "stored_database_records", "Depots source_type is stored_database_records")

    code, res = request("GET", "/inventory")
    assert_eq(code, 200, "GET /inventory returns 200")
    assert_eq(res.get("count"), 0, "No dummy inventory seeded; table is empty (count=0)")
    assert_eq(res.get("is_live"), False, "Inventory is marked is_live=False (stored database records)")

    code, res = request("GET", "/zones")
    assert_eq(code, 200, "GET /zones returns 200")
    assert_eq(res.get("count"), 0, "No dummy disaster zones seeded; table is empty (count=0)")
    assert_eq(res.get("is_live"), False, "Zones are marked is_live=False (stored database records)")

    code, res = request("GET", "/field-operations")
    assert_eq(code, 200, "GET /field-operations returns 200")
    assert_eq(res.get("count"), 0, "No dummy operations seeded; table is empty (count=0)")
    assert_eq(res.get("is_live"), False, "Operations are marked is_live=False (stored database records)")

    # 4. Create and verify real user data through API
    code, res = request("POST", "/depots", {
        "name": "Guindy Response Center",
        "latitude": 13.0067,
        "longitude": 80.2025
    })
    assert_eq(code, 201, "POST /depots creates genuine depot record")
    depot_id = res["depot"]["id"]

    code, res = request("POST", "/inventory", {
        "depot_id": depot_id,
        "resource_type": "water_liters",
        "quantity": 5000
    })
    assert_eq(code, 201, "POST /inventory records verified stock")
    inv_id = res["item"]["id"]

    code, res = request("POST", "/zones", {
        "name": "Adyar Basin Lowland Zone",
        "disaster_type": "Flood",
        "severity": "High",
        "geom": {
            "type": "Polygon",
            "coordinates": [[
                [80.2200, 13.0000],
                [80.2400, 13.0000],
                [80.2400, 13.0200],
                [80.2200, 13.0200],
                [80.2200, 13.0000]
            ]]
        }
    })
    assert_eq(code, 201, "POST /zones creates verified disaster zone")
    zone_id = res["zone"]["id"]

    code, res = request("POST", "/field-operations", {
        "title": "Adyar Water Evacuation Team Alpha",
        "zone_id": zone_id,
        "depot_id": depot_id,
        "status": "Active"
    })
    assert_eq(code, 201, "POST /field-operations creates verified mission record")
    op_id = res["operation"]["id"]

    # Verify counts now reflect real data
    code, res = request("GET", "/depots")
    assert_eq(res.get("count"), 1, "GET /depots reflects 1 real record")

    code, res = request("GET", "/inventory")
    assert_eq(res.get("count"), 1, "GET /inventory reflects 1 real record")

    code, res = request("GET", "/zones")
    assert_eq(res.get("count"), 1, "GET /zones reflects 1 real record")

    code, res = request("GET", "/field-operations")
    assert_eq(res.get("count"), 1, "GET /field-operations reflects 1 real record")

    # Clean up test records to keep tables clean
    request("DELETE", f"/field-operations/{op_id}")
    request("DELETE", f"/zones/{zone_id}")
    request("DELETE", f"/inventory/{inv_id}")
    request("DELETE", f"/depots/{depot_id}")

    # Verify clean tables once again
    code, res = request("GET", "/depots")
    assert_eq(res.get("count"), 0, "After cleanup, depots count is 0")

    print(f"\n=== TEST SUMMARY: {passed} PASSED, {failed} FAILED ===")
    if failed > 0:
        sys.exit(1)

if __name__ == "__main__":
    run_tests()
