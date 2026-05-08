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

def _is_light_color(hex_color: str) -> bool:
    """True if a hex color is too light to use as a button bg on a dark background."""
    h = hex_color.lstrip('#')
    if len(h) != 6:
        return False
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255 > 0.70


def _build_chat_widget(intel: dict) -> str:
    """Build the chat widget — uses Shadow DOM for total CSS isolation from the host page.

    Why Shadow DOM: previously we used `all:initial` to reset host CSS bleed, but it's too
    aggressive — SVG presentation attributes get reset and icons disappear. Shadow DOM gives
    perfect isolation: host page CSS can't reach in, and our widget CSS can't leak out.
    SVGs render normally because no global reset is needed."""
    color = intel.get('primary_color', '#333')
    name = intel.get('business_name') or 'Us'
    initial = name[0].upper() if name else 'C'
    greeting = intel.get('chat_persona') or 'Hey there'
    phone = intel.get('phone') or ''
    # Build a chat-context intel: include everything but cap raw_text to 12000 chars.
    # raw_text now includes homepage + subpages (/menu, /about, /contact). The chatbot
    # needs the full menu/pricing data to answer "what's on the menu" questions.
    chat_intel = dict(intel)
    if chat_intel.get('raw_text'):
        chat_intel['raw_text'] = chat_intel['raw_text'][:12000]
    intel_json = json.dumps(chat_intel, ensure_ascii=False)
    # Prevent </script> (or any </tag>) inside JSON values from closing the script block.
    intel_json = intel_json.replace('</', '<\\/')
    endpoint = os.environ.get("CHAT_ENDPOINT") or "https://lvrg-engine-production.up.railway.app/chat"

    # CSS template — placeholder __COLOR__ replaced after construction so we don't have to
    # escape every single `{` and `}` for an f-string.
    css = (
        ":host{all:initial;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;}"
        "*,*::before,*::after{box-sizing:border-box;}"
        ".btn{position:fixed;bottom:24px;right:24px;width:60px;height:60px;border-radius:50%;background:__COLOR__;border:none;cursor:pointer;box-shadow:0 4px 20px rgba(0,0,0,0.25);display:flex;align-items:center;justify-content:center;z-index:2147483647;transition:transform 0.15s ease;padding:0;}"
        ".btn:hover{transform:scale(1.06);}"
        ".btn svg{display:block;}"
        ".panel{position:fixed;bottom:96px;right:24px;width:340px;max-width:calc(100vw - 32px);height:480px;max-height:calc(100vh - 120px);background:#fff;border-radius:16px;box-shadow:0 12px 48px rgba(0,0,0,0.22);overflow:hidden;display:flex;flex-direction:column;z-index:2147483647;opacity:0;transform:translateY(16px) scale(0.96);pointer-events:none;transition:opacity 0.22s cubic-bezier(0.4,0,0.2,1),transform 0.22s cubic-bezier(0.4,0,0.2,1);}"
        ".panel.open{opacity:1;transform:translateY(0) scale(1);pointer-events:auto;}"
        ".head{background:__COLOR__;padding:16px 20px;color:#fff;display:flex;align-items:center;gap:12px;flex-shrink:0;}"
        ".avatar{width:40px;height:40px;border-radius:50%;background:rgba(255,255,255,0.22);display:flex;align-items:center;justify-content:center;font-weight:700;font-size:17px;color:#fff;flex-shrink:0;}"
        ".title{font-weight:700;font-size:15px;color:#fff;line-height:1.2;margin:0 0 2px;}"
        ".subtitle{font-size:12px;color:rgba(255,255,255,0.85);line-height:1.2;}"
        ".subtitle .dot{display:inline-block;width:6px;height:6px;border-radius:50%;background:#22c55e;margin-right:6px;vertical-align:middle;}"
        ".msgs{flex:1;padding:16px;overflow-y:auto;background:#f8f9fb;display:flex;flex-direction:column;gap:10px;}"
        ".bubble{padding:11px 14px;border-radius:14px;font-size:14px;line-height:1.5;max-width:85%;word-wrap:break-word;}"
        ".bubble.bot{background:#fff;color:#1a1a1a;border-bottom-left-radius:4px;box-shadow:0 1px 3px rgba(0,0,0,0.08);align-self:flex-start;}"
        ".bubble.user{background:__COLOR__;color:#fff;border-bottom-right-radius:4px;align-self:flex-end;}"
        ".foot{padding:12px;background:#fff;border-top:1px solid #eee;display:flex;gap:8px;flex-shrink:0;}"
        ".input{flex:1;padding:10px 14px;border-radius:22px;border:1px solid #e0e0e0;font-size:14px;outline:none;color:#1a1a1a;background:#fff;font-family:inherit;}"
        ".input:focus{border-color:__COLOR__;}"
        ".send{width:40px;height:40px;border-radius:50%;background:__COLOR__;border:none;cursor:pointer;display:flex;align-items:center;justify-content:center;flex-shrink:0;padding:0;transition:transform 0.12s ease;}"
        ".send:hover{transform:scale(1.06);}"
        ".send svg{display:block;}"
    ).replace("__COLOR__", color)
    css_js = json.dumps(css)  # safely escape for use in JS string

    inner_html = (
        '<button class="btn" type="button" aria-label="Open chat">'
        '<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>'
        '</button>'
        '<div class="panel">'
        '<div class="head">'
        '<div class="avatar">__INITIAL__</div>'
        '<div><div class="title">__NAME__</div><div class="subtitle"><span class="dot"></span>AI Assistant</div></div>'
        '</div>'
        '<div class="msgs"></div>'
        '<div class="foot">'
        '<input class="input" type="text" placeholder="Ask a question..." />'
        '<button class="send" type="button" aria-label="Send">'
        '<svg width="16" height="16" viewBox="0 0 24 24" fill="#ffffff"><path d="M2 21l21-9L2 3v7l15 2-15 2z"/></svg>'
        '</button>'
        '</div>'
        '</div>'
    )
    inner_html_js = json.dumps(
        inner_html.replace("__INITIAL__", initial).replace("__NAME__", name)
    )

    # The JS body uses placeholder tokens that are replaced at the end. This keeps us out
    # of f-string-vs-CSS-brace hell and avoids special-character escaping bugs.
    js = """
(function(){
  var host=document.getElementById('lvrg-chat-host');
  if(!host)return;
  var shadow=host.attachShadow({mode:'open'});
  var intel=__INTEL_JSON__;
  var endpoint=__ENDPOINT__;
  var greeting=__GREETING__;
  var name=__NAME__;
  var phone=__PHONE__;
  var history=[];
  var isOpen=false;
  shadow.innerHTML='<style>'+__CSS__+'</style>'+__INNER__;
  var btn=shadow.querySelector('.btn');
  var panel=shadow.querySelector('.panel');
  var msgs=shadow.querySelector('.msgs');
  var input=shadow.querySelector('.input');
  var send=shadow.querySelector('.send');
  function append(role,text){
    var b=document.createElement('div');
    b.className='bubble '+(role==='user'?'user':'bot');
    b.textContent=text;
    msgs.appendChild(b);
    msgs.scrollTop=msgs.scrollHeight;
  }
  function open_(){isOpen=true;panel.classList.add('open');setTimeout(function(){input.focus();},220);}
  function close_(){isOpen=false;panel.classList.remove('open');}
  function toggle(){if(isOpen)close_();else open_();}
  btn.addEventListener('click',function(e){e.stopPropagation();toggle();});
  panel.addEventListener('click',function(e){e.stopPropagation();});
  document.addEventListener('click',function(){close_();});
  document.addEventListener('keydown',function(e){if(e.key==='Escape')close_();});
  async function sendMsg(){
    var msg=input.value.trim();if(!msg)return;
    input.value='';
    append('user',msg);
    history.push({role:'user',content:msg});
    try{
      var r=await fetch(endpoint,{
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({message:msg,business_name:intel.business_name,intel:intel,history:history.slice(-8)})
      });
      var d=await r.json();
      append('assistant',d.reply);
      history.push({role:'assistant',content:d.reply});
    }catch(e){
      append('assistant','Sorry, something went wrong. Please reach us directly'+(phone?' at '+phone:'')+'.');
    }
  }
  send.addEventListener('click',sendMsg);
  input.addEventListener('keydown',function(e){if(e.key==='Enter')sendMsg();});
  append('bot',greeting+'! I can help answer questions about '+name+'. What can I help you with?');
})();
"""
    js = js.replace("__INTEL_JSON__", intel_json)
    js = js.replace("__ENDPOINT__", json.dumps(endpoint))
    js = js.replace("__GREETING__", json.dumps(greeting))
    js = js.replace("__NAME__", json.dumps(name))
    js = js.replace("__PHONE__", json.dumps(phone))
    js = js.replace("__CSS__", css_js)
    js = js.replace("__INNER__", inner_html_js)

    return '<div id="lvrg-chat-host"></div>\n<script>' + js + '</script>'


