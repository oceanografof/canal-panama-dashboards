@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "REPO=C:\Users\JFRodriguez\OneDrive - Autoridad del Canal de Panama\Documents\Doc Doctorado\Articulo 1\Borrador Articulo\nuevo\MareasTest\DATA\TuRepo"
set "BRANCH=main"

cd /d "%REPO%" || (
    echo ERROR: no se pudo entrar al repositorio.
    timeout /t 10 /nobreak >nul
    exit /b 1
)

echo ============================================================
echo Actualizacion automatica - GitHub
echo Sube archivos nuevos y modificados antes de sincronizar
echo ============================================================

call :cleanup_cache
call :ensure_gitignore

echo.
echo [1/6] Guardando cambios locales antes de sincronizar...
call :commit_all "Cambios locales antes de sincronizar"

echo.
echo [2/6] Sincronizando con GitHub...
git fetch origin
if errorlevel 1 goto :git_error

git checkout %BRANCH%
if errorlevel 1 goto :git_error

git pull --no-rebase -X ours origin %BRANCH%
if errorlevel 1 call :resolve_conflicts
if errorlevel 1 goto :git_error

git push origin %BRANCH%
if errorlevel 1 goto :git_error

echo.
echo [3/6] Ejecutando descarga de datos...
python download_data.py
if errorlevel 1 (
    echo ADVERTENCIA: download_data.py termino con error.
    echo Se intentara subir cualquier archivo que haya cambiado.
)

echo.
echo [4/6] Preparando archivos para subir...
call :cleanup_cache
call :ensure_gitignore

echo.
echo [5/6] Subiendo cualquier archivo nuevo o modificado...
call :commit_all "Auto todos los archivos"

echo.
echo [6/6] Sincronizacion final con GitHub...
git pull --no-rebase -X ours origin %BRANCH%
if errorlevel 1 call :resolve_conflicts
if errorlevel 1 goto :git_error

git push origin %BRANCH%
if errorlevel 1 goto :git_error

echo.
echo ============================================================
echo OK: cambios enviados a GitHub.
echo Streamlit Cloud se actualizara en 1-2 minutos.
echo La ventana se cerrara en 10 segundos...
echo ============================================================
timeout /t 10 /nobreak >nul
exit /b 0


:cleanup_cache
if exist "__pycache__" rmdir /s /q "__pycache__"
for /d /r %%D in (__pycache__) do if exist "%%D" rmdir /s /q "%%D"
del /s /q "*.pyc" 2>nul
exit /b 0


:ensure_gitignore
if not exist ".gitignore" type nul > ".gitignore"
findstr /x /c:"__pycache__/" ".gitignore" >nul 2>nul || echo __pycache__/>> ".gitignore"
findstr /x /c:"*.pyc" ".gitignore" >nul 2>nul || echo *.pyc>> ".gitignore"
exit /b 0


:commit_all
git add -A
set "HAS_CHANGES="
for /f "delims=" %%S in ('git status --porcelain') do set "HAS_CHANGES=1"

if defined HAS_CHANGES (
    git commit -m "%~1 %date% %time%"
) else (
    echo Sin cambios para commit.
)
exit /b 0


:resolve_conflicts
echo.
echo Resolviendo conflictos automaticamente.
echo Se conservara la version local para archivos en conflicto.

set "HAS_CONFLICTS="
for /f "delims=" %%F in ('git diff --name-only --diff-filter=U') do (
    set "HAS_CONFLICTS=1"
    echo Conservando local: %%F
    git checkout --ours -- "%%F"
    git add "%%F"
)

if defined HAS_CONFLICTS (
    git commit -m "Resuelve conflictos conservando version local %date% %time%"
    exit /b 0
) else (
    echo No se encontraron archivos en conflicto.
    exit /b 1
)


:git_error
echo.
echo ============================================================
echo ERROR: hubo un problema de Git.
echo Revise los mensajes de arriba.
echo La ventana se cerrara en 10 segundos...
echo ============================================================
timeout /t 10 /nobreak >nul
exit /b 1
