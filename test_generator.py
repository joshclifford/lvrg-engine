"""
Tests for generator.py — 2-pass site generation.

Tests are split into:
  - TestPart1Prompt     : _build_part1_prompt content (no Claude call needed)
  - TestPart2Prompt     : _build_part2_prompt content (no Claude call needed)
  - TestStripFences     : _strip_fences helper
  - TestTwoCallBehavior : generate_site makes 2 calls, prefills correctly, stitches output
  - TestHeroImage       : image/gradient rules flow through to the part1 prompt
  - TestRegression      : key sections still present, nothing broken

Run:
    pytest test_generator.py -v
"""
import pytest
from unittest.mock import patch, MagicMock, mock_open, call

from generator import _build_part1_prompt, _build_part2_prompt, _strip_fences, _is_image_reachable
from config import BOOKING_URL


# ─── Shared fixtures ──────────────────────────────────────────────────────────

INTEL = {
    "domain": "testbistro.com",
    "business_name": "Test Bistro",
    "description": "A great restaurant in San Diego",
    "services": ["Dining", "Catering", "Private Events"],
    "location": "Gaslamp, San Diego, CA",
    "phone": "619-555-0000",
    "hours": "Mon-Sun 11am-10pm",
    "social_proof": "Best of SD 2023, 500+ reviews",
    "brand_vibe": "warm and modern",
    "primary_color": "#1a1a2e",
    "secondary_color": "#c9a961",
    "business_type": "restaurant",
    "missing": "no chat widget, no online booking",
    "key_cta": "Reserve a Table",
    "tagline": "Fresh food, great vibes",
    "pain_point": "No online booking",
    "chat_persona": "Friendly host",
    "cta_angle": "Reserve a Table",
    "owner_name": "",
    "neighborhood": "Gaslamp",
    "images": [],
    "raw_text": "Great restaurant in the Gaslamp Quarter.",
}

PART1_HTML = (
    "<!DOCTYPE html><html><head><style>*{margin:0}</style></head>"
    "<body>\n<div>CLAIM BAR</div><nav>NAV</nav>"
    "<section>HERO</section><section>SOCIAL PROOF</section>"
    "<section>SERVICES</section>\n<!-- CONTINUE -->"
)
PART2_HTML = (
    "<section>TESTIMONIALS</section>"
    "<section>CTA BANNER</section>"
    "<footer>FOOTER</footer>\n</body></html>"
)


def _run(intel_override=None, part1=PART1_HTML, part2=PART2_HTML, image_reachable=True):
    """
    Run generate_site with mocked Claude + filesystem.
    Returns (create_calls, written_html).
    image_reachable: bool or callable(url) -> bool passed to _is_image_reachable mock.
    """
    intel = {**INTEL, **(intel_override or {})}

    msg1 = MagicMock()
    msg1.content = [MagicMock(text=part1)]
    msg2 = MagicMock()
    msg2.content = [MagicMock(text=part2)]

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = [msg1, msg2]

    written = []
    mo = mock_open()
    mo.return_value.__enter__.return_value.write.side_effect = lambda x: written.append(x)

    reach_kwargs = (
        {"side_effect": image_reachable}
        if callable(image_reachable)
        else {"return_value": image_reachable}
    )

    with patch("anthropic.Anthropic", return_value=mock_client), \
         patch("generator._is_image_reachable", **reach_kwargs), \
         patch("os.makedirs"), \
         patch("builtins.open", mo):
        from generator import generate_site
        generate_site(intel, "test-bistro")

    return mock_client.messages.create.call_args_list, "".join(written)


# ─── _strip_fences ────────────────────────────────────────────────────────────

class TestStripFences:

    def test_plain_html_unchanged(self):
        html = "<!DOCTYPE html><html></html>"
        assert _strip_fences(html) == html

    def test_strips_generic_fence(self):
        raw = "```\n<!DOCTYPE html>\n```"
        assert _strip_fences(raw) == "<!DOCTYPE html>"

    def test_strips_html_fence(self):
        raw = "```html\n<!DOCTYPE html>\n```"
        assert _strip_fences(raw) == "<!DOCTYPE html>"

    def test_strips_leading_trailing_whitespace(self):
        assert _strip_fences("  hello  ") == "hello"


