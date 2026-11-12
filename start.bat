@echo off
REM ASHA Vaani one-command start (Windows). Requires Python 3.10+ on PATH.
cd /d "%~dp0"
if not exist .venv (python -m venv .venv)
call .venv\Scripts\activate.bat
pip install -q -r backend\requirements.txt
python scripts\setup\generate_keys.py
if not exist frontend\dist\index.html (
  echo Building frontend - needs Node 18+
  pushd frontend && call npm install && call npm run build && popd
)
echo Open http://localhost:8000  (phones need HTTPS: see README "Test on a phone")
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
