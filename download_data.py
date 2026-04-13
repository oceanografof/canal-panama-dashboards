"""
download_data.py — Descarga datos de Aquatic Informatics, los guarda en /data/
y los sube a GitHub automáticamente.

Corre desde tu PC dentro de la red ACP:
    python download_data.py
"""
from __future__ import annotations
import io, sys, time, zipfile, subprocess, urllib.request, urllib.error
from datetime import datetime
from pathlib import Path
import pandas as pd

# ── Configuración ──────────────────────────────────────────────────────────
OUTPUT_DIR   = Path(__file__).resolve().parent / "data"
REPO_DIR     = Path(__file__).resolve().parent   # raíz del repositorio git
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

DATASET_MAP = [
    {"keywords": ["LAN WT AVG","LAN_WT"],  "name": "LAN_WT_AVG_AMA",     "label": "Temp LAN WT AVG @ AMA"},
    {"keywords": ["Telemetria","TEMP@AMA"],"name": "Telemetria_TEMP_AMA", "label": "Temp Telemetría @ AMA"},
    {"keywords": ["WS AVG@LMB","WS_AVG"],  "name": "WS_AVG_LMB",         "label": "Viento WS AVG @ LMB"},
    {"keywords": ["LAN WS AVG","LAN_WS"],  "name": "LAN_WS_AVG_FLC",     "label": "Viento LAN WS AVG @ FLC"},
]

TIMEOUT_CONN = 300
TIMEOUT_READ = 600
CHUNK_SIZE   = 65536


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
        print(f"  Descargando", end="", flush=True)
        deadline = time.time() + TIMEOUT_READ
        while True:
            if time.time() > deadline:
                raise TimeoutError(f"Timeout ({TIMEOUT_READ}s)")
            chunk = resp.read(CHUNK_SIZE)
            if not chunk: break
            chunks.append(chunk); total += len(chunk)
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
                    try: results[name] = raw.decode(enc); break
                    except: continue
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
    if not lines: return ""
    header = lines[0]
    sep = "," if header.count(",") >= header.count(";") else ";"
    def split_row(line):
        return [p.strip().strip('"').strip("'") for p in line.split(sep)]
    h = [x.lower() for x in split_row(header)]
    TS_KW  = ("time","stamp","fecha","iso","utc","start","inicio")
    VAL_KW = ("value","valor","°c","degc","m/s","ft","temp","wind","speed","nivel")
    ts_cols  = [i for i,x in enumerate(h) if any(k in x for k in TS_KW)]
    val_cols = [i for i,x in enumerate(h) if any(k in x for k in VAL_KW)]
    if not ts_cols:  ts_cols  = [0]
    if not val_cols: val_cols = [2 if len(ts_cols)>=2 else 1]
    ts1 = ts_cols[0]
    ts2 = ts_cols[1] if len(ts_cols)>=2 else None
    vi  = val_cols[0]
    out = ["fecha_inicio,fecha_fin,valor_raw"]
    for line in lines[1:]:
        if not line.strip(): continue
        parts = split_row(line); n = len(parts)
        if n <= max(ts1, vi): continue
        val = parts[vi] if vi < n else ""
        if not val or val.lower() in ("","nan","null","none","--"): continue
        try: float(val.replace(",",".").replace(" ",""))
        except ValueError: continue
        t1 = parts[ts1] if ts1 < n else ""
        if not t1: continue
        t2 = parts[ts2] if (ts2 is not None and ts2<n and parts[ts2].strip()) else t1
        out.append(f"{t1},{t2},{val}")
    return "\n".join(out)


