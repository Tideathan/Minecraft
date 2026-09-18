import os
import sys
import json
import subprocess
import threading
import tkinter as tk
from tkinter import messagebox, filedialog
from PIL import Image
import customtkinter as ctk

from launcher_core import (
    MC_DIR,
    DEFAULT_JAVA,
    build_launch_command
)
from java_manager import (
    find_all_javas,
    get_java_version_info,
    download_and_extract_java_21
)
from version_manager import (
    get_installed_versions,
    fetch_available_neoforge_versions,
    install_neoforge_version
)
from skin_manager import (
    validate_skin,
    generate_skin_preview,
    apply_skin_to_game,
    SKIN_PREVIEW_PATH
)
from mod_updater import (
    get_installed_mods_info,
    check_mod_updates_async,
    install_mod_update
)
from pack_distributor import (
    export_build_pack,
    import_build_pack
)
from github_sync import (
    normalize_repo_slug,
    fetch_manifest_from_github,
    compare_manifest_with_local,
    sync_differences
)
from push_to_github import export_and_push
from launcher_updater import (
    CURRENT_LAUNCHER_VERSION,
    check_launcher_update,
    apply_launcher_update,
    restart_launcher
)

LAUNCHER_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(MC_DIR, "launcher_config.json")

ICON_ICO_PATH = os.path.join(LAUNCHER_DIR, "minecraft_wolf.ico")
if not os.path.exists(ICON_ICO_PATH):
    ICON_ICO_PATH = os.path.join(MC_DIR, "minecraft_wolf.ico")
if not os.path.exists(ICON_ICO_PATH):
    ICON_ICO_PATH = os.path.join(LAUNCHER_DIR, "launcher_icon.ico")
if not os.path.exists(ICON_ICO_PATH):
    ICON_ICO_PATH = os.path.join(MC_DIR, "launcher_icon.ico")

ICON_PNG_PATH = os.path.join(LAUNCHER_DIR, "launcher_icon.png")
if not os.path.exists(ICON_PNG_PATH):
    ICON_PNG_PATH = os.path.join(MC_DIR, "launcher_icon.png")

# RAM settings (in 256 MB chunks)
RAM_MIN_MB = 4096
RAM_MAX_MB = 24576
RAM_STEP_MB = 256
DEFAULT_RAM_MB = 10240

# THEME PALETTES WITH TUPLES: (Light/Day, Dark/Night)
COLOR_CARD_BG = ("#ffffff", "#1a1e27")
COLOR_CARD_BORDER = ("#c8d1db", "#2c3342")
COLOR_INPUT_BG = ("#f1f5f9", "#151820")
COLOR_ACCENT = ("#2e7d32", "#00e676")
COLOR_ACCENT_HOVER = ("#1b5e20", "#00c853")
COLOR_BTN_SEC = ("#e2e8f0", "#262c38")
COLOR_BTN_SEC_HOVER = ("#cbd5e1", "#363e4f")
COLOR_BTN_SEC_BORDER = ("#94a3b8", "#3c4659")
COLOR_TEXT_PRIMARY = ("#1a202c", "#ffffff")
COLOR_TEXT_SECONDARY = ("#5a687c", "#8e99a8")
COLOR_BTN_PLAY = ("#2e7d32", "#00e676")
COLOR_BTN_PLAY_HOVER = ("#1b5e20", "#00c853")
COLOR_BTN_PLAY_BORDER = ("#1b5e20", "#00ff88")

