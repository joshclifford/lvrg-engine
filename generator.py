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

def _build_chat_widget(intel: dict) -> str:
    """Build the chat widget HTML — injected programmatically after Claude generates the site."""
    color = intel.get('primary_color', '#333')
    name = intel.get('business_name', 'Us')
    initial = name[0].upper()
    greeting = intel.get('chat_persona', 'Hey there')
    phone = intel.get('phone', '')
    intel_json = json.dumps({k: v for k, v in intel.items() if k != 'raw_text'}, ensure_ascii=False)
    intel_json = intel_json.replace('</', '<\\/')  # prevent </script> (or any </tag>) from closing the block
    return f"""<style>#lvrg-chat,#lvrg-chat *{{all:initial;box-sizing:border-box!important;}}</style>
<div id="lvrg-chat" style="position:fixed;bottom:24px;right:24px;z-index:2147483647;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <button id="lvrg-btn" onclick="lvrgToggle()" style="width:60px;height:60px;border-radius:50%;background:{color};border:none;cursor:pointer;box-shadow:0 4px 20px rgba(0,0,0,0.25);display:flex;align-items:center;justify-content:center;">
    <svg width="26" height="26" fill="none" stroke="#fff" stroke-width="2" viewBox="0 0 24 24"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
  </button>
  <div id="lvrg-panel" style="display:none;position:fixed;bottom:96px;right:24px;width:320px;max-width:calc(100vw - 48px);height:460px;background:#fff;border-radius:16px;box-shadow:0 8px 40px rgba(0,0,0,0.18);overflow:hidden;flex-direction:column;z-index:2147483647;">
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
var _lvrgEndpoint='{os.environ.get("CHAT_ENDPOINT") or "https://lvrg-engine-production.up.railway.app/chat"}';
function lvrgOpen(){{var p=document.getElementById('lvrg-panel');p.style.display='flex';}}
function lvrgClose(){{var p=document.getElementById('lvrg-panel');p.style.display='none';}}
function lvrgToggle(){{var p=document.getElementById('lvrg-panel');if(p.style.display==='none'){{lvrgOpen();}}else{{lvrgClose();}}}}
document.addEventListener('click',function(e){{var w=document.getElementById('lvrg-chat');if(w&&!w.contains(e.target)){{lvrgClose();}}}});
document.addEventListener('keydown',function(e){{if(e.key==='Escape'){{lvrgClose();}}}});
function lvrgAppend(role,text){{var d=document.getElementById('lvrg-msgs');var m=document.createElement('div');m.style.cssText=role==='user'?'background:{color};color:#fff;padding:10px 14px;border-radius:12px;border-bottom-right-radius:4px;font-size:14px;line-height:1.5;align-self:flex-end;max-width:85%;':'background:#fff;padding:12px 14px;border-radius:12px;border-bottom-left-radius:4px;font-size:14px;line-height:1.5;box-shadow:0 1px 4px rgba(0,0,0,0.06);max-width:85%;';m.textContent=text;d.appendChild(m);d.scrollTop=d.scrollHeight;}}
async function lvrgSend(){{var inp=document.getElementById('lvrg-input');var msg=inp.value.trim();if(!msg)return;inp.value='';lvrgAppend('user',msg);_lvrgHistory.push({{role:'user',content:msg}});try{{var r=await fetch(_lvrgEndpoint,{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{message:msg,business_name:_lvrgIntel.business_name,intel:_lvrgIntel,history:_lvrgHistory.slice(-8)}})}});var d=await r.json();lvrgAppend('assistant',d.reply);_lvrgHistory.push({{role:'assistant',content:d.reply}})}}catch(e){{lvrgAppend('assistant','Sorry, something went wrong. Please call us directly at {phone}.');}}}}
</script>"""


def _get_client():
    key = os.environ.get("ANTHROPIC_API_KEY") or ""
    return anthropic.Anthropic(api_key=key)


