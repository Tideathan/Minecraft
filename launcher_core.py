import os
import sys
import json
import uuid
import subprocess

MC_DIR = os.path.normpath(r"c:\Users\user\AppData\Roaming\.minecraft")
DEFAULT_JAVA = os.path.join(MC_DIR, "runtime", "java-runtime-delta", "windows", "java-runtime-delta", "bin", "javaw.exe")
if not os.path.exists(DEFAULT_JAVA):
    DEFAULT_JAVA = "javaw.exe"

def build_launch_command(
    username, 
    version_id="neoforge-21.1.250", 
    ram_mb=10240, 
    java_path=None, 
    width=1280, 
    height=720,
    gc_type="ZGC",
    custom_jvm_args=""
):
    if not java_path or not os.path.exists(java_path):
        java_path = DEFAULT_JAVA

    version_dir = os.path.join(MC_DIR, "versions", version_id)
    version_json_path = os.path.join(version_dir, f"{version_id}.json")
    
    if not os.path.exists(version_json_path):
        raise FileNotFoundError(f"Version json not found: {version_json_path}")

    with open(version_json_path, "r", encoding="utf-8") as f:
        vdata = json.load(f)

    natives_dir = os.path.join(version_dir, "natives")
    libs_dir = os.path.join(MC_DIR, "libraries")
    assets_dir = os.path.join(MC_DIR, "assets")

    # 1. Resolve Classpath
    classpath = []
    for lib in vdata.get("libraries", []):
        rules = lib.get("rules", [])
        allowed = True
        for r in rules:
            action = r.get("action")
            os_rule = r.get("os", {})
            os_name = os_rule.get("name")
            if action == "allow" and os_name and os_name != "windows":
                allowed = False
            elif action == "disallow" and (not os_name or os_name == "windows"):
                allowed = False
        if not allowed:
            continue

        downloads = lib.get("downloads", {})
        artifact = downloads.get("artifact", {})
        path = artifact.get("path")
        if not path:
            name_parts = lib.get("name", "").split(":")
            if len(name_parts) >= 3:
                group, artifact_id, ver = name_parts[0], name_parts[1], name_parts[2]
                classifier = f"-{name_parts[3]}" if len(name_parts) > 3 else ""
                path = f"{group.replace('.', '/')}/{artifact_id}/{ver}/{artifact_id}-{ver}{classifier}.jar"
        if path:
            full_path = os.path.normpath(os.path.join(libs_dir, path))
            if os.path.exists(full_path):
                classpath.append(full_path)

    client_jar = os.path.join(version_dir, f"{version_id}.jar")
    if os.path.exists(client_jar):
        classpath.append(client_jar)

    cp_string = ";".join(classpath)

    # 2. Player UUID
    player_uuid = uuid.uuid3(uuid.NAMESPACE_DNS, username).hex

    # 3. Replacements map
    replacements = {
        "${natives_directory}": natives_dir,
        "${launcher_name}": "AntigravityLauncher",
        "${launcher_version}": "2.0.0",
        "${classpath}": cp_string,
        "${version_name}": version_id,
        "${library_directory}": libs_dir,
        "${classpath_separator}": ";",
        "${auth_player_name}": username,
        "${game_directory}": MC_DIR,
        "${assets_root}": assets_dir,
        "${assets_index_name}": "17",
        "${auth_uuid}": player_uuid,
        "${auth_access_token}": "0",
        "${clientid}": "null",
        "${auth_xuid}": "null",
        "${user_type}": "mojang",
        "${version_type}": "release",
        "${resolution_width}": str(width),
        "${resolution_height}": str(height),
    }

    # 4. JVM Arguments
    jvm_args = [
        f"-Xmx{ram_mb}M",
        "-Xms2048M",
        "-Dfml.ignoreInvalidMinecraftCertificates=true",
        "-Dfml.ignorePatchDiscrepancies=true",
        "-Djava.net.preferIPv4Stack=true",
    ]

    # Select Garbage Collector
    if gc_type == "ZGC":
        jvm_args.extend([
            "-XX:+UnlockExperimentalVMOptions",
            "-XX:+UseZGC",
            "-XX:+ZGenerational"
        ])
    elif gc_type == "G1GC":
        jvm_args.extend([
            "-XX:+UnlockExperimentalVMOptions",
            "-XX:+UseG1GC",
            "-XX:G1NewSizePercent=20",
            "-XX:G1ReservePercent=20",
            "-XX:MaxGCPauseMillis=50",
            "-XX:G1HeapRegionSize=32M"
        ])
    elif gc_type == "Shenandoah":
        jvm_args.extend([
            "-XX:+UnlockExperimentalVMOptions",
            "-XX:+UseShenandoahGC"
        ])

    log_cfg = os.path.join(assets_dir, "log_configs", "client-1.12.xml")
    if os.path.exists(log_cfg):
        jvm_args.append(f"-Dlog4j.configurationFile={log_cfg}")

    # Append any custom user JVM args
    if custom_jvm_args and custom_jvm_args.strip():
        for custom_arg in custom_jvm_args.split():
            if custom_arg.strip():
                jvm_args.append(custom_arg.strip())

    for arg in vdata.get("arguments", {}).get("jvm", []):
        if isinstance(arg, str):
            val = arg
            for k, v in replacements.items():
                val = val.replace(k, v)
            jvm_args.append(val)
            continue
        rules = arg.get("rules", [])
        allowed = True
        for r in rules:
            os_rule = r.get("os", {})
            os_name = os_rule.get("name")
            if r.get("action") == "allow" and os_name and os_name != "windows":
                allowed = False
        if not allowed:
            continue
        vals = arg.get("values", [])
        if "value" in arg:
            v = arg["value"]
            vals = v if isinstance(v, list) else [v]
        for val in vals:
            for k, v in replacements.items():
                val = val.replace(k, v)
            jvm_args.append(val)

    # 5. Main Class
    main_class = vdata.get("mainClass", "cpw.mods.bootstraplauncher.BootstrapLauncher")

    # 6. Game Arguments
    game_args = []
    for arg in vdata.get("arguments", {}).get("game", []):
        if isinstance(arg, str):
            val = arg
            for k, v in replacements.items():
                val = val.replace(k, v)
            game_args.append(val)
            continue
        rules = arg.get("rules", [])
        allowed = True
        for r in rules:
            features = r.get("features", {})
            if features.get("is_demo_user") or features.get("has_quick_plays_support") or features.get("is_quick_play_singleplayer") or features.get("is_quick_play_multiplayer") or features.get("is_quick_play_realms"):
                allowed = False
        if not allowed:
            continue
        vals = arg.get("values", [])
        if "value" in arg:
            v = arg["value"]
            vals = v if isinstance(v, list) else [v]
        for val in vals:
            for k, v in replacements.items():
                val = val.replace(k, v)
            game_args.append(val)

    cmd = [java_path] + jvm_args + [main_class] + game_args
    return cmd
