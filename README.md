# Google Maps Scraper

Pure Python scraper for any Google Maps place — no browser, no paid APIs.

## Demo

[![Watch the demo](https://img.youtube.com/vi/VtLQgs7eOaQ/0.jpg)](https://www.youtube.com/watch?v=VtLQgs7eOaQ)

---

## What It Does

For any Google Maps URL:
- Extracts name, category, rating, address, website, phone number
- Fetches all reviews with author, star rating, date, and text
- Filters reviews by star rating (5-star, 1–2 star)
- Downloads results as JSON or CSV

Works for any place type — restaurants, hotels, cafes, anything.

---

## How It Works

Replicates Google Maps' internal protobuf API calls using Python `requests`.
No Playwright, no Selenium, no paid services.

- Place details via the `tbm=map` protobuf endpoint
- Reviews via the `listentitiesreviews` endpoint with limit-based pagination
- Place IDs converted from hex to signed 64-bit integers for the `pb` parameter

---

## How to Run

**Install:**
```bash
pip install requests
```

**Web UI:**
```bash
cd src
python3 server.py
# open Chrome → localhost:8000
```

**Command line:**
```bash
python3 src/parse.py 'https://www.google.com/maps/place/...'
python3 src/reviews.py
```
