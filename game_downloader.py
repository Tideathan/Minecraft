import os
import sys
import json
import urllib.request
import concurrent.futures
from java_manager import find_all_javas, download_and_extract_java_21, get_java_version_info
from version_manager import install_neoforge_version
from github_sync import fetch_manifest_from_github, compare_manifest_with_local, sync_differences

_CURR_DIR = os.path.dirname(os.path.abspath(__file__))
MC_DIR = os.path.normpath(os.path.join(_CURR_DIR, "..")) if os.path.basename(_CURR_DIR).lower() == "launcher" else os.path.normpath(os.path.expandvars(r"%APPDATA%\.minecraft"))

ASSET_INDEX_URL = "https://piston-meta.mojang.com/v1/packages/76d7a97b9e0778fda3b14e474f012450ca0de1bb/17.json"
ASSET_CDN_BASE = "https://resources.download.minecraft.net"

def check_game_status(target_ver="neoforge-21.1.248"):
    """
    Checks what components are currently installed.
    Returns dict with status flags.
    """
    # 1. Java
    javas = find_all_javas()
    compat_javas = [j for j in javas if j["compatible"]]
    has_java = len(compat_javas) > 0
    best_java = compat_javas[0]["path"] if compat_javas else (javas[0]["path"] if javas else None)

    # 2. NeoForge / Version
    ver_json = os.path.join(MC_DIR, "versions", target_ver, f"{target_ver}.json")
    has_version = os.path.exists(ver_json)

    # 3. Assets
    asset_index = os.path.join(MC_DIR, "assets", "indexes", "17.json")
    has_assets = os.path.exists(asset_index)

    # 4. Mods
    mods_dir = os.path.join(MC_DIR, "mods")
    mods_count = len([f for f in os.listdir(mods_dir) if f.endswith(".jar")]) if os.path.exists(mods_dir) else 0
    has_mods = mods_count >= 100

    fully_ready = has_java and has_version and has_mods

    missing = []
    if not has_java:
        missing.append("Java 21 OpenJDK")
    if not has_version:
        missing.append(f"Клиент {target_ver} и библиотеки")
    if not has_assets:
        missing.append("Ванильные звуки и текстуры (Assets 1.21.1)")
    if not has_mods:
        missing.append("Сборка модов и конфигураций (GitHub)")

    return {
        "has_java": has_java,
        "java_path": best_java,
        "has_version": has_version,
        "has_assets": has_assets,
        "has_mods": has_mods,
        "mods_count": mods_count,
        "fully_ready": fully_ready,
        "missing": missing
    }

