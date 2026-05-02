"""
LVRG Lead Magnet Engine — Prospect Intel Gatherer
Fetches site content via requests + Claude extraction.
Falls back gracefully if site is unreachable.
"""

import requests
import json
import os
import anthropic
from config import INTEL_DIR
import os

def _get_client():
    key = os.environ.get("ANTHROPIC_API_KEY") or ""
    return anthropic.Anthropic(api_key=key)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def fetch_screenshot(domain: str) -> str | None:
    """Fetch a full-page screenshot via Firecrawl. Returns base64 PNG string or None."""
    api_key = os.environ.get("FIRECRAWL_API_KEY", "")
    if not api_key:
        print("  [intel] No FIRECRAWL_API_KEY — skipping screenshot")
        return None
    url = f"https://{domain}" if not domain.startswith("http") else domain
    try:
        resp = requests.post(
            "https://api.firecrawl.dev/v1/scrape",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"url": url, "formats": ["screenshot@fullPage"], "waitFor": 1500},
            timeout=30
        )
        data = resp.json()
        # Firecrawl returns a URL or base64 string under data.screenshot
        screenshot = (data.get("data") or {}).get("screenshot")
        if not screenshot:
            print(f"  [intel] Screenshot not returned for {domain}")
            return None
        # If it's a URL, fetch and convert to base64
        if screenshot.startswith("http"):
            img_resp = requests.get(screenshot, timeout=15)
            import base64
            screenshot = base64.b64encode(img_resp.content).decode("utf-8")
        # Strip data URI prefix if present
        if "," in screenshot and screenshot.startswith("data:"):
            screenshot = screenshot.split(",", 1)[1]
        print(f"  [intel] ✓ Screenshot captured for {domain} ({len(screenshot)//1024}KB)")
        return screenshot
    except Exception as e:
        print(f"  [intel] Screenshot failed: {e}")
        return None


def fetch_yelp_intel(business_name: str, domain: str) -> dict:
    """Fetch Yelp data for a business: rating, review count, top reviews, photo URLs.
    Uses Firecrawl to find + scrape the Yelp listing.
    Returns a dict with keys: rating, review_count, reviews (list), photo_urls (list).
    Returns empty dict if not found or Firecrawl key missing."""
    api_key = os.environ.get("FIRECRAWL_API_KEY", "")
    if not api_key:
        print("  [yelp] No FIRECRAWL_API_KEY — skipping")
        return {}

    # Step 1: Search Yelp for the business
    try:
        city = "San Diego"
        search_query = f"{business_name} {city} site:yelp.com"
        search_resp = requests.post(
            "https://api.firecrawl.dev/v1/search",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"query": search_query, "limit": 3},
            timeout=20
        )
        search_data = search_resp.json()
        results = search_data.get("data") or []
        yelp_url = None
        for r in results:
            url_candidate = r.get("url", "")
            if "yelp.com/biz/" in url_candidate:
                yelp_url = url_candidate
                break
        if not yelp_url:
            print(f"  [yelp] No Yelp listing found for {business_name}")
            return {}
        print(f"  [yelp] Found listing: {yelp_url}")
    except Exception as e:
        print(f"  [yelp] Search failed: {e}")
        return {}

    # Step 2: Scrape the Yelp page
    try:
        scrape_resp = requests.post(
            "https://api.firecrawl.dev/v1/scrape",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"url": yelp_url, "formats": ["markdown"], "waitFor": 2000},
            timeout=30
        )
        scrape_data = scrape_resp.json()
        content = (scrape_data.get("data") or {}).get("markdown", "")
        if not content:
            print(f"  [yelp] Empty Yelp page returned")
            return {}
    except Exception as e:
        print(f"  [yelp] Scrape failed: {e}")
        return {}

    # Step 3: Extract structured Yelp data with Claude (haiku — cheap + fast)
    try:
        client = _get_client()
        extract_prompt = f"""Extract structured Yelp data from this page content.

YELP PAGE CONTENT:
{content[:6000]}

Return ONLY valid JSON with these fields:
- rating: overall star rating as a float (e.g. 4.5)
- review_count: number of reviews as an integer
- reviews: array of up to 5 objects, each with: {{"author": "First name only", "rating": 5, "text": "review text (max 120 chars)"}}
- photo_urls: array of up to 6 image URLs from the page that appear to be food/venue photos (full https:// URLs only; skip avatars/icons)
- price_range: e.g. "$$" or empty string
- categories: array of category strings e.g. ["Japanese", "Sushi"]

If a field is not found, use null or empty array. Return ONLY JSON, no markdown."""
        response = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=1000,
            messages=[{"role": "user", "content": extract_prompt}]
        )
        raw = response.content[0].text.strip()
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.split("```")[0]
        yelp_data = json.loads(raw)
        yelp_data["yelp_url"] = yelp_url
        count = len(yelp_data.get("reviews") or [])
        photos = len(yelp_data.get("photo_urls") or [])
        print(f"  [yelp] ✓ {yelp_data.get('rating')} stars, {yelp_data.get('review_count')} reviews, {count} pulled, {photos} photos")
        return yelp_data
    except Exception as e:
        print(f"  [yelp] Extraction failed: {e}")
        return {}