def _get_client():
    key = os.environ.get("ANTHROPIC_API_KEY") or ""
    return anthropic.Anthropic(api_key=key)


def _build_part1_prompt(intel: dict, notes_block: str, hero_bg_instruction: str, image_rule: str) -> str:
    """Prompt for Call 1 — above-fold sections (head through services)."""
    primary = intel.get('primary_color', '#1a1a2e')
    secondary = intel.get('secondary_color', '#333')
    raw_text = intel.get('raw_text', '') or ''
    content_notes = intel.get('content_notes') or ''
    return f"""You are an expert web designer building a high-end preview website for {intel['business_name']}.{notes_block}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PRIMARY COPY SOURCE — this is the actual content from the prospect's website.
Your headlines, taglines, descriptions, and section copy MUST be LIFTED FROM HERE,
not invented. Reuse their exact phrases wherever they fit. Paraphrase minimally.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{raw_text[:5000]}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

VERBATIM DETAILS (menu items, prices, named services, awards — use the EXACT wording):
{content_notes if content_notes else 'None extracted — rely on the primary copy source above.'}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ CONTENT ACCURACY — MANDATORY. Read before writing a single word of copy.
You are a copywriter working from the prospect's own website above. You are NOT
an inventor — you are a translator. Every sentence on this page must be traceable
back to the PRIMARY COPY SOURCE or the structured intel below.

RULES:
1. HERO HEADLINE: scan the primary copy source above for an existing tagline,
   slogan, or value proposition and USE THAT. If none exists, build the headline
   from a real phrase or claim found in the source. NEVER invent generic lines
   like "Excellence in Every Bite" or "Where Quality Meets Tradition".
2. HERO SUBHEADLINE: paraphrase one specific sentence from the source — keep their
   actual nouns, place names, and product names intact.
3. SERVICES SECTION: render ONLY services listed in the structured intel — do not
   add, rename, or remove any. Card descriptions must be lifted from how the source
   describes that service.
4. SOCIAL PROOF BAR: use ONLY numbers/claims explicitly present in the source or
   social_proof field. NEVER invent star counts, review counts, customer numbers,
   "10+ years experience", or award names.
5. CONTACT DETAILS: phone, hours, address — if listed, render exactly as given.
   If not listed, omit that element. Never invent a phone number or address.
6. MENU / PRICES / SPECIALS: copy from VERBATIM DETAILS unchanged. "Flat White £3.50"
   stays exactly "Flat White £3.50" — never round, abbreviate, or paraphrase prices.
7. NEVER INVENT: testimonials, certifications, founding year, staff names, seating
   capacity, delivery radius, social media follower counts, or any fact not present
   in the source above.
8. EMPTY FIELD = OMIT. If a field is empty or marked "Not listed", remove that
   element from the layout — do NOT fill the gap with generic placeholder copy.
9. NO EM-DASHES in body copy. Em-dashes (—) are an AI-writing tell. Use commas, periods,
   or colons instead. "Coffee for everyone, from commuters to creatives" — NOT
   "Coffee for everyone — from commuters to creatives".
10. NO SECTION LABELS as visible text. Never write headings like "Services Section",
    "About Section", "Features Section", "CTA Banner", "Testimonials". Section headings
    must be benefit-driven copy from the source — e.g. "What we serve", "How it started",
    "Why locals love us" — NOT generic labels.

QUALITY TEST — before you finalise, verify:
   - Can a reader find every headline phrase echoed somewhere in the PRIMARY COPY SOURCE?
   - If yes → ship it. If no → rewrite using the source's actual words.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STRUCTURED INTEL:
- Business: {intel['business_name']}
- Domain: {intel['domain']}
- Tagline (use as hero if present): {intel.get('tagline', '') or '(none — derive hero from primary copy source)'}
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

BUILD the FIRST HALF of a single-file HTML homepage.

⚠️ OUTPUT RULES:
- Write a SHORT <style> block (CSS reset + :root vars only, max 30 lines)
- ALL section styling as inline style= attributes on every element
- Start with <!DOCTYPE html>
- <head> MUST include: <meta name="viewport" content="width=device-width, initial-scale=1">
- Stop after the services section — end your response with exactly: <!-- CONTINUE -->
- Do NOT write </body> or </html>
- Do NOT add any chat bubble, chat widget, floating button, or fixed-position popup — LVRG injects its own
- Do NOT generate <form>, <input>, <textarea>, or <select> elements — there is no backend to process them; use visual info cards and CTA buttons instead

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
- ZERO dividers anywhere on the page — no <hr>, no border-top, no border-bottom, no box-shadow used as a line, no margin lines between sections. Sections flow into each other with only background-color or padding changes.
- ⚠️ CRITICAL: The section names below (CLAIM BAR, NAV, HERO, SOCIAL PROOF, SERVICES) are YOUR internal reference labels ONLY. NEVER output any of these words as visible text, headings, comments, <p> tags, <span> tags, or HTML comments on the page. A real website never labels its own sections.
- ⚠️ CONTRAST: Every text element MUST be readable against its background. Nav logo and links: if nav background is dark, text MUST be white (#fff) or very light. If nav background is light, text MUST be dark (#111 or #222). NEVER use the same color for text and its background. Hero text: always white (#fff) or off-white (#f5f5f5) on dark/gradient backgrounds. CTA buttons: text must contrast the button background — if button is light, text is dark; if button is dark, text is white.
{image_rule}

SECTIONS TO GENERATE (1–5 only):
1. CLAIM BAR: sticky top bar, black background. Centered single line: "This site was built for **{intel['business_name']}** by LVRG Agency" + gold "Claim This Site →" pill → {BOOKING_URL}
2. NAV: business name as logo, 3 nav links, primary CTA button
3. HERO: bold 5-8 word headline ("{intel.get('tagline','')}"), subheadline, 2 CTAs, {hero_bg_instruction}
4. SOCIAL PROOF BAR: real stats — {intel.get('social_proof', '3 key stats')}
5. SERVICES: 3 cards — {', '.join((intel.get('services') or [])[:3])}

End your response with exactly: <!-- CONTINUE -->"""