# ── Guardar ────────────────────────────────────────────────────────────────
def save_and_summarize(csv_map: dict[str, str], output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
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
            last  = df["fecha_inicio"].max()
            first = df["fecha_inicio"].min()
            n = df["valor_raw"].notna().sum()
            print(f"  {path.stem:<25} {n:>6} registros  "
                  f"{first.strftime('%Y-%m-%d')} → {last.strftime('%Y-%m-%d %H:%M')}")
        except Exception as e:
            print(f"  {path.stem}: error ({e})")


# ── Git: verificar .gitignore y hacer push ─────────────────────────────────
def fix_gitignore(repo_dir: Path) -> None:
    """Asegura que data/*.csv NO esté en .gitignore."""
    gitignore = repo_dir / ".gitignore"
    if not gitignore.exists():
        return
    content = gitignore.read_text(encoding="utf-8", errors="replace")
    problematic = ["*.csv", "data/", "/data/", "data/*"]
    found = [p for p in problematic if p in content]
    if found:
        print(f"\n  ⚠️  .gitignore tiene reglas que bloquean los CSV: {found}")
        print(f"  Eliminando esas reglas automáticamente...")
        lines = content.splitlines()
        new_lines = [l for l in lines if l.strip() not in problematic]
        gitignore.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        print(f"  ✅  .gitignore corregido")
    else:
        print(f"  ✅  .gitignore OK (no bloquea CSV)")


def git_push(repo_dir: Path, saved: list[Path]) -> bool:
    """Hace git add + commit + push automáticamente."""
    def run(cmd):
        result = subprocess.run(
            cmd, cwd=str(repo_dir),
            capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()

    print("\n── Subiendo a GitHub ──────────────────────────")

    # git add — data/ + cualquier archivo .py o .bat modificado
    for target in ["data/", "download_data.py", "app_temperatura.py",
                   "requirements.txt", "actualizar.bat"]:
        p = repo_dir / target.rstrip("/")
        if p.exists():
            run(["git", "add", target])
    # también .gitignore si existe
    if (repo_dir / ".gitignore").exists():
        run(["git", "add", ".gitignore"])
    print("  ✅ git add OK")

    # git status
    code, out, err = run(["git", "status", "--short"])
    if not out.strip():
        print("  ℹ️  Sin cambios nuevos — GitHub ya está actualizado.")
        return True
    print(f"  Cambios:\n    {out}")

    # git commit — mensaje sin tildes para evitar problemas en Windows
    msg = f"Datos {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    code, out, err = run(["git", "commit", "-m", msg])
    if code != 0:
        full_msg = (out + " " + err).strip()
        if "nothing to commit" in full_msg or "nada para hacer commit" in full_msg:
            print("  ℹ️  Sin cambios nuevos — GitHub ya está actualizado.")
            return True
        print(f"  ❌ git commit fallo: {full_msg}")
        return False
    print(f"  ✅ git commit OK: '{msg}'")

    # git push
    code, out, err = run(["git", "push"])
    if code != 0:
        print(f"  ❌ git push falló:\n    {err}")
        print("  → Asegúrate que tu token de GitHub esté configurado.")
        print("    Corre una vez: git push   (te pedirá usuario + token)")
        return False
    print("  ✅ git push OK — GitHub actualizado")
    print("  ⏳ Streamlit Cloud se actualizará en 1-2 minutos")
    return True


# ── Main ───────────────────────────────────────────────────────────────────
def main() -> None:
    print("=" * 60)
    print("  Descarga de datos — Aquatic Informatics / ACP")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 1. Descargar
    try:
        print("\n[1/4] Descargando BulkExport...")
        raw_bytes = download_bytes(BASE_URL)
    except Exception as e:
        print(f"\n❌ Error: {e}"); sys.exit(1)

    # 2. Verificar formato
    is_zip = raw_bytes[:2] == b"PK"
    print(f"\n  Formato: {'ZIP ✅' if is_zip else 'texto plano (inesperado)'}")
    if not is_zip:
        (OUTPUT_DIR / "_raw.bin").write_bytes(raw_bytes)
        print("  Guardado como _raw.bin para diagnóstico."); sys.exit(1)

    # 3. Extraer y guardar
    print("\n[2/4] Extrayendo CSVs del ZIP...")
    try:
        csv_map = extract_csvs_from_zip(raw_bytes)
    except zipfile.BadZipFile as e:
        print(f"\n❌ ZIP inválido: {e}"); sys.exit(1)

    print(f"\n[3/4] Normalizando y guardando en: {OUTPUT_DIR}")
    saved = save_and_summarize(csv_map, OUTPUT_DIR)
    if not saved:
        print("\n❌ No se guardó ningún archivo."); sys.exit(1)

    print_summary(saved)

    # 4. Verificar .gitignore y hacer push
    print("\n[4/4] Verificando .gitignore y subiendo a GitHub...")
    fix_gitignore(REPO_DIR)
    git_push(REPO_DIR, saved)


if __name__ == "__main__":
    main()
