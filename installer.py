import os
import sys
import shutil
import subprocess
import tkinter as tk
from tkinter import messagebox, filedialog
import customtkinter as ctk

# Determine source directory (works both in development and inside PyInstaller bundle)
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    BUNDLE_DIR = sys._MEIPASS
else:
    BUNDLE_DIR = os.path.dirname(os.path.abspath(__file__))

DEFAULT_INSTALL_DIR = os.path.normpath(os.path.expandvars(r"%APPDATA%\.minecraft"))

LAUNCHER_FILES = [
    "launcher.py",
    "launcher_core.py",
    "java_manager.py",
    "version_manager.py",
    "mod_updater.py",
    "skin_manager.py",
    "github_sync.py",
    "launcher_updater.py",
    "push_to_github.py",
    "Launcher.bat",
    "Launcher.vbs",
    "launcher_icon.ico",
    "launcher_icon.png",
    "minecraft_wolf.ico"
]

DEFAULT_CONFIG_CONTENT = {
    "username": "Player",
    "version": "neoforge-21.1.250",
    "ram_mb": 8192,
    "width": 1280,
    "height": 720,
    "gc_type": "ZGC",
    "custom_jvm_args": "",
    "theme": "night",
    "skin_path": "",
    "github_repo": "Tideathan/Minecraft",
    "github_branch": "main",
    "cloud_sync_url": ""
}

def create_windows_shortcut(target_path, shortcut_path, working_dir, icon_path="", description=""):
    try:
        import win32com.client
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(shortcut_path)
        shortcut.TargetPath = target_path
        shortcut.WorkingDirectory = working_dir
        if icon_path and os.path.exists(icon_path):
            shortcut.IconLocation = f"{icon_path},0"
        if description:
            shortcut.Description = description
        shortcut.Save()
        return True
    except Exception:
        # Fallback via PowerShell
        ps_cmd = (
            f'$WshShell = New-Object -ComObject WScript.Shell; '
            f'$Shortcut = $WshShell.CreateShortcut("{shortcut_path}"); '
            f'$Shortcut.TargetPath = "{target_path}"; '
            f'$Shortcut.WorkingDirectory = "{working_dir}"; '
        )
        if icon_path and os.path.exists(icon_path):
            ps_cmd += f'$Shortcut.IconLocation = "{icon_path},0"; '
        if description:
            ps_cmd += f'$Shortcut.Description = "{description}"; '
        ps_cmd += '$Shortcut.Save()'
        try:
            subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, check=True)
            return True
        except Exception:
            return False

class InstallerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Установка Minecraft NeoForge Launcher")
        self.geometry("560x420")
        self.resizable(False, False)

        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("green")

        # Window icon
        icon_path = os.path.join(BUNDLE_DIR, "minecraft_wolf.ico")
        if not os.path.exists(icon_path):
            icon_path = os.path.join(BUNDLE_DIR, "launcher_icon.ico")
        if os.path.exists(icon_path):
            try:
                self.iconbitmap(icon_path)
            except Exception:
                pass

        self.install_dir = DEFAULT_INSTALL_DIR

        self.setup_ui()

    def setup_ui(self):
        # Header
        header = ctk.CTkFrame(self, corner_radius=0, fg_color="#18231c", height=70)
        header.pack(fill="x")

        ctk.CTkLabel(
            header,
            text="🐺 Minecraft NeoForge Launcher",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#2ecc71"
        ).pack(anchor="w", padx=20, pady=(12, 2))

        ctk.CTkLabel(
            header,
            text="Мастер установки лаунчера и компонентов сборки",
            font=ctk.CTkFont(size=11),
            text_color="#8fa394"
        ).pack(anchor="w", padx=20, pady=(0, 10))

        # Main content
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=20, pady=16)

        # Path chooser
        ctk.CTkLabel(
            content,
            text="Папка для установки игры и лаунчера:",
            font=ctk.CTkFont(size=12, weight="bold")
        ).pack(anchor="w", pady=(0, 4))

        row_path = ctk.CTkFrame(content, fg_color="transparent")
        row_path.pack(fill="x", pady=(0, 14))

        self.entry_path = ctk.CTkEntry(row_path, font=ctk.CTkFont(size=11))
        self.entry_path.insert(0, self.install_dir)
        self.entry_path.pack(side="left", fill="x", expand=True, padx=(0, 8))

        btn_browse = ctk.CTkButton(
            row_path,
            text="Обзор...",
            width=80,
            command=self.choose_dir
        )
        btn_browse.pack(side="left")

        # Options
        self.chk_desktop = ctk.CTkCheckBox(content, text="Создать ярлык на Рабочем столе (с иконкой волка)", font=ctk.CTkFont(size=12))
        self.chk_desktop.select()
        self.chk_desktop.pack(anchor="w", pady=4)

        self.chk_start_menu = ctk.CTkCheckBox(content, text="Добавить ярлык в меню «Пуск»", font=ctk.CTkFont(size=12))
        self.chk_start_menu.select()
        self.chk_start_menu.pack(anchor="w", pady=4)

        self.chk_launch = ctk.CTkCheckBox(content, text="Запустить лаунчер сразу после завершения установки", font=ctk.CTkFont(size=12))
        self.chk_launch.select()
        self.chk_launch.pack(anchor="w", pady=4)

        # Progress
        self.progress_bar = ctk.CTkProgressBar(content)
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x", pady=(16, 6))

        self.lbl_status = ctk.CTkLabel(
            content,
            text="Нажмите кнопку «Установить» для начала распаковки файлов.",
            font=ctk.CTkFont(size=11),
            text_color="#8fa394"
        )
        self.lbl_status.pack(anchor="w")

        # Footer Buttons
        footer = ctk.CTkFrame(self, fg_color="transparent", height=45)
        footer.pack(fill="x", padx=20, pady=(0, 16), side="bottom")

        btn_cancel = ctk.CTkButton(
            footer,
            text="Отмена",
            width=90,
            fg_color="#2c3e50",
            hover_color="#34495e",
            command=self.destroy
        )
        btn_cancel.pack(side="right", padx=(8, 0))

        self.btn_install = ctk.CTkButton(
            footer,
            text="🚀 Установить",
            width=130,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#27ae60",
            hover_color="#2ecc71",
            text_color="#ffffff",
            command=self.start_installation
        )
        self.btn_install.pack(side="right")

    def choose_dir(self):
        d = filedialog.askdirectory(initialdir=self.entry_path.get())
        if d:
            self.entry_path.delete(0, "end")
            self.entry_path.insert(0, os.path.normpath(d))

    def start_installation(self):
        target_dir = os.path.normpath(self.entry_path.get().strip())
        if not target_dir:
            messagebox.showwarning("Внимание", "Укажите путь к папке установки!")
            return

        self.btn_install.configure(state="disabled")
        self.lbl_status.configure(text="Подготовка папки установки...")
        self.progress_bar.set(0.1)

        import threading
        def worker():
            try:
                os.makedirs(target_dir, exist_ok=True)
                
                # 1. Copy launcher files
                total = len(LAUNCHER_FILES)
                for i, fname in enumerate(LAUNCHER_FILES):
                    src = os.path.join(BUNDLE_DIR, fname)
                    dst = os.path.join(target_dir, fname)
                    if os.path.exists(src):
                        os.makedirs(os.path.dirname(dst), exist_ok=True)
                        shutil.copy2(src, dst)
                    
                    p = 0.1 + (i / total) * 0.5
                    self.after(0, lambda p=p, f=fname: (
                        self.progress_bar.set(p),
                        self.lbl_status.configure(text=f"Копирование: {f}...")
                    ))

                # 2. Config file
                cfg_path = os.path.join(target_dir, "launcher_config.json")
                if not os.path.exists(cfg_path):
                    import json
                    with open(cfg_path, "w", encoding="utf-8") as f:
                        json.dump(DEFAULT_CONFIG_CONTENT, f, indent=2, ensure_ascii=False)

                # 3. Create shortcuts
                self.after(0, lambda: self.lbl_status.configure(text="Создание ярлыков..."))
                self.progress_bar.set(0.75)

                wolf_ico = os.path.join(target_dir, "minecraft_wolf.ico")
                if not os.path.exists(wolf_ico):
                    wolf_ico = os.path.join(target_dir, "launcher_icon.ico")

                vbs_launcher = os.path.join(target_dir, "Launcher.vbs")
                # Ensure Launcher.vbs points to current directory
                with open(vbs_launcher, "w", encoding="utf-8") as vf:
                    vf.write(f'Set WshShell = CreateObject("WScript.Shell")\n')
                    vf.write(f'WshShell.CurrentDirectory = "{target_dir}"\n')
                    vf.write(f'WshShell.Run "pythonw.exe launcher.py", 0, False\n')

                # Target for shortcut: wscript.exe running Launcher.vbs (silent no console)
                wscript_path = os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "System32", "wscript.exe")
                
                if self.chk_desktop.get():
                    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
                    shortcut_desktop = os.path.join(desktop, "Minecraft NeoForge Launcher.lnk")
                    create_windows_shortcut(
                        target_path=wscript_path,
                        shortcut_path=shortcut_desktop,
                        working_dir=target_dir,
                        icon_path=wolf_ico,
                        description="Minecraft NeoForge 1.21.1 Launcher"
                    )

                if self.chk_start_menu.get():
                    appdata = os.environ.get("APPDATA", "")
                    if appdata:
                        start_menu = os.path.join(appdata, r"Microsoft\Windows\Start Menu\Programs")
                        shortcut_sm = os.path.join(start_menu, "Minecraft NeoForge Launcher.lnk")
                        create_windows_shortcut(
                            target_path=wscript_path,
                            shortcut_path=shortcut_sm,
                            working_dir=target_dir,
                            icon_path=wolf_ico,
                            description="Minecraft NeoForge 1.21.1 Launcher"
                        )

                self.after(0, lambda: (
                    self.progress_bar.set(1.0),
                    self.lbl_status.configure(text="✓ Установка успешно завершена!"),
                    self.on_success(target_dir)
                ))

            except Exception as e:
                self.after(0, lambda err=e: (
                    self.btn_install.configure(state="normal"),
                    self.lbl_status.configure(text=f"Ошибка установки: {err}"),
                    messagebox.showerror("Ошибка", f"Не удалось завершить установку:\n{err}")
                ))

        threading.Thread(target=worker, daemon=True).start()

    def on_success(self, target_dir):
        msg = "Minecraft NeoForge Launcher успешно установлен!\nЯрлык с волком создан на Рабочем столе."
        messagebox.showinfo("Успех", msg)

        if self.chk_launch.get():
            vbs_p = os.path.join(target_dir, "Launcher.vbs")
            try:
                subprocess.Popen(["wscript.exe", vbs_p], cwd=target_dir)
            except Exception:
                pass

        self.destroy()

if __name__ == "__main__":
    app = InstallerApp()
    app.mainloop()