def _build_footer(intel: dict) -> str:
    """Build a data-rich HTML footer from intel — Python-generated so it always appears."""
    primary = intel.get('primary_color', '#1a1a2e')
    secondary = intel.get('secondary_color', '#c9a961')
    # If secondary is too light (e.g. #fff) it becomes invisible on dark footer — fall back to primary
    cta_bg = primary if _is_light_color(secondary) else secondary
    name = intel.get('business_name', '')
    location = intel.get('location', '')
    phone = intel.get('phone', '')
    email = intel.get('email', '')
    hours = intel.get('hours', '')
    cta = intel.get('cta_angle', 'Get in Touch')

    contact_items = []
    if location:
        contact_items.append(f'<div style="margin-bottom:10px;display:flex;gap:10px;align-items:flex-start;"><span style="opacity:0.6;">📍</span><span>{location}</span></div>')
    if phone:
        contact_items.append(f'<div style="margin-bottom:10px;"><a href="tel:{phone}" style="color:rgba(255,255,255,0.8);text-decoration:none;display:flex;gap:10px;align-items:center;"><span style="opacity:0.6;">📞</span><span>{phone}</span></a></div>')
    if email:
        contact_items.append(f'<div style="margin-bottom:10px;"><a href="mailto:{email}" style="color:rgba(255,255,255,0.8);text-decoration:none;display:flex;gap:10px;align-items:center;"><span style="opacity:0.6;">✉</span><span>{email}</span></a></div>')
    contact_html = '\n'.join(contact_items) if contact_items else '<div style="color:rgba(255,255,255,0.4);font-size:14px;">Contact us online</div>'

    hours_html = (
        f'<div style="color:rgba(255,255,255,0.8);font-size:14px;line-height:1.9;white-space:pre-line;">{hours}</div>'
        if hours else
        '<div style="color:rgba(255,255,255,0.4);font-size:14px;">Call for hours</div>'
    )

    desc = (intel.get('description') or '')[:160]

    return f"""<footer style="background:{primary};padding:64px 24px 0;margin-top:0;">
  <div style="max-width:1100px;margin:0 auto;display:flex;flex-wrap:wrap;gap:48px;padding-bottom:48px;border-bottom:1px solid rgba(255,255,255,0.1);">
    <div style="flex:2;min-width:220px;">
      <div style="font-size:22px;font-weight:700;color:#ffffff;margin-bottom:14px;letter-spacing:-0.3px;">{name}</div>
      <div style="font-size:14px;color:rgba(255,255,255,0.6);line-height:1.75;margin-bottom:28px;">{desc}</div>
      <a href="{BOOKING_URL}" style="display:inline-block;background:{cta_bg};color:#fff;padding:13px 26px;border-radius:10px;font-size:14px;font-weight:600;text-decoration:none;transition:all 0.2s ease;box-shadow:0 4px 16px rgba(0,0,0,0.25);" onmouseover="this.style.opacity='0.85';this.style.transform='translateY(-1px)'" onmouseout="this.style.opacity='1';this.style.transform='translateY(0)'">{cta} →</a>
    </div>
    <div style="flex:1;min-width:180px;">
      <div style="font-size:11px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:{secondary};margin-bottom:20px;">Contact</div>
      <div style="font-size:14px;color:rgba(255,255,255,0.8);line-height:1.9;">
        {contact_html}
      </div>
    </div>
    <div style="flex:1;min-width:180px;">
      <div style="font-size:11px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:{secondary};margin-bottom:20px;">Hours</div>
      {hours_html}
    </div>
  </div>
  <div style="max-width:1100px;margin:0 auto;padding:20px 0;display:flex;flex-wrap:wrap;gap:12px;align-items:center;justify-content:space-between;">
    <div style="font-size:13px;color:rgba(255,255,255,0.35);">© 2025 {name}. All rights reserved.</div>
    <div style="font-size:12px;color:rgba(255,255,255,0.25);">Smart Site by <a href="https://{SENDER_WEBSITE}" style="color:rgba(255,255,255,0.4);text-decoration:none;">LVRG Agency</a></div>
  </div>
</footer>"""


