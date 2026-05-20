@echo off
chcp 65001 >nul
echo.
echo  ================================================
echo    JobAgent LATAM - Instalacion de dependencias
echo  ================================================
echo.

:: Activar venv
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo  [ERROR] No se encontro el entorno virtual.
    echo  Creandolo ahora...
    python -m venv venv
    call venv\Scripts\activate.bat
)

echo  [1/3] Instalando paquetes Python...
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo  [ERROR] Fallo la instalacion de paquetes.
    pause
    exit /b 1
)
echo  OK - Paquetes instalados

echo.
echo  [2/3] Instalando navegador Chromium (Playwright)...
playwright install chromium
if errorlevel 1 (
    echo  [AVISO] Playwright install fallo - puede que ya este instalado.
)
echo  OK - Chromium listo

echo.
echo  [3/3] Verificando instalacion...
python -c "import groq, playwright, streamlit, pydantic, bs4, rich, lxml; print('  OK - Todos los modulos disponibles')"
if errorlevel 1 (
    echo  [ERROR] Algunos modulos no se instalaron correctamente.
    pause
    exit /b 1
)

echo.
echo  ================================================
echo    Instalacion completada exitosamente!
echo  ================================================
echo.
echo  Proximo paso: ejecuta  configurar.bat  para
echo  ingresar tus credenciales de los portales.
echo.
pause
