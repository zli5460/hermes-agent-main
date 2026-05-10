"""
🦅 Phoenix 自动保存机制
=========================
当AI通过对话修改Phoenix代码后，自动：
1. 检测哪些.py文件在最近5分钟内被修改过
2. 如果有修改，自动更新桌面发布包
3. 把关键改动记录到 changelog.json（追加模式）

每5分钟由 __init__.py 中的定时器自动调用。
"""

import os
import json
import time
import subprocess
from pathlib import Path
from datetime import datetime


# ===== 路径常量 =====
PHOENIX_DIR = Path.home() / ".hermes" / "phoenix"
DATA_DIR = PHOENIX_DIR / "data"
CHANGELOG_FILE = DATA_DIR / "changelog.json"
LAST_CHECK_FILE = DATA_DIR / "last_save_check.json"
DESKTOP_ZIP = Path.home() / "Desktop" / "phoenix-v4-release.zip"
RELEASE_DIR = PHOENIX_DIR / "release_v4"
CHECK_INTERVAL = 300  # 5分钟 = 300秒


def get_py_files(root: Path) -> list:
    """递归扫描目录下所有 .py 文件，排除 __pycache__ 和 release_v4 子目录（避免重复扫描）"""
    py_files = []
    for dirpath, dirnames, filenames in os.walk(root):
        # 跳过缓存目录和 release_v4（release 有独立的复制逻辑）
        dirnames[:] = [
            d for d in dirnames
            if d != "__pycache__" and d != "release_v4"
        ]
        for f in filenames:
            if f.endswith(".py"):
                py_files.append(Path(dirpath) / f)
    return py_files


def load_last_check() -> float:
    """加载上次检查时间戳"""
    try:
        if LAST_CHECK_FILE.exists():
            data = json.loads(LAST_CHECK_FILE.read_text())
            return data.get("last_check_timestamp", 0)
    except Exception as exc:
        _ = exc
    return 0


def save_last_check(timestamp: float):
    """保存本次检查时间戳"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "last_check_timestamp": timestamp,
        "last_check_human": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    LAST_CHECK_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def find_modified_files(py_files: list, since: float) -> list:
    """找出 since 时间之后被修改过的 .py 文件"""
    modified = []
    for fp in py_files:
        try:
            mtime = os.path.getmtime(fp)
            if mtime > since:
                modified.append({
                    "path": str(fp.relative_to(PHOENIX_DIR)),
                    "mtime": mtime,
                    "mtime_human": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S"),
                })
        except OSError:
            continue
    return modified


def update_desktop_release() -> dict:
    """删除旧的发布包并重新打包"""
    result = {"success": False, "output": "", "error": ""}

    # 检查 release_v4 目录是否存在
    if not RELEASE_DIR.exists():
        result["error"] = f"release_v4 目录不存在: {RELEASE_DIR}"
        return result

    try:
        # 删除旧包
        if DESKTOP_ZIP.exists():
            subprocess.run(
                ["rm", "-rf", str(DESKTOP_ZIP)],
                check=True, capture_output=True, timeout=10
            )

        # 打包
        proc = subprocess.run(
            ["zip", "-r", str(DESKTOP_ZIP), "release_v4/", "-x", "release_v4/**/__pycache__/*"],
            cwd=str(PHOENIX_DIR),
            capture_output=True, text=True, timeout=120
        )

        if proc.returncode == 0:
            zip_size = DESKTOP_ZIP.stat().st_size if DESKTOP_ZIP.exists() else 0
            result["success"] = True
            result["output"] = f"打包成功: {zip_size / 1024:.1f} KB"
        else:
            result["error"] = proc.stderr or proc.stdout or "zip 返回非零退出码"

    except Exception as e:
        result["error"] = str(e)

    return result


def append_changelog(modified_files: list, zip_result: dict):
    """追加改动记录到 changelog.json"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # 读取现有记录
    changelog = []
    if CHANGELOG_FILE.exists():
        try:
            changelog = json.loads(CHANGELOG_FILE.read_text())
            if not isinstance(changelog, list):
                changelog = []
        except Exception:
            changelog = []

    # 构建摘要
    file_list = [f["path"] for f in modified_files]
    entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "unix_time": time.time(),
        "files_changed": file_list,
        "files_count": len(file_list),
        "zip_updated": zip_result.get("success", False),
        "zip_output": zip_result.get("output", ""),
        "zip_error": zip_result.get("error", ""),
    }

    # 生成改动摘要
    if len(file_list) == 1:
        entry["summary"] = f"修改了 {file_list[0]}"
    else:
        entry["summary"] = f"修改了 {len(file_list)} 个文件: {', '.join(file_list[:5])}"
        if len(file_list) > 5:
            entry["summary"] += f" 等{len(file_list)}个"

    changelog.append(entry)

    # 只保留最近 500 条记录（防止无限膨胀）
    if len(changelog) > 500:
        changelog = changelog[-500:]

    CHANGELOG_FILE.write_text(json.dumps(changelog, indent=2, ensure_ascii=False))


def run_auto_save() -> dict:
    """
    自动保存主入口
    返回本次操作的结果摘要
    """
    now = time.time()
    last_check = load_last_check()
    result = {
        "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "modified_files": [],
        "zip_updated": False,
        "changelog_appended": False,
        "message": "",
    }

    # 如果距离上次检查不到 10 秒，跳过（防抖）
    if now - last_check < 10:
        result["message"] = "距离上次检查不足10秒，跳过"
        return result

    # 扫描 .py 文件
    py_files = get_py_files(PHOENIX_DIR)

    # 找出最近5分钟内修改过的文件
    modified = find_modified_files(py_files, since=last_check)

    if not modified:
        result["message"] = "无新改动"
        save_last_check(now)
        return result

    result["modified_files"] = [f["path"] for f in modified]
    result["message"] = f"发现 {len(modified)} 个文件被修改"

    # 执行保存操作
    # 1. 更新桌面发布包
    zip_result = update_desktop_release()
    result["zip_updated"] = zip_result["success"]
    result["zip_detail"] = zip_result

    # 2. 记录到 changelog
    try:
        append_changelog(modified, zip_result)
        result["changelog_appended"] = True
    except Exception as e:
        result["changelog_error"] = str(e)

    # 更新上次检查时间
    save_last_check(now)

    return result


# ===== 命令行直接执行 =====
if __name__ == "__main__":
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🦅 Phoenix 自动保存检查...")
    result = run_auto_save()

    if result["modified_files"]:
        print(f"  📝 发现改动: {result['files_count'] if 'files_count' in result else len(result['modified_files'])} 个文件")
        for f in result["modified_files"]:
            print(f"     - {f}")
        print(f"  📦 发布包更新: {'✅ 成功' if result['zip_updated'] else '❌ 失败'}")
        print(f"  📋 Changelog: {'✅ 已记录' if result['changelog_appended'] else '❌ 失败'}")
    else:
        print(f"  ℹ️  {result['message']}")
