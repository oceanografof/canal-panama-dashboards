"""
download_data.py — Descarga datos de Aquatic Informatics y los guarda en /data/
El servidor devuelve un ZIP con un CSV por dataset. Este script lo descomprime
y normaliza automáticamente.

Corre desde tu PC dentro de la red ACP:
    python download_data.py
"""
from __future__ import annotations
import io, sys, time, zipfile, urllib.request, urllib.error
from datetime import datetime
from pathlib import Path
import pandas as pd

# ── Configuración ──────────────────────────────────────────────────────────
OUTPUT_DIR   = Path(__file__).resolve().parent / "data"
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

# Palabras clave para identificar cada dataset por el nombre del CSV dentro del ZIP
DATASET_MAP = [
    {"keywords": ["LAN WT AVG","LAN_WT"],  "name": "LAN_WT_AVG_AMA",     "label": "Temp LAN WT AVG @ AMA",    "variable": "Temperatura", "sensor": "LAN"},
    {"keywords": ["Telemetria","TEMP@AMA"],"name": "Telemetria_TEMP_AMA", "label": "Temp Telemetría @ AMA",   "variable": "Temperatura", "sensor": "Telemetría"},
    {"keywords": ["WS AVG@LMB","WS_AVG"],  "name": "WS_AVG_LMB",         "label": "Viento WS AVG @ LMB",     "variable": "Viento",      "sensor": "WS AVG"},
    {"keywords": ["LAN WS AVG","LAN_WS"],  "name": "LAN_WS_AVG_FLC",     "label": "Viento LAN WS AVG @ FLC", "variable": "Viento",      "sensor": "LAN WS AVG"},
]

TIMEOUT_CONN = 300
TIMEOUT_READ = 600
CHUNK_SIZE   = 65536


