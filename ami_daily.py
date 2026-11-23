
import json
import os
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

API_URL = "https://api.api.sh/avito/v1/search"
API_KEY = os.environ.get("AVITO_API_KEY")

if not API_KEY:
    print("ERROR: AVITO_API_KEY secret is missing.")
    sys.exit(1)

params = {
    "q": "iphone",
    "location": "moskva",
    "category": "telefony",
    "sort": "newest",
    "page": "1",
}

url = API_URL + "?" + urlencode(params)

request = Request(
    url,
    headers={
        "x-api-key": API_KEY,
        "Accept": "application/json"
    }
)

# Повторные попытки при временных ошибках
payload = None
delays = [30, 60, 120]

for attempt in range(4):
    try:
        print(f"API request: attempt {attempt + 1}/4")

        with urlopen(request, timeout=120) as response:
            payload = json.loads(response.read().decode("utf-8"))

        break

    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")

        temporary = (
            error.code == 429
            or error.code >= 500
            or (
                error.code == 502
                and "status 429" in detail
            )
        )

        if not temporary or attempt == 3:
            print(f"API error HTTP {error.code}: {detail[:1000]}")
            sys.exit(1)

        print(f"Temporary API error: HTTP {error.code}")
        print(f"Waiting {delays[attempt]} seconds before retry")
        time.sleep(delays[attempt])

    except (URLError, TimeoutError) as error:
        if attempt == 3:
            print(f"Network/API error: {error}")
            sys.exit(1)

        print(f"Network error: {error}")
        print(f"Waiting {delays[attempt]} seconds before retry")
        time.sleep(delays[attempt])

if payload is None:
    print("ERROR: API returned no data.")
    sys.exit(1)

if payload.get("success") is False:
    print("API error:", payload.get("error", "unknown"))
    sys.exit(1)

listings = payload.get("listings")

if not isinstance(listings, list):
    print("Unexpected API response:")
    print(json.dumps(payload, ensure_ascii=False)[:2000])
    sys.exit(1)

generated_at = datetime.now(timezone.utc).isoformat()

# Полная резервная копия — только в архиве Actions.
full_result = {
    "generated_at": generated_at,
    "source": "API.SH Avito Search",
    "query": params,
    "credits_used": payload.get("credits_used"),
    "total_found": payload.get("total"),
    "count_returned": len(listings),
    "listings": listings,
}

with open("ami-search-test.json", "w", encoding="utf-8") as file:
    json.dump(full_result, file, ensure_ascii=False, indent=2)

# Очищенная публичная база AMI.
allowed_fields = {
    "id", "title", "price",
    "url", "link", "avito_url",
    "created_at", "published_at", "date",
    "location", "city", "region",
    "category", "params", "attributes"
}

allowed_param_words = (
    "model", "память", "памяти", "gb", "гб",
    "condition", "состояние", "диагональ",
    "цвет", "экран", "комплект"
)

def safe_params(value):
    if isinstance(value, dict):
        result = {}

        for key, item in value.items():
            key_text = str(key).lower()

            if any(word in key_text for word in allowed_param_words):
                if isinstance(item, (str, int, float, bool)) or item is None:
                    result[key] = item

        return result

    if isinstance(value, list):
        result = []

        for item in value:
            if isinstance(item, dict):
                cleaned = safe_params(item)
                if cleaned:
                    result.append(cleaned)

        return result

    return None

def clean_listing(listing):
    cleaned = {}

    for key, value in listing.items():
        if key not in allowed_fields:
            continue

        if key in ("params", "attributes"):
            safe_value = safe_params(value)
            if safe_value:
                cleaned[key] = safe_value

        elif key == "location":
            if isinstance(value, str):
                cleaned[key] = value

            elif isinstance(value, dict):
                location = {}

                for loc_key in ("city", "region"):
                    if isinstance(value.get(loc_key), str):
                        location[loc_key] = value[loc_key]

                if location:
                    cleaned[key] = location

        elif isinstance(value, (str, int, float, bool)) or value is None:
            cleaned[key] = value

    return cleaned

public_listings = [
    clean_listing(item)
    for item in listings
    if isinstance(item, dict)
]

public_result = {
    "generated_at": generated_at,
    "source": "API.SH Avito Search",
    "query": params,
    "total_found": payload.get("total"),
    "count_returned": len(public_listings),
    "listings": public_listings,
}

with open("ami-search-public.json", "w", encoding="utf-8") as file:
    json.dump(public_result, file, ensure_ascii=False, indent=2)

print(f"API search successful. Listings: {len(listings)}")
print(f"Public listings prepared: {len(public_listings)}")
print(f"Credits used: {payload.get('credits_used')}")
