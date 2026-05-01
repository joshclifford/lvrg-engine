"""
LVRG Lead Magnet Engine — Site + Email Generator
Uses Claude to generate personalized HTML site and outreach email.
"""

import anthropic
import os
import json
from config import (SENDER_NAME, SENDER_EMAIL,
                    SENDER_AGENCY, SENDER_WEBSITE, SENDER_PHONE,
                    BOOKING_URL, PREVIEW_BASE_URL, SITES_DIR, EMAILS_DIR)

def _get_client():
    key = os.environ.get("ANTHROPIC_API_KEY") or ""
    return anthropic.Anthropic(api_key=key)


def generate_site(intel: dict, prospect_id: str) -> str:
    """Generate a complete 2-page HTML site for a prospect. Returns folder path."""
    
    print(f"  [generator] Generating site for {intel['business_name']}...")
    
    site_prompt = f"""You are an expert web designer building a high-end preview website for {intel['business_name']}.

PROSPECT INTEL:
- Business: {intel['business_name']}
- Domain: {intel['domain']}
- Description: {intel['description']}
- Services: {', '.join(intel['services']) if intel['services'] else 'Not listed'}
- Location: {intel['location']}
- Phone: {intel.get('phone', 'Not listed')}
- Hours: {intel.get('hours', 'Not listed')}
- Social proof: {intel.get('social_proof', 'Not listed')}
- Brand vibe: {intel.get('brand_vibe', 'clean, modern')}
- Primary color: {intel.get('primary_color', '#333')}
- Business type: {intel.get('business_type', 'other')}
- What's missing on their site: {intel.get('missing', 'chat, CTA, contact info')}
- Raw site content: {intel.get('raw_text', '')[:2000]}

BUILD a complete single-file HTML homepage (index.html).

⚠️ CRITICAL OUTPUT RULE — READ FIRST:
DO NOT write a large <style> block. Write a SHORT <style> (CSS reset + :root vars only, max 30 lines),
then immediately write <body> with ALL styling as inline style= attributes on each element.
This is mandatory — long <style> blocks get cut off before the HTML body is ever written.

REQUIRED FILE STRUCTURE:
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{{business name}} | {{tagline}}</title>
  <link href="https://fonts.googleapis.com/css2?family=..." rel="stylesheet">
  <style>
    * {{ margin:0; padding:0; box-sizing:border-box; }}
    body {{ font-family: '...', sans-serif; }}
    /* NOTHING ELSE IN STYLE — use inline styles on every element */
  </style>
</head>
<body>
  <!-- ALL CONTENT HERE WITH INLINE style= ATTRIBUTES -->
</body>
</html>

DESIGN:
- Use primary color {intel.get('primary_color', '#333')} and secondary {intel.get('secondary_color', '#f5f5f5')} throughout
- Brand vibe: {intel.get('brand_vibe', 'clean, modern')} — let this guide fonts, spacing, mood
- Must look like a $5,000 professionally designed website
- Use Google Fonts that match the brand vibe
- NO external image URLs — use CSS gradients and background colors for visual sections

SECTIONS (all using inline style= attributes):
1. CLAIM BAR: sticky top bar, black background. "This site was built for {intel['business_name']} by LVRG Agency" + gold "Claim This Site →" button → {BOOKING_URL}
2. NAV: business name as logo, 3 nav links, primary CTA button
3. HERO: bold 5-8 word headline (use their tagline/vibe: "{intel.get('tagline','')}"), subheadline with value prop, 2 CTAs, CSS gradient background using brand colors
4. SOCIAL PROOF BAR: use their REAL stats — {intel.get('social_proof', '3 key stats')}
5. SERVICES: 3 cards based on their REAL services: {', '.join((intel.get('services') or [])[:3])}
6. TESTIMONIALS: 2-3 compelling pull quotes — write them fresh but grounded in their real social proof and business type
7. CTA BANNER: compelling headline + description driving toward: {intel.get('key_cta', 'booking')}
8. CHAT WIDGET (fixed bottom-right): circular button → 300x420 panel, opening message specific to their business (persona: {intel.get('chat_persona', 'friendly assistant')}), input + send button
9. FOOTER: {intel.get('location','')}, {intel.get('phone','')}, hours, © LVRG Agency

COPY RULES:
- Use their REAL business details, real services, real social proof
- Reference {intel.get('location','').split(',')[0] if intel.get('location') else 'their city'} naturally in copy
- Every CTA drives toward: {intel.get('cta_angle', 'booking a visit')}
- Pain point to address: {intel.get('pain_point', '')}

OUTPUT: Return ONLY the complete HTML. No explanation. No markdown code fences. Start with <!DOCTYPE html>"""

    client = _get_client()
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=12000,
        messages=[{"role": "user", "content": site_prompt}]
    )
    
    html = response.content[0].text.strip()
    
    # Strip markdown code blocks if Claude wrapped it
    if html.startswith("```"):
        html = html.split("\n", 1)[1]
        if html.endswith("```"):
            html = html.rsplit("```", 1)[0]
    
    # Ensure HTML is complete — if truncated, close it
    if not html.rstrip().endswith("</html>"):
        if not "</body>" in html:
            html += "\n</body>"
        html += "\n</html>"
    
    # Save site
    os.makedirs(SITES_DIR, exist_ok=True)
    site_dir = os.path.join(SITES_DIR, prospect_id)
    os.makedirs(site_dir, exist_ok=True)
    
    index_path = os.path.join(site_dir, "index.html")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(html)
    
    print(f"  [generator] Site saved to {index_path}")
    return site_dir


