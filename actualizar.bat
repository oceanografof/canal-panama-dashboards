@echo off
setlocal EnableExtensions DisableDelayedExpansion

REM ============================================================
REM Actualizacion automatica segura - Aquarius / GitHub
REM Debe estar en la RAIZ del repositorio, junto a download_data.py
REM ============================================================

set "REPO=%~dp0"
set "PY_SCRIPT=download_data.py"

pushd "%REPO%" >nul 2>&1
if errorlevel 1 goto ERROR_REPO

echo ============================================================
echo Actualizacion automatica segura - Aquarius / GitHub
echo Descarga series de tiempo, guarda data y sube cambios seguros
echo ============================================================
echo.

REM Verificaciones basicas de seguridad y ubicacion
where git >nul 2>&1
if errorlevel 1 (
    echo ERROR: Git no esta disponible en PATH.
    echo Instale Git para Windows o revise la variable PATH.
    goto ERROR_FINAL
)

if not exist ".git" (
    git rev-parse --is-inside-work-tree >nul 2>&1
    if errorlevel 1 (
        echo ERROR: esta carpeta no parece ser un repositorio Git.
        echo Coloque este BAT dentro de la raiz del repositorio.
        goto ERROR_FINAL
    )
)

if not exist "%PY_SCRIPT%" (
    echo ERROR: no se encontro %PY_SCRIPT% en esta carpeta.
    echo Copie el download_data.py blindado dentro de la raiz del repositorio.
    goto ERROR_FINAL
)

set "PYTHON_CMD="
where py >nul 2>&1
if not errorlevel 1 set "PYTHON_CMD=py -3"
if not defined PYTHON_CMD (
    where python >nul 2>&1
    if not errorlevel 1 set "PYTHON_CMD=python"
)
if not defined PYTHON_CMD (
    echo ERROR: no se encontro Python.
    echo Instale Python o agreguelo al PATH.
    goto ERROR_FINAL
)

echo Repositorio: %CD%
echo Python usado: %PYTHON_CMD%
echo.
echo El Python se encarga de:
echo   1. validar repositorio y rama,
echo   2. evitar subir credenciales o archivos sensibles,
echo   3. descargar solo desde panama.aquaticinformatics.net,
echo   4. normalizar CSV esperados,
echo   5. hacer commit y push solo de archivos autorizados.
echo.

%PYTHON_CMD% "%PY_SCRIPT%"
if errorlevel 1 goto ERROR_FINAL

echo.
echo ============================================================
echo OK: series descargadas y cambios seguros enviados a GitHub.
echo La ventana se cerrara en 10 segundos...
echo ============================================================
timeout /t 10 /nobreak >nul
popd >nul 2>&1
exit /b 0

:ERROR_REPO
echo.
echo ERROR: no se pudo entrar al repositorio.
echo Revise la ubicacion de actualizar.bat.
goto ERROR_FINAL

:ERROR_FINAL
echo.
echo ============================================================
echo ERROR: hubo un problema en la actualizacion segura.
echo Revise los mensajes de arriba.
echo La ventana se cerrara en 15 segundos...
echo ============================================================
timeout /t 15 /nobreak >nul
popd >nul 2>&1
exit /b 1
