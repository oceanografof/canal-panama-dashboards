"""
download_data.py — Descarga series de tiempo de Aquatic Informatics, normaliza CSV,
guarda solo archivos esperados en /data/ y sube cambios seguros al repositorio.

Diseñado para ejecutarse desde el repositorio local dentro de la red ACP:
    python download_data.py

Medidas de seguridad incluidas:
- No usa git add -A indiscriminado.
- Solo agrega al commit archivos permitidos y esperados.
- Bloquea patrones típicos de credenciales antes del commit.
- No imprime URLs completas ni credenciales.
- Valida dominio HTTPS permitido para descargas.
- Limita tamaño de descarga y contenido ZIP.
- No extrae ZIPs al disco, evitando Zip Slip.
- Detiene el flujo si hay cambios rastreados fuera de la lista permitida.
"""
from __future__ import annotations

import csv
import fnmatch
import io
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode, urlparse

import pandas as pd

# ── Configuración general ──────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_DIR = SCRIPT_DIR
OUTPUT_DIR = REPO_DIR / "data"

TIME_SERIES_DATE_RANGE = "Months6"
TIME_ZONE = "-5"
CALENDAR = "CALENDARYEAR"

ALLOWED_DOWNLOAD_HOSTS = {"panama.aquaticinformatics.net"}
TIMEOUT_CONN = 300
TIMEOUT_READ = 900
CHUNK_SIZE = 65536
MAX_DOWNLOAD_BYTES = 180 * 1024 * 1024        # 180 MB por BulkExport
MAX_ZIP_FILES = 25
MAX_ZIP_UNCOMPRESSED_BYTES = 220 * 1024 * 1024

# Archivos raíz que pueden subirse automáticamente.
ALLOWED_ROOT_FILES = {
    "LakeHouse_Data.xlsx",
    "app_dss.py",
    "app_demandas.py",
    "app_temperatura.py",
    "download_data.py",
    "actualizar.bat",
    "requirements.txt",
    ".gitignore",
    # Activo visual usado por el dashboard. Se permite de forma explícita
    # para que un cambio legítimo del logo no bloquee la actualización segura.
    "LOGO HIMH.jpg",
}

# Activos visuales permitidos únicamente si están en la raíz del repositorio,
# no tienen nombres sensibles y no exceden MAX_AUTO_ASSET_BYTES.
# Esto cubre logos/íconos usados por Streamlit sin abrir permisos generales.
ALLOWED_ROOT_ASSET_PATTERNS = (
    "*.png", "*.jpg", "*.jpeg", "*.webp", "*.svg",
)
MAX_AUTO_ASSET_BYTES = 8 * 1024 * 1024

# Apps Streamlit del repositorio que pueden subirse automáticamente.
# Esto evita que cada nueva app tipo app_temperatura.py, app_AyS.py,
# app_simulacion_dss.py, etc. bloquee el commit seguro.
# La seguridad se mantiene porque antes de permitirlas se aplican:
#   1) bloqueo por nombre sensible,
#   2) revisión de posibles credenciales con scan_for_secrets(),
#   3) solo archivos Python en la raíz del repo.
ALLOWED_ROOT_APP_PATTERNS = (
    "app_*.py",
)

# Nunca subir automáticamente archivos sensibles, aunque estén modificados.
BLOCKED_PATH_PATTERNS = (
    ".env", ".env.local", ".env.production", ".env.development",
    "credential", "credentials", "secret", "secrets", "token", "tokens",
    "service_account", "private_key", "id_rsa", "id_dsa", "id_ed25519",
    ".pem", ".key", ".p12", ".pfx", ".kdbx", ".ovpn",
)

# Solo estos archivos generados se resuelven automáticamente en rebase conservando local.
# Se evita resolver automáticamente scripts, para no sobrescribir cambios remotos importantes.
PREFER_LOCAL_PATTERNS = (
    "LakeHouse_Data.xlsx",
    "data/",
)

# Archivos locales generados por la app o por descargas manuales que NO deben
# quedarse versionados en Git. Si ya estaban rastreados, el script los retira
# del control de Git con `git rm --cached` y deja el archivo local intacto.
LOCAL_ONLY_GIT_PATTERNS = (
    "dss_views.txt",
    ".dss_views.txt",
    ".app_state",
    ".app_state/*",
    "BulkExport*.csv",
    "BulkExport-*.csv",
    # Archivos de sistema creados por Windows/macOS/OneDrive; no son datos operativos.
    "desktop.ini",
    "**/desktop.ini",
    "Thumbs.db",
    "**/Thumbs.db",
    ".DS_Store",
    "**/.DS_Store",
)

SENSITIVE_REGEXES = [
    re.compile(r"ghp_[A-Za-z0-9_]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN (?:RSA |OPENSSH |DSA |EC |)?PRIVATE KEY-----"),
    re.compile(r"(?i)(?:password|passwd|pwd|token|api[_-]?key|secret)\s*[:=]\s*['\"][^'\"]{8,}['\"]"),
]

