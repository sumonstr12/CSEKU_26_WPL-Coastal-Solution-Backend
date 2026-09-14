"""
Seed shelters from DDM (rapid.ddm.gov.bd).

Features:
  - Fetches HTML table from DDM source
  - Normalizes district + upazila to Bangla
  - Geocodes location (with cache + retry + rate-limit safety)
  - SQLite + Postgres compatible
  - Resumable (skips already-geocoded rows on re-run)
  - Stores geocode cache in a JSON file so re-runs are fast

Usage:
    python scripts/seed_shelters.py
    python scripts/seed_shelters.py --limit 150
    python scripts/seed_shelters.py --skip-geocode   # fast import, no lat/lng
    python scripts/seed_shelters.py --refresh-geocode  # ignore cache
"""

import os
import re
import sys
import json
import time
import argparse
from pathlib import Path

import django
import requests
from bs4 import BeautifulSoup


# =========================================================
# DJANGO SETUP
# =========================================================

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "coastal_solution_backend.settings",
)

django.setup()


from incidents.models import Shelter   # adjust if your app is different


# =========================================================
# CONFIG
# =========================================================

SOURCE_URL = "https://rapid.ddm.gov.bd/service/shelter_info"

CACHE_FILE = BASE_DIR / "scripts" / ".geocode_cache.json"

NOMINATIM_DELAY = 1.1   # seconds between requests (free tier = 1/sec)
NOMINATIM_TIMEOUT = 10
MAX_RETRIES = 2


# =========================================================
# GEOCODER (lazy init so --skip-geocode doesn't require geopy)
# =========================================================

_geolocator = None
_geo_cache = {}


def _init_geocoder():
    global _geolocator, _geo_cache

    if _geolocator is not None:
        return

    try:
        from geopy.geocoders import Nominatim
    except ImportError:
        print("⚠  geopy not installed. Run: pip install geopy")
        print("   Continuing WITHOUT geocoding...\n")
        _geolocator = False
        return

    _geolocator = Nominatim(
        user_agent="coastalguard_bd_shelter_import",
        timeout=NOMINATIM_TIMEOUT,
    )

    # Load cache from disk
    if CACHE_FILE.exists():
        try:
            _geo_cache = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            print(f"✓ Loaded {len(_geo_cache)} cached geocode entries")
        except Exception as e:
            print(f"⚠  Could not load cache: {e}")
            _geo_cache = {}


