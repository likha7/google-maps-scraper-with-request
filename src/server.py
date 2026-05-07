from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import re
import requests
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
    if place_id not in text:
        return None

    # Pattern 1 — with rating/website before place_id
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

    # Pattern 2 — place_id directly followed by name
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

    return {
        "place_id": place_id,
        "name":     name,
        "category": "",
        "district": "",
        "address":  "",
        "rating":   "",
        "website":  ""
    }


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


def fetch_reviews_batch(place_id, limit=100, sort=2):
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

    reviews = []
    raw     = data[2] if len(data) > 2 and data[2] else []
    total   = sum(data[5]) if len(data) > 5 and data[5] else 0

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

    return reviews, total


def get_all_reviews(place_id, max_reviews=100, sort=2):
    """
    Pagination: increase limit each batch to get more reviews.
    limit=100  → reviews 1-100
    limit=200  → reviews 1-200
    Stop when no new reviews appear or limit > max_reviews.
    Max batch size 150 to avoid Google returning invalid JSON.
    """
    if not is_valid_place_id(place_id):
        return []

    BATCH = 100
    all_reviews = []
    seen_keys   = set()
    limit       = min(BATCH, max_reviews)

    while len(all_reviews) < max_reviews:
        try:
            batch, total = fetch_reviews_batch(place_id, limit=limit, sort=sort)
        except Exception:
            break

        if not batch:
            break

        new = []
        for r in batch:
            key = (r["author"], r["date"], r["text"][:30])
            if key not in seen_keys:
                seen_keys.add(key)
                new.append(r)

        if not new:
            break

        all_reviews = list({
            (r["author"], r["date"], r["text"][:30]): r
            for r in all_reviews + new
        }.values())

        if len(batch) < limit:
            break

        if limit >= max_reviews:
            break

        limit = min(limit + BATCH, max_reviews)
        time.sleep(0.3)

    return all_reviews[:max_reviews]


def filter_by_stars(reviews, stars):
    if isinstance(stars, int):
        stars = [stars]
    return [r for r in reviews if r["rating"] in stars]


# ── HTTP server ────────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass

    def send_cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_cors()
        self.end_headers()

    def do_GET(self):
        if self.path in ('/', '/index.html'):
            try:
                with open('ui.html', 'rb') as f:
                    content = f.read()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', len(content))
                self.send_cors()
                self.end_headers()
                self.wfile.write(content)
            except FileNotFoundError:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b'ui.html not found')
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path != '/scrape':
            self.send_response(404)
            self.end_headers()
            return

        length = int(self.headers.get('Content-Length', 0))
        body   = json.loads(self.rfile.read(length))

        url         = body.get('url', '').strip()
        max_reviews = int(body.get('max_reviews', 0)) or 100
        sort        = int(body.get('sort', 2))

        result = {"error": None, "data": None}

        place_id = extract_place_id(url)
        if not place_id:
            result["error"] = "Could not find a place ID in this URL. Make sure it is a valid Google Maps place URL."
        else:
            print(f"→ {url[:60]}...")
            name     = extract_name(url)
            lat, lng = extract_coords(url)
            details  = get_place_details(place_id, name, lat, lng)
            phone    = get_phone(details.get("website", ""))
            reviews  = get_all_reviews(place_id, max_reviews=max_reviews, sort=sort)
            print(f"✓ {details['name']} — {len(reviews)} reviews")

            result["data"] = {
                **details,
                "phone":           phone,
                "total_reviews":   len(reviews),
                "reviews":         reviews,
                "reviews_5star":   filter_by_stars(reviews, 5),
                "reviews_1_2star": filter_by_stars(reviews, [1, 2]),
            }

        body_bytes = json.dumps(result).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', len(body_bytes))
        self.send_cors()
        self.end_headers()
        self.wfile.write(body_bytes)


if __name__ == "__main__":
    port = 8000
    print("=" * 50)
    print("  Google Maps Scraper — Server")
    print("=" * 50)
    print(f"\n  Running at http://localhost:{port}")
    print("  Open Chrome and go to that URL")
    print("  Press Ctrl+C to stop\n")
    HTTPServer(('', port), Handler).serve_forever()
