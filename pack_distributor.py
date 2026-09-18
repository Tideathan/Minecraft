import os
import zipfile
import json
import urllib.request
import shutil

MC_DIR = os.path.normpath(r"c:\Users\user\AppData\Roaming\.minecraft")

def export_build_pack(output_zip_path, progress_callback=None):
    try:
        if progress_callback:
            progress_callback(0.05, "Подготовка списка файлов для сборки...")

        folders_to_pack = [
            ("mods", "mods"),
            ("config", "config"),
            ("shaderpacks", "shaderpacks"),
            ("resourcepacks", "resourcepacks")
        ]
        files_to_pack = [
            "options.txt",
            "optionsshaders.txt",
            "servers.dat"
        ]

        total_files = 0
        for rel_dir, _ in folders_to_pack:
            fp = os.path.join(MC_DIR, rel_dir)
            if os.path.exists(fp):
                for root, _, fs in os.walk(fp):
                    total_files += len(fs)
        total_files += len(files_to_pack)

        packed_count = 0
        with zipfile.ZipFile(output_zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            # Write build manifest
            manifest = {
                "name": "Minecraft NeoForge 1.21.1 Custom Pack",
                "version": "neoforge-21.1.248",
                "total_files": total_files,
                "created_at": "2026-09-18"
            }
            z.writestr("pack_manifest.json", json.dumps(manifest, indent=2))

            for rel_dir, arc_prefix in folders_to_pack:
                src_dir = os.path.join(MC_DIR, rel_dir)
                if not os.path.exists(src_dir):
                    continue
                for root, _, fs in os.walk(src_dir):
                    for f in fs:
                        full_p = os.path.join(root, f)
                        rel_p = os.path.relpath(full_p, MC_DIR)
                        z.write(full_p, rel_p)
                        packed_count += 1
                        if progress_callback and total_files > 0:
                            progress_callback(0.05 + (packed_count / total_files) * 0.9, f"Упаковка: {f}...")

            for fn in files_to_pack:
                fp = os.path.join(MC_DIR, fn)
                if os.path.exists(fp):
                    z.write(fp, fn)
                    packed_count += 1

        if progress_callback:
            progress_callback(1.0, f"Сборка успешно сохранена в: {os.path.basename(output_zip_path)}")
        return True, f"Сборка успешно упакована ({os.path.getsize(output_zip_path) // (1024*1024)} МБ)"
    except Exception as e:
        return False, f"Ошибка экспорта: {e}"

def import_build_pack(source_path_or_url, progress_callback=None):
    temp_zip = None
    try:
        if source_path_or_url.startswith("http://") or source_path_or_url.startswith("https://"):
            if progress_callback:
                progress_callback(0.1, "Скачивание сборки из облака...")
            temp_zip = os.path.join(MC_DIR, "downloaded_pack.zip")
            urllib.request.urlretrieve(source_path_or_url, temp_zip)
            zip_file_to_extract = temp_zip
        else:
            zip_file_to_extract = source_path_or_url

        if not os.path.exists(zip_file_to_extract):
            return False, "Файл сборки не найден"

        if progress_callback:
            progress_callback(0.5, "Распаковка сборки и синхронизация...")

        with zipfile.ZipFile(zip_file_to_extract, "r") as z:
            members = z.namelist()
            total = len(members)
            for i, member in enumerate(members):
                if member == "pack_manifest.json":
                    continue
                z.extract(member, MC_DIR)
                if progress_callback and total > 0:
                    progress_callback(0.5 + (i / total) * 0.48, f"Синхронизация: {member}...")

        if temp_zip and os.path.exists(temp_zip):
            try: os.remove(temp_zip)
            except Exception: pass

        if progress_callback:
            progress_callback(1.0, "Сборка успешно синхронизирована!")
        return True, "Сборка успешно установлена!"
    except Exception as e:
        if temp_zip and os.path.exists(temp_zip):
            try: os.remove(temp_zip)
            except Exception: pass
        return False, f"Ошибка импорта: {e}"
