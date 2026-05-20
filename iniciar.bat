@echo off
chcp 65001 >nul
call venv\Scripts\activate.bat 2>nul

:menu
cls
echo.
echo  ================================================
echo    JobAgent LATAM  -  Marcelo Joel Rodriguez
echo    QA Analyst ^| Manual ^& Automation Testing
echo  ================================================
echo.
echo    [1]  Buscar vacantes y aplicar
echo    [2]  Ver dashboard web (navegador)
echo    [3]  Ver estadisticas rapidas
echo    [4]  Configurar credenciales de portales
echo    [5]  Instalar / actualizar dependencias
echo    [6]  Probar scrapers (modo test)
echo    [0]  Salir
echo.
set /p opcion="  Elegir opcion: "

if "%opcion%"=="1" goto buscar
if "%opcion%"=="2" goto dashboard
if "%opcion%"=="3" goto stats
if "%opcion%"=="4" goto configurar
if "%opcion%"=="5" goto instalar
if "%opcion%"=="6" goto test
if "%opcion%"=="0" goto salir
goto menu

:buscar
cls
echo.
echo  Iniciando busqueda de vacantes...
echo  (podes ver el navegador abrirse - es normal)
echo.
python main.py search
echo.
echo  Busqueda finalizada.
pause
goto menu

:dashboard
cls
echo.
echo  Abriendo dashboard en http://localhost:8501
echo  Para cerrar el dashboard, presiona Ctrl+C en esta ventana.
echo.
python main.py dashboard
pause
goto menu

:stats
cls
echo.
python main.py stats
echo.
pause
goto menu

:configurar
cls
echo.
python configurar.py
pause
goto menu

:instalar
cls
echo.
call instalar.bat
goto menu

:test
cls
echo.
echo  Portales a probar: computrabajo bumeran
echo.
python check_scraper_live.py computrabajo bumeran
echo.
pause
goto menu

:salir
exit /b 0
