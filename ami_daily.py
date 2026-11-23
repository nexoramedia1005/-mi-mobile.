
import json
import os
import sys
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
    "condition": "used",
    "sort": "newest",
    "page": "1",
}

url = API_URL + "?" + urlencode(params)
request = Request(
    url,
    headers={"x-api-key": API_KEY, "Accept": "application/json"}
)

try:
    with urlopen(request, timeout=120) as response:
        payload = json.loads(response.read().decode("utf-8"))
except HTTPError as error:
    detail = error.read().decode("utf-8", errors="replace")
    print(f"API error HTTP {error.code}: {detail[:1000]}")
    sys.exit(1)
except (URLError, TimeoutError) as error:
    print(f"Network/API error: {error}")
    sys.exit(1)

if payload.get("success") is False:
    print("API error:", payload.get("error", "unknown"))
    sys.exit(1)

listings = payload.get("listings")

if not isinstance(listings, list):
    print("Unexpected API response: listings missing")
    sys.exit(1)

result = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "source": "API.SH Avito Search",
    "query": params,
    "credits_used": payload.get("credits_used"),
    "total_found": payload.get("total"),
    "count_returned": len(listings),
    "listings": listings,
}

with open("ami-search-test.json", "w", encoding="utf-8") as file:
    json.dump(result, file, ensure_ascii=False, indent=2)

print(f"API test successful. Listings: {len(listings)}")
print(f"Credits used: {payload.get('credits_used')}")
