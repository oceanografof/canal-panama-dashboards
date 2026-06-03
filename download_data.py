"""
download_data.py — Descarga datos de Aquatic Informatics, los guarda en /data/,
sube LakeHouse_Data.xlsx cuando cambie y sincroniza GitHub sin conflictos comunes.

Corre desde tu PC dentro de la red ACP:
    python download_data.py
"""
from __future__ import annotations
import io, sys, time, zipfile, subprocess, urllib.request, shutil, os
from datetime import datetime
from pathlib import Path
import pandas as pd

# ── Configuración ──────────────────────────────────────────────────────────
OUTPUT_DIR   = Path(__file__).resolve().parent / "data"
REPO_DIR     = Path(__file__).resolve().parent
DATE_RANGE   = "Custom&Period=P90D"        # últimos 90 días (rápido)
# DATE_RANGE = "EntirePeriodOfRecord"      # histórico completo (lento)

BASE_URL = (
    "https://panama.aquaticinformatics.net/Export/BulkExport"
    f"?DateRange={DATE_RANGE}"
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

# Series adicionales solicitadas. Se mantienen como BulkExport separados para respetar
# sus parámetros originales: Months6, PointsAsRecorded, TimeAligned=True y unidades.
EXTRA_URLS = [
    (
        "https://panama.aquaticinformatics.net/Export/BulkExport"
        "?DateRange=Months6&TimeZone=-5&Calendar=CALENDARYEAR"
        "&Interval=PointsAsRecorded&Step=1&ExportFormat=csv&TimeAligned=True"
        "&RoundData=True&IncludeGradeCodes=undefined&IncludeApprovalLevels=undefined"
        "&IncludeQualifiers=undefined&IncludeInterpolationTypes=False&IncludeNotes=undefined"
        "&Datasets%5B0%5D.DatasetName=Discharge.AT_GAT_Diario%40TstCHCP_AT"
        "&Datasets%5B0%5D.Calculation=Instantaneous&Datasets%5B0%5D.UnitId=218"
        "&_=1780498979073"
    ),
    (
        "https://panama.aquaticinformatics.net/Export/BulkExport"
        "?DateRange=Months6&TimeZone=-5&Calendar=CALENDARYEAR"
        "&Interval=PointsAsRecorded&Step=1&ExportFormat=csv&TimeAligned=True"
        "&RoundData=True&IncludeGradeCodes=undefined&IncludeApprovalLevels=undefined"
        "&IncludeQualifiers=undefined&IncludeInterpolationTypes=False&IncludeNotes=undefined"
        "&Datasets%5B0%5D.DatasetName=Discharge.AT_ALHA_Diario%40TstCHCP_AT"
        "&Datasets%5B0%5D.Calculation=Instantaneous&Datasets%5B0%5D.UnitId=218"
        "&_=1780512828046"
    ),
    (
        "https://panama.aquaticinformatics.net/Export/BulkExport"
        "?DateRange=Months6&TimeZone=-5&Calendar=CALENDARYEAR"
        "&Interval=PointsAsRecorded&Step=1&ExportFormat=csv&TimeAligned=True"
        "&RoundData=True&IncludeGradeCodes=undefined&IncludeApprovalLevels=undefined"
        "&IncludeQualifiers=undefined&IncludeInterpolationTypes=False&IncludeNotes=undefined"
        "&Datasets%5B0%5D.DatasetName=Lake-Res%20elevation.Telem%20AVG%40GAT"
        "&Datasets%5B0%5D.Calculation=Instantaneous&Datasets%5B0%5D.UnitId=70"
        "&_=1780499075754"
    ),
]

DOWNLOAD_URLS = [BASE_URL] + EXTRA_URLS

DATASET_MAP = [
    {"keywords": ["LAN WT AVG","LAN_WT"],  "name": "LAN_WT_AVG_AMA",     "label": "Temp LAN WT AVG @ AMA"},
    {"keywords": ["Telemetria","TEMP@AMA"],"name": "Telemetria_TEMP_AMA", "label": "Temp Telemetría @ AMA"},
    {"keywords": ["WS AVG@LMB","WS_AVG"],  "name": "WS_AVG_LMB",         "label": "Viento WS AVG @ LMB"},
    {"keywords": ["LAN WS AVG","LAN_WS"],  "name": "LAN_WS_AVG_FLC",     "label": "Viento LAN WS AVG @ FLC"},
    {"keywords": ["AT_GAT_Diario", "AT_GAT_DIARIO", "AT GAT Diario"], "name": "Discharge_AT_GAT_Diario", "label": "Caudal AT GAT Diario @ TstCHCP_AT"},
    {"keywords": ["AT_ALHA_Diario", "AT_ALHA_DIARIO", "AT ALHA Diario"], "name": "Discharge_AT_ALHA_Diario", "label": "Caudal AT ALHA Diario @ TstCHCP_AT"},
    {"keywords": ["Lake-Res", "Lake_Res", "Lake Res", "Lake-Res elevation", "elevation.Telem", "elevation_Telem", "Telem AVG@GAT", "Telem_AVG@GAT"], "name": "Lake_Res_elevation_Telem_AVG_GAT", "label": "Nivel Lake-Res Telem AVG @ GAT"},
]

TIMEOUT_CONN = 300
TIMEOUT_READ = 600
CHUNK_SIZE   = 65536

# Archivos que el proceso puede subir automáticamente.
# Incluye LakeHouse_Data.xlsx para que se actualice en GitHub/Streamlit cuando cambie.
AUTO_ADD_TARGETS = [
    "data/",
    "LakeHouse_Data.xlsx",
    "download_data.py",
    "actualizar.bat",
    "requirements.txt",
    ".gitignore",
]

# En conflictos durante rebase, estos archivos se consideran generados/locales;
# se conserva la versión local más reciente.
PREFER_LOCAL_PATTERNS = ("LakeHouse_Data.xlsx", "data/")


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
    """Elimina archivos temporales que no deben bloquear git pull/rebase."""
    pycache = repo_dir / "__pycache__"
    if pycache.exists():
        shutil.rmtree(pycache, ignore_errors=True)
        print("  ✅ __pycache__/ eliminado")


def ensure_gitignore_temp(repo_dir: Path) -> None:
    """Evita que __pycache__ y .pyc vuelvan a aparecer como archivos sin seguimiento."""
    gitignore = repo_dir / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8", errors="replace") if gitignore.exists() else ""
    lines = existing.splitlines()
    changed = False
    for rule in ("__pycache__/", "*.pyc"):
        if rule not in [line.strip() for line in lines]:
            lines.append(rule)
            changed = True
    if changed:
        gitignore.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        print("  ✅ .gitignore actualizado para temporales Python")


def git_add_existing(repo_dir: Path, targets: list[str] | tuple[str, ...] = AUTO_ADD_TARGETS) -> None:
    """Agrega al índice solo los archivos/carpetas existentes. Usa -f para datos aunque .gitignore los bloquee."""
    for target in targets:
        clean = target.rstrip("/")
        p = repo_dir / clean
        if p.exists():
            # -f permite agregar LakeHouse_Data.xlsx o data/ aunque alguna regla del .gitignore los ignore.
            run_git(repo_dir, "git", "add", "-f", "--", target)


def git_status_short(repo_dir: Path) -> str:
    code, out, err = run_git(repo_dir, "git", "status", "--short")
    if code != 0:
        return (err or out).strip()
    return out.strip()


def commit_auto_changes(repo_dir: Path, message: str) -> bool:
    """Hace commit de LakeHouse/data/scripts si hay cambios. No falla cuando no hay cambios."""
    cleanup_temp_files(repo_dir)
    ensure_gitignore_temp(repo_dir)
    git_add_existing(repo_dir)

    status = git_status_short(repo_dir)
    if not status:
        return False

    print("  Cambios para commit automático:")
    for line in status.splitlines():
        print(f"    {line}")

    code, out, err = run_git(repo_dir, "git", "commit", "-m", message)
    if code != 0:
        full_msg = (out + " " + err).strip()
        if "nothing to commit" in full_msg or "nada para hacer commit" in full_msg:
            return False
        raise RuntimeError(f"git commit falló: {full_msg}")
    print(f"  ✅ git commit OK: '{message}'")
    return True


def is_prefer_local_path(path: str) -> bool:
    path = path.replace("\\", "/")
    return any(path == pat.rstrip("/") or path.startswith(pat) for pat in PREFER_LOCAL_PATTERNS)


def resolve_generated_rebase_conflicts(repo_dir: Path) -> bool:
    """Resuelve conflictos de archivos generados conservando la versión local durante rebase."""
    status = git_status_short(repo_dir)
    if not status:
        return False

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

    print("  ⚠️  Conflicto detectado en archivos generados. Se conservará la versión local:")
    for path in conflicted:
        print(f"    · {path}")
        # Durante rebase, --theirs corresponde al commit local que se está reaplicando.
        run_git(repo_dir, "git", "checkout", "--theirs", "--", path)
        run_git(repo_dir, "git", "add", "--", path)
    return True


def pull_rebase_with_generated_resolution(repo_dir: Path, branch: str) -> None:
    """Ejecuta pull --rebase y resuelve automáticamente conflictos de LakeHouse/data."""
    code, out, err = run_git(repo_dir, "git", "pull", "--rebase", "origin", branch)
    if code == 0:
        return

    print(f"  ⚠️  pull --rebase encontró un problema:\n    {(err or out).strip()}")

    for _ in range(10):
        if not resolve_generated_rebase_conflicts(repo_dir):
            raise RuntimeError(f"No se pudo sincronizar {branch}: {(err or out).strip()}")

        code, out, err = run_git(
            repo_dir, "git", "rebase", "--continue", env={"GIT_EDITOR": "true"}
        )
        if code == 0:
            print("  ✅ Rebase continuado después de resolver archivos generados")
            return

        msg = (out + " " + err).strip()
        if "No changes" in msg or "no changes" in msg:
            code, out, err = run_git(repo_dir, "git", "rebase", "--skip")
            if code == 0:
                return
        # Puede haber otro conflicto generado en el siguiente commit; el loop lo atiende.

    raise RuntimeError("No se pudo completar el rebase después de varios intentos.")


def ensure_default_branch(repo_dir: Path) -> str:
    """Sincroniza con la rama principal y evita conflictos por LakeHouse_Data.xlsx sin guardar."""
    print("\n── Verificando rama remota ───────────────────")

    cleanup_temp_files(repo_dir)
    ensure_gitignore_temp(repo_dir)

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
        raise RuntimeError("No pude identificar la rama principal del remoto (main/master).")

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
            raise RuntimeError(f"No se pudo cambiar a la rama {default_branch}: {(err or out).strip()}")
        print(f"  ✅ Cambiado a la rama {default_branch}")

    # Si LakeHouse_Data.xlsx o data/ quedaron modificados de una corrida previa,
    # se guardan primero para que git pull --rebase no falle por cambios sin staged.
    commit_auto_changes(
        repo_dir,
        f"Actualiza LakeHouse/data antes de sincronizar {datetime.now().strftime('%Y-%m-%d %H:%M')}",
    )

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
                raise TimeoutError(f"Timeout ({TIMEOUT_READ}s)")
            chunk = resp.read(CHUNK_SIZE)
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            print(".", end="", flush=True)
    print(f" {total/1024:.0f} KB en {time.time()-t0:.1f}s")
    return b"".join(chunks)


# ── Extraer CSVs del ZIP ───────────────────────────────────────────────────
def extract_csvs_from_zip(raw_bytes: bytes) -> dict[str, str]:
    results = {}
    with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
        names = zf.namelist()
        print(f"\n  Archivos en el ZIP ({len(names)}):")
        for name in names:
            print(f"    · {name}")
            with zf.open(name) as f:
                raw = f.read()
                for enc in ["utf-8-sig", "utf-8", "latin-1", "cp1252"]:
                    try:
                        results[name] = raw.decode(enc)
                        break
                    except Exception:
                        continue
    return results


# ── Identificar dataset ────────────────────────────────────────────────────
def match_dataset(filename: str) -> dict | None:
    fn_upper = filename.upper()
    for meta in DATASET_MAP:
        if any(kw.upper() in fn_upper for kw in meta["keywords"]):
            return meta
    return None


# ── Normalizar CSV ─────────────────────────────────────────────────────────
def normalize_csv(text: str) -> str:
    lines = [l for l in text.splitlines() if l.strip() and not l.strip().startswith("#")]
    if not lines:
        return ""
    header = lines[0]
    sep = "," if header.count(",") >= header.count(";") else ";"

    def split_row(line):
        return [p.strip().strip('"').strip("'") for p in line.split(sep)]

    h = [x.lower() for x in split_row(header)]
    ts_kw  = ("time", "stamp", "fecha", "iso", "utc", "start", "inicio")
    val_kw = ("value", "valor", "°c", "degc", "m/s", "ft", "cfs", "cms", "temp", "wind", "speed", "nivel", "level", "elevation", "discharge", "caudal")
    ts_cols  = [i for i, x in enumerate(h) if any(k in x for k in ts_kw)]
    val_cols = [i for i, x in enumerate(h) if any(k in x for k in val_kw)]
    if not ts_cols:
        ts_cols = [0]
    if not val_cols:
        val_cols = [2 if len(ts_cols) >= 2 else 1]
    ts1 = ts_cols[0]
    ts2 = ts_cols[1] if len(ts_cols) >= 2 else None
    vi  = val_cols[0]
    out = ["fecha_inicio,fecha_fin,valor_raw"]
    for line in lines[1:]:
        if not line.strip():
            continue
        parts = split_row(line)
        n = len(parts)
        if n <= max(ts1, vi):
            continue
        val = parts[vi] if vi < n else ""
        if not val or val.lower() in ("", "nan", "null", "none", "--"):
            continue
        try:
            float(val.replace(",", ".").replace(" ", ""))
        except ValueError:
            continue
        t1 = parts[ts1] if ts1 < n else ""
        if not t1:
            continue
        t2 = parts[ts2] if (ts2 is not None and ts2 < n and parts[ts2].strip()) else t1
        out.append(f"{t1},{t2},{val}")
    return "\n".join(out)


# ── Guardar ────────────────────────────────────────────────────────────────
def save_and_summarize(csv_map: dict[str, str], output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)

    # Limpieza de salida anterior que ya no se descarga, para evitar confusión en /data/.
    legacy = output_dir / "Discharge_ATotal_ALHA_tst.csv"
    if legacy.exists():
        legacy.unlink()
        print(f"  🧹  Archivo anterior eliminado: {legacy.name}")

    saved = []
    for filename, content in csv_map.items():
        meta = match_dataset(filename)
        if meta is None:
            print(f"\n  ⚠️  No se reconoció: {filename}")
            continue
        norm = normalize_csv(content)
        if not norm or norm.count("\n") < 1:
            print(f"  ⚠️  {meta['label']}: sin datos válidos.")
            continue
        path = output_dir / f"{meta['name']}.csv"
        path.write_text(norm, encoding="utf-8")
        n = norm.count("\n")
        print(f"  ✅  {meta['label']}: {n} registros → {path.name}")
        saved.append(path)
    return saved


def print_summary(saved: list[Path]) -> None:
    print("\n── Resumen ────────────────────────────────────")
    for path in saved:
        try:
            df = pd.read_csv(path)
            df["fecha_inicio"] = pd.to_datetime(df["fecha_inicio"], errors="coerce")
            last = df["fecha_inicio"].max()
            first = df["fecha_inicio"].min()
            n = df["valor_raw"].notna().sum()
            print(
                f"  {path.stem:<25} {n:>6} registros  "
                f"{first.strftime('%Y-%m-%d')} → {last.strftime('%Y-%m-%d %H:%M')}"
            )
        except Exception as e:
            print(f"  {path.stem}: error ({e})")


# ── Git: verificar .gitignore y hacer push ─────────────────────────────────
def fix_gitignore(repo_dir: Path) -> None:
    gitignore = repo_dir / ".gitignore"
    if not gitignore.exists():
        return
    content = gitignore.read_text(encoding="utf-8", errors="replace")
    problematic = ["*.csv", "data/", "/data/", "data/*"]
    found = [p for p in problematic if p in content]
    if found:
        print(f"\n  ⚠️  .gitignore tiene reglas que bloquean los CSV: {found}")
        print("  Eliminando esas reglas automáticamente...")
        lines = content.splitlines()
        new_lines = [l for l in lines if l.strip() not in problematic]
        gitignore.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        print("  ✅  .gitignore corregido")
    else:
        print("  ✅  .gitignore OK (no bloquea CSV)")


def git_push(repo_dir: Path, saved: list[Path], branch: str) -> bool:
    print("\n── Subiendo a GitHub ──────────────────────────")

    try:
        commit_auto_changes(
            repo_dir,
            f"Datos LakeHouse {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        )
    except Exception as e:
        print(f"  ❌ git commit falló: {e}")
        return False

    status = git_status_short(repo_dir)
    if status:
        print(f"  ⚠️  Aún quedan cambios sin confirmar:\n    {status}")

    code, out, err = run_git(repo_dir, "git", "push", "origin", branch)
    if code != 0:
        print(f"  ⚠️  git push falló inicialmente:\n    {err or out}")
        print("  → Intentando sincronizar con rebase y volver a subir...")
        try:
            pull_rebase_with_generated_resolution(repo_dir, branch)
        except Exception as e:
            print(f"  ❌ No se pudo hacer rebase automático: {e}")
            return False
        code, out, err = run_git(repo_dir, "git", "push", "origin", branch)
        if code != 0:
            print(f"  ❌ git push falló:\n    {err or out}")
            print("  → Revisa si tu token de GitHub sigue vigente o si la rama está protegida.")
            return False

    print(f"  ✅ git push OK hacia origin/{branch}")
    print("  ⏳ Streamlit Cloud se actualizará en 1-2 minutos")
    return True


# ── Main ───────────────────────────────────────────────────────────────────
def main() -> None:
    print("=" * 60)
    print("  Descarga de datos — Aquatic Informatics / ACP")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    try:
        branch = ensure_default_branch(REPO_DIR)
    except Exception as e:
        print(f"\n❌ Error de Git: {e}")
        sys.exit(1)

    csv_map = {}
    try:
        print("\n[1/4] Descargando BulkExport...")
        for idx, url in enumerate(DOWNLOAD_URLS, start=1):
            print(f"\n  BulkExport {idx}/{len(DOWNLOAD_URLS)}")
            raw_bytes = download_bytes(url)
            is_zip = raw_bytes[:2] == b"PK"
            print(f"\n  Formato: {'ZIP ✅' if is_zip else 'texto plano (inesperado)'}")
            if not is_zip:
                (OUTPUT_DIR / f"_raw_{idx}.bin").write_bytes(raw_bytes)
                print(f"  Guardado como _raw_{idx}.bin para diagnóstico.")
                sys.exit(1)

            print("\n[2/4] Extrayendo CSVs del ZIP...")
            try:
                csv_map.update(extract_csvs_from_zip(raw_bytes))
            except zipfile.BadZipFile as e:
                print(f"\n❌ ZIP inválido: {e}")
                sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)

    print(f"\n[3/4] Normalizando y guardando en: {OUTPUT_DIR}")
    saved = save_and_summarize(csv_map, OUTPUT_DIR)
    if not saved:
        print("\n❌ No se guardó ningún archivo.")
        sys.exit(1)

    print_summary(saved)

    print("\n[4/4] Verificando .gitignore y subiendo a GitHub...")
    fix_gitignore(REPO_DIR)
    git_push(REPO_DIR, saved, branch)


if __name__ == "__main__":
    main()
