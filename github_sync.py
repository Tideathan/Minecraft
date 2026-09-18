import os
import json
import hashlib
import urllib.request
import shutil

MC_DIR = os.path.normpath(r"c:\Users\user\AppData\Roaming\.minecraft")
BACKUP_DIR = r"c:\Users\user\AppData\Roaming\.minecraft_backup\mods_replaced"

def calculate_sha1(filepath):
    h = hashlib.sha1()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def normalize_repo_slug(url_or_slug):
    s = url_or_slug.strip().rstrip("/")
    if s.endswith(".git"):
        s = s[:-4]
    for prefix in ["https://github.com/", "http://github.com/", "git@github.com:"]:
        if s.startswith(prefix):
            s = s[len(prefix):]
            break
    return s.strip("/")

def get_raw_url(repo_slug, file_path, branch="main"):
    slug = normalize_repo_slug(repo_slug)
    clean_p = file_path.replace("\\", "/").lstrip("/")
    return f"https://raw.githubusercontent.com/{slug}/{branch}/{clean_p}"

def fetch_manifest_from_github(repo_slug, branch="main", token=None):
    slug = normalize_repo_slug(repo_slug)
    manifest_url = f"https://raw.githubusercontent.com/{slug}/{branch}/manifest.json"
    headers = {"User-Agent": "AntigravityLauncher/1.0", "Cache-Control": "no-cache"}
    if token:
        headers["Authorization"] = f"token {token}"
    try:
        req = urllib.request.Request(manifest_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return True, data, manifest_url
    except Exception as e:
        return False, f"Ошибка загрузки манифеста: {e}", manifest_url

def compare_manifest_with_local(manifest, progress_callback=None):
    files_map = manifest.get("files", {})
    total_files = len(files_map)
    
    to_download = []
    up_to_date_count = 0
    total_bytes = 0

    idx = 0
    for rel_path, meta in files_map.items():
        idx += 1
        if progress_callback and total_files > 0:
            progress_callback(idx / total_files * 0.7, f"Проверка: {rel_path}...")

        expected_sha1 = meta.get("sha1")
        expected_size = meta.get("size", 0)
        local_full = os.path.join(MC_DIR, rel_path)

        if not os.path.exists(local_full):
            to_download.append({
                "rel_path": rel_path,
                "size": expected_size,
                "expected_sha1": expected_sha1,
                "reason": "Отсутствует"
            })
            total_bytes += expected_size
        else:
            local_size = os.path.getsize(local_full)
            if local_size != expected_size:
                to_download.append({
                    "rel_path": rel_path,
                    "size": expected_size,
                    "expected_sha1": expected_sha1,
                    "reason": "Изменен"
                })
                total_bytes += expected_size
            else:
                # Check SHA1
                local_sha1 = calculate_sha1(local_full)
                if local_sha1.lower() != expected_sha1.lower():
                    to_download.append({
                        "rel_path": rel_path,
                        "size": expected_size,
                        "expected_sha1": expected_sha1,
                        "reason": "Обновлен"
                    })
                    total_bytes += expected_size
                else:
                    up_to_date_count += 1

    # Check for outdated mods locally that are deleted in manifest
    to_delete = []
    local_mods_dir = os.path.join(MC_DIR, "mods")
    if os.path.exists(local_mods_dir):
        manifest_mods = {os.path.normpath(p).lower() for p in files_map if p.lower().startswith("mods/") or p.lower().startswith("mods\\")}
        for f in os.listdir(local_mods_dir):
            if f.endswith(".jar"):
                rel_f = os.path.normpath(os.path.join("mods", f)).lower()
                if rel_f not in manifest_mods:
                    to_delete.append(os.path.join("mods", f))

    if progress_callback:
        progress_callback(1.0, "Сравнение завершено!")

    return {
        "version": manifest.get("version", "1.0.0"),
        "updated_at": manifest.get("updated_at", ""),
        "neoforge_version": manifest.get("neoforge_version", "21.1.250"),
        "to_download": to_download,
        "to_delete": to_delete,
        "up_to_date_count": up_to_date_count,
        "total_download_bytes": total_bytes
    }

def sync_differences(comparison_result, repo_slug, branch="main", token=None, progress_callback=None):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    to_dl = comparison_result["to_download"]
    to_del = comparison_result["to_delete"]
    total = len(to_dl)

    slug = normalize_repo_slug(repo_slug)

    for i, item in enumerate(to_dl):
        rel_p = item["rel_path"]
        raw_url = get_raw_url(slug, rel_p, branch)
        dest_path = os.path.join(MC_DIR, rel_p)
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)

        if progress_callback:
            progress_callback((i / total) * 0.9, f"Скачивание ({i+1}/{total}): {os.path.basename(rel_p)}...")

        temp_target = dest_path + ".tmp_download"
        try:
            headers = {"User-Agent": "AntigravityLauncher/1.0"}
            if token:
                headers["Authorization"] = f"token {token}"
            req = urllib.request.Request(raw_url, headers=headers)
            with urllib.request.urlopen(req, timeout=20) as resp:
                with open(temp_target, "wb") as f:
                    while chunk := resp.read(65536):
                        f.write(chunk)

            # Handle Git LFS pointer files (download real binary from GitHub Media CDN)
            if os.path.exists(temp_target) and os.path.getsize(temp_target) < 1024:
                with open(temp_target, "rb") as check_f:
                    prefix = check_f.read(60)
                if prefix.startswith(b"version https://git-lfs"):
                    clean_p = rel_p.replace("\\", "/").lstrip("/")
                    media_url = f"https://media.githubusercontent.com/media/{slug}/{branch}/{clean_p}"
                    headers_lfs = {"User-Agent": "Mozilla/5.0 AntigravityLauncher/1.0"}
                    if token:
                        headers_lfs["Authorization"] = f"token {token}"
                    req_lfs = urllib.request.Request(media_url, headers=headers_lfs)
                    with urllib.request.urlopen(req_lfs, timeout=60) as resp_lfs:
                        with open(temp_target, "wb") as f_lfs:
                            while chunk := resp_lfs.read(65536):
                                f_lfs.write(chunk)

            # Check downloaded file SHA1
            dl_sha1 = calculate_sha1(temp_target)
            if item.get("expected_sha1") and dl_sha1.lower() != item["expected_sha1"].lower():
                try: os.remove(temp_target)
                except Exception: pass
                return False, f"Не совпадает хеш SHA1 для {rel_p}"

            if os.path.exists(dest_path):
                # Archive old mod to backup
                if "mods" in rel_p.lower():
                    shutil.move(dest_path, os.path.join(BACKUP_DIR, os.path.basename(dest_path)))
                else:
                    os.remove(dest_path)

            shutil.move(temp_target, dest_path)
        except Exception as e:
            if os.path.exists(temp_target):
                try: os.remove(temp_target)
                except Exception: pass
            return False, f"Ошибка загрузки {rel_p}: {e}"

    # Remove / archive deleted files
    for del_rel in to_del:
        del_path = os.path.join(MC_DIR, del_rel)
        if os.path.exists(del_path):
            shutil.move(del_path, os.path.join(BACKUP_DIR, os.path.basename(del_path)))

    if progress_callback:
        progress_callback(1.0, f"Успешно синхронизировано {total} файлов!")

    return True, f"Сборка синхронизирована: обновлено {total} файлов, удалено {len(to_del)} старых."
