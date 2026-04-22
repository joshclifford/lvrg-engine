"""
LVRG Lead Magnet Engine — Site + Email Generator
Uses Claude to generate personalized HTML site and outreach email.
"""

import anthropic
import os
import json
from config import (ANTHROPIC_API_KEY, SENDER_NAME, SENDER_EMAIL,
                    SENDER_AGENCY, SENDER_WEBSITE, SENDER_PHONE,
                    BOOKING_URL, PREVIEW_BASE_URL, SITES_DIR, EMAILS_DIR)

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


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
- Raw site content: {intel.get('raw_markdown', '')[:1500]}

BUILD a complete single-file HTML homepage (index.html). Requirements:

DESIGN:
- All CSS inline in <style> tags — no external CSS files
- Google Fonts only (via @import in style) 
- Use the brand vibe and primary color to guide the design
- Must look like a $5,000 professionally designed website
- Modern, beautiful, conversion-optimized

LAYOUT (in order):
1. LVRG CLAIM BAR: Sticky top bar — black background, subtle. Text: "This site was built for [Business Name] by LVRG Agency." Right side: gold "Claim This Site →" button linking to {BOOKING_URL}
2. NAV: Logo (text), nav links, primary CTA button
3. HERO: Bold 5-8 word headline, subheadline, 2 CTAs, visual element (CSS gradient/geometric — NO external img URLs)
4. SOCIAL PROOF BAR: 3 key stats from their intel
5. SERVICES: 3 cards
6. TESTIMONIALS: 2-3 pull quotes (write compelling ones based on their business type and social proof)
7. CTA BANNER: "Ask us anything" above the chat widget area
8. FOOTER: Contact info, hours, copyright "LVRG Agency"

CHAT WIDGET (bottom-right, fixed):
- Circular button with chat icon
- Opens a 300x420px panel on click
- Header: business name + "AI Assistant" + avatar (CSS circle with initial)
- Pre-populated opening message specific to their business and main offering
- Input field + send button
- Style in brand colors
- Make it feel real and premium

COPY:
- Write ALL copy fresh — do not copy their existing site verbatim
- Headline: punchy, benefit-driven, 5-8 words
- Every CTA drives toward their main conversion goal
- Mention their city/neighborhood naturally

OUTPUT: Return ONLY the complete HTML. No explanation. No markdown code blocks. Just raw HTML starting with <!DOCTYPE html>"""

    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=8000,
        messages=[{"role": "user", "content": site_prompt}]
    )
    
    html = response.content[0].text.strip()
    
    # Strip markdown code blocks if Claude wrapped it
    if html.startswith("```"):
        html = html.split("\n", 1)[1]
        if html.endswith("```"):
            html = html.rsplit("```", 1)[0]
    
    # Save site
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
    email_path = os.path.join(EMAILS_DIR, f"{prospect_id}.json")
    with open(email_path, "w") as f:
        json.dump(email_data, f, indent=2)
    
    print(f"  [generator] Email saved to {email_path}")
    return email_data
