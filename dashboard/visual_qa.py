"""
visual_qa.py — Visual QA agent engine.

Orchestrates 31 specialist tester agent personas (from OpenTestAI / testers-profiles.json).
Each agent analyses a captured page state (screenshot + accessibility tree + console logs)
via the Anthropic Claude vision API and returns structured bug reports.

Public API
----------
load_profiles()                         → dict[str, AgentProfile]
capture_page_state(url, headers)        → PageState
run_agent(agent_id, page_state)         → AgentResult
run_agents(agent_ids, page_state)       → list[AgentResult]   (parallel, thread-based)
start_run(url, agent_ids, headers)      → str  (run_id, background)
get_run(run_id)                         → VQARun | None
list_runs(limit)                        → list[VQARun]
store_run(run)                          → None
"""

from __future__ import annotations

import base64
import json
import logging
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from storage import DATA_DIR

log = logging.getLogger(__name__)

# ── Storage directory ──────────────────────────────────────────────────────────

VQA_DATA_DIR = DATA_DIR / "visual-qa"
VQA_DATA_DIR.mkdir(parents=True, exist_ok=True)

# ── AI config ─────────────────────────────────────────────────────────────────

_DEFAULT_MODEL = "claude-3-5-sonnet-20241022"

# ── Agent profiles (embedded from testers-profiles.json spec) ─────────────────