# ── Series a descargar ─────────────────────────────────────────────────────
SERIES_CONFIG = [
    {
        "station": "TstCHCP_AT",
        "dataset": "Discharge.AT_GAT_Diario@TstCHCP_AT",
        "calculation": "Instantaneous",
        "unit_id": 218,
        "interval": "PointsAsRecorded",
        "time_aligned": "True",
        "out_name": "Discharge_AT_GAT_Diario.csv",
        "label": "Caudal AT GAT Diario @ TstCHCP_AT",
        "kind_keywords": ["Discharge.AT_GAT_Diario", "AT_GAT_Diario"],
    },
    {
        "station": "TstCHCP_AT",
        "dataset": "Discharge.AT_ALHA_Diario@TstCHCP_AT",
        "calculation": "Instantaneous",
        "unit_id": 218,
        "interval": "PointsAsRecorded",
        "time_aligned": "True",
        "out_name": "Discharge_AT_ALHA_Diario.csv",
        "label": "Caudal AT ALHA Diario @ TstCHCP_AT",
        "kind_keywords": ["Discharge.AT_ALHA_Diario", "AT_ALHA_Diario"],
    },
    {
        "station": "GAT",
        "dataset": "Lake-Res elevation.Telem AVG@GAT",
        "calculation": "Instantaneous",
        "unit_id": 70,
        "interval": "PointsAsRecorded",
        "time_aligned": "True",
        "out_name": "Lake_Res_elevation_Telem_AVG_GAT.csv",
        "label": "Nivel Lake-Res Telem AVG @ GAT",
        "kind_keywords": ["Lake-Res elevation.Telem AVG@GAT", "Telem AVG@GAT", "AVG@GAT"],
    },
    {
        "station": "MAD",
        "dataset": "Lake-Res elevation.Telem Radar@MAD",
        "calculation": "Instantaneous",
        "unit_id": 70,
        "interval": "PointsAsRecorded",
        "time_aligned": "True",
        "date_range": "Years1",
        "calendar": "CALENDARYEAR2",
        "out_name": "Lake_Res_elevation_Telem_Radar_MAD.csv",
        "label": "Nivel Lake-Res Telem Radar @ MAD",
        "kind_keywords": ["Lake-Res elevation.Telem Radar@MAD", "Telem Radar@MAD", "Radar@MAD"],
    },
    {
        "station": "AMA",
        "dataset": "Tide Height.Telem Radar@AMA",
        "calculation": "Instantaneous",
        "unit_id": 70,
        "interval": "PointsAsRecorded",
        "time_aligned": "True",
        "out_name": "Tide_Height_Telem_Radar_AMA.csv",
        "label": "Marea radar @ AMA",
        "kind_keywords": ["Tide Height.Telem Radar", "AMA", "Amador"],
    },
    {
        "station": "DHT",
        "dataset": "Tide Height.Telem Radar@DHT",
        "calculation": "Instantaneous",
        "unit_id": 70,
        "interval": "PointsAsRecorded",
        "time_aligned": "True",
        "out_name": "Tide_Height_Telem_Radar_DHT.csv",
        "label": "Marea radar @ DHT / Diablo Heights",
        "kind_keywords": ["Tide Height.Telem Radar", "DHT", "Diablo Heights"],
    },
    {
        "station": "LMB",
        "dataset": "Tide Height.Telem Radar@LMB",
        "calculation": "Instantaneous",
        "unit_id": 70,
        "interval": "PointsAsRecorded",
        "time_aligned": "True",
        "out_name": "Tide_Height_Telem_Radar_LMB.csv",
        "label": "Marea radar @ LMB / Limon Bay",
        "kind_keywords": ["Tide Height.Telem Radar", "LMB", "Limon Bay"],
    },
    {
        "station": "PMG",
        "dataset": "Evapo Rate.Daily Tank@PMG",
        "calculation": "Instantaneous",
        "unit_id": 166,
        "interval": "PointsAsRecorded",
        "time_aligned": "True",
        "date_range": "Years1",
        "calendar": "CALENDARYEAR",
        "out_name": "Evapo_Rate_Daily_Tank_PMG.csv",
        "label": "Evaporación diaria de tanque @ PMG",
        "kind_keywords": ["Evapo Rate.Daily Tank@PMG", "Daily Tank@PMG", "PMG"],
    },
    {
        "station": "CZL",
        "dataset": "Evapo Rate.Daily Tank@CZL",
        "calculation": "Instantaneous",
        "unit_id": 166,
        "interval": "PointsAsRecorded",
        "time_aligned": "True",
        "date_range": "Years1",
        "calendar": "CALENDARYEAR",
        "out_name": "Evapo_Rate_Daily_Tank_CZL.csv",
        "label": "Evaporación diaria de tanque @ CZL",
        "kind_keywords": ["Evapo Rate.Daily Tank@CZL", "Daily Tank@CZL", "CZL"],
    },
    {
        "station": "GAT",
        "dataset": "Total Storage.V Evap Gat 0.85@GAT",
        "calculation": "Instantaneous",
        "unit_id": 181,
        "interval": "PointsAsRecorded",
        "time_aligned": "True",
        "date_range": "Years1",
        "calendar": "CALENDARYEAR",
        "out_name": "Total_Storage_V_Evap_Gat_0_85_GAT.csv",
        "label": "Volumen total de evaporación Gatún 0.85 @ GAT",
        "kind_keywords": ["Total Storage.V Evap Gat 0.85@GAT", "V Evap Gat 0.85", "GAT"],
    },
    {
        "station": "MAD",
        "dataset": "Total Storage.V Evap Alha 0.85@MAD",
        "calculation": "Instantaneous",
        "unit_id": 181,
        "interval": "PointsAsRecorded",
        "time_aligned": "True",
        "date_range": "Years1",
        "calendar": "CALENDARYEAR",
        "out_name": "Total_Storage_V_Evap_Alha_0_85_MAD.csv",
        "label": "Volumen total de evaporación Alhajuela 0.85 @ MAD",
        "kind_keywords": ["Total Storage.V Evap Alha 0.85@MAD", "V Evap Alha 0.85", "MAD"],
    },
]

BASE_BULK_URL = (
    "https://panama.aquaticinformatics.net/Export/BulkExport"
    "?DateRange=Custom&Period=P90D"
    "&TimeZone=-5&Calendar=CALENDARYEAR2"
    "&Interval=Hourly&Step=1&ExportFormat=csv&TimeAligned=False"
    "&RoundData=True&IncludeGradeCodes=undefined&IncludeApprovalLevels=undefined"
    "&IncludeQualifiers=undefined&IncludeInterpolationTypes=False"
    "&Datasets%5B0%5D.DatasetName=Water%20Temp.LAN%20WT%20AVG%40AMA"
    "&Datasets%5B0%5D.Calculation=Aggregate&Datasets%5B0%5D.UnitId=153"
    "&Datasets%5B1%5D.DatasetName=Water%20Temp.Telemetria%20TEMP%40AMA"
    "&Datasets%5B1%5D.Calculation=Aggregate&Datasets%5B1%5D.UnitId=153"
    "&Datasets%5B2%5D.DatasetName=Wind%20Speed.WS%20AVG%40LMB"
    "&Datasets%5B2%5D.Calculation=Aggregate&Datasets%5B2%5D.UnitId=170"
    "&Datasets%5B3%5D.DatasetName=Wind%20Speed.LAN%20WS%20AVG%40FLC"
    "&Datasets%5B3%5D.Calculation=Aggregate&Datasets%5B3%5D.UnitId=170"
)

BASE_DATASET_MAP = [
    {"keywords": ["Water Temp.LAN WT AVG", "LAN WT AVG", "LAN_WT"], "out_name": "LAN_WT_AVG_AMA.csv", "label": "Temp LAN WT AVG @ AMA"},
    {"keywords": ["Water Temp.Telemetria TEMP", "Telemetria", "TEMP@AMA"], "out_name": "Telemetria_TEMP_AMA.csv", "label": "Temp Telemetría @ AMA"},
    {"keywords": ["Wind Speed.WS AVG", "WS AVG@LMB", "WS_AVG"], "out_name": "WS_AVG_LMB.csv", "label": "Viento WS AVG @ LMB"},
    {"keywords": ["Wind Speed.LAN WS AVG", "LAN WS AVG", "LAN_WS"], "out_name": "LAN_WS_AVG_FLC.csv", "label": "Viento LAN WS AVG @ FLC"},
]

