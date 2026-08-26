from datetime import datetime
from pathlib import Path

from utils.logger import ROOT, load_json, save_json


def should_run(interval_days: int, state_file: str) -> tuple[bool, str]:
    path = ROOT / state_file
    data = load_json(path)
    last = data.get("last_success_at")
    if not last:
        return True, "无历史成功记录，允许运行"

    last_dt = datetime.fromisoformat(last)
    now = datetime.now()
    delta_days = (now - last_dt).total_seconds() / 86400
    if delta_days < interval_days:
        return False, f"距上次成功仅 {delta_days:.1f} 天，需间隔 {interval_days} 天"
    return True, f"距上次成功 {delta_days:.1f} 天，允许运行"


def mark_success(state_file: str, url: str, output_dir: Path) -> None:
    path = ROOT / state_file
    path.parent.mkdir(parents=True, exist_ok=True)
    save_json(
        path,
        {
            "last_success_at": datetime.now().isoformat(timespec="seconds"),
            "last_url": url,
            "last_output_dir": str(output_dir.relative_to(ROOT)),
        },
    )


def write_meta(output_dir: Path, *, success: bool, duration_sec: float, error: str = "") -> None:
    save_json(
        output_dir / "meta.json",
        {
            "success": success,
            "duration_sec": round(duration_sec, 2),
            "error_message": error,
            "finished_at": datetime.now().isoformat(timespec="seconds"),
        },
    )
