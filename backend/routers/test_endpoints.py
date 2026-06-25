"""
test_endpoints.py — Smoke test for all Day 6 FastAPI endpoints.
Run AFTER starting the server: uvicorn main:app --reload --port 8000

Usage:
    cd backend
    python test_endpoints.py
"""
import sys
import httpx

BASE_URL = "http://127.0.0.1:8000"
TEST_STATION = "Peenya"   # guaranteed to have data from db_seed.py

PASS = "✅"
FAIL = "❌"

failures = []


def check(label: str, url: str, assert_key: str = None, expected_status: int = 200):
    try:
        r = httpx.get(url, timeout=30)
        status_ok = r.status_code == expected_status
        key_ok = True
        if assert_key and status_ok:
            data = r.json()
            key_ok = assert_key in data
        if status_ok and key_ok:
            print(f"{PASS} {label}  [{r.status_code}]")
            if assert_key:
                val = r.json().get(assert_key)
                preview = str(val)[:80]
                print(f"     {assert_key} = {preview}")
        else:
            print(f"{FAIL} {label}  [status={r.status_code}, key_ok={key_ok}]")
            print(f"     response: {r.text[:200]}")
            failures.append(label)
    except Exception as e:
        print(f"{FAIL} {label}  [EXCEPTION: {e}]")
        failures.append(label)


def main():
    print("=" * 60)
    print("AirIQ — Day 6 Endpoint Smoke Test")
    print(f"Target : {BASE_URL}")
    print("=" * 60)

    check("GET /",                              f"{BASE_URL}/",                                    "status")
    check("GET /api/stations",                 f"{BASE_URL}/api/stations",                        "stations")
    check("GET /api/forecast/{station}",       f"{BASE_URL}/api/forecast/{TEST_STATION}",         "forecast_hours")
    check("GET /api/attribution/{station}",    f"{BASE_URL}/api/attribution/{TEST_STATION}",      "attribution")
    check("GET /api/advisory/{station}",       f"{BASE_URL}/api/advisory/{TEST_STATION}",         "advisory")
    check("GET /static/shap_chart.png",        f"{BASE_URL}/static/shap_chart.png",               expected_status=200)

    print()
    if not failures:
        print("✅ All checks passed. Day 6 complete!")
        sys.exit(0)
    else:
        print(f"❌ {len(failures)} check(s) failed: {failures}")
        sys.exit(1)


if __name__ == "__main__":
    main()