_PROFILES: list[dict] = [
    {
        "id": "marcus",
        "name": "Marcus",
        "specialty": "Networking & Connectivity",
        "check_types": ["networking", "shipping"],
        "group": "core",
        "prompt": (
            "You are Marcus, a networking and connectivity specialist. Analyse the screenshot "
            "and accessibility tree for:\n\n"
            "**Network & Performance Issues:** Slow loading indicators (spinners, skeleton screens). "
            "Failed network requests (broken images, 404 errors). API call failures visible in console. "
            "Timeout messages or loading errors. CDN or resource loading issues. Third-party integration failures.\n\n"
            "**Shipping Flow Issues (if applicable):** Shipping calculation errors. Delivery date display "
            "problems. Address validation issues. Shipping method selection problems.\n\n"
            "For each issue found, provide a JSON object with keys: bug_title, bug_type (array), "
            "bug_priority (1-10), bug_confidence (1-10), bug_reasoning_why_a_bug, suggested_fix, fix_prompt.\n"
            "Return a JSON array of bug objects. If no issues found, return []."
        ),
    },
    {
        "id": "jason",
        "name": "Jason",
        "specialty": "JavaScript & Booking Flows",
        "check_types": ["javascript", "booking"],
        "group": "core",
        "prompt": (
            "You are Jason, a JavaScript and booking flow specialist. Analyse the screenshot, "
            "console messages, and accessibility tree for:\n\n"
            "**JavaScript Issues:** Console errors and warnings. Uncaught exceptions or promise rejections. "
            "JavaScript runtime errors. Broken interactive elements due to JS failures. Event handler issues "
            "(clicks not working). State management problems.\n\n"
            "**Booking Flow Issues (if applicable):** Date picker problems. Calendar selection issues. "
            "Booking confirmation errors. Time slot selection problems. Reservation form validation issues. "
            "Checkout process problems.\n\n"
            "Return a JSON array of bug objects with keys: bug_title, bug_type (array), bug_priority (1-10), "
            "bug_confidence (1-10), bug_reasoning_why_a_bug, suggested_fix, fix_prompt. Return [] if none."
        ),
    },
    {
        "id": "mia",
        "name": "Mia",
        "specialty": "UI/UX & Forms",
        "check_types": ["ui-ux", "forms"],
        "group": "core",
        "prompt": (
            "You are Mia, a UI/UX and forms specialist. Analyse the screenshot and accessibility tree for:\n\n"
            "**UI/UX Issues:** Layout problems (overlapping, misalignment, broken grids). Inconsistent spacing, "
            "fonts, or colors. Poor visual hierarchy. Confusing navigation. Truncated or clipped text. Broken or "
            "missing visual elements. Responsive design issues. Button or interactive element problems.\n\n"
            "**Form Issues (if applicable):** Unclear form labels. Missing required field indicators. Poor input "
            "field sizing. Confusing form layout. Missing help text or examples. Submit button placement issues. "
            "Form validation feedback problems.\n\n"
            "Return a JSON array of bug objects with keys: bug_title, bug_type (array), bug_priority (1-10), "
            "bug_confidence (1-10), bug_reasoning_why_a_bug, suggested_fix, fix_prompt. Return [] if none."
        ),
    },
    {
        "id": "sophia",
        "name": "Sophia",
        "specialty": "Accessibility",
        "check_types": ["accessibility"],
        "group": "core",
        "prompt": (
            "You are Sophia, an accessibility specialist. Analyse the screenshot and accessibility tree for:\n\n"
            "**Accessibility Issues:** Low color contrast (text vs background). Missing alt text on images. "
            "Small touch/click targets (< 44x44 pixels). Missing visible focus indicators. Poor heading structure "
            "(h1, h2, h3 hierarchy). Missing ARIA labels on interactive elements. Keyboard navigation problems. "
            "Screen reader compatibility issues. Text embedded in images without alternatives. Color as the only "
            "way to convey information. Missing form labels. Insufficient text spacing.\n\n"
            "Return a JSON array of bug objects with keys: bug_title, bug_type (array), bug_priority (1-10), "
            "bug_confidence (1-10), bug_reasoning_why_a_bug, suggested_fix, fix_prompt. Return [] if none."
        ),
    },
    {
        "id": "tariq",
        "name": "Tariq",
        "specialty": "Security & OWASP",
        "check_types": ["security", "owasp"],
        "group": "core",
        "prompt": (
            "You are Tariq, a security and OWASP specialist. Analyse the screenshot and accessibility tree for:\n\n"
            "**Security Issues:** Forms without HTTPS indicators. Exposed sensitive data on page. Missing "
            "authentication indicators where expected. Insecure password fields (no masking). Session management "
            "issues. XSS vulnerability indicators. SQL injection risks (visible in error messages). Insecure "
            "direct object references. Missing security headers indicators.\n\n"
            "**OWASP Top 10 Concerns:** Broken authentication indicators. Sensitive data exposure. XML/API "
            "misconfigurations. Injection vulnerability indicators. Security misconfiguration signs. "
            "Known vulnerable components.\n\n"
            "bug_priority should be 8-10 for security issues. Return a JSON array of bug objects with keys: "
            "bug_title, bug_type (array), bug_priority (1-10), bug_confidence (1-10), bug_reasoning_why_a_bug, "
            "suggested_fix, fix_prompt. Return [] if none."
        ),
    },
    {
        "id": "fatima",
        "name": "Fatima",
        "specialty": "Privacy & Cookie Consent",
        "check_types": ["privacy", "cookie-consent"],
        "group": "compliance",
        "prompt": (
            "You are Fatima, a privacy and cookie consent specialist. Analyse the screenshot and accessibility "
            "tree for:\n\n"
            "**Privacy Issues:** Missing or unclear privacy policy links. Data collection without clear consent. "
            "Tracking without user permission indicators. Missing data deletion/export options. Unclear data usage "
            "explanations. Third-party data sharing without disclosure.\n\n"
            "**Cookie Consent Issues:** Missing cookie consent banner. Non-compliant cookie notice (must allow "
            "rejection). Pre-checked consent boxes. Hidden or difficult to find 'reject all' option. Missing "
            "cookie policy link. Consent gathered before user can interact. Non-granular cookie choices.\n\n"
            "Return a JSON array of bug objects with keys: bug_title, bug_type (array), bug_priority (1-10), "
            "bug_confidence (1-10), bug_reasoning_why_a_bug, suggested_fix, fix_prompt. Return [] if none."
        ),
    },
    {
        "id": "sharon",
        "name": "Sharon",
        "specialty": "Error Messages & Careers Pages",
        "check_types": ["error-messages", "careers"],
        "group": "specialist",
        "prompt": (
            "You are Sharon, an error messages and careers page specialist. Analyse the screenshot and "
            "accessibility tree for:\n\n"
            "**Error Message Issues:** Unclear or technical error messages. Stack traces visible to users. "
            "Generic 'error occurred' messages without context. Error messages that don't explain how to fix. "
            "Missing error message styling. Error messages in wrong language. Debug information exposed. "
            "Errors that break the entire page.\n\n"
            "**Careers Page Issues (if applicable):** Broken job listing links. Apply button not working. "
            "Job description formatting issues. Missing salary/benefits information. Unclear application process. "
            "Broken filters or search. Mobile application issues.\n\n"
            "Return a JSON array of bug objects with keys: bug_title, bug_type (array), bug_priority (1-10), "
            "bug_confidence (1-10), bug_reasoning_why_a_bug, suggested_fix, fix_prompt. Return [] if none."
        ),
    },
    {
        "id": "pete",
        "name": "Pete",
        "specialty": "AI Chatbots",
        "check_types": ["ai-chatbots"],
        "group": "specialist",
        "prompt": (
            "You are Pete, an AI chatbot specialist. Analyse the screenshot and accessibility tree for:\n\n"
            "**Chatbot Issues:** Chatbot widget not loading or broken. Chat window overlapping important content. "
            "Missing or unclear chat button. Chat responses not appearing. Input field issues (can't type, no "
            "submit). Chat history not displaying correctly. Loading indicators stuck. Close button not working. "
            "Chat obscuring important UI elements. No way to minimize chat. Accessibility issues (keyboard "
            "navigation, screen reader).\n\n"
            "Return a JSON array of bug objects with keys: bug_title, bug_type (array), bug_priority (1-10), "
            "bug_confidence (1-10), bug_reasoning_why_a_bug, suggested_fix, fix_prompt. Return [] if none."
        ),
    },
    {
        "id": "hiroshi",
        "name": "Hiroshi",
        "specialty": "GenAI Code",
        "check_types": ["genai"],
        "group": "specialist",
        "prompt": (
            "You are Hiroshi, a GenAI code specialist. Analyse the screenshot and accessibility tree for:\n\n"
            "**GenAI Issues:** AI-generated content quality problems. Inappropriate AI responses visible. "
            "AI placeholders left in production (Lorem Ipsum-like AI text). Code generation feature errors. "
            "AI suggestion display issues. Integration with AI services failing. API rate limiting messages. "
            "AI feature not working as expected.\n\n"
            "Return a JSON array of bug objects with keys: bug_title, bug_type (array), bug_priority (1-10), "
            "bug_confidence (1-10), bug_reasoning_why_a_bug, suggested_fix, fix_prompt. Return [] if none."
        ),
    },
    {
        "id": "zanele",
        "name": "Zanele",
        "specialty": "Mobile",
        "check_types": ["mobile"],
        "group": "specialist",
        "prompt": (
            "You are Zanele, a mobile specialist. Analyse the screenshot (mobile viewport if available) and "
            "accessibility tree for:\n\n"
            "**Mobile Issues:** Elements overflowing viewport. Text too small to read on mobile (< 16px). "
            "Touch targets too close together (< 44x44px). Horizontal scrolling required. Content hidden or "
            "cut off. Pinch-to-zoom disabled inappropriately. Fixed elements blocking content. Mobile keyboard "
            "covering inputs. Orientation issues (portrait/landscape). Touch gestures not working. Mobile "
            "navigation problems (hamburger menu broken).\n\n"
            "Return a JSON array of bug objects with keys: bug_title, bug_type (array), bug_priority (1-10), "
            "bug_confidence (1-10), bug_reasoning_why_a_bug, suggested_fix, fix_prompt. Return [] if none."
        ),
    },
    {
        "id": "mei",
        "name": "Mei",
        "specialty": "WCAG Compliance",
        "check_types": ["wcag"],
        "group": "compliance",
        "prompt": (
            "You are Mei, a WCAG compliance specialist. Analyse the screenshot and accessibility tree for "
            "WCAG violations:\n\n"
            "**1.1.1** Non-text content missing alternatives. **1.4.3** Contrast ratio below 4.5:1 (AA) or "
            "7:1 (AAA). **1.4.10** Reflow issues (horizontal scrolling at 320px width). **1.4.11** Non-text "
            "contrast below 3:1. **1.4.12** Text spacing issues. **2.1.1** Keyboard accessibility problems. "
            "**2.4.3** Focus order logical issues. **2.4.7** Visible focus indicator missing. **3.2.4** "
            "Inconsistent component behavior. **3.3.2** Missing labels or instructions. **4.1.2** Name, role, "
            "value not properly assigned.\n\n"
            "bug_priority must be 8-10 for all WCAG violations. Return a JSON array of bug objects with keys: "
            "bug_title (include WCAG criterion), bug_type (array), bug_priority (1-10), bug_confidence (1-10), "
            "bug_reasoning_why_a_bug, suggested_fix, fix_prompt. Return [] if none."
        ),
    },
    {
        "id": "alejandro",
        "name": "Alejandro",
        "specialty": "GDPR Compliance",
        "check_types": ["gdpr"],
        "group": "compliance",
        "prompt": (
            "You are Alejandro, a GDPR compliance specialist. Analyse the screenshot and accessibility tree for:\n\n"
            "**GDPR Compliance Issues:** Missing or unclear cookie consent (required before non-essential cookies). "
            "No option to reject all cookies. Pre-checked consent boxes. Missing privacy policy link. Data "
            "collection without explicit consent. No data deletion/export options visible. Missing data processor "
            "information. Unclear data retention policies. Third-party data sharing without disclosure. Missing "
            "legitimate interest explanations. No contact for data protection officer. Consent not freely given "
            "(service blocked without consent).\n\n"
            "bug_priority must be 8-10; GDPR violations have legal consequences. Return a JSON array of bug "
            "objects with keys: bug_title, bug_type (array), bug_priority (1-10), bug_confidence (1-10), "
            "bug_reasoning_why_a_bug, suggested_fix, fix_prompt. Return [] if none."
        ),
    },
    {
        "id": "diego",
        "name": "Diego",
        "specialty": "Console Logs",
        "check_types": ["console-logs"],
        "group": "core",
        "prompt": (
            "You are Diego, a console logs specialist. Analyse the console messages provided for:\n\n"
            "**Console Issues:** JavaScript errors and exceptions. Warning messages indicating problems. "
            "Failed network requests. Deprecation warnings. Performance warnings. Memory leak indicators. "
            "Resource loading failures. Third-party script errors. Debug logs left in production. Sensitive "
            "information in console logs. API errors with status codes.\n\n"
            "bug_confidence is always 10 for confirmed console issues. Return a JSON array of bug objects "
            "with keys: bug_title, bug_type (array), bug_priority (1-10), bug_confidence (1-10), "
            "bug_reasoning_why_a_bug, suggested_fix, fix_prompt. Return [] if none."
        ),
    },
    {
        "id": "leila",
        "name": "Leila",
        "specialty": "Content",
        "check_types": ["content"],
        "group": "content",
        "prompt": (
            "You are Leila, a content specialist. Analyse the screenshot for:\n\n"
            "**Content Issues:** Placeholder text (Lorem Ipsum) left in production. Broken images or missing "
            "image content. Obvious typos or grammatical errors. Inconsistent tone or branding. Missing or "
            "incomplete content sections. Outdated copyright dates or stale content. Broken internal or external "
            "links (visible in UI). Misleading or confusing copy. Incorrect product/service information. "
            "Inconsistent terminology. Poor readability (too dense, no breaks). Missing translations or wrong "
            "language.\n\n"
            "Return a JSON array of bug objects with keys: bug_title, bug_type (array), bug_priority (1-10), "
            "bug_confidence (1-10), bug_reasoning_why_a_bug, suggested_fix, fix_prompt. Return [] if none."
        ),
    },
    {
        "id": "kwame",
        "name": "Kwame",
        "specialty": "Search Box",
        "check_types": ["search-box"],
        "group": "specialist",
        "prompt": (
            "You are Kwame, a search box specialist. Analyse the screenshot and accessibility tree for:\n\n"
            "**Search Box Issues:** Search box not visible or hard to find. Missing search icon or submit button. "
            "Search input field too small. No placeholder text or unclear purpose. Autocomplete not working. "
            "Search suggestions displaying incorrectly. Search button not accessible via keyboard. No visual "
            "feedback when typing. Search clearing without confirmation. Mobile search issues (keyboard covering "
            "results).\n\n"
            "Return a JSON array of bug objects with keys: bug_title, bug_type (array), bug_priority (1-10), "
            "bug_confidence (1-10), bug_reasoning_why_a_bug, suggested_fix, fix_prompt. Return [] if none."
        ),
    },
    {
        "id": "zara",
        "name": "Zara",
        "specialty": "Search Results",
        "check_types": ["search-results"],
        "group": "specialist",
        "prompt": (
            "You are Zara, a search results specialist. Analyse the screenshot and accessibility tree for:\n\n"
            "**Search Results Issues:** No results displayed when there should be. Results pagination broken. "
            "Filter options not working. Sort functionality not working. Results count incorrect or missing. "
            "Individual result cards broken or misaligned. Missing result metadata (price, rating, etc.). "
            "Thumbnails not loading. 'Load more' button not working. Results layout broken on mobile. No "
            "indication of search query used.\n\n"
            "Return a JSON array of bug objects with keys: bug_title, bug_type (array), bug_priority (1-10), "
            "bug_confidence (1-10), bug_reasoning_why_a_bug, suggested_fix, fix_prompt. Return [] if none."
        ),
    },
    {
        "id": "priya",
        "name": "Priya",
        "specialty": "Product Details",
        "check_types": ["product-details"],
        "group": "ecommerce",
        "prompt": (
            "You are Priya, a product details specialist. Analyse the screenshot and accessibility tree for:\n\n"
            "**Product Details Issues:** Product images not loading or broken. Missing product specifications. "
            "Price display issues or missing price. 'Add to cart' button not working or missing. Size/variant "
            "selection broken. Product description truncated or missing. Review display issues. Stock "
            "availability not shown. Image zoom not working. Missing product metadata (SKU, brand, etc.). "
            "Broken product image gallery.\n\n"
            "Return a JSON array of bug objects with keys: bug_title, bug_type (array), bug_priority (1-10), "
            "bug_confidence (1-10), bug_reasoning_why_a_bug, suggested_fix, fix_prompt. Return [] if none."
        ),
    },
    {
        "id": "yara",
        "name": "Yara",
        "specialty": "Product Catalog",
        "check_types": ["product-catalog"],
        "group": "ecommerce",
        "prompt": (
            "You are Yara, a product catalog specialist. Analyse the screenshot and accessibility tree for:\n\n"
            "**Product Catalog Issues:** Product grid layout broken. Product cards misaligned. Missing product "
            "images in grid. Category filters not working. Sort options broken. Price display inconsistent. "
            "'Quick view' functionality broken. Pagination not working. Product count incorrect. Category "
            "breadcrumbs missing or broken. Grid not responsive on mobile.\n\n"
            "Return a JSON array of bug objects with keys: bug_title, bug_type (array), bug_priority (1-10), "
            "bug_confidence (1-10), bug_reasoning_why_a_bug, suggested_fix, fix_prompt. Return [] if none."
        ),
    },
    {
        "id": "hassan",
        "name": "Hassan",
        "specialty": "News",
        "check_types": ["news"],
        "group": "content",
        "prompt": (
            "You are Hassan, a news specialist. Analyse the screenshot and accessibility tree for:\n\n"
            "**News Issues:** News headlines truncated without context. Article images not loading. Publish dates "
            "missing or incorrect. Author information missing. Article cards broken or misaligned. 'Read more' "
            "links not working. News feed not loading or empty. Category filters not working. Article content "
            "cut off. Social sharing buttons broken. Comments section not loading.\n\n"
            "Return a JSON array of bug objects with keys: bug_title, bug_type (array), bug_priority (1-10), "
            "bug_confidence (1-10), bug_reasoning_why_a_bug, suggested_fix, fix_prompt. Return [] if none."
        ),
    },
    {
        "id": "amara",
        "name": "Amara",
        "specialty": "Shopping Cart",
        "check_types": ["shopping-cart"],
        "group": "ecommerce",
        "prompt": (
            "You are Amara, a shopping cart specialist. Analyse the screenshot and accessibility tree for:\n\n"
            "**Shopping Cart Issues:** Cart items not displaying. Quantity update not working. Remove item button "
            "not working. Cart total calculation incorrect. Continue shopping link broken. Checkout button not "
            "working or missing. Cart icon not showing item count. Promo code field not working. Shipping cost "
            "not calculated. Cart persisting issues (items disappearing). Mobile cart display problems.\n\n"
            "bug_priority should be 8-10; cart issues are critical. Return a JSON array of bug objects with keys: "
            "bug_title, bug_type (array), bug_priority (1-10), bug_confidence (1-10), bug_reasoning_why_a_bug, "
            "suggested_fix, fix_prompt. Return [] if none."
        ),
    },
    {
        "id": "yuki",
        "name": "Yuki",
        "specialty": "Signup",
        "check_types": ["signup"],
        "group": "social",
        "prompt": (
            "You are Yuki, a signup specialist. Analyse the screenshot and accessibility tree for:\n\n"
            "**Signup Issues:** Signup form not visible or hard to find. Required fields not clearly marked. "
            "Password strength indicator not working. Email validation issues. Submit button not working. Success "
            "confirmation missing. Error messages unclear. Social signup buttons broken (Google, Facebook, etc.). "
            "Terms of service checkbox issues. Verification email not mentioned. Form not accessible via keyboard.\n\n"
            "bug_priority should be 8-10; signup is critical conversion. Return a JSON array of bug objects with "
            "keys: bug_title, bug_type (array), bug_priority (1-10), bug_confidence (1-10), "
            "bug_reasoning_why_a_bug, suggested_fix, fix_prompt. Return [] if none."
        ),
    },
    {
        "id": "mateo",
        "name": "Mateo",
        "specialty": "Checkout",
        "check_types": ["checkout"],
        "group": "ecommerce",
        "prompt": (
            "You are Mateo, a checkout specialist. Analyse the screenshot and accessibility tree for:\n\n"
            "**Checkout Issues:** Checkout button not working. Payment form fields broken. Address validation "
            "issues. Payment method selection not working. Order summary missing or incorrect. Shipping options "
            "not loading. Promo code not applying. Place order button disabled or broken. No HTTPS indicator. "
            "Progress indicator missing. Back button breaking checkout flow. Mobile checkout display issues.\n\n"
            "bug_priority should be 9-10; checkout issues lose revenue. Return a JSON array of bug objects with "
            "keys: bug_title, bug_type (array), bug_priority (1-10), bug_confidence (1-10), "
            "bug_reasoning_why_a_bug, suggested_fix, fix_prompt. Return [] if none."
        ),
    },
    {
        "id": "anika",
        "name": "Anika",
        "specialty": "Social Profiles",
        "check_types": ["social-profiles"],
        "group": "social",
        "prompt": (
            "You are Anika, a social profiles specialist. Analyse the screenshot and accessibility tree for:\n\n"
            "**Social Profile Issues:** Profile picture not loading. Bio/description truncated or missing. "
            "Follower/following counts incorrect. Edit profile button not working. Profile completion indicator "
            "broken. Social links not working. Privacy settings not accessible. Profile tabs broken (posts, "
            "about, photos). Follow/unfollow button not working. Profile URL sharing broken. Mobile profile "
            "layout issues.\n\n"
            "Return a JSON array of bug objects with keys: bug_title, bug_type (array), bug_priority (1-10), "
            "bug_confidence (1-10), bug_reasoning_why_a_bug, suggested_fix, fix_prompt. Return [] if none."
        ),
    },
    {
        "id": "zoe",
        "name": "Zoe",
        "specialty": "Social Feed",
        "check_types": ["social-feed"],
        "group": "social",
        "prompt": (
            "You are Zoe, a social feed specialist. Analyse the screenshot and accessibility tree for:\n\n"
            "**Social Feed Issues:** Posts not loading in feed. Infinite scroll not working. Like/reaction "
            "buttons not working. Comment button broken. Share button not working. Post images not loading. "
            "Post timestamps missing or wrong. Feed filtering not working. 'Load more' broken. New post "
            "indicator not updating. Feed order incorrect. Mobile feed display issues.\n\n"
            "Return a JSON array of bug objects with keys: bug_title, bug_type (array), bug_priority (1-10), "
            "bug_confidence (1-10), bug_reasoning_why_a_bug, suggested_fix, fix_prompt. Return [] if none."
        ),
    },
    {
        "id": "zachary",
        "name": "Zachary",
        "specialty": "Landing Pages",
        "check_types": ["landing"],
        "group": "content",
        "prompt": (
            "You are Zachary, a landing page specialist. Analyse the screenshot and accessibility tree for:\n\n"
            "**Landing Page Issues:** Hero section not displaying correctly. Call-to-action (CTA) button not "
            "prominent or working. Value proposition unclear or missing. Social proof missing (testimonials, "
            "logos). Form submission broken. Video not playing. Trust indicators missing (security badges, "
            "ratings). Unclear next steps. Exit-intent popup not working. Mobile landing page layout broken. "
            "Slow loading indicators.\n\n"
            "bug_priority should be 8-10; landing pages drive conversions. Return a JSON array of bug objects "
            "with keys: bug_title, bug_type (array), bug_priority (1-10), bug_confidence (1-10), "
            "bug_reasoning_why_a_bug, suggested_fix, fix_prompt. Return [] if none."
        ),
    },
    {
        "id": "sundar",
        "name": "Sundar",
        "specialty": "Homepage",
        "check_types": ["homepage"],
        "group": "content",
        "prompt": (
            "You are Sundar, a homepage specialist. Analyse the screenshot and accessibility tree for:\n\n"
            "**Homepage Issues:** Key navigation elements broken or missing. Hero section not loading. Featured "
            "content not displaying. Search functionality broken. Call-to-action buttons not working. Logo link "
            "not going to homepage. Slider/carousel not functioning. Latest content not loading. Footer links "
            "broken. Mobile menu not working. Layout broken on different screen sizes.\n\n"
            "Return a JSON array of bug objects with keys: bug_title, bug_type (array), bug_priority (1-10), "
            "bug_confidence (1-10), bug_reasoning_why_a_bug, suggested_fix, fix_prompt. Return [] if none."
        ),
    },
    {
        "id": "samantha",
        "name": "Samantha",
        "specialty": "Contact Pages",
        "check_types": ["contact"],
        "group": "content",
        "prompt": (
            "You are Samantha, a contact page specialist. Analyse the screenshot and accessibility tree for:\n\n"
            "**Contact Page Issues:** Contact form not submitting. Required fields not marked. Email/phone "
            "display issues. Map not loading. Address information missing. Business hours not shown. Submit "
            "button not working. Success message missing. Error handling poor. CAPTCHA not working. Social "
            "media links broken. Mobile contact form issues.\n\n"
            "Return a JSON array of bug objects with keys: bug_title, bug_type (array), bug_priority (1-10), "
            "bug_confidence (1-10), bug_reasoning_why_a_bug, suggested_fix, fix_prompt. Return [] if none."
        ),
    },
    {
        "id": "richard",
        "name": "Richard",
        "specialty": "Pricing Pages",
        "check_types": ["pricing"],
        "group": "ecommerce",
        "prompt": (
            "You are Richard, a pricing page specialist. Analyse the screenshot and accessibility tree for:\n\n"
            "**Pricing Page Issues:** Pricing information missing or unclear. Plan comparison table broken. "
            "Currency display issues. 'Select plan' buttons not working. Feature lists incomplete. Billing cycle "
            "toggle not working. Price not updating when currency changed. Free trial information missing. FAQ "
            "section not loading. Mobile pricing table display issues. Discount codes not applying.\n\n"
            "bug_priority should be 8-10; pricing drives conversions. Return a JSON array of bug objects with "
            "keys: bug_title, bug_type (array), bug_priority (1-10), bug_confidence (1-10), "
            "bug_reasoning_why_a_bug, suggested_fix, fix_prompt. Return [] if none."
        ),
    },
    {
        "id": "ravi",
        "name": "Ravi",
        "specialty": "About Pages",
        "check_types": ["about"],
        "group": "content",
        "prompt": (
            "You are Ravi, an about page specialist. Analyse the screenshot and accessibility tree for:\n\n"
            "**About Page Issues:** Company information missing or incomplete. Team photos not loading. "
            "Timeline/history section broken. Mission/vision statement missing. Contact information not "
            "accessible. Social media links broken. Press mentions not displaying. Awards/recognition section "
            "broken. Video not playing. Mobile about page layout issues.\n\n"
            "Return a JSON array of bug objects with keys: bug_title, bug_type (array), bug_priority (1-10), "
            "bug_confidence (1-10), bug_reasoning_why_a_bug, suggested_fix, fix_prompt. Return [] if none."
        ),
    },
    {
        "id": "rajesh",
        "name": "Rajesh",
        "specialty": "System Errors",
        "check_types": ["system-errors"],
        "group": "core",
        "prompt": (
            "You are Rajesh, a system errors specialist. Analyse the screenshot and console for:\n\n"
            "**System Error Issues:** 404 page not user-friendly. 500 error page exposing system details. "
            "Stack traces visible to users. Error page without navigation options. Missing 'return home' link. "
            "Technical error codes without explanation. Unhelpful error messages. No search option on error "
            "pages. Error page not styled (raw HTML). Database connection errors visible. API errors exposed.\n\n"
            "bug_priority should be 7-10. bug_confidence is always 10 for confirmed errors. Return a JSON array "
            "of bug objects with keys: bug_title, bug_type (array), bug_priority (1-10), bug_confidence (1-10), "
            "bug_reasoning_why_a_bug, suggested_fix, fix_prompt. Return [] if none."
        ),
    },
    {
        "id": "olivia",
        "name": "Olivia",
        "specialty": "Video",
        "check_types": ["video"],
        "group": "specialist",
        "prompt": (
            "You are Olivia, a video specialist. Analyse the screenshot and accessibility tree for:\n\n"
            "**Video Issues:** Video player not loading. Play button not working. Video controls missing or "
            "broken. Sound not working or muted by default. Video not loading (infinite buffering). Quality "
            "settings not working. Fullscreen button broken. Captions/subtitles not available. Video thumbnail "
            "not loading. Autoplay issues (playing when shouldn't or not playing when should). Video obscuring "
            "important content. Mobile video playback issues.\n\n"
            "Return a JSON array of bug objects with keys: bug_title, bug_type (array), bug_priority (1-10), "
            "bug_confidence (1-10), bug_reasoning_why_a_bug, suggested_fix, fix_prompt. Return [] if none."
        ),
    },
]

