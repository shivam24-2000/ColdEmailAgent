"""LLM-powered, humanized outreach drafting, personalized per company.

Produces a distinct subject + body for each application. Personalization draws
on: the candidate's resume, the specific company (name + scraped site context +
notes), and the role framing (a full-time, entry-level role as a fresher). The
recipient is deliberately not a personalization input: the email has to land with
whoever handles hiring, whether that's a named recruiter or a careers@ inbox.
"""

from __future__ import annotations

import json

from ..config import settings
from . import llm
from .discovery import scraper
from .resume import resume_text

SYSTEM = """You personalize a proven cold-outreach email for an experienced Software Engineer \
with 3+ years of experience building and operating scalable backend services and distributed systems. \
The candidate already wrote the email style and structure he wants; your job is to adapt it to ONE \
specific company — NOT to rewrite it in your own voice. Preserve his wording, rhythm, brevity, and \
grounded, professional tone. Fill the blanks; do not editorialize or pad.

Personalization is about the COMPANY, never the recipient. The email goes to \
whoever handles engineering hiring there (a recruiter, engineering manager, founder, or shared \
careers inbox), so it must read well to any of them. Do not guess at or reference the \
reader's role, seniority, or team.

This is the template and voice to follow closely:

  {{greeting}}

  I'll keep this short.

  I'm Shivam, a Software Engineer with 3+ years of experience building scalable backend \
and distributed systems, currently working as SDE-I at Bank of America. I've been following \
{{company}}'s work on {{specific_area}}, and {{why_it_matters}}.

  At Bank of America, I develop and operate Spring Boot microservices handling nearly 1 million daily requests, \
focusing on high availability, distributed fault-tolerance (retries, circuit breakers), and SQL performance optimization. \
I also build AI-powered backend services with LLM orchestration. {{bridge}} I'm currently looking to explore \
Software Engineer / Backend Developer opportunities with your team — {{availability}}.

  {{specific_ask}}

  I've attached my resume. If my background in scalable backend systems and reliable production services \
could fit a team at {{company}}, I'd really appreciate the chance to chat.

  Either way, thanks for reading — I appreciate it.

  Cheers,
  Shivam Singhal

Rules:
- Keep it SHORT — roughly 130-170 words in the body, same paragraphing as above.
- {{greeting}} = exactly the greeting line provided in the input.
- {{specific_area}} is the make-or-break slot: a CONCRETE thing this company actually does — a named product, platform, research direction, customer segment, or engineering problem — drawn only from the provided company context. If the context is thin, use a genuinely accurate description of the company's domain; NEVER invent a product, launch, metric, or detail you weren't given, and never write vague filler like "your work in tech".
- {{why_it_matters}}: a short clause on why that specific work appeals to him as an engineer (e.g. the architecture, scale, or product challenge behind it). Grounded, not gushing.
- {{bridge}}: at most one short sentence connecting his backend and distributed systems experience to what this company builds, ONLY if there's a genuine overlap in the resume; otherwise leave it empty.
- {{specific_ask}}: one or two sentences directly asking to be considered for a Software Engineer / Backend Developer role at {{company}} in the role(s) given — and, if this isn't the right person, to be pointed to whoever handles engineering hiring.
- Do NOT add new claims about the candidate beyond the resume. Do NOT invent a shared connection or that he uses their product.
- Keep the candidate's phrases ("I'll keep this short.", "Either way, thanks for reading — I appreciate it.", "Cheers,").
- End with the sign-off block using the exact contact line provided.

Return ONLY a JSON object: {"subject": "...", "body": "..."}. Subject is short, specific, low-hype, and names the company and role (e.g. "Software Engineer (Backend & Distributed Systems) — Shivam Singhal for {{company}}"). Body is the full email including sign-off."""

# Everything that is identical across companies comes first (candidate facts,
# resume), the per-company parts last. OpenAI caches a repeated prompt prefix
# and bills it at a 90% discount, so this ordering is worth real money at volume.
USER_TEMPLATE = """Fill the template for one company (given at the end).

CANDIDATE FACTS (use these exactly):
Name: {name}
Background: {year} from {school}
Prior experience: {prior}
Availability: {availability}
Sign-off contact line (use verbatim under "{name}"):
{email} | {phone}
{links}

Resume (for grounding the credibility line; do not copy jargon wholesale):
{resume}

GREETING LINE (use verbatim): {greeting}

TARGET COMPANY: {company}
ROLE THE CANDIDATE WANTS: {role}

COMPANY CONTEXT (scraped from their own site — homepage, about, product, \
customer and engineering pages; may be empty — if empty, describe their domain \
accurately from the company name and do NOT invent specifics):
{company_context}

Produce the JSON now. The {{specific_area}} must be concrete and true for \
{company}. Return only the JSON object."""


