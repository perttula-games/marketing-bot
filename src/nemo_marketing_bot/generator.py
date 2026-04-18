"""Nemotron-powered content generator.

Uses NVIDIA's OpenAI-compatible endpoint (integrate.api.nvidia.com) to call
Nemotron models. Each platform has its own length/voice constraints, so we ask
the model for a structured JSON response we can parse safely.
"""

from __future__ import annotations

import json
import logging
from typing import cast

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from .config import settings
from .models import Brief, GeneratedPost, PostBundle, Platform

logger = logging.getLogger(__name__)

PLATFORM_RULES: dict[Platform, str] = {
    "linkedin": (
        "LinkedIn post: professional, value-driven voice. 900-1600 characters. "
        "Open with a strong hook line, use short paragraphs and 1-2 line breaks. "
        "End with a clear CTA. 3-5 focused hashtags."
    ),
    "x": (
        "X (Twitter) post: punchy, conversational. Strict 270 character limit "
        "INCLUDING hashtags and the URL. One idea only. 1-3 hashtags."
    ),
    "instagram": (
        "Instagram caption: warm, visual, story-first. 150-400 characters of copy "
        "followed by up to 10 hashtags on a new line. Include an image_prompt that "
        "describes the accompanying photo/graphic."
    ),
}

SYSTEM_PROMPT = (
    "You are a senior B2B social media marketer. Given a campaign brief, you "
    "write platform-native posts that follow each platform's rules exactly. "
    "Respond ONLY with valid JSON matching the requested schema. No prose, no "
    "markdown fences."
)


def _build_user_prompt(brief: Brief, platforms: list[Platform]) -> str:
    rules_block = "\n".join(f"- {p}: {PLATFORM_RULES[p]}" for p in platforms)
    url_line = f"\nLink to include where relevant: {brief.url}" if brief.url else ""
    cta_line = f"\nPreferred CTA: {brief.call_to_action}" if brief.call_to_action else ""
    tag_line = f"\nSuggested tag themes: {', '.join(brief.tags)}" if brief.tags else ""
    return (
        f"Campaign brief\n"
        f"Topic: {brief.topic}\n"
        f"Details: {brief.details}"
        f"{url_line}{cta_line}{tag_line}\n\n"
        f"Platforms and rules:\n{rules_block}\n\n"
        "Return JSON with this exact shape:\n"
        "{\n"
        '  "posts": [\n'
        '    {"platform": "linkedin|x|instagram", "text": "...", '
        '"hashtags": ["tag1", "tag2"], "image_prompt": "... or null"}\n'
        "  ]\n"
        "}\n"
        "Do not wrap in code fences. Hashtags must NOT include the # symbol."
    )


class ContentGenerator:
    def __init__(self) -> None:
        if not settings.nvidia_api_key:
            raise RuntimeError("NVIDIA_API_KEY is not set. See .env.example.")
        self._client = OpenAI(
            api_key=settings.nvidia_api_key,
            base_url=settings.nvidia_base_url,
        )
        self._model = settings.nvidia_model

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
    def generate(self, brief: Brief, platforms: list[Platform]) -> PostBundle:
        logger.info("Generating posts for %s via %s", platforms, self._model)
        response = self._client.chat.completions.create(
            model=self._model,
            temperature=0.7,
            top_p=0.95,
            max_tokens=1400,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _build_user_prompt(brief, platforms)},
            ],
        )
        raw = response.choices[0].message.content or ""
        payload = _extract_json(raw)
        posts = [GeneratedPost(**p) for p in payload.get("posts", [])]
        found = {p.platform for p in posts}
        missing = [p for p in platforms if p not in found]
        if missing:
            raise ValueError(f"Model response missing platforms: {missing}. Raw: {raw[:400]}")
        return PostBundle(brief=brief, posts=posts)


def _extract_json(raw: str) -> dict:
    """Tolerate stray prose or fenced code by extracting the outermost JSON object."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        # Drop an optional leading language tag like "json\n"
        if "\n" in text:
            text = text.split("\n", 1)[1]
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"No JSON object found in model output: {raw[:200]}")
    return cast(dict, json.loads(text[start : end + 1]))