# Estas 4 series antes se descargaban juntas en un BulkExport base. Para evitar
# que Aquarius entregue un ZIP parcial/cacheado y queden archivos sin actualizar,
# también se consultan individualmente, igual que las demás series operativas.
BASE_SERIES_CONFIG = [
    # Estas 4 series deben descargarse con los parámetros exactos indicados por Aquarius:
    # DateRange=EntirePeriodOfRecord, Calendar=CALENDARYEAR,
    # Interval=PointsAsRecorded, TimeAligned=True, Calculation=Instantaneous.
    # Antes estaban como Aggregate/Hourly/P90D y por eso Aquarius devolvía CSV tipo
    # "Aggregate" que no se normalizaban correctamente.
    {
        "station": "AMA",
        "dataset": "Water Temp.LAN WT AVG@AMA",
        "calculation": "Instantaneous",
        "unit_id": 153,
        "interval": "PointsAsRecorded",
        "time_aligned": "True",
        "date_range": "EntirePeriodOfRecord",
        "calendar": "CALENDARYEAR",
        "out_name": "LAN_WT_AVG_AMA.csv",
        "label": "Temp LAN WT AVG @ AMA",
        "kind_keywords": ["Water Temp.LAN WT AVG", "LAN WT AVG", "LAN_WT", "WT AVG@AMA", "AMA"],
    },
    {
        "station": "AMA",
        "dataset": "Water Temp.Telemetria TEMP@AMA",
        "calculation": "Instantaneous",
        "unit_id": 153,
        "interval": "PointsAsRecorded",
        "time_aligned": "True",
        "date_range": "EntirePeriodOfRecord",
        "calendar": "CALENDARYEAR",
        "out_name": "Telemetria_TEMP_AMA.csv",
        "label": "Temp Telemetría @ AMA",
        "kind_keywords": ["Water Temp.Telemetria TEMP", "Telemetria TEMP", "TEMP@AMA", "AMA"],
    },
    {
        "station": "LMB",
        "dataset": "Wind Speed.WS AVG@LMB",
        "calculation": "Instantaneous",
        "unit_id": 170,
        "interval": "PointsAsRecorded",
        "time_aligned": "True",
        "date_range": "EntirePeriodOfRecord",
        "calendar": "CALENDARYEAR",
        "out_name": "WS_AVG_LMB.csv",
        "label": "Viento WS AVG @ LMB",
        "kind_keywords": ["Wind Speed.WS AVG", "WS AVG@LMB", "WS_AVG", "LMB"],
    },
    {
        "station": "FLC",
        "dataset": "Wind Speed.LAN WS AVG@FLC",
        "calculation": "Instantaneous",
        "unit_id": 170,
        "interval": "PointsAsRecorded",
        "time_aligned": "True",
        "date_range": "EntirePeriodOfRecord",
        "calendar": "CALENDARYEAR",
        "out_name": "LAN_WS_AVG_FLC.csv",
        "label": "Viento LAN WS AVG @ FLC",
        "kind_keywords": ["Wind Speed.LAN WS AVG", "LAN WS AVG", "LAN_WS", "FLC"],
    },
]

ALL_SERIES_CONFIG = SERIES_CONFIG + BASE_SERIES_CONFIG
EXPECTED_DATA_FILES = {m["out_name"] for m in ALL_SERIES_CONFIG}


@dataclass
class GitStatusEntry:
    xy: str
    path: str


def sanitize_text(text: str) -> str:
    """Redacta posibles credenciales antes de imprimir mensajes de Git/errores."""
    if not text:
        return ""
    text = re.sub(r"https://([^/@:\s]+):([^/@\s]+)@", r"https://***:***@", text)
    text = re.sub(r"https://([^/@\s]+)@github\.com", r"https://***@github.com", text)
    for rgx in SENSITIVE_REGEXES[:4]:
        text = rgx.sub("***REDACTED***", text)
    return text


def rel_path(path: Path) -> str:
    return path.relative_to(REPO_DIR).as_posix()


def is_path_blocked(path: str) -> bool:
    p = path.replace("\\", "/").lower()
    name = Path(p).name.lower()
    return any(pattern.lower() in p or pattern.lower() == name for pattern in BLOCKED_PATH_PATTERNS)


def is_allowed_root_app_file(path: str) -> bool:
    """Permite apps Streamlit de la raíz sin abrir permisos generales.

    Ejemplos permitidos: app_temperatura.py, app_demandas.py, app_AyS.py.
    No permite subcarpetas ni nombres con patrones sensibles como token/secret.
    """
    p = path.replace("\\", "/")
    name = Path(p).name
    if "/" in p:
        return False
    if is_path_blocked(p):
        return False
    return any(fnmatch.fnmatch(name, pat) for pat in ALLOWED_ROOT_APP_PATTERNS)


def is_allowed_root_asset_file(path: str) -> bool:
    """Permite logos/activos visuales pequeños en la raíz del repo.

    Evita que un logo modificado bloquee el flujo, pero conserva blindaje:
    - no permite subcarpetas,
    - no permite nombres sensibles,
    - no permite archivos mayores al límite,
    - no autoriza eliminaciones accidentales de activos.
    """
    p = path.replace("\\", "/")
    name = Path(p).name
    if "/" in p:
        return False
    if is_path_blocked(p):
        return False
    if not any(fnmatch.fnmatch(name.lower(), pat.lower()) for pat in ALLOWED_ROOT_ASSET_PATTERNS):
        return False

    asset_path = REPO_DIR / p
    try:
        return asset_path.is_file() and asset_path.stat().st_size <= MAX_AUTO_ASSET_BYTES
    except OSError:
        return False


def is_allowed_to_commit(path: str) -> bool:
    p = path.replace("\\", "/")
    if is_path_blocked(p):
        return False
    if "/" not in p and (p in ALLOWED_ROOT_FILES or is_allowed_root_app_file(p) or is_allowed_root_asset_file(p)):
        return True
    if p.startswith("data/") and Path(p).name in EXPECTED_DATA_FILES:
        return True
    return False


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    tmp.replace(path)


def build_series_url(series: dict) -> str:
    params = {
        "DateRange": series.get("date_range", TIME_SERIES_DATE_RANGE),
        "TimeZone": series.get("time_zone", TIME_ZONE),
        "Calendar": series.get("calendar", CALENDAR),
        "Interval": series.get("interval", "PointsAsRecorded"),
        "Step": str(series.get("step", "1")),
        "ExportFormat": "csv",
        "TimeAligned": series.get("time_aligned", "True"),
        "RoundData": "True",
        "IncludeGradeCodes": "undefined",
        "IncludeApprovalLevels": "undefined",
        "IncludeQualifiers": "undefined",
        "IncludeInterpolationTypes": "False",
        "IncludeNotes": "undefined",
        "Datasets[0].DatasetName": series["dataset"],
        "Datasets[0].Calculation": series.get("calculation", "Instantaneous"),
        "Datasets[0].UnitId": str(series["unit_id"]),
        "_": str(int(time.time() * 1000)),
    }
    if series.get("period"):
        params["Period"] = series["period"]
    return "https://panama.aquaticinformatics.net/Export/BulkExport?" + urlencode(params)