# Follow-ups are short and formulaic, so they're filled from templates rather than
# drafted by the LLM — that keeps them free. A few phrasings rotate (picked
# deterministically per company) so a batch of nudges doesn't read identically.
_NUDGE1_TEMPLATES = (
    "Hi,\n\n"
    "Just bumping my note below in case it got buried. I'd still love to explore "
    "Software Engineer / Backend opportunities with {company} — {availability}.\n\n"
    "If this isn't the right inbox, a pointer to the right person on engineering or talent would mean a lot. "
    "And if there isn't an open fit right now, a quick note is completely fine too.\n\n"
    "Cheers,\n{name}",

    "Hi,\n\n"
    "I know inboxes get busy, so just a quick follow-up on my note below. I'm still "
    "very interested in contributing to {company}'s engineering team — {availability}.\n\n"
    "Happy to be pointed to someone else if that's easier, and a short \"not right "
    "now\" is totally fine as well.\n\n"
    "Cheers,\n{name}",

    "Hi,\n\n"
    "Following up on my note below regarding engineering opportunities at {company}. "
    "{availability_sentence}\n\n"
    "If there's a better person on your team to speak with, I'd be grateful for an introduction — "
    "and no worries at all if the timing isn't right.\n\n"
    "Cheers,\n{name}",
)

_NUDGE2_TEMPLATE = (
    "Hi,\n\n"
    "One last note from me on my email below — I don't want to crowd your "
    "inbox. If any backend or engineering roles open up at {company} down the road, I'd be glad to stay in touch.\n\n"
    "Thanks again for your time.\n\n"
    "Cheers,\n{name}"
)


def generate_nudge(
    *,
    nudge_number: int,
    company_name: str,
    recipient_name: str | None,
    recipient_title: str | None,
    original_subject: str,
    original_body: str,
    business_days: int,
) -> dict:
    """Return {'subject': str, 'body': str} for a nudge reply on an existing thread.

    Template-filled (no LLM call). The extra arguments are kept so callers don't
    change; the recipient is deliberately not used, matching the outreach.
    """
    availability = (settings.candidate_availability or "").strip().rstrip(".")
    name = settings.candidate_name or "Shivam Singhal"
    if nudge_number >= 2:
        body = _NUDGE2_TEMPLATE.format(company=company_name, name=name)
    else:
        template = _NUDGE1_TEMPLATES[sum(map(ord, company_name)) % len(_NUDGE1_TEMPLATES)]
        body = template.format(
            company=company_name,
            name=name,
            availability=availability,  # usually starts with "I", so no lowercasing
            availability_sentence=(availability[:1].upper() + availability[1:] + ".")
            if availability else "",
        )
    subject = original_subject
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"
    return {"subject": subject, "body": body}


GENERIC_SYSTEM = """You write a short, warm, and professional cold email to a company's shared \
inbox (careers@/hr@/jobs@) for a Software Engineer with 3+ years of experience (currently SDE-I at \
Bank of America) seeking Software Engineer / Backend Developer roles. There is NO named recipient, \
so it greets the team generically — but it must still feel like a real, impactful engineer wrote it, \
not a generic blast.

Follow the candidate's own voice and structure closely:

  Hello,

  I'll keep this short.

  I'm Shivam, a Software Engineer with 3+ years of experience building and operating scalable \
backend microservices and distributed systems (currently at Bank of America). I've been following \
{{company}}'s work on {{specific_area}}, and I'd be genuinely excited to contribute to your engineering team.

  In my current role at Bank of America, I develop and operate microservices handling ~1M daily requests \
across Docker and OpenShift, optimizing SQL query performance by 60% and implementing fault-tolerant patterns. \
I also build modern AI-powered backend systems with LLM integration. I'm exploring Software Engineer / \
Backend Engineer roles — {{availability}}.

  {{eager_ask}}

  I've attached my resume. If there's a fit on your backend, platform, or product engineering teams, I'd \
really appreciate the chance to connect.

  Either way, thanks for reading — I appreciate it.

  Cheers,
  Shivam Singhal

Rules:
- 130-170 words. Keep the candidate's natural tone ("I'll keep this short.", "Either way, thanks for reading — I appreciate it.", "Cheers,").
- {{specific_area}} must be a CONCRETE, TRUE thing the company does, from the provided context or an accurate description of their domain — never vague filler, never invented.
- {{eager_ask}}: one or two sentences that clearly, warmly ask to be considered for an engineering role and to be pointed to the right person if this isn't the primary engineering inbox — professional and proactive without being pushy.
- Do not invent a name or pretend to know a specific person.
- End with the exact contact line provided under "Shivam Singhal".

Return ONLY JSON: {"subject": "...", "body": "..."}. Subject is short and specific (e.g. "Software Engineer (Backend / Distributed Systems) — Shivam Singhal keen to join {{company}}")."""