def _build_part1_prompt(intel: dict, notes_block: str, hero_bg_instruction: str, image_rule: str) -> str:
    """Prompt for Call 1 — above-fold sections (head through services)."""
    primary = intel.get('primary_color', '#1a1a2e')
    secondary = intel.get('secondary_color', '#333')
    return f"""You are an expert web designer building a high-end preview website for {intel['business_name']}.{notes_block}

PROSPECT INTEL:
- Business: {intel['business_name']}
- Domain: {intel['domain']}
- Description: {intel['description']}
- Services: {', '.join(intel['services']) if intel['services'] else 'Not listed'}
- Location: {intel.get('location') or 'Not found — do not invent a location'}
- Phone: {intel.get('phone', 'Not listed')}
- Hours: {intel.get('hours', 'Not listed')}
- Social proof: {intel.get('social_proof', 'Not listed')}
- Brand vibe: {intel.get('brand_vibe', 'clean, modern')}
- Primary color: {primary}
- Secondary color: {secondary}
- Business type: {intel.get('business_type', 'other')}
- What's missing: {intel.get('missing', 'chat, CTA, contact info')}
- Raw site content: {intel.get('raw_text', '')[:2000]}

BUILD the FIRST HALF of a single-file HTML homepage.

⚠️ OUTPUT RULES:
- Write a SHORT <style> block (CSS reset + :root vars only, max 30 lines)
- ALL section styling as inline style= attributes on every element
- Start with <!DOCTYPE html>
- <head> MUST include: <meta name="viewport" content="width=device-width, initial-scale=1">
- Stop after the services section — end your response with exactly: <!-- CONTINUE -->
- Do NOT write </body> or </html>
- Do NOT add any chat bubble, chat widget, floating button, or fixed-position popup — LVRG injects its own chat widget programmatically after generation

MOBILE:
- All sections must be full-width on small screens — use max-width containers (e.g. max-width:1100px;margin:0 auto) not fixed pixel widths
- Nav: hamburger or stacked layout on mobile — no overflow
- Cards/grids: stack to single column below 600px using inline style with flex-wrap:wrap

DESIGN:
- Primary: {primary}, Secondary: {secondary}
- Brand vibe: {intel.get('brand_vibe', 'clean, modern')} — guide fonts, spacing, mood
- Must look like a $5,000 professionally designed website
- Use Google Fonts matching the brand vibe
- Buttons: border-radius 8–12px minimum, padding 14px 28px, font-weight 600
- Cards: border-radius 12–16px, subtle box-shadow (0 4px 24px rgba(0,0,0,0.08)), padding 28px+
- Hover effects on every button and card: use inline onmouseover/onmouseout to apply transform:translateY(-2px) and box-shadow lift — no :hover in <style>
- Transitions: add transition:all 0.2s ease inline on every interactive element
- Sections: generous padding (80px+ top/bottom), never flat white backgrounds back-to-back — alternate with light tints or the brand color
{image_rule}

SECTIONS TO GENERATE (1–5 only):
1. CLAIM BAR: sticky top bar, black background. Centered single line: "This site was built for **{intel['business_name']}** by LVRG Agency" + gold "Claim This Site →" pill → {BOOKING_URL}
2. NAV: business name as logo, 3 nav links, primary CTA button
3. HERO: bold 5-8 word headline ("{intel.get('tagline','')}"), subheadline, 2 CTAs, {hero_bg_instruction}
4. SOCIAL PROOF BAR: real stats — {intel.get('social_proof', '3 key stats')}
5. SERVICES: 3 cards — {', '.join((intel.get('services') or [])[:3])}

End your response with exactly: <!-- CONTINUE -->"""


def _build_part2_prompt(intel: dict) -> str:
    """Prompt for Call 2 — below-fold sections (testimonials through footer)."""
    city = intel.get('location', '').split(',')[0] if intel.get('location') else 'their city'
    primary = intel.get('primary_color', '#1a1a2e')
    secondary = intel.get('secondary_color', '#333')
    brand_vibe = intel.get('brand_vibe', 'clean, modern')
    return f"""Continue this HTML page. Generate the remaining sections using the exact same design system, fonts, and inline-style patterns already established above.

BRAND VARIABLES (must match Part 1 exactly — do not drift):
- Primary color: {primary}
- Secondary color: {secondary}
- Brand vibe: {brand_vibe}
- Use the same Google Font already loaded in <head>
- All background accents, button colors, and heading colors must use {primary} or {secondary} — never introduce new colors

SECTIONS TO ADD (6–8):
6. TESTIMONIALS: 2-3 compelling pull quotes grounded in real social proof: "{intel.get('social_proof', '')}" — business type: {intel.get('business_type', 'other')}
7. CTA BANNER: compelling headline + description driving toward: {intel.get('key_cta', 'booking')}
8. FOOTER: {intel.get('location', '')}, {intel.get('phone', '')}, hours, © LVRG Agency

DESIGN RULES (same system as above):
- Buttons: border-radius 8–12px, padding 14px 28px, font-weight 600, transition:all 0.2s ease inline
- Cards: border-radius 12–16px, box-shadow 0 4px 24px rgba(0,0,0,0.08), padding 28px+
- Hover: inline onmouseover/onmouseout for transform:translateY(-2px) and shadow lift on every button and card
- Sections: 80px+ vertical padding, alternate background tints — no two plain white sections in a row

COPY RULES:
- Reference {city} naturally in copy
- Every CTA drives toward: {intel.get('cta_angle', 'booking a visit')}
- Pain point to address: {intel.get('pain_point', '')}
- Use same inline style= attribute patterns as the sections above

Do NOT add any chat bubble, floating button, or fixed-position widget — LVRG injects its own.
Close with </body></html>. Output HTML only — no explanation, no markdown fences."""


