import os
import sys
import json
import time
import hashlib
import urllib.request
import shutil
import subprocess

CURRENT_LAUNCHER_VERSION = "1.0.1"
DEFAULT_REPO_SLUG = "Tideathan/Minecraft"
LAUNCHER_BRANCH = "launcher"

_CURR_DIR = os.path.dirname(os.path.abspath(__file__))
LAUNCHER_DIR = _CURR_DIR
MC_DIR = os.path.normpath(os.path.join(_CURR_DIR, "..")) if os.path.basename(_CURR_DIR).lower() == "launcher" else os.path.normpath(os.path.expandvars(r"%APPDATA%\.minecraft"))
BACKUP_DIR = os.path.join(MC_DIR, "..", ".minecraft_backup", "launcher_updates")

LAUNCHER_FILES = [
    "Minecraft_Launcher.exe",
    "launcher.py",
    "launcher_core.py",
    "game_downloader.py",
    "java_manager.py",
    "version_manager.py",
    "mod_updater.py",
    "skin_manager.py",
    "pack_distributor.py",
    "github_sync.py",
    "launcher_updater.py",
    "push_to_github.py",
    "publisher_gui.py",
    "Publisher.bat",
    "Publisher.vbs",
    "Launcher.bat",
    "Launcher.vbs",
    "launcher_icon.ico",
    "launcher_icon.png",
    "minecraft_wolf.ico"
]

def parse_version(v_str):
    try:
        clean = v_str.strip().lstrip("vV")
        parts = [int(x) for x in clean.split(".") if x.isdigit()]
        return tuple(parts)
    except Exception:
        return (0, 0, 0)

def normalize_slug(url_or_slug):
    s = url_or_slug.strip().rstrip("/")
    if s.endswith(".git"):
        s = s[:-4]
    for prefix in ["https://github.com/", "http://github.com/", "git@github.com:"]:
        if s.startswith(prefix):
            s = s[len(prefix):]
            break
    return s.strip("/")