def download_vanilla_assets(progress_callback=None):
    """
    Downloads Mojang vanilla assets index and objects via multithreading.
    """
    indexes_dir = os.path.join(MC_DIR, "assets", "indexes")
    objects_dir = os.path.join(MC_DIR, "assets", "objects")
    os.makedirs(indexes_dir, exist_ok=True)
    os.makedirs(objects_dir, exist_ok=True)

    index_path = os.path.join(indexes_dir, "17.json")
    if progress_callback:
        progress_callback(0.02, "Загрузка манифеста звуков и текстур Mojang...")

    try:
        req = urllib.request.Request(ASSET_INDEX_URL, headers={"User-Agent": "Mozilla/5.0 (Minecraft Launcher)"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception as e:
        return False, f"Ошибка загрузки ассетов Mojang: {e}"

    objects = data.get("objects", {})
    to_download = []
    for name, info in objects.items():
        h = info["hash"]
        dest = os.path.join(objects_dir, h[:2], h)
        if not os.path.exists(dest) or os.path.getsize(dest) != info["size"]:
            to_download.append((h, dest, info["size"]))

    total = len(to_download)
    if total == 0:
        if progress_callback:
            progress_callback(1.0, "Все ассеты Mojang уже загружены.")
        return True, "Ассеты актуальны"

    done = 0
    def _fetch_one(item):
        h, dest, size = item
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        url = f"{ASSET_CDN_BASE}/{h[:2]}/{h}"
        for _ in range(2):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=12) as r, open(dest, "wb") as f:
                    while chunk := r.read(65536):
                        f.write(chunk)
                return True
            except Exception:
                pass
        return False

    with concurrent.futures.ThreadPoolExecutor(max_workers=24) as executor:
        futures = {executor.submit(_fetch_one, item): item for item in to_download}
        for future in concurrent.futures.as_completed(futures):
            done += 1
            if progress_callback and (done % 50 == 0 or done == total):
                frac = done / total
                progress_callback(0.05 + frac * 0.95, f"Загрузка ассетов: {done}/{total}...")

    return True, f"Загружено ассетов: {done}"

def download_everything_auto(
    repo_slug="Tideathan/Minecraft", 
    branch="main", 
    target_ver="neoforge-21.1.248",
    progress_callback=None,
    step_callback=None
):
    """
    Executes full end-to-end automated installation:
    1. Java 21
    2. NeoForge 21.1.248 + Vanilla 1.21.1
    3. Vanilla Assets
    4. GitHub Modpack
    """
    def _notify(step_name, p, detail):
        if step_callback:
            step_callback(step_name)
        if progress_callback:
            progress_callback(p, detail)

    # --- PRE-STEP: CLEAN JUNK & TLAUNCHER ARTIFACTS ---
    try:
        from github_sync import cleanup_tlauncher_artifacts
        cleanup_tlauncher_artifacts(MC_DIR)
    except Exception:
        pass

    # --- STEP 1: JAVA 21 ---
    _notify("Проверка Java 21", 0.05, "Поиск совместимого Java 21...")
    status = check_game_status(target_ver)
    java_exe = status["java_path"]

    if not status["has_java"] or not java_exe:
        _notify("Загрузка Java 21", 0.08, "Загрузка Adoptium Temurin OpenJDK 21...")
        ok, msg, j_path = download_and_extract_java_21(
            progress_callback=lambda p, t: _notify("Загрузка Java 21", 0.08 + p * 0.2, t)
        )
        if not ok or not j_path:
            return False, f"Не удалось установить Java 21: {msg}"
        java_exe = j_path
    else:
        _notify("Java 21 найдена", 0.28, f"Найдена Java: {os.path.basename(java_exe)}")

    # Convert to java.exe if javaw.exe
    runner = java_exe
    if "javaw.exe" in runner.lower():
        cand = os.path.join(os.path.dirname(runner), "java.exe")
        if os.path.exists(cand):
            runner = cand

    # --- STEP 2: NEOFORGE & VANILLA BASE ---
    status = check_game_status(target_ver)
    if not status["has_version"]:
        ver_num = target_ver.replace("neoforge-", "").replace("NeoForge-", "")
        _notify("Установка NeoForge", 0.30, f"Установка ядра {target_ver} и библиотек...")
        ok, msg = install_neoforge_version(
            ver_num, 
            runner, 
            progress_callback=lambda p, t: _notify("Установка NeoForge", 0.30 + p * 0.3, t)
        )
        if not ok:
            return False, f"Не удалось установить NeoForge: {msg}"
    else:
        _notify("Ядро NeoForge готово", 0.60, f"Версия {target_ver} уже установлена.")

    # --- STEP 3: VANILLA ASSETS ---
    status = check_game_status(target_ver)
    if not status["has_assets"]:
        _notify("Загрузка ассетов", 0.62, "Загрузка текстур и звуков Mojang...")
        download_vanilla_assets(
            progress_callback=lambda p, t: _notify("Загрузка ассетов", 0.62 + p * 0.15, t)
        )
    else:
        _notify("Ассеты готовы", 0.77, "Ванильные ассеты Mojang присутствуют.")

    # --- STEP 4: GITHUB MODPACK ---
    _notify("Синхронизация сборки", 0.78, f"Получение списка модов с GitHub ({repo_slug})...")
    ok, manifest, url = fetch_manifest_from_github(repo_slug, branch=branch)
    if not ok:
        return False, f"Не удалось получить сборку с GitHub: {manifest}\n(Убедитесь, что репозиторий открыт как Public)"

    _notify("Синхронизация сборки", 0.82, "Сравнение модов и конфигураций...")
    diff = compare_manifest_with_local(manifest)
    
    to_dl = diff.get("to_download", [])
    to_del = diff.get("to_delete", [])
    if to_dl or to_del:
        action_text = f"Синхронизация сборки (скачать: {len(to_dl)}, очистить старых/чужих: {len(to_del)})..."
        _notify("Загрузка модов", 0.84, action_text)
        ok_sync, msg_sync = sync_differences(
            diff, 
            repo_slug, 
            branch=branch,
            progress_callback=lambda p, t: _notify("Загрузка модов", 0.84 + p * 0.15, t)
        )
        if not ok_sync:
            return False, f"Ошибка загрузки модов: {msg_sync}"
    else:
        _notify("Моды актуальны", 0.99, "Все моды и конфиги совпадают с GitHub.")

    _notify("Готово к игре", 1.0, "[OK] Полная установка завершена! Всё готово к игре.")
    return True, "Все компоненты, Java, ядро и сборка модов успешно установлены!"
