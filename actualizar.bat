@echo off
setlocal EnableExtensions

REM Ajuste esta ruta si cambia la carpeta local del repositorio.
set "REPO=C:\Users\JFRodriguez\OneDrive - Autoridad del Canal de Panama\Documents\Doc Doctorado\Articulo 1\Borrador Articulo\nuevo\MareasTest\DATA\TuRepo"
set "PY_SCRIPT=download_data.py"

cd /d "%REPO%"
if errorlevel 1 goto ERROR_REPO

echo ============================================================
echo Actualizacion automatica - Aquarius / GitHub
echo Descarga series de tiempo, guarda data y sube al repositorio
echo ============================================================
echo.

if exist "__pycache__" rmdir /s /q "__pycache__"
for /d /r %%D in (__pycache__) do if exist "%%D" rmdir /s /q "%%D"
del /s /q "*.pyc" 2>nul

if not exist "%PY_SCRIPT%" (
    echo ERROR: no se encontro %PY_SCRIPT% en esta carpeta.
    echo Copie el download_data.py corregido dentro del repositorio.
    goto ERROR_FINAL
)

echo Ejecutando %PY_SCRIPT%...
echo El script de Python se encarga de:
echo   1. guardar cambios locales,
echo   2. sincronizar con GitHub,
echo   3. descargar las series,
echo   4. hacer commit,
echo   5. hacer push.
echo.

python "%PY_SCRIPT%"
if errorlevel 1 goto ERROR_FINAL

echo.
echo ============================================================
echo OK: series descargadas y cambios enviados a GitHub.
echo La ventana se cerrara en 10 segundos...
echo ============================================================
timeout /t 10 /nobreak >nul
exit /b 0

:ERROR_REPO
echo.
echo ERROR: no se pudo entrar al repositorio configurado.
echo Revise la variable REPO dentro de actualizar.bat.
goto ERROR_FINAL

:ERROR_FINAL
echo.
echo ============================================================
echo ERROR: hubo un problema en la actualizacion.
echo Revise los mensajes de arriba.
echo La ventana se cerrara en 10 segundos...
echo ============================================================
timeout /t 10 /nobreak >nul
exit /b 1
