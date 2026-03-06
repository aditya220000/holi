import json
import random
import re
from dataclasses import dataclass
from typing import Any

import requests

from app.config import settings
from app.models import Topic


MASTER_SCRIPT_PROMPT = """
You are a world-class 2026 short-form scriptwriter for faceless Instagram Reels and TikTok who has generated 300M+ views in relationships, finance, health, and cultural debate niches. Write a 25–45 second spoken script that is completely standalone — zero references to gaming, video games, war, or any gameplay.

Rules (NEVER break these):
- First 3 seconds = brutal, addictive hook (question, bold truth, or contradiction) that works perfectly as big white text with black outline in the exact middle of the screen.
- Every single sentence = ONE subtitle line (maximum 6–8 words per line, punchy, easy to read in under 1 second).
- Use simple, emotional, spoken language — like a smart friend talking directly to the viewer. Zero corporate, zero AI filler.
- Professional tone only: insightful, empowering, controversial when needed, never childish.
- End with a strong payoff or CTA that makes people save/share/comment.
- Topic must feel timeless yet 2026-relevant for huge audiences.

Structure exactly:
1. Hook (0–3s)
2. Build the truth (3–20s)
3. Twist or deeper realization (20–35s)
4. Payoff + CTA (35–end)

Current broad topic pool: Man vs Women / Relationships / Heartbreak OR Finance OR Health OR Left vs Right.
Randomly choose one topic per script unless specified.

Output ONLY in this clean format:
HOOK: "exact text"
LINE 1: "exact text"
LINE 2: "exact text"
...
CTA: "exact text"

Make it so powerful that someone watching intense action footage cannot scroll away — the message hits their soul.
""".strip()


STYLE_MAP: dict[str, str] = {
    "finance": "deep motivational",
    "relationships": "deep emotional",
    "health": "calm and grounded",
    "left_vs_right": "gravelly and analytical",
}


@dataclass
class ScriptVariant:
    variant_index: int
    style_label: str
    script_payload: dict[str, Any]
    virality_score: float


def _topic_prompt(topic: Topic) -> str:
    return f"{MASTER_SCRIPT_PROMPT}\n\nUse this topic for this run: {topic.value}."


def _request_json(url: str, payload: dict, headers: dict[str, str], timeout: int = 45) -> dict[str, Any]:
    response = requests.post(url, json=payload, headers=headers, timeout=timeout)
    response.raise_for_status()
    return response.json()


def _call_anthropic(prompt: str) -> str:
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not configured")

    data = _request_json(
        "https://api.anthropic.com/v1/messages",
        {
            "model": settings.script_model_primary,
            "max_tokens": 900,
            "temperature": 0.8,
            "messages": [{"role": "user", "content": prompt}],
        },
        {
            "x-api-key": settings.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
    )
    chunks = data.get("content", [])
    text_parts = [c.get("text", "") for c in chunks if c.get("type") == "text"]
    return "\n".join(text_parts).strip()


def _call_grok(prompt: str) -> str:
    if not settings.grok_api_key:
        raise RuntimeError("GROK_API_KEY is not configured")

    data = _request_json(
        f"{settings.grok_base_url.rstrip('/')}/chat/completions",
        {
            "model": settings.script_model_fallback,
            "temperature": 0.9,
            "messages": [{"role": "user", "content": prompt}],
        },
        {
            "Authorization": f"Bearer {settings.grok_api_key}",
            "Content-Type": "application/json",
        },
    )
    return data["choices"][0]["message"]["content"].strip()


def _call_ollama(prompt: str) -> str:
    data = _request_json(
        f"{settings.ollama_base_url.rstrip('/')}/api/generate",
        {
            "model": settings.script_model_local,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.85},
        },
        {"Content-Type": "application/json"},
    )
    return data.get("response", "").strip()


def _fallback_script(topic: Topic, style_label: str) -> str:
    hooks = {
        Topic.RELATIONSHIPS: [
            "Love fails when ego feels safer.",
            "Why do good hearts pick pain?",
            "Most breakups begin before the fight.",
        ],
        Topic.FINANCE: [
            "Broke is often a systems problem.",
            "Your income leaks while you sleep.",
            "Rich habits look boring at first.",
        ],
        Topic.HEALTH: [
            "You are not lazy, just overloaded.",
            "Your body keeps the hidden score.",
            "Burnout starts where boundaries end.",
        ],
        Topic.CULTURE: [
            "Both sides profit from your outrage.",
            "Debate died when listening became weakness.",
            "Tribal certainty is intellectual debt.",
        ],
    }

    bodies = {
        Topic.RELATIONSHIPS: [
            "People beg for honesty then punish it.",
            "We chase intensity and call it destiny.",
            "Real love feels stable, not chaotic.",
            "Choose peace over temporary butterflies.",
        ],
        Topic.FINANCE: [
            "One budget line can free your future.",
            "Automate saving before emotion votes.",
            "Status spending steals compound growth.",
            "Small discipline beats big motivation.",
        ],
        Topic.HEALTH: [
            "Sleep debt looks like anxiety tomorrow.",
            "Your nervous system needs daily silence.",
            "Healing starts with repeatable basics.",
            "Consistency beats extreme routines.",
        ],
        Topic.CULTURE: [
            "Nuance scares people addicted to teams.",
            "Facts matter less than identity online.",
            "Ask who benefits from your anger.",
            "Think slower than the headline cycle.",
        ],
    }

    ctas = {
        Topic.RELATIONSHIPS: "Save this before your next argument.",
        Topic.FINANCE: "Share this with someone building freedom.",
        Topic.HEALTH: "Save this and start tonight.",
        Topic.CULTURE: "Comment if nuance still matters.",
    }

    chosen_hook = random.choice(hooks[topic])
    selected_lines = random.sample(bodies[topic], k=4)
    cta = ctas[topic]

    payload = [f'HOOK: "{chosen_hook}"']
    for idx, line in enumerate(selected_lines, start=1):
        payload.append(f'LINE {idx}: "{line}"')
    payload.append(f'CTA: "{cta}"')

    # Keep style visible for debugging and A/B traceability.
    payload.append(f'STYLE: "{style_label}"')
    return "\n".join(payload)


