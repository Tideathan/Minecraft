import os
import re
import zipfile
import subprocess
import urllib.request
import shutil

MC_DIR = os.path.normpath(r"c:\Users\user\AppData\Roaming\.minecraft")
ADOPTIUM_URL = "https://api.adoptium.net/v3/binary/latest/21/ga/windows/x64/jre/hotspot/normal/eclipse?project=jdk"

def get_java_version_info(javaw_path):
    if not os.path.exists(javaw_path):
        return None

    # Try running java.exe in the same folder first (javaw has no console, java has stderr output)
    java_exe = os.path.join(os.path.dirname(javaw_path), "java.exe")
    exe_to_run = java_exe if os.path.exists(java_exe) else javaw_path

    try:
        proc = subprocess.run(
            [exe_to_run, "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        )
        out = proc.stderr or proc.stdout
        
        # Parse version
        version_match = re.search(r'version "([^"]+)"', out)
        ver_str = version_match.group(1) if version_match else "Неизвестно"
        
        # Major version
        if ver_str.startswith("1."):
            major = int(ver_str.split(".")[1])
        else:
            major = int(ver_str.split(".")[0]) if ver_str.split(".")[0].isdigit() else 0
            
        # Vendor
        vendor = "Java"
        if "microsoft" in out.lower():
            vendor = "Microsoft OpenJDK"
        elif "temurin" in out.lower() or "adoptium" in out.lower():
            vendor = "Eclipse Adoptium Temurin"
        elif "oracle" in out.lower():
            vendor = "Oracle"
        elif "zulu" in out.lower():
            vendor = "Azul Zulu"
        elif "openjdk" in out.lower():
            vendor = "OpenJDK"
            
        is_64bit = "64-Bit" in out
        compatible = (major >= 21)

        return {
            "path": javaw_path,
            "version": ver_str,
            "major": major,
            "vendor": vendor,
            "is_64bit": is_64bit,
            "compatible": compatible,
            "raw": out.strip()
        }
    except Exception as e:
        return {
            "path": javaw_path,
            "version": "Ошибка",
            "major": 0,
            "vendor": "Unknown",
            "is_64bit": True,
            "compatible": False,
            "raw": str(e)
        }

def find_all_javas():
    found_paths = set()
    
    # 1. Bundled runtimes
    runtime_dir = os.path.join(MC_DIR, "runtime")
    if os.path.exists(runtime_dir):
        for root, dirs, files in os.walk(runtime_dir):
            if "javaw.exe" in files:
                found_paths.add(os.path.normpath(os.path.join(root, "javaw.exe")))

    # 2. Standard Program Files
    search_dirs = [
        r"C:\Program Files\Java",
        r"C:\Program Files\Eclipse Adoptium",
        r"C:\Program Files\Microsoft",
        r"C:\Program Files\BellSoft",
        r"C:\Program Files\Zulu"
    ]
    for sdir in search_dirs:
        if os.path.exists(sdir):
            for root, dirs, files in os.walk(sdir):
                if "javaw.exe" in files:
                    found_paths.add(os.path.normpath(os.path.join(root, "javaw.exe")))

    # 3. System where javaw
    try:
        proc = subprocess.run(["where", "javaw"], stdout=subprocess.PIPE, text=True, timeout=3, creationflags=subprocess.CREATE_NO_WINDOW)
        for line in proc.stdout.splitlines():
            line = line.strip()
            if line and os.path.exists(line):
                found_paths.add(os.path.normpath(line))
    except Exception:
        pass

    results = []
    for p in sorted(found_paths):
        info = get_java_version_info(p)
        if info:
            results.append(info)

    # Sort so compatible Java 21 comes first
    def sort_key(item):
        is_exact_21 = (item["major"] == 21)
        is_bundled = "runtime" in item["path"].lower()
        return (0 if (is_exact_21 and is_bundled) else (1 if is_exact_21 else (2 if item["compatible"] else 3)))

    results.sort(key=sort_key)
    return results

def download_and_extract_java_21(progress_callback=None):
    """
    Downloads Adoptium Temurin OpenJDK 21 JRE zip and extracts to MC_DIR/runtime/java-21
    """
    target_runtime_dir = os.path.join(MC_DIR, "runtime", "java-21")
    os.makedirs(target_runtime_dir, exist_ok=True)
    temp_zip = os.path.join(MC_DIR, "runtime", "java21_download.zip")

    if progress_callback:
        progress_callback(0, 100, 0, "Подключение к серверу Adoptium...")

    req = urllib.request.Request(ADOPTIUM_URL, headers={"User-Agent": "AntigravityLauncher/1.0"})
    with urllib.request.urlopen(req) as resp:
        total_size = int(resp.headers.get("Content-Length", 48999141))
        downloaded = 0
        chunk_size = 131072 # 128 KB
        
        with open(temp_zip, "wb") as f:
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                pct = int((downloaded / total_size) * 100) if total_size else 50
                mb_down = downloaded / (1024 * 1024)
                mb_tot = total_size / (1024 * 1024)
                if progress_callback:
                    progress_callback(downloaded, total_size, pct, f"Скачивание Java 21: {mb_down:.1f} / {mb_tot:.1f} МБ ({pct}%)")

    if progress_callback:
        progress_callback(total_size, total_size, 100, "Распаковка Java 21...")

    # Extract
    with zipfile.ZipFile(temp_zip, "r") as z:
        z.extractall(target_runtime_dir)

    try:
        os.remove(temp_zip)
    except Exception:
        pass

    # Find the javaw.exe
    for root, dirs, files in os.walk(target_runtime_dir):
        if "javaw.exe" in files:
            javaw_path = os.path.normpath(os.path.join(root, "javaw.exe"))
            if progress_callback:
                progress_callback(total_size, total_size, 100, "Java 21 успешно установлена!")
            return javaw_path

    raise RuntimeError("Не удалось найти javaw.exe после распаковки.")

if __name__ == "__main__":
    javas = find_all_javas()
    print(f"Found {len(javas)} Java runtimes:")
    for j in javas:
        print(f"  {j['vendor']} {j['version']} (Major: {j['major']}, Comp: {j['compatible']}) -> {j['path']}")
