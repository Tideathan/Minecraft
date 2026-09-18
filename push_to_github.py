import os
import sys
import json
import hashlib
import subprocess
import shutil
from datetime import datetime

_CURR_DIR = os.path.dirname(os.path.abspath(__file__))
MC_DIR = os.path.normpath(os.path.join(_CURR_DIR, "..")) if os.path.basename(_CURR_DIR).lower() == "launcher" else os.path.normpath(r"c:\Users\user\AppData\Roaming\.minecraft")
CONFIG_PATH = os.path.join(MC_DIR, "launcher_config.json")
DEFAULT_REPO_DIR = os.path.join(_CURR_DIR, "github_repo") if os.path.basename(_CURR_DIR).lower() == "launcher" else os.path.join(MC_DIR, "github_repo")

def calculate_sha1(filepath):
    h = hashlib.sha1()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def gather_build_files():
    """
    Scans ONLY essential build files:
    - mods/*.jar
    - config/**/*
    - shaderpacks/photon*
    - resourcepacks/*.zip
    - options.txt, optionsshaders.txt, servers.dat
    Strictly ignores all junk, saves, logs, caches, runtime, etc.
    """
    files = {}

    # 1. Mods
    mods_dir = os.path.join(MC_DIR, "mods")
    if os.path.exists(mods_dir):
        for f in os.listdir(mods_dir):
            if f.endswith(".jar"):
                fp = os.path.join(mods_dir, f)
                rel = os.path.join("mods", f).replace("\\", "/")
                files[rel] = fp

    # 2. Configs
    config_dir = os.path.join(MC_DIR, "config")
    if os.path.exists(config_dir):
        for root, _, fs in os.walk(config_dir):
            for f in fs:
                fp = os.path.join(root, f)
                rel = os.path.relpath(fp, MC_DIR).replace("\\", "/")
                files[rel] = fp

    # 3. Shaderpacks
    shader_dir = os.path.join(MC_DIR, "shaderpacks")
    if os.path.exists(shader_dir):
        for f in os.listdir(shader_dir):
            if "photon" in f.lower() or f.endswith(".zip") or f.endswith(".txt"):
                fp = os.path.join(shader_dir, f)
                if os.path.isfile(fp):
                    rel = os.path.join("shaderpacks", f).replace("\\", "/")
                    files[rel] = fp

    # 4. Resourcepacks
    rp_dir = os.path.join(MC_DIR, "resourcepacks")
    if os.path.exists(rp_dir):
        for f in os.listdir(rp_dir):
            if f.endswith(".zip") or f.endswith(".rar"):
                fp = os.path.join(rp_dir, f)
                if os.path.isfile(fp):
                    rel = os.path.join("resourcepacks", f).replace("\\", "/")
                    files[rel] = fp

    # 5. Root config files
    for root_f in ["options.txt", "optionsshaders.txt", "servers.dat"]:
        fp = os.path.join(MC_DIR, root_f)
        if os.path.exists(fp):
            files[root_f] = fp

    return files

def build_manifest(files_map, version="1.0.0", neoforge_version="21.1.248"):
    manifest_files = {}
    print(f"Вычисление SHA1 хешей для {len(files_map)} файлов сборки...")
    for i, (rel_path, abs_path) in enumerate(files_map.items()):
        sha = calculate_sha1(abs_path)
        sz = os.path.getsize(abs_path)
        manifest_files[rel_path] = {
            "sha1": sha,
            "size": sz
        }
        if (i + 1) % 50 == 0 or i + 1 == len(files_map):
            print(f"  Проверено {i + 1}/{len(files_map)} файлов...")

    manifest = {
        "build_name": "Minecraft NeoForge 1.21.1 Clean Build",
        "version": version,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "neoforge_version": neoforge_version,
        "total_files": len(manifest_files),
        "files": manifest_files
    }
    return manifest

