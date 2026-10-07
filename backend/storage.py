"""Private JSON snapshots with atomic replacement and process-local serialization."""
import json
import os
import threading
import uuid
from pathlib import Path
from datetime import datetime, timezone, timedelta
ROOT = Path(__file__).resolve().parents[1]
TZ = timezone(timedelta(hours=8))
LOCK = threading.RLock()

def now():
    return datetime.now(TZ).isoformat(timespec="seconds")

def read(path, default=None):
    return json.loads(Path(path).read_text(encoding="utf-8")) if Path(path).exists() else default

def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    with temporary.open("x", encoding="utf-8") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)

def timestamp(value):
    try:
        parsed = datetime.fromisoformat(value)
    except (ValueError, TypeError):
        raise ValueError("时间须为 ISO 8601 格式") from None
    if parsed.tzinfo is None:
        raise ValueError("时间必须包含时区，例如 +08:00")
    return parsed.astimezone(TZ)