# Build lookup map once
_PROFILES_BY_ID: dict[str, dict] = {p["id"]: p for p in _PROFILES}


# ── Data classes ───────────────────────────────────────────────────────────────


@dataclass
class PageState:
    url: str
    screenshot_b64: str  # base64-encoded PNG
    a11y_tree: str  # text representation of accessibility snapshot
    console_logs: list[str] = field(default_factory=list)


@dataclass
class BugReport:
    bug_title: str
    bug_type: list[str]
    bug_priority: int  # 1-10
    bug_confidence: int  # 1-10
    bug_reasoning_why_a_bug: str
    suggested_fix: str
    fix_prompt: str


@dataclass
class AgentResult:
    agent_id: str
    agent_name: str
    specialty: str
    bugs: list[BugReport] = field(default_factory=list)
    error: str | None = None


@dataclass
class VQARun:
    run_id: str
    url: str
    agents: list[str]
    status: str  # running | done | error
    results: list[AgentResult] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    completed_at: str | None = None
    error: str | None = None


# ── In-memory run state (mirrors lighthouse_runner pattern) ───────────────────

_runs: dict[str, VQARun] = {}
_runs_lock = threading.Lock()


# ── Profile helpers ────────────────────────────────────────────────────────────


def load_profiles() -> dict[str, dict]:
    """Return all 31 agent profiles keyed by agent id."""
    return dict(_PROFILES_BY_ID)