# ── Descarga ───────────────────────────────────────────────────────────────
def download_bytes(url: str) -> bytes:
    """Descarga la URL y devuelve bytes crudos (puede ser ZIP o CSV)."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "*/*",
    }
    req = urllib.request.Request(url, headers=headers)
    chunks, total, t0 = [], 0, time.time()
    print("  Conectando...", flush=True)
    with urllib.request.urlopen(req, timeout=TIMEOUT_CONN) as resp:
        print(f"  HTTP {resp.status} · Content-Type: {resp.headers.get('Content-Type','?')}")
        print(f"  Descargando", end="", flush=True)
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
    print(f" {total/1024:.0f} KB en {time.time()-t0:.1f}s")
    return b"".join(chunks)


# ── Extraer CSVs del ZIP ────────────────────────────────────────────────────
def extract_csvs_from_zip(raw_bytes: bytes) -> dict[str, str]:
    """
    Abre el ZIP en memoria y devuelve un diccionario {nombre_archivo: contenido_texto}.
    """
    results = {}
    with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
        names = zf.namelist()
        print(f"\n  Archivos en el ZIP ({len(names)}):")
        for name in names:
            print(f"    · {name}")
            with zf.open(name) as f:
                raw = f.read()
                # Detectar encoding
                for enc in ["utf-8-sig", "utf-8", "latin-1", "cp1252"]:
                    try:
                        results[name] = raw.decode(enc)
                        break
                    except Exception:
                        continue
    return results


# ── Identificar dataset por nombre de archivo ─────────────────────────────
def match_dataset(filename: str) -> dict | None:
    """Busca en DATASET_MAP cuál meta corresponde al nombre del archivo CSV."""
    fn_upper = filename.upper()
    for meta in DATASET_MAP:
        if any(kw.upper() in fn_upper for kw in meta["keywords"]):
            return meta
    return None


# ── Normalizar CSV al formato que espera el app ───────────────────────────
def normalize_csv(text: str) -> str:
    """
    Convierte cualquier formato de Aquatic Informatics a:
        fecha_inicio,fecha_fin,valor_raw
    Salta líneas de comentario (#), detecta separador, detecta columnas.
    """
    lines = [l for l in text.splitlines() if l.strip() and not l.strip().startswith("#")]
    if not lines:
        return ""

    header = lines[0]
    sep = "," if header.count(",") >= header.count(";") else ";"

    def split_row(line: str) -> list[str]:
        return [p.strip().strip('"').strip("'") for p in line.split(sep)]

    h = [x.lower() for x in split_row(header)]
    TS_KW  = ("time", "stamp", "fecha", "iso", "utc", "start", "inicio")
    VAL_KW = ("value", "valor", "°c", "degc", "m/s", "ft", "temp", "wind", "speed", "nivel")

    ts_cols  = [i for i, x in enumerate(h) if any(k in x for k in TS_KW)]
    val_cols = [i for i, x in enumerate(h) if any(k in x for k in VAL_KW)]

    if not ts_cols:  ts_cols  = [0]
    if not val_cols: val_cols = [2 if len(ts_cols) >= 2 else 1]

    ts1 = ts_cols[0]
    ts2 = ts_cols[1] if len(ts_cols) >= 2 else None
    vi  = val_cols[0]

    print(f"    Header detectado: {h}")
    print(f"    Columnas TS={ts_cols}  Valor={val_cols}  Sep='{sep}'")

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
        t2 = (parts[ts2] if ts2 is not None and ts2 < n and parts[ts2].strip() else t1)
        out.append(f"{t1},{t2},{val}")

    return "\n".join(out)


# ── Guardar y resumir ──────────────────────────────────────────────────────
def save_and_summarize(csv_map: dict[str, str], output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    saved = []

    for filename, content in csv_map.items():
        meta = match_dataset(filename)
        if meta is None:
            print(f"\n  ⚠️  No se reconoció: {filename} — omitido")
            continue

        print(f"\n  Procesando: {filename}")
        norm = normalize_csv(content)

        if not norm or norm.count("\n") < 1:
            print(f"  ⚠️  {meta['label']}: sin datos válidos tras normalización.")
            continue

        n_rows = norm.count("\n")
        path = output_dir / f"{meta['name']}.csv"
        path.write_text(norm, encoding="utf-8")
        print(f"  ✅  {meta['label']}: {n_rows} registros → {path.name}")
        saved.append(path)

    return saved


def print_summary(saved: list[Path]) -> None:
    print("\n── Resumen final ──────────────────────────────────────")
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
            print(f"  {path.stem}: error al leer ({e})")


# ── Main ───────────────────────────────────────────────────────────────────
def main() -> None:
    print("=" * 60)
    print("  Descarga de datos — Aquatic Informatics / ACP")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 1. Descargar
    try:
        print("\n[1/3] Descargando BulkExport...")
        raw_bytes = download_bytes(BASE_URL)
    except Exception as e:
        print(f"\n❌ Error de descarga: {e}")
        sys.exit(1)

    # 2. Verificar si es ZIP o CSV plano
    is_zip = raw_bytes[:2] == b"PK"
    print(f"\n  Formato detectado: {'ZIP comprimido ✅' if is_zip else 'texto plano'}")

    if not is_zip:
        # Guardar como raw y salir con diagnóstico
        raw_path = OUTPUT_DIR / "_raw_bulk_export.bin"
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        raw_path.write_bytes(raw_bytes)
        print(f"  Archivo guardado en {raw_path}")
        print("  El formato no es ZIP ni texto reconocido. Comparte este archivo.")
        sys.exit(1)

    # 3. Extraer CSVs del ZIP
    print("\n[2/3] Extrayendo CSVs del ZIP...")
    try:
        csv_map = extract_csvs_from_zip(raw_bytes)
    except zipfile.BadZipFile as e:
        print(f"\n❌ El archivo no es un ZIP válido: {e}")
        sys.exit(1)

    if not csv_map:
        print("\n❌ El ZIP estaba vacío.")
        sys.exit(1)

    # 4. Normalizar y guardar
    print(f"\n[3/3] Normalizando y guardando en: {OUTPUT_DIR}")
    saved = save_and_summarize(csv_map, OUTPUT_DIR)

    if not saved:
        print("\n❌ No se guardó ningún archivo.")
        sys.exit(1)

    print_summary(saved)

    print("\n✅ Descarga completa. Sube a GitHub:")
    print("  git add data/")
    print(f"  git commit -m \"Datos {datetime.now().strftime('%Y-%m-%d %H:%M')}\"")
    print("  git push\n")


if __name__ == "__main__":
    main()
