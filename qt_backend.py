"""Standalone backend used by the PySide6 OCR interface.

This module owns the OCR API calls and persistent data store.  It intentionally
has no dependency on the legacy Tk application in ``ocr.py``.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import io
import json
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from PIL import Image
from PySide6.QtCore import QObject, QRunnable, Signal, Slot


APP_DIR = (Path(sys.executable).resolve().parent if getattr(sys, "frozen", False)
           else Path(__file__).resolve().parent)

# Load the external .env.  This also works in a one-folder PyInstaller build,
# where user configuration stays beside the executable.
env_path = APP_DIR / ".env"
if env_path.exists():
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ[key.strip()] = value.strip()


API_KEY = os.getenv("BAIDU_API_KEY", "")
SECRET_KEY = os.getenv("BAIDU_SECRET_KEY", "")
API_KEY_BASIC = os.getenv("BAIDU_API_KEY_BASIC", "")
SECRET_KEY_BASIC = os.getenv("BAIDU_SECRET_KEY_BASIC", "")
API_KEY_GENERAL = os.getenv("BAIDU_API_KEY_GENERAL", "")
SECRET_KEY_GENERAL = os.getenv("BAIDU_SECRET_KEY_GENERAL", "")

_token_cache: dict[str, dict[str, Any]] = {}


DATA_FILE = APP_DIR / "ocr_data.json"
CLASSIFIER_HISTORY_LIMIT = 100

MODE_NAMES = {
    "accurate": "高精度",
    "basic": "快速",
    "general": "通用",
}


def _is_network_error(exc: Exception) -> bool:
    """Return whether an exception looks like a network connection failure."""
    message = str(exc).lower()
    return any(keyword in message for keyword in (
        "connectionerror", "timeout", "ssl", "eof", "max retries",
        "connection refused", "network", "socket", "httpsconnectionpool",
        "remotedisconnected", "connection reset",
    ))


def _friendly_error_msg(exc: Exception) -> str:
    if _is_network_error(exc):
        return "网络连接失败，请检查网络后重试"
    return str(exc)


def update_credentials(values: dict[str, str]) -> None:
    """Apply credentials edited in the UI without restarting the application."""
    global API_KEY, SECRET_KEY, API_KEY_BASIC, SECRET_KEY_BASIC
    global API_KEY_GENERAL, SECRET_KEY_GENERAL

    API_KEY = values.get("BAIDU_API_KEY", "")
    SECRET_KEY = values.get("BAIDU_SECRET_KEY", "")
    API_KEY_BASIC = values.get("BAIDU_API_KEY_BASIC", "")
    SECRET_KEY_BASIC = values.get("BAIDU_SECRET_KEY_BASIC", "")
    API_KEY_GENERAL = values.get("BAIDU_API_KEY_GENERAL", "")
    SECRET_KEY_GENERAL = values.get("BAIDU_SECRET_KEY_GENERAL", "")
    _token_cache.clear()


def get_access_token(use_basic: bool = False, use_general: bool = False) -> str:
    """Request and cache a Baidu access token for the selected OCR mode."""
    cache_key = "general" if use_general else "basic" if use_basic else "accurate"
    cached = _token_cache.get(cache_key)
    if cached and cached["expires"] > time.time():
        return str(cached["token"])

    if use_general:
        api_key, secret_key = API_KEY_GENERAL, SECRET_KEY_GENERAL
    elif use_basic:
        api_key, secret_key = API_KEY_BASIC, SECRET_KEY_BASIC
    else:
        api_key, secret_key = API_KEY, SECRET_KEY

    if not api_key or not secret_key:
        raise ValueError(f"{MODE_NAMES[cache_key]}识别密钥未配置")

    response = requests.post(
        "https://aip.baidubce.com/oauth/2.0/token",
        params={
            "grant_type": "client_credentials",
            "client_id": api_key,
            "client_secret": secret_key,
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    token = payload.get("access_token")
    if not token:
        raise RuntimeError(payload.get("error_description") or payload.get("error") or "获取百度访问令牌失败")

    expires_in = int(payload.get("expires_in", 2592000))
    _token_cache[cache_key] = {
        "token": token,
        "expires": time.time() + max(0, expires_in - 300),
    }
    return str(token)


def get_file_content_as_base64(path: str, max_size: int = 8192,
                               max_file_size_mb: float = 3.5) -> str | None:
    """Read an image as base64, resizing or recompressing it when necessary."""
    try:
        file_size_mb = os.path.getsize(path) / (1024 * 1024)
        with Image.open(path) as source:
            image = source.copy()
        width, height = image.size
        needs_compression = width > max_size or height > max_size or file_size_mb > max_file_size_mb

        if not needs_compression:
            with open(path, "rb") as stream:
                return base64.b64encode(stream.read()).decode("utf-8")

        scale = min(1.0, max_size / width, max_size / height)
        if scale < 1.0:
            image = image.resize(
                (max(1, int(width * scale)), max(1, int(height * scale))),
                Image.Resampling.LANCZOS,
            )
        if image.mode not in ("RGB", "L"):
            background = Image.new("RGB", image.size, "white")
            if "A" in image.getbands():
                background.paste(image, mask=image.getchannel("A"))
            else:
                background.paste(image)
            image = background

        initial_quality = 60 if file_size_mb > 10 else 70 if file_size_mb > 5 else 80 if file_size_mb > 3 else 85
        compressed = b""
        for quality in (initial_quality, 50, 40, 30, 20):
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=quality, optimize=True)
            compressed = buffer.getvalue()
            if len(compressed) / (1024 * 1024) <= max_file_size_mb:
                break
        return base64.b64encode(compressed).decode("utf-8")
    except Exception:
        try:
            with open(path, "rb") as stream:
                return base64.b64encode(stream.read()).decode("utf-8")
        except OSError:
            return None


def _ocr_request(image_path: str, endpoint: str, *, use_basic: bool = False,
                 use_general: bool = False, max_size: int = 8192,
                 max_file_size_mb: float = 3.5,
                 multidirectional: bool = False) -> dict[str, Any]:
    token = get_access_token(use_basic=use_basic, use_general=use_general)
    image_base64 = get_file_content_as_base64(image_path, max_size, max_file_size_mb)
    if image_base64 is None:
        return {"error_msg": "图片处理失败", "error_code": -1}

    payload = {
        "image": image_base64,
        "detect_direction": "false",
        "paragraph": "false",
        "probability": "true",
    }
    if multidirectional:
        payload["multidirectional_recognize"] = "false"
    response = requests.post(
        f"https://aip.baidubce.com/rest/2.0/ocr/v1/{endpoint}?access_token={token}",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        data=payload,
        timeout=120,
    )
    response.raise_for_status()
    response.encoding = "utf-8"
    return response.json()


def ocr_image(image_path: str) -> dict[str, Any]:
    """Recognize an image with Baidu's high-accuracy endpoint."""
    return _ocr_request(
        image_path, "accurate", max_file_size_mb=3.8, multidirectional=True,
    )