def _build_testimonials(intel: dict) -> str:
    """Build the testimonials section in Python from real Google reviews.

    Why this is Python-built (not Claude-generated): Pass 2 was hitting max_tokens
    mid-card and producing empty cards (just a star icon, no quote). Python
    templating guarantees every card renders fully and consistently.
    """
    primary = intel.get('primary_color', '#1a1a2e')
    secondary = intel.get('secondary_color', '#c9a961')
    accent = secondary if secondary and secondary.lower() not in ('#fff', '#ffffff', '#000', '#000000') else primary

    reviews = intel.get('reviews') or []
    real_reviews = [r for r in reviews if (r.get('text') or '').strip()][:3]
    if not real_reviews:
        return ''  # No reviews → skip section entirely

    def _star_svg(filled: bool) -> str:
        color = accent if filled else 'rgba(0,0,0,0.15)'
        return (
            f'<svg width="18" height="18" viewBox="0 0 24 24" fill="{color}" style="display:inline-block;">'
            '<path d="M12 2L15.09 8.26L22 9.27L17 14.14L18.18 21.02L12 17.77L5.82 21.02L7 14.14L2 9.27L8.91 8.26L12 2Z"/>'
            '</svg>'
        )

    def _initial(author: str) -> str:
        return (author or 'A').strip()[0].upper() if author else 'A'

    cards = []
    for r in real_reviews:
        rating = int(r.get('rating', 5))
        author = (r.get('author') or 'Anonymous').strip()
        time_ago = r.get('time_ago', '') or ''
        # Full review text — no truncation. Long reviews are visually clamped to ~6 lines
        # by default and expand on hover (handled by inline onmouseover/out below).
        text = (r.get('text') or '').strip().replace('"', '&quot;')
        stars = ''.join(_star_svg(i < rating) for i in range(5))

        # Visual clamp: max-height 168px (~6 lines at 1.65 line-height × 15px font),
        # gradient fade at bottom hints there's more text. On hover, max-height jumps
        # to 800px (effectively unlimited) and the fade disappears — card grows
        # naturally to fit the full quote.
        cards.append(f'''      <div style="background:#ffffff;border-radius:16px;padding:32px;flex:1 1 300px;max-width:380px;box-shadow:0 4px 24px rgba(0,0,0,0.08);transition:all 0.3s ease;display:flex;flex-direction:column;cursor:default;" onmouseover="this.style.transform='translateY(-4px)';this.style.boxShadow='0 12px 40px rgba(0,0,0,0.15)';var t=this.querySelector('[data-review-text]');if(t){{t.style.maxHeight='800px';var f=t.querySelector('[data-fade]');if(f)f.style.opacity='0';}}" onmouseout="this.style.transform='translateY(0)';this.style.boxShadow='0 4px 24px rgba(0,0,0,0.08)';var t=this.querySelector('[data-review-text]');if(t){{t.style.maxHeight='168px';var f=t.querySelector('[data-fade]');if(f)f.style.opacity='1';}}">
        <div style="display:flex;gap:3px;margin-bottom:16px;">{stars}</div>
        <div data-review-text style="position:relative;max-height:168px;overflow:hidden;transition:max-height 0.35s ease;margin:0 0 24px;flex:1;">
          <p style="color:#1a1a1a;font-size:15px;line-height:1.65;font-style:italic;margin:0;">"{text}"</p>
          <div data-fade style="position:absolute;bottom:0;left:0;right:0;height:48px;background:linear-gradient(to bottom, rgba(255,255,255,0), rgba(255,255,255,1));pointer-events:none;transition:opacity 0.25s ease;"></div>
        </div>
        <div style="display:flex;align-items:center;gap:12px;margin-top:auto;">
          <div style="width:42px;height:42px;border-radius:50%;background:{accent};color:#fff;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:16px;flex-shrink:0;">{_initial(author)}</div>
          <div>
            <div style="color:#1a1a1a;font-weight:600;font-size:14px;line-height:1.2;">{author}</div>
            <div style="color:#666;font-size:12px;margin-top:2px;">{time_ago}</div>
          </div>
        </div>
      </div>''')

    rating_avg = intel.get('google_rating', 0)
    total = intel.get('google_total_ratings', 0)
    rating_badge = ''
    if rating_avg and total:
        rating_badge = f'<div style="display:inline-flex;align-items:center;gap:8px;background:rgba(0,0,0,0.04);padding:8px 16px;border-radius:24px;margin-top:16px;font-size:13px;color:#666;"><span style="color:{accent};font-weight:700;">{rating_avg}★</span><span>{total} Google reviews</span></div>'

    return f'''<section style="background:#f8f9fb;padding:96px 24px;">
  <div style="max-width:1200px;margin:0 auto;">
    <div style="text-align:center;margin-bottom:56px;">
      <p style="color:{accent};font-weight:600;font-size:13px;letter-spacing:2px;text-transform:uppercase;margin-bottom:12px;">Loved by locals</p>
      <h2 style="font-size:clamp(32px,4.5vw,44px);font-weight:700;color:#1a1a1a;margin:0 0 8px;line-height:1.15;">What our customers are saying</h2>
      {rating_badge}
    </div>
    <div style="display:flex;gap:24px;flex-wrap:wrap;justify-content:center;align-items:stretch;">
{chr(10).join(cards)}
    </div>
  </div>
</section>
'''


