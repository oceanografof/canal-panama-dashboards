"""
download_data.py — Descarga series de tiempo de Aquatic Informatics, las normaliza,
las guarda en /data/ y sube automáticamente los archivos nuevos o modificados al repositorio.

Corre desde tu PC dentro de la red ACP:
    python download_data.py
"""
from __future__ import annotations

import csv
import io
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

import pandas as pd

# ── Configuración general ──────────────────────────────────────────────────
REPO_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = REPO_DIR / "data"

# Para las series nuevas de tiempo: últimos 6 meses, puntos como fueron registrados.
TIME_SERIES_DATE_RANGE = "Months6"
TIME_ZONE = "-5"
CALENDAR = "CALENDARYEAR"

TIMEOUT_CONN = 300
TIMEOUT_READ = 900
CHUNK_SIZE = 65536

# Archivos/carpetas que se suben automáticamente al repo.
AUTO_ADD_TARGETS = [
    "data/",
    "LakeHouse_Data.xlsx",
    "download_data.py",
    "actualizar.bat",
    "requirements.txt",
    ".gitignore",
]

# En conflictos de rebase/pull se conserva la versión local para datos generados.
PREFER_LOCAL_PATTERNS = (
    "LakeHouse_Data.xlsx",
    "data/",
    "download_data.py",
    "actualizar.bat",
)

# ── Series a descargar ─────────────────────────────────────────────────────
# Nota: UnitId se mantiene según lo observado en los enlaces/archivos de Aquarius.
# Los nombres de salida quedan fijos en /data/ para que la app los pueda leer siempre igual.
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
        "kind_keywords": ["Lake-Res elevation.Telem AVG", "Lake-Res", "elevation.Telem"],
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
]

# Series meteorológicas/temperatura existentes en el script anterior. Se dejan activas.
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


def build_series_url(series: dict) -> str:
    params = {
        "DateRange": TIME_SERIES_DATE_RANGE,
        "TimeZone": TIME_ZONE,
        "Calendar": CALENDAR,
        "Interval": series.get("interval", "PointsAsRecorded"),
        "Step": "1",
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
    return "https://panama.aquaticinformatics.net/Export/BulkExport?" + urlencode(params)


def run_git(repo_dir: Path, *cmd: str, env: dict | None = None) -> tuple[int, str, str]:
    full_env = os.environ.copy()
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
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def cleanup_temp_files(repo_dir: Path) -> None:
    for pycache in repo_dir.rglob("__pycache__"):
        shutil.rmtree(pycache, ignore_errors=True)
    for pyc in repo_dir.rglob("*.pyc"):
        try:
            pyc.unlink()
        except OSError:
            pass


def ensure_gitignore(repo_dir: Path) -> None:
    gitignore = repo_dir / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8", errors="replace") if gitignore.exists() else ""
    lines = existing.splitlines()
    stripped = [line.strip() for line in lines]
    changed = False

    for rule in ("__pycache__/", "*.pyc"):
        if rule not in stripped:
            lines.append(rule)
            changed = True

    # Si estaba bloqueando data/ o CSV, se quita para poder subir las series.
    block_rules = {"*.csv", "data/", "/data/", "data/*"}
    filtered = [line for line in lines if line.strip() not in block_rules]
    if filtered != lines:
        lines = filtered
        changed = True
        print("  ✅ .gitignore ajustado: data/ y CSV quedan disponibles para subir")

    if changed:
        gitignore.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def git_add_existing(repo_dir: Path, targets: list[str] | tuple[str, ...] = AUTO_ADD_TARGETS) -> None:
    """
    Agrega al commit todos los archivos nuevos/modificados.

    Primero usa git add -A para que no queden cambios locales sin preparar
    que bloqueen git pull --rebase. Luego fuerza los targets importantes
    como data/ por si alguna regla de .gitignore los estuviera ignorando.
    """
    run_git(repo_dir, "git", "add", "-A")
    for target in targets:
        p = repo_dir / target.rstrip("/")
        if p.exists():
            run_git(repo_dir, "git", "add", "-f", "--", target)


def git_status_short(repo_dir: Path) -> str:
    code, out, err = run_git(repo_dir, "git", "status", "--short")
    return out.strip() if code == 0 else (err or out).strip()


def commit_auto_changes(repo_dir: Path, message: str) -> bool:
    cleanup_temp_files(repo_dir)
    ensure_gitignore(repo_dir)
    git_add_existing(repo_dir)

    status = git_status_short(repo_dir)
    if not status:
        print("  Sin cambios para commit.")
        return False

    print("  Cambios detectados:")
    for line in status.splitlines():
        print(f"    {line}")

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
    for line in status.splitlines():
        if len(line) < 4:
            continue
        xy = line[:2]
        path = line[3:].strip()
        if any(c in xy for c in ("U", "A", "D")) and is_prefer_local_path(path):
            conflicted.append(path)

    if not conflicted:
        return False

    print("  ⚠️ Conflicto en archivos generados. Se conserva la versión local:")
    for path in conflicted:
        print(f"    · {path}")
        run_git(repo_dir, "git", "checkout", "--theirs", "--", path)
        run_git(repo_dir, "git", "add", "--", path)
    return True


def pull_rebase_with_generated_resolution(repo_dir: Path, branch: str) -> None:
    # Debe estar limpio antes del pull. Si quedó algo local por cualquier motivo,
    # se guarda en commit automático para evitar: "cannot pull with rebase: unstaged changes".
    commit_auto_changes(repo_dir, f"Cambios locales antes de pull {datetime.now():%Y-%m-%d %H:%M}")

    code, out, err = run_git(repo_dir, "git", "pull", "--rebase", "--autostash", "origin", branch)
    if code == 0:
        return

    # Compatibilidad: versiones antiguas de Git pueden no soportar --autostash en pull.
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
            print("  ✅ Rebase continuado después de resolver archivos generados")
            return
        msg = (out + " " + err).strip()
        if "No changes" in msg or "no changes" in msg:
            code, out, err = run_git(repo_dir, "git", "rebase", "--skip")
            if code == 0:
                return
    raise RuntimeError("No se pudo completar el rebase automáticamente.")


def ensure_default_branch(repo_dir: Path) -> str:
    print("\n── Verificando rama remota ───────────────────")
    cleanup_temp_files(repo_dir)
    ensure_gitignore(repo_dir)

    code, out, err = run_git(repo_dir, "git", "rev-parse", "--is-inside-work-tree")
    if code != 0 or out.strip().lower() != "true":
        raise RuntimeError("Esta carpeta no parece ser un repositorio Git.")

    code, out, err = run_git(repo_dir, "git", "fetch", "origin")
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

    commit_auto_changes(repo_dir, f"Cambios locales antes de sincronizar {datetime.now():%Y-%m-%d %H:%M}")
    pull_rebase_with_generated_resolution(repo_dir, default_branch)
    print(f"  ✅ Rama {default_branch} sincronizada con origin/{default_branch}")
    return default_branch


# ── Descarga ───────────────────────────────────────────────────────────────
def download_bytes(url: str) -> bytes:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "*/*",
    }
    req = urllib.request.Request(url, headers=headers)
    chunks, total, t0 = [], 0, time.time()
    print("  Conectando...", flush=True)
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
            chunks.append(chunk)
            total += len(chunk)
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
    """Acepta ZIP de Aquarius o CSV plano."""
    results: dict[str, str] = {}
    if raw_bytes[:2] == b"PK":
        print("  Formato: ZIP ✅")
        with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
            names = zf.namelist()
            print(f"  Archivos en el ZIP ({len(names)}):")
            for name in names:
                print(f"    · {name}")
                with zf.open(name) as f:
                    results[name] = decode_bytes(f.read())
    else:
        print("  Formato: CSV/texto plano ✅")
        results[fallback_name] = decode_bytes(raw_bytes)
    return results