def fetch_site_content(domain: str) -> str:
    """Fetch raw HTML/text from a site."""
    url = f"https://{domain}" if not domain.startswith("http") else domain
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        # Strip HTML tags roughly for Claude
        import re
        text = resp.text
        # Remove scripts and styles
        text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', ' ', text)
        # Collapse whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        return text[:4000]
    except Exception as e:
        print(f"  [intel] Fetch failed: {e}")
        return ""


def extract_intel_with_claude(domain: str, raw_text: str) -> dict:
    """Use Claude to extract structured intel from raw site content."""
    
    prompt = f"""Analyze this website content from {domain} and extract structured information.

WEBSITE CONTENT:
{raw_text}

Extract and return a JSON object with these fields:
- business_name: The name of the business (string)
- tagline: Their tagline or hero headline (string, empty if none)
- description: What the business does in 2-3 sentences (string)
- services: List of main services/offerings (array of strings)
- location: City, neighborhood, or address (string)
- phone: Phone number if present (string, empty if none)
- email: Email address if present (string, empty if none)
- hours: Business hours if present (string, empty if none)
- social_proof: Awards, years in business, testimonials, notable claims (string)
- key_cta: Their main call to action if any (string, empty if none)
- missing: Important elements missing from the site - be specific (string, e.g. "no chat widget, no online booking, no menu listed")
- brand_vibe: Describe the brand feel in 5-10 words (string, e.g. "dark moody speakeasy with gold accents")
- primary_color: Best guess at primary brand color as hex (string, e.g. "#1a1a2e")
- secondary_color: Secondary brand color as hex (string)
- business_type: One of: restaurant, bar, catering, coffee_shop, retail, craft_beverage, service, other (string)
- pain_point: The single biggest conversion problem with their current site in one sentence (string)
- chat_persona: How an AI chat agent should behave for this business in one sentence (string)
- cta_angle: The best CTA angle for this business - what they most want customers to do (string, e.g. "Book a Private Event", "Get a Free Quote", "Reserve a Table")
- owner_name: Owner or decision maker first name if mentioned anywhere on the site (string, empty if not found)
- neighborhood: Specific San Diego neighborhood or area, parsed from the location field (string, e.g. "North Park", "Little Italy", "Gaslamp", empty if unknown)

Return ONLY valid JSON, no markdown, no explanation."""

    client = _get_client()
    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}]
    )
    
    raw = response.content[0].text.strip()
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.split("```")[0]
    
    try:
        return json.loads(raw)
    except:
        return {}


