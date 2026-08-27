# -*- coding: utf-8 -*-
"""AI content generation."""

import json
import os
import re
from typing import Any

from openai import OpenAI

from utils.logger import ROOT


class ContentGenerationError(Exception):
    pass


def _load_prompt_template(prompt_file: str) -> str:
    path = ROOT / prompt_file
    return path.read_text(encoding="utf-8")


def _parse_json_response(text: str) -> dict[str, str]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    data = json.loads(text)
    if not isinstance(data, dict):
        raise ContentGenerationError("AI response is not a JSON object")
    title = str(data.get("title", "")).strip()
    body = str(data.get("body", "")).strip()
    if not title or not body:
        raise ContentGenerationError("AI title or body is empty")
    return {"title": title, "body": body}


def _validate_content(content: dict[str, str], ai_cfg: dict[str, Any]) -> None:
    title = content["title"]
    body = content["body"]
    min_len = ai_cfg["min_body_length"]
    max_len = ai_cfg["max_body_length"]

    if not (10 <= len(title) <= 40):
        raise ContentGenerationError(f"title length {len(title)} not in 10-40")
    if not (min_len <= len(body) <= max_len):
        raise ContentGenerationError(f"body length {len(body)} not in {min_len}-{max_len}")

    for kw in ai_cfg.get("required_keywords", []):
        if kw not in body:
            raise ContentGenerationError(f"missing required keyword: {kw}")


def _render_prompt(template: str, **values: str | int) -> str:
    result = template
    for key, value in values.items():
        result = result.replace(f"{{{key}}}", str(value))
    return result


def generate_content(config: dict[str, Any]) -> dict[str, str]:
    ai_cfg = config["ai"]
    api_key = os.environ.get(ai_cfg["api_key_env"], "")
    if not api_key:
        raise ContentGenerationError(
            f"env {ai_cfg['api_key_env']} is empty, set it in .env"
        )

    template = _load_prompt_template(ai_cfg["prompt_file"])
    topics = "\u3001".join(config["zhihu"]["topics"])
    prompt = _render_prompt(
        template,
        min_body_length=ai_cfg["min_body_length"],
        max_body_length=ai_cfg["max_body_length"],
        topics=topics,
    )

    client = OpenAI(api_key=api_key, base_url=ai_cfg["api_base"])
    max_retries = ai_cfg.get("max_retries", 3)
    last_error: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=ai_cfg["model"],
                messages=[{"role": "user", "content": prompt}],
                temperature=0.9,
            )
            raw = response.choices[0].message.content or ""
            content = _parse_json_response(raw)
            _validate_content(content, ai_cfg)
            return content
        except Exception as exc:
            last_error = exc
            if attempt < max_retries:
                continue
            raise ContentGenerationError(f"AI generate failed after {max_retries}: {exc}") from exc

    raise ContentGenerationError(f"AI generate failed: {last_error}")
