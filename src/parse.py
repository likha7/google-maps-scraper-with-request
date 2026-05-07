import requests
import re
import json
import csv
import sys
import time

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
}


def extract_place_id(url):
    match = re.search(r'(0x[0-9a-f]+:0x[0-9a-f]+)', url)
    return match.group(1) if match else None


def extract_name(url):
    match = re.search(r'/maps/place/([^/@]+)', url)
    if match:
        return requests.utils.unquote(match.group(1)).replace('+', ' ')
    return ""


def extract_coords(url):
    match = re.search(r'@([-\d.]+),([-\d.]+)', url)
    if match:
        return float(match.group(1)), float(match.group(2))
    return None, None


def parse_details_from_response(text, place_id):
    """
    Try two patterns:
    1 — with rating/website before place_id (e.g. Yuzhanin)
    2 — place_id directly followed by name (e.g. Syrovarnya)
    """
    if place_id not in text:
        return None

    # Pattern 1: rating + website + place_id + name + category + district + address
    p1 = (
        r'\[null,null,null,null,null,null,null,([\d.]+)\]'
        r',null,null,\["(https?://[^"]+)","([^"]+)"'
        r'.*?'
        rf'"{re.escape(place_id)}"'
        r',"([^"]{2,80})"'
        r',null,\[([^\]]*)\]'
        r',"([^"]*)"'
        r',null,null,null,"([^"]{5,200})"'
    )
    m = re.search(p1, text, re.DOTALL)
    if m:
        rating, website, _, name, cats_raw, district, address = m.groups()
        cats = re.findall(r'"([^"]+)"', cats_raw)
        return {
            "name":     name.replace('\\u0026', '&'),
            "category": ", ".join(cats),
            "district": district,
            "address":  address.replace("\\u0026", "&"),
            "rating":   rating,
            "website":  website,
        }

    # Pattern 2: place_id directly → name → category → district → address
    p2 = (
        rf'"{re.escape(place_id)}"'
        r',"([^"]{2,80})"'
        r',null,\[([^\]]*)\]'
        r',"([^"]*)"'
        r',null,null,null,"([^"]{5,200})"'
    )
    m = re.search(p2, text, re.DOTALL)
    if m:
        name, cats_raw, district, address = m.groups()
        cats = re.findall(r'"([^"]+)"', cats_raw)
        return {
            "name":     name.replace('\\u0026', '&'),
            "category": ", ".join(cats),
            "district": district,
            "address":  address.replace("\\u0026", "&"),
            "rating":   "",
            "website":  "",
        }

    return None


def search_tbm_map(query, lat=None, lng=None):
    params = {"tbm": "map", "q": query, "hl": "en"}
    if lat and lng:
        params["pb"] = (
            f"!4m12!1m3!1d24567!2d{lng}!3d{lat}"
            f"!2m3!1f0!2f0!3f0!3m2!1i1024!2i768!4f13.1"
            f"!7i20!10b1!12m4!1m2!3d{lat}!4d{lng}!2d14!14b1"
        )
    r = requests.get(
        "https://www.google.com/search",
        params=params,
        headers=HEADERS,
        timeout=10
    )
    return r.text[r.text.index('\n') + 1:]


def get_place_details(place_id, name, lat=None, lng=None):
    """Try multiple search queries until we find the place details."""
    queries = [name, place_id]
    if name and len(name.split()) > 1:
        queries.append(name.split()[0])

    for query in queries:
        if not query:
            continue
        try:
            text    = search_tbm_map(query, lat, lng)
            details = parse_details_from_response(text, place_id)
            if details:
                return {"place_id": place_id, **details}
        except Exception:
            pass
        time.sleep(0.3)

    # fallback — basic info from URL only
    return {
        "place_id": place_id,
        "name":     name,
        "category": "",
        "district": "",
        "address":  "",
        "rating":   "",
        "website":  ""
    }


if __name__ == "__main__":

    print("=" * 50)
    print("  Google Maps Scraper — URL Parser")
    print("=" * 50)

    if len(sys.argv) > 1:
        urls = sys.argv[1:]
        print(f"\nProcessing {len(urls)} URL(s)...\n")
    else:
        print("\nPaste Google Maps URLs one per line.")
        print("Press Enter twice when done.\n")
        urls = []
        while True:
            line = input().strip()
            if not line:
                break
            urls.append(line)

    if not urls:
        print("No URLs provided.")
        sys.exit(1)

    places = []

    for i, url in enumerate(urls):
        place_id = extract_place_id(url)
        name     = extract_name(url)
        lat, lng = extract_coords(url)

        if not place_id:
            print(f"[{i+1}] Could not extract place ID from URL")
            continue

        print(f"[{i+1}] {name}")
        d = get_place_details(place_id, name, lat, lng)

        print(f"  Name:     {d['name']}")
        print(f"  Category: {d['category'] or '—'}")
        print(f"  Rating:   {d['rating'] or '—'}")
        print(f"  Address:  {d['address'] or '—'}")
        print(f"  Website:  {d['website'] or '—'}")
        print()

        places.append(d)
        time.sleep(0.5)

    if not places:
        print("No valid places found.")
        sys.exit(1)

    with open("places.json", "w", encoding="utf-8") as f:
        json.dump(places, f, indent=2, ensure_ascii=False)

    with open("places.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "place_id", "name", "category", "district", "address", "rating", "website"
        ])
        writer.writeheader()
        writer.writerows(places)

    print(f"Saved {len(places)} place(s) → places.json + places.csv")
    print("Now run: python3 reviews.py")
