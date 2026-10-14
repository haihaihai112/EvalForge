import os
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_env():
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def price(name):
    value = os.getenv(name, "").strip()
    if not value:
        return None
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{name} 必须为有限非负数")
    return number


def model_config():
    api_key = os.getenv("EVALFORGE_API_KEY", "").strip()
    base = os.getenv("EVALFORGE_API_BASE", "").strip()
    model = os.getenv("EVALFORGE_MODEL", "").strip()
    if not all((api_key, base, model)):
        raise ValueError("真实模式需要配置 EVALFORGE_API_KEY、EVALFORGE_API_BASE、EVALFORGE_MODEL")
    return {"base_url": base, "api_key": api_key, "model": model,
            "input_price": price("EVALFORGE_INPUT_PRICE"), "output_price": price("EVALFORGE_OUTPUT_PRICE")}


def public_config():
    return {"model_configured": bool(os.getenv("EVALFORGE_API_KEY") and os.getenv("EVALFORGE_API_BASE") and os.getenv("EVALFORGE_MODEL")),
            "model": os.getenv("EVALFORGE_MODEL", "未配置"),
            "agents_configured": all(os.getenv(f"EVALFORGE_AGENT_{i}_URL") for i in (1, 2)),
            "versions": [os.getenv(f"EVALFORGE_AGENT_{i}_NAME", f"Agent v{i}") for i in (1, 2)]}
