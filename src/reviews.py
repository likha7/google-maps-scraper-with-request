import requests
import json
import re
import csv
import time

# ── YOUR COOKIES ───────────────────────────────────────────────────────────────
COOKIES_DICT = {
    "SID":               "your_SID_here",
    "SSID":              "your_SSID_here",
    "HSID":              "your_HSID_here",
    "SAPISID":           "your_SAPISID_here",
    "__Secure-1PSID":    "your_Secure1PSID_here",
    "__Secure-3PSID":    "your_Secure3PSID_here",
    "NID":               "your_NID_here",
}


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
}

# ── helpers ────────────────────────────────────────────────────────────────────
def hex_to_signed_int(hex_str):
    val = int(hex_str, 16)
    if val >= 2**63:
        val -= 2**64
    return val


def is_valid_place_id(place_id):
    if not place_id:
        return False
    parts = place_id.split(':')
    if len(parts) != 2:
        return False
    try:
        int(parts[0], 16)
        int(parts[1], 16)
        return len(parts[1]) >= 10
    except ValueError:
        return False


# ── phone ──────────────────────────────────────────────────────────────────────
def get_phone(website_url):
    if not website_url:
        return ""
    try:
        r = requests.get(website_url, headers=HEADERS, timeout=5, allow_redirects=True)
        phones = re.findall(r'\+998[\d\s\-\(\)]{9,15}', r.text)
        if phones:
            return re.sub(r'[\s\-\(\)]', '', phones[0])
    except Exception:
        pass
    return ""


# ── reviews ────────────────────────────────────────────────────────────────────
def fetch_reviews_batch(place_id, limit=100, sort=2):
    """
    Fetch a batch of reviews using the limit parameter.
    The API returns reviews 1..limit in one shot.
    Max safe limit is ~150 before Google returns invalid JSON.
    """
    parts = place_id.split(':')
    id1   = hex_to_signed_int(parts[0])
    id2   = hex_to_signed_int(parts[1])

    pb = (
        f"!1m2!1y{id1}!2y{id2}"
        f"!2m2!1i0!2i{limit}"
        f"!3e{sort}"
        f"!4m5!3b1!4b1!5b1!6b1!7b1"
        f"!5m2!1s!7e81"
    )

    r = requests.get(
        "https://www.google.com/maps/preview/review/listentitiesreviews",
        params={"authuser": "0", "hl": "en", "gl": "us", "pb": pb},
        headers=HEADERS,
        cookies=COOKIES_DICT,
        timeout=20
    )
    text = r.text[r.text.index('\n') + 1:]
    data = json.loads(text)

    reviews   = []
    raw       = data[2] if len(data) > 2 and data[2] else []
    # data[5] contains rating distribution e.g. [37, 15, 47, 95, 757]
    # sum = total review count on Google Maps
    total_count = sum(data[5]) if len(data) > 5 and data[5] else 0

    for item in raw:
        try:
            reviews.append({
                "author": item[0][1],
                "rating": item[4],
                "date":   item[1],
                "text":   item[3] or ""
            })
        except Exception:
            continue

    return reviews, total_count


def get_all_reviews(place_id, max_reviews=100, sort=2):
    """
    Pagination strategy: the API uses limit-based pagination, not offset.
    request limit=100  → returns reviews 1-100
    request limit=150  → returns reviews 1-150
    We fetch in batches of 100, stopping when no new reviews come back.
    Max safe batch size is 150. Above that Google returns invalid JSON.
    """
    if not is_valid_place_id(place_id):
        return []

    BATCH = 100   # safe batch size
    all_reviews  = []
    seen_keys    = set()

    limit = BATCH
    while len(all_reviews) < max_reviews:
        actual_limit = min(limit, max_reviews)
        try:
            batch, total = fetch_reviews_batch(place_id, limit=actual_limit, sort=sort)
        except Exception:
            break

        if not batch:
            break

        # add only genuinely new reviews
        new = []
        for r in batch:
            key = (r["author"], r["date"], r["text"][:30])
            if key not in seen_keys:
                seen_keys.add(key)
                new.append(r)

        if not new:
            break  # no new reviews — we've hit the ceiling

        all_reviews = list({
            (r["author"], r["date"], r["text"][:30]): r
            for r in all_reviews + new
        }.values())

        print(f"    fetched {len(all_reviews)} reviews...", end="\r")

        if len(batch) < actual_limit:
            break  # got fewer than asked — end of reviews

        if limit >= max_reviews:
            break

        limit += BATCH  # increase limit to get next batch
        time.sleep(0.5)

    print()
    return all_reviews[:max_reviews]


def filter_by_stars(reviews, stars):
    if isinstance(stars, int):
        stars = [stars]
    return [r for r in reviews if r["rating"] in stars]


# ── main ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":

    print("=" * 50)
    print("  Google Maps Scraper — Reviews & Phones")
    print("=" * 50)

    try:
        with open("places.json", "r", encoding="utf-8") as f:
            places = json.load(f)
    except FileNotFoundError:
        print("\nplaces.json not found. Run parse.py first.")
        exit(1)

    print(f"\nLoaded {len(places)} place(s)")

    max_r = input("Max reviews per place (press Enter for 100): ").strip()
    max_reviews = int(max_r) if max_r.isdigit() else 100

    print("\nSort reviews by:")
    print("  1 = Most relevant")
    print("  2 = Newest (default)")
    print("  3 = Highest rated")
    print("  4 = Lowest rated")
    sort_input = input("Choose (1-4, press Enter for 2): ").strip()
    sort = int(sort_input) if sort_input in ["1", "2", "3", "4"] else 2

    print()
    results = []

    for i, place in enumerate(places):
        place_id = place.get("place_id", "")
        name     = place.get("name", "")
        website  = place.get("website", "")

        print(f"[{i+1}/{len(places)}] {name}")

        phone = get_phone(website) if website else ""
        if phone:
            print(f"  Phone:   {phone}")

        reviews = get_all_reviews(place_id, max_reviews=max_reviews, sort=sort)
        print(f"  Reviews: {len(reviews)}")

        results.append({
            "place_id":        place_id,
            "name":            name,
            "category":        place.get("category", ""),
            "district":        place.get("district", ""),
            "address":         place.get("address", ""),
            "rating":          place.get("rating", ""),
            "website":         website,
            "phone":           phone,
            "total_reviews":   len(reviews),
            "reviews":         reviews,
            "reviews_5star":   filter_by_stars(reviews, 5),
            "reviews_1_2star": filter_by_stars(reviews, [1, 2]),
        })

        time.sleep(0.3)

    with open("output.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    with open("output.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "name", "category", "district", "address",
            "rating", "phone", "website",
            "total_reviews", "5star_count", "1_2star_count"
        ])
        writer.writeheader()
        for r in results:
            writer.writerow({
                "name":          r["name"],
                "category":      r["category"],
                "district":      r["district"],
                "address":       r["address"],
                "rating":        r["rating"],
                "phone":         r["phone"],
                "website":       r["website"],
                "total_reviews": r["total_reviews"],
                "5star_count":   len(r["reviews_5star"]),
                "1_2star_count": len(r["reviews_1_2star"]),
            })

    total  = sum(r["total_reviews"] for r in results)
    phones = sum(1 for r in results if r["phone"])

    print(f"\n{'=' * 50}")
    print(f"Places:        {len(results)}")
    print(f"Total reviews: {total}")
    print(f"With phone:    {phones}")
    print(f"\nSaved: output.json + output.csv")
