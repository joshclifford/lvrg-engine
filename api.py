"""
LVRG Engine — FastAPI Server
Wraps the engine pipeline as an HTTP API with SSE streaming.
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# Engine modules
from intel import scrape_site, grade_site
from generator import generate_site, generate_email
from deploy import deploy_site
from supabase_client import upsert_lead, log_event

app = FastAPI(title="LVRG Engine API", version="1.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class BuildRequest(BaseModel):
    domain: str
    no_deploy: bool = False
    offer: str = "Smart Site"
    cta: str = "Book a Call"
    notes: str = ""


class ChatRequest(BaseModel):
    message: str
    business_name: str
    intel: dict  # full intel object baked into each widget
    history: list = []  # [{"role": "user"|"assistant", "content": "..."}]


def sse(type: str, **kwargs) -> str:
    return f"data: {json.dumps({'type': type, **kwargs})}\n\n"


async def run_pipeline(domain: str, no_deploy: bool, offer: str, cta: str, notes: str = "") -> AsyncGenerator[str, None]:
    """Run the full engine pipeline, yielding SSE events."""

    loop = asyncio.get_event_loop()

    def emit(type: str, **kwargs):
        # Returns the SSE string — we collect and yield from outside
        pass

    logs = []

    def log(text: str, level: str = "info"):
        line = sse("log", text=text, level=level)
        logs.append(line)

    try:
        # ── Step 1: Intel ────────────────────────────────────────────
        yield sse("log", text=f"Reading {domain}...", level="info")
        intel = await loop.run_in_executor(None, scrape_site, domain)
        yield sse("log", text=f"Got intel for {intel['business_name']}", level="success")
        yield sse("intel", data=intel)

        # ── Step 2: Grade ────────────────────────────────────────────
        yield sse("log", text="Grading site...", level="info")
        grade = await loop.run_in_executor(None, grade_site, intel)
        yield sse("log", text=f"Score: {grade['total']}/10 — {grade['verdict']}", level="success")
        yield sse("grade", data=grade)

        if not grade["worth_targeting"]:
            yield sse("log", text=f"Score {grade['total']}/10 — noted, building anyway", level="info")

        # ── Step 3: Generate site ────────────────────────────────────
        from slugify import slugify
        prospect_id = slugify(domain.split(".")[0]) or slugify(domain.replace(".", "-"))

        yield sse("log", text="Generating Smart Site with Claude...", level="info")
        if notes:
            yield sse("log", text=f"Notes: {notes}", level="info")
        site_dir = await loop.run_in_executor(None, generate_site, intel, prospect_id, notes)
        yield sse("log", text="Site generated", level="success")

        # ── Step 4: Deploy ───────────────────────────────────────────
        preview_url = None
        if not no_deploy:
            yield sse("log", text="Deploying to GitHub Pages...", level="info")
            try:
                preview_url = await loop.run_in_executor(None, deploy_site, prospect_id, site_dir)
                yield sse("log", text=f"Live at {preview_url}", level="success")
            except Exception as e:
                yield sse("log", text=f"Deploy failed: {e} — continuing", level="error")
                preview_url = None
        else:
            preview_url = f"[local] {site_dir}/index.html"

        # ── Step 5: Generate email ───────────────────────────────────
        yield sse("log", text="Writing outreach messaging...", level="info")
        email_data = await loop.run_in_executor(None, generate_email, intel, grade, prospect_id)
        yield sse("log", text="Messaging ready", level="success")

        # ── Step 6: Save to Supabase ─────────────────────────────────
        yield sse("log", text="Saving to Supabase...", level="info")
        try:
            sb_lead = await loop.run_in_executor(
                None,
                lambda: upsert_lead(
                    domain=domain,
                    intel=intel,
                    grade=grade,
                    preview_url=preview_url,
                    email_data=email_data,
                    instantly_lead_id=None,
                    instantly_campaign_id=None,
                    offer=offer,
                    cta=cta,
                    status="built",
                )
            )
            if sb_lead:
                await loop.run_in_executor(
                    None,
                    lambda: log_event(sb_lead["id"], "site_built", {
                        "preview_url": preview_url,
                        "score": grade.get("total"),
                    })
                )
        except Exception as e:
            yield sse("log", text=f"Supabase save failed: {e}", level="error")

        # ── Done ─────────────────────────────────────────────────────
        yield sse("result", payload={
            "preview_url": preview_url,
            "email": email_data,
            "intel": intel,
            "grade": grade,
        })
        yield sse("done", status="complete")

    except Exception as e:
        yield sse("log", text=f"Pipeline error: {e}", level="error")
        yield sse("error", text=str(e))
        yield sse("done", status="error")


@app.post("/build")
async def build(req: BuildRequest):
    """Run the full engine pipeline for a domain. Returns SSE stream."""
    domain = req.domain.strip().lower()
    domain = domain.replace("https://", "").replace("http://", "")
    domain = domain.split("/")[0].split("?")[0].strip()
    if not domain:
        raise HTTPException(status_code=400, detail="domain is required")

    return StreamingResponse(
        run_pipeline(domain, req.no_deploy, req.offer, req.cta, req.notes),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/chat")
async def chat(req: ChatRequest):
    """AI chat endpoint for Smart Site widgets. Responds as the business."""
    import anthropic
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    client = anthropic.Anthropic(api_key=key)

    # Build system prompt from scraped intel
    intel = req.intel
    system = f"""You are the AI assistant for {intel.get('business_name', 'this business')}.
Answer questions warmly and helpfully as a knowledgeable team member.
Keep responses concise — 1-3 sentences. Never say you are an AI unless directly asked.

BUSINESS DETAILS:
- Name: {intel.get('business_name', '')}
- Description: {intel.get('description', '')}
- Services: {', '.join(intel.get('services') or [])}
- Location: {intel.get('location', '')}
- Phone: {intel.get('phone', '')}
- Hours: {intel.get('hours', '')}
- Social proof: {intel.get('social_proof', '')}
- Main CTA: {intel.get('cta_angle', 'contact us')}

If asked about booking, reservations, or appointments, direct them to call or visit.
If you don't know something specific, say you'll have the team follow up."""

    messages = req.history[-10:] + [{"role": "user", "content": req.message}]

    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=300,
        system=system,
        messages=messages,
    )

    return {"reply": response.content[0].text.strip()}


@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.1.0"}


@app.get("/")
async def root():
    return {"service": "LVRG Engine API", "endpoints": ["/build", "/health"]}