# ─── _build_part1_prompt ──────────────────────────────────────────────────────

class TestPart1Prompt:

    def _prompt(self, image_rule="- no images", hero_bg="gradient"):
        return _build_part1_prompt(INTEL, "", hero_bg, image_rule)

    def test_contains_claim_bar(self):
        assert "CLAIM BAR" in self._prompt()

    def test_contains_nav(self):
        assert "NAV" in self._prompt()

    def test_contains_hero(self):
        assert "HERO" in self._prompt()

    def test_contains_social_proof(self):
        assert "SOCIAL PROOF" in self._prompt()

    def test_contains_services(self):
        assert "SERVICES" in self._prompt()

    def test_does_not_contain_testimonials(self):
        assert "TESTIMONIALS" not in self._prompt()

    def test_does_not_contain_cta_banner(self):
        assert "CTA BANNER" not in self._prompt()

    def test_does_not_contain_footer_section(self):
        assert "FOOTER" not in self._prompt()

    def test_instructs_to_end_with_continue_marker(self):
        assert "<!-- CONTINUE -->" in self._prompt()

    def test_instructs_not_to_close_body(self):
        prompt = self._prompt()
        assert "Do NOT write </body>" in prompt

    def test_booking_url_present(self):
        assert BOOKING_URL in self._prompt()

    def test_business_name_present(self):
        assert "Test Bistro" in self._prompt()

    def test_primary_color_present(self):
        assert "#1a1a2e" in self._prompt()

    def test_secondary_color_present(self):
        assert "#c9a961" in self._prompt()

    def test_services_listed(self):
        prompt = self._prompt()
        assert "Dining" in prompt

    def test_image_rule_injected(self):
        prompt = _build_part1_prompt(INTEL, "", "gradient", "- NO external image URLs")
        assert "NO external image URLs" in prompt

    def test_hero_bg_instruction_injected(self):
        prompt = _build_part1_prompt(INTEL, "", "background: linear-gradient(red,blue)", "- no images")
        assert "linear-gradient(red,blue)" in prompt

    def test_notes_block_injected_when_present(self):
        prompt = _build_part1_prompt(INTEL, "\n\nSPECIAL: Use blue everywhere\n", "g", "r")
        assert "SPECIAL: Use blue everywhere" in prompt

    def test_no_notes_block_when_empty(self):
        prompt = self._prompt()
        assert "SPECIAL INSTRUCTIONS" not in prompt


# ─── _build_part2_prompt ──────────────────────────────────────────────────────

class TestPart2Prompt:

    def _prompt(self):
        return _build_part2_prompt(INTEL)

    def test_contains_testimonials(self):
        assert "TESTIMONIALS" in self._prompt()

    def test_contains_cta_banner(self):
        assert "CTA BANNER" in self._prompt()

    def test_contains_footer(self):
        assert "FOOTER" in self._prompt()

    def test_does_not_contain_claim_bar(self):
        assert "CLAIM BAR" not in self._prompt()

    def test_does_not_contain_hero(self):
        assert "HERO" not in self._prompt()

    def test_instructs_to_close_body_html(self):
        assert "</body></html>" in self._prompt()

    def test_social_proof_referenced(self):
        assert "Best of SD 2023" in self._prompt()

    def test_cta_angle_referenced(self):
        assert "Reserve a Table" in self._prompt()

    def test_city_extracted_from_location(self):
        assert "Gaslamp" in self._prompt()

    def test_pain_point_referenced(self):
        assert "No online booking" in self._prompt()

    def test_phone_in_footer_spec(self):
        assert "619-555-0000" in self._prompt()

    # B21 — brand variables re-injected
    def test_primary_color_in_part2_prompt(self):
        assert "#1a1a2e" in self._prompt()

    def test_secondary_color_in_part2_prompt(self):
        assert "#c9a961" in self._prompt()

    def test_brand_vibe_in_part2_prompt(self):
        assert "warm and modern" in self._prompt()

    def test_no_new_colors_instruction_in_part2_prompt(self):
        assert "never introduce new colors" in self._prompt()

    def test_same_google_font_instruction_in_part2_prompt(self):
        assert "same Google Font" in self._prompt()

    def test_different_primary_color_reflected_in_part2_prompt(self):
        intel = {**INTEL, "primary_color": "#ff0000"}
        prompt = _build_part2_prompt(intel)
        assert "#ff0000" in prompt

    def test_different_secondary_color_reflected_in_part2_prompt(self):
        intel = {**INTEL, "secondary_color": "#00ff00"}
        prompt = _build_part2_prompt(intel)
        assert "#00ff00" in prompt


