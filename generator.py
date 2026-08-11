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

# Ceiling for a generated page. This is a cap, not a target — most pages come in
# well under it, so raising it costs nothing on a typical build and only helps
# the pages that were previously cut off. Deliberately not 128K: the caller
# aborts the whole engine call at 135s (build-smart-site ENGINE_TIMEOUT_MS) and
# generation already runs ~82s, so an unbounded ceiling would trade truncated
# pages for timed-out builds.
SITE_MAX_TOKENS = int(os.environ.get("SITE_MAX_TOKENS", "32000"))

def _build_chat_widget(intel: dict) -> str:
    """Build the chat widget HTML — injected programmatically after Claude generates the site."""
    color = intel.get('primary_color', '#333')
    name = intel.get('business_name', 'Us')
    initial = name[0].upper()
    greeting = intel.get('chat_persona', 'Hey there')
    phone = intel.get('phone', '')
    intel_json = json.dumps({k: v for k, v in intel.items() if k != 'raw_text'}, ensure_ascii=False)
    return f"""
<div id="lvrg-chat" style="position:fixed;bottom:24px;right:24px;z-index:2147483647;font-family:sans-serif;">
  <button id="lvrg-btn" onclick="lvrgToggle()" style="width:60px;height:60px;border-radius:50%;background:{color};border:none;cursor:pointer;box-shadow:0 4px 20px rgba(0,0,0,0.25);display:flex;align-items:center;justify-content:center;">
    <svg width="26" height="26" fill="none" stroke="#fff" stroke-width="2" viewBox="0 0 24 24"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
  </button>
  <div id="lvrg-panel" style="display:none;position:fixed;bottom:96px;right:24px;width:320px;height:460px;background:#fff;border-radius:16px;box-shadow:0 8px 40px rgba(0,0,0,0.18);overflow:hidden;flex-direction:column;z-index:2147483647;">
    <div style="background:{color};padding:16px 20px;color:#fff;display:flex;align-items:center;gap:12px;">
      <div style="width:38px;height:38px;border-radius:50%;background:rgba(255,255,255,0.2);display:flex;align-items:center;justify-content:center;font-weight:700;font-size:16px;">{initial}</div>
      <div><div style="font-weight:700;font-size:15px;">{name}</div><div style="font-size:12px;opacity:0.85;">AI Assistant &#x2022; Online</div></div>
    </div>
    <div id="lvrg-msgs" style="flex:1;padding:16px;overflow-y:auto;background:#f8f8f8;display:flex;flex-direction:column;gap:10px;">
      <div style="background:#fff;padding:12px 14px;border-radius:12px;border-bottom-left-radius:4px;font-size:14px;line-height:1.5;box-shadow:0 1px 4px rgba(0,0,0,0.06);">{greeting}! I can help answer questions about {name}. What can I help you with?</div>
    </div>
    <div style="padding:12px;background:#fff;border-top:1px solid #eee;display:flex;gap:8px;">
      <input id="lvrg-input" type="text" placeholder="Ask a question..." onkeydown="if(event.key==='Enter')lvrgSend()" style="flex:1;padding:10px 14px;border-radius:20px;border:1px solid #ddd;font-size:14px;outline:none;">
      <button onclick="lvrgSend()" style="width:40px;height:40px;border-radius:50%;background:{color};border:none;cursor:pointer;display:flex;align-items:center;justify-content:center;">
        <svg width="16" height="16" fill="#fff" viewBox="0 0 24 24"><path d="M2 21l21-9L2 3v7l15 2-15 2z"/></svg>
      </button>
    </div>
  </div>
</div>
<script>
var _lvrgIntel={intel_json};
var _lvrgHistory=[];
var _lvrgEndpoint='https://lvrg-engine-production.up.railway.app/chat';
function lvrgToggle(){{var p=document.getElementById('lvrg-panel');p.style.display=p.style.display==='none'?'flex':'none';}}
function lvrgAppend(role,text){{var d=document.getElementById('lvrg-msgs');var m=document.createElement('div');m.style.cssText=role==='user'?'background:{color};color:#fff;padding:10px 14px;border-radius:12px;border-bottom-right-radius:4px;font-size:14px;line-height:1.5;align-self:flex-end;max-width:85%;':'background:#fff;padding:12px 14px;border-radius:12px;border-bottom-left-radius:4px;font-size:14px;line-height:1.5;box-shadow:0 1px 4px rgba(0,0,0,0.06);max-width:85%;';m.textContent=text;d.appendChild(m);d.scrollTop=d.scrollHeight;}}
async function lvrgSend(){{var inp=document.getElementById('lvrg-input');var msg=inp.value.trim();if(!msg)return;inp.value='';lvrgAppend('user',msg);_lvrgHistory.push({{role:'user',content:msg}});try{{var r=await fetch(_lvrgEndpoint,{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{message:msg,business_name:_lvrgIntel.business_name,intel:_lvrgIntel,history:_lvrgHistory.slice(-8)}})}});var d=await r.json();lvrgAppend('assistant',d.reply);_lvrgHistory.push({{role:'assistant',content:d.reply}})}}catch(e){{lvrgAppend('assistant','Sorry, something went wrong. Please call us directly at {phone}.');}}}}
</script>"""