def _build_part2_prompt(intel: dict) -> str:
    """Prompt for Call 2 — below-fold sections (testimonials + CTA). Footer is Python-generated."""
    city = intel.get('location', '').split(',')[0] if intel.get('location') else 'their city'
    primary = intel.get('primary_color', '#1a1a2e')
    secondary = intel.get('secondary_color', '#333')
    brand_vibe = intel.get('brand_vibe', 'clean, modern')

    raw_text = intel.get('raw_text', '') or ''
    content_notes = intel.get('content_notes') or ''

    return f"""Continue this HTML page. Generate ONLY the CTA banner section using the exact same design system, fonts, and inline-style patterns already established above.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PRIMARY COPY SOURCE — actual content from the prospect's website.
The CTA banner copy below MUST be lifted from this source. Do not invent.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{raw_text[:3500]}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

VERBATIM DETAILS (exact wording for menu, prices, awards): {content_notes if content_notes else 'None — rely on the primary copy source.'}

BRAND VARIABLES (must match Part 1 exactly — do not drift):
- Primary color: {primary}
- Secondary color: {secondary}
- Brand vibe: {brand_vibe}
- Use the same Google Font already loaded in <head>
- All background accents, button colors, and heading colors must use {primary} or {secondary} — never introduce new colors

⚠️ CRITICAL: NEVER output "CTA BANNER", "SECTION 7", or any numbered/named section label as visible text, headings, comments, or HTML comments. A real website never labels its own sections. The testimonials section is injected separately by LVRG — do NOT generate testimonials.

⚠️ CONTENT ACCURACY (same rules as Part 1):
- CTA banner headline: lift a real value proposition or claim from the PRIMARY COPY SOURCE above
- CTA banner subcopy: paraphrase one specific sentence from the source — keep their actual nouns and phrases
- Never invent: customer success stats, award names, certifications, founding year, or any benefit not present in the source
- NO em-dashes (—) in body copy — use commas instead. Em-dashes are an AI tell.
- NO section-label headings — use benefit-driven copy from the source instead (e.g. "Ready to drop in?", "Visit us today").

SECTION TO ADD (CTA banner only — testimonials and footer are injected separately, do NOT write either):
CTA BANNER: full-width section, bold headline, 1-2 sentences of copy, one large CTA button → {BOOKING_URL}. NO form, NO input fields, NO textarea — buttons and text only.

DESIGN RULES (same system as above):
- Buttons: border-radius 8–12px, padding 14px 28px, font-weight 600, transition:all 0.2s ease inline
- Cards: border-radius 12–16px, box-shadow 0 4px 24px rgba(0,0,0,0.08), padding 28px+
- Hover: inline onmouseover/onmouseout for transform:translateY(-2px) and shadow lift on every button and card
- Sections: 80px+ vertical padding, alternate background tints — no two plain white sections in a row
- ZERO dividers — no <hr>, no border-top, no border-bottom between sections. Background color changes only.
- CONTRAST: all text must be readable — white text on dark backgrounds, dark text on light backgrounds. Never same color for text and background.

COPY RULES:
- Reference {city} naturally in copy
- Every CTA drives toward: {intel.get('cta_angle', 'booking a visit')}
- Pain point to address: {intel.get('pain_point', '')}
- Real business details to use verbatim (menu items, pricing, named services, awards): {intel.get('content_notes') or 'Use general copy based on business type'}
- Use same inline style= attribute patterns as the sections above

Do NOT add any chat bubble, floating button, fixed-position widget, or footer — LVRG injects all of these.
Do NOT write </body> or </html>. Output HTML only — no explanation, no markdown fences."""


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


