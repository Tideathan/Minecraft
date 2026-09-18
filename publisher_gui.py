import os
import sys

# Windows Taskbar and Start Menu integration
APP_USER_MODEL_ID = "tideathan.minecraft.publisher.v1"
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    except Exception:
        pass

import json
import shutil
import threading
import subprocess
from datetime import datetime
import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk

from push_to_github import gather_build_files, build_manifest, export_and_push
from publish_launcher_update import publish_launcher
from launcher_updater import CURRENT_LAUNCHER_VERSION

_CURR_DIR = os.path.dirname(os.path.abspath(__file__))
if os.path.basename(_CURR_DIR).lower() == "launcher":
    LAUNCHER_DIR = _CURR_DIR
    MC_DIR = os.path.normpath(os.path.join(_CURR_DIR, ".."))
else:
    LAUNCHER_DIR = os.path.normpath(os.path.expandvars(r"%APPDATA%\.minecraft\launcher"))
    MC_DIR = os.path.normpath(os.path.expandvars(r"%APPDATA%\.minecraft"))

LAUNCHER_REPO_DIR = os.path.join(LAUNCHER_DIR, "github_launcher_repo")

COLOR_BG = "#0d1310"
COLOR_HEADER = "#131c16"
COLOR_CARD = "#18231c"
COLOR_CARD_BORDER = "#25362b"
COLOR_ACCENT = "#2ecc71"
COLOR_ACCENT_HOVER = "#27ae60"
COLOR_BTN_SEC = "#223026"
COLOR_BTN_SEC_HOVER = "#2c3d31"
COLOR_TEXT_PRIMARY = "#f0fdf4"
COLOR_TEXT_SECONDARY = "#8fa394"

class PublisherApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Minecraft Build & Launcher Publisher")
        self.geometry("780x640")
        self.minsize(700, 550)

        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("green")

        # Icons
        icon_path = os.path.join(LAUNCHER_DIR, "minecraft_wolf.ico")
        if not os.path.exists(icon_path):
            icon_path = os.path.join(MC_DIR, "minecraft_wolf.ico")
        if not os.path.exists(icon_path):
            icon_path = os.path.join(LAUNCHER_DIR, "launcher_icon.ico")
        if not os.path.exists(icon_path):
            icon_path = os.path.join(MC_DIR, "launcher_icon.ico")

        if os.path.exists(icon_path):
            try:
                self.iconbitmap(icon_path)
                self.wm_iconbitmap(icon_path)
            except Exception:
                pass

        self.is_busy = False
        self.setup_ui()
        self.refresh_stats_async()

    def setup_ui(self):
        # 1. Header
        header = ctk.CTkFrame(self, height=65, corner_radius=0, fg_color=COLOR_HEADER)
        header.pack(fill="x")

        title_box = ctk.CTkFrame(header, fg_color="transparent")
        title_box.pack(side="left", padx=20, pady=12)

        ctk.CTkLabel(
            title_box,
            text="🚀 Minecraft Publisher",
            font=ctk.CTkFont(size=19, weight="bold"),
            text_color=COLOR_ACCENT
        ).pack(anchor="w")

        ctk.CTkLabel(
            title_box,
            text="Публикация обновлений сборки и лаунчера на GitHub (Tideathan/Minecraft)",
            font=ctk.CTkFont(size=11),
            text_color=COLOR_TEXT_SECONDARY
        ).pack(anchor="w")

        # 2. Tabs
        self.tabview = ctk.CTkTabview(self, corner_radius=10, fg_color=COLOR_BG)
        self.tabview.pack(fill="both", expand=True, padx=16, pady=8)

        self.tab_build = self.tabview.add("📦 Сборка игры (ветка main)")
        self.tab_launcher = self.tabview.add("🐺 Лаунчер (ветка launcher)")

        self.setup_tab_build()
        self.setup_tab_launcher()

        # 3. Log Console at Bottom
        console_frame = ctk.CTkFrame(self, corner_radius=10, fg_color=COLOR_CARD, border_width=1, border_color=COLOR_CARD_BORDER)
        console_frame.pack(fill="x", padx=16, pady=(0, 12))

        console_header = ctk.CTkFrame(console_frame, fg_color="transparent", height=28)
        console_header.pack(fill="x", padx=12, pady=(8, 4))

        ctk.CTkLabel(
            console_header,
            text="📋 ЖУРНАЛ ОПЕРАЦИЙ",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=COLOR_ACCENT
        ).pack(side="left")

        btn_clear = ctk.CTkButton(
            console_header,
            text="Очистить",
            width=70,
            height=22,
            font=ctk.CTkFont(size=11),
            fg_color=COLOR_BTN_SEC,
            hover_color=COLOR_BTN_SEC_HOVER,
            command=self.clear_log
        )
        btn_clear.pack(side="right")

        self.log_text = ctk.CTkTextbox(console_frame, height=130, font=ctk.CTkFont(family="Consolas", size=11), fg_color="#080c09", text_color="#a3e635")
        self.log_text.pack(fill="x", padx=12, pady=(0, 10))

    # --- TAB 1: GAME BUILD PUSH ---
    def setup_tab_build(self):
        tab = self.tab_build

        # Stats Card
        card_stats = ctk.CTkFrame(tab, corner_radius=10, fg_color=COLOR_CARD, border_width=1, border_color=COLOR_CARD_BORDER)
        card_stats.pack(fill="x", pady=(4, 8))

        ctk.CTkLabel(card_stats, text="СОСТОЯНИЕ ЛОКАЛЬНОЙ СБОРКИ", font=ctk.CTkFont(size=12, weight="bold"), text_color=COLOR_ACCENT).pack(anchor="w", padx=16, pady=(10, 4))

        self.lbl_stats = ctk.CTkLabel(
            card_stats,
            text="Сканирование файлов сборки...",
            font=ctk.CTkFont(size=12),
            text_color=COLOR_TEXT_PRIMARY,
            justify="left"
        )
        self.lbl_stats.pack(anchor="w", padx=16, pady=(0, 10))

        # Commit & Settings Card
        card_action = ctk.CTkFrame(tab, corner_radius=10, fg_color=COLOR_CARD, border_width=1, border_color=COLOR_CARD_BORDER)
        card_action.pack(fill="x", pady=4)

        ctk.CTkLabel(card_action, text="ПАРАМЕТРЫ ПУБЛИКАЦИИ НА GITHUB", font=ctk.CTkFont(size=12, weight="bold"), text_color=COLOR_ACCENT).pack(anchor="w", padx=16, pady=(10, 4))

        ctk.CTkLabel(card_action, text="Сообщение коммита (что изменилось в сборке):", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_SECONDARY).pack(anchor="w", padx=16, pady=(2, 2))
        
        self.entry_build_commit = ctk.CTkEntry(card_action, height=34, font=ctk.CTkFont(size=12))
        default_msg = f"Update build: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        self.entry_build_commit.insert(0, default_msg)
        self.entry_build_commit.pack(fill="x", padx=16, pady=(0, 10))

        # Progress
        self.progress_build = ctk.CTkProgressBar(card_action)
        self.progress_build.set(0)
        self.progress_build.pack(fill="x", padx=16, pady=(0, 6))

        self.lbl_build_status = ctk.CTkLabel(card_action, text="Готов к сборке манифеста и отправке в ветку 'main'.", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_SECONDARY)
        self.lbl_build_status.pack(anchor="w", padx=16, pady=(0, 10))

        # Buttons Row
        row_btns = ctk.CTkFrame(card_action, fg_color="transparent")
        row_btns.pack(fill="x", padx=16, pady=(0, 12))

        self.btn_rescan_build = ctk.CTkButton(
            row_btns,
            text="🔄 Пересканировать",
            width=140,
            height=34,
            fg_color=COLOR_BTN_SEC,
            hover_color=COLOR_BTN_SEC_HOVER,
            command=self.refresh_stats_async
        )
        self.btn_rescan_build.pack(side="left", padx=(0, 8))

        self.btn_push_build = ctk.CTkButton(
            row_btns,
            text="🚀 Опубликовать сборку на GitHub",
            font=ctk.CTkFont(size=13, weight="bold"),
            height=34,
            fg_color=COLOR_ACCENT,
            hover_color=COLOR_ACCENT_HOVER,
            text_color="#000000",
            command=self.start_push_build
        )
        self.btn_push_build.pack(side="left", fill="x", expand=True)

    # --- TAB 2: LAUNCHER UPDATE PUSH ---
    def setup_tab_launcher(self):
        tab = self.tab_launcher

        card_info = ctk.CTkFrame(tab, corner_radius=10, fg_color=COLOR_CARD, border_width=1, border_color=COLOR_CARD_BORDER)
        card_info.pack(fill="x", pady=(4, 8))

        ctk.CTkLabel(card_info, text="ПУБЛИКАЦИЯ ВЕРСИИ ЛАУНЧЕРА (ВЕТКА 'LAUNCHER')", font=ctk.CTkFont(size=12, weight="bold"), text_color=COLOR_ACCENT).pack(anchor="w", padx=16, pady=(10, 4))

        ctk.CTkLabel(
            card_info,
            text=f"Текущая установленная версия: v{CURRENT_LAUNCHER_VERSION}\n"
                 f"При публикации скрипт обновит манифест launcher_version.json и запушит файлы в ветку 'launcher'.\n"
                 f"Друзья увидят обновление лаунчера в 1 клик по нажатию кнопки «Проверить обновление».",
            font=ctk.CTkFont(size=11),
            text_color=COLOR_TEXT_PRIMARY,
            justify="left"
        ).pack(anchor="w", padx=16, pady=(0, 10))

        # Version & Changelog Card
        card_release = ctk.CTkFrame(tab, corner_radius=10, fg_color=COLOR_CARD, border_width=1, border_color=COLOR_CARD_BORDER)
        card_release.pack(fill="x", pady=4)

        row_ver = ctk.CTkFrame(card_release, fg_color="transparent")
        row_ver.pack(fill="x", padx=16, pady=(10, 4))

        ctk.CTkLabel(row_ver, text="Новый номер версии:", font=ctk.CTkFont(size=12, weight="bold"), text_color=COLOR_TEXT_SECONDARY).pack(side="left", padx=(0, 8))
        self.entry_launcher_ver = ctk.CTkEntry(row_ver, width=120, height=32, font=ctk.CTkFont(size=12, weight="bold"))
        # Auto-suggest next patch version
        try:
            parts = [int(x) for x in CURRENT_LAUNCHER_VERSION.split(".")]
            parts[-1] += 1
            next_ver = ".".join(str(x) for x in parts)
        except Exception:
            next_ver = "1.0.1"
        self.entry_launcher_ver.insert(0, next_ver)
        self.entry_launcher_ver.pack(side="left")

        ctk.CTkLabel(card_release, text="Описание изменений (Changelog для друзей):", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_SECONDARY).pack(anchor="w", padx=16, pady=(8, 2))
        self.entry_changelog = ctk.CTkEntry(card_release, height=34, font=ctk.CTkFont(size=12))
        self.entry_changelog.insert(0, "Улучшения производительности и исправления интерфейса.")
        self.entry_changelog.pack(fill="x", padx=16, pady=(0, 10))

        self.chk_rebuild_setup = ctk.CTkCheckBox(
            card_release,
            text="Собрать свежий Minecraft_Launcher_Setup.exe перед публикацией",
            font=ctk.CTkFont(size=12)
        )
        self.chk_rebuild_setup.pack(anchor="w", padx=16, pady=(0, 10))

        self.progress_launcher = ctk.CTkProgressBar(card_release)
        self.progress_launcher.set(0)
        self.progress_launcher.pack(fill="x", padx=16, pady=(0, 6))

        self.lbl_launcher_status = ctk.CTkLabel(card_release, text="Готов к публикации версии лаунчера в ветку 'launcher'.", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_SECONDARY)
        self.lbl_launcher_status.pack(anchor="w", padx=16, pady=(0, 10))

        self.btn_push_launcher = ctk.CTkButton(
            card_release,
            text="🚀 Опубликовать обновление лаунчера",
            font=ctk.CTkFont(size=13, weight="bold"),
            height=34,
            fg_color=COLOR_ACCENT,
            hover_color=COLOR_ACCENT_HOVER,
            text_color="#000000",
            command=self.start_push_launcher
        )
        self.btn_push_launcher.pack(fill="x", padx=16, pady=(0, 12))

    # --- LOGGING HELPER ---
    def log(self, text):
        def _do():
            self.log_text.insert("end", f"{text}\n")
            self.log_text.see("end")
        self.after(0, _do)

    def clear_log(self):
        self.log_text.delete("1.0", "end")

    # --- ACTIONS ---
    def refresh_stats_async(self):
        def worker():
            files_map = gather_build_files()
            mods_count = sum(1 for k in files_map if k.startswith("mods/"))
            configs_count = sum(1 for k in files_map if k.startswith("config/"))
            total_size_mb = sum(os.path.getsize(v) for v in files_map.values()) / (1024 * 1024)

            txt = (
                f"• Всего файлов сборки: {len(files_map)}\n"
                f"• Модов (.jar): {mods_count}\n"
                f"• Конфигураций: {configs_count}\n"
                f"• Шейдеры и ресурспаки: включены\n"
                f"• Общий объем сборки: {total_size_mb:.1f} МБ"
            )
            self.after(0, lambda: self.lbl_stats.configure(text=txt))
        threading.Thread(target=worker, daemon=True).start()

    def start_push_build(self):
        if self.is_busy:
            return
        
        commit_msg = self.entry_build_commit.get().strip()
        if not commit_msg:
            commit_msg = f"Update build: {datetime.now().strftime('%Y-%m-%d %H:%M')}"

        confirm = messagebox.askyesno(
            "Публикация сборки",
            f"Отправить обновления сборки игры на GitHub?\n"
            f"Ветка: main\n"
            f"Коммит: {commit_msg}\n\n"
            f"Будут отправлены только чистые игровые файлы (без миров и логов)."
        )
        if not confirm:
            return

        self.is_busy = True
        self.btn_push_build.configure(state="disabled")
        self.lbl_build_status.configure(text="Вычисление хешей и синхронизация...")
        self.progress_build.set(0.2)
        self.log(f"\n--- [ПУБЛИКАЦИЯ СБОРКИ В MAIN] ---")

        def worker():
            try:
                self.log("Сбор рабочих файлов сборки...")
                files_map = gather_build_files()
                self.after(0, lambda: self.progress_build.set(0.4))
                
                self.log(f"Найдено {len(files_map)} файлов. Построение manifest.json...")
                manifest = build_manifest(files_map)
                self.after(0, lambda: self.progress_build.set(0.6))

                self.log("Синхронизация файлов в репозиторий сборки...")
                export_and_push(commit_message=commit_msg)
                self.after(0, lambda: self.progress_build.set(1.0))

                self.log("✓ Сборка успешно отправлена в ветку main!")
                self.after(0, lambda: (
                    self.lbl_build_status.configure(text="✓ Сборка успешно опубликована на GitHub!"),
                    self.btn_push_build.configure(state="normal"),
                    messagebox.showinfo("Успех", "Сборка игры успешно обновлена на GitHub в ветке main!")
                ))
            except Exception as e:
                self.log(f"✕ Ошибка публикации сборки: {e}")
                self.after(0, lambda err=e: (
                    self.lbl_build_status.configure(text=f"Ошибка: {err}"),
                    self.btn_push_build.configure(state="normal"),
                    messagebox.showerror("Ошибка", f"Не удалось опубликовать сборку:\n{err}")
                ))
            finally:
                self.is_busy = False

        threading.Thread(target=worker, daemon=True).start()

    def start_push_launcher(self):
        if self.is_busy:
            return

        ver = self.entry_launcher_ver.get().strip().lstrip("vV")
        changelog = self.entry_changelog.get().strip()

        if not ver:
            messagebox.showwarning("Внимание", "Укажите номер версии лаунчера (например, 1.0.1)!")
            return

        confirm = messagebox.askyesno(
            "Публикация версии лаунчера",
            f"Выпустить версию лаунчера v{ver} на GitHub?\n"
            f"Ветка: launcher\n"
            f"Описание: {changelog}\n\n"
            f"Ветка main с модами затронута не будет."
        )
        if not confirm:
            return

        self.is_busy = True
        self.btn_push_launcher.configure(state="disabled")
        self.lbl_launcher_status.configure(text=f"Публикация версии v{ver}...")
        self.progress_launcher.set(0.2)
        self.log(f"\n--- [ПУБЛИКАЦИЯ ЛАУНЧЕРА V{ver} В ВЕТКУ LAUNCHER] ---")

        def worker():
            try:
                # 1. Check if need to rebuild installer
                if self.chk_rebuild_setup.get():
                    self.log("Пересборка Minecraft_Launcher_Setup.exe через PyInstaller...")
                    self.after(0, lambda: self.progress_launcher.set(0.4))

                    clean_env = os.environ.copy()
                    clean_env.pop("_MEIPASS2", None)
                    clean_env.pop("_MEIPASS", None)
                    clean_env.pop("PYTHONPATH", None)
                    clean_env.pop("PYTHONHOME", None)

                    py_exe = "python"
                    if getattr(sys, "frozen", False):
                        for cand in [
                            shutil.which("python"),
                            r"C:\Users\user\AppData\Local\Programs\Python\Python312\python.exe",
                            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Python\Python312\python.exe"),
                            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Python\Python311\python.exe")
                        ]:
                            if cand and os.path.exists(cand):
                                py_exe = cand
                                break
                    else:
                        py_exe = sys.executable

                    cmd = [
                        py_exe, "-m", "PyInstaller",
                        "--noconfirm", "--onefile", "--windowed",
                        "--name", "Minecraft_Launcher_Setup",
                        "--icon", "minecraft_wolf.ico",
                        "--collect-all", "customtkinter",
                        "--add-data", "Minecraft_Launcher.exe;.",
                        "--add-data", "launcher.py;.",
                        "--add-data", "launcher_core.py;.",
                        "--add-data", "game_downloader.py;.",
                        "--add-data", "java_manager.py;.",
                        "--add-data", "version_manager.py;.",
                        "--add-data", "mod_updater.py;.",
                        "--add-data", "skin_manager.py;.",
                        "--add-data", "pack_distributor.py;.",
                        "--add-data", "github_sync.py;.",
                        "--add-data", "launcher_updater.py;.",
                        "--add-data", "push_to_github.py;.",
                        "--add-data", "publisher_gui.py;.",
                        "--add-data", "Publisher.bat;.",
                        "--add-data", "Publisher.vbs;.",
                        "--add-data", "Launcher.bat;.",
                        "--add-data", "Launcher.vbs;.",
                        "--add-data", "launcher_icon.ico;.",
                        "--add-data", "launcher_icon.png;.",
                        "--add-data", "minecraft_wolf.ico;.",
                        "installer.py"
                    ]
                    
                    proc = subprocess.Popen(
                        cmd,
                        cwd=LAUNCHER_DIR,
                        env=clean_env,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        bufsize=1,
                        creationflags=0x08000000 if sys.platform == "win32" else 0
                    )
                    for line in iter(proc.stdout.readline, ""):
                        if not line: break
                        l = line.strip()
                        if "Building PKG" in l or "Building EXE" in l or "Build complete" in l:
                            self.after(0, lambda t=l: self.log(f"  [PyInstaller] {t}"))
                    
                    proc.stdout.close()
                    rc = proc.wait()
                    if rc != 0:
                        raise RuntimeError(f"PyInstaller завершился с кодом ошибки {rc}")

                    # Copy to launcher directory and Desktop
                    dist_setup = os.path.join(LAUNCHER_DIR, "dist", "Minecraft_Launcher_Setup.exe")
                    if os.path.exists(dist_setup):
                        local_setup = os.path.join(LAUNCHER_DIR, "Minecraft_Launcher_Setup.exe")
                        desktop_setup = os.path.join(os.path.expanduser("~"), "Desktop", "Minecraft_Launcher_Setup.exe")
                        shutil.copy2(dist_setup, local_setup)
                        shutil.copy2(dist_setup, desktop_setup)
                        # Clean temp folders
                        for j in ["build", "dist"]:
                            jp = os.path.join(LAUNCHER_DIR, j)
                            if os.path.exists(jp):
                                shutil.rmtree(jp, ignore_errors=True)
                        spec = os.path.join(LAUNCHER_DIR, "Minecraft_Launcher_Setup.spec")
                        if os.path.exists(spec):
                            os.remove(spec)
                    self.log("✓ Установщик успешно пересобран!")

                self.after(0, lambda: self.progress_launcher.set(0.7))
                self.log(f"Упаковка файлов и отправка коммита v{ver} на GitHub...")
                publish_launcher(version=ver, changelog=changelog)
                self.after(0, lambda: self.progress_launcher.set(1.0))

                self.log(f"✓ Версия лаунчера v{ver} успешно опубликована!")
                self.after(0, lambda: (
                    self.lbl_launcher_status.configure(text=f"✓ Версия v{ver} успешно опубликована на GitHub!"),
                    self.btn_push_launcher.configure(state="normal"),
                    messagebox.showinfo("Успех", f"Версия лаунчера v{ver} успешно отправлена на GitHub!")
                ))
            except Exception as e:
                self.log(f"✕ Ошибка публикации лаунчера: {e}")
                self.after(0, lambda err=e: (
                    self.lbl_launcher_status.configure(text=f"Ошибка: {err}"),
                    self.btn_push_launcher.configure(state="normal"),
                    messagebox.showerror("Ошибка", f"Не удалось опубликовать лаунчер:\n{err}")
                ))
            finally:
                self.is_busy = False

        threading.Thread(target=worker, daemon=True).start()

if __name__ == "__main__":
    app = PublisherApp()
    app.mainloop()
