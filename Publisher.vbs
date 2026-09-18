Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "c:\Users\user\AppData\Roaming\.minecraft"
WshShell.Run "pythonw.exe publisher_gui.py", 0, False
