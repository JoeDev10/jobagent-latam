@echo off
chcp 65001 >nul
echo.
echo  Migrando base de datos...
echo.
cd /d "%~dp0"
call venv\Scripts\activate
python migrar_db.py
pause
