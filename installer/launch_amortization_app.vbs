Set shell = CreateObject("WScript.Shell")
localAppData = shell.ExpandEnvironmentStrings("%LOCALAPPDATA%")
launcherPath = localAppData & "\AmortizationCalculator\run_amortization_app.ps1"
command = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File """ & launcherPath & """"
shell.Run command, 0, False
