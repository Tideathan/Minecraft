import os
import hashlib
import json
import urllib.request
import shutil
import zipfile

MC_DIR = os.path.normpath(r"c:\Users\user\AppData\Roaming\.minecraft")
MODS_DIR = os.path.join(MC_DIR, "mods")
BACKUP_REPLACED_DIR = r"c:\Users\user\AppData\Roaming\.minecraft_backup\mods_replaced"

def calculate_sha1(filepath):
    h = hashlib.sha1()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def get_installed_mods_info():
    mods = []
    if not os.path.exists(MODS_DIR):
        return mods

    for f in os.listdir(MODS_DIR):
        if not f.endswith(".jar"):
            continue
        full_path = os.path.join(MODS_DIR, f)
        mod_name = f[:-4]
        # Clean common version strings from display name
        display_name = f.split("-")[0].split("+")[0].replace("_", " ")
        mods.append({
            "filename": f,
            "filepath": full_path,
            "display_name": display_name,
            "size_mb": round(os.path.getsize(full_path) / (1024 * 1024), 2),
            "status": "Установлен"
        })
    return sorted(mods, key=lambda x: x["display_name"].lower())

def check_mod_updates_async(progress_callback=None):
    installed = get_installed_mods_info()
    total = len(installed)
    if total == 0:
        return []

    # Calculate SHA1 hashes
    hash_map = {}
    for idx, m in enumerate(installed):
        if progress_callback:
            progress_callback(idx / total * 0.4, f"Сканирование хешей ({idx+1}/{total})...")
        try:
            h = calculate_sha1(m["filepath"])
            hash_map[h] = m
        except Exception:
            pass

    # Batch query Modrinth version_files API
    hashes = list(hash_map.keys())
    batch_size = 100
    updates_found = []

    for i in range(0, len(hashes), batch_size):
        batch = hashes[i:i + batch_size]
        if progress_callback:
            progress_callback(0.4 + (i / len(hashes)) * 0.5, "Запрос актуальных версий в Modrinth...")

        req_data = json.dumps({
            "hashes": batch,
            "algorithm": "sha1"
        }).encode("utf-8")

        try:
            req = urllib.request.Request(
                "https://api.modrinth.com/v2/version_files",
                data=req_data,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "AntigravityLauncher/1.0 (contact@minecraft.launcher)"
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            for h, vinfo in data.items():
                local_mod = hash_map.get(h)
                if not local_mod:
                    continue
                
                project_id = vinfo.get("project_id")
                current_ver_num = vinfo.get("version_number", "")
                
                # Check if there is a newer version for NeoForge 1.21.1
                try:
                    p_url = f"https://api.modrinth.com/v2/project/{project_id}/version?game_versions=[%221.21.1%22]&loaders=[%22neoforge%22]"
                    p_req = urllib.request.Request(p_url, headers={"User-Agent": "AntigravityLauncher/1.0"})
                    with urllib.request.urlopen(p_req, timeout=8) as p_resp:
                        p_versions = json.loads(p_resp.read().decode("utf-8"))
                        if p_versions:
                            latest = p_versions[0]
                            if latest.get("version_number") != current_ver_num:
                                files = latest.get("files", [])
                                primary = next((x for x in files if x.get("primary")), files[0] if files else None)
                                if primary:
                                    updates_found.append({
                                        "filename": local_mod["filename"],
                                        "display_name": local_mod["display_name"],
                                        "current_version": current_ver_num or "текущая",
                                        "latest_version": latest.get("version_number"),
                                        "download_url": primary.get("url"),
                                        "new_filename": primary.get("filename")
                                    })
                except Exception:
                    pass
        except Exception as e:
            print(f"Error querying Modrinth batch: {e}")

    if progress_callback:
        progress_callback(1.0, f"Готово! Доступно обновлений: {len(updates_found)}")

    return updates_found

def install_mod_update(update_item, progress_callback=None):
    os.makedirs(BACKUP_REPLACED_DIR, exist_ok=True)
    old_file = os.path.join(MODS_DIR, update_item["filename"])
    new_filename = update_item.get("new_filename", update_item["filename"])
    new_file = os.path.join(MODS_DIR, new_filename)

    url = update_item["download_url"]
    temp_target = new_file + ".download"

    try:
        if progress_callback:
            progress_callback(0.2, f"Скачивание {update_item['display_name']}...")
        urllib.request.urlretrieve(url, temp_target)

        # Move old jar to backup
        if os.path.exists(old_file):
            shutil.move(old_file, os.path.join(BACKUP_REPLACED_DIR, update_item["filename"]))

        # Move new jar into place
        shutil.move(temp_target, new_file)

        if progress_callback:
            progress_callback(1.0, f"{update_item['display_name']} обновлен!")
        return True, "Успешно обновлено"
    except Exception as e:
        if os.path.exists(temp_target):
            try: os.remove(temp_target)
            except Exception: pass
        return False, f"Ошибка: {e}"