# ─── Two-call behavior ────────────────────────────────────────────────────────

class TestTwoCallBehavior:

    def test_exactly_two_claude_calls(self):
        calls, _ = _run()
        assert len(calls) == 2

    def test_call1_max_tokens_is_6000(self):
        calls, _ = _run()
        assert calls[0][1]["max_tokens"] == 6000

    def test_call2_max_tokens_is_6000(self):
        calls, _ = _run()
        assert calls[1][1]["max_tokens"] == 6000

    def test_call2_has_assistant_prefill(self):
        calls, _ = _run()
        msgs = calls[1][1]["messages"]
        roles = [m["role"] for m in msgs]
        assert "assistant" in roles

    def test_call2_prefill_contains_part1_content(self):
        calls, _ = _run()
        msgs = calls[1][1]["messages"]
        assistant_content = next(m["content"] for m in msgs if m["role"] == "assistant")
        assert "CLAIM BAR" in assistant_content

    def test_continue_marker_stripped_from_prefill(self):
        calls, _ = _run()
        msgs = calls[1][1]["messages"]
        assistant_content = next(m["content"] for m in msgs if m["role"] == "assistant")
        assert "<!-- CONTINUE -->" not in assistant_content

    def test_continue_marker_not_in_final_html(self):
        _, html = _run()
        assert "<!-- CONTINUE -->" not in html

    def test_both_parts_stitched_in_output(self):
        _, html = _run()
        assert "SERVICES" in html       # from part1
        assert "TESTIMONIALS" in html   # from part2

    def test_final_html_closes_with_html_tag(self):
        _, html = _run()
        assert "</html>" in html

    def test_chat_widget_injected_before_body_close(self):
        _, html = _run()
        assert "lvrg-chat" in html
        assert html.index("lvrg-chat") < html.index("</body>")

    def test_part1_without_continue_marker_still_works(self):
        part1_no_marker = PART1_HTML.replace("<!-- CONTINUE -->", "")
        calls, html = _run(part1=part1_no_marker)
        assert len(calls) == 2
        assert "TESTIMONIALS" in html

    def test_truncated_part2_gets_html_closed(self):
        truncated_part2 = "<section>TESTIMONIALS</section>"  # no </body></html>
        _, html = _run(part2=truncated_part2)
        assert "</html>" in html


# ─── Hero image — flows through to Call 1 prompt ─────────────────────────────