def load_config():
    default_cfg = {
        "username": "Adolf",
        "version": "neoforge-21.1.250",
        "ram_mb": DEFAULT_RAM_MB,
        "width": 1280,
        "height": 720,
        "java_path": DEFAULT_JAVA,
        "gc_type": "ZGC",
        "custom_jvm_args": "",
        "theme": "night",
        "skin_path": "",
        "github_repo": "Tideathan/Minecraft",
        "github_branch": "main",
        "cloud_sync_url": ""
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                default_cfg.update(data)
        except Exception:
            pass
    return default_cfg

def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving config: {e}")

class ModernLauncherApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.cfg = load_config()
        self.current_theme_key = self.cfg.get("theme", "night")
        if self.current_theme_key not in ["day", "night"]:
            self.current_theme_key = "night"

        # Apply appearance mode dynamically
        ctk.set_appearance_mode("Dark" if self.current_theme_key == "night" else "Light")

        self.title("Minecraft NeoForge Launcher")
        self.geometry("920x730")
        self.minsize(860, 680)

        if os.path.exists(ICON_ICO_PATH):
            try:
                self.iconbitmap(ICON_ICO_PATH)
            except Exception:
                pass

        self.game_process = None
        self.detected_javas = []
        self.installed_versions = []
        self.updates_cache = []
        self.github_diff = None

        self.create_ui()
        self.refresh_all_data()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def create_ui(self):
        # 1. Header Frame
        self.header = ctk.CTkFrame(
            self, 
            corner_radius=12, 
            fg_color=COLOR_CARD_BG,
            border_width=1,
            border_color=COLOR_CARD_BORDER
        )
        self.header.pack(fill="x", padx=16, pady=(12, 6))

        # Wolf Logo
        if os.path.exists(ICON_PNG_PATH):
            try:
                pil_img = Image.open(ICON_PNG_PATH)
                self.logo_ctk = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(52, 52))
                self.logo_lbl = ctk.CTkLabel(self.header, text="", image=self.logo_ctk)
                self.logo_lbl.pack(side="left", padx=(14, 6), pady=8)
            except Exception:
                pass

        # Title Box
        title_box = ctk.CTkFrame(self.header, fg_color="transparent")
        title_box.pack(side="left", padx=8, pady=8)

        self.title_lbl = ctk.CTkLabel(
            title_box,
            text="MINECRAFT LAUNCHER",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=COLOR_ACCENT
        )
        self.title_lbl.pack(anchor="w")

        self.subtitle_lbl = ctk.CTkLabel(
            title_box,
            text="NeoForge 1.21.1 • Photon Shaders • Generational ZGC",
            font=ctk.CTkFont(size=12),
            text_color=COLOR_TEXT_SECONDARY
        )
        self.subtitle_lbl.pack(anchor="w")

        # Right Controls: Theme toggle & Folder button
        right_box = ctk.CTkFrame(self.header, fg_color="transparent")
        right_box.pack(side="right", padx=14, pady=8)

        # Theme toggle button
        theme_icon_text = "☀️ День" if self.current_theme_key == "night" else "🌙 Ночь"
        self.btn_theme = ctk.CTkButton(
            right_box,
            text=theme_icon_text,
            width=90,
            height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=COLOR_BTN_SEC,
            hover_color=COLOR_BTN_SEC_HOVER,
            border_width=1,
            border_color=COLOR_BTN_SEC_BORDER,
            text_color=COLOR_TEXT_PRIMARY,
            command=self.toggle_theme_dynamic
        )
        self.btn_theme.pack(side="left", padx=6)

        btn_folder = ctk.CTkButton(
            right_box,
            text="📂 Папка игры",
            width=105,
            height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=COLOR_BTN_SEC,
            hover_color=COLOR_BTN_SEC_HOVER,
            border_width=1,
            border_color=COLOR_BTN_SEC_BORDER,
            text_color=COLOR_TEXT_PRIMARY,
            command=lambda: os.startfile(MC_DIR)
        )
        btn_folder.pack(side="left", padx=6)

        # 2. Tabs
        self.tabview = ctk.CTkTabview(self, corner_radius=12)
        self.tabview.pack(fill="both", expand=True, padx=16, pady=6)

        self.tab_play = self.tabview.add("🎮 Игра")
        self.tab_github = self.tabview.add("🌐 Сборка и GitHub")
        self.tab_mods = self.tabview.add("🧩 Моды")
        self.tab_settings = self.tabview.add("⚙️ Настройки")
        self.tab_console = self.tabview.add("📋 Консоль")

        self.setup_tab_play()
        self.setup_tab_github()
        self.setup_tab_mods()
        self.setup_tab_settings()
        self.setup_tab_console()

    # --- DYNAMIC THEME SWITCH (NO RESTART) ---
    def toggle_theme_dynamic(self):
        new_theme = "day" if self.current_theme_key == "night" else "night"
        self.current_theme_key = new_theme
        self.cfg["theme"] = new_theme
        save_config(self.cfg)

        # Instantly switch appearance mode in memory
        new_mode = "Dark" if new_theme == "night" else "Light"
        ctk.set_appearance_mode(new_mode)

        # Update button text dynamically
        btn_text = "☀️ День" if new_theme == "night" else "🌙 Ночь"
        self.btn_theme.configure(text=btn_text)

        # Update Play Button text color
        if hasattr(self, "btn_play"):
            play_text_color = "#0a1f11" if new_theme == "night" else "#ffffff"
            self.btn_play.configure(text_color=play_text_color)

    # --- TAB 1: PLAY ---
    def setup_tab_play(self):
        tab = self.tab_play
        
        main_grid = ctk.CTkFrame(tab, fg_color="transparent")
        main_grid.pack(fill="both", expand=True, padx=8, pady=8)

        # Left Column: Player & Skin
        left_col = ctk.CTkFrame(
            main_grid, 
            corner_radius=12, 
            fg_color=COLOR_CARD_BG,
            border_width=1,
            border_color=COLOR_CARD_BORDER
        )
        left_col.pack(side="left", fill="both", expand=False, padx=(0, 8), pady=0, ipadx=10)

        ctk.CTkLabel(left_col, text="ПРОФИЛЬ ИГРОКА", font=ctk.CTkFont(size=13, weight="bold"), text_color=COLOR_ACCENT).pack(anchor="w", padx=16, pady=(14, 8))

        ctk.CTkLabel(left_col, text="Никнейм:", font=ctk.CTkFont(size=12), text_color=COLOR_TEXT_SECONDARY).pack(anchor="w", padx=16)
        self.entry_username = ctk.CTkEntry(left_col, width=200, height=36, font=ctk.CTkFont(size=14, weight="bold"))
        self.entry_username.insert(0, self.cfg.get("username", "Adolf"))
        self.entry_username.pack(anchor="w", padx=16, pady=(4, 12))
        self.entry_username.bind("<KeyRelease>", lambda e: self.on_config_change())

        # Skin Section
        ctk.CTkLabel(left_col, text="Скин игрока:", font=ctk.CTkFont(size=12), text_color=COLOR_TEXT_SECONDARY).pack(anchor="w", padx=16)
        
        self.skin_preview_lbl = ctk.CTkLabel(
            left_col, 
            text="[Нет скина]", 
            width=96, 
            height=192,
            fg_color=COLOR_INPUT_BG,
            corner_radius=8
        )
        self.skin_preview_lbl.pack(anchor="center", pady=(6, 10))

        btn_load_skin = ctk.CTkButton(
            left_col,
            text="👔 Загрузить скин (.png)",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=COLOR_BTN_SEC,
            hover_color=COLOR_BTN_SEC_HOVER,
            border_width=1,
            border_color=COLOR_BTN_SEC_BORDER,
            text_color=COLOR_TEXT_PRIMARY,
            command=self.select_and_apply_skin
        )
        btn_load_skin.pack(anchor="center", padx=16, pady=(0, 14))

        self.update_skin_preview_ui()

        # Right Column: RAM, Launch, Version Info
        right_col = ctk.CTkFrame(
            main_grid, 
            corner_radius=12, 
            fg_color=COLOR_CARD_BG,
            border_width=1,
            border_color=COLOR_CARD_BORDER
        )
        right_col.pack(side="right", fill="both", expand=True, padx=(8, 0), pady=0)

        # RAM Slider (256 MB chunks)
        ctk.CTkLabel(right_col, text="ВЫДЕЛЕНИЕ ОПЕРАТИВНОЙ ПАМЯТИ", font=ctk.CTkFont(size=13, weight="bold"), text_color=COLOR_ACCENT).pack(anchor="w", padx=16, pady=(14, 4))
        
        self.lbl_ram_val = ctk.CTkLabel(right_col, text="", font=ctk.CTkFont(size=15, weight="bold"), text_color=COLOR_ACCENT)
        self.lbl_ram_val.pack(anchor="w", padx=16, pady=(0, 4))

        self.ram_slider = ctk.CTkSlider(
            right_col,
            from_=RAM_MIN_MB,
            to=RAM_MAX_MB,
            number_of_steps=int((RAM_MAX_MB - RAM_MIN_MB) / RAM_STEP_MB),
            command=self.on_ram_slider_change
        )
        curr_ram = self.cfg.get("ram_mb", DEFAULT_RAM_MB)
        self.ram_slider.set(curr_ram)
        self.ram_slider.pack(fill="x", padx=16, pady=(0, 8))
        self.update_ram_label(curr_ram)

        # Quick RAM presets
        preset_frame = ctk.CTkFrame(right_col, fg_color="transparent")
        preset_frame.pack(fill="x", padx=16, pady=(0, 14))

        presets = [(6144, "6 ГБ"), (8192, "8 ГБ"), (10240, "10 ГБ ★"), (12288, "12 ГБ"), (16384, "16 ГБ")]
        for mb, name in presets:
            btn = ctk.CTkButton(
                preset_frame,
                text=name,
                width=65,
                height=26,
                font=ctk.CTkFont(size=11),
                fg_color=COLOR_BTN_SEC,
                hover_color=COLOR_BTN_SEC_HOVER,
                border_width=1,
                border_color=COLOR_BTN_SEC_BORDER,
                text_color=COLOR_TEXT_PRIMARY,
                command=lambda val=mb: self.set_ram_preset(val)
            )
            btn.pack(side="left", padx=3)

        # Launch Status & Play Button Area
        play_card = ctk.CTkFrame(right_col, corner_radius=10, fg_color=COLOR_INPUT_BG)
        play_card.pack(fill="both", expand=True, padx=16, pady=(6, 16))

        self.lbl_play_version = ctk.CTkLabel(
            play_card,
            text="Сборка: " + self.cfg.get("version", "neoforge-21.1.250"),
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=COLOR_TEXT_SECONDARY
        )
        self.lbl_play_version.pack(pady=(16, 4))

        self.lbl_play_details = ctk.CTkLabel(
            play_card,
            text="Шейдер Photon 1.3b • Память чанками по 256 МБ • ZGC включен",
            font=ctk.CTkFont(size=12),
            text_color=COLOR_TEXT_SECONDARY
        )
        self.lbl_play_details.pack(pady=(0, 16))

        play_text_color = "#0a1f11" if self.current_theme_key == "night" else "#ffffff"
        self.btn_play = ctk.CTkButton(
            play_card,
            text="▶   ИГРАТЬ",
            height=60,
            width=280,
            font=ctk.CTkFont(size=22, weight="bold"),
            fg_color=COLOR_BTN_PLAY,
            hover_color=COLOR_BTN_PLAY_HOVER,
            text_color=play_text_color,
            corner_radius=8,
            border_width=2,
            border_color=COLOR_BTN_PLAY_BORDER,
            command=self.launch_game
        )
        self.btn_play.pack(pady=(4, 12))

        self.lbl_status = ctk.CTkLabel(
            play_card,
            text="Готов к запуску",
            font=ctk.CTkFont(size=12),
            text_color=COLOR_TEXT_SECONDARY
        )
        self.lbl_status.pack(pady=(0, 10))

    # --- TAB 2: GITHUB & BUILD SYNC ---
    def setup_tab_github(self):
        tab = self.tab_github

        # Top Section: Remote Repository Settings
        repo_card = ctk.CTkFrame(tab, corner_radius=12, fg_color=COLOR_CARD_BG, border_width=1, border_color=COLOR_CARD_BORDER)
        repo_card.pack(fill="x", padx=16, pady=(10, 6))

        ctk.CTkLabel(repo_card, text="🌐 ОБНОВЛЕНИЕ И СИНХРОНИЗАЦИЯ ЧЕРЕЗ GITHUB", font=ctk.CTkFont(size=14, weight="bold"), text_color=COLOR_ACCENT).pack(anchor="w", padx=16, pady=(12, 4))
        ctk.CTkLabel(
            repo_card, 
            text="Любой игрок может проверить версию сборки с репозиторием GitHub, увидеть различия и в 1 клик докачать только новые/измененные моды и конфиги без перекачивания всей сборки!",
            font=ctk.CTkFont(size=12),
            text_color=COLOR_TEXT_SECONDARY,
            justify="left"
        ).pack(anchor="w", padx=16, pady=(0, 10))

        row_repo = ctk.CTkFrame(repo_card, fg_color="transparent")
        row_repo.pack(fill="x", padx=16, pady=(0, 12))

        ctk.CTkLabel(row_repo, text="GitHub репозиторий:", font=ctk.CTkFont(size=12), text_color=COLOR_TEXT_SECONDARY).pack(side="left", padx=(0, 8))
        self.entry_github_repo = ctk.CTkEntry(row_repo, width=280, height=34, font=ctk.CTkFont(size=12))
        self.entry_github_repo.insert(0, self.cfg.get("github_repo", "Tideathan/Minecraft"))
        self.entry_github_repo.pack(side="left", padx=(0, 10))
        self.entry_github_repo.bind("<KeyRelease>", lambda e: self.on_config_change())

        self.btn_check_github = ctk.CTkButton(
            row_repo,
            text="🔍 Проверить версию на GitHub",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=COLOR_ACCENT,
            hover_color=COLOR_ACCENT_HOVER,
            text_color="#000000" if self.current_theme_key == "night" else "#ffffff",
            command=self.start_check_github_version
        )
        self.btn_check_github.pack(side="left", padx=4)

        self.btn_sync_github = ctk.CTkButton(
            row_repo,
            text="⚡ Докачать обновления",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=COLOR_BTN_SEC,
            hover_color=COLOR_BTN_SEC_HOVER,
            border_width=1,
            border_color=COLOR_BTN_SEC_BORDER,
            text_color=COLOR_TEXT_PRIMARY,
            state="disabled",
            command=self.start_sync_github_diff
        )
        self.btn_sync_github.pack(side="left", padx=4)

        # Progress bar
        self.github_progress = ctk.CTkProgressBar(tab)
        self.github_progress.set(0)
        self.github_progress.pack(fill="x", padx=16, pady=(4, 4))

        self.lbl_github_status = ctk.CTkLabel(tab, text="Укажите репозиторий и нажмите 'Проверить версию на GitHub'", font=ctk.CTkFont(size=12), text_color=COLOR_TEXT_SECONDARY)
        self.lbl_github_status.pack(anchor="w", padx=16, pady=(0, 6))

        # Diff View Frame
        self.github_diff_frame = ctk.CTkScrollableFrame(tab, corner_radius=10, fg_color=COLOR_CARD_BG)
        self.github_diff_frame.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        # Bottom Author Controls Frame
        author_card = ctk.CTkFrame(tab, corner_radius=10, fg_color=COLOR_INPUT_BG)
        author_card.pack(fill="x", padx=16, pady=(0, 10))

        ctk.CTkLabel(author_card, text="🛠️ ИНСТРУМЕНТЫ СОЗДАТЕЛЯ СБОРКИ:", font=ctk.CTkFont(size=12, weight="bold"), text_color=COLOR_TEXT_PRIMARY).pack(side="left", padx=14, pady=8)

        btn_push = ctk.CTkButton(
            author_card,
            text="🚀 Собрать манифест и загрузить на GitHub",
            height=30,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=COLOR_BTN_SEC,
            hover_color=COLOR_BTN_SEC_HOVER,
            border_width=1,
            border_color=COLOR_BTN_SEC_BORDER,
            text_color=COLOR_TEXT_PRIMARY,
            command=self.action_push_to_github
        )
        btn_push.pack(side="left", padx=6, pady=8)

        btn_export_zip = ctk.CTkButton(
            author_card,
            text="💾 Экспорт сборки в .ZIP",
            height=30,
            font=ctk.CTkFont(size=11),
            fg_color=COLOR_BTN_SEC,
            hover_color=COLOR_BTN_SEC_HOVER,
            border_width=1,
            border_color=COLOR_BTN_SEC_BORDER,
            text_color=COLOR_TEXT_PRIMARY,
            command=self.start_export_pack
        )
        btn_export_zip.pack(side="left", padx=6, pady=8)

    # --- TAB 3: MODS ---
    def setup_tab_mods(self):
        tab = self.tab_mods

        header_frame = ctk.CTkFrame(tab, fg_color="transparent")
        header_frame.pack(fill="x", padx=12, pady=10)

        self.lbl_mods_count = ctk.CTkLabel(
            header_frame,
            text="Установлено модов: ...",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=COLOR_ACCENT
        )
        self.lbl_mods_count.pack(side="left")

        self.btn_check_updates = ctk.CTkButton(
            header_frame,
            text="🔍 Проверить обновления модов",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=COLOR_ACCENT,
            hover_color=COLOR_ACCENT_HOVER,
            text_color="#000000" if self.current_theme_key == "night" else "#ffffff",
            command=self.start_check_updates
        )
        self.btn_check_updates.pack(side="right", padx=6)

        self.btn_update_all = ctk.CTkButton(
            header_frame,
            text="⚡ Обновить всё",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=COLOR_BTN_SEC,
            hover_color=COLOR_BTN_SEC_HOVER,
            border_width=1,
            border_color=COLOR_BTN_SEC_BORDER,
            text_color=COLOR_TEXT_PRIMARY,
            state="disabled",
            command=self.start_update_all_mods
        )
        self.btn_update_all.pack(side="right", padx=6)

        self.mods_progress = ctk.CTkProgressBar(tab)
        self.mods_progress.set(0)
        self.mods_progress.pack(fill="x", padx=12, pady=(0, 6))

        self.lbl_mods_status = ctk.CTkLabel(
            tab,
            text="Все моды проверены под NeoForge 1.21.1",
            font=ctk.CTkFont(size=12),
            text_color=COLOR_TEXT_SECONDARY
        )
        self.lbl_mods_status.pack(anchor="w", padx=12, pady=(0, 6))

        self.mods_scroll = ctk.CTkScrollableFrame(tab, corner_radius=10, fg_color=COLOR_CARD_BG)
        self.mods_scroll.pack(fill="both", expand=True, padx=12, pady=(0, 10))

    # --- TAB 4: SETTINGS ---
    def setup_tab_settings(self):
        tab = self.tab_settings

        scroll = ctk.CTkScrollableFrame(tab, corner_radius=12, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=4, pady=4)

        # Version Setting
        card_v = ctk.CTkFrame(scroll, corner_radius=10, fg_color=COLOR_CARD_BG, border_width=1, border_color=COLOR_CARD_BORDER)
        card_v.pack(fill="x", pady=6)
        ctk.CTkLabel(card_v, text="ВЕРСИЯ NEOFORGE / MINECRAFT", font=ctk.CTkFont(size=13, weight="bold"), text_color=COLOR_ACCENT).pack(anchor="w", padx=16, pady=(12, 4))
        
        v_box = ctk.CTkFrame(card_v, fg_color="transparent")
        v_box.pack(fill="x", padx=16, pady=(2, 12))

        self.combo_versions = ctk.CTkComboBox(v_box, width=320, height=36, font=ctk.CTkFont(size=13), command=self.on_version_selected)
        self.combo_versions.pack(side="left", padx=(0, 10))

        btn_install_nf = ctk.CTkButton(
            v_box,
            text="➕ Установить другую версию NeoForge",
            height=36,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=COLOR_BTN_SEC,
            hover_color=COLOR_BTN_SEC_HOVER,
            border_width=1,
            border_color=COLOR_BTN_SEC_BORDER,
            text_color=COLOR_TEXT_PRIMARY,
            command=self.open_neoforge_installer_modal
        )
        btn_install_nf.pack(side="left")

        # Java Setting
        card_j = ctk.CTkFrame(scroll, corner_radius=10, fg_color=COLOR_CARD_BG, border_width=1, border_color=COLOR_CARD_BORDER)
        card_j.pack(fill="x", pady=6)
        ctk.CTkLabel(card_j, text="JAVA RUNTIME", font=ctk.CTkFont(size=13, weight="bold"), text_color=COLOR_ACCENT).pack(anchor="w", padx=16, pady=(12, 4))

        j_box = ctk.CTkFrame(card_j, fg_color="transparent")
        j_box.pack(fill="x", padx=16, pady=(2, 8))

        self.combo_java = ctk.CTkComboBox(j_box, width=460, height=36, font=ctk.CTkFont(size=12), values=["Поиск установленных Java..."], command=self.on_java_selected)
        self.combo_java.set("Поиск установленных Java...")
        self.combo_java.pack(side="left", padx=(0, 10))

        btn_dl_java = ctk.CTkButton(
            j_box,
            text="📥 Скачать Java 21",
            height=36,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=COLOR_ACCENT,
            hover_color=COLOR_ACCENT_HOVER,
            text_color="#000000" if self.current_theme_key == "night" else "#ffffff",
            command=self.download_java_action
        )
        btn_dl_java.pack(side="left")

        self.java_progress = ctk.CTkProgressBar(card_j)
        self.java_progress.set(0)
        self.java_progress.pack(fill="x", padx=16, pady=(0, 6))

        self.lbl_java_status = ctk.CTkLabel(card_j, text="Проверка совместимости Java...", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_SECONDARY)
        self.lbl_java_status.pack(anchor="w", padx=16, pady=(0, 12))

        # GC & JVM Arguments Setting
        card_jvm = ctk.CTkFrame(scroll, corner_radius=10, fg_color=COLOR_CARD_BG, border_width=1, border_color=COLOR_CARD_BORDER)
        card_jvm.pack(fill="x", pady=6)
        ctk.CTkLabel(card_jvm, text="СБОРЩИК МУСОРА (GC) И АРГУМЕНТЫ JVM", font=ctk.CTkFont(size=13, weight="bold"), text_color=COLOR_ACCENT).pack(anchor="w", padx=16, pady=(12, 4))

        gc_box = ctk.CTkFrame(card_jvm, fg_color="transparent")
        gc_box.pack(fill="x", padx=16, pady=(2, 8))

        ctk.CTkLabel(gc_box, text="Сборщик мусора:", font=ctk.CTkFont(size=12), text_color=COLOR_TEXT_SECONDARY).pack(side="left", padx=(0, 10))
        
        self.combo_gc = ctk.CTkComboBox(
            gc_box,
            width=360,
            height=34,
            font=ctk.CTkFont(size=12, weight="bold"),
            values=[
                "Generational ZGC (-XX:+UseZGC -XX:+ZGenerational)",
                "G1GC (-XX:+UseG1GC)",
                "Shenandoah GC (-XX:+UseShenandoahGC)",
                "Пользовательский (Свои аргументы)"
            ],
            command=self.on_gc_selected
        )
        curr_gc = self.cfg.get("gc_type", "ZGC")
        if curr_gc == "ZGC":
            self.combo_gc.set("Generational ZGC (-XX:+UseZGC -XX:+ZGenerational)")
        elif curr_gc == "G1GC":
            self.combo_gc.set("G1GC (-XX:+UseG1GC)")
        elif curr_gc == "Shenandoah":
            self.combo_gc.set("Shenandoah GC (-XX:+UseShenandoahGC)")
        else:
            self.combo_gc.set("Пользовательский (Свои аргументы)")
        self.combo_gc.pack(side="left")

        ctk.CTkLabel(card_jvm, text="Дополнительные аргументы JVM:", font=ctk.CTkFont(size=12), text_color=COLOR_TEXT_SECONDARY).pack(anchor="w", padx=16, pady=(4, 2))
        self.entry_jvm_args = ctk.CTkEntry(card_jvm, height=36, font=ctk.CTkFont(size=12))
        self.entry_jvm_args.insert(0, self.cfg.get("custom_jvm_args", ""))
        self.entry_jvm_args.pack(fill="x", padx=16, pady=(0, 12))
        self.entry_jvm_args.bind("<KeyRelease>", lambda e: self.on_config_change())

        # Resolution Setting
        card_res = ctk.CTkFrame(scroll, corner_radius=10, fg_color=COLOR_CARD_BG, border_width=1, border_color=COLOR_CARD_BORDER)
        card_res.pack(fill="x", pady=6)
        ctk.CTkLabel(card_res, text="РАЗРЕШЕНИЕ ЭКРАНА", font=ctk.CTkFont(size=13, weight="bold"), text_color=COLOR_ACCENT).pack(anchor="w", padx=16, pady=(12, 4))
        
        res_box = ctk.CTkFrame(card_res, fg_color="transparent")
        res_box.pack(fill="x", padx=16, pady=(2, 14))

        ctk.CTkLabel(res_box, text="Ширина:").pack(side="left", padx=(0, 4))
        self.entry_w = ctk.CTkEntry(res_box, width=70)
        self.entry_w.insert(0, str(self.cfg.get("width", 1280)))
        self.entry_w.pack(side="left", padx=(0, 16))

        ctk.CTkLabel(res_box, text="Высота:").pack(side="left", padx=(0, 4))
        self.entry_h = ctk.CTkEntry(res_box, width=70)
        self.entry_h.insert(0, str(self.cfg.get("height", 720)))
        self.entry_h.pack(side="left")

        self.entry_w.bind("<KeyRelease>", lambda e: self.on_config_change())
        self.entry_h.bind("<KeyRelease>", lambda e: self.on_config_change())

        # Launcher Version & Update Card
        card_launcher = ctk.CTkFrame(scroll, corner_radius=10, fg_color=COLOR_CARD_BG, border_width=1, border_color=COLOR_CARD_BORDER)
        card_launcher.pack(fill="x", pady=6)
        ctk.CTkLabel(card_launcher, text="О ЛАУНЧЕРЕ И ОБНОВЛЕНИЯХ", font=ctk.CTkFont(size=13, weight="bold"), text_color=COLOR_ACCENT).pack(anchor="w", padx=16, pady=(12, 4))

        row_lu = ctk.CTkFrame(card_launcher, fg_color="transparent")
        row_lu.pack(fill="x", padx=16, pady=(2, 8))

        ctk.CTkLabel(row_lu, text=f"Версия лаунчера: v{CURRENT_LAUNCHER_VERSION}", font=ctk.CTkFont(size=12, weight="bold"), text_color=COLOR_TEXT_PRIMARY).pack(side="left", padx=(0, 15))

        self.btn_check_launcher_update = ctk.CTkButton(
            row_lu,
            text="🔄 Проверить обновление лаунчера",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=COLOR_ACCENT,
            hover_color=COLOR_ACCENT_HOVER,
            text_color="#000000" if self.current_theme_key == "night" else "#ffffff",
            command=self.start_check_launcher_update
        )
        self.btn_check_launcher_update.pack(side="left")

        self.launcher_update_progress = ctk.CTkProgressBar(card_launcher)
        self.launcher_update_progress.set(0)
        self.launcher_update_progress.pack(fill="x", padx=16, pady=(0, 6))

        self.lbl_launcher_update_status = ctk.CTkLabel(
            card_launcher,
            text="Нажмите кнопку для проверки наличия обновлений лаунчера на GitHub.",
            font=ctk.CTkFont(size=11),
            text_color=COLOR_TEXT_SECONDARY
        )
        self.lbl_launcher_update_status.pack(anchor="w", padx=16, pady=(0, 12))

    # --- TAB 5: CONSOLE ---
    def setup_tab_console(self):
        tab = self.tab_console
        
        top_bar = ctk.CTkFrame(tab, fg_color="transparent")
        top_bar.pack(fill="x", padx=8, pady=(4, 6))

        btn_clear = ctk.CTkButton(
            top_bar,
            text="Очистить лог",
            width=110,
            height=28,
            font=ctk.CTkFont(size=12),
            fg_color=COLOR_BTN_SEC,
            hover_color=COLOR_BTN_SEC_HOVER,
            border_width=1,
            border_color=COLOR_BTN_SEC_BORDER,
            text_color=COLOR_TEXT_PRIMARY,
            command=lambda: self.console_text.delete("1.0", "end")
        )
        btn_clear.pack(side="right")

        self.console_text = ctk.CTkTextbox(
            tab,
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color="#0a0c10",
            text_color="#c9d1d9"
        )
        self.console_text.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.log("=== Minecraft Launcher Console Ready ===\n")

    def log(self, text):
        try:
            self.console_text.insert("end", text + "\n")
            self.console_text.see("end")
        except Exception:
            pass

    # --- GITHUB SYNC LOGIC ---
    def start_check_github_version(self):
        repo = self.entry_github_repo.get().strip()
        if not repo:
            messagebox.showwarning("Внимание", "Укажите репозиторий GitHub (например: username/minecraft-pack)")
            return

        self.btn_check_github.configure(state="disabled")
        self.lbl_github_status.configure(text=f"Загрузка манифеста из {repo}...")
        self.github_progress.set(0.1)

        def worker():
            ok, manifest, url = fetch_manifest_from_github(repo, branch=self.cfg.get("github_branch", "main"))
            if not ok:
                self.after(0, lambda: (
                    self.lbl_github_status.configure(text=f"Ошибка: {manifest}"),
                    self.btn_check_github.configure(state="normal"),
                    messagebox.showerror("GitHub Ошибка", f"Не удалось загрузить манифест с GitHub:\n{manifest}\n\nURL: {url}")
                ))
                return

            self.after(0, lambda: self.lbl_github_status.configure(text="Сравнение файлов с локальной сборкой..."))
            diff = compare_manifest_with_local(manifest, progress_callback=lambda p, t: self.after(0, lambda: (self.github_progress.set(p), self.lbl_github_status.configure(text=t))))
            self.after(0, lambda: self._on_github_diff_ready(diff, repo))

        threading.Thread(target=worker, daemon=True).start()

    def _on_github_diff_ready(self, diff, repo):
        self.github_diff = diff
        self.btn_check_github.configure(state="normal")

        to_dl = diff["to_download"]
        to_del = diff["to_delete"]
        up_to_date = diff["up_to_date_count"]
        total_mb = diff["total_download_bytes"] / (1024 * 1024)

        # Clear diff frame
        for w in self.github_diff_frame.winfo_children():
            w.destroy()

        if not to_dl and not to_del:
            self.lbl_github_status.configure(text=f"✓ Сборка полностью актуальна! Все {up_to_date} файлов совпадают с GitHub.")
            self.btn_sync_github.configure(state="disabled")
            lbl_ok = ctk.CTkLabel(self.github_diff_frame, text="✓ Все моды, конфиги и шейдеры совпадают с версией на GitHub.", font=ctk.CTkFont(size=13, weight="bold"), text_color="#00e676")
            lbl_ok.pack(pady=20)
            return

        self.lbl_github_status.configure(
            text=f"Найдено отличий: нужно скачать {len(to_dl)} файлов ({total_mb:.1f} МБ), удалить устаревших: {len(to_del)}."
        )
        self.btn_sync_github.configure(state="normal")

        # Display list of diffs
        ctk.CTkLabel(
            self.github_diff_frame, 
            text=f"Файлы для загрузки и обновления ({len(to_dl)} шт.):", 
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COLOR_ACCENT
        ).pack(anchor="w", padx=10, pady=(6, 2))

        for item in to_dl:
            row = ctk.CTkFrame(self.github_diff_frame, height=28, fg_color=COLOR_INPUT_BG)
            row.pack(fill="x", padx=4, pady=2)
            sz_mb = item["size"] / (1024 * 1024)
            sz_txt = f"{sz_mb:.2f} МБ" if sz_mb >= 0.1 else f"{item['size']//1024} КБ"
            ctk.CTkLabel(row, text=f"• {item['rel_path']}", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_PRIMARY).pack(side="left", padx=8)
            ctk.CTkLabel(row, text=f"[{item['reason']}] ({sz_txt})", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_SECONDARY).pack(side="right", padx=8)

        if to_del:
            ctk.CTkLabel(
                self.github_diff_frame, 
                text=f"Устаревшие файлы для удаления ({len(to_del)} шт.):", 
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color="#e74c3c"
            ).pack(anchor="w", padx=10, pady=(10, 2))
            for del_f in to_del:
                row = ctk.CTkFrame(self.github_diff_frame, height=26, fg_color=COLOR_INPUT_BG)
                row.pack(fill="x", padx=4, pady=2)
                ctk.CTkLabel(row, text=f"✕ {del_f}", font=ctk.CTkFont(size=11), text_color="#e74c3c").pack(side="left", padx=8)

    def start_sync_github_diff(self):
        if not self.github_diff:
            return
        repo = self.entry_github_repo.get().strip()
        self.btn_sync_github.configure(state="disabled")
        self.btn_check_github.configure(state="disabled")

        def worker():
            ok, msg = sync_differences(
                self.github_diff,
                repo,
                branch=self.cfg.get("github_branch", "main"),
                progress_callback=lambda p, t: self.after(0, lambda: (self.github_progress.set(p), self.lbl_github_status.configure(text=t)))
            )
            if ok:
                self.after(0, lambda: (
                    messagebox.showinfo("GitHub Синхронизация", msg),
                    self.start_check_github_version(),
                    self.refresh_all_data()
                ))
            else:
                self.after(0, lambda: (
                    self.btn_sync_github.configure(state="normal"),
                    self.btn_check_github.configure(state="normal"),
                    messagebox.showerror("Ошибка синхронизации", msg)
                ))

        threading.Thread(target=worker, daemon=True).start()

    def action_push_to_github(self):
        remote = self.entry_github_repo.get().strip()
        if remote and not remote.startswith("http") and not remote.startswith("git@"):
            remote = f"https://github.com/{remote}.git"

        confirm = messagebox.askyesno(
            "Публикация на GitHub", 
            f"Собрать манифест и отправить изменения сборки на GitHub?\nРепозиторий: {remote or 'по умолчанию'}\n\nБудут отправлены только моды, конфиги, шейдеры и настройки (без мусора)."
        )
        if not confirm:
            return

        self.tabview.set("📋 Консоль")
        self.log(f"[GITHUB PUSH] Начата публикация на: {remote}...")

        def worker():
            try:
                export_and_push(remote_url=remote)
                self.after(0, lambda: messagebox.showinfo("Успех", "Манифест и сборка успешно подготовлены и отправлены на GitHub!"))
            except Exception as e:
                self.after(0, lambda err=e: messagebox.showerror("Ошибка", f"Ошибка публикации: {err}"))

        threading.Thread(target=worker, daemon=True).start()

    # --- LAUNCHER SELF-UPDATE LOGIC ---
    def start_check_launcher_update(self):
        repo = self.entry_github_repo.get().strip() if hasattr(self, "entry_github_repo") else "Tideathan/Minecraft"
        if not repo:
            repo = "Tideathan/Minecraft"
        
        self.btn_check_launcher_update.configure(state="disabled")
        self.lbl_launcher_update_status.configure(text=f"Проверка обновлений лаунчера на GitHub ({repo})...")
        self.launcher_update_progress.set(0.2)

        def worker():
            ok, result = check_launcher_update(repo_slug=repo, branch="launcher")
            if not ok:
                self.after(0, lambda: (
                    self.lbl_launcher_update_status.configure(text=f"Ошибка: {result}"),
                    self.launcher_update_progress.set(0),
                    self.btn_check_launcher_update.configure(state="normal"),
                    messagebox.showerror("Ошибка проверки обновления", f"Не удалось проверить обновления лаунчера:\n{result}")
                ))
                return

            if not result["has_update"]:
                self.after(0, lambda: (
                    self.lbl_launcher_update_status.configure(text=f"✓ У вас установлена актуальная версия лаунчера (v{result['current_version']})!"),
                    self.launcher_update_progress.set(1.0),
                    self.btn_check_launcher_update.configure(state="normal"),
                    messagebox.showinfo("Обновление лаунчера", f"У вас установлена самая актуальная версия лаунчера (v{result['current_version']}). Обновление не требуется.")
                ))
            else:
                self.after(0, lambda: (
                    self.lbl_launcher_update_status.configure(text=f"⚡ Доступно обновление: v{result['remote_version']} (текущая: v{result['current_version']})"),
                    self.launcher_update_progress.set(0.5),
                    self.btn_check_launcher_update.configure(state="normal"),
                    self._prompt_launcher_update(result, repo)
                ))

        threading.Thread(target=worker, daemon=True).start()

    def _prompt_launcher_update(self, update_info, repo):
        msg = (
            f"Доступна новая версия лаунчера: v{update_info['remote_version']}!\n\n"
            f"Текущая версия: v{update_info['current_version']}\n"
            f"Дата релиза: {update_info.get('release_date', 'Не указана')}\n\n"
            f"Список изменений:\n{update_info.get('changelog', 'Улучшения стабильности.')}\n\n"
            f"Обновить лаунчер прямо сейчас?"
        )
        ans = messagebox.askyesno("Найдено обновление лаунчера", msg)
        if ans:
            self.start_apply_launcher_update(update_info, repo)

    def start_apply_launcher_update(self, update_info, repo):
        self.btn_check_launcher_update.configure(state="disabled")
        self.lbl_launcher_update_status.configure(text="Загрузка обновления лаунчера...")
        self.launcher_update_progress.set(0.1)

        def worker():
            ok, msg = apply_launcher_update(
                update_info,
                repo_slug=repo,
                branch="launcher",
                progress_callback=lambda p, t: self.after(0, lambda: (
                    self.launcher_update_progress.set(p),
                    self.lbl_launcher_update_status.configure(text=t)
                ))
            )
            if ok:
                def on_done():
                    messagebox.showinfo("Обновление завершено", "Лаунчер успешно обновлен! Нажмите OK для перезапуска.")
                    restart_launcher()
                self.after(0, on_done)
            else:
                self.after(0, lambda: (
                    self.btn_check_launcher_update.configure(state="normal"),
                    self.lbl_launcher_update_status.configure(text=f"Ошибка обновления: {msg}"),
                    messagebox.showerror("Ошибка обновления", msg)
                ))

        threading.Thread(target=worker, daemon=True).start()

    # --- DATA REFRESH ---
    def refresh_all_data(self):
        # Versions
        self.installed_versions = get_installed_versions()
        v_labels = [v["label"] for v in self.installed_versions]
        self.combo_versions.configure(values=v_labels)
        
        curr_vid = self.cfg.get("version", "neoforge-21.1.250")
        matched = next((v["label"] for v in self.installed_versions if v["id"] == curr_vid), None)
        if matched:
            self.combo_versions.set(matched)
        elif v_labels:
            self.combo_versions.set(v_labels[0])

        # Java
        try:
            self.on_javas_found(find_all_javas())
        except Exception as e:
            print(f"Error detecting Javas: {e}")

        # Mods count
        mods = get_installed_mods_info()
        self.lbl_mods_count.configure(text=f"Установлено модов: {len(mods)}")
        self._populate_mods_list(mods)

    def on_javas_found(self, javas):
        self.detected_javas = javas
        self.java_map = {}
        labels = []

        cfg_java = self.cfg.get("java_path", "")
        selected_label = None

        for j in javas:
            tag = "✓" if j["compatible"] else "✕"
            loc = " [Встроенная]" if "runtime" in j["path"] else ""
            bitness = "64-bit" if j["is_64bit"] else "32-bit"
            base_label = f"{tag} {j['vendor']} {j['version']} ({bitness}){loc}"
            
            label = base_label
            counter = 2
            while label in self.java_map:
                label = f"{base_label} #{counter}"
                counter += 1

            labels.append(label)
            self.java_map[label] = j["path"]

            if cfg_java and os.path.normpath(cfg_java) == os.path.normpath(j["path"]):
                selected_label = label

        if not labels:
            labels = ["✕ Java не обнаружена"]
            self.java_map[labels[0]] = DEFAULT_JAVA

        self.combo_java.configure(values=labels)
        if selected_label:
            self.combo_java.set(selected_label)
            self.lbl_java_status.configure(text=f"Активна: {selected_label}")
        elif labels:
            compat = next((l for l in labels if l.startswith("✓")), labels[0])
            self.combo_java.set(compat)
            self.cfg["java_path"] = self.java_map[compat]
            self.lbl_java_status.configure(text=f"Активна: {compat}")
            save_config(self.cfg)

    def _populate_mods_list(self, mods):
        for widget in self.mods_scroll.winfo_children():
            widget.destroy()

        for m in mods:
            row = ctk.CTkFrame(self.mods_scroll, height=36, fg_color="transparent")
            row.pack(fill="x", padx=4, pady=2)

            lbl_name = ctk.CTkLabel(row, text=f"• {m['display_name']}", font=ctk.CTkFont(size=12, weight="bold"), text_color=COLOR_TEXT_PRIMARY)
            lbl_name.pack(side="left", padx=6)

            lbl_fn = ctk.CTkLabel(row, text=f"({m['filename']}, {m['size_mb']} МБ)", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_SECONDARY)
            lbl_fn.pack(side="left", padx=4)

            lbl_st = ctk.CTkLabel(row, text=m["status"], font=ctk.CTkFont(size=11), text_color=COLOR_ACCENT)
            lbl_st.pack(side="right", padx=8)

    # --- SKIN PREVIEW ---
    def update_skin_preview_ui(self):
        if os.path.exists(SKIN_PREVIEW_PATH):
            try:
                img = Image.open(SKIN_PREVIEW_PATH)
                ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(96, 192))
                self.skin_preview_lbl.configure(image=ctk_img, text="")
                return
            except Exception:
                pass
        self.skin_preview_lbl.configure(image=None, text="[Нет скина]")

    def select_and_apply_skin(self):
        f = filedialog.askopenfilename(
            title="Выберите файл скина",
            filetypes=[("PNG Скин", "*.png")]
        )
        if not f:
            return
        ok, msg = apply_skin_to_game(f)
        if ok:
            self.cfg["skin_path"] = f
            save_config(self.cfg)
            self.update_skin_preview_ui()
            messagebox.showinfo("Скин", "Скин успешно применен в игре!")
        else:
            messagebox.showerror("Ошибка скина", msg)

    # --- MOD UPDATER ACTIONS ---
    def start_check_updates(self):
        self.btn_check_updates.configure(state="disabled")
        self.lbl_mods_status.configure(text="Поиск обновлений модов в Modrinth API...")
        self.mods_progress.set(0.1)

        def worker():
            updates = check_mod_updates_async(
                progress_callback=lambda p, t: self.after(0, lambda: self._update_mods_progress(p, t))
            )
            self.after(0, lambda: self._on_updates_checked(updates))

        threading.Thread(target=worker, daemon=True).start()

    def _update_mods_progress(self, p, t):
        self.mods_progress.set(p)
        self.lbl_mods_status.configure(text=t)

    def _on_updates_checked(self, updates):
        self.btn_check_updates.configure(state="normal")
        self.updates_cache = updates
        if not updates:
            self.lbl_mods_status.configure(text="✓ Все моды имеют актуальные версии для NeoForge 1.21.1!")
            self.btn_update_all.configure(state="disabled")
            return

        self.lbl_mods_status.configure(text=f"Доступно обновлений: {len(updates)}")
        self.btn_update_all.configure(state="normal")

        for widget in self.mods_scroll.winfo_children():
            widget.destroy()

        for u in updates:
            row = ctk.CTkFrame(self.mods_scroll, corner_radius=8, fg_color=COLOR_INPUT_BG)
            row.pack(fill="x", padx=4, pady=4)

            lbl = ctk.CTkLabel(
                row, 
                text=f"⬆ {u['display_name']}: {u['current_version']} ➔ {u['latest_version']}",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=COLOR_ACCENT
            )
            lbl.pack(side="left", padx=10, pady=8)

            btn = ctk.CTkButton(
                row,
                text="Обновить",
                width=80,
                height=28,
                font=ctk.CTkFont(size=11, weight="bold"),
                fg_color=COLOR_ACCENT,
                text_color="#000000" if self.current_theme_key == "night" else "#ffffff",
                command=lambda item=u: self.install_single_mod_update(item)
            )
            btn.pack(side="right", padx=10, pady=8)

    def install_single_mod_update(self, item):
        def worker():
            ok, msg = install_mod_update(item, progress_callback=lambda p, t: self.after(0, lambda: self._update_mods_progress(p, t)))
            if ok:
                self.after(0, lambda: messagebox.showinfo("Обновление", f"{item['display_name']} успешно обновлен!"))
                self.after(0, self.refresh_all_data)
            else:
                self.after(0, lambda: messagebox.showerror("Ошибка", msg))
        threading.Thread(target=worker, daemon=True).start()

    def start_update_all_mods(self):
        if not self.updates_cache:
            return
        self.btn_update_all.configure(state="disabled")

        def worker():
            total = len(self.updates_cache)
            for i, u in enumerate(self.updates_cache):
                self.after(0, lambda idx=i, item=u: self._update_mods_progress((idx+1)/total, f"Обновление {item['display_name']} ({idx+1}/{total})..."))
                install_mod_update(u)
            self.after(0, lambda: messagebox.showinfo("Готово", f"Успешно обновлено {total} модов!"))
            self.after(0, self.refresh_all_data)

        threading.Thread(target=worker, daemon=True).start()

    # --- FRIENDS EXPORT ---
    def start_export_pack(self):
        save_path = filedialog.asksaveasfilename(
            title="Сохранить архив сборки",
            defaultextension=".zip",
            filetypes=[("ZIP Архив", "*.zip")],
            initialfile="Minecraft_NeoForge_1.21.1_Pack.zip"
        )
        if not save_path:
            return

        def worker():
            self.log(f"[EXPORT] Начат экспорт сборки в: {save_path}")
            ok, msg = export_build_pack(save_path)
            if ok:
                self.after(0, lambda: messagebox.showinfo("Экспорт завершен", f"{msg}\nАрхив готов к отправке друзьям!"))
            else:
                self.after(0, lambda: messagebox.showerror("Ошибка экспорта", msg))

        threading.Thread(target=worker, daemon=True).start()

    # --- VERSION & NEOFORGE MODAL ---
    def on_version_selected(self, choice):
        matched = next((v["id"] for v in self.installed_versions if v["label"] == choice), None)
        if matched:
            self.cfg["version"] = matched
            self.lbl_play_version.configure(text=f"Сборка: {matched}")
            save_config(self.cfg)

    def open_neoforge_installer_modal(self):
        modal = ctk.CTkToplevel(self)
        modal.title("Установка NeoForge")
        modal.geometry("480x280")
        modal.resizable(False, False)
        modal.grab_set()

        ctk.CTkLabel(modal, text="УСТАНОВКА NEOFORGE", font=ctk.CTkFont(size=14, weight="bold"), text_color=COLOR_ACCENT).pack(anchor="w", padx=20, pady=(16, 4))
        ctk.CTkLabel(modal, text="Выберите версию NeoForge для Minecraft 1.21.1:", font=ctk.CTkFont(size=12), text_color=COLOR_TEXT_SECONDARY).pack(anchor="w", padx=20, pady=(0, 8))

        combo_nf = ctk.CTkComboBox(modal, width=320, height=36, font=ctk.CTkFont(size=13))
        combo_nf.set("Загрузка версий...")
        combo_nf.pack(padx=20, pady=(0, 10))

        prog = ctk.CTkProgressBar(modal, width=440)
        prog.set(0)
        prog.pack(padx=20, pady=(0, 6))

        lbl_st = ctk.CTkLabel(modal, text="Получение версий с Maven...", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_SECONDARY)
        lbl_st.pack(padx=20, pady=(0, 12))

        def load_versions():
            vers = fetch_available_neoforge_versions("21.1")
            modal.after(0, lambda: (combo_nf.configure(values=vers), combo_nf.set(vers[0] if vers else "21.1.250"), lbl_st.configure(text="Выберите версию и нажмите Установить")))
        threading.Thread(target=load_versions, daemon=True).start()

        def do_install():
            ver = combo_nf.get().strip()
            java_exe = self.cfg.get("java_path", DEFAULT_JAVA)
            lbl_st.configure(text=f"Начало установки {ver}...")
            btn_inst.configure(state="disabled")

            def inst_worker():
                ok, msg = install_neoforge_version(ver, java_exe, progress_callback=lambda p, t: modal.after(0, lambda: (prog.set(p), lbl_st.configure(text=t))))
                if ok:
                    modal.after(0, lambda: (messagebox.showinfo("Успех", msg), modal.destroy(), self.refresh_all_data()))
                else:
                    modal.after(0, lambda: (messagebox.showerror("Ошибка", msg), btn_inst.configure(state="normal")))

            threading.Thread(target=inst_worker, daemon=True).start()

        btn_inst = ctk.CTkButton(
            modal,
            text="⚡ Установить версию",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=COLOR_ACCENT,
            hover_color=COLOR_ACCENT_HOVER,
            text_color="#000000" if self.current_theme_key == "night" else "#ffffff",
            command=do_install
        )
        btn_inst.pack(pady=4)

    # --- JAVA ACTIONS ---
    def on_java_selected(self, choice):
        path = self.java_map.get(choice)
        if path:
            self.cfg["java_path"] = path
            self.lbl_java_status.configure(text=f"Выбрана: {choice}")
            save_config(self.cfg)

    def download_java_action(self):
        self.lbl_java_status.configure(text="Скачивание Adoptium Temurin OpenJDK 21...")
        self.java_progress.set(0.1)

        def worker():
            ok, msg, path = download_and_extract_java_21(
                progress_callback=lambda p, t: self.after(0, lambda: (self.java_progress.set(p), self.lbl_java_status.configure(text=t)))
            )
            if ok:
                self.cfg["java_path"] = path
                save_config(self.cfg)
                self.after(0, lambda: messagebox.showinfo("Java", "Java 21 успешно установлена и активирована!"))
                self.after(0, self.refresh_all_data)
            else:
                self.after(0, lambda: messagebox.showerror("Ошибка", msg))

        threading.Thread(target=worker, daemon=True).start()

    # --- GC & CONFIG ---
    def on_gc_selected(self, choice):
        if "ZGC" in choice:
            self.cfg["gc_type"] = "ZGC"
        elif "G1GC" in choice:
            self.cfg["gc_type"] = "G1GC"
        elif "Shenandoah" in choice:
            self.cfg["gc_type"] = "Shenandoah"
        else:
            self.cfg["gc_type"] = "Custom"
        save_config(self.cfg)

    def on_ram_slider_change(self, val):
        val = int(val)
        snapped = round(val / RAM_STEP_MB) * RAM_STEP_MB
        self.cfg["ram_mb"] = snapped
        self.update_ram_label(snapped)
        save_config(self.cfg)

    def set_ram_preset(self, mb):
        self.ram_slider.set(mb)
        self.cfg["ram_mb"] = mb
        self.update_ram_label(mb)
        save_config(self.cfg)

    def update_ram_label(self, mb):
        gb = mb / 1024.0
        self.lbl_ram_val.configure(text=f"{mb} МБ  ({gb:.2f} ГБ)")

    def on_config_change(self):
        self.cfg["username"] = self.entry_username.get().strip() or "Adolf"
        self.cfg["custom_jvm_args"] = self.entry_jvm_args.get().strip()
        if hasattr(self, "entry_github_repo"):
            self.cfg["github_repo"] = self.entry_github_repo.get().strip()
        try:
            self.cfg["width"] = int(self.entry_w.get().strip())
            self.cfg["height"] = int(self.entry_h.get().strip())
        except Exception:
            pass
        save_config(self.cfg)

    # --- LAUNCH GAME ---
    def launch_game(self):
        self.on_config_change()
        username = self.cfg["username"]
        version_id = self.cfg["version"]
        ram_mb = self.cfg["ram_mb"]
        java_path = self.cfg.get("java_path", DEFAULT_JAVA)
        width = self.cfg.get("width", 1280)
        height = self.cfg.get("height", 720)
        gc_type = self.cfg.get("gc_type", "ZGC")
        custom_jvm_args = self.cfg.get("custom_jvm_args", "")

        self.btn_play.configure(state="disabled", text="⏳ ЗАПУСК...")
        self.lbl_status.configure(text="Подготовка аргументов запуска...")
        self.tabview.set("📋 Консоль")

        def worker():
            try:
                self.log(f"[LAUNCH] Запуск {version_id} для игрока '{username}'...")
                self.log(f"[LAUNCH] Выделено памяти: {ram_mb} МБ ({ram_mb/1024:.2f} ГБ)")
                self.log(f"[LAUNCH] Garbage Collector: {gc_type}")
                self.log(f"[LAUNCH] Java runtime: {java_path}")

                cmd = build_launch_command(
                    username=username,
                    version_id=version_id,
                    ram_mb=ram_mb,
                    java_path=java_path,
                    width=width,
                    height=height,
                    gc_type=gc_type,
                    custom_jvm_args=custom_jvm_args
                )

                self.log(f"[CMD] {cmd[0]} {cmd[1]} ... {cmd[-1]}\n")

                self.game_process = subprocess.Popen(
                    cmd,
                    cwd=MC_DIR,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    creationflags=0
                )

                self.after(0, lambda: (
                    self.lbl_status.configure(text="Игра запущена и работает!"),
                    self.btn_play.configure(state="normal", text="⏹ ОСТАНОВИТЬ")
                ))

                for line in iter(self.game_process.stdout.readline, ""):
                    if not line:
                        break
                    self.after(0, lambda l=line.strip(): self.log(l))

                self.game_process.stdout.close()
                code = self.game_process.wait()

                self.after(0, lambda: (
                    self.log(f"\n[EXIT] Игра завершена с кодом: {code}"),
                    self.lbl_status.configure(text=f"Игра завершена (код {code})"),
                    self.btn_play.configure(state="normal", text="▶   ИГРАТЬ")
                ))
            except Exception as e:
                self.after(0, lambda err=e: (
                    self.log(f"\n[ERROR] Ошибка запуска: {err}"),
                    self.lbl_status.configure(text=f"Ошибка: {err}"),
                    self.btn_play.configure(state="normal", text="▶   ИГРАТЬ"),
                    messagebox.showerror("Ошибка запуска", str(err))
                ))

        threading.Thread(target=worker, daemon=True).start()

    def on_close(self):
        save_config(self.cfg)
        self.destroy()

if __name__ == "__main__":
    app = ModernLauncherApp()
    app.mainloop()