def generate_email(intel: dict, grade: dict, prospect_id: str) -> dict:
    """Generate personalized outreach email. Returns dict with subjects + body."""
    
    print(f"  [generator] Drafting email for {intel['business_name']}...")
    
    preview_url = f"{PREVIEW_BASE_URL}/{prospect_id}/index.html"
    
    email_prompt = f"""Write a cold outreach email from {SENDER_NAME} at {SENDER_AGENCY} to the owner/decision maker of {intel['business_name']}.

PROSPECT INTEL:
- Business: {intel['business_name']} ({intel['domain']})
- What they do: {intel['description']}
- Location: {intel['location']}
- What's missing on their site: {intel.get('missing', '')}
- Social proof: {intel.get('social_proof', '')}
- Site score: {grade['total']}/10 — {grade['verdict']}
- Business type: {intel['business_type']}

CAMPAIGN CONTEXT:
We built them a free personalized preview website showing what their site could look like with AI-powered redesign + a live AI chat agent. They can claim it by booking a call.

WRITE:
1. THREE subject line variants:
   - A: Curiosity ("We built something for [name]...")
   - B: Pain-point (reference their specific gap)  
   - C: Benefit/outcome

2. EMAIL BODY (4-6 sentences MAX):
   - Opening: hyper-specific to their business — reference something real and unique about them
   - Problem: 1 sentence naming their exact gap from the intel
   - Offer: "We built you a free preview — new homepage and a live AI chat agent that [specific use case]"
   - Preview URL: {preview_url}
   - CTA: "Claim it free by booking a 15-min call: {BOOKING_URL}"
   - Signature: {SENDER_NAME} | {SENDER_AGENCY} | {SENDER_WEBSITE} | {SENDER_PHONE}

RULES:
- No exclamation points
- No buzzwords (synergy, leverage, game-changer, cutting-edge)
- Sound like a real human, not a marketing department
- Every sentence must feel written only for this business
- Body is 4-6 sentences only — brevity wins in cold email

OUTPUT FORMAT (JSON only, no markdown):
{{
  "subject_a": "...",
  "subject_b": "...", 
  "subject_c": "...",
  "body": "...",
  "recommended_subject": "b"
}}"""

    client = _get_client()
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=1500,
        messages=[{"role": "user", "content": email_prompt}]
    )
    
    raw = response.content[0].text.strip()
    
    # Strip markdown if present
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    
    try:
        email_data = json.loads(raw)
    except:
        # Fallback parse
        email_data = {
            "subject_a": f"We built something for {intel['business_name']}...",
            "subject_b": f"Quick question about {intel['domain']}",
            "subject_c": f"Free preview site for {intel['business_name']}",
            "body": raw,
            "recommended_subject": "b"
        }
    
    email_data["preview_url"] = preview_url
    email_data["prospect_id"] = prospect_id
    
    # Save
    os.makedirs(EMAILS_DIR, exist_ok=True)
    email_path = os.path.join(EMAILS_DIR, f"{prospect_id}.json")
    with open(email_path, "w") as f:
        json.dump(email_data, f, indent=2)
    
    print(f"  [generator] Email saved to {email_path}")
    return email_data