class TestHeroImage:

    def test_real_image_url_in_call1_prompt(self):
        calls, _ = _run({"images": ["https://testbistro.com/hero.jpg"]})
        prompt = calls[0][1]["messages"][0]["content"]
        assert "https://testbistro.com/hero.jpg" in prompt

    def test_dark_overlay_in_call1_prompt_when_image_present(self):
        calls, _ = _run({"images": ["https://testbistro.com/hero.jpg"]})
        prompt = calls[0][1]["messages"][0]["content"]
        assert "rgba(0,0,0" in prompt

    def test_gradient_fallback_present_even_with_image(self):
        calls, _ = _run({"images": ["https://testbistro.com/hero.jpg"]})
        prompt = calls[0][1]["messages"][0]["content"]
        assert "linear-gradient" in prompt

    def test_no_external_url_in_prompt_when_no_images(self):
        calls, _ = _run({"images": []})
        prompt = calls[0][1]["messages"][0]["content"]
        assert "url('http" not in prompt

    def test_restriction_message_when_no_images(self):
        calls, _ = _run({"images": []})
        prompt = calls[0][1]["messages"][0]["content"]
        assert "NO external image URLs" in prompt

    def test_no_restriction_message_when_image_present(self):
        calls, _ = _run({"images": ["https://testbistro.com/hero.jpg"]})
        prompt = calls[0][1]["messages"][0]["content"]
        assert "NO external image URLs" not in prompt

    def test_uses_first_image_only(self):
        calls, _ = _run({"images": [
            "https://testbistro.com/hero1.jpg",
            "https://testbistro.com/hero2.jpg",
        ]})
        prompt = calls[0][1]["messages"][0]["content"]
        assert "https://testbistro.com/hero1.jpg" in prompt

    def test_missing_images_key_treated_as_no_images(self):
        intel = {k: v for k, v in INTEL.items() if k != "images"}
        calls, _ = _run(intel_override=intel)
        prompt = calls[0][1]["messages"][0]["content"]
        assert "NO external image URLs" in prompt


# ─── Regression — nothing broken ─────────────────────────────────────────────

class TestRegression:

    def test_booking_url_in_call1_prompt(self):
        calls, _ = _run()
        assert BOOKING_URL in calls[0][1]["messages"][0]["content"]

    def test_business_name_in_call1_prompt(self):
        calls, _ = _run()
        assert "Test Bistro" in calls[0][1]["messages"][0]["content"]

    def test_services_in_call1_prompt(self):
        calls, _ = _run()
        assert "Dining" in calls[0][1]["messages"][0]["content"]

    def test_social_proof_in_call2_prompt(self):
        calls, _ = _run()
        assert "Best of SD 2023" in calls[1][1]["messages"][0]["content"]

    def test_model_is_claude_opus(self):
        calls, _ = _run()
        assert calls[0][1]["model"] == "claude-opus-4-5"
        assert calls[1][1]["model"] == "claude-opus-4-5"


# ─── Location handling ────────────────────────────────────────────────────────

class TestLocationHandling:

    def test_real_location_passed_to_part1_prompt(self):
        prompt = _build_part1_prompt(INTEL, "", "gradient", "no images")
        assert "Gaslamp, San Diego, CA" in prompt

    def test_empty_location_shows_not_found_in_part1_prompt(self):
        intel = {**INTEL, "location": ""}
        prompt = _build_part1_prompt(intel, "", "gradient", "no images")
        assert "Not found" in prompt
        assert "do not invent" in prompt

    def test_empty_location_uses_their_city_fallback_in_part2_prompt(self):
        intel = {**INTEL, "location": ""}
        prompt = _build_part2_prompt(intel)
        assert "their city" in prompt

    def test_real_location_city_extracted_for_part2_copy_rules(self):
        prompt = _build_part2_prompt(INTEL)
        assert "Gaslamp" in prompt

    def test_empty_location_no_san_diego_invented_in_part1(self):
        intel = {**INTEL, "location": ""}
        prompt = _build_part1_prompt(intel, "", "gradient", "no images")
        assert "San Diego, CA" not in prompt

    def test_non_sd_location_preserved_in_part1_prompt(self):
        intel = {**INTEL, "location": "Austin, TX"}
        prompt = _build_part1_prompt(intel, "", "gradient", "no images")
        assert "Austin, TX" in prompt


# ─── Chat widget endpoint — CHAT_ENDPOINT env var ─────────────────────────────