def export_and_push(remote_url=None, commit_message=None, repo_dir=DEFAULT_REPO_DIR):
    print("==================================================")
    print("      ПУБЛИКАЦИЯ СБОРКИ MINECRAFT НА GITHUB       ")
    print("==================================================")

    # 1. Scan files
    files_map = gather_build_files()
    print(f"\nНайдено файлов сборки: {len(files_map)}")

    # 2. Build manifest
    manifest = build_manifest(files_map)

    # 3. Setup repo directory
    os.makedirs(repo_dir, exist_ok=True)
    
    # 4. Sync files to repo folder
    print(f"\nСинхронизация файлов в папку репозитория: {repo_dir}...")
    
    # Write manifest.json
    manifest_path = os.path.join(repo_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    # Copy files
    for rel_path, abs_path in files_map.items():
        dst = os.path.join(repo_dir, rel_path)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        # Copy if not exists or size/mtime different
        if not os.path.exists(dst) or os.path.getsize(dst) != os.path.getsize(abs_path):
            shutil.copy2(abs_path, dst)

    # Remove files from repo that are deleted locally
    for root, _, fs in os.walk(repo_dir):
        if ".git" in root: continue
        for f in fs:
            if f == "manifest.json" or f == ".gitignore" or f == "README.md": continue
            full = os.path.join(root, f)
            rel = os.path.relpath(full, repo_dir).replace("\\", "/")
            if rel not in files_map:
                os.remove(full)
                print(f"  Удален устаревший файл из репозитория: {rel}")

    # Write .gitignore in repo
    gitignore_path = os.path.join(repo_dir, ".gitignore")
    with open(gitignore_path, "w", encoding="utf-8") as f:
        f.write(".git/\n*.tmp\n*.download\n")

    # 5. Git operations
    print("\nВыполнение Git операций...")
    
    # Check git init
    if not os.path.exists(os.path.join(repo_dir, ".git")):
        subprocess.run(["git", "init"], cwd=repo_dir, check=True)
        print("  Инициализирован git репозиторий.")

    # Configure local git user if not set
    subprocess.run(["git", "config", "--local", "user.name", "Tideathan"], cwd=repo_dir, check=False)
    subprocess.run(["git", "config", "--local", "user.email", "Tideathan@users.noreply.github.com"], cwd=repo_dir, check=False)
    subprocess.run(["git", "branch", "-M", "main"], cwd=repo_dir, check=False)

    # Git LFS setup for large files (> 100MB)
    try:
        subprocess.run(["git", "lfs", "install"], cwd=repo_dir, capture_output=True, check=False)
        subprocess.run(["git", "lfs", "track", "mods/spore_1.21.1_2.2.0j_neo.jar"], cwd=repo_dir, capture_output=True, check=False)
    except Exception:
        pass

    if remote_url:
        subprocess.run(["git", "remote", "remove", "origin"], cwd=repo_dir, capture_output=True)
        subprocess.run(["git", "remote", "add", "origin", remote_url], cwd=repo_dir, check=True)
        print(f"  Установлен remote origin: {remote_url}")

    subprocess.run(["git", "add", "-A"], cwd=repo_dir, check=True)
    
    if not commit_message:
        commit_message = f"Update build: {datetime.now().strftime('%Y-%m-%d %H:%M')} ({len(files_map)} files)"
    
    res = subprocess.run(["git", "commit", "-m", commit_message], cwd=repo_dir, capture_output=True, text=True)
    if "nothing to commit" in res.stdout:
        print("  Нет изменений для коммита (сборка уже актуальна).")
    else:
        print(f"  Создан коммит: {commit_message}")

    # Push if remote is configured
    try:
        print("  Отправка изменений на GitHub (origin main)...")
        push_res = subprocess.run(["git", "push", "-u", "origin", "main"], cwd=repo_dir, capture_output=True, text=True)
        if push_res.returncode == 0:
            print("  [OK] Успешно отправлено на GitHub (origin/main)!")
        else:
            print(f"  Git push info: {push_res.stderr.strip() or push_res.stdout.strip()}")
    except Exception as e:
        print(f"  Предупреждение при push: {e}")

    print("\n[OK] Экспорт и сборка манифеста завершены!")
    print(f"Манифест: {manifest_path}")
    print("==================================================")

DEFAULT_REMOTE_URL = "https://github.com/Tideathan/Minecraft.git"

if __name__ == "__main__":
    remote = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_REMOTE_URL
    export_and_push(remote)
