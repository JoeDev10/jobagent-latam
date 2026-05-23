@echo off
chcp 65001 >nul
title JobAgent LATAM

cd /d "%~dp0"

echo.
echo   ==========================================
echo    JobAgent LATAM - Iniciando servidor...
echo   ==========================================
echo.

if not exist venv\Scripts\python.exe (
    echo   ERROR: No se encontró el entorno virtual.
    echo   Ejecutá primero: setup.bat
    pause
    exit /b 1
)

venv\Scripts\python.exe main_web.py

echo.
echo   Servidor detenido.
pause
