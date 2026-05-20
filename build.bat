@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Building SocialMediaTool.exe (with embedded Chromium)...
echo.
python build.py
if %errorlevel% neq 0 (
  echo.
  echo Build failed. See errors above.
  pause
  exit /b 1
)
echo.
pause
