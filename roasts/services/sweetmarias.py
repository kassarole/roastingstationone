import logging
import re
import time
from html import unescape

import requests

logger = logging.getLogger(__name__)

# 1. CHANGED: Point to the root products endpoint, not the collection
BASE_URL = "https://www.sweetmarias.com/products.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; roastlab-scraper/1.0)"}


def html_to_text(html: str) -> str:
    """Strip tags and style/script blocks from the raw HTML."""
    if not html:
        return ""
    html = re.sub(r"<(style|script)[^>]*>.*?</\1>", "", html, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", unescape(text)).strip()


def parse_origin(tags: list[str]) -> str:
    """Extract origin from tags like 'Category_Sweet Marias/Green Coffee/Africa/Kenya'."""
    for tag in tags:
        if tag.startswith("Category_Sweet Marias/Green Coffee/"):
            parts = tag.split("/")
            if len(parts) >= 4 and parts[3] not in (
                "Latest Additions", "Decaf", "Coffee Sets", "By Type", "Sweet Maria's Blends"
            ):
                return parts[-1].strip()
    return ""


def parse_description(text: str) -> dict:
    """Extract process, roast rec, and flavors from natural language."""
    if not text:
        return {"process": "", "roast_recommendation": "", "flavor_keywords": ""}

    process = ""
    for p in ["Dry Process", "Wet Hulled", "Washed", "Natural", "Honey", "Anaerobic", "Decaf"]:
        if p.lower() in text.lower():
            process = p
            break

    roast_pattern = r'((?:City|Full City|French|Vienna)(?:\+)?(?:\s*(?:to|-)\s*(?:City|Full City|French|Vienna)(?:\+)?)?)'
    roast_rec = ""
    roast_match = re.search(roast_pattern, text)
    if roast_match:
        roast_rec = roast_match.group(1)

    flavor = ""
    flavor_match = re.match(r'^([^.]+\.)', text)
    if flavor_match:
        flavor = flavor_match.group(1).strip()
    else:
        flavor = text[:150].strip() + ("..." if len(text) > 150 else "")

    for prefix in ["Presents ", "Brings ", "This lot ", "An unique ", "A ", "An "]:
        if flavor.startswith(prefix):
            flavor = flavor[len(prefix):]
            break
            
    if flavor:
        flavor = flavor[0].upper() + flavor[1:]

    return {
        "process": process,
        "roast_recommendation": roast_rec,
        "flavor_keywords": flavor[:255]
    }


def fetch_green_coffee(max_pages: int = 40) -> list[dict]:
    results = []
    page = 1

    while page <= max_pages:
        resp = requests.get(
            BASE_URL,
            params={"limit": 250, "page": page},
            headers=HEADERS,
            timeout=30,
        )
        resp.raise_for_status()
        products = resp.json().get("products", [])
        if not products:
            break

        for p in products:
            # 2. CHANGED: Accept both Green Coffee and Archived Coffee
            if p.get("product_type") not in ("Green Coffee", "Archived Coffee"):
                continue
                
            variants = p.get("variants", [])
            if not variants:
                continue

            desc_text = html_to_text(p.get("body_html", ""))
            parsed_desc = parse_description(desc_text)
            tags = p.get("tags", [])

            results.append({
                "shopify_id": p["id"],
                "shopify_handle": p["handle"],
                "name": p["title"],
                "sweetmarias_url": f"https://www.sweetmarias.com/products/{p['handle']}",
                "price": variants[0]["price"],
                "available": any(v.get("available") for v in variants),
                "body_html": p.get("body_html", ""),
                "description": desc_text,
                "tags": tags,
                "variant_prices": {v["title"]: v["price"] for v in variants},
                "origin": parse_origin(tags),
                "process": parsed_desc["process"],
                "roast_recommendation": parsed_desc["roast_recommendation"],
                "flavor_keywords": parsed_desc["flavor_keywords"],
            })

        logger.info("Fetched page %s (%s products)", page, len(products))
        page += 1
        time.sleep(0.5)

    return results