def _close_unclosed_elements(html: str) -> str:
    """Close any block-level elements that Claude left open — prevents injected HTML from
    appearing as visible text inside a <textarea> or <select>.
    Used as a fast pre-check; _repair_html_structure does the deeper work via html5lib."""
    import re
    for tag in ('textarea', 'select', 'script', 'style'):
        opens = len(re.findall(fr'<{tag}[\s>]', html, re.IGNORECASE))
        closes = len(re.findall(fr'</{tag}>', html, re.IGNORECASE))
        for _ in range(max(0, opens - closes)):
            html += f'</{tag}>\n'
    return html


def _repair_html_structure(html: str) -> str:
    """Parse Claude's HTML with a browser-grade parser (html5lib) and re-emit valid HTML.

    Why this is needed: Claude often leaves <div>, <section>, or <a> elements unclosed,
    especially across the Part 1 / Part 2 stitch. When unclosed containers exist, our
    Python-injected footer + chat widget end up rendered INSIDE those containers, breaking
    the layout (e.g. footer appears inside a service card's grid cell).

    html5lib mimics a real browser's parser — it correctly closes implicit and missing tags
    and produces a well-formed tree, so when we serialize back the structure is valid.
    """
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html5lib')
        body = soup.body
        head = soup.head
        if body is None or head is None:
            return html  # Bail safely if parser couldn't find the structure
        head_html = ''.join(str(c) for c in head.contents)
        body_html = ''.join(str(c) for c in body.contents)
        # Preserve original DOCTYPE / html lang
        doctype = '<!DOCTYPE html>'
        html_attrs = ''
        if soup.html and soup.html.attrs:
            html_attrs = ''.join(f' {k}="{v}"' for k, v in soup.html.attrs.items())
        return f"{doctype}\n<html{html_attrs}>\n<head>{head_html}</head>\n<body>{body_html}</body>\n</html>"
    except Exception as e:
        print(f"  [generator] HTML repair skipped: {e}")
        return html


