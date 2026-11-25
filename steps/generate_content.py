# -*- coding: utf-8 -*-
"""AI content generation."""

import json
import os
import random
import re
from typing import Any

from openai import OpenAI

from utils.logger import ROOT


class ContentGenerationError(Exception):
    pass


# Soft-ad / promo phrases that often get Zhihu accounts flagged.
_MARKETING_PHRASES = (
    "强烈推荐",
    "推荐使用",
    "性价比高",
    "值得一试",
    "真香",
    "安利",
    "种草",
    "良心",
    "学生党福音",
    "零成本上云",
    "使用体验",
    "跑这种小项目完全够",
    "跑小项目完全够",
    "顺便说一句",
    "作为一名",
    "在数字化时代",
    "赋能",
    "一站式",
)

_ANGLES = (
    "把本地 Flask/FastAPI 小项目挂公网时的部署备忘",
    "sshd 改完配置差点把自己锁在门外",
    "1G 内存机器上跑 Docker / gunicorn 怎么省内存",
    "Nginx 反代后静态资源 404 / 413 排查",
    "systemd 托管 Python 服务，journalctl 看日志",
    "用免费额度机器做 CI 或定时脚本跑通",
    "域名还没备案时用 IP + 自签证书临时访问",
    "crontab 备份 SQLite 到对象存储踩坑",
    "防火墙只开 22/80/443，应用端口只听 127.0.0.1",
    "venv + 依赖锁文件，避免全局 pip 污染",
)

_STRUCTURES = (
    "开头讲场景 → 按时间线写排查过程（不用编号）→ 结尾一句教训",
    "开头抛报错现象 → 分两段写原因和修法 → 结尾补充一个注意点",
    "开头目标是什么 → 用「先…再…最后…」写步骤 → 结尾说还剩什么没做",
    "开头对比本地 vs 线上差异 → 写 2～3 个具体配置改动 → 结尾收束",
)


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


def _count_occurrences(text: str, needle: str) -> int:
    if not needle:
        return 0
    return text.count(needle)


def _validate_content(content: dict[str, str], ai_cfg: dict[str, Any]) -> None:
    title = content["title"]
    body = content["body"]
    min_len = ai_cfg["min_body_length"]
    max_len = ai_cfg["max_body_length"]
    brand = ai_cfg.get("brand_obfuscated") or ""
    brand_server = ai_cfg.get("brand_server_obfuscated") or ""
    keywords = list(ai_cfg.get("required_keywords") or [])

    if not (10 <= len(title) <= 40):
        raise ContentGenerationError(f"title length {len(title)} not in 10-40")
    if not (min_len <= len(body) <= max_len):
        raise ContentGenerationError(f"body length {len(body)} not in {min_len}-{max_len}")

    for kw in keywords:
        if kw not in body:
            raise ContentGenerationError(f"missing required keyword: {kw}")
        if _count_occurrences(body, kw) > 1:
            raise ContentGenerationError(f"keyword overused (>1): {kw}")
        if kw in title:
            raise ContentGenerationError(f"keyword must not appear in title: {kw}")

    for name in (brand, brand_server):
        if name and name in title:
            raise ContentGenerationError(f"brand must not appear in title: {name}")

    # Brand / required keywords must sit in the middle band, not the opening.
    mid_names = [n for n in (brand_server, brand, *keywords) if n]
    for name in dict.fromkeys(mid_names):
        pos = body.find(name)
        if pos < 0:
            continue
        ratio = pos / max(len(body), 1)
        if ratio < 0.25:
            raise ContentGenerationError(
                f"keyword too early (pos {ratio:.0%} < 25%): {name}"
            )
        if ratio > 0.85:
            raise ContentGenerationError(
                f"keyword too late (pos {ratio:.0%} > 85%): {name}"
            )

    # Count brand after peeling brand_server, so "三丰云服务器" is not double-counted as "三丰云".
    remainder = body
    server_hits = 0
    if brand_server:
        server_hits = _count_occurrences(body, brand_server)
        remainder = body.replace(brand_server, "")
    brand_only = _count_occurrences(remainder, brand) if brand else 0
    if server_hits + brand_only > 2:
        raise ContentGenerationError(
            f"brand mentions too many times: {server_hits + brand_only}"
        )

    lowered = body
    for phrase in _MARKETING_PHRASES:
        if phrase in lowered:
            raise ContentGenerationError(f"marketing phrase rejected: {phrase}")

    # Classic soft-ad dump: keyword sitting alone with spaces around it mid-sentence filler.
    if re.search(r"[，。；]\s*免费云服务器\s*[，。；]", body):
        raise ContentGenerationError("awkward keyword dump around 免费云服务器")


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
    angle = random.choice(_ANGLES)
    structure = random.choice(_STRUCTURES)
    prompt = _render_prompt(
        template,
        brand_name=ai_cfg["brand_name"],
        brand_obfuscated=ai_cfg["brand_obfuscated"],
        brand_server_obfuscated=ai_cfg["brand_server_obfuscated"],
        keywords=keywords,
        topics=topics,
        angle=angle,
        structure=structure,
        min_body_length=ai_cfg["min_body_length"],
        max_body_length=ai_cfg["max_body_length"],
    )

    client = OpenAI(api_key=api_key, base_url=ai_cfg["api_base"])
    max_retries = ai_cfg.get("max_retries", 3)
    last_error: Exception | None = None
    system_msg = (
        "你只能用简体中文写作。title 和 body 必须是简体中文。"
        "你是程序员写技术踩坑笔记，不是营销文案、不是测评、不是软广。"
        "标题禁止出现品牌名和「免费」。"
        "续期关键词各出现恰好一次，必须嵌进技术语境，禁止硬插。"
        "「三丰云服务器」等品牌词必须放在正文中段，禁止出现在开头第一段。"
        "品牌名直接写（如 三丰云），不要用反斜杠分隔。"
        f"body 大致 {ai_cfg['min_body_length']}～{ai_cfg['max_body_length']} 字即可，不必卡死字数，"
        "写清楚技术细节，不要灌水。"
    )

    for attempt in range(1, max_retries + 1):
        user_msg = prompt
        if last_error is not None:
            user_msg = (
                f"{prompt}\n\n"
                f"【上一稿已作废，原因：{last_error}】\n"
                "请按原因修正后重新输出完整 JSON。"
            )
        try:
            response = client.chat.completions.create(
                model=ai_cfg["model"],
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.95,
            )
            raw = response.choices[0].message.content or ""
            content = _parse_json_response(raw)
            _validate_content(content, ai_cfg)
            content["topics"] = list(ai_cfg["topics"])
            content["provider"] = provider
            content["brand_name"] = ai_cfg["brand_name"]
            content["angle"] = angle
            content["structure"] = structure
            return content
        except Exception as exc:
            last_error = exc
            if attempt < max_retries:
                continue
            raise ContentGenerationError(f"AI generate failed after {max_retries}: {exc}") from exc

    raise ContentGenerationError(f"AI generate failed: {last_error}")