class TestChatWidgetEndpoint:

    def test_default_endpoint_is_prod_railway_url(self):
        _, html = _run()
        assert "lvrg-engine-production.up.railway.app/chat" in html

    def test_chat_endpoint_env_var_overrides_default(self):
        with patch.dict("os.environ", {"CHAT_ENDPOINT": "http://localhost:8766/chat"}):
            _, html = _run()
        assert "http://localhost:8766/chat" in html

    def test_custom_endpoint_replaces_prod_url(self):
        with patch.dict("os.environ", {"CHAT_ENDPOINT": "http://localhost:8766/chat"}):
            _, html = _run()
        assert "lvrg-engine-production.up.railway.app" not in html

    def test_endpoint_is_in_widget_js(self):
        _, html = _run()
        assert "_lvrgEndpoint" in html

    def test_env_var_empty_string_falls_back_to_default(self):
        with patch.dict("os.environ", {"CHAT_ENDPOINT": ""}):
            _, html = _run()
        assert "lvrg-engine-production.up.railway.app/chat" in html


# ─── B15: Chat outside-click + Escape close ───────────────────────────────────

class TestChatOutsideClick:

    def test_document_click_listener_present(self):
        _, html = _run()
        assert "document.addEventListener('click'" in html

    def test_document_keydown_listener_present(self):
        _, html = _run()
        assert "document.addEventListener('keydown'" in html

    def test_escape_key_closes_panel(self):
        _, html = _run()
        assert "e.key==='Escape'" in html
        assert "lvrgClose()" in html

    def test_outside_click_calls_lvrgClose(self):
        _, html = _run()
        assert "!w.contains(e.target)" in html

    def test_lvrg_close_function_defined(self):
        _, html = _run()
        assert "function lvrgClose()" in html

    def test_lvrg_open_function_defined(self):
        _, html = _run()
        assert "function lvrgOpen()" in html

    def test_outside_click_checks_lvrg_chat_container(self):
        _, html = _run()
        assert "getElementById('lvrg-chat')" in html


# ─── B16: CSS isolation — scoped reset ────────────────────────────────────────

class TestChatCSSIsolation:

    def test_scoped_style_block_present(self):
        _, html = _run()
        assert "<style>#lvrg-chat" in html

    def test_all_initial_applied_to_widget_and_children(self):
        _, html = _run()
        assert "all:initial" in html

    def test_box_sizing_reset_present(self):
        _, html = _run()
        assert "box-sizing:border-box" in html

    def test_scoped_style_targets_lvrg_chat_star(self):
        _, html = _run()
        assert "#lvrg-chat,#lvrg-chat *" in html

    def test_scoped_style_appears_before_widget_div(self):
        _, html = _run()
        assert html.index("<style>#lvrg-chat") < html.index('<div id="lvrg-chat"')

    def test_system_font_stack_on_container(self):
        _, html = _run()
        assert "BlinkMacSystemFont" in html


# ─── B17: No duplicate chat widget — prompt instruction ───────────────────────

class TestNoDuplicateChatPrompt:

    def test_part1_prompt_forbids_chat_widget(self):
        prompt = _build_part1_prompt(INTEL, "", "gradient", "- no images")
        assert "LVRG injects its own chat widget" in prompt

    def test_part2_prompt_forbids_chat_widget(self):
        prompt = _build_part2_prompt(INTEL)
        assert "LVRG injects its own" in prompt

    def test_part1_prompt_forbids_floating_button(self):
        prompt = _build_part1_prompt(INTEL, "", "gradient", "- no images")
        assert "floating button" in prompt

    def test_part2_prompt_forbids_floating_button(self):
        prompt = _build_part2_prompt(INTEL)
        assert "floating button" in prompt


# ─── B18: UI quality — radius, hover, transitions in prompts ─────────────────