# ── Identificación y normalización ─────────────────────────────────────────
def text_has_any(text: str, keywords: list[str]) -> bool:
    upper = text.upper()
    return any(k.upper() in upper for k in keywords)


def match_dataset(filename: str, content: str) -> dict | None:
    target = f"{filename}\n{content[:3000]}"
    target_upper = target.upper()

    for meta in SERIES_CONFIG:
        # Primero exige el nombre de dataset o una palabra clave específica.
        # No basta con la estación, porque GAT y ALHA comparten TstCHCP_AT.
        specific_keywords = list(meta.get("kind_keywords", [])) + [meta["dataset"]]
        if text_has_any(target, specific_keywords):
            # Para mareógrafos se confirma también la estación correcta.
            if "Tide Height" in meta["dataset"]:
                if meta["station"].upper() not in target_upper:
                    continue
            return meta

    for meta in BASE_DATASET_MAP:
        if text_has_any(target, meta["keywords"]):
            return meta
    return None


def find_header_index(lines: list[str]) -> int | None:
    for i, line in enumerate(lines):
        low = line.lower()
        if (
            ("timestamp" in low or "sello de tiempo" in low or "fecha" in low or "time" in low)
            and ("value" in low or "valor" in low)
        ):
            return i
    return None


def detect_separator(line: str) -> str:
    return ";" if line.count(";") > line.count(",") else ","


def parse_float(value: str) -> float | None:
    value = value.strip().strip('"').strip("'")
    if not value or value.lower() in {"nan", "null", "none", "--"}:
        return None
    # Maneja decimales con coma cuando no hay punto decimal.
    clean = value.replace(" ", "")
    if "," in clean and "." not in clean:
        clean = clean.replace(",", ".")
    try:
        return float(clean)
    except ValueError:
        return None


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

    header_low = [h.strip().lower() for h in header]
    ts_idx = next((i for i, h in enumerate(header_low) if "timestamp" in h or "sello de tiempo" in h or "fecha" in h or "time" in h), 0)
    val_idx = next((i for i, h in enumerate(header_low) if "value" in h or "valor" in h), 1 if len(header) > 1 else 0)

    rows = []
    for row in reader:
        if len(row) <= max(ts_idx, val_idx):
            continue
        timestamp = row[ts_idx].strip().strip('"').strip("'")
        value_raw = row[val_idx].strip().strip('"').strip("'")
        value = parse_float(value_raw)
        if not timestamp or value is None:
            continue
        rows.append((timestamp, timestamp, value))

    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["fecha_inicio", "fecha_fin", "valor_raw"])
    writer.writerows(rows)
    return output.getvalue().strip()