def validate_download_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme.lower() != "https":
        raise ValueError("URL bloqueada: solo se permite HTTPS.")
    if parsed.hostname not in ALLOWED_DOWNLOAD_HOSTS:
        raise ValueError(f"URL bloqueada: dominio no permitido ({parsed.hostname}).")


def run_git(repo_dir: Path, *cmd: str, env: dict | None = None) -> tuple[int, str, str]:
    full_env = os.environ.copy()
    full_env.setdefault("GIT_TERMINAL_PROMPT", "0")
    if env:
        full_env.update(env)
    result = subprocess.run(
        list(cmd),
        cwd=str(repo_dir),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=full_env,
    )
    # IMPORTANTE:
    # No usar .strip() aquí. La salida de `git status --short` usa los dos
    # primeros caracteres como columnas de estado y un espacio separador.
    # Si se eliminan espacios iniciales, rutas como "LakeHouse_Data.xlsx"
    # pueden quedar mal interpretadas como "akeHouse_Data.xlsx", y
    # "data/archivo.csv" como "ata/archivo.csv".
    stdout = sanitize_text(result.stdout.rstrip("\r\n"))
    stderr = sanitize_text(result.stderr.rstrip("\r\n"))
    return result.returncode, stdout, stderr


def cleanup_temp_files(repo_dir: Path) -> None:
    for pycache in repo_dir.rglob("__pycache__"):
        if ".git" not in pycache.parts:
            shutil.rmtree(pycache, ignore_errors=True)
    for pyc in repo_dir.rglob("*.pyc"):
        if ".git" not in pyc.parts:
            try:
                pyc.unlink()
            except OSError:
                pass

    # Limpieza de BulkExport crudos dejados en la raíz por descargas manuales.
    # Los CSV normalizados esperados se conservan en /data/.
    for raw in list(repo_dir.glob("BulkExport*.csv")) + list(repo_dir.glob("BulkExport-*.csv")):
        if raw.is_file():
            try:
                raw.unlink()
                print(f"  ✅ BulkExport crudo eliminado de la raíz: {raw.name}")
            except OSError:
                pass


def path_matches_any(path: str, patterns: tuple[str, ...]) -> bool:
    p = path.replace("\\", "/")
    return any(fnmatch.fnmatch(p, pat) or p == pat.rstrip("/") or p.startswith(pat.rstrip("/") + "/") for pat in patterns)


def is_local_only_path(path: str) -> bool:
    return path_matches_any(path, LOCAL_ONLY_GIT_PATTERNS)


def untrack_local_only_files(repo_dir: Path) -> None:
    """Retira del control Git contadores/estado local y BulkExport crudos.

    No borra los archivos del disco; solo evita que bloqueen la automatización
    o se suban al repositorio.
    """
    code, out, err = run_git(repo_dir, "git", "ls-files")
    if code != 0:
        return
    tracked = [line.strip().replace("\\", "/") for line in out.splitlines() if line.strip()]
    to_untrack = sorted({p for p in tracked if is_local_only_path(p)})
    if not to_untrack:
        return
    code, out, err = run_git(repo_dir, "git", "rm", "--cached", "-r", "-f", "--", *to_untrack)
    if code == 0:
        print("  ✅ Archivos locales retirados del control Git:")
        for path in to_untrack:
            print(f"    · {path}")
    else:
        raise RuntimeError(f"No se pudieron retirar archivos locales del control Git: {(err or out).strip()}")


def ensure_gitignore(repo_dir: Path) -> None:
    gitignore = repo_dir / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8", errors="replace") if gitignore.exists() else ""
    lines = existing.splitlines()
    stripped = [line.strip() for line in lines]
    changed = False
    for rule in (
        "__pycache__/", "*.pyc", "*.tmp", "*.bak",
        ".env", ".env.*", "*.pem", "*.key", "credentials*", "secrets*",
        # Estado local del dashboard y BulkExport crudos no normalizados.
        ".app_state/", "dss_views.txt", ".dss_views.txt",
        "BulkExport*.csv", "BulkExport-*.csv",
        "desktop.ini", "**/desktop.ini", "Thumbs.db", "**/Thumbs.db", ".DS_Store", "**/.DS_Store",
    ):
        if rule not in stripped:
            lines.append(rule)
            changed = True
    if changed:
        atomic_write_text(gitignore, "\n".join(lines).rstrip() + "\n")
        print("  ✅ .gitignore reforzado para temporales, credenciales y estado local")


def unquote_git_path(path: str) -> str:
    """Normaliza rutas de `git status --short` cuando Git las imprime entre comillas.

    Ejemplo real: Git puede devolver ` M "LOGO HIMH.jpg"`. Si no se quitan
    esas comillas, el archivo se interpreta como no autorizado aunque esté en
    ALLOWED_ROOT_FILES.
    """
    cleaned = path.rstrip()
    if len(cleaned) >= 2 and cleaned[0] == '"' and cleaned[-1] == '"':
        try:
            import ast
            value = ast.literal_eval(cleaned)
            if isinstance(value, str):
                return value
        except Exception:
            return cleaned[1:-1]
    return cleaned


def parse_status(status: str) -> list[GitStatusEntry]:
    entries: list[GitStatusEntry] = []
    for line in status.splitlines():
        if len(line) < 4:
            continue
        xy = line[:2]
        # No eliminar espacios al inicio de la ruta; Git ya separa el estado
        # con los tres primeros caracteres. Solo se eliminan finales.
        path = line[3:].rstrip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1].rstrip()
        path = unquote_git_path(path)
        entries.append(GitStatusEntry(xy=xy, path=path.replace("\\", "/")))
    return entries


def git_status_short(repo_dir: Path) -> str:
    code, out, err = run_git(repo_dir, "git", "status", "--short")
    # Conserva espacios iniciales de las columnas XY de Git.
    return out.rstrip("\r\n") if code == 0 else (err or out).rstrip("\r\n")


def scan_for_secrets(repo_dir: Path, paths: list[str]) -> None:
    suspicious: list[str] = []
    for path in paths:
        if path.startswith("data/") or path.lower().endswith(".xlsx"):
            continue
        p = repo_dir / path
        if not p.exists() or p.is_dir():
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for rgx in SENSITIVE_REGEXES:
            if rgx.search(text):
                suspicious.append(path)
                break
    if suspicious:
        joined = ", ".join(sorted(set(suspicious)))
        raise RuntimeError(
            "Se detectaron posibles credenciales en archivos que iban a subirse. "
            f"Revise antes de continuar: {joined}"
        )


