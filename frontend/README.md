# MINI Agent UI

Standalone Minerva Bot UI built with React + Vite and a lightweight Flask backend.

## Run (Frontend)

```powershell
cd mini
npm install
npm run dev
```

App runs on `http://localhost:5181` by default.

## Run Backend (required for fixed login + user-wise chat history)

```powershell
Set-Location "c:\Git_Files\MIW_Agent\mini\backend"
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
py app.py
```

Backend runs on `http://127.0.0.1:8008`.

## Fixed login setup

- Users:
	- `miw_admin`
	- `Tharun Veeramgari`
	- `Viswaa Ramasubramanian`
	- `Abinash Lingan`
- Password for all users: `MIW@2026`

Chat history is persisted in `mini/backend/data/minerva_bot.db` per user.

## Run with local Node at C:\node

Use this if `npm` is not globally available or PowerShell blocks `npm.ps1`.

```powershell
Set-Location "c:\Git_Files\MIW_Agent\mini"
$nodeHome = "C:\node\node-v24.16.0-win-x64"
$env:Path = "$nodeHome;" + $env:Path
& "$nodeHome\npm.cmd" install
& "$nodeHome\npm.cmd" run dev
```

## Build with local Node at C:\node

```powershell
Set-Location "c:\Git_Files\MIW_Agent\mini"
$nodeHome = "C:\node\node-v24.16.0-win-x64"
$env:Path = "$nodeHome;" + $env:Path
& "$nodeHome\npm.cmd" run build
```

## Notes

- This project is intentionally isolated from existing dashboards.
- Uses MIW-style green color coding and a ChatGPT-like workspace layout.
- Guest mode does not retain chat history.
