import logging
import re
import time
from html import unescape

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://shop.thetaridgecoffee.com/products.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; roastlab-scraper/1.0)"}


def html_to_text(html: str) -> str:
    if not html:
        return ""
    html = re.sub(r"<(style|script)[^>]*>.*?</\1>", "", html, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", unescape(text)).strip()


def parse_thetaridge_description(text: str) -> dict:
    """Extract structured fields from Theta Ridge's specific description format."""
    if not text:
        return {}

    def extract(keyword):
        # Matches "Keyword: Value" but stops at the first period, newline, or 200 chars
        match = re.search(rf"{keyword}\s*:\s*([^\.\n]+)", text, re.IGNORECASE)
        if match:
            val = match.group(1).strip()
            # Hard cap to be safe, since we increased DB to 255
            return val[:250]
        return ""

    return {
        "origin": extract("Origin"),
        "process": extract("Process") or extract("Processing"),
        "cultivar": extract("Variety") or extract("Varietal") or extract("Varieties"),
        # Roast recommendations can be tricky, we'll grab the first one mentioned
        "roast_recommendation": extract("Suggested roast") or extract("Roast Profile Suggestions"),
        # Flavors usually start after "Cupping Notes:"
        "flavor_keywords": extract("Cupping Notes") or extract("Cupping notes"),
    }


def fetch_thetaridge(max_pages: int = 20) -> list[dict]:
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
            variants = p.get("variants", [])
            if not variants:
                continue

            desc_text = html_to_text(p.get("body_html", ""))
            parsed = parse_thetaridge_description(desc_text)
            
            # Grab the first available variant, or the first variant if none are available
            active_variant = next((v for v in variants if v.get("available")), variants[0])

            results.append({
                "shopify_id": p["id"],
                "shopify_handle": p["handle"],
                "name": p["title"],
                "sweetmarias_url": f"https://shop.thetaridgecoffee.com/products/{p['handle']}",
                "price": active_variant["price"],
                "available": any(v.get("available") for v in variants),
                "body_html": p.get("body_html", ""),
                "description": desc_text,
                "tags": p.get("tags", []),
                "variant_prices": {v["title"]: v["price"] for v in variants},
                # Use the parsed fields
                "origin": parsed.get("origin", ""),
                "process": parsed.get("process", ""),
                "cultivar": parsed.get("cultivar", ""),
                "roast_recommendation": parsed.get("roast_recommendation", ""),
                "flavor_keywords": parsed.get("flavor_keywords", "")[:255],
            })

        logger.info("Fetched Theta Ridge page %s (%s products)", page, len(products))
        page += 1
        time.sleep(0.5)

    return results