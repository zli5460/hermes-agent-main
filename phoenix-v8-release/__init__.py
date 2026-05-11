"""
🦅 不死鸟 Phoenix V8

让AI系统像不死鸟一样，死不了、砍不掉、自己会修自己、越用越牛逼。
"""

try:
    # Prefer package-relative import when this repo layout is imported directly.
    from .phoenix import Phoenix  # type: ignore[attr-defined]  # noqa: F401
except Exception:
    try:
        # Fallback for runtime environments that expose ``phoenix`` as a top-level package.
        from phoenix.phoenix import Phoenix  # type: ignore  # noqa: F401
    except Exception:
        # Allow package import for tests/tooling even when runtime Phoenix module is absent.
        Phoenix = None  # type: ignore
import threading
import atexit
import sys

__all__ = ["Phoenix"]


# ===== 自动保存定时器 =====
_auto_save_stop = threading.Event()

def _auto_save_loop():
    """后台线程：每5分钟扫描.py改动并自动保存"""
    import time
    while not _auto_save_stop.is_set():
        _auto_save_stop.wait(300)  # 每300秒(5分钟)醒一次
        if _auto_save_stop.is_set():
            break
        try:
            from phoenix.auto_save import run_auto_save
            result = run_auto_save()
            if result.get("modified_files"):
                print(f"[Phoenix AutoSave {result.get('checked_at', '?')}] "
                      f"📦 自动保存: {result['message']}")
        except Exception as e:
            # 静默失败，不干扰主流程
            pass

def _stop_auto_save():
    """退出时停止自动保存线程"""
    _auto_save_stop.set()

# 启动自动保存后台线程
_auto_save_thread = threading.Thread(
    target=_auto_save_loop,
    daemon=True,
    name="PhoenixAutoSave",
)
_auto_save_thread.start()
atexit.register(_stop_auto_save)