def _get_client():
    key = os.environ.get("ANTHROPIC_API_KEY") or ""
    return anthropic.Anthropic(api_key=key)


def generate_site(intel: dict, prospect_id: str, notes: str = "") -> str:
    """Generate a complete 2-page HTML site for a prospect. Returns folder path."""
    
    print(f"  [generator] Generating site for {intel['business_name']}...")
    
    notes_block = f"\n\nSPECIAL INSTRUCTIONS FROM CLIENT:\n{notes}\n" if notes else ""

    # Real photos scraped off the prospect's own site. When there are none the
    # page falls back to gradients — which is exactly what every page looked
    # like before, because nothing ever populated this.
    photos = intel.get("photos", [])
    if photos:
        photo_block = "REAL PHOTOS (from the business's own website — use these as <img> tags, linking straight to the URLs):\n" \
            + "\n".join(f"  {i + 1}. {url}" for i, url in enumerate(photos[:4])) \
            + "\nUse the strongest one as the hero (an <img> with object-fit:cover, or a CSS background-image url())." \
            + "\nUse the others in gallery or service sections where they fit. Don't force a photo in where it doesn't belong."
    else:
        photo_block = "PHOTOS: none available. Use CSS gradients and brand colours only — no placeholder images, no stock photo URLs."

    # Rating comes from the app (Google Maps via Apify), merged in by api.py.
    # Never invented here: a fabricated star rating on a real business's page
    # is a legal problem, not a design choice.
    # A rating and a review count arrive independently — Apify returns plenty of
    # listings with one and not the other. Branch on both, or a missing count is
    # interpolated as the literal "None" and published as "from None reviews".
    rating = intel.get("rating")
    review_count = intel.get("review_count")
    if rating is not None and review_count is not None:
        rating_block = (f"VERIFIED RATING: {rating}★ from {review_count} reviews. "
                        f"Use this as a real social-proof stat.")
    elif rating is not None:
        rating_block = (f"VERIFIED RATING: {rating}★. Use this as a real social-proof "
                        f"stat. You were NOT given a review count — do not state one.")
    else:
        rating_block = "RATING: none supplied. Do NOT invent a star rating or a review count."

    socials = intel.get("socials") or {}
    social_links = "\n".join(f"  {k.replace('_url', '').title()}: {v}" for k, v in socials.items())
    social_block = f"SOCIAL PROFILES (link these in the footer):\n{social_links}" if social_links else ""

    site_prompt = f"""You are an expert web designer building a high-end preview website for {intel['business_name']}.{notes_block}

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
- Raw site content: {intel.get('raw_text', '')}

{photo_block}

{rating_block}

{social_block}

BUILD a complete single-file HTML homepage (index.html).

STYLING:
Write a proper <style> block in the <head>. Use it — you have room.
It MUST include responsive breakpoints: the page has to work on a phone, not
just a desktop. Use @media queries for layout, type scale, and spacing, and add
:hover states on links and buttons.

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
    /* Full stylesheet here: layout, type scale, components, :hover states. */
    /* And @media breakpoints — the page must work on a phone. */
  </style>
</head>
<body>
  <!-- Content, styled by the classes defined above -->
</body>
</html>

DESIGN:
- Use primary color {intel.get('primary_color', '#333')} and secondary {intel.get('secondary_color', '#f5f5f5')} throughout
- Brand vibe: {intel.get('brand_vibe', 'clean, modern')} — let this guide fonts, spacing, mood
- Must look like a $5,000 professionally designed website
- Use Google Fonts that match the brand vibe
- Images: use ONLY the REAL PHOTOS listed above, if any were given. Never invent an
  image URL, never use a stock-photo or placeholder service. With no photos, build
  the visual sections from CSS gradients and brand colours.

SECTIONS:
1. CLAIM BAR: sticky top bar, black background. Centered single line: "This site was built for **{intel['business_name']}** by LVRG Agency" (business name in bold white, rest in normal gray/white text), then immediately a gold "Claim This Site →" pill button linking to {BOOKING_URL}. All on one centered line. No left/right split.
2. NAV: business name as logo, 3 nav links, primary CTA button
3. HERO: bold 5-8 word headline (use their tagline/vibe: "{intel.get('tagline','')}"), subheadline with value prop, 2 CTAs. Background: the best real photo if you were given one, otherwise a CSS gradient in their brand colours
4. SOCIAL PROOF BAR: only stats you were actually given — the verified rating above and {intel.get('social_proof', 'their listed claims')}. If you were given none, omit this section rather than filling it with invented numbers
5. SERVICES: 3 cards based on their REAL services: {', '.join((intel.get('services') or [])[:3])}
6. TESTIMONIALS: OMIT this section. You have not been given a single real customer quote, and this page carries the business's own name and branding — an invented quote puts words in a real customer's mouth on a page the owner will be asked to claim. Never write a testimonial, a customer name, or a quote.
7. CTA BANNER: compelling headline + description driving toward: {intel.get('key_cta', 'booking')}
8. FOOTER: {intel.get('location','')}, {intel.get('phone','')}, hours, © LVRG Agency

COPY RULES:
- Use their REAL business details, real services, real social proof
- NEVER write a fake testimonial, customer name, or quote. No real review text is
  ever supplied to you, so there is no case where a quote is legitimate — skip
  quotes entirely rather than inventing one that sounds plausible
- Reference {intel.get('location','').split(',')[0] if intel.get('location') else 'their city'} naturally in copy
- Every CTA drives toward: {intel.get('cta_angle', 'booking a visit')}
- Pain point to address: {intel.get('pain_point', '')}

OUTPUT: Return ONLY the complete HTML. No explanation. No markdown code fences. No chat widget — it will be injected. Start with <!DOCTYPE html>"""

    client = _get_client()
    # Streamed, not create(). A full page runs well past the SDK's non-streaming
    # HTTP timeout at this token ceiling; streaming also lets max_tokens rise
    # without the request dying mid-generation. get_final_message() gives the
    # same object create() would have returned.
    with client.messages.stream(
        model="claude-opus-4-5",
        max_tokens=SITE_MAX_TOKENS,
        messages=[{"role": "user", "content": site_prompt}],
    ) as stream:
        response = stream.get_final_message()

    if response.stop_reason == "max_tokens":
        print(f"  [generator] WARNING: hit max_tokens ({SITE_MAX_TOKENS}) — page may be cut short")

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
    
    # Inject chat widget programmatically — guaranteed last child of <body>
    # This avoids Claude placing it inside overflow:hidden sections
    widget_html = _build_chat_widget(intel)
    if '</body>' in html:
        html = html.replace('</body>', widget_html + '\n</body>', 1)
    else:
        html += widget_html + '\n</body>\n</html>'

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

    # Structured fields for Instantly custom variables
    email_data["business_name"] = intel.get("business_name", "")
    email_data["owner_name"] = intel.get("owner_name", "")
    email_data["neighborhood"] = intel.get("neighborhood", "")
    email_data["business_type"] = intel.get("business_type", "")
    email_data["pain_point"] = intel.get("pain_point", "")
    email_data["grade"] = grade.get("total", 0)
    email_data["hook"] = "new_site" if grade.get("total", 5) <= 5 else "live_chat"
    
    # Save
    os.makedirs(EMAILS_DIR, exist_ok=True)
    email_path = os.path.join(EMAILS_DIR, f"{prospect_id}.json")
    with open(email_path, "w") as f:
        json.dump(email_data, f, indent=2)
    
    print(f"  [generator] Email saved to {email_path}")
    return email_data