def save_and_summarize(csv_map: dict[str, str], output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)

    # Limpieza de nombres viejos/incorrectos para no confundir la app.
    for legacy_name in ("Discharge_ATotal_ALHA_tst.csv",):
        legacy = output_dir / legacy_name
        if legacy.exists():
            legacy.unlink()
            print(f"  🧹 Archivo anterior eliminado: {legacy.name}")

    saved: list[Path] = []
    seen_names: set[str] = set()

    for filename, content in csv_map.items():
        meta = match_dataset(filename, content)
        if meta is None:
            print(f"  ⚠️ No se reconoció la serie: {filename}")
            continue

        norm = normalize_csv(content)
        if not norm or norm.count("\n") < 1:
            print(f"  ⚠️ {meta['label']}: sin datos válidos.")
            continue

        out_name = meta["out_name"]
        path = output_dir / out_name
        path.write_text(norm + "\n", encoding="utf-8")
        n = norm.count("\n")
        print(f"  ✅ {meta['label']}: {n} registros → {out_name}")
        saved.append(path)
        seen_names.add(out_name)

    missing = [m["out_name"] for m in SERIES_CONFIG if m["out_name"] not in seen_names]
    if missing:
        print("\n  ⚠️ Series configuradas que no se guardaron en esta corrida:")
        for name in missing:
            print(f"    · {name}")

    return saved


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
            print(f"  {path.name}: error leyendo resumen ({e})")


# ── Git push ───────────────────────────────────────────────────────────────
def git_push(repo_dir: Path, branch: str) -> bool:
    print("\n── Subiendo a GitHub ──────────────────────────")
    try:
        commit_auto_changes(repo_dir, f"Actualiza series de tiempo {datetime.now():%Y-%m-%d %H:%M}")
    except Exception as e:
        print(f"  ❌ git commit falló: {e}")
        return False

    code, out, err = run_git(repo_dir, "git", "push", "origin", branch)
    if code != 0:
        print(f"  ⚠️ git push falló inicialmente:\n    {err or out}")
        print("  → Intentando pull --rebase y nuevo push...")
        try:
            pull_rebase_with_generated_resolution(repo_dir, branch)
        except Exception as e:
            print(f"  ❌ No se pudo sincronizar automáticamente: {e}")
            return False
        code, out, err = run_git(repo_dir, "git", "push", "origin", branch)
        if code != 0:
            print(f"  ❌ git push falló:\n    {err or out}")
            print("  → Revise token de GitHub, permisos o protección de rama.")
            return False

    print(f"  ✅ git push OK hacia origin/{branch}")
    print("  Streamlit Cloud debería detectar el cambio del repositorio.")
    return True


def main() -> None:
    print("=" * 60)
    print("  Descarga de series de tiempo — Aquatic Informatics / ACP")
    print(f"  {datetime.now():%Y-%m-%d %H:%M:%S}")
    print("=" * 60)

    try:
        branch = ensure_default_branch(REPO_DIR)
    except Exception as e:
        print(f"\n❌ Error de Git: {e}")
        sys.exit(1)

    csv_map: dict[str, str] = {}

    print("\n[1/4] Descargando BulkExport base de temperatura/viento...")
    try:
        raw = download_bytes(BASE_BULK_URL)
        csv_map.update(extract_csv_payloads(raw, "base_temp_wind.csv"))
    except Exception as e:
        print(f"  ⚠️ No se pudo descargar el BulkExport base: {e}")

    print("\n[2/4] Descargando series de tiempo solicitadas...")
    for idx, series in enumerate(SERIES_CONFIG, start=1):
        print(f"\n  Serie {idx}/{len(SERIES_CONFIG)}: {series['label']}")
        try:
            raw = download_bytes(build_series_url(series))
            csv_map.update(extract_csv_payloads(raw, series["out_name"]))
        except Exception as e:
            print(f"  ⚠️ No se pudo descargar {series['label']}: {e}")

    print(f"\n[3/4] Normalizando y guardando en: {OUTPUT_DIR}")
    saved = save_and_summarize(csv_map, OUTPUT_DIR)
    if not saved:
        print("\n❌ No se guardó ningún archivo. Revise conexión/VPN o nombres de datasets.")
        sys.exit(1)
    print_summary(saved)

    print("\n[4/4] Commit y push al repositorio...")
    ok = git_push(REPO_DIR, branch)
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
