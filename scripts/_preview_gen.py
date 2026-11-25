# -*- coding: utf-8 -*-
"""One-off: generate sample articles without posting."""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
import yaml

from steps.generate_content import generate_content


def main() -> None:
    load_dotenv(ROOT / ".env")
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    out_path = ROOT / "output" / "_preview_gen.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    results = []
    providers = sys.argv[1:] or ["sanfeng", "sanfeng2"]
    for provider in providers:
        print(f"generating {provider} ...", flush=True)
        try:
            content = generate_content(cfg, provider)
            item = {
                "provider": provider,
                "title": content["title"],
                "angle": content.get("angle"),
                "structure": content.get("structure"),
                "len": len(content["body"]),
                "body": content["body"],
            }
            results.append(item)
            print(f"  ok title={content['title']!r} len={len(content['body'])}", flush=True)
        except Exception as exc:
            results.append({"provider": provider, "error": str(exc), "trace": traceback.format_exc()})
            print(f"  FAIL: {exc}", flush=True)

    if out_path.exists():
        try:
            prev = json.loads(out_path.read_text(encoding="utf-8"))
            if isinstance(prev, list) and len(providers) < 2:
                by_p = {x.get("provider"): x for x in prev if isinstance(x, dict)}
                for item in results:
                    by_p[item["provider"]] = item
                results = list(by_p.values())
        except Exception:
            pass

    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out_path}", flush=True)


if __name__ == "__main__":
    main()