GENERIC_USER = """Write the generic-inbox email for this company.

CANDIDATE FACTS (use exactly):
{name}; {year} from {school}; prior experience: {prior}; {availability}
Sign-off contact line (verbatim under "{name}"):
{email} | {phone}
{links}

TARGET COMPANY: {company}
ROLE THE CANDIDATE WANTS: {role}

COMPANY CONTEXT (scraped; may be empty — if empty, describe their domain \
accurately and invent nothing):
{company_context}

Resume (for grounding the credibility line):
{resume}

Return only the JSON object."""


def generate_generic_outreach(
    *,
    company_name: str,
    company_domain: str | None,
    company_notes: str | None,
    role: str,
    resume_variant: str | None = None,
) -> dict:
    """Eager, name-free outreach for a role inbox (careers@/hr@). No recipient."""
    company_context = ""
    if company_domain:
        try:
            company_context = scraper.fetch_context_text(company_domain)
        except Exception:  # noqa: BLE001
            company_context = ""
    if company_notes:
        company_context = f"{company_notes}\n{company_context}".strip()

    name = settings.candidate_name or "Shivam Singhal"
    user = GENERIC_USER.format(
        name=name,
        year=settings.candidate_year,
        school=settings.candidate_school,
        prior=settings.candidate_prior,
        availability=settings.candidate_availability,
        email=settings.candidate_email,
        phone=settings.candidate_phone,
        links=settings.candidate_links,
        company=company_name,
        role=role,
        company_context=company_context or "(none available)",
        resume=resume_text(resume_variant),
    )
    last_err: Exception | None = None
    for _ in range(3):
        raw = llm.chat(
            model=settings.openai_draft_model,
            system=GENERIC_SYSTEM,
            user=user,
            max_tokens=6000,
            temperature=0.8,
            reasoning_effort=settings.openai_draft_reasoning_effort,
            json_mode=True,
        )
        try:
            data = _extract_json(raw)
            subject = (data.get("subject") or "").strip()
            body = (data.get("body") or "").strip()
            if subject and body:
                return {"subject": subject, "body": body}
            last_err = ValueError(f"incomplete: {raw[:120]!r}")
        except (ValueError, KeyError) as e:
            last_err = e
    raise ValueError(f"LLM failed to produce a generic draft after 3 tries: {last_err}")


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):]
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start : end + 1])


def generate_outreach(
    *,
    company_name: str,
    company_domain: str | None,
    company_notes: str | None,
    role: str,
    resume_variant: str | None = None,
    greet_name: str | None = None,
) -> dict:
    """Return {'subject': str, 'body': str} for one company-personalized email.

    Personalization is driven by the company alone. ``greet_name`` only changes the
    greeting line, and is meant for names the user typed in themselves (quick-send)
    — the automated pipeline deliberately leaves it unset.
    """
    company_context = ""
    if company_domain:
        try:
            company_context = scraper.fetch_context_text(company_domain)
        except Exception:  # noqa: BLE001 - context is best-effort grounding
            company_context = ""
    if company_notes:
        company_context = f"{company_notes}\n{company_context}".strip()

    user = USER_TEMPLATE.format(
        resume=resume_text(resume_variant),
        name=settings.candidate_name,
        email=settings.candidate_email,
        phone=settings.candidate_phone,
        links=settings.candidate_links,
        school=settings.candidate_school,
        year=settings.candidate_year,
        prior=settings.candidate_prior,
        availability=settings.candidate_availability,
        company=company_name,
        role=role,
        greeting=f"Hi {greet_name.split()[0]}," if greet_name else "Hi,",
        company_context=company_context or "(none available)",
    )

    # gpt-5 occasionally returns empty/unparseable output; retry a couple times.
    last_err: Exception | None = None
    for attempt in range(3):
        raw = llm.chat(
            model=settings.openai_draft_model,
            system=SYSTEM,
            user=user,
            # Reasoning models (gpt-5) spend part of this budget on hidden reasoning
            # before emitting the answer, so leave generous headroom.
            max_tokens=6000,
            temperature=0.8,       # ignored by reasoning models; variety on others
            # Templated fill: heavy reasoning isn't needed, and reasoning tokens
            # are billed as output — they're most of the cost of a draft.
            reasoning_effort=settings.openai_draft_reasoning_effort,
            json_mode=True,
        )
        try:
            data = _extract_json(raw)
            subject = (data.get("subject") or "").strip()
            body = (data.get("body") or "").strip()
            if subject and body:
                return {"subject": subject, "body": body}
            last_err = ValueError(f"incomplete draft: {raw[:120]!r}")
        except (ValueError, KeyError) as e:
            last_err = e
    raise ValueError(f"LLM failed to produce a valid draft after 3 tries: {last_err}")