def scrape_site(domain: str) -> dict:
    """Full intel gather for a prospect domain."""
    
    # Strip protocol, path, query — keep only the hostname
    domain = domain.strip().lower()
    domain = domain.replace("https://", "").replace("http://", "")
    domain = domain.split("/")[0].split("?")[0].strip()
    url = f"https://{domain}"
    print(f"  [intel] Fetching {url}...")
    
    raw_text = fetch_site_content(domain)
    screenshot_b64 = fetch_screenshot(domain)
    
    if raw_text:
        print(f"  [intel] Extracting structured intel with Claude...")
        extracted = extract_intel_with_claude(domain, raw_text)
    else:
        extracted = {}

    # Yelp enrichment — fetch after we know the business name
    business_name_for_yelp = extracted.get("business_name") or domain.split(".")[0].replace("-", " ").title()
    print(f"  [intel] Fetching Yelp data for {business_name_for_yelp}...")
    yelp = fetch_yelp_intel(business_name_for_yelp, domain)
    
    # Build final intel object with fallbacks
    intel = {
        "domain": domain,
        "url": url,
        "business_name": extracted.get("business_name") or domain.split(".")[0].replace("-", " ").title(),
        "tagline": extracted.get("tagline", ""),
        "description": extracted.get("description", f"Local business at {domain}"),
        "services": extracted.get("services", []),
        "location": extracted.get("location", "San Diego, CA"),
        "phone": extracted.get("phone", ""),
        "email": extracted.get("email", ""),
        "hours": extracted.get("hours", ""),
        "social_proof": extracted.get("social_proof", ""),
        "key_cta": extracted.get("key_cta", ""),
        "missing": extracted.get("missing", "chat widget, clear CTA, contact info"),
        "brand_vibe": extracted.get("brand_vibe", "clean, modern local business"),
        "primary_color": extracted.get("primary_color", "#1a1a2e"),
        "secondary_color": extracted.get("secondary_color", "#c9a961"),
        "business_type": extracted.get("business_type", "other"),
        "pain_point": extracted.get("pain_point", "Visitors can't easily take action on the site"),
        "chat_persona": extracted.get("chat_persona", "Friendly assistant that answers questions and helps customers"),
        "cta_angle": extracted.get("cta_angle", "Get in Touch"),
        "owner_name": extracted.get("owner_name", ""),
        "neighborhood": extracted.get("neighborhood", ""),
        "raw_text": raw_text[:1000],
        "screenshot_b64": screenshot_b64,  # base64 PNG of existing site, used by Kimi vision
        # Yelp enrichment
        "yelp_rating": yelp.get("rating"),
        "yelp_review_count": yelp.get("review_count"),
        "yelp_reviews": yelp.get("reviews") or [],
        "yelp_photo_urls": yelp.get("photo_urls") or [],
        "yelp_url": yelp.get("yelp_url", ""),
        "yelp_price_range": yelp.get("price_range", ""),
        "yelp_categories": yelp.get("categories") or [],
    }
    
    print(f"  [intel] ✓ {intel['business_name']} — {intel['business_type']} — {intel['location']}")
    
    # Save
    os.makedirs(INTEL_DIR, exist_ok=True)
    slug = domain.replace(".", "_")
    with open(os.path.join(INTEL_DIR, f"{slug}.json"), "w") as f:
        json.dump(intel, f, indent=2)
    
    return intel


def grade_site(intel: dict) -> dict:
    """Score the site 0-10 against the LVRG rubric. Target: 2-7."""
    
    scores = {}
    
    scores["value_prop"] = 7 if intel.get("tagline") else (5 if len(intel.get("description","")) > 30 else 2)
    
    cta = (intel.get("key_cta") or "").lower()
    scores["primary_cta"] = 8 if any(w in cta for w in ["book","order","call","get","contact","buy","reserve","quote"]) else (4 if cta else 1)
    
    contact_score = 0
    if intel.get("phone"): contact_score += 4
    if intel.get("email"): contact_score += 3
    if intel.get("location") and intel["location"] != "San Diego, CA": contact_score += 3
    scores["contact"] = min(contact_score, 10)
    
    sp = intel.get("social_proof", "")
    scores["social_proof"] = 8 if len(sp) > 50 else (5 if len(sp) > 10 else 2)
    
    scores["hours"] = 6 if intel.get("hours") else 2
    
    missing = (intel.get("missing") or "").lower()
    has_chat = "chat" not in missing
    scores["chat"] = 8 if has_chat else 0
    
    gap_count = sum(1 for w in ["chat","booking","menu","email","phone","contact"] if w in missing)
    scores["gaps"] = max(0, 10 - gap_count * 2)
    
    total = round(sum(scores.values()) / len(scores))
    
    return {
        "scores": scores,
        "total": total,
        "verdict": get_verdict(total),
        "worth_targeting": 2 <= total <= 7
    }


def get_verdict(score: int) -> str:
    if score <= 2: return "Barely functional — may not convert well"
    if score <= 4: return "Weak — strong opportunity"
    if score <= 6: return "Mid — clear conversion gaps"
    if score <= 8: return "Good — may not need us"
    return "Strong — not a target"