class TestUIQualityPrompt:

    def _p1(self):
        return _build_part1_prompt(INTEL, "", "gradient", "- no images")

    def _p2(self):
        return _build_part2_prompt(INTEL)

    # Part 1
    def test_p1_button_border_radius_instruction(self):
        assert "border-radius 8" in self._p1()

    def test_p1_card_border_radius_instruction(self):
        assert "border-radius 12" in self._p1()

    def test_p1_hover_onmouseover_instruction(self):
        assert "onmouseover" in self._p1()

    def test_p1_transition_instruction(self):
        assert "transition:all 0.2s ease" in self._p1()

    def test_p1_section_padding_instruction(self):
        assert "80px" in self._p1()

    def test_p1_card_box_shadow_instruction(self):
        assert "box-shadow" in self._p1()

    # Part 2 — same design rules repeated
    def test_p2_button_border_radius_instruction(self):
        assert "border-radius 8" in self._p2()

    def test_p2_card_border_radius_instruction(self):
        assert "border-radius 12" in self._p2()

    def test_p2_hover_onmouseover_instruction(self):
        assert "onmouseover" in self._p2()

    def test_p2_transition_instruction(self):
        assert "transition:all 0.2s ease" in self._p2()


# ─── B19: Image reachability — HEAD check + fallback ─────────────────────────

class TestIsImageReachable:

    def _mock_resp(self, status: int):
        resp = MagicMock()
        resp.status = status
        resp.__enter__ = lambda s: resp
        resp.__exit__ = MagicMock(return_value=False)
        return resp

    def test_returns_true_on_200(self):
        with patch("urllib.request.urlopen", return_value=self._mock_resp(200)):
            assert _is_image_reachable("https://example.com/hero.jpg") is True

    def test_returns_true_on_301(self):
        with patch("urllib.request.urlopen", return_value=self._mock_resp(301)):
            assert _is_image_reachable("https://example.com/hero.jpg") is True

    def test_returns_false_on_403(self):
        with patch("urllib.request.urlopen", side_effect=Exception("403 Forbidden")):
            assert _is_image_reachable("https://example.com/hero.jpg") is False

    def test_returns_false_on_404(self):
        with patch("urllib.request.urlopen", side_effect=Exception("404 Not Found")):
            assert _is_image_reachable("https://example.com/hero.jpg") is False

    def test_returns_false_on_network_error(self):
        with patch("urllib.request.urlopen", side_effect=Exception("Connection refused")):
            assert _is_image_reachable("https://example.com/hero.jpg") is False

    def test_returns_false_on_timeout(self):
        import socket
        with patch("urllib.request.urlopen", side_effect=socket.timeout()):
            assert _is_image_reachable("https://example.com/hero.jpg") is False


class TestHeroImageReachabilityFallback:

    def test_unreachable_image_falls_back_to_gradient(self):
        calls, _ = _run({"images": ["https://testbistro.com/hero.jpg"]}, image_reachable=False)
        prompt = calls[0][1]["messages"][0]["content"]
        assert "NO external image URLs" in prompt

    def test_reachable_image_used_in_prompt(self):
        calls, _ = _run({"images": ["https://testbistro.com/hero.jpg"]}, image_reachable=True)
        prompt = calls[0][1]["messages"][0]["content"]
        assert "https://testbistro.com/hero.jpg" in prompt

    def test_skips_unreachable_picks_next_reachable(self):
        calls, _ = _run(
            {"images": ["https://testbistro.com/hero1.jpg", "https://testbistro.com/hero2.jpg"]},
            image_reachable=lambda url: "hero2" in url,
        )
        prompt = calls[0][1]["messages"][0]["content"]
        assert "hero2.jpg" in prompt
        assert "hero1.jpg" not in prompt

    def test_all_unreachable_uses_gradient(self):
        calls, _ = _run(
            {"images": ["https://testbistro.com/a.jpg", "https://testbistro.com/b.jpg"]},
            image_reachable=False,
        )
        prompt = calls[0][1]["messages"][0]["content"]
        assert "NO external image URLs" in prompt
        assert "linear-gradient" in prompt


# ─── B20: Regression QA — chat, hero image, mobile ───────────────────────────

