Amortization Calculator Installer
=================================

This installer is for Windows.

Requirements
------------
- Python 3.10 or newer, or Windows Package Manager (winget) so the installer can offer to install Python
- Internet access during installation so Python can download Streamlit, pandas, and Plotly

If Python is not installed:
1. Run Install-AmortizationCalculator.bat
2. If prompted, choose Y to install Python 3.12 using Windows Package Manager
3. If winget is not available, install Python manually from https://www.python.org/downloads/
4. During manual Python install, check "Add Python to PATH"
5. Run Install-AmortizationCalculator.bat again

Install
-------
1. Double-click Install-AmortizationCalculator.bat
2. If Windows asks for permission to run the script, allow it

The installer will:
- Copy the app into your local AppData folder
- Create a private Python virtual environment
- Install the required packages
- Create a Desktop shortcut named "Amortization Calculator"

Run
---
Double-click the Desktop shortcut named "Amortization Calculator".

Uninstall
---------
Double-click Uninstall-AmortizationCalculator.bat.

Saved Payment Schedules
-----------------------
Saved schedules are stored locally in the installed app folder:

%LOCALAPPDATA%\AmortizationCalculator\app\settings.json