def _save_cache():
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(
            json.dumps(_geo_cache, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        print(f"⚠  Could not save cache: {e}")


def geocode(query, refresh=False):
    """
    Returns (lat, lng) or (None, None).
    Uses Nominatim with cache + retry + polite delay.
    """
    if _geolocator is False:   # geopy not available
        return None, None

    if not query or len(query.strip()) < 3:
        return None, None

    query = query.strip()

    if not refresh and query in _geo_cache:
        cached = _geo_cache[query]
        return cached[0], cached[1]

    for attempt in range(MAX_RETRIES + 1):
        try:
            time.sleep(NOMINATIM_DELAY)

            result = _geolocator.geocode(
                query,
                country_codes="bd",
                exactly_one=True,
            )

            if result:
                coords = [result.latitude, result.longitude]
                _geo_cache[query] = coords
                _save_cache()
                return coords[0], coords[1]

            # Negative cache (avoid re-hitting for known-miss)
            _geo_cache[query] = [None, None]
            _save_cache()
            return None, None

        except Exception as e:
            if attempt < MAX_RETRIES:
                print(f"    retry {attempt + 1} for '{query}': {e}")
                time.sleep(2)
            else:
                print(f"    geocode failed for '{query}': {e}")

    return None, None


def geocode_location(location, upazila, district, refresh=False):
    """
    Try most-specific → least-specific queries.
    Returns (lat, lng) or (None, None).
    """
    candidates = []

    if location:
        candidates.append(f"{location}, Bangladesh")

    if upazila and district:
        candidates.append(f"{upazila}, {district}, Bangladesh")

    if district:
        candidates.append(f"{district}, Bangladesh")

    for q in candidates:
        lat, lng = geocode(q, refresh=refresh)
        if lat is not None and lng is not None:
            return lat, lng

    return None, None


# =========================================================
# DISTRICT MAP (English → Bangla)
# =========================================================

DISTRICT_MAP = {
    # Chattogram division
    "Chittagong": "চট্টগ্রাম",
    "Chattogram": "চট্টগ্রাম",
    "Cox's Bazar": "কক্সবাজার",
    "Cox’s Bazar": "কক্সবাজার",
    "Coxs Bazar": "কক্সবাজার",
    "Noakhali": "নোয়াখালী",
    "Feni": "ফেনী",
    "Lakshmipur": "লক্ষ্মীপুর",
    "Laxmipur": "লক্ষ্মীপুর",
    "Chandpur": "চাঁদপুর",
    "Comilla": "কুমিল্লা",
    "Cumilla": "কুমিল্লা",
    "Brahmanbaria": "ব্রাহ্মণবাড়িয়া",
    "Rangamati": "রাঙ্গামাটি",
    "Bandarban": "বান্দরবান",
    "Khagrachhari": "খাগড়াছড়ি",

    # Khulna division
    "Khulna": "খুলনা",
    "Satkhira": "সাতক্ষীরা",
    "Bagerhat": "বাগেরহাট",
    "Jessore": "যশোর",
    "Jashore": "যশোর",
    "Jhenaidah": "ঝিনাইদহ",
    "Magura": "মাগুরা",
    "Narail": "নড়াইল",
    "Kushtia": "কুষ্টিয়া",
    "Chuadanga": "চুয়াডাঙ্গা",
    "Meherpur": "মেহেরপুর",

    # Barishal division
    "Bhola": "ভোলা",
    "Patuakhali": "পটুয়াখালী",
    "Barguna": "বরগুনা",
    "Barisal": "বরিশাল",
    "Barishal": "বরিশাল",
    "Pirojpur": "পিরোজপুর",
    "Jhalokati": "ঝালকাঠি",
    "Jhalokathi": "ঝালকাঠি",

    # Dhaka division
    "Dhaka": "ঢাকা",
    "Gopalganj": "গোপালগঞ্জ",
    "Madaripur": "মাদারীপুর",
    "Shariatpur": "শরীয়তপুর",
    "Rajbari": "রাজবাড়ী",
    "Faridpur": "ফরিদপুর",
    "Kishoreganj": "কিশোরগঞ্জ",
    "Manikganj": "মানিকগঞ্জ",
    "Munshiganj": "মুন্সিগঞ্জ",
    "Narayanganj": "নারায়ণগঞ্জ",
    "Narsingdi": "নরসিংদী",
    "Tangail": "টাঙ্গাইল",
}


# =========================================================
# UPAZILA MAP (English → Bangla)
# =========================================================

UPAZILA_MAP = {
    # Khulna
    "Koyra": "কয়রা",
    "Kaira": "কয়রা",
    "Dacope": "দাকোপ",
    "Dakope": "দাকোপ",
    "Paikgacha": "পাইকগাছা",
    "Paikgachha": "পাইকগাছা",
    "Botiaghata": "বটিয়াঘাটা",
    "Batiaghata": "বটিয়াঘাটা",
    "Dumuria": "ডুমুরিয়া",
    "Dighalia": "দিঘলিয়া",
    "Phultala": "ফুলতলা",
    "Rupsha": "রূপসা",
    "Terokhada": "তেরখাদা",

    # Satkhira
    "Shyamnagar": "শ্যামনগর",
    "Assasuni": "আশাশুনি",
    "Ashashuni": "আশাশুনি",
    "Kaliganj": "কালীগঞ্জ",
    "Debhata": "দেবহাটা",
    "Kalaroa": "কলারোয়া",
    "Tala": "তালা",
    "Satkhira Sadar": "সাতক্ষীরা সদর",

    # Bagerhat
    "Mongla": "মোংলা",
    "Sarankhola": "শরণখোলা",
    "Morrelganj": "মোরেলগঞ্জ",
    "Moralganj": "মোরেলগঞ্জ",
    "Rampal": "রামপাল",
    "Fakirhat": "ফকিরহাট",
    "Mollahat": "মোল্লাহাট",
    "Chitalmari": "চিতলমারী",
    "Kachua": "কচুয়া",
    "Bagerhat Sadar": "বাগেরহাট সদর",

    # Bhola
    "Char Fasson": "চরফ্যাশন",
    "Charfasson": "চরফ্যাশন",
    "Monpura": "মনপুরা",
    "Manpura": "মনপুরা",
    "Daulatkhan": "দৌলতখান",
    "Lalmohan": "লালমোহন",
    "Tazumuddin": "তজুমদ্দিন",
    "Borhanuddin": "বোরহানউদ্দিন",
    "Bhola Sadar": "ভোলা সদর",

    # Patuakhali
    "Bauphal": "বাউফল",
    "Dashmina": "দশমিনা",
    "Galachipa": "গলাচিপা",
    "Kalapara": "কলাপাড়া",
    "Mirzaganj": "মির্জাগঞ্জ",
    "Rangabali": "রাঙ্গাবালী",
    "Dumki": "দুমকি",
    "Patuakhali Sadar": "পটুয়াখালী সদর",

    # Barguna
    "Patharghata": "পাথরঘাটা",
    "Amtali": "আমতলী",
    "Bamna": "বামনা",
    "Betagi": "বেতাগী",
    "Taltali": "তালতলী",
    "Barguna Sadar": "বরগুনা সদর",

    # Barishal
    "Barisal Sadar": "বরিশাল সদর",
    "Bakerganj": "বাকেরগঞ্জ",
    "Babuganj": "বাবুগঞ্জ",
    "Wazirpur": "উজিরপুর",
    "Banaripara": "বানারীপাড়া",
    "Gaurnadi": "গৌরনদী",
    "Agailjhara": "আগৈলঝাড়া",
    "Mehendiganj": "মেহেন্দিগঞ্জ",
    "Muladi": "মুলাদী",
    "Hizla": "হিজলা",

    # Pirojpur
    "Mathbaria": "মঠবাড়িয়া",
    "Bhandaria": "ভান্ডারিয়া",
    "Kawkhali": "কাউখালী",
    "Nazirpur": "নাজিরপুর",
    "Nesarabad": "নেছারাবাদ",
    "Swarupkathi": "স্বরূপকাঠি",
    "Pirojpur Sadar": "পিরোজপুর সদর",

    # Jhalokati
    "Jhalokati Sadar": "ঝালকাঠি সদর",
    "Kathalia": "কাঠালিয়া",
    "Nalchity": "নলছিটি",
    "Rajapur": "রাজাপুর",

    # Noakhali
    "Subarnachar": "সুবর্ণচর",
    "Hatiya": "হাতিয়া",
    "Companiganj": "কোম্পানীগঞ্জ",
    "Companigonj": "কোম্পানীগঞ্জ",
    "Senbagh": "সেনবাগ",
    "Begumganj": "বেগমগঞ্জ",
    "Chatkhil": "চাটখিল",
    "Sonaimuri": "সোনাইমুড়ী",
    "Kabirhat": "কবিরহাট",
    "Noakhali Sadar": "নোয়াখালী সদর",

    # Feni
    "Feni Sadar": "ফেনী সদর",
    "Chhagalnaiya": "ছাগলনাইয়া",
    "Daganbhuiyan": "দাগনভূঞা",
    "Parshuram": "পরশুরাম",
    "Sonagazi": "সোনাগাজী",
    "Fulgazi": "ফুলগাজী",

    # Lakshmipur
    "Ramgati": "রামগতি",
    "Ramganj": "রামগঞ্জ",
    "Raipur": "রায়পুর",
    "Kamalnagar": "কমলনগর",
    "Lakshmipur Sadar": "লক্ষ্মীপুর সদর",

    # Chandpur
    "Chandpur Sadar": "চাঁদপুর সদর",
    "Faridganj": "ফরিদগঞ্জ",
    "Haimchar": "হাইমচর",
    "Haziganj": "হাজীগঞ্জ",
    "Kachua Chandpur": "কচুয়া",
    "Matlab Dakshin": "মতলব দক্ষিণ",
    "Matlab Uttar": "মতলব উত্তর",
    "Shahrasti": "শাহরাস্তি",

    # Chattogram
    "Sandwip": "সন্দ্বীপ",
    "Sandweep": "সন্দ্বীপ",
    "Mirsarai": "মীরসরাই",
    "Sitakunda": "সীতাকুণ্ড",
    "Banshkhali": "বাঁশখালী",
    "Anwara": "আনোয়ারা",
    "Patiya": "পটিয়া",
    "Chandanaish": "চন্দনাইশ",
    "Satkania": "সাতকানিয়া",
    "Lohagara": "লোহাগাড়া",
    "Boalkhali": "বোয়ালখালী",
    "Fatikchhari": "ফটিকছড়ি",
    "Hathazari": "হাটহাজারী",
    "Raozan": "রাউজান",
    "Rangunia": "রাঙ্গুনিয়া",
    "Chattogram Sadar": "চট্টগ্রাম সদর",

    # Cox's Bazar
    "Teknaf": "টেকনাফ",
    "Ukhia": "উখিয়া",
    "Maheshkhali": "মহেশখালী",
    "Kutubdia": "কুতুবদিয়া",
    "Chakaria": "চকরিয়া",
    "Pekua": "পেকুয়া",
    "Ramu": "রামু",
    "Cox's Bazar Sadar": "কক্সবাজার সদর",

    # Gopalganj
    "Tungi Para": "টুঙ্গিপাড়া",
    "Tungipara": "টুঙ্গিপাড়া",
    "Kashiani": "কাশিয়ানী",
    "Kotalipara": "কোটালীপাড়া",
    "Muksudpur": "মুকসুদপুর",
    "Gopalganj Sadar": "গোপালগঞ্জ সদর",
}


# =========================================================
# STATUS
# =========================================================

def normalize_status(status):
    s = (status or "").strip().lower()

    if not s:
        return "READY"

    if any(k in s for k in ["useable", "usable", "open", "ready"]):
        return "OPEN"

    if any(k in s for k in ["repair", "maintenance", "construction"]):
        return "MAINTENANCE"

    if any(k in s for k in ["closed", "close", "shut"]):
        return "CLOSED"

    if "crowd" in s or "full" in s:
        return "CROWDED"

    return "READY"


# =========================================================
# PARSERS
# =========================================================

def parse_int(value, default=0):
    if not value:
        return default

    value = str(value).replace(",", "").strip()
    match = re.search(r"\d+", value)

    if not match:
        return default

    try:
        return int(match.group())
    except ValueError:
        return default


def parse_location(location):
    """
    DDM location format (typically):
        <detail>, <upazila>, <district>
    or  <upazila>, <district>
    or  <district>
    """
    if not location:
        return {"union": None, "upazila": None, "district": None}

    parts = [p.strip() for p in location.split(",") if p.strip()]

    if len(parts) >= 3:
        union = parts[0]
        upazila = parts[-2]
        district = parts[-1]
    elif len(parts) == 2:
        union = None
        upazila = parts[0]
        district = parts[1]
    elif len(parts) == 1:
        union = None
        upazila = None
        district = parts[0]
    else:
        union = None
        upazila = None
        district = None

    return {
        "union": union,
        "upazila": UPAZILA_MAP.get(upazila, upazila),
        "district": DISTRICT_MAP.get(district, district),
    }


def default_facilities(capacity):
    facilities = ["বিশুদ্ধ পানি", "শৌচাগার"]

    if capacity >= 500:
        facilities.append("প্রাথমিক চিকিৎসা")

    if capacity >= 1000:
        facilities.append("খাবার")

    if capacity >= 1500:
        facilities.append("গোবাদি পশুর জায়গা")

    return facilities


# =========================================================
# FETCH
# =========================================================

def fetch_rows():
    print(f"Fetching: {SOURCE_URL}")

    response = requests.get(
        SOURCE_URL,
        timeout=30,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (compatible; CoastalGuardBD/1.0; "
                "+https://github.com/coastalguard)"
            )
        },
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    table = soup.find("table")

    if not table:
        raise RuntimeError("Shelter table not found at source URL.")

    rows = table.find_all("tr")
    print(f"Found {len(rows) - 1} data rows\n")
    return rows[1:]


# =========================================================
# MAIN IMPORT
# =========================================================

def main(limit=None, skip_geocode=False, refresh_geocode=False):
    if not skip_geocode:
        _init_geocoder()

    rows = fetch_rows()

    imported = 0
    skipped = 0
    geocoded = 0
    geocode_failed = 0

    for row in rows:
        cells = row.find_all(["td", "th"])

        if len(cells) < 9:
            continue

        values = [c.get_text(" ", strip=True) for c in cells]

        try:
            serial = parse_int(values[0])
            name = values[1]
            area = parse_int(values[2])
            constructed_by = values[3]
            construction_year = values[4]
            capacity = parse_int(values[5])
            location = values[6]
            contact = values[7]
            source_status = values[8]

            loc = parse_location(location)
            district = loc["district"]
            upazila = loc["upazila"] or ""
            union = loc["union"]

            if not name or not district:
                skipped += 1
                continue

            shelter_id = str(serial) if serial > 0 else str(imported + 1)

            if capacity < 0:
                capacity = 0

            facilities = default_facilities(capacity)

            # -------- Geocode --------
            latitude = None
            longitude = None

            if not skip_geocode:
                latitude, longitude = geocode_location(
                    location=location,
                    upazila=upazila,
                    district=district,
                    refresh=refresh_geocode,
                )

                if latitude is not None:
                    geocoded += 1
                else:
                    geocode_failed += 1

            # -------- Save --------
            Shelter.objects.update_or_create(
                id=shelter_id,
                defaults={
                    "name": name[:255],
                    "division": None,
                    "district": district,
                    "upazila": upazila,
                    "union": union,
                    "village": None,
                    "address": location,
                    "latitude": latitude,
                    "longitude": longitude,
                    "capacity": capacity,
                    "occupied": 0,
                    "status": normalize_status(source_status),
                    "is_active": True,
                    "facilities": facilities,
                    "water": "বিশুদ্ধ পানি" in facilities,
                    "power": False,
                    "contact_person": (contact[:150] if contact else None),
                    "contact_phone": None,
                    "construction_year": (
                        construction_year[:50]
                        if construction_year
                        else None
                    ),
                    "constructed_by": (
                        constructed_by[:150]
                        if constructed_by
                        else None
                    ),
                },
            )

            imported += 1

            gps_tag = (
                f"✓ ({latitude:.3f},{longitude:.3f})"
                if latitude is not None
                else "✗"
            )

            print(
                f"[{imported:3d}] {shelter_id} | "
                f"{district}/{upazila} | "
                f"cap={capacity} | {gps_tag} | {name[:50]}"
            )

            if limit and imported >= limit:
                print(f"\nReached limit ({limit}). Stopping.")
                break

        except Exception as e:
            skipped += 1
            print(f"  Skipped: {values[:3]} | Error: {e}")

    # -------- Summary --------
    print()
    print("=" * 60)
    print("Shelter import completed")
    print("=" * 60)
    print(f"Imported/updated : {imported}")
    print(f"Skipped          : {skipped}")
    if not skip_geocode:
        print(f"Geocoded         : {geocoded}")
        print(f"Geocode failed   : {geocode_failed}")
    print(f"Cache file       : {CACHE_FILE}")
    print("=" * 60)


# =========================================================
# CLI
# =========================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed shelters from DDM.")
    parser.add_argument(
        "--limit",
        type=int,
        default=150,
        help="Max rows to import (default: 150, use 0 for all).",
    )
    parser.add_argument(
        "--skip-geocode",
        action="store_true",
        help="Skip geocoding (fast, no lat/lng).",
    )
    parser.add_argument(
        "--refresh-geocode",
        action="store_true",
        help="Ignore cache and re-geocode everything.",
    )

    args = parser.parse_args()

    main(
        limit=args.limit if args.limit > 0 else None,
        skip_geocode=args.skip_geocode,
        refresh_geocode=args.refresh_geocode,
    )