def git_add_allowed(repo_dir: Path) -> bool:
    status = git_status_short(repo_dir)
    entries = parse_status(status)
    if not entries:
        return False

    allowed: list[str] = []
    staged_local_removals: list[str] = []
    blocked_or_unapproved: list[str] = []
    tracked_unapproved: list[str] = []

    for entry in entries:
        path = entry.path
        if is_allowed_to_commit(path):
            allowed.append(path)
            continue

        # Los archivos locales retirados con git rm --cached aparecen como D.
        # Se permite esa eliminación del repositorio, pero nunca se vuelve a
        # agregar el archivo local al commit.
        if is_local_only_path(path) and "D" in entry.xy:
            staged_local_removals.append(path)
            continue

        blocked_or_unapproved.append(path)
        # Cambios rastreados fuera de la lista permitida pueden bloquear pull --rebase.
        if entry.xy != "??":
            tracked_unapproved.append(path)

    if blocked_or_unapproved:
        print("  ⚠️ Archivos no autorizados para commit automático; se omiten:")
        for path in sorted(set(blocked_or_unapproved)):
            print(f"    · {path}")

    if staged_local_removals:
        print("  ✅ Se retirarán del repositorio archivos locales/no operativos:")
        for path in sorted(set(staged_local_removals)):
            print(f"    · {path}")

    if tracked_unapproved:
        raise RuntimeError(
            "Hay archivos rastreados modificados fuera de la lista segura. "
            "No haré commit ni rebase automático para evitar subir o sobrescribir algo sensible. "
            "Revise estos archivos: " + ", ".join(sorted(set(tracked_unapproved)))
        )

    if not allowed and not staged_local_removals:
        return False

    scan_for_secrets(repo_dir, allowed)
    for path in sorted(set(allowed)):
        code, out, err = run_git(repo_dir, "git", "add", "-f", "--", path)
        if code != 0:
            raise RuntimeError(f"git add falló para {path}: {(err or out).strip()}")
    return True

def commit_auto_changes(repo_dir: Path, message: str) -> bool:
    cleanup_temp_files(repo_dir)
    ensure_gitignore(repo_dir)
    untrack_local_only_files(repo_dir)
    staged_any = git_add_allowed(repo_dir)
    if not staged_any:
        print("  Sin cambios seguros para commit.")
        return False

    code, out, err = run_git(repo_dir, "git", "diff", "--cached", "--name-only")
    staged_files = [p.strip() for p in out.splitlines() if p.strip()] if code == 0 else []
    print("  Cambios seguros para commit:")
    for path in staged_files:
        print(f"    · {path}")

    code, out, err = run_git(repo_dir, "git", "commit", "-m", message)
    if code != 0:
        msg = (out + " " + err).strip()
        if "nothing to commit" in msg or "nada para hacer commit" in msg:
            return False
        raise RuntimeError(f"git commit falló: {msg}")
    print(f"  ✅ git commit OK: {message}")
    return True


def is_prefer_local_path(path: str) -> bool:
    path = path.replace("\\", "/")
    return any(path == pat.rstrip("/") or path.startswith(pat) for pat in PREFER_LOCAL_PATTERNS)


def resolve_generated_rebase_conflicts(repo_dir: Path) -> bool:
    status = git_status_short(repo_dir)
    conflicted = []
    for entry in parse_status(status):
        if any(c in entry.xy for c in ("U", "A", "D")) and is_prefer_local_path(entry.path):
            conflicted.append(entry.path)
    if not conflicted:
        return False

    print("  ⚠️ Conflicto en archivos generados. Se conserva la versión local solo para datos:")
    for path in conflicted:
        print(f"    · {path}")
        run_git(repo_dir, "git", "checkout", "--theirs", "--", path)
        run_git(repo_dir, "git", "add", "--", path)
    return True


def pull_rebase_with_generated_resolution(repo_dir: Path, branch: str) -> None:
    commit_auto_changes(repo_dir, f"Cambios seguros antes de pull {datetime.now():%Y-%m-%d %H:%M}")

    code, out, err = run_git(repo_dir, "git", "pull", "--rebase", "--autostash", "origin", branch)
    if code == 0:
        return

    msg0 = (out + " " + err).strip()
    if "unknown option" in msg0.lower() or "autostash" in msg0.lower():
        code, out, err = run_git(repo_dir, "git", "pull", "--rebase", "origin", branch)
        if code == 0:
            return

    print(f"  ⚠️ pull --rebase encontró un problema:\n    {(err or out).strip()}")
    for _ in range(12):
        if not resolve_generated_rebase_conflicts(repo_dir):
            raise RuntimeError(f"No se pudo sincronizar {branch}: {(err or out).strip()}")
        code, out, err = run_git(repo_dir, "git", "rebase", "--continue", env={"GIT_EDITOR": "true"})
        if code == 0:
            print("  ✅ Rebase continuado después de resolver datos generados")
            return
        msg = (out + " " + err).strip()
        if "No changes" in msg or "no changes" in msg:
            code, out, err = run_git(repo_dir, "git", "rebase", "--skip")
            if code == 0:
                return
    raise RuntimeError("No se pudo completar el rebase automáticamente.")


def warn_remote_credentials(repo_dir: Path) -> None:
    code, out, err = run_git(repo_dir, "git", "remote", "get-url", "origin")
    if code != 0:
        return
    raw = out.strip()
    if re.search(r"https://[^/@:\s]+:[^/@\s]+@", raw) or re.search(r"https://[^/@\s]+@github\.com", raw):
        print("  ⚠️ El remoto origin parece tener credenciales embebidas en la URL.")
        print("     Recomendado: usar Git Credential Manager o SSH, no tokens dentro de la URL remota.")