def parse_script(raw_text: str) -> dict[str, Any]:
    hook = ""
    lines: list[str] = []
    cta = ""

    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.upper().startswith("HOOK:"):
            hook = _extract_quote(line)
            continue
        if re.match(r"^LINE\s+\d+:", line, flags=re.IGNORECASE):
            lines.append(_extract_quote(line))
            continue
        if line.upper().startswith("CTA:"):
            cta = _extract_quote(line)

    if not hook:
        hook = "Truth hurts before it heals."
    if not lines:
        lines = [
            "Most people repeat inherited patterns.",
            "Pause long enough to see them.",
            "Then choose the harder better path.",
            "That is where your power begins.",
        ]
    if not cta:
        cta = "Save this and share it." 

    clipped_lines = [
        _ensure_max_words(text, 8)
        for text in [hook, *lines, cta]
        if text.strip()
    ]
    normalized_hook = clipped_lines[0]
    normalized_cta = clipped_lines[-1]
    normalized_lines = clipped_lines[1:-1]

    full_text = " ".join([normalized_hook, *normalized_lines, normalized_cta])
    return {
        "hook": normalized_hook,
        "lines": normalized_lines,
        "cta": normalized_cta,
        "full_text": full_text,
    }


def _extract_quote(line: str) -> str:
    match = re.search(r'"(.*)"', line)
    if match:
        return match.group(1).strip()
    return line.split(":", maxsplit=1)[-1].strip().strip('"')


def _ensure_max_words(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words])


def _heuristic_virality_score(script_payload: dict[str, Any], topic: Topic, style_label: str) -> float:
    text = " ".join([script_payload["hook"], *script_payload["lines"], script_payload["cta"]]).lower()
    power_words = ["truth", "save", "share", "today", "secret", "real", "freedom", "choose", "stop"]
    score = 5.0
    score += min(2.5, sum(1 for w in power_words if w in text) * 0.3)

    if topic == Topic.CULTURE and "both" in text:
        score += 0.6
    if topic == Topic.FINANCE and "automate" in text:
        score += 0.6
    if topic == Topic.RELATIONSHIPS and "love" in text:
        score += 0.6
    if topic == Topic.HEALTH and "sleep" in text:
        score += 0.6
    if "deep" in style_label:
        score += 0.3

    line_lengths = [len(x.split()) for x in script_payload["lines"]]
    if line_lengths and min(line_lengths) >= 3 and max(line_lengths) <= 8:
        score += 0.8

    return float(max(1.0, min(10.0, round(score, 2))))


def _llm_virality_score(script_payload: dict[str, Any], topic: Topic) -> float:
    prompt = (
        "Rate this short-form script from 1.0 to 10.0 for likely retention and shares. "
        "Respond with JSON only: {\"score\": 7.4}.\n"
        f"Topic: {topic.value}\n"
        f"Script: {json.dumps(script_payload)}"
    )

    try:
        raw = _call_anthropic(prompt)
        parsed = json.loads(raw)
        score = float(parsed.get("score", 0))
        if 1 <= score <= 10:
            return round(score, 2)
    except Exception:
        pass

    return _heuristic_virality_score(script_payload, topic, "")


def _generate_raw_script(prompt: str, topic: Topic, style_label: str) -> str:
    for caller in (_call_anthropic, _call_grok, _call_ollama):
        try:
            return caller(prompt)
        except Exception:
            continue
    return _fallback_script(topic, style_label)


def generate_script_variants(
    topic: Topic | None = None,
    count: int = 3,
    fast_mode: bool = False,
) -> tuple[Topic, list[ScriptVariant]]:
    chosen_topic = topic or random.choice(list(Topic))
    styles = [
        STYLE_MAP[chosen_topic.value],
        f"{STYLE_MAP[chosen_topic.value]} with urgency",
        f"{STYLE_MAP[chosen_topic.value]} with reflective twist",
        f"{STYLE_MAP[chosen_topic.value]} with contrarian edge",
    ]

    variants: list[ScriptVariant] = []
    for idx in range(count):
        style_label = styles[idx % len(styles)]
        prompt = _topic_prompt(chosen_topic) + f"\n\nVoice/style target: {style_label}."
        raw_text = _generate_raw_script(prompt, chosen_topic, style_label)
        payload = parse_script(raw_text)

        heuristic = _heuristic_virality_score(payload, chosen_topic, style_label)
        if fast_mode:
            score = heuristic
        else:
            llm_bonus = _llm_virality_score(payload, chosen_topic)
            score = round((heuristic * 0.65) + (llm_bonus * 0.35), 2)

        variants.append(
            ScriptVariant(
                variant_index=idx,
                style_label=style_label,
                script_payload=payload,
                virality_score=score,
            )
        )

    variants.sort(key=lambda v: v.virality_score, reverse=True)
    return chosen_topic, variants