def calculate_sha1(filepath):
    ext = os.path.splitext(filepath)[1].lower()
    if ext in [".py", ".bat", ".vbs", ".json", ".txt", ".md"]:
        with open(filepath, "rb") as f:
            data = f.read().replace(b"\r\n", b"\n")
        return hashlib.sha1(data).hexdigest()
    h = hashlib.sha1()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def check_file_matches(filepath, expected_sha1):
    if not expected_sha1:
        return True
    actual = calculate_sha1(filepath)
    if actual.lower() == expected_sha1.lower():
        return True
    # Also check raw binary or CRLF conversion just in case
    try:
        h = hashlib.sha1()
        with open(filepath, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        if h.hexdigest().lower() == expected_sha1.lower():
            return True
        with open(filepath, "rb") as f:
            raw = f.read()
        crlf_sha = hashlib.sha1(raw.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")).hexdigest()
        if crlf_sha.lower() == expected_sha1.lower():
            return True
    except Exception:
        pass
    return False

def check_launcher_update(repo_slug=DEFAULT_REPO_SLUG, branch=LAUNCHER_BRANCH, token=None):
    slug = normalize_slug(repo_slug)
    url = f"https://raw.githubusercontent.com/{slug}/{branch}/launcher_version.json?_nocache={int(time.time())}"
    headers = {
        "User-Agent": "AntigravityLauncherUpdater/1.0",
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache"
    }
    if token:
        headers["Authorization"] = f"token {token}"

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        remote_ver_str = data.get("version", "1.0.0")
        remote_tuple = parse_version(remote_ver_str)
        curr_tuple = parse_version(CURRENT_LAUNCHER_VERSION)

        has_update = remote_tuple > curr_tuple
        return True, {
            "has_update": has_update,
            "current_version": CURRENT_LAUNCHER_VERSION,
            "remote_version": remote_ver_str,
            "release_date": data.get("release_date", ""),
            "changelog": data.get("changelog", "Улучшения стабильности и исправления интерфейса."),
            "files": data.get("files", {}),
            "download_zip_url": data.get("download_zip_url", "")
        }
    except Exception as e:
        return False, f"Ошибка соединения с GitHub: {e}"

def apply_launcher_update(update_info, repo_slug=DEFAULT_REPO_SLUG, branch=LAUNCHER_BRANCH, token=None, progress_callback=None):
    slug = normalize_slug(repo_slug)
    files_map = update_info.get("files", {})
    if not files_map:
        # Fallback: update known launcher files
        files_map = {f: {} for f in LAUNCHER_FILES}

    os.makedirs(BACKUP_DIR, exist_ok=True)
    curr_v = update_info.get("current_version", CURRENT_LAUNCHER_VERSION)
    backup_ver_dir = os.path.join(BACKUP_DIR, f"backup_v{curr_v}")
    os.makedirs(backup_ver_dir, exist_ok=True)

    # Filter out setup installer from self-update files if updating an installed launcher
    files_map = {k: v for k, v in files_map.items() if "Setup.exe" not in k}
    total_files = len(files_map)
    downloaded_files = {}

    headers = {"User-Agent": "AntigravityLauncherUpdater/1.0"}
    if token:
        headers["Authorization"] = f"token {token}"

    # 1. Download to temp
    for i, (rel_path, meta) in enumerate(files_map.items()):
        if progress_callback:
            progress_callback(i / total_files * 0.8, f"Загрузка файла: {rel_path}...")

        raw_url = f"https://raw.githubusercontent.com/{slug}/{branch}/{rel_path.replace('\\', '/')}?_nocache={int(time.time())}"
        dest_local = os.path.join(LAUNCHER_DIR, rel_path)
        temp_dest = dest_local + ".new_update"
        os.makedirs(os.path.dirname(temp_dest), exist_ok=True)

        try:
            req = urllib.request.Request(raw_url, headers=headers)
            with urllib.request.urlopen(req, timeout=20) as resp:
                with open(temp_dest, "wb") as f:
                    while chunk := resp.read(65536):
                        f.write(chunk)

            expected_sha1 = meta.get("sha1")
            if expected_sha1 and not check_file_matches(temp_dest, expected_sha1):
                try: os.remove(temp_dest)
                except Exception: pass
                return False, f"Не совпал хеш для {rel_path}"

            downloaded_files[dest_local] = temp_dest
        except Exception as e:
            # Clean up all downloaded temp files
            for _, t_file in downloaded_files.items():
                try: os.remove(t_file)
                except Exception: pass
            return False, f"Ошибка загрузки {rel_path}: {e}"

    # 2. Backup current files and move new ones
    if progress_callback:
        progress_callback(0.9, "Применение обновления файлов...")

    for dest_local, temp_dest in downloaded_files.items():
        if os.path.exists(dest_local):
            rel = os.path.relpath(dest_local, LAUNCHER_DIR)
            b_dst = os.path.join(backup_ver_dir, rel)
            os.makedirs(os.path.dirname(b_dst), exist_ok=True)
            try:
                shutil.copy2(dest_local, b_dst)
            except Exception:
                pass
            try:
                os.remove(dest_local)
            except Exception:
                # Windows locked running executable: rename to .old first
                old_path = dest_local + ".old"
                if os.path.exists(old_path):
                    try: os.remove(old_path)
                    except Exception: pass
                try:
                    os.rename(dest_local, old_path)
                except Exception:
                    pass
        try:
            shutil.move(temp_dest, dest_local)
        except Exception:
            pass

    cleanup_old_binaries()

    if progress_callback:
        progress_callback(1.0, "Обновление лаунчера успешно установлено!")

    return True, "Обновление завершено"

def cleanup_old_binaries():
    if os.path.exists(LAUNCHER_DIR):
        for f in os.listdir(LAUNCHER_DIR):
            if f.endswith(".old") or f.endswith(".new_update"):
                try:
                    os.remove(os.path.join(LAUNCHER_DIR, f))
                except Exception:
                    pass

def restart_launcher():
    launcher_py = os.path.join(LAUNCHER_DIR, "launcher.py")
    if getattr(sys, "frozen", False):
        subprocess.Popen([sys.executable] + sys.argv[1:])
    else:
        # Check pythonw or python
        py_exe = sys.executable
        if "python.exe" in py_exe.lower():
            pyw = os.path.join(os.path.dirname(py_exe), "pythonw.exe")
            if os.path.exists(pyw):
                py_exe = pyw
        subprocess.Popen([py_exe, launcher_py], cwd=LAUNCHER_DIR)
    
    sys.exit(0)