def ensure_default_branch(repo_dir: Path) -> str:
    print("\n── Verificando repositorio y rama remota ──────")
    cleanup_temp_files(repo_dir)
    ensure_gitignore(repo_dir)
    untrack_local_only_files(repo_dir)

    code, out, err = run_git(repo_dir, "git", "rev-parse", "--is-inside-work-tree")
    if code != 0 or out.strip().lower() != "true":
        raise RuntimeError("Esta carpeta no parece ser un repositorio Git.")

    code, top, err = run_git(repo_dir, "git", "rev-parse", "--show-toplevel")
    if code == 0:
        top_path = Path(top).resolve()
        if top_path != repo_dir.resolve():
            raise RuntimeError(
                f"El script está en {repo_dir}, pero la raíz Git es {top_path}. "
                "Coloque download_data.py y actualizar.bat en la raíz del repositorio."
            )

    warn_remote_credentials(repo_dir)

    code, out, err = run_git(repo_dir, "git", "fetch", "origin", "--prune")
    if code != 0:
        raise RuntimeError(f"No se pudo hacer git fetch origin: {(err or out).strip()}")

    default_branch = ""
    code, out, err = run_git(repo_dir, "git", "symbolic-ref", "refs/remotes/origin/HEAD")
    if code == 0 and out.strip():
        default_branch = out.strip().split("/")[-1]
    if not default_branch:
        for candidate in ("main", "master"):
            code, _, _ = run_git(repo_dir, "git", "show-ref", f"refs/remotes/origin/{candidate}")
            if code == 0:
                default_branch = candidate
                break
    if not default_branch:
        raise RuntimeError("No pude identificar la rama principal del remoto.")

    code, current_branch, err = run_git(repo_dir, "git", "branch", "--show-current")
    if code != 0:
        raise RuntimeError(f"No pude leer la rama actual: {(err or current_branch).strip()}")
    current_branch = current_branch.strip()

    print(f"  Rama local actual : {current_branch or '(detached)'}")
    print(f"  Rama remota usada : {default_branch}")

    if current_branch != default_branch:
        code, _, _ = run_git(repo_dir, "git", "show-ref", f"refs/heads/{default_branch}")
        if code == 0:
            code, out, err = run_git(repo_dir, "git", "checkout", default_branch)
        else:
            code, out, err = run_git(repo_dir, "git", "checkout", "-B", default_branch, f"origin/{default_branch}")
        if code != 0:
            raise RuntimeError(f"No se pudo cambiar a {default_branch}: {(err or out).strip()}")
        print(f"  ✅ Cambiado a la rama {default_branch}")

    commit_auto_changes(repo_dir, f"Cambios seguros antes de sincronizar {datetime.now():%Y-%m-%d %H:%M}")
    pull_rebase_with_generated_resolution(repo_dir, default_branch)
    print(f"  ✅ Rama {default_branch} sincronizada con origin/{default_branch}")
    return default_branch