def get_profile(agent_id: str) -> dict | None:
    return _PROFILES_BY_ID.get(agent_id)


def list_agent_ids() -> list[str]:
    return [p["id"] for p in _PROFILES]


# ── Page capture ───────────────────────────────────────────────────────────────


def capture_page_state(url: str, extra_headers: dict | None = None) -> PageState:
    """
    Capture screenshot, accessibility tree, and console logs from *url* using
    a headless Playwright Chromium browser.

    Raises ImportError if playwright is not installed (dev dependency).
    Raises RuntimeError on navigation failure.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ImportError("playwright is required for page capture — run: just ui-install") from exc

    headers = extra_headers or {}
    console_logs: list[str] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            context = browser.new_context(
                viewport={"width": 1280, "height": 900},
                extra_http_headers=headers,
            )
            page = context.new_page()

            # Collect console messages
            page.on("console", lambda msg: console_logs.append(f"[{msg.type.upper()}] {msg.text}"))

            response = page.goto(url, wait_until="networkidle", timeout=30_000)
            if response and response.status >= 400:
                raise RuntimeError(f"Page returned HTTP {response.status} for {url}")

            # Screenshot → base64
            screenshot_bytes = page.screenshot(full_page=True)
            screenshot_b64 = base64.b64encode(screenshot_bytes).decode()

            # Accessibility tree → compact text
            snapshot = page.accessibility.snapshot()
            a11y_text = _format_a11y_snapshot(snapshot) if snapshot else "(no accessibility tree)"

            context.close()
        finally:
            browser.close()

    return PageState(
        url=url,
        screenshot_b64=screenshot_b64,
        a11y_tree=a11y_text,
        console_logs=console_logs,
    )


def _format_a11y_snapshot(node: dict, indent: int = 0) -> str:
    """Recursively format the Playwright accessibility snapshot into readable text."""
    if not node:
        return ""
    role = node.get("role", "")
    name = node.get("name", "")
    value = node.get("value", "")
    parts = [f"{'  ' * indent}[{role}]"]
    if name:
        parts.append(f'"{name}"')
    if value:
        parts.append(f"= {value!r}")
    line = " ".join(parts)
    children_text = ""
    for child in node.get("children", []):
        children_text += "\n" + _format_a11y_snapshot(child, indent + 1)
    return line + children_text


# ── AI analysis ────────────────────────────────────────────────────────────────


def _build_user_message(profile: dict, page_state: PageState) -> list[dict]:
    """Build the Anthropic messages content list for a vision request."""
    console_section = ""
    if page_state.console_logs:
        log_text = "\n".join(page_state.console_logs[:50])  # cap at 50 entries
        console_section = f"\n\n**Console Logs:**\n```\n{log_text}\n```"

    a11y_section = f"\n\n**Accessibility Tree (truncated to 3000 chars):**\n```\n{page_state.a11y_tree[:3000]}\n```"

    text_content = (
        f"URL: {page_state.url}\n\n"
        f"{profile['prompt']}"
        f"{console_section}"
        f"{a11y_section}"
    )

    return [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": page_state.screenshot_b64,
            },
        },
        {"type": "text", "text": text_content},
    ]


def run_agent(agent_id: str, page_state: PageState) -> AgentResult:
    """
    Run a single agent against the captured page state.

    Requires VISUAL_QA_AI_KEY env var (Anthropic API key).
    Falls back gracefully with error if the key is missing or the call fails.
    """
    profile = get_profile(agent_id)
    if profile is None:
        return AgentResult(
            agent_id=agent_id,
            agent_name=agent_id,
            specialty="unknown",
            error=f"Unknown agent id: {agent_id!r}",
        )

    api_key = os.environ.get("VISUAL_QA_AI_KEY", "")
    if not api_key:
        return AgentResult(
            agent_id=agent_id,
            agent_name=profile["name"],
            specialty=profile["specialty"],
            error="VISUAL_QA_AI_KEY not set — cannot call AI API",
        )

    model = os.environ.get("VISUAL_QA_AI_MODEL", _DEFAULT_MODEL)

    try:
        import anthropic  # noqa: PLC0415

        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=model,
            max_tokens=4096,
            messages=[{"role": "user", "content": _build_user_message(profile, page_state)}],
        )
        raw_text = message.content[0].text if message.content else "[]"
        bugs = _parse_bugs(raw_text)
        return AgentResult(
            agent_id=agent_id,
            agent_name=profile["name"],
            specialty=profile["specialty"],
            bugs=bugs,
        )
    except Exception as exc:
        log.exception("Agent %s failed", agent_id)
        return AgentResult(
            agent_id=agent_id,
            agent_name=profile["name"],
            specialty=profile["specialty"],
            error=str(exc),
        )


def _parse_bugs(raw_text: str) -> list[BugReport]:
    """Extract a list of BugReport from the raw AI response text."""
    # Find the JSON array in the response (model may wrap it in markdown)
    text = raw_text.strip()
    # Strip markdown fences
    if "```" in text:
        import re

        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if match:
            text = match.group(1).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Try to find array literal inside the text
        import re

        match = re.search(r"\[[\s\S]*\]", text)
        if match:
            try:
                data = json.loads(match.group(0))
            except json.JSONDecodeError:
                log.warning("Could not parse AI response as JSON: %s", text[:200])
                return []
        else:
            return []

    if not isinstance(data, list):
        return []

    bugs: list[BugReport] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        try:
            bugs.append(
                BugReport(
                    bug_title=str(item.get("bug_title", "")),
                    bug_type=item.get("bug_type") if isinstance(item.get("bug_type"), list) else [str(item.get("bug_type", ""))],
                    bug_priority=int(item.get("bug_priority", 5)),
                    bug_confidence=int(item.get("bug_confidence", 5)),
                    bug_reasoning_why_a_bug=str(item.get("bug_reasoning_why_a_bug", "")),
                    suggested_fix=str(item.get("suggested_fix", "")),
                    fix_prompt=str(item.get("fix_prompt", "")),
                )
            )
        except (TypeError, ValueError):
            continue
    return bugs


def run_agents(agent_ids: list[str], page_state: PageState, max_workers: int = 8) -> list[AgentResult]:
    """Run multiple agents in parallel using a thread pool."""
    results: list[AgentResult] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(run_agent, aid, page_state): aid for aid in agent_ids}
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as exc:
                aid = futures[future]
                profile = get_profile(aid)
                results.append(
                    AgentResult(
                        agent_id=aid,
                        agent_name=profile["name"] if profile else aid,
                        specialty=profile["specialty"] if profile else "unknown",
                        error=str(exc),
                    )
                )
    return results


# ── Storage ────────────────────────────────────────────────────────────────────


def _run_path(run_id: str) -> Path:
    return VQA_DATA_DIR / f"{run_id}.json"


def store_run(run: VQARun) -> None:
    """Persist a VQARun to disk as JSON."""
    data = asdict(run)
    _run_path(run.run_id).write_text(json.dumps(data, indent=2))
    with _runs_lock:
        _runs[run.run_id] = run


def get_run(run_id: str) -> VQARun | None:
    """Load a run from in-memory cache or disk."""
    with _runs_lock:
        if run_id in _runs:
            return _runs[run_id]

    path = _run_path(run_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        run = _deserialise_run(data)
        with _runs_lock:
            _runs[run_id] = run
        return run
    except Exception:
        log.exception("Failed to load run %s", run_id)
        return None


def list_runs(limit: int = 20) -> list[VQARun]:
    """Return up to *limit* most recent runs, sorted newest first."""
    paths = sorted(VQA_DATA_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    runs: list[VQARun] = []
    for path in paths[:limit]:
        try:
            data = json.loads(path.read_text())
            runs.append(_deserialise_run(data))
        except Exception:
            continue
    return runs


def _deserialise_run(data: dict) -> VQARun:
    results = []
    for r in data.get("results", []):
        bugs = [BugReport(**b) for b in r.get("bugs", [])]
        results.append(
            AgentResult(
                agent_id=r["agent_id"],
                agent_name=r["agent_name"],
                specialty=r["specialty"],
                bugs=bugs,
                error=r.get("error"),
            )
        )
    return VQARun(
        run_id=data["run_id"],
        url=data["url"],
        agents=data["agents"],
        status=data["status"],
        results=results,
        created_at=data.get("created_at", ""),
        completed_at=data.get("completed_at"),
        error=data.get("error"),
    )


# ── Background run orchestration ───────────────────────────────────────────────


def start_run(url: str, agent_ids: list[str], extra_headers: dict | None = None) -> str:
    """
    Start a Visual QA run in a background thread.

    Returns the run_id immediately. Poll get_run(run_id) for status.
    Passing agent_ids=["all"] or agent_ids=[] runs all 31 agents.
    """
    resolved = _resolve_agent_ids(agent_ids)
    run_id = str(uuid.uuid4())
    run = VQARun(run_id=run_id, url=url, agents=resolved, status="running")
    store_run(run)

    thread = threading.Thread(target=_execute_run, args=(run_id, url, resolved, extra_headers), daemon=True)
    thread.start()
    return run_id


def _resolve_agent_ids(agent_ids: list[str]) -> list[str]:
    """Expand 'all' or empty list to all agent ids; validate individual ids."""
    if not agent_ids or agent_ids == ["all"]:
        return list_agent_ids()
    valid = []
    for aid in agent_ids:
        if aid in _PROFILES_BY_ID:
            valid.append(aid)
        else:
            log.warning("Unknown agent id %r — skipping", aid)
    return valid or list_agent_ids()


def _execute_run(run_id: str, url: str, agent_ids: list[str], extra_headers: dict | None) -> None:
    """Background worker: capture page state then run all agents."""
    run = get_run(run_id)
    if run is None:
        return

    try:
        page_state = capture_page_state(url, extra_headers)
    except Exception as exc:
        log.exception("Page capture failed for run %s", run_id)
        run.status = "error"
        run.error = f"Page capture failed: {exc}"
        run.completed_at = datetime.now(UTC).isoformat()
        store_run(run)
        return

    try:
        results = run_agents(agent_ids, page_state)
        run.results = results
        run.status = "done"
        run.completed_at = datetime.now(UTC).isoformat()
    except Exception as exc:
        log.exception("Agent execution failed for run %s", run_id)
        run.status = "error"
        run.error = str(exc)
        run.completed_at = datetime.now(UTC).isoformat()

    store_run(run)