def ocr_image_basic(image_path: str) -> dict[str, Any]:
    """Recognize an image with the fast general endpoint."""
    return _ocr_request(
        image_path, "general", use_basic=True, max_size=8100,
    )


def ocr_image_general(image_path: str) -> dict[str, Any]:
    """Recognize an image with the accurate-basic endpoint."""
    return _ocr_request(
        image_path, "accurate_basic", use_general=True, max_size=8100,
        multidirectional=True,
    )


MODE_CALLS = {
    "accurate": ocr_image,
    "basic": ocr_image_basic,
    "general": ocr_image_general,
}


def key_available(mode: str) -> bool:
    if mode == "accurate":
        return bool(API_KEY and SECRET_KEY)
    if mode == "basic":
        return bool(API_KEY_BASIC and SECRET_KEY_BASIC)
    return bool(API_KEY_GENERAL and SECRET_KEY_GENERAL)


def image_hash(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def format_words_result(payload: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for item in payload.get("words_result", []):
        location = item.get("location", {}) or {}
        probability = item.get("probability", {}) or {}
        confidence = int(probability.get("average", 0) * 100) if isinstance(probability, dict) else 0
        lines.append(
            f"{item.get('words', '')}|{location.get('top', 0)}|"
            f"{location.get('left', 0)}|{location.get('height', 0)}|{confidence}"
        )
    return lines


def extract_word_boxes(payload: dict[str, Any]) -> list[dict[str, int]]:
    """Preserve the full OCR location separately from the legacy text format."""
    boxes: list[dict[str, int]] = []
    for item in payload.get("words_result", []):
        location = item.get("location", {}) or {}
        boxes.append({
            "left": int(location.get("left", 0) or 0),
            "top": int(location.get("top", 0) or 0),
            "width": int(location.get("width", 0) or 0),
            "height": int(location.get("height", 0) or 0),
        })
    return boxes


def parse_line(line: str) -> dict[str, Any]:
    parts = str(line).rsplit("|", 4)
    while len(parts) < 5:
        parts.append("0")
    label, top, left, height, confidence = parts

    def number(value: str) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    return {
        "label": label,
        "y": number(top),
        "x": number(left),
        "width": 0.0,
        "height": number(height),
        "confidence": int(number(confidence)),
        "group": "B",
    }


class DataStore:
    """JSON-backed application data store compatible with the legacy schema."""

    DEFAULT_DATA = {
        "window_config": {},
        "stats": {},
        "history": [],
        "history_limit": 100,
        "classifier_history": [],
        "classifier_history_limit": 100,
        "ocr_cache": {},
        "size_limits": {},
        "font_config": {"font_size": 11},
        "popup_windows": {},
        "merge_save_path": "",
        "export_save_path": "",
        "merge_history": [],
        "gallery_ocr_limit": 30,
        "preview_ocr_defaults": {
            "merge": "accurate",
            "crop": "general",
            "screenshot": "general",
        },
        "tree_column_widths": {},
    }

    def __init__(self, filepath: str | Path) -> None:
        self.filepath = Path(filepath)
        self.data = copy.deepcopy(self.DEFAULT_DATA)
        self.load()

    def load(self) -> None:
        if not self.filepath.exists():
            return
        try:
            with self.filepath.open("r", encoding="utf-8") as stream:
                saved = json.load(stream)
            if not isinstance(saved, dict):
                raise ValueError("数据文件的顶层内容必须是对象")
            self.data.update(saved)
        except Exception as exc:
            print(f"加载数据文件失败: {exc}")

    def save(self) -> None:
        try:
            self.filepath.parent.mkdir(parents=True, exist_ok=True)
            with self.filepath.open("w", encoding="utf-8") as stream:
                json.dump(self.data, stream, ensure_ascii=False, indent=2)
        except Exception as exc:
            print(f"保存数据文件失败: {exc}")

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value
        self.save()


class Repository:
    """Compatibility wrapper around the existing JSON store and schemas."""

    DEFAULT_LIMITS = {
        "accurate_min_width": 3500,
        "accurate_min_height": 4000,
        "accurate_max_width": 15000,
        "accurate_max_height": 15000,
        "basic_min_width": 0,
        "basic_min_height": 0,
        "basic_max_width": 8100,
        "basic_max_height": 3000,
        "general_min_width": 0,
        "general_min_height": 0,
        "general_max_width": 8192,
        "general_max_height": 8192,
    }

    def __init__(self) -> None:
        self.store = DataStore(DATA_FILE)

    def get(self, key: str, default: Any = None) -> Any:
        return self.store.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.store.set(key, value)

    def reload(self) -> None:
        self.store.load()

    def daily_ocr_limit_config(self, mode: str) -> dict[str, Any]:
        """Return the saved limit configuration for a restricted OCR mode."""
        if mode not in {"accurate", "general"}:
            return {"enabled": False, "max_count": 0, "date": "", "used": 0}
        limits = self.get("daily_ocr_limits", {}) or {}
        raw = limits.get(mode, {}) if isinstance(limits, dict) else {}
        # Read the previous single-limit setting when upgrading existing data.
        if not isinstance(raw, dict) or not raw:
            raw = self.get("daily_ocr_limit", {}) or {}
        return dict(raw) if isinstance(raw, dict) else {}

    def daily_ocr_limit_status(self, mode: str) -> tuple[bool, int, int]:
        """Return whether the selected OCR mode allows another batch today."""
        if mode not in {"accurate", "general"}:
            return True, 0, 0
        raw = self.daily_ocr_limit_config(mode)
        enabled = bool(raw.get("enabled", False))
        try:
            max_count = max(1, int(raw.get("max_count", 10)))
            used = max(0, int(raw.get("used", 0)))
        except (TypeError, ValueError):
            max_count, used = 10, 0
        today = datetime.now().strftime("%Y-%m-%d")
        if str(raw.get("date", "")) != today:
            used = 0
        return (not enabled or used < max_count), used, max_count

    def consume_daily_ocr_limit(self, mode: str, increment: bool = True) -> tuple[bool, int, int]:
        """Reserve one batch for the selected restricted OCR mode.
        
        Args:
            mode: OCR mode ('accurate' or 'general')
            increment: If True, actually consume one quota; if False, only check
        
        Returns:
            (allowed, used_count, max_count)
        """
        if mode not in {"accurate", "general"}:
            return True, 0, 0
        raw = self.daily_ocr_limit_config(mode)
        enabled = bool(raw.get("enabled", False))
        try:
            max_count = max(1, int(raw.get("max_count", 10)))
            used = max(0, int(raw.get("used", 0)))
        except (TypeError, ValueError):
            max_count, used = 10, 0
        today = datetime.now().strftime("%Y-%m-%d")
        if str(raw.get("date", "")) != today:
            used = 0
        if enabled and used >= max_count:
            return False, used, max_count
        if enabled and increment:
            raw.update({"enabled": True, "max_count": max_count, "date": today, "used": used + 1})
            limits = self.get("daily_ocr_limits", {}) or {}
            limits = dict(limits) if isinstance(limits, dict) else {}
            limits[mode] = raw
            self.set("daily_ocr_limits", limits)
            used += 1
        return True, used, max_count

    def limits(self) -> dict[str, int]:
        result = dict(self.DEFAULT_LIMITS)
        result.update(self.get("size_limits", {}) or {})
        return result

    def mode_allowed_for_size(self, width: int, height: int, mode: str) -> tuple[bool, str]:
        if mode not in MODE_NAMES:
            return False, f"未知识别模式：{mode}"
        if width <= 0 or height <= 0:
            return False, "图片尺寸无效"
        limits = self.limits()
        ok = (
            limits[f"{mode}_min_width"] <= width <= limits[f"{mode}_max_width"]
            and limits[f"{mode}_min_height"] <= height <= limits[f"{mode}_max_height"]
        )
        range_text = (
            f"宽 {limits[f'{mode}_min_width']}~{limits[f'{mode}_max_width']}，"
            f"高 {limits[f'{mode}_min_height']}~{limits[f'{mode}_max_height']}"
        )
        if ok:
            return True, f"{width} × {height}；{range_text}"
        return False, f"{width} × {height} 不符合{MODE_NAMES[mode]}规则（{range_text}）"

    def mode_allowed_for_image(self, path: str, mode: str) -> tuple[bool, str]:
        try:
            with Image.open(path) as image:
                width, height = image.size
        except Exception as exc:
            return False, f"无法读取图片：{exc}"
        return self.mode_allowed_for_size(width, height, mode)

    def cached(self, path: str, mode: str) -> tuple[str, dict[str, Any] | None]:
        digest = image_hash(path)
        record = (self.get("ocr_cache", {}) or {}).get(f"{mode}:{digest}")
        if not record:
            return digest, None
        lines = list(record.get("lines", []))
        boxes = copy.deepcopy(record.get("boxes", []))
        has_exact_boxes = (
            isinstance(boxes, list)
            and len(boxes) == len(lines)
            and all(
                isinstance(box, dict)
                and int(box.get("width", 0) or 0) > 0
                and int(box.get("height", 0) or 0) > 0
                for box in boxes
            )
        )
        # Legacy cache records omitted width. Treat them as stale so the next
        # recognition upgrades them with the API's exact location boxes.
        if not has_exact_boxes:
            return digest, None
        return digest, {
            "file": os.path.basename(path),
            "path": path,
            "type": mode,
            "lines": lines,
            "boxes": boxes,
            "count": len(lines),
            "cached": True,
            "image_hash": digest,
        }

    def save_cache(self, digest: str, mode: str, path: str, lines: list[str],
                   boxes: list[dict[str, int]] | None = None) -> None:
        if not digest or not lines:
            return
        cache = self.get("ocr_cache", {}) or {}
        cache[f"{mode}:{digest}"] = {
            "hash": digest,
            "type": mode,
            "file": os.path.basename(path),
            "path": path,
            "lines": lines,
            "boxes": copy.deepcopy(boxes or []),
            "line_count": len(lines),
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.set("ocr_cache", cache)

    def save_history_and_stats(self, mode: str, results: list[dict[str, Any]],
                               book_name: str, start_page: int) -> None:
        history = self.get("history", []) or []
        history_limit = int(self.get("history_limit", 100) or 100)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        page = start_page
        for result in results:
            if result.get("error") or result.get("skipped") or not result.get("lines"):
                continue
            history.insert(0, {
                "timestamp": timestamp,
                "type": MODE_NAMES.get(mode, mode),
                "file_count": 1,
                "total_lines": len(result["lines"]),
                "book_name": book_name,
                "page_no": page,
                "files": [{
                    "name": result.get("file", ""),
                    "content": list(result["lines"]),
                    "boxes": copy.deepcopy(result.get("boxes", [])),
                    "lines": len(result["lines"]),
                    "image_hash": result.get("image_hash", ""),
                }],
            })
            page += 1
        self.set("history", history[:history_limit])
        self.set("book_page", page)

        stats = self.get("stats", {}) or {}
        day = datetime.now().strftime("%Y-%m-%d")
        day_data = stats.setdefault(day, {})
        mode_stats = day_data.setdefault(mode, {})
        defaults = {
            "count": 0, "processed": 0, "success": 0, "failed": 0,
            "cached": 0, "lines": 0, "api_lines": 0, "cached_lines": 0,
        }
        for key, value in defaults.items():
            mode_stats.setdefault(key, value)
        mode_stats["count"] += 1
        mode_stats["processed"] += len(results)
        for result in results:
            count = len(result.get("lines", []))
            mode_stats["lines"] += count
            if result.get("cached"):
                mode_stats["cached"] += 1
                mode_stats["cached_lines"] += count
            elif result.get("error") or result.get("skipped"):
                mode_stats["failed"] += 1
            else:
                mode_stats["success"] += 1
                mode_stats["api_lines"] += count
        self.set("stats", stats)

    def save_classifier_history(self, snapshot: dict[str, Any], book_name: str,
                                page_no: int) -> None:
        """Save an editable classification-table snapshot separately from OCR history."""
        history = list(self.get("classifier_history", []) or [])
        timestamp = datetime.now()
        history.insert(0, {
            "id": timestamp.strftime("%Y%m%d%H%M%S%f"),
            "timestamp": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "book_name": str(book_name or ""),
            "page_no": int(page_no),
            "row_count": len(snapshot.get("rows", []) or []),
            "snapshot": copy.deepcopy(snapshot),
        })
        self.set("classifier_history", history[:CLASSIFIER_HISTORY_LIMIT])

    def save_export_record(self, file_path: str, content: str) -> None:
        """Persist exports with the exact legacy history/backup schema."""
        history = self.get("export_history", []) or []
        limit = int(self.get("export_history_limit", 500) or 500)
        path = Path(file_path)
        backup_path = ""
        backup_name = ""
        if path.exists() and path.suffix.lower() in {".xlsx", ".xls", ".xlsm", ".txt"}:
            backup_dir = APP_DIR / "export_history_files"
            backup_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            backup_name = f"{stamp}_{path.stem}{path.suffix.lower()}"
            backup = backup_dir / backup_name
            shutil.copy2(path, backup)
            backup_path = str(backup)
        record = {
            "timestamp": datetime.now().isoformat(),
            "file_path": str(path),
            "file_name": path.name,
            "backup_path": backup_path,
            "backup_name": backup_name,
            "content": content,
            "line_count": len([line for line in content.splitlines() if line.strip()]),
            "char_count": len(content),
            "size_bytes": len(content.encode("utf-8")),
        }
        history.insert(0, record)
        self.set("export_history", history[:limit])


class WorkerSignals(QObject):
    progress = Signal(str)
    completed = Signal(list)
    failed = Signal(str)


class OCRWorker(QRunnable):
    def __init__(self, repository: Repository, paths: list[str], mode: str) -> None:
        super().__init__()
        self.repository = repository
        self.paths = list(paths)
        self.mode = mode
        self.signals = WorkerSignals()

    @Slot()
    def run(self) -> None:
        results: list[dict[str, Any]] = []
        try:
            api_call = MODE_CALLS[self.mode]
            total = len(self.paths)
            for index, path in enumerate(self.paths, start=1):
                self.signals.progress.emit(
                    f"正在识别 {index}/{total} · {os.path.basename(path)}"
                )
                allowed, reason = self.repository.mode_allowed_for_image(path, self.mode)
                if not allowed:
                    results.append({
                        "file": os.path.basename(path), "path": path, "lines": [],
                        "count": 0, "skipped": True, "reason": reason,
                    })
                    continue
                digest, cached = self.repository.cached(path, self.mode)
                if cached:
                    results.append(cached)
                    continue
                # 先检查限额（不实际扣减）
                permitted, used, max_count = self.repository.consume_daily_ocr_limit(self.mode, increment=False)
                if not permitted:
                    results.append({
                        "file": os.path.basename(path), "path": path, "lines": [],
                        "count": 0, "skipped": True,
                        "reason": (
                            f"今日{MODE_NAMES[self.mode]}接口调用次数已达上限"
                            f"（{used}/{max_count}）"
                        ),
                    })
                    continue
                payload = api_call(path)
                if "words_result" not in payload:
                    # 识别失败，不扣减限额
                    results.append({
                        "file": os.path.basename(path), "path": path, "lines": [],
                        "count": 0, "error": payload.get("error_msg", str(payload)),
                    })
                    continue
                # 识别成功，才实际扣减限额
                self.repository.consume_daily_ocr_limit(self.mode, increment=True)
                lines = format_words_result(payload)
                boxes = extract_word_boxes(payload)
                record = {
                    "file": os.path.basename(path), "path": path, "type": self.mode,
                    "lines": lines, "boxes": boxes, "count": len(lines), "image_hash": digest,
                }
                self.repository.save_cache(digest, self.mode, path, lines, boxes)
                results.append(record)
            self.signals.completed.emit(results)
        except Exception as exc:
            self.signals.failed.emit(_friendly_error_msg(exc))
