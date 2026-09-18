Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Users\user\AppData\Roaming\.minecraft\launcher"
WshShell.Run "pythonw.exe launcher.py", 0, False