def _clean_html(html: str) -> str:
    """Post-process Claude's HTML to fix common generation artifacts."""
    import re

    # SVG data URLs inside inline style= attributes contain unencoded " chars which break the
    # HTML attribute boundary and cause raw CSS/text to leak into the visible page.
    # Fix: encode " inside url('data:image/svg+xml,...') with %22.
    def _encode_svg_data_url(m: 're.Match') -> str:
        prefix = "url('data:image/svg+xml,"
        suffix = "')"
        inner = m.group(0)[len(prefix):-len(suffix)]
        return prefix + inner.replace('"', '%22') + suffix
    html = re.sub(r"url\('data:image/svg\+xml,[^']*'\)", _encode_svg_data_url, html)

    # Strip any element that renders ONLY a section-label word Claude leaked as visible text.
    # These are internal prompt labels — they should never appear on the page.
    _SECTION_LABELS = {
        "CLAIM BAR", "NAVIGATION", "NAV", "HERO SECTION", "HERO",
        "SOCIAL PROOF", "SOCIAL PROOF BAR", "SERVICES", "SERVICES SECTION",
        "ABOUT", "ABOUT US", "ABOUT SECTION", "FEATURES", "FEATURES SECTION",
        "TESTIMONIALS", "TESTIMONIALS SECTION", "REVIEWS SECTION",
        "CTA", "CTA BANNER", "CTA SECTION", "FOOTER", "FOOTER SECTION",
        "MENU", "MENU SECTION", "PRICING", "PRICING SECTION",
        "GALLERY", "GALLERY SECTION", "CONTACT", "CONTACT SECTION",
        "ABOVE FOLD", "BELOW FOLD",
    }
    # Words that, when followed by " SECTION", become a label even if not in the explicit set.
    _GENERIC_SECTION_WORDS = {
        "SERVICES", "ABOUT", "FEATURES", "TESTIMONIALS", "REVIEWS", "MENU",
        "PRICING", "GALLERY", "CONTACT", "CTA", "HERO", "FOOTER", "TEAM",
        "FAQ", "PROCESS", "BENEFITS", "STATS", "BANNER", "PRODUCTS",
    }

    def _is_label_text(text: str) -> bool:
        """Return True if text is purely a section label."""
        t = text.strip().upper().rstrip(":-–—")
        t = t.strip()
        # Direct match
        if t in _SECTION_LABELS:
            return True
        # "SECTION N: LABEL" prefix
        t_stripped = re.sub(r'^SECTION\s*\d+\s*[:\-–]?\s*', '', t).strip()
        if t_stripped in _SECTION_LABELS:
            return True
        # Bare "SECTION N" or "SECTION N:"
        if re.match(r'^SECTION\s*\d+\s*[:\-–]?\s*$', t):
            return True
        # Generic "X SECTION" / "X BANNER" pattern — e.g. "FEATURES SECTION", "ABOUT SECTION"
        m = re.match(r'^([A-Z][A-Z\s]{1,30}?)\s+(SECTION|BANNER|BAR)$', t)
        if m and m.group(1).strip() in _GENERIC_SECTION_WORDS:
            return True
        # "SECTION X" prefix on its own
        m = re.match(r'^SECTION\s+([A-Z][A-Z\s]{1,30})$', t)
        if m and m.group(1).strip() in _GENERIC_SECTION_WORDS:
            return True
        return False

    # Match elements whose content is ONLY a section-label word (no nested tags).
    # Using [^<]{0,120} ensures we never eat elements that contain real nested HTML.
    def _strip_label_element(m: 're.Match') -> str:
        if _is_label_text(m.group(2)):
            return ''
        return m.group(0)
    html = re.sub(
        r'(<(?:p|span|div|h[1-6]|label|header)[^>]*>)([^<]{0,120})(</(?:p|span|div|h[1-6]|label|header)>)',
        _strip_label_element,
        html,
        flags=re.IGNORECASE,
    )

    # Also strip bare HTML comments that are just section labels, e.g. <!-- SECTION 7: CTA BANNER -->
    def _strip_label_comment(m: 're.Match') -> str:
        if _is_label_text(m.group(1)):
            return ''
        return m.group(0)
    html = re.sub(r'<!--(.*?)-->', _strip_label_comment, html, flags=re.DOTALL)

    # Strip all <hr> tags — no horizontal rules anywhere on the page
    html = re.sub(r'<hr\s*/?>', '', html, flags=re.IGNORECASE)

    # Replace em-dashes (—) in body copy with commas — these are an LLM tell.
    # We only target em-dashes (U+2014), NOT en-dashes (U+2013) which are legitimate for
    # hours/day ranges ("Mon – Fri", "9am – 5pm"). We protect <script> / <style> blocks
    # so JS string literals and CSS values aren't touched.
    def _replace_em_dashes(html_str: str) -> str:
        placeholders: list[str] = []
        def _stash(m):
            placeholders.append(m.group(0))
            return f"\x00PH{len(placeholders)-1}\x00"
        protected = re.sub(r'<(script|style)\b[^>]*>.*?</\1>', _stash, html_str,
                           flags=re.IGNORECASE | re.DOTALL)
        # " — " with letters on both sides → ", "  (the marketing-copy idiom)
        protected = re.sub(r'(?<=[A-Za-z])\s*—\s*(?=[A-Za-z])', ', ', protected)
        for i, ph in enumerate(placeholders):
            protected = protected.replace(f"\x00PH{i}\x00", ph, 1)
        return protected
    html = _replace_em_dashes(html)

    return html


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

    # Build testimonials in Python (always renders fully — no token-limit truncation).
    # Inject between Part 1 (services) and Part 2 (CTA banner) so flow is:
    # claim bar → nav → hero → social proof → services → testimonials → CTA → footer.
    testimonials_html = _build_testimonials(intel)
    part1_with_testimonials = part1_prefill + "\n" + testimonials_html if testimonials_html else part1_prefill

    # Anthropic requires the prefilled assistant content to NOT end with whitespace.
    prefill_for_api = part1_with_testimonials.rstrip()

    # ── Pass 2: CTA banner only (testimonials + footer are Python-built) ──
    print(f"  [generator] Pass 2/2 — CTA banner...")
    resp2 = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=3000,  # Reduced — only CTA banner now, no testimonials
        messages=[
            {"role": "user", "content": _build_part2_prompt(intel)},
            {"role": "assistant", "content": prefill_for_api},
        ]
    )
    part2 = _strip_fences(resp2.content[0].text)

    # Stitch: Part 1 + Python testimonials + Part 2 CTA
    stitched = part1_with_testimonials + "\n" + part2

    # Pre-clean: fix SVG data URL escaping that breaks attribute quoting
    stitched = _clean_html(stitched)

    # Pre-close obvious unclosed inline elements (cheap pass before parser)
    stitched = _close_unclosed_elements(stitched)

    # Repair HTML structure with browser-grade parser. This is the critical step:
    # html5lib auto-closes any unclosed <div>, <section>, <a>, <button>, etc., so the
    # subsequent footer + widget injection lands at the body level — not inside an
    # accidentally-still-open services card or testimonials grid.
    repaired = _repair_html_structure(stitched)

    # Inject footer + chat widget right before </body> on the repaired tree
    footer_html = _build_footer(intel)
    widget_html = _build_chat_widget(intel)
    injection = "\n" + footer_html + "\n" + widget_html + "\n"
    if '</body>' in repaired:
        html = repaired.replace('</body>', injection + '</body>', 1)
    else:
        html = repaired.rstrip() + injection + "</body>\n</html>"

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