def _is_image_reachable(url: str) -> bool:
    """HEAD request to verify an image URL is actually loadable (hotlink / CSP / 404 check)."""
    try:
        import urllib.request as _ur
        req = _ur.Request(url, method='HEAD', headers={
            'User-Agent': 'Mozilla/5.0 (compatible; LVRG-Engine/1.0)'
        })
        with _ur.urlopen(req, timeout=5) as resp:
            return 200 <= resp.status < 400
    except Exception:
        return False


def _strip_fences(text: str) -> str:
    """Remove markdown code fences if Claude wrapped the output."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        text = text.rsplit("```", 1)[0]
    return text.strip()


def generate_site(intel: dict, prospect_id: str, notes: str = "") -> str:
    """Generate a complete HTML site using 2 sequential Opus calls to prevent truncation."""

    print(f"  [generator] Generating site for {intel['business_name']} (2-pass)...")

    notes_block = f"\n\nSPECIAL INSTRUCTIONS FROM CLIENT:\n{notes}\n" if notes else ""

    images = intel.get('images', [])
    hero_image = next((url for url in images if _is_image_reachable(url)), None)
    primary = intel.get('primary_color', '#1a1a2e')
    secondary = intel.get('secondary_color', '#333')

    if hero_image:
        hero_bg_instruction = (
            f"CSS background combining a real photo + overlay for readability: "
            f"background: linear-gradient(rgba(0,0,0,0.52), rgba(0,0,0,0.42)), "
            f"url('{hero_image}') center/cover no-repeat, "
            f"linear-gradient(135deg, {primary}, {secondary}); "
            f"(The gradient fires if the image fails — keep it always.)"
        )
        image_rule = "- Hero uses a real photo from their site (URL provided below). Apply dark overlay so text stays readable."
    else:
        hero_bg_instruction = f"CSS gradient background: linear-gradient(135deg, {primary}, {secondary})"
        image_rule = "- NO external image URLs — use CSS gradients and background colors for all visual sections"

    client = _get_client()

    # ── Pass 1: above fold (head + claim bar + nav + hero + social proof + services) ──
    print(f"  [generator] Pass 1/2 — above fold...")
    resp1 = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=6000,
        messages=[{"role": "user", "content": _build_part1_prompt(intel, notes_block, hero_bg_instruction, image_rule)}]
    )
    part1 = _strip_fences(resp1.content[0].text)
    part1_prefill = part1.replace("<!-- CONTINUE -->", "").rstrip()

    # ── Pass 2: below fold (testimonials + CTA + footer), prefilled for consistency ──
    print(f"  [generator] Pass 2/2 — below fold...")
    resp2 = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=6000,
        messages=[
            {"role": "user", "content": _build_part2_prompt(intel)},
            {"role": "assistant", "content": part1_prefill},
        ]
    )
    part2 = _strip_fences(resp2.content[0].text)

    # Stitch the two halves
    html = part1_prefill + "\n" + part2

    # Ensure properly closed
    if not html.rstrip().endswith("</html>"):
        if "</body>" not in html:
            html += "\n</body>"
        html += "\n</html>"

    # Inject chat widget — guaranteed last child of <body>
    widget_html = _build_chat_widget(intel)
    if '</body>' in html:
        html = html.replace('</body>', widget_html + '\n</body>', 1)
    else:
        html += widget_html + '\n</body>\n</html>'

    # Save
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
- Location: {intel.get('location') or 'Unknown'}
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
