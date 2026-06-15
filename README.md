# Amortization Line Graph Calculator

This is a Python application built with Streamlit and a pywebview desktop wrapper.

## What You Need

- Python 3.10 or newer.
- The Python packages listed in `requirements.txt`.
- A terminal or command prompt.

## Install On Windows

Download and run `AmortizationCalculatorSetup.exe`.

The setup executable downloads the latest app files from GitHub during installation,
preserves any existing `settings.json`, installs the Python package requirements into
the local app environment, and creates a Desktop shortcut named `Amortization Calculator`.

If Python 3.10 or newer is not installed, the setup executable can prompt to install
Python 3.12 using Windows Package Manager.

## Run Locally

```powershell
cd "C:\Users\jmb13\OneDrive\Documents\Python Code\amortization_app"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run app.py
```

Streamlit will print a local URL, usually `http://localhost:8501`.