class TestRegressionQA:
    """Golden-domain regression suite. Any B15-B20 change that breaks these fails here."""

    # ── Chat ──────────────────────────────────────────────────────────────────

    def test_chat_widget_injected_into_final_html(self):
        _, html = _run()
        assert "lvrg-chat" in html

    def test_chat_widget_before_body_close(self):
        _, html = _run()
        assert html.index("lvrg-chat") < html.index("</body>")

    def test_chat_outside_click_listener_in_final_html(self):
        _, html = _run()
        assert "document.addEventListener('click'" in html

    def test_chat_escape_listener_in_final_html(self):
        _, html = _run()
        assert "e.key==='Escape'" in html

    def test_chat_css_isolation_in_final_html(self):
        _, html = _run()
        assert "all:initial" in html

    def test_chat_panel_has_mobile_max_width(self):
        _, html = _run()
        assert "max-width:calc(100vw - 48px)" in html

    # ── Hero image ────────────────────────────────────────────────────────────

    def test_hero_image_in_prompt_when_reachable(self):
        calls, _ = _run({"images": ["https://testbistro.com/hero.jpg"]}, image_reachable=True)
        prompt = calls[0][1]["messages"][0]["content"]
        assert "https://testbistro.com/hero.jpg" in prompt

    def test_hero_gradient_in_prompt_when_no_images(self):
        calls, _ = _run({"images": []})
        prompt = calls[0][1]["messages"][0]["content"]
        assert "linear-gradient" in prompt
        assert "NO external image URLs" in prompt

    def test_hero_gradient_fallback_when_image_unreachable(self):
        calls, _ = _run({"images": ["https://testbistro.com/blocked.jpg"]}, image_reachable=False)
        prompt = calls[0][1]["messages"][0]["content"]
        assert "NO external image URLs" in prompt

    # ── Mobile ────────────────────────────────────────────────────────────────

    def test_viewport_meta_instruction_in_part1_prompt(self):
        prompt = _build_part1_prompt(INTEL, "", "gradient", "- no images")
        assert "viewport" in prompt
        assert "width=device-width" in prompt

    def test_mobile_max_width_container_instruction_in_part1_prompt(self):
        prompt = _build_part1_prompt(INTEL, "", "gradient", "- no images")
        assert "max-width" in prompt

    def test_mobile_flex_wrap_instruction_in_part1_prompt(self):
        prompt = _build_part1_prompt(INTEL, "", "gradient", "- no images")
        assert "flex-wrap" in prompt


# ─── B22: </script> injection — intel_json escaping ──────────────────────────

class TestIntelJsonEscaping:

    def _widget(self, intel_override=None):
        from generator import _build_chat_widget
        intel = {**INTEL, **(intel_override or {})}
        return _build_chat_widget(intel)

    def test_script_close_tag_escaped_in_description(self):
        html = self._widget({"description": "We love </script> tags"})
        assert "</script>" not in html.split("<script>", 1)[1].split("</script>")[0]

    def test_escaped_form_present(self):
        html = self._widget({"description": "We love </script> tags"})
        assert "<\\/script>" in html

    def test_script_close_in_business_name_escaped(self):
        html = self._widget({"business_name": "Acme</script>Co"})
        assert "<\\/script>" in html

    def test_script_close_in_social_proof_escaped(self):
        html = self._widget({"social_proof": "Best</script>ever"})
        assert "<\\/script>" in html

    def test_uppercase_script_tag_escaped(self):
        html = self._widget({"description": "Bad </SCRIPT> input"})
        assert "</SCRIPT>" not in html.split("<script>", 1)[1].split("</script>")[0]

    def test_normal_content_not_affected(self):
        html = self._widget({"description": "A great restaurant in San Diego"})
        assert "A great restaurant in San Diego" in html

    def test_other_html_tags_not_mangled(self):
        html = self._widget({"description": "Visit <a href='/'>our site</a>"})
        assert "our site" in html

    def test_widget_js_still_valid_with_escaped_json(self):
        html = self._widget({"description": "Tricky </script> content"})
        assert "var _lvrgIntel=" in html
        assert "_lvrgHistory" in html
