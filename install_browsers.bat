@echo off
chcp 65001 >nul
echo 正在安装 Playwright Chromium 浏览器（首次使用或升级后需执行一次）...
echo.
python -m playwright install chromium
if %errorlevel% equ 0 (
  echo.
  echo 安装完成！现在可以运行: python main.py
) else (
  echo.
  echo 安装失败，请确认已安装 Python 并执行过: pip install -r requirements.txt
)
pause