# ── Descarga ───────────────────────────────────────────────────────────────
def download_bytes(url: str) -> bytes:
    validate_download_url(url)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/csv,application/zip,*/*",
    }
    req = urllib.request.Request(url, headers=headers)
    chunks, total, t0 = [], 0, time.time()
    print("  Conectando al servidor autorizado...", flush=True)
    with urllib.request.urlopen(req, timeout=TIMEOUT_CONN) as resp:
        print(f"  HTTP {resp.status}")
        print("  Descargando", end="", flush=True)
        deadline = time.time() + TIMEOUT_READ
        while True:
            if time.time() > deadline:
                raise TimeoutError(f"Timeout de lectura ({TIMEOUT_READ}s)")
            chunk = resp.read(CHUNK_SIZE)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_DOWNLOAD_BYTES:
                raise RuntimeError(f"Descarga bloqueada: supera {MAX_DOWNLOAD_BYTES / 1024 / 1024:.0f} MB")
            chunks.append(chunk)
            print(".", end="", flush=True)
    print(f" {total / 1024:.0f} KB en {time.time() - t0:.1f}s")
    return b"".join(chunks)


def decode_bytes(raw: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace")


def extract_csv_payloads(raw_bytes: bytes, fallback_name: str) -> dict[str, str]:
    results: dict[str, str] = {}
    if raw_bytes[:2] == b"PK":
        print("  Formato: ZIP ✅")
        with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
            infos = zf.infolist()
            if len(infos) > MAX_ZIP_FILES:
                raise RuntimeError(f"ZIP bloqueado: contiene demasiados archivos ({len(infos)}).")
            total_size = sum(i.file_size for i in infos)
            if total_size > MAX_ZIP_UNCOMPRESSED_BYTES:
                raise RuntimeError("ZIP bloqueado: tamaño descomprimido demasiado grande.")
            print(f"  Archivos en el ZIP ({len(infos)}):")
            for info in infos:
                name = Path(info.filename).name
                if not name.lower().endswith(".csv"):
                    print(f"    · {name} omitido: no es CSV")
                    continue
                print(f"    · {name}")
                with zf.open(info) as f:
                    results[name] = decode_bytes(f.read())
    else:
        print("  Formato: CSV/texto plano ✅")
        results[Path(fallback_name).name] = decode_bytes(raw_bytes)
    return results


# ── Identificación y normalización ─────────────────────────────────────────
def text_has_any(text: str, keywords: list[str]) -> bool:
    upper = text.upper()
    return any(k.upper() in upper for k in keywords)


def match_dataset(filename: str, content: str) -> dict | None:
    target = f"{filename}\n{content[:5000]}"
    target_upper = target.upper()

    # Buscar primero en todas las series configuradas, incluyendo las 4 series
    # de temperatura/viento que ahora se descargan individualmente.
    for meta in globals().get("ALL_SERIES_CONFIG", SERIES_CONFIG):
        specific_keywords = list(meta.get("kind_keywords", [])) + [meta["dataset"], Path(meta["out_name"]).stem]
        if text_has_any(target, specific_keywords):
            # Confirmar estación en series donde varios sensores comparten palabras similares.
            if ("Tide Height" in meta["dataset"] or "Lake-Res" in meta["dataset"]
                    or "Wind Speed" in meta["dataset"] or "Water Temp" in meta["dataset"]):
                station_token = f"@{meta['station']}".upper()
                if station_token not in target_upper and meta["station"].upper() not in target_upper:
                    continue
            return meta

    for meta in BASE_DATASET_MAP:
        if text_has_any(target, meta["keywords"]):
            return meta
    return None


def find_header_index(lines: list[str]) -> int | None:
    """Ubica la fila de encabezados del CSV exportado por Aquarius.

    Aquarius puede cambiar los títulos según el tipo de cálculo:
    - Instantaneous / PointsAsRecorded suele traer columnas de tiempo y valor.
    - Aggregate puede traer "Interval Start", "Interval End", "Value", etc.
    Por eso no se exige literalmente "timestamp"; se aceptan variantes de fecha,
    hora, inicio/fin de intervalo y valor.
    """
    time_words = ("timestamp", "sello de tiempo", "fecha", "date", "time", "hora", "interval", "inicio", "start", "end", "fin")
    value_words = ("value", "valor", "result", "resultado", "reading", "lectura", "avg", "average", "mean", "promedio")
    for i, line in enumerate(lines):
        low = line.lower()
        if any(w in low for w in time_words) and any(w in low for w in value_words):
            return i
    return None


def detect_separator(line: str) -> str:
    # Aquarius normalmente usa coma, pero algunos equipos/regiones pueden usar punto y coma.
    return ";" if line.count(";") > line.count(",") else ","


def parse_float(value: str) -> float | None:
    value = value.strip().strip('"').strip("'")
    if not value or value.lower() in {"nan", "null", "none", "--"}:
        return None
    clean = value.replace(" ", "")
    if "," in clean and "." not in clean:
        clean = clean.replace(",", ".")
    try:
        return float(clean)
    except ValueError:
        return None


def _column_score_for_time(header_name: str) -> int:
    h = header_name.strip().lower()
    score = 0
    if "timestamp" in h or "sello de tiempo" in h:
        score += 100
    if "date" in h or "fecha" in h:
        score += 80
    if "time" in h or "hora" in h:
        score += 60
    if "interval start" in h or "start time" in h or "inicio" in h:
        score += 70
    if "interval" in h:
        score += 20
    if h in {"time", "date time", "datetime", "fecha", "fecha/hora"}:
        score += 50
    return score


def _column_score_for_value(header_name: str) -> int:
    h = header_name.strip().lower()
    score = 0
    if h in {"value", "valor"}:
        score += 100
    if "value" in h or "valor" in h:
        score += 90
    if "reading" in h or "lectura" in h or "result" in h or "resultado" in h:
        score += 70
    if "avg" in h or "average" in h or "mean" in h or "promedio" in h:
        score += 40
    # Evita escoger columnas de calidad/aprobación como si fueran valores.
    if any(bad in h for bad in ("grade", "quality", "approval", "qualifier", "nota", "note", "interpolation")):
        score -= 100
    return score


def normalize_csv(text: str) -> str:
    raw_lines = [line.rstrip("\r") for line in text.splitlines() if line.strip()]
    header_idx = find_header_index(raw_lines)
    if header_idx is None:
        return ""

    data_lines = raw_lines[header_idx:]
    sep = detect_separator(data_lines[0])
    reader = csv.reader(data_lines, delimiter=sep)

    try:
        header = next(reader)
    except StopIteration:
        return ""

    header_clean = [h.strip().strip('"').strip("'") for h in header]

    # Selección robusta de columna de tiempo.
    time_scores = [(_column_score_for_time(h), i) for i, h in enumerate(header_clean)]
    time_scores.sort(reverse=True)
    ts_idx = time_scores[0][1] if time_scores and time_scores[0][0] > 0 else 0

    # Selección robusta de columna de valor.
    value_scores = [(_column_score_for_value(h), i) for i, h in enumerate(header_clean)]
    value_scores.sort(reverse=True)
    val_idx = value_scores[0][1] if value_scores and value_scores[0][0] > 0 else (1 if len(header_clean) > 1 else 0)

    # Si por alguna razón coincide con la columna de tiempo, buscar la primera columna numérica distinta.
    rows = []
    sample_rows = []
    for row in reader:
        sample_rows.append(row)
        if len(sample_rows) >= 50:
            break

    if val_idx == ts_idx:
        best_numeric = None
        best_count = -1
        for i in range(len(header_clean)):
            if i == ts_idx:
                continue
            count = 0
            for row in sample_rows:
                if len(row) > i and parse_float(row[i]) is not None:
                    count += 1
            if count > best_count:
                best_count = count
                best_numeric = i
        if best_numeric is not None:
            val_idx = best_numeric

    def add_row(row: list[str]) -> None:
        if len(row) <= max(ts_idx, val_idx):
            return
        timestamp = row[ts_idx].strip().strip('"').strip("'")
        value_raw = row[val_idx].strip().strip('"').strip("'")
        value = parse_float(value_raw)
        if not timestamp or value is None:
            return

        # Evita fórmulas si alguien abre el CSV en Excel.
        safe_timestamp = timestamp.replace("\n", " ").replace("\r", " ").replace("\t", " ").strip()
        if safe_timestamp[:1] in {"=", "+", "-", "@"}:
            return
        rows.append((safe_timestamp, safe_timestamp, value))

    for row in sample_rows:
        add_row(row)
    for row in reader:
        add_row(row)

    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["fecha_inicio", "fecha_fin", "valor_raw"])
    writer.writerows(rows)
    return output.getvalue().strip()


def save_and_summarize(csv_map: dict[str, str], output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    if output_dir.resolve().parent != REPO_DIR.resolve():
        raise RuntimeError("La carpeta data debe estar directamente dentro del repositorio.")

    for legacy_name in ("Discharge_ATotal_ALHA_tst.csv",):
        legacy = output_dir / legacy_name
        if legacy.exists():
            legacy.unlink()
            print(f"  🧹 Archivo anterior eliminado: {legacy.name}")

    saved: list[Path] = []
    seen_names: set[str] = set()
    skipped_empty: dict[str, int] = {}

    for filename, content in csv_map.items():
        meta = match_dataset(filename, content)
        if meta is None:
            # Se omite sin ruido para evitar alertas falsas por CSVs no relacionados.
            continue

        norm = normalize_csv(content)
        out_name = Path(meta["out_name"]).name
        if out_name not in EXPECTED_DATA_FILES:
            raise RuntimeError(f"Nombre de salida no autorizado: {out_name}")

        if not norm or norm.count("\n") < 1:
            skipped_empty[meta["label"]] = skipped_empty.get(meta["label"], 0) + 1
            continue

        path = output_dir / out_name
        if path.resolve().parent != output_dir.resolve():
            raise RuntimeError(f"Ruta de salida insegura: {path}")

        atomic_write_text(path, norm + "\n")
        n = norm.count("\n")
        print(f"  ✅ {meta['label']}: {n} registros → {out_name}")
        saved.append(path)
        seen_names.add(out_name)

    for label, count in sorted(skipped_empty.items()):
        if count:
            print(f"  ℹ️ {label}: {count} archivo(s) sin datos válidos omitidos; se usó el archivo válido si aparece arriba.")

    missing = [m["out_name"] for m in SERIES_CONFIG if m["out_name"] not in seen_names]
    if missing:
        print("\n  ⚠️ Series configuradas que no se guardaron en esta corrida:")
        for name in missing:
            print(f"    · {name}")

    return saved


def clean_legacy_data_files(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for legacy_name in ("Discharge_ATotal_ALHA_tst.csv",):
        legacy = output_dir / legacy_name
        if legacy.exists():
            legacy.unlink()
            print(f"  🧹 Archivo anterior eliminado: {legacy.name}")


def choose_best_payload_for_series(series: dict, csv_map: dict[str, str]) -> tuple[str, str]:
    """Escoge el CSV descargado para una serie individual.

    Como cada consulta usa un solo Datasets[0], si Aquarius cambia el nombre
    del archivo dentro del ZIP, no dependemos únicamente del nombre. Se intenta
    confirmar por palabras clave y, si no hay coincidencia explícita, se usa el
    primer CSV con datos válidos de esa descarga individual.
    """
    candidates: list[tuple[int, str, str]] = []
    keywords = list(series.get("kind_keywords", [])) + [series["dataset"], Path(series["out_name"]).stem]

    for filename, content in csv_map.items():
        norm = normalize_csv(content)
        if not norm or norm.count("\n") < 1:
            continue

        target = f"{filename}\n{content[:5000]}"
        matched = match_dataset(filename, content)
        score = 10
        if matched and matched.get("out_name") == series["out_name"]:
            score = 100
        elif text_has_any(target, keywords):
            score = 80

        candidates.append((score, filename, norm))

    if not candidates:
        raise RuntimeError("Aquarius respondió, pero no se encontró un CSV con filas válidas para normalizar.")

    candidates.sort(key=lambda item: item[0], reverse=True)
    score, filename, norm = candidates[0]
    return filename, norm


def save_single_series(series: dict, csv_map: dict[str, str], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    if output_dir.resolve().parent != REPO_DIR.resolve():
        raise RuntimeError("La carpeta data debe estar directamente dentro del repositorio.")

    out_name = Path(series["out_name"]).name
    if out_name not in EXPECTED_DATA_FILES:
        raise RuntimeError(f"Nombre de salida no autorizado: {out_name}")

    source_name, norm = choose_best_payload_for_series(series, csv_map)
    path = output_dir / out_name
    if path.resolve().parent != output_dir.resolve():
        raise RuntimeError(f"Ruta de salida insegura: {path}")

    atomic_write_text(path, norm + "\n")
    records = norm.count("\n")
    print(f"  ✅ {series['label']}: {records} registros → {out_name}")
    print(f"     Fuente Aquarius: {source_name}")
    return path


def verify_expected_outputs(saved: list[Path]) -> None:
    saved_names = {p.name for p in saved}
    expected_names = {m["out_name"] for m in ALL_SERIES_CONFIG}
    missing = sorted(expected_names - saved_names)
    if missing:
        raise RuntimeError(
            "No se actualizaron todas las series requeridas. Faltan: " + ", ".join(missing)
        )

    print("\n── Verificación de archivos actualizados ──────")
    for meta in ALL_SERIES_CONFIG:
        path = OUTPUT_DIR / meta["out_name"]
        if not path.exists():
            raise RuntimeError(f"No existe el archivo esperado: {path.name}")
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        print(f"  ✅ {path.name:<40} modificado {mtime:%Y-%m-%d %H:%M:%S}")



def print_summary(saved: list[Path]) -> None:
    print("\n── Resumen de archivos normalizados ───────────")
    for path in saved:
        try:
            df = pd.read_csv(path)
            df["fecha_inicio_dt"] = pd.to_datetime(df["fecha_inicio"], errors="coerce")
            first = df["fecha_inicio_dt"].min()
            last = df["fecha_inicio_dt"].max()
            n = df["valor_raw"].notna().sum()
            if pd.isna(first) or pd.isna(last):
                print(f"  {path.name:<40} {n:>8} registros")
            else:
                print(f"  {path.name:<40} {n:>8} registros  {first:%Y-%m-%d} → {last:%Y-%m-%d %H:%M}")
        except Exception as e:
            print(f"  {path.name}: error leyendo resumen ({sanitize_text(str(e))})")


# ── Git push ───────────────────────────────────────────────────────────────
def git_push(repo_dir: Path, branch: str) -> bool:
    print("\n── Subiendo a GitHub ──────────────────────────")
    try:
        commit_auto_changes(repo_dir, f"Actualiza series de tiempo {datetime.now():%Y-%m-%d %H:%M}")
    except Exception as e:
        print(f"  ❌ git commit bloqueado: {sanitize_text(str(e))}")
        return False

    code, out, err = run_git(repo_dir, "git", "push", "origin", branch)
    if code != 0:
        print(f"  ⚠️ git push falló inicialmente:\n    {err or out}")
        print("  → Intentando pull --rebase y nuevo push...")
        try:
            pull_rebase_with_generated_resolution(repo_dir, branch)
        except Exception as e:
            print(f"  ❌ No se pudo sincronizar automáticamente: {sanitize_text(str(e))}")
            return False
        code, out, err = run_git(repo_dir, "git", "push", "origin", branch)
        if code != 0:
            print(f"  ❌ git push falló:\n    {err or out}")
            print("  → Revise permisos, Git Credential Manager, token/SSH o protección de rama.")
            return False

    print(f"  ✅ git push OK hacia origin/{branch}")
    print("  Streamlit Cloud debería detectar el cambio del repositorio.")
    return True


def main() -> None:
    print("=" * 60)
    print("  Descarga segura de series de tiempo — Aquarius / GitHub")
    print(f"  {datetime.now():%Y-%m-%d %H:%M:%S}")
    print("=" * 60)

    try:
        branch = ensure_default_branch(REPO_DIR)
    except Exception as e:
        print(f"\n❌ Error de Git/seguridad: {sanitize_text(str(e))}")
        sys.exit(1)

    clean_legacy_data_files(OUTPUT_DIR)
    saved: list[Path] = []
    failures: list[str] = []

    print(f"\n[1/4] Descargando y guardando {len(ALL_SERIES_CONFIG)} series individuales desde Aquarius...")
    for idx, series in enumerate(ALL_SERIES_CONFIG, start=1):
        print(f"\n  Serie {idx}/{len(ALL_SERIES_CONFIG)}: {series['label']}")
        try:
            raw = download_bytes(build_series_url(series))
            payloads = extract_csv_payloads(raw, series["out_name"])
            saved_path = save_single_series(series, payloads, OUTPUT_DIR)
            saved.append(saved_path)
        except Exception as e:
            msg = sanitize_text(str(e))
            failures.append(f"{series['out_name']}: {msg}")
            print(f"  ❌ No se pudo actualizar {series['label']}: {msg}")

    print(f"\n[2/4] Verificando que todos los CSV requeridos se hayan actualizado en: {OUTPUT_DIR}")
    try:
        verify_expected_outputs(saved)
    except Exception as e:
        print(f"\n❌ {sanitize_text(str(e))}")

    if failures:
        print("\n❌ Fallaron una o más series. No se hará commit ni push para evitar subir datos incompletos:")
        for item in failures:
            print(f"    · {item}")
        sys.exit(1)

    if len({p.name for p in saved}) != len(ALL_SERIES_CONFIG):
        print("\n❌ No se actualizaron todas las series requeridas. No se hará commit ni push.")
        sys.exit(1)

    print("\n[3/4] Resumen de archivos normalizados...")
    print_summary(saved)

    print("\n[4/4] Commit y push seguro al repositorio...")
    ok = git_push(REPO_DIR, branch)
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
