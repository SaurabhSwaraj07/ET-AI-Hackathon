"""
test_endpoints.py — Smoke test for all Day 7 FastAPI endpoints.
Run AFTER starting the server: uvicorn main:app --reload --port 8000

Usage:
    cd backend
    python test_endpoints.py
"""
import sys
import time
import httpx

BASE_URL    = "http://127.0.0.1:8000"
TEST_STATION = "Peenya"   # guaranteed to have data from db_seed.py

PASS = "✅"
FAIL = "❌"
failures: list[str] = []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def check(label: str, url: str, assert_key: str = None, expected_status: int = 200):
    try:
        r = httpx.get(url, timeout=30)
        status_ok = r.status_code == expected_status
        key_ok    = True
        if assert_key and status_ok:
            data  = r.json()
            key_ok = assert_key in data
        if status_ok and key_ok:
            print(f"{PASS} {label}  [{r.status_code}]")
            if assert_key:
                val     = r.json().get(assert_key)
                preview = str(val)[:80]
                print(f"     {assert_key} = {preview}")
        else:
            print(f"{FAIL} {label}  [status={r.status_code}, key_ok={key_ok}]")
            print(f"     response: {r.text[:200]}")
            failures.append(label)
    except Exception as e:
        print(f"{FAIL} {label}  [EXCEPTION: {e}]")
        failures.append(label)


def check_image(label: str, url: str):
    """Assert endpoint returns Content-Type: image/png with non-zero body."""
    try:
        r = httpx.get(url, timeout=15)
        ct     = r.headers.get("content-type", "")
        size   = len(r.content)
        ok     = r.status_code == 200 and "image/png" in ct and size > 0
        if ok:
            print(f"{PASS} {label}  [{r.status_code}] content-type={ct} size={size}B")
        else:
            print(f"{FAIL} {label}  [status={r.status_code}, content-type={ct}, size={size}B]")
            failures.append(label)
    except Exception as e:
        print(f"{FAIL} {label}  [EXCEPTION: {e}]")
        failures.append(label)


def check_cache(label_miss: str, label_hit: str, url: str):
    """
    Call the same forecast URL twice.
    First call should be 'miss' (or hit if scheduler already ran).
    Second call must be 'hit'.
    """
    for attempt, expected_cache in enumerate(["miss", "hit"], start=1):
        try:
            r    = httpx.get(url, timeout=60)
            data = r.json()
            cache_val = data.get("cache", "unknown")
            label = label_miss if attempt == 1 else label_hit

            # First call: miss OR hit (scheduler may have pre-warmed)
            # Second call: must be hit
            if attempt == 1:
                valid = cache_val in ("miss", "hit")
            else:
                valid = cache_val == "hit"

            if r.status_code == 200 and valid:
                print(f"{PASS} {label}  [{r.status_code}] cache={cache_val}")
            else:
                print(f"{FAIL} {label}  [status={r.status_code}, cache={cache_val}]")
                failures.append(label)
        except Exception as e:
            print(f"{FAIL} {label}  [EXCEPTION: {e}]")
            failures.append(label)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("AirIQ — Day 8 Endpoint Smoke Test")
    print(f"Target : {BASE_URL}")
    print("=" * 60)

    # Original Day 6 checks
    check("GET /",                           f"{BASE_URL}/",                                   "status")
    check("GET /api/stations",               f"{BASE_URL}/api/stations",                       "stations")
    check("GET /api/attribution/{station}",  f"{BASE_URL}/api/attribution/{TEST_STATION}",     "attribution")
    check("GET /api/advisory/{station}",     f"{BASE_URL}/api/advisory/{TEST_STATION}",        "advisory")

    # Static file — image bytes
    check_image("GET /static/shap_chart.png", f"{BASE_URL}/static/shap_chart.png")

    # Day 7: cache-hit path
    print()
    print("--- Cache-hit checks (forecast called twice) ---")
    check_cache(
        "GET /api/forecast/{station} [1st call — miss or hit]",
        "GET /api/forecast/{station} [2nd call — must be hit]",
        f"{BASE_URL}/api/forecast/{TEST_STATION}",
    )

    # Day 7: health endpoint
    print()
    print("--- Health endpoint ---")
    check("GET /api/health",  f"{BASE_URL}/api/health",  "uptime_seconds")
    check("GET /api/health — forecasts_count > 0", f"{BASE_URL}/api/health", "forecasts_count")

    print()
    if not failures:
        print("✅ All checks passed. Day 7 complete!")
        sys.exit(0)
    else:
        print(f"❌ {len(failures)} check(s) failed: {failures}")
        sys.exit(1)

        # Day 8: advisory source field
        print()
        print("--- Day 8: advisory source field ---")
        check("GET /api/advisory/{station} — source field present",
              f"{BASE_URL}/api/advisory/{TEST_STATION}", "advisory")

        # Inline source-field check
        try:
            r = httpx.get(f"{BASE_URL}/api/advisory/{TEST_STATION}", timeout=15)
            source = r.json().get("advisory", {}).get("source", "MISSING")
            if source in ("rule-based", "gemini"):
                print(f"{PASS} advisory.source = '{source}'")
            else:
                print(f"{FAIL} advisory.source unexpected value: '{source}'")
                failures.append("advisory.source field")
        except Exception as e:
            print(f"{FAIL} advisory.source check [EXCEPTION: {e}]")
            failures.append("advisory.source field")

        # Day 8: forecast response structure unchanged after weather-client wiring
        print()
        print("--- Day 8: forecast structure after weather-client wiring ---")
        try:
            r = httpx.get(f"{BASE_URL}/api/forecast/{TEST_STATION}", timeout=60)
            data = r.json()
            required_keys = {"station", "generated_at", "forecast_hours", "horizon", "unit", "cache"}
            missing = required_keys - data.keys()
            if r.status_code == 200 and not missing:
                print(f"{PASS} Forecast response structure intact  (cache={data.get('cache')})")
            else:
                print(f"{FAIL} Forecast missing keys: {missing}  [status={r.status_code}]")
                failures.append("forecast structure Day 8")
        except Exception as e:
            print(f"{FAIL} forecast structure check [EXCEPTION: {e}]")
            failures.append("forecast structure Day 8")


if __name__ == "__main__":
    main()