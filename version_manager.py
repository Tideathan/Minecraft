import os
import json
import urllib.request
import xml.etree.ElementTree as ET
import subprocess

_CURR_DIR = os.path.dirname(os.path.abspath(__file__))
MC_DIR = os.path.normpath(os.path.join(_CURR_DIR, "..")) if os.path.basename(_CURR_DIR).lower() == "launcher" else os.path.normpath(r"c:\Users\user\AppData\Roaming\.minecraft")
VERSIONS_DIR = os.path.join(MC_DIR, "versions")
MAVEN_METADATA_URL = "https://maven.neoforged.net/releases/net/neoforged/neoforge/maven-metadata.xml"

def get_installed_versions():
    result = []
    if not os.path.exists(VERSIONS_DIR):
        return result

    dirs = os.listdir(VERSIONS_DIR)
    dirs.sort(reverse=True)
    
    for v_id in dirs:
        json_file = os.path.join(VERSIONS_DIR, v_id, f"{v_id}.json")
        if os.path.exists(json_file):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}

            is_neoforge = "neoforge" in v_id.lower() or "neoforge" in data.get("mainClass", "").lower()
            if is_neoforge:
                ver_num = v_id.replace("neoforge-", "").replace("NeoForge-", "")
                label = f"NeoForge {ver_num}"
                if ver_num == "21.1.248":
                    label += " (Рекомендуемая)"
                elif ver_num == "21.1.250":
                    label += " (NeoForge)"
            elif v_id == "1.21.1":
                label = "Minecraft 1.21.1 (Vanilla)"
            else:
                label = v_id

            result.append({
                "id": v_id,
                "label": label,
                "is_neoforge": is_neoforge,
                "json_path": json_file
            })
    return result

def fetch_available_neoforge_versions(mc_target="21.1"):
    try:
        req = urllib.request.Request(MAVEN_METADATA_URL, headers={"User-Agent": "AntigravityLauncher/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            xml_data = resp.read()
        root = ET.fromstring(xml_data)
        versions = [v.text for v in root.findall(".//version") if v.text and v.text.startswith(mc_target)]
        versions.sort(key=lambda x: [int(p) for p in x.split(".")], reverse=True)
        return versions[:20]
    except Exception as e:
        print(f"Error fetching NeoForge versions: {e}")
        return ["21.1.248", "21.1.250", "21.1.238"]

def install_neoforge_version(neoforge_ver, java_exe, progress_callback=None):
    installer_url = f"https://maven.neoforged.net/releases/net/neoforged/neoforge/{neoforge_ver}/neoforge-{neoforge_ver}-installer.jar"
    temp_dir = os.path.join(MC_DIR, "runtime")
    os.makedirs(temp_dir, exist_ok=True)
    installer_path = os.path.join(temp_dir, f"neoforge-{neoforge_ver}-installer.jar")

    try:
        # Ensure launcher_profiles.json exists (required by NeoForge installer)
        lp_path = os.path.join(MC_DIR, "launcher_profiles.json")
        if not os.path.exists(lp_path):
            with open(lp_path, "w", encoding="utf-8") as lpf:
                json.dump({"profiles": {}}, lpf, indent=2)

        if progress_callback:
            progress_callback(0.1, f"Скачивание установщика NeoForge {neoforge_ver}...")

        req = urllib.request.Request(installer_url, headers={"User-Agent": "AntigravityLauncher/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp, open(installer_path, "wb") as out_f:
            while chunk := resp.read(65536):
                out_f.write(chunk)

        if progress_callback:
            progress_callback(0.35, f"Установка NeoForge {neoforge_ver} (загрузка библиотек Mojang и сборки)...")

        # Resolve java.exe for console execution
        runner = java_exe
        if "javaw.exe" in runner.lower():
            cand = os.path.join(os.path.dirname(runner), "java.exe")
            if os.path.exists(cand):
                runner = cand

        cmd = [runner, "-jar", installer_path, "--install-client", MC_DIR]
        res = subprocess.run(cmd, cwd=MC_DIR, capture_output=True, text=True)

        if progress_callback:
            progress_callback(0.9, "Очистка временных файлов...")

        if os.path.exists(installer_path):
            try:
                os.remove(installer_path)
            except Exception:
                pass

        log_p = os.path.join(MC_DIR, "neoforge-installer.jar.log")
        if os.path.exists(log_p):
            try:
                os.remove(log_p)
            except Exception:
                pass

        if res.returncode != 0:
            err_msg = res.stderr.strip() or res.stdout.strip()
            return False, f"Ошибка установки NeoForge (код {res.returncode}): {err_msg[:300]}"

        if progress_callback:
            progress_callback(1.0, f"NeoForge {neoforge_ver} успешно установлен!")

        return True, f"NeoForge {neoforge_ver} успешно установлен!"
    except Exception as e:
        return False, f"Ошибка: {e}"
