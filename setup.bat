@echo off
chcp 65001 >nul
echo ========================================
echo    JobAgent LATAM - Instalacion
echo ========================================
echo.

echo [1/4] Creando entorno virtual...
python -m venv venv
call venv\Scripts\activate

echo [2/4] Instalando dependencias...
pip install -r requirements.txt

echo [3/4] Instalando Playwright (navegador Chromium)...
playwright install chromium

echo [4/4] Creando archivo .env...
if not exist .env (
    copy .env.example .env
    echo.
    echo  IMPORTANTE: Edita el archivo .env y completalo con:
    echo    - GROQ_API_KEY  (conseguila gratis en console.groq.com)
    echo    - Credenciales de los portales (Computrabajo, Bumeran, etc.)
    echo    - Token de Telegram (opcional, para notificaciones)
)

echo.
echo ========================================
echo    Instalacion completada!
echo ========================================
echo.
echo Proximos pasos:
echo   1. Edita .env con tu GROQ_API_KEY y credenciales de los portales
echo   2. Ejecuta: python main.py setup   (para cargar tu CV/perfil)
echo   3. Ejecuta: python main.py search  (para buscar y aplicar)
echo   4. Ejecuta: python main.py dashboard  (para ver el panel web)
echo.
pause
