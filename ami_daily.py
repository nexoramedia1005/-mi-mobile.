
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from zoneinfo import ZoneInfo

API_URL = "https://api.api.sh/avito/v1/search"
API_KEY = os.environ.get("AVITO_API_KEY")

if not API_KEY:
    print("ERROR: AVITO_API_KEY secret is missing.")
    sys.exit(1)

SEARCHES = [
    {"key": "iphone", "name": "iPhone", "q": "iphone",
     "category": "telefony"},
    {"key": "laptops", "name": "Ноутбуки", "q": "ноутбук",
     "category": "noutbuki"},
    {"key": "sneakers", "name": "Кроссовки", "q": "кроссовки",
     "category": "odezhda_obuv_aksessuary"},
    {"key": "winter_jackets", "name": "Зимние куртки",
     "q": "зимняя куртка",
     "category": "odezhda_obuv_aksessuary"},
    {"key": "tv", "name": "Телевизоры", "q": "телевизор",
     "category": "bytovaya_elektronika"}
]


def api_request(params):
    url = API_URL + "?" + urlencode(params)
    request = Request(
        url,
        headers={
            "x-api-key": API_KEY,
            "Accept": "application/json"
        }
    )

    delays = [30, 60, 120]

    for attempt in range(4):
        try:
            print(f"API attempt {attempt + 1}/4")

            with urlopen(request, timeout=120) as response:
                data = json.loads(
                    response.read().decode("utf-8")
                )

            if data.get("success") is False:
                raise RuntimeError(
                    data.get("error", "Unknown API error")
                )

            return data

        except HTTPError as error:
            detail = error.read().decode(
                "utf-8", errors="replace"
            )

            temporary = (
                error.code == 429 or error.code >= 500
                or "status 429" in detail
            )

            if not temporary or attempt == 3:
                raise RuntimeError(
                    f"HTTP {error.code}: {detail[:700]}"
                )

            print(
                f"Temporary HTTP {error.code}. "
                f"Waiting {delays[attempt]} seconds."
            )
            time.sleep(delays[attempt])

        except (URLError, TimeoutError) as error:
            if attempt == 3:
                raise RuntimeError(str(error))

            print(
                f"Network error. Waiting "
                f"{delays[attempt]} seconds."
            )
            time.sleep(delays[attempt])

    raise RuntimeError("API request failed")


def clean_listing(item, search):
    if not isinstance(item, dict):
        return None

    title = item.get("title")
    price = item.get("price")

    if not title or not isinstance(price, (int, float)):
        return None

    listing_id = item.get("id")
    url = item.get("url") or item.get("link")

    if not listing_id and not url:
        return None

    return {
        "id": str(listing_id or url),
        "title": str(title)[:300],
        "price": price,
        "url": url if isinstance(url, str) else "",
        "published": item.get("published"),
        "search_group": search["key"],
        "search_name": search["name"]
    }


def load_history():
    path = Path("data/market-history.json")

    if not path.exists():
        return {"version": 2, "snapshots": []}

    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)

        if isinstance(data.get("snapshots"), list):
            return data

    except (OSError, json.JSONDecodeError):
        print("WARNING: History file could not be read.")

    return {"version": 2, "snapshots": []}


def main():
    generated_at = datetime.now(timezone.utc).isoformat()
    today = datetime.now(
        ZoneInfo("Europe/Moscow")
    ).date().isoformat()

    all_listings = {}
    search_results = []

    for number, search in enumerate(SEARCHES, start=1):
        print(
            f"\nSEARCH {number}/{len(SEARCHES)}: "
            f"{search['name']}"
        )

        params = {
            "q": search["q"],
            "location": "moskva",
            "category": search["category"],
            "radius_km": "100",
            "sort": "newest",
            "page": "1"
        }

        payload = api_request(params)
        listings = payload.get("listings")

        if not isinstance(listings, list):
            raise RuntimeError(
                f"Unexpected response for {search['name']}"
            )

        ids = []

        for item in listings:
            cleaned = clean_listing(item, search)

            if not cleaned:
                continue

            listing_id = cleaned["id"]
            ids.append(listing_id)

            if listing_id not in all_listings:
                all_listings[listing_id] = cleaned
                all_listings[listing_id]["search_groups"] = [
                    search["key"]
                ]
            elif search["key"] not in all_listings[
                listing_id
            ]["search_groups"]:
                all_listings[listing_id][
                    "search_groups"
                ].append(search["key"])

        search_results.append({
            "key": search["key"],
            "name": search["name"],
            "category": search["category"],
            "total_found": payload.get("total"),
            "count_returned": len(listings),
            "unique_count": len(set(ids)),
            "credits_used": payload.get("credits_used"),
            "ids": sorted(set(ids))
        })

        print(
            f"Found: {len(listings)}; "
            f"credits: {payload.get('credits_used')}"
        )

        if number < len(SEARCHES):
            time.sleep(3)

    listings_for_history = list(all_listings.values())

    public_result = {
        "generated_at": generated_at,
        "source": "API.SH Avito Search",
        "location": "Москва, радиус 100 км",
        "searches": search_results,
        "total_found": sum(
            int(x.get("total_found") or 0)
            for x in search_results
        ),
        "count_returned": len(all_listings),
        "listings": listings_for_history
    }

    Path("data").mkdir(exist_ok=True)

    with open(
        "ami-search-public.json", "w", encoding="utf-8"
    ) as file:
        json.dump(
            public_result, file,
            ensure_ascii=False, indent=2
        )

    # Загружаем прежнюю историю, не удаляя старые записи.
    history = load_history()

    snapshot = {
        "date": today,
        "generated_at": generated_at,
        "searches": search_results,
        "count_listings": len(listings_for_history),
        "listings": listings_for_history
    }

    snapshots = [
        x for x in history["snapshots"]
        if x.get("date") != today
    ]

    snapshots.append(snapshot)
    snapshots.sort(key=lambda x: x.get("date", ""))

    history = {
        "version": 2,
        "updated_at": generated_at,
        "snapshots": snapshots[-45:]
    }

    with open(
        "data/market-history.json", "w", encoding="utf-8"
    ) as file:
        json.dump(
            history, file,
            ensure_ascii=False, separators=(",", ":")
        )

    archive = {
        "generated_at": generated_at,
        "searches": search_results,
        "count_unique": len(all_listings),
        "listings": listings_for_history
    }

    with open(
        "ami-search-test.json", "w", encoding="utf-8"
    ) as file:
        json.dump(
            archive, file,
            ensure_ascii=False, indent=2
        )

    print("\nAMI SEARCH COMPLETED")
    print(f"Unique listings: {len(all_listings)}")
    print(f"Searches: {len(SEARCHES)}")
    print(f"History days: {len(history['snapshots'])}")
    print(
        "History listings saved: "
        f"{len(listings_for_history)}"
    )
    print("History format: version 2")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"\nAMI ERROR: {error}")
        sys.exit(1)
