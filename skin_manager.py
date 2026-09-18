import os
import shutil
from PIL import Image

MC_DIR = os.path.normpath(r"c:\Users\user\AppData\Roaming\.minecraft")
RESOURCEPACKS_DIR = os.path.join(MC_DIR, "resourcepacks")
SKIN_PACK_DIR = os.path.join(RESOURCEPACKS_DIR, "UserSkinPack")
SKIN_PREVIEW_PATH = os.path.join(MC_DIR, "current_skin_preview.png")

def validate_skin(skin_path):
    if not os.path.exists(skin_path):
        return False, "Файл не найден"
    try:
        with Image.open(skin_path) as img:
            if img.format != "PNG":
                return False, "Скин должен быть в формате PNG"
            if img.size not in [(64, 64), (64, 32)]:
                return False, f"Недопустимый размер: {img.size[0]}x{img.size[1]} (нужен 64x64 или 64x32)"
            return True, "OK"
    except Exception as e:
        return False, f"Ошибка чтения скина: {e}"

def generate_skin_preview(skin_path, out_preview_path=None):
    if not out_preview_path:
        out_preview_path = SKIN_PREVIEW_PATH
    try:
        with Image.open(skin_path) as img:
            img = img.convert("RGBA")
            is_legacy = (img.size == (64, 32))

            # Compose head with overlay
            head = img.crop((8, 8, 16, 16))
            head_overlay = img.crop((40, 8, 48, 16))
            combined_head = Image.alpha_composite(head, head_overlay)

            # Torso
            torso = img.crop((20, 20, 28, 32))
            if not is_legacy:
                torso_overlay = img.crop((20, 36, 28, 48))
                torso = Image.alpha_composite(torso, torso_overlay)

            # Left and Right Arms
            r_arm = img.crop((44, 20, 48, 32))
            if not is_legacy:
                r_arm_overlay = img.crop((44, 36, 48, 48))
                r_arm = Image.alpha_composite(r_arm, r_arm_overlay)
                l_arm = img.crop((36, 52, 40, 64))
                l_arm_overlay = img.crop((52, 52, 56, 64))
                l_arm = Image.alpha_composite(l_arm, l_arm_overlay)
            else:
                l_arm = r_arm.transpose(Image.FLIP_LEFT_RIGHT)

            # Legs
            r_leg = img.crop((4, 20, 8, 32))
            if not is_legacy:
                r_leg_overlay = img.crop((4, 36, 8, 48))
                r_leg = Image.alpha_composite(r_leg, r_leg_overlay)
                l_leg = img.crop((20, 52, 24, 64))
                l_leg_overlay = img.crop((4, 52, 8, 64))
                l_leg = Image.alpha_composite(l_leg, l_leg_overlay)
            else:
                l_leg = r_leg.transpose(Image.FLIP_LEFT_RIGHT)

            # Canvas 16x32 (Minecraft character proportions)
            char_canvas = Image.new("RGBA", (16, 32), (0, 0, 0, 0))
            char_canvas.paste(combined_head, (4, 0))
            char_canvas.paste(torso, (4, 8))
            char_canvas.paste(r_arm, (0, 8))
            char_canvas.paste(l_arm, (12, 8))
            char_canvas.paste(r_leg, (4, 20))
            char_canvas.paste(l_leg, (8, 20))

            # Upscale pixel-art cleanly with Nearest Neighbor
            preview = char_canvas.resize((96, 192), Image.Resampling.NEAREST)
            preview.save(out_preview_path, "PNG")
            return out_preview_path
    except Exception as e:
        print(f"Error generating skin preview: {e}")
        return None

def apply_skin_to_game(skin_path):
    ok, msg = validate_skin(skin_path)
    if not ok:
        return False, msg

    try:
        # Create resource pack structure
        target_dir = os.path.join(SKIN_PACK_DIR, "assets", "minecraft", "textures", "entity", "player", "wide")
        target_slim_dir = os.path.join(SKIN_PACK_DIR, "assets", "minecraft", "textures", "entity", "player", "slim")
        os.makedirs(target_dir, exist_ok=True)
        os.makedirs(target_slim_dir, exist_ok=True)

        # Copy to steve and alex and all default player textures
        defaults_wide = ["steve.png", "ari.png", "efe.png", "kai.png", "makena.png", "noor.png", "sunny.png", "zuri.png"]
        defaults_slim = ["alex.png"]

        # If 64x32, convert to 64x64 standard
        with Image.open(skin_path) as img:
            img = img.convert("RGBA")
            if img.size == (64, 32):
                new_img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
                new_img.paste(img, (0, 0))
                # copy legs & arms to lower part
                leg = img.crop((0, 16, 16, 32))
                arm = img.crop((40, 16, 56, 32))
                new_img.paste(leg, (16, 48))
                new_img.paste(arm, (32, 48))
                work_img = new_img
            else:
                work_img = img

            for name in defaults_wide:
                work_img.save(os.path.join(target_dir, name), "PNG")
            for name in defaults_slim:
                work_img.save(os.path.join(target_slim_dir, name), "PNG")

        # Write pack.mcmeta
        mcmeta_content = '''{
  "pack": {
    "pack_format": 34,
    "description": "Пользовательский скин игрока"
  }
}'''
        with open(os.path.join(SKIN_PACK_DIR, "pack.mcmeta"), "w", encoding="utf-8") as f:
            f.write(mcmeta_content)

        # Generate preview
        generate_skin_preview(skin_path)

        # Ensure pack is enabled in options.txt
        options_path = os.path.join(MC_DIR, "options.txt")
        if os.path.exists(options_path):
            with open(options_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            new_lines = []
            pack_entry = "file/UserSkinPack"
            for line in lines:
                if line.startswith("resourcePacks:"):
                    # e.g. resourcePacks:["vanilla"]
                    val = line.split(":", 1)[1].strip()
                    if pack_entry not in val:
                        # insert right after [
                        if val.startswith("["):
                            val = "[" + f'"{pack_entry}",' + val[1:]
                        else:
                            val = f'["{pack_entry}"]'
                    new_lines.append(f"resourcePacks:{val}\n")
                else:
                    new_lines.append(line)
            with open(options_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)

        return True, "Скин успешно применен в игру!"
    except Exception as e:
        return False, f"Ошибка применения скина: {e}"
