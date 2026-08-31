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


def _provider_content_cfg(config: dict[str, Any], provider: str) -> dict[str, Any]:
    ai_cfg = config["ai"]
    content = (config.get(provider) or {}).get("content") or {}
    brand_name = content.get("brand_name") or provider
    brand_obfuscated = content.get("brand_obfuscated") or brand_name
    brand_server_obfuscated = content.get("brand_server_obfuscated") or brand_obfuscated
    return {
        "brand_name": brand_name,
        "brand_obfuscated": brand_obfuscated,
        "brand_server_obfuscated": brand_server_obfuscated,
        "topics": content.get("topics") or [],
        "required_keywords": content.get("required_keywords") or [],
        "prompt_file": content.get("prompt_file") or ai_cfg["prompt_file"],
        "min_body_length": ai_cfg["min_body_length"],
        "max_body_length": ai_cfg["max_body_length"],
        "max_retries": ai_cfg.get("max_retries", 3),
        "api_base": ai_cfg["api_base"],
        "api_key_env": ai_cfg["api_key_env"],
        "model": ai_cfg["model"],
    }


def generate_content(config: dict[str, Any], provider: str) -> dict[str, str]:
    ai_cfg = _provider_content_cfg(config, provider)
    api_key = os.environ.get(ai_cfg["api_key_env"], "")
    if not api_key:
        raise ContentGenerationError(
            f"env {ai_cfg['api_key_env']} is empty, set it in .env"
        )

    template = _load_prompt_template(ai_cfg["prompt_file"])
    topics = "\u3001".join(ai_cfg["topics"])
    keywords = "\u3001".join(ai_cfg["required_keywords"])
    prompt = _render_prompt(
        template,
        brand_name=ai_cfg["brand_name"],
        brand_obfuscated=ai_cfg["brand_obfuscated"],
        brand_server_obfuscated=ai_cfg["brand_server_obfuscated"],
        keywords=keywords,
        topics=topics,
        min_body_length=ai_cfg["min_body_length"],
        max_body_length=ai_cfg["max_body_length"],
    )

    client = OpenAI(api_key=api_key, base_url=ai_cfg["api_base"])
    max_retries = ai_cfg.get("max_retries", 3)
    last_error: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=ai_cfg["model"],
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你只能用简体中文写作。title 和 body 必须是简体中文。"
                            "你是程序员在博客园写技术笔记，不是营销文案写手。"
                            "品牌名必须用反斜杠分隔字符（如 三\\丰\\云），禁止连续写三丰云/阿贝云。"
                            "文章要有开头、1/2/3 分点、结尾，语气真实自然，侧重技术分享。"
                            f"硬性限制：body 字数（含标点）必须在 "
                            f"{ai_cfg['min_body_length']}-{ai_cfg['max_body_length']} 之间，"
                            "宁短勿长，超字数整篇作废。"
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.9,
            )
            raw = response.choices[0].message.content or ""
            content = _parse_json_response(raw)
            _validate_content(content, ai_cfg)
            content["topics"] = list(ai_cfg["topics"])
            content["provider"] = provider
            content["brand_name"] = ai_cfg["brand_name"]
            return content
        except Exception as exc:
            last_error = exc
            if attempt < max_retries:
                continue
            raise ContentGenerationError(f"AI generate failed after {max_retries}: {exc}") from exc

    raise ContentGenerationError(f"AI generate failed: {last_error}")
