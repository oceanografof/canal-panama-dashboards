# -*- coding: utf-8 -*-
"""
DSS Simulación 2026 — Dashboard de toma de decisiones
Autor : JFRodriguez · Hidrólogo / Oceanógrafo Físico · ACP-HIMH

Versión simplificada y blindada:
- Pestañas enfocadas en decisión operativa
- Manejo robusto de errores en toda lectura de datos
- Sin pestañas redundantes ni funciones muertas
- Soporte nativo para BulkExport-GAT/MAD/TstCHCP (niveles y aportes directos)

Ejecución (Windows):
    py -m pip install streamlit openpyxl plotly pandas numpy
    py -m streamlit run app_simulacion_dss.py
"""
from __future__ import annotations

import re
from io import BytesIO, StringIO
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from openpyxl import load_workbook

try:
    import plotly.express as px
    import plotly.graph_objects as go
    PLOTLY_OK = True
except ImportError:
    PLOTLY_OK = False

# ─────────────────────────────────────────────────────────────────────
# Configuración de página
# ─────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="DSS Simulación 2026",
    page_icon="🏞️",
    layout="wide",
    initial_sidebar_state="expanded",
)

APP_TITLE   = "DSS Simulación 2026 · Embalses ACP"
AUTHOR_NOTE = "JFRodriguez · Hidrólogo / Oceanógrafo Físico · ACP-HIMH"
SIMULATION_NOTE = "Simulación realizada por JFRodriguez"
PROJ_NOTE   = "Proyecciones basadas en el decenio 2015-2025."
VIEW_FILE   = ".dss_views.txt"
RADAR_URL   = "https://radar-meteorologico.delcanal.com/es.gif"

DSS_NAMES = [
    "SimulacionDSS_2026.xlsx", "SimulacionDSS_2026(3).xlsx",
    "SimulacionDSS_2026(2).xlsx", "SimulacionDSS_2026(1).xlsx",
]

# Carpeta estándar de datos del proyecto.
# La app busca primero en ./data y, como respaldo, en la carpeta donde está el script.
DATA_DIR_NAME = "data"

CFS_TO_M3S     = 0.028316846592
CFS_TO_HM3_DAY = CFS_TO_M3S * 86400 / 1_000_000

PERCENTILE_ORDER = [95, 90, 80, 70, 60, 50, 40, 30, 20, 10, 5]
EXCEEDANCE_COLORS = {
    95: "#001f5b", 90: "#003f88", 80: "#005f99", 70: "#0077b6",
    60: "#0096c7", 50: "#48cae4", 40: "#90e0ef",
    30: "#f4a261", 20: "#e76f51", 10: "#d62828", 5: "#9b2226",
}

RESERVOIR_CONFIG: Dict[str, Dict] = {
    "gatun": {
        "sheet":      "GATUN Px DSS",
        "token":      "GAT",
        "name":       "Gatún",
        "level_unit": "ft PLD",
        "color":      "#0066cc",
    },
    "alhajuela": {
        "sheet":      "ALHAJUELA Px DSS ",
        "token":      "ALH",
        "name":       "Alhajuela / Madden",
        "level_unit": "ft PLD",
        "color":      "#cc6600",
    },
}


def unit_label(unit: str) -> str:
    return "p³/s" if unit == "cfs" else unit


def today_panama() -> pd.Timestamp:
    """Fecha actual en Panamá, usada para evitar graficar observaciones en días futuros."""
    try:
        return pd.Timestamp.now(tz="America/Panama").tz_localize(None).normalize()
    except Exception:
        return pd.Timestamp.today().normalize()


def clamp_observed_future_dates(df: pd.DataFrame, date_col: str = "Fecha_dia") -> pd.DataFrame:
    """Corrige observaciones que por zona horaria/sello de tiempo caigan en un día futuro.

    Los aportes y niveles observados no deben aparecer después del día actual operativo.
    Si un BulkExport trae un sello futuro por conversión/horario, se coloca en el día actual.
    """
    if df is None or df.empty or date_col not in df.columns:
        return df
    out = df.copy()
    out[date_col] = pd.to_datetime(out[date_col], errors="coerce").dt.normalize()
    today = today_panama()
    out.loc[out[date_col] > today, date_col] = today
    return out


# ─────────────────────────────────────────────────────────────────────
# CSS mínimo
# ─────────────────────────────────────────────────────────────────────
def inject_css() -> None:
    st.markdown("""
    <style>
    .main-title{font-size:2.1rem;font-weight:900;color:#003E69;margin-bottom:.1rem}
    .sub-title{color:#5f6b7a;font-size:1rem;margin-bottom:.8rem}
    div[data-testid="metric-container"]{
        border:1px solid rgba(0,62,105,.15);border-radius:12px;
        padding:.8rem 1rem;background:rgba(248,250,252,.92)}
    div[data-testid="stMetricValue"]{font-size:1.7rem;font-weight:800}
    .footer{margin-top:1rem;padding:.6rem;border-top:1px solid rgba(0,62,105,.12);
            color:#475467;font-size:.88rem;text-align:center}
    .badge{display:inline-block;background:#003E69;color:#fff;
           border-radius:8px;padding:2px 10px;font-size:.8rem;font-weight:700}
    </style>""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────
# Contador de vistas (por sesión, persistente en archivo)
# ─────────────────────────────────────────────────────────────────────
def get_view_count() -> int:
    if "view_count" in st.session_state:
        return int(st.session_state["view_count"])
    try:
        p = Path(VIEW_FILE)
        n = int(p.read_text().strip()) if p.exists() else 0
        n += 1
        p.write_text(str(n))
    except Exception:
        n = int(st.session_state.get("view_count", 0)) + 1
    st.session_state["view_count"] = n
    return n


# ─────────────────────────────────────────────────────────────────────
# Utilidades de archivo
# ─────────────────────────────────────────────────────────────────────
def app_base_dir() -> Path:
    """Carpeta donde está ubicado el script, con respaldo al directorio actual."""
    try:
        return Path(__file__).resolve().parent
    except Exception:
        return Path.cwd().resolve()


def local_search_dirs() -> List[Path]:
    """Directorios locales de búsqueda, priorizando la carpeta ./data.

    Estructura recomendada del proyecto:
        app_dss.py
        data/
          SimulacionDSS_2026.xlsx
          BulkExport*.csv
          Discharge_AT_GAT_Diario.csv
          Discharge_AT_ALHA_Diario.csv
          Lake_Res_elevation_*GAT*.csv
          Lake_Res_elevation_*ALHA*.csv
    """
    base = app_base_dir()
    candidates = [base / DATA_DIR_NAME, Path.cwd().resolve() / DATA_DIR_NAME, base, Path.cwd().resolve()]
    dirs: List[Path] = []
    seen = set()
    for d in candidates:
        try:
            rd = d.resolve()
        except Exception:
            rd = d
        if rd in seen or not rd.exists() or not rd.is_dir():
            continue
        seen.add(rd)
        dirs.append(rd)
    return dirs


def find_local(candidates: List[str]) -> Optional[Path]:
    """Busca un archivo local primero en ./data y luego junto al script."""
    for base in local_search_dirs():
        for n in candidates:
            p = base / n
            if p.exists() and p.is_file():
                return p
    return None


@st.cache_data(show_spinner=False)
def _read_bytes_cached(path_str: str, mtime_ns: int, size: int) -> bytes:
    return Path(path_str).read_bytes()


def read_path_safe(path: Optional[Path]) -> Optional[bytes]:
    if path is None or not path.exists():
        return None
    try:
        st = path.stat()
        return _read_bytes_cached(str(path), int(st.st_mtime_ns), int(st.st_size))
    except PermissionError:
        st.warning(f"⚠️ `{path.name}` está bloqueado (Excel/OneDrive abierto). Ciérrelo o cargue manualmente.")
        return None
    except OSError as exc:
        st.warning(f"⚠️ No se pudo leer `{path.name}`: {exc}")
        return None


def read_first_local(candidates: List[str]) -> Tuple[Optional[bytes], Optional[Path]]:
    """Lee el primer archivo encontrado, priorizando ./data.

    Primero busca nombres exactos; si no aparecen, usa un respaldo flexible
    para versiones como SimulacionDSS_2026(4).xlsx o copias nuevas del DSS.
    """
    for base in local_search_dirs():
        for name in candidates:
            p = base / name
            if p.exists() and p.is_file():
                data = read_path_safe(p)
                if data:
                    return data, p

    # Respaldo flexible: usa el Excel DSS más reciente dentro de data/ o junto al app.
    fallback_patterns = ["SimulacionDSS_2026*.xlsx", "SimulacionDSS*.xlsx", "*DSS*.xlsx"]
    seen: Dict[Path, Path] = {}
    for base in local_search_dirs():
        for pat in fallback_patterns:
            for fp in base.glob(pat):
                try:
                    if fp.exists() and fp.is_file() and fp.suffix.lower() in {".xlsx", ".xlsm"}:
                        seen[fp.resolve()] = fp
                except OSError:
                    continue
    for fp in sorted(seen.values(), key=lambda x: x.stat().st_mtime, reverse=True):
        data = read_path_safe(fp)
        if data:
            return data, fp

    return None, None


# ─────────────────────────────────────────────────────────────────────
# Carga de hojas DSS
# ─────────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner="Cargando hoja DSS…")
def load_dss_sheet(file_bytes: bytes, wanted: str) -> pd.DataFrame:
    """Carga una hoja DSS desde bytes. Blindado contra hojas inexistentes y headers duplicados."""
    try:
        names = pd.ExcelFile(BytesIO(file_bytes), engine="openpyxl").sheet_names
    except Exception as exc:
        raise ValueError(f"No se pudo abrir el Excel DSS: {exc}")

    target = next((s for s in names if s.strip().lower() == wanted.strip().lower()), None)
    if target is None:
        target = next((s for s in names if wanted.strip().lower() in s.strip().lower()), None)
    if target is None:
        raise ValueError(f"Hoja '{wanted}' no encontrada. Disponibles: {names}")

    wb = load_workbook(BytesIO(file_bytes), read_only=True, data_only=True)
    try:
        ws = wb[target]
        hrow = list(next(ws.iter_rows(min_row=1, max_row=1, values_only=True)))
        last = max((i for i, v in enumerate(hrow) if v is not None), default=-1) + 1
        if last == 0:
            raise ValueError(f"Hoja '{target}' sin encabezados.")
        # Headers únicos
        seen: Dict[str, int] = {}
        headers = []
        for i, v in enumerate(hrow[:last], 1):
            name = str(v).strip() if v is not None else f"Col_{i}"
            if not name or name.lower().startswith("unnamed"):
                name = f"Col_{i}"
            seen[name] = seen.get(name, 0) + 1
            headers.append(f"{name}_{seen[name]}" if seen[name] > 1 else name)
        rows, blanks, started = [], 0, False
        for row in ws.iter_rows(min_row=2, max_col=last, values_only=True):
            fecha = row[0] if row else None
            if fecha is None or str(fecha).strip() == "":
                if started:
                    blanks += 1
                    if blanks >= 24:
                        break
                continue
            started, blanks = True, 0
            rows.append(row)
    finally:
        wb.close()

    df = pd.DataFrame(rows, columns=headers)
    df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce")
    df = df[df["Fecha"].notna()].sort_values("Fecha").copy()
    for col in df.columns:
        if col != "Fecha":
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df.dropna(axis=1, how="all", inplace=True)
    return df


# ─────────────────────────────────────────────────────────────────────
# Carga de CSV de BulkExport (GAT, MAD, TstCHCP_AT)
# ─────────────────────────────────────────────────────────────────────
def _detect_embalse(header_text: str, filename: str) -> str:
    t = f"{filename} {header_text}".upper()
    if any(x in t for x in ["ATOTAL_GAT", "_GAT_", "GAT_TST", "GATUN", "GATÚN", "BulkExport-GAT".upper()]):
        return "Gatún"
    if any(x in t for x in ["ATOTAL_ALHA", "_ALHA_", "ALHA", "MADDEN", "MAD", "BulkExport-MAD".upper(),
                              "BulkExport-TstCHCP".upper()]):
        return "Alhajuela / Madden"
    if "GAT" in t and "ALH" not in t:
        return "Gatún"
    return "Desconocido"


def _detect_variable(header_text: str, filename: str) -> str:
    """Detect if CSV contains level or flow data."""
    t = f"{filename} {header_text}".upper()
    if any(x in t for x in ["ELEVATION", "NIVEL", "LAKE", "FT)", "FT "]):
        return "nivel"
    if any(x in t for x in ["DISCHARGE", "ATOTAL", "APORTE", "FLOW", "FT^3", "CFS"]):
        return "aporte"
    return "aporte"  # default


@st.cache_data(show_spinner=False)
def read_bulk_csv(file_bytes: bytes, filename: str = "") -> Tuple[pd.DataFrame, str, str, str]:
    """
    Lee un CSV de BulkExport o un CSV normalizado por el descargador local.

    Formatos soportados:
    1) BulkExport original de Aquatic Informatics.
    2) CSV normalizado/sanitizado con columnas:
       fecha_inicio, fecha_fin, valor_raw

    Retorna: (df_diario, embalse, variable, serie_name)
    df_diario tiene columnas: Fecha_dia, Valor, Fuente
    variable: 'nivel' | 'aporte'
    """
    empty = pd.DataFrame(columns=["Fecha_dia", "Valor", "Fuente"])
    if not file_bytes:
        return empty, "Desconocido", "aporte", "—"
    try:
        text = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = file_bytes.decode("latin-1", errors="replace")

    lines = text.splitlines()
    if not lines:
        return empty, "Desconocido", "aporte", "—"

    # Detectar separador con las primeras líneas.
    sep = ";" if sum(l.count(";") for l in lines[:10]) >= sum(l.count(",") for l in lines[:10]) else ","

    # Buscar fila de encabezado. Incluye BulkExport y CSV normalizado local.
    header_idx = 0
    for i, line in enumerate(lines[:80]):
        low = line.lower()
        has_time = any(x in low for x in ["sello", "timestamp", "fecha", "date", "time"])
        has_value = any(x in low for x in ["valor", "value", "valor_raw", "ft", "cfs", "cms", "m3", "m³"])
        if has_time and has_value:
            header_idx = i
            break

    meta_text = "\n".join(lines[:header_idx])
    embalse = _detect_embalse(meta_text, filename)
    variable = _detect_variable(meta_text, filename)

    serie = "—"
    for line in reversed(lines[:header_idx]):
        parts = [p.strip() for p in line.split(sep) if p.strip()]
        cand = next((p for p in parts if any(t in p.upper() for t in
                     ["DISCHARGE", "ATOTAL", "ELEVATION", "LAKE", "APORTE", "NIVEL"])), None)
        if cand:
            serie = cand
            break

    try:
        df = pd.read_csv(StringIO("\n".join(lines[header_idx:])), sep=sep, header=0)
    except Exception:
        return empty, embalse, variable, serie

    if df.empty or len(df.columns) < 2:
        return empty, embalse, variable, serie

    # ── Detección robusta de columnas ───────────────────────────────
    # Los CSV normalizados tienen: fecha_inicio, fecha_fin, valor_raw.
    # Antes se tomaba la segunda columna como valor; eso podía leer fecha_fin
    # y dejar todo como NaN. Aquí se detecta explícitamente la columna numérica.
    def _norm_col(c: object) -> str:
        s = str(c).strip().lower()
        repl = str.maketrans("áéíóúüñ", "aeiouun")
        return s.translate(repl)

    cols = list(df.columns)
    norm = {_norm_col(c): c for c in cols}

    preferred_time_names = [
        "fecha_inicio", "timestamp", "sello de tiempo", "sello", "fecha", "date", "time"
    ]
    time_col = None
    for key in preferred_time_names:
        for n, original in norm.items():
            if key in n:
                parsed = pd.to_datetime(df[original], errors="coerce")
                if parsed.notna().sum() > 0:
                    time_col = original
                    break
        if time_col is not None:
            break
    if time_col is None:
        time_col = cols[0]

    preferred_value_names = [
        "valor_raw", "valor", "value", "elevation", "nivel", "discharge", "aporte", "flow", "cfs", "ft"
    ]
    value_col = None
    for key in preferred_value_names:
        for n, original in norm.items():
            if original == time_col:
                continue
            if key in n and not any(x in n for x in ["fecha", "date", "time", "sello"]):
                sample = df[original].astype(str).str.replace(",", ".", regex=False).str.strip()
                parsed = pd.to_numeric(sample, errors="coerce")
                if parsed.notna().sum() > 0:
                    value_col = original
                    break
        if value_col is not None:
            break

    # Respaldo: escoger la columna con mayor cantidad de valores numéricos,
    # excluyendo columnas claramente temporales.
    if value_col is None:
        best = None
        best_count = -1
        for c in cols:
            n = _norm_col(c)
            if c == time_col or any(x in n for x in ["fecha", "date", "time", "sello"]):
                continue
            sample = df[c].astype(str).str.replace(",", ".", regex=False).str.strip()
            parsed = pd.to_numeric(sample, errors="coerce")
            count = int(parsed.notna().sum())
            if count > best_count:
                best = c
                best_count = count
        value_col = best

    if time_col is None or value_col is None:
        return empty, embalse, variable, serie

    out = pd.DataFrame()
    out["Fecha"] = pd.to_datetime(df[time_col], errors="coerce")
    raw_val = df[value_col].astype(str).str.replace(",", ".", regex=False).str.strip()
    out["Valor"] = pd.to_numeric(raw_val, errors="coerce")
    out = out.dropna(subset=["Fecha", "Valor"]).sort_values("Fecha")
    out["Fuente"] = filename or serie

    if out.empty:
        return empty, embalse, variable, serie

    # Agregar a diario.
    # - Nivel subdiario: último valor diario, más representativo del estado operativo.
    # - Aporte diario/subdiario: promedio diario.
    out["Fecha_dia"] = out["Fecha"].dt.floor("D")
    out = clamp_observed_future_dates(out, "Fecha_dia")

    if variable == "nivel":
        daily = out.groupby("Fecha_dia", as_index=False).agg(
            Valor=("Valor", "last"),
            Fuente=("Fuente", "last"),
        )
    else:
        daily = out.groupby("Fecha_dia", as_index=False).agg(
            Valor=("Valor", "mean"),
            Fuente=("Fuente", "last"),
        )

    return daily.sort_values("Fecha_dia"), embalse, variable, serie


def discover_local_bulk_csvs() -> List[Path]:
    """Descubre CSV observados, priorizando la carpeta ./data.

    Acepta nombres BulkExport originales y archivos ya normalizados/sanitizados
    generados por el proceso de descarga, por ejemplo:
    - BulkExport-GAT.csv / BulkExport-MAD.csv
    - Discharge_AT_GAT_Diario.csv / Discharge_AT_ALHA_Diario.csv
    - Lake_Res_elevation_*GAT*.csv / Lake_Res_elevation_*ALHA*.csv
    """
    patterns = [
        "BulkExport*.csv",
        "*GAT*.csv",
        "*GATUN*.csv",
        "*Gatún*.csv",
        "*Gatun*.csv",
        "*MAD*.csv",
        "*MADDEN*.csv",
        "*ALHA*.csv",
        "*ALHAJUELA*.csv",
    ]
    seen: Dict[Path, Path] = {}
    for base in local_search_dirs():
        for pat in patterns:
            for p in base.glob(pat):
                try:
                    if p.exists() and p.is_file():
                        seen[p.resolve()] = p
                except OSError:
                    continue
    return sorted(seen.values(), key=lambda p: p.stat().st_mtime, reverse=True)


# ─────────────────────────────────────────────────────────────────────
# Agregación diaria DSS
# ─────────────────────────────────────────────────────────────────────
def cols_by_prefix(df: pd.DataFrame, prefix: str, token: str) -> List[str]:
    """Columnas que empiecen con prefix y contengan token (case-insensitive)."""
    pat = re.compile(rf"^{re.escape(prefix)}(\d+)", re.I)
    out = [c for c in df.columns
           if pat.match(str(c).strip()) and token.upper() in str(c).upper()]
    return sorted(out, key=lambda c: -int(re.search(r"\d+", c).group()))


def exceedance_pct(col: str) -> int:
    m = re.search(r"(\d+)", str(col))
    return int(m.group()) if m else 50


def ordered_percentile_map_by_value(df: pd.DataFrame, cols: List[str], ref_row: Optional[pd.Series] = None) -> Dict[str, int]:
    """Devuelve el percentil original de cada columna DSS.

    Importante: no se reetiquetan los percentiles por magnitud.
    En aportes DSS la lógica operativa es de probabilidad de excedencia:
    P95 suele representar una condición más seca / menor aporte y P5 una
    condición más húmeda / mayor aporte. Por eso se conserva la etiqueta
    original de cada columna AP del DSS.
    """
    return {c: exceedance_pct(c) for c in cols if c in df.columns}


def make_ordered_ap_columns(df: pd.DataFrame, cols: List[str], flow_unit: str, add_cfs: float = 0.0) -> Tuple[pd.DataFrame, List[str], Dict[str, int]]:
    """Crea columnas AP conservando el percentil original del DSS."""
    out = df.copy()
    cols = [c for c in cols if c in out.columns]
    pct_map = ordered_percentile_map_by_value(out, cols)
    new_cols: List[str] = []
    for c in cols:
        pct = pct_map.get(c, exceedance_pct(c))
        nc = f"AP P{pct} [{unit_label(flow_unit)}]"
        # Evita duplicados si dos columnas terminan con la misma etiqueta
        if nc in out.columns:
            nc = f"AP P{pct} {c} [{unit_label(flow_unit)}]"
        out[nc] = convert_flow(pd.to_numeric(out[c], errors="coerce") + float(add_cfs or 0.0), flow_unit)
        new_cols.append(nc)
    return out, new_cols, pct_map


def to_daily(df: pd.DataFrame, cfg: Dict) -> pd.DataFrame:
    """Horario/subhorario DSS → diario. NP=last, flujos=mean."""
    if df is None or df.empty:
        return pd.DataFrame()
    data = df.copy()
    data["Fecha_dia"] = data["Fecha"].dt.floor("D")
    token = cfg["token"]
    agg: Dict[str, str] = {}
    for c in cols_by_prefix(data, "NP", token):
        agg[c] = "last"
    for px in ["HP", "AP", "V", "EG", "EP", "E"]:
        for c in cols_by_prefix(data, px, token):
            agg[c] = "mean"
    if "Observado" in data.columns:
        data["Obs_DSS"] = data["Observado"]
        agg["Obs_DSS"] = "last"
    if not agg:
        return pd.DataFrame()
    daily = data.groupby("Fecha_dia", as_index=False).agg(agg)
    return daily.sort_values("Fecha_dia")


# ─────────────────────────────────────────────────────────────────────
# Conversión de unidades
# ─────────────────────────────────────────────────────────────────────
def convert_flow(s: pd.Series, unit: str) -> pd.Series:
    s = pd.to_numeric(s, errors="coerce")
    if unit == "m³/s":
        return s * CFS_TO_M3S
    if unit == "hm³/d":
        return s * CFS_TO_HM3_DAY
    return s


def scalar_to_cfs(v: float, unit: str) -> float:
    try:
        v = float(v)
    except Exception:
        return 0.0
    if unit == "m³/s":
        return v / CFS_TO_M3S
    if unit == "hm³/d":
        return v / CFS_TO_HM3_DAY
    return v


# ─────────────────────────────────────────────────────────────────────
# Utilidades de gráficas
# ─────────────────────────────────────────────────────────────────────
def _today_line(fig, date_series) -> None:
    """Línea vertical 'Hoy' compatible con todos los rangos de fechas."""
    try:
        fechas = pd.to_datetime(date_series, errors="coerce").dropna()
        if fechas.empty:
            return
        today = pd.Timestamp.today().normalize()
        if not (fechas.min().normalize() <= today <= fechas.max().normalize()):
            return
        x_today = today.to_pydatetime()
        fig.add_shape(type="line", x0=x_today, x1=x_today, y0=0, y1=1,
                      xref="x", yref="paper",
                      line=dict(width=2, dash="dash", color="rgba(255,140,0,0.85)"))
        fig.add_annotation(x=x_today, y=1, xref="x", yref="paper",
                           text="Hoy", showarrow=False, yshift=12,
                           font=dict(color="darkorange", size=11),
                           bgcolor="rgba(255,255,255,0.75)",
                           bordercolor="rgba(255,140,0,0.55)", borderwidth=1)
    except Exception:
        pass


def _base_layout(title: str, y_title: str, height: int = 560) -> dict:
    return dict(
        title=dict(text=title, font=dict(size=14, color="#003E69")),
        height=height,
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=10, r=10, t=60, b=10),
        plot_bgcolor="rgba(250,252,255,1)",
        paper_bgcolor="rgba(250,252,255,0)",
        yaxis=dict(title=y_title, gridcolor="rgba(0,0,0,0.07)"),
        xaxis=dict(title="Fecha", gridcolor="rgba(0,0,0,0.07)"),
    )


def fan_chart(df: pd.DataFrame, cols: List[str], title: str, y_label: str, key: str,
              obs_col: Optional[str] = None, obs_label: str = "Observado",
              show_band: bool = True) -> None:
    """Abanico de percentiles con banda P90-P10 y traza observada."""
    if df.empty or not cols:
        st.info("Sin datos para graficar.")
        return
    cols = [c for c in cols if c in df.columns]
    if not cols:
        st.info("Columnas no disponibles.")
        return

    plot_df = df[["Fecha_dia"] + cols +
                 ([obs_col] if obs_col and obs_col in df.columns else [])].copy()
    plot_df = plot_df.dropna(how="all", subset=cols)
    if len(plot_df) > 4000:
        plot_df = plot_df.iloc[::max(1, len(plot_df) // 4000)]

    if not PLOTLY_OK:
        st.line_chart(plot_df.set_index("Fecha_dia")[cols])
        return

    fig = go.Figure()

    # Banda de incertidumbre P90-P10
    if show_band and len(cols) >= 2:
        p90 = next((c for c in cols if "90" in c), None)
        p10 = next((c for c in cols if "10" in c), None)
        if p90 and p10:
            fig.add_trace(go.Scatter(
                x=pd.concat([plot_df["Fecha_dia"], plot_df["Fecha_dia"][::-1]]),
                y=pd.concat([plot_df[p90], plot_df[p10][::-1]]),
                fill="toself", fillcolor="rgba(0,102,204,0.08)",
                line=dict(color="rgba(255,255,255,0)"),
                name="Banda P90-P10", showlegend=True, hoverinfo="skip",
            ))

    for col in cols:
        exc = exceedance_pct(col)
        is_p50 = exc == 50
        fig.add_trace(go.Scatter(
            x=plot_df["Fecha_dia"], y=plot_df[col], mode="lines",
            name=f"P{exc}",
            line=dict(
                color=EXCEEDANCE_COLORS.get(exc, "#999"),
                width=2.5 if is_p50 else 1.2,
                dash="dot" if exc in (90, 10) else "solid",
            ),
        ))

    if obs_col and obs_col in plot_df.columns:
        obs_v = plot_df[plot_df[obs_col].notna()].copy()
        if not obs_v.empty:
            lv = float(obs_v[obs_col].iloc[-1])
            labels = [""] * len(obs_v)
            labels[-1] = f"{lv:,.2f} {y_label}"
            fig.add_trace(go.Scatter(
                x=obs_v["Fecha_dia"], y=obs_v[obs_col],
                mode="lines+markers+text", name=f"🔴 {obs_label}",
                text=labels, textposition="top right",
                line=dict(color="#d90429", width=5),
                marker=dict(size=8, color="#d90429", line=dict(width=1.5, color="white")),
                connectgaps=True,
            ))
            fig.add_trace(go.Scatter(
                x=[obs_v["Fecha_dia"].iloc[-1]], y=[lv],
                mode="markers", name="📍 Último obs.",
                marker=dict(size=18, color="#d90429", symbol="star",
                            line=dict(width=2, color="white")),
            ))

    _today_line(fig, plot_df["Fecha_dia"])
    fig.update_layout(**_base_layout(title, y_label))
    st.plotly_chart(fig, use_container_width=True, key=key)


# ─────────────────────────────────────────────────────────────────────
# Percentil más cercano al observado
# ─────────────────────────────────────────────────────────────────────
def closest_np(daily: pd.DataFrame, cfg: Dict,
               obs_date: Optional[pd.Timestamp], obs_val: Optional[float]) -> Optional[Dict]:
    """Percentil NP DSS más cercano al nivel observado."""
    if daily is None or daily.empty or obs_date is None or obs_val is None:
        return None
    base = daily.copy()
    base["Fecha_dia"] = pd.to_datetime(base["Fecha_dia"], errors="coerce").dt.normalize()
    base = base[base["Fecha_dia"].notna()].sort_values("Fecha_dia")
    np_cols = cols_by_prefix(base, "NP", cfg["token"])
    if not np_cols:
        return None
    obs_day = pd.to_datetime(obs_date).normalize()
    exact = base[base["Fecha_dia"] == obs_day]
    row = exact.iloc[0] if not exact.empty else base.loc[(base["Fecha_dia"] - obs_day).abs().idxmin()]
    candidates = []
    for col in np_cols:
        v = pd.to_numeric(pd.Series([row.get(col, np.nan)]), errors="coerce").iloc[0]
        if pd.notna(v):
            candidates.append((col, float(v), abs(float(obs_val) - float(v))))
    if not candidates:
        return None
    col, dss_v, _ = min(candidates, key=lambda x: x[2])
    return {
        "label": f"P{exceedance_pct(col)}", "column": col,
        "dss_value": dss_v, "diff": float(obs_val) - dss_v,
        "date": pd.to_datetime(row["Fecha_dia"]),
    }


# ─────────────────────────────────────────────────────────────────────
# Filtro de fechas
# ─────────────────────────────────────────────────────────────────────
def date_filter(df: pd.DataFrame, key: str,
                default_days: int = 0) -> pd.DataFrame:
    """Filtro de fechas. default_days=0 usa rango completo."""
    if df.empty or "Fecha_dia" not in df.columns:
        return df
    valid = df["Fecha_dia"].dropna()
    if valid.empty:
        return df
    mn, mx = valid.min().date(), valid.max().date()
    if default_days > 0:
        import datetime
        default_start = max(mn, (pd.Timestamp(mx) - pd.Timedelta(days=default_days)).date())
    else:
        default_start = mn
    c1, c2 = st.columns(2)
    s = c1.date_input("Desde", value=default_start, min_value=mn, max_value=mx, key=f"{key}_s")
    e = c2.date_input("Hasta", value=mx, min_value=mn, max_value=mx, key=f"{key}_e")
    if s > e:
        st.warning("Fecha inicial > Fecha final. Se usa el período completo.")
        return df
    return df.loc[(df["Fecha_dia"].dt.date >= s) & (df["Fecha_dia"].dt.date <= e)].copy()


# ─────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────
def sidebar() -> Dict:
    st.sidebar.markdown(f"## 💧 {APP_TITLE.split('·')[0].strip()}")
    st.sidebar.markdown("---")
    st.sidebar.header("📁 Archivos DSS")

    dss_up = st.sidebar.file_uploader("DSS (SimulacionDSS…xlsx)", type=["xlsx", "xlsm"], key="dss_up")

    if st.sidebar.button("🔄 Recargar archivos", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    if dss_up:
        dss_bytes = dss_up.getvalue()
        dss_name  = dss_up.name
    else:
        dss_bytes, dss_path = read_first_local(DSS_NAMES)
        dss_name = dss_path.name if dss_path else "—"

    st.sidebar.caption(f"DSS: **{dss_name}** · búsqueda local: `data/` → carpeta del app")

    st.sidebar.header("⚙️ Ajustes")
    flow_unit = st.sidebar.radio(
        "🔁 Unidad de caudal / flujo",
        ["cfs", "m³/s", "hm³/d"], index=0,
        format_func=unit_label,
        help="p³/s = pies cúbicos por segundo · m³/s · hm³/d",
    )
    pct_ref_gat = st.sidebar.selectbox(
        "Percentil de referencia Gatún",
        PERCENTILE_ORDER, index=PERCENTILE_ORDER.index(50),
        format_func=lambda x: f"P{x}",
        key="pct_ref_gat",
        help="Percentil DSS de referencia para las pestañas y métricas de Gatún.",
    )
    pct_ref_alh = st.sidebar.selectbox(
        "Percentil de referencia Alhajuela/Madden",
        PERCENTILE_ORDER, index=PERCENTILE_ORDER.index(50),
        format_func=lambda x: f"P{x}",
        key="pct_ref_alh",
        help="Percentil DSS de referencia para las pestañas y métricas de Alhajuela/Madden.",
    )

    st.sidebar.header("🌫️ Caudal evaporado para ajuste AP DSS")
    evap_gat_cfs = st.sidebar.number_input(
        "Evaporación GAT (p³/s)",
        min_value=0.0, value=0.0, step=10.0, format="%.3f",
        help="Se suma al AP neto DSS de Gatún para estimar AP total DSS."
    )
    evap_alh_cfs = st.sidebar.number_input(
        "Evaporación ALHA (p³/s)",
        min_value=0.0, value=0.0, step=10.0, format="%.3f",
        help="Se suma al AP neto DSS de Alhajuela/Madden para estimar AP total DSS."
    )
    st.sidebar.caption("AP total DSS estimado = AP neto DSS + caudal evaporado.")

    st.sidebar.header("📖 Glosario")
    for var, desc in [
        ("NP", "Nivel proyectado (ft PLD)"),
        ("HP", "Hidrogeneración (MW)"),
        ("AP", "Aportes al embalse (p³/s)"),
        ("V",  "Vertidos / Spill (p³/s)"),
        ("EG", "Esclusaje Gatún"),
        ("EP", "Esclusaje Panamax"),
        ("P90…P5", "Prob. excedencia"),
    ]:
        st.sidebar.markdown(f"**{var}**: {desc}")

    st.sidebar.markdown("---")
    st.sidebar.caption(AUTHOR_NOTE)
    if "view_count" in st.session_state:
        st.sidebar.caption(f"👁️ Vistas: {int(st.session_state['view_count']):,}")

    return {
        "dss_bytes": dss_bytes,
        "flow_unit": flow_unit,
        "pct_ref_gat": int(pct_ref_gat),
        "pct_ref_alh": int(pct_ref_alh),
        # Compatibilidad con versiones anteriores: si alguna función antigua consulta pct_ref,
        # se usa Gatún como referencia por defecto.
        "pct_ref": int(pct_ref_gat),
        "evap_gat_cfs": float(evap_gat_cfs),
        "evap_alh_cfs": float(evap_alh_cfs),
    }


# ─────────────────────────────────────────────────────────────────────
# Métricas de cabecera
# ─────────────────────────────────────────────────────────────────────
def show_header_metrics(daily: pd.DataFrame, cfg: Dict, flow_unit: str,
                        obs_daily: Optional[pd.DataFrame] = None) -> None:
    if daily.empty:
        return
    token = cfg["token"]
    np_cols = cols_by_prefix(daily, "NP", token)
    hp_cols = cols_by_prefix(daily, "HP", token)
    ap_cols = cols_by_prefix(daily, "AP", token)

    np50 = next((c for c in np_cols if "50" in c), np_cols[0] if np_cols else None)
    hp50 = next((c for c in hp_cols if "50" in c), hp_cols[0] if hp_cols else None)
    ap50 = next((c for c in ap_cols if "50" in c), ap_cols[0] if ap_cols else None)

    today = pd.Timestamp.today().normalize()
    srt   = daily.sort_values("Fecha_dia")
    exact = srt[srt["Fecha_dia"] == today]
    rec   = exact.iloc[0] if not exact.empty else srt.iloc[-1]

    np50_v = float(rec.get(np50, np.nan)) if np50 else np.nan
    hp50_v = float(rec.get(hp50, np.nan)) if hp50 else np.nan
    ap50_v = float(rec.get(ap50, np.nan)) if ap50 else np.nan
    ap50_c = convert_flow(pd.Series([ap50_v]), flow_unit).iloc[0]

    # Último nivel observado
    obs_val, obs_date, closest = None, None, None
    if obs_daily is not None and not obs_daily.empty:
        obs_valid = obs_daily[obs_daily["Valor"].notna()].sort_values("Fecha_dia")
        if not obs_valid.empty:
            last_obs = obs_valid.iloc[-1]
            obs_val  = float(last_obs["Valor"])
            obs_date = pd.to_datetime(last_obs["Fecha_dia"])
            closest  = closest_np(daily, cfg, obs_date, obs_val)

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("📅 Referencia DSS", rec["Fecha_dia"].strftime("%d-%m-%Y"))
    if obs_val is not None:
        delta = f"Δ vs NP50: {obs_val - np50_v:+.3f} ft" if pd.notna(np50_v) else None
        c2.metric(f"🔴 Obs. {cfg['level_unit']}", f"{obs_val:,.3f}", delta=delta,
                  delta_color="inverse",
                  help=f"Último observado: {obs_date:%d-%m-%Y}" if obs_date else None)
    else:
        c2.metric("🔴 Obs. LKH", "—")
    c3.metric(f"NP50 ({cfg['level_unit']})", f"{np50_v:,.3f}" if pd.notna(np50_v) else "—")
    c4.metric("HP50 (MW)", f"{hp50_v:,.2f}" if pd.notna(hp50_v) else "—")
    c5.metric(f"AP50 ({unit_label(flow_unit)})", f"{ap50_c:,.2f}" if pd.notna(ap50_c) else "—")
    if closest:
        c6.metric("🎯 Percentil más cercano", closest["label"],
                  delta=f"Obs-DSS: {closest['diff']:+.3f} ft", delta_color="inverse",
                  help=f"NP DSS: {closest['dss_value']:.3f} ft · {closest['date']:%d-%m-%Y}")
    else:
        c6.metric("🎯 Percentil más cercano", "—")


def show_aporte_reservoir_metrics(
    daily: pd.DataFrame,
    cfg: Dict,
    flow_unit: str,
    pct_ref: int,
    obs_aportes: Optional[pd.DataFrame] = None,
    evap_cfs: float = 0.0,
) -> None:
    """Muestra aporte observado, AP DSS ajustado por evaporación y HP DSS recomendada."""
    if daily is None or daily.empty:
        return

    token = cfg["token"]
    ap_cols = cols_by_prefix(daily, "AP", token)
    hp_cols = cols_by_prefix(daily, "HP", token)
    if not ap_cols:
        return

    base = daily.copy()
    base["Fecha_dia"] = pd.to_datetime(base["Fecha_dia"], errors="coerce").dt.normalize()
    base = base[base["Fecha_dia"].notna()].sort_values("Fecha_dia")
    today = today_panama()

    exact = base[base["Fecha_dia"] == today]
    if not exact.empty:
        ref_row = exact.iloc[0]
    else:
        past = base[base["Fecha_dia"] <= today]
        ref_row = past.iloc[-1] if not past.empty else base.iloc[-1]

    ap_pct_map = ordered_percentile_map_by_value(base, ap_cols, ref_row=ref_row)
    # Columna AP de referencia visual según pct_ref
    ap_ref = next((c for c, p in ap_pct_map.items() if p == pct_ref), None)
    if ap_ref is None:
        ap_ref = next((c for c in ap_cols if exceedance_pct(c) == pct_ref), ap_cols[0])

    ap_dss_total_cfs = float(ref_row.get(ap_ref, np.nan)) + float(evap_cfs or 0.0) if ap_ref else np.nan
    ap_dss_total = convert_flow(pd.Series([ap_dss_total_cfs]), flow_unit).iloc[0] if pd.notna(ap_dss_total_cfs) else np.nan

    obs_val_cfs = np.nan
    obs_date = None
    if obs_aportes is not None and isinstance(obs_aportes, pd.DataFrame) and not obs_aportes.empty:
        obs = clamp_observed_future_dates(obs_aportes, "Fecha_dia")
        obs = obs[obs["Valor"].notna()].copy()
        obs["Fecha_dia"] = pd.to_datetime(obs["Fecha_dia"], errors="coerce").dt.normalize()
        obs = obs[obs["Fecha_dia"].notna()].sort_values("Fecha_dia")
        obs_past = obs[obs["Fecha_dia"] <= today]
        if not obs_past.empty:
            last_obs = obs_past.iloc[-1]
        elif not obs.empty:
            last_obs = obs.iloc[-1]
        else:
            last_obs = None
        if last_obs is not None:
            obs_val_cfs = float(last_obs["Valor"])
            obs_date = pd.to_datetime(last_obs["Fecha_dia"])

    obs_val = convert_flow(pd.Series([obs_val_cfs]), flow_unit).iloc[0] if pd.notna(obs_val_cfs) else np.nan
    nearest_obs = None
    if pd.notna(obs_val_cfs) and obs_date is not None:
        nearest_obs = _nearest_ap_percentile(base, cfg, obs_date, obs_val_cfs, dss_add_cfs=float(evap_cfs or 0.0))

    # Hidrogeneración DSS recomendada: usa el mismo percentil operativo del aporte más cercano.
    hp_rec_val = np.nan
    hp_rec_label = "—"
    if nearest_obs and hp_cols:
        raw_pct = nearest_obs.get("raw_percentile", nearest_obs.get("percentile", pct_ref))
        hp_col = next((c for c in hp_cols if exceedance_pct(c) == raw_pct), None)
        if hp_col is not None:
            hp_rec_val = float(ref_row.get(hp_col, np.nan))
            hp_rec_label = nearest_obs["label"]
    elif hp_cols:
        hp_col = next((c for c in hp_cols if exceedance_pct(c) == pct_ref), hp_cols[0])
        hp_rec_val = float(ref_row.get(hp_col, np.nan))
        hp_rec_label = f"P{pct_ref}"

    st.markdown("#### 🌧️ Aporte observado, AP DSS ajustado e hidrogeneración")
    st.caption(f"{SIMULATION_NOTE} · AP total DSS estimado = AP neto DSS + evaporación.")

    m1, m2, m3, m4, m5, m6 = st.columns([1.05, 0.85, 1.15, 1.05, 1.10, 1.05])
    m1.metric(
        f"Último aporte observado ({unit_label(flow_unit)})",
        f"{obs_val:,.2f}" if pd.notna(obs_val) else "—",
        help=f"Fecha: {obs_date:%d-%m-%Y}" if obs_date is not None else "Sin BulkExport de aporte observado.",
    )
    m2.metric("Fecha aporte obs.", f"{obs_date:%d-%m-%Y}" if obs_date is not None else "—")
    m3.metric("Evaporación aplicada (p³/s)", f"{float(evap_cfs or 0.0):,.1f}")
    m4.metric(
        f"AP total DSS P{ap_pct_map.get(ap_ref, exceedance_pct(ap_ref))} ({unit_label(flow_unit)})",
        f"{ap_dss_total:,.2f}" if pd.notna(ap_dss_total) else "—",
    )
    if nearest_obs:
        m5.metric(
            "Percentil AP más cercano",
            nearest_obs["label"],
            delta=f"Obs-DSS: {nearest_obs['diff_cfs']:+,.1f} p³/s",
            delta_color="inverse",
            help=f"AP total DSS cercano: {nearest_obs['dss_total_cfs']:,.1f} p³/s · Fecha DSS: {nearest_obs['date']:%d-%m-%Y}",
        )
    else:
        m5.metric("Percentil AP más cercano", "—")
    m6.metric(
        f"Hidrogeneración DSS recomendada ({hp_rec_label})",
        f"{hp_rec_val:,.2f} MW" if pd.notna(hp_rec_val) else "—",
    )


# ─────────────────────────────────────────────────────────────────────
# PESTAÑA 1 — GATÚN DSS
# PESTAÑA 2 — ALHAJUELA DSS
# ─────────────────────────────────────────────────────────────────────
def tab_reservoir(res_key: str, dss_bytes: bytes, flow_unit: str, pct_ref: int,
                  obs_niveles: Optional[pd.DataFrame] = None,
                  obs_aportes: Optional[pd.DataFrame] = None,
                  evap_cfs: float = 0.0) -> None:
    cfg = RESERVOIR_CONFIG[res_key]
    st.subheader(f"💧 {cfg['name']}")
    st.caption(PROJ_NOTE)

    try:
        dss_raw = load_dss_sheet(dss_bytes, cfg["sheet"])
    except Exception as exc:
        st.error(f"Error cargando DSS: {exc}")
        return

    daily = to_daily(dss_raw, cfg)
    if daily.empty:
        st.warning("No se pudo construir el diario DSS.")
        return

    with st.expander("🗓️ Filtro de período", expanded=True):
        filtered = date_filter(daily, f"{res_key}_res")

    show_header_metrics(filtered, cfg, flow_unit, obs_niveles)
    if obs_niveles is not None and not obs_niveles.empty:
        last = obs_niveles[obs_niveles["Valor"].notna()].sort_values("Fecha_dia")
        if not last.empty:
            st.caption(f"Último nivel observado disponible: "
                       f"{last.iloc[-1]['Fecha_dia']:%d-%m-%Y} · {last.iloc[-1]['Valor']:,.3f} ft")

    show_aporte_reservoir_metrics(filtered, cfg, flow_unit, pct_ref, obs_aportes, evap_cfs)
    st.markdown("---")

    token = cfg["token"]
    np_cols = cols_by_prefix(filtered, "NP", token)
    hp_cols = cols_by_prefix(filtered, "HP", token)
    ap_cols = cols_by_prefix(filtered, "AP", token)
    v_cols  = cols_by_prefix(filtered, "V",  token)

    # --- NP con observado ---
    st.markdown("### 📈 Nivel proyectado vs observado")
    default_np = [c for c in np_cols if any(x in c for x in ["50", "90", "10"])]
    sel_np = st.multiselect("Series NP", np_cols, default=default_np, key=f"{res_key}_np")

    obs_col_in_df = None
    if obs_niveles is not None and not obs_niveles.empty:
        # Merge nivel observado
        obs_merge = obs_niveles[["Fecha_dia", "Valor"]].rename(columns={"Valor": "Nivel obs."})
        plot_df = filtered.merge(obs_merge, on="Fecha_dia", how="left")
        obs_col_in_df = "Nivel obs."
    else:
        plot_df = filtered.copy()

    fan_chart(plot_df, sel_np,
              f"{cfg['name']} · Nivel diario DSS (ft PLD)", "ft PLD",
              f"{res_key}_np_plot", obs_col=obs_col_in_df, obs_label="Nivel obs. BulkExport")

    # --- HP ---
    if hp_cols:
        st.markdown("### ⚡ Hidrogeneración (MW)")
        sel_hp = st.multiselect("Series HP", hp_cols,
                                default=[c for c in hp_cols if any(x in c for x in ["50", "90", "10"])],
                                key=f"{res_key}_hp")
        fan_chart(filtered, sel_hp, f"{cfg['name']} · HP diario promedio", "MW",
                  f"{res_key}_hp_plot")

    # --- AP ---
    if ap_cols:
        st.markdown(f"### 🌊 Aportes — AP total DSS estimado "
                    f"<span class='badge'>{unit_label(flow_unit)}</span>",
                    unsafe_allow_html=True)
        st.caption(f"AP total DSS estimado = AP neto DSS + {float(evap_cfs or 0.0):,.1f} p³/s de evaporación. Se conserva el percentil original del DSS.")
        # Reetiquetar AP por magnitud: percentil alto arriba, percentil bajo abajo.
        ap_df_all, ordered_ap_cols_all, ap_pct_map = make_ordered_ap_columns(
            filtered, ap_cols, flow_unit, add_cfs=float(evap_cfs or 0.0)
        )
        pcts_available = sorted(set(ap_pct_map.values()), reverse=True)
        default_pcts = pcts_available
        sel_pcts = st.multiselect(
            "Percentiles AP",
            options=pcts_available,
            default=default_pcts,
            format_func=lambda x: f"P{x}",
            key=f"{res_key}_ap",
        )
        new_ap_cols = [c for c in ordered_ap_cols_all if exceedance_pct(c) in sel_pcts]

        obs_ap_col = None
        nearest_ap_info = None
        if obs_aportes is not None and isinstance(obs_aportes, pd.DataFrame) and not obs_aportes.empty:
            try:
                obs_ap = clamp_observed_future_dates(obs_aportes, "Fecha_dia")
                obs_ap = obs_ap[obs_ap["Valor"].notna()].copy()
                obs_ap["Fecha_dia"] = pd.to_datetime(obs_ap["Fecha_dia"], errors="coerce").dt.normalize()
                obs_ap = obs_ap[obs_ap["Fecha_dia"].notna()].sort_values("Fecha_dia")
                obs_ap = obs_ap.groupby("Fecha_dia", as_index=False).agg(Valor=("Valor", "last"))
                obs_ap_col = f"Aporte observado [{unit_label(flow_unit)}]"
                obs_ap[obs_ap_col] = convert_flow(obs_ap["Valor"], flow_unit)
                ap_df_all = ap_df_all.merge(obs_ap[["Fecha_dia", obs_ap_col]], on="Fecha_dia", how="left")

                obs_past = obs_ap[obs_ap["Fecha_dia"] <= today_panama()]
                if not obs_past.empty:
                    last_obs_ap = obs_past.iloc[-1]
                    nearest_ap_info = _nearest_ap_percentile(
                        filtered,
                        cfg,
                        pd.to_datetime(last_obs_ap["Fecha_dia"]),
                        float(last_obs_ap["Valor"]),
                        dss_add_cfs=float(evap_cfs or 0.0),
                    )
            except Exception as exc:
                st.warning(f"No se pudo agregar el aporte observado a la gráfica: {exc}")
                obs_ap_col = None

        if nearest_ap_info:
            st.caption(
                f"🎯 Según el **aporte observado**, el percentil AP DSS ajustado más cercano es "
                f"**{nearest_ap_info['label']}** "
                f"(Obs-DSS: {nearest_ap_info['diff_cfs']:+,.1f} p³/s; "
                f"fecha DSS: {nearest_ap_info['date']:%d-%m-%Y})."
            )

        fan_chart(ap_df_all, new_ap_cols,
                  f"{cfg['name']} · AP total DSS estimado y aporte observado ({unit_label(flow_unit)})",
                  unit_label(flow_unit), f"{res_key}_ap_plot",
                  obs_col=obs_ap_col, obs_label="Aporte observado")

    # --- V ---
    if v_cols:
        st.markdown(f"### 🚿 Vertidos — promedio diario "
                    f"<span class='badge'>{unit_label(flow_unit)}</span>",
                    unsafe_allow_html=True)
        sel_v = st.multiselect("Probabilidades V", v_cols,
                               default=[c for c in v_cols if any(x in c for x in ["50", "90", "10"])],
                               key=f"{res_key}_v")
        v_df = filtered.copy()
        new_v_cols = []
        for c in sel_v:
            nc = f"{c} [{unit_label(flow_unit)}]"
            v_df[nc] = convert_flow(v_df[c], flow_unit)
            new_v_cols.append(nc)
        fan_chart(v_df, new_v_cols,
                  f"{cfg['name']} · Vertidos diarios promedio ({unit_label(flow_unit)})",
                  unit_label(flow_unit), f"{res_key}_v_plot")

    # --- EG + EP (solo Gatún) ---
    if res_key == "gatun":
        eg_cols = cols_by_prefix(filtered, "EG", token)
        ep_cols = cols_by_prefix(filtered, "EP", token)
        if eg_cols or ep_cols:
            st.markdown(f"### 🚢 Consumo esclusajes EG+EP "
                        f"<span class='badge'>{unit_label(flow_unit)}</span>",
                        unsafe_allow_html=True)
            esc_df = filtered.copy()
            total_cols = []
            # Sum EG+EP por percentil
            pcts_found = sorted(
                set(exceedance_pct(c) for c in eg_cols + ep_cols), reverse=True
            )
            for pct in pcts_found:
                eg_c = next((c for c in eg_cols if exceedance_pct(c) == pct), None)
                ep_c = next((c for c in ep_cols if exceedance_pct(c) == pct), None)
                parts = [esc_df[c] for c in [eg_c, ep_c] if c and c in esc_df.columns]
                if not parts:
                    continue
                nc = f"Total esc P{pct} [{unit_label(flow_unit)}]"
                raw_sum = pd.concat(parts, axis=1).sum(axis=1, min_count=1)
                esc_df[nc] = convert_flow(raw_sum, flow_unit)
                total_cols.append(nc)
            sel_esc = st.multiselect(
                "Probabilidades esclusajes",
                [exceedance_pct(c) for c in eg_cols],
                default=[p for p in [90, 50, 10] if p in [exceedance_pct(c) for c in eg_cols]],
                format_func=lambda x: f"P{x}", key="gat_esc",
            )
            plot_esc_cols = [c for c in total_cols if any(f"P{p}" in c for p in sel_esc)]
            fan_chart(esc_df, plot_esc_cols,
                      f"Gatún · Esclusajes EG+EP ({unit_label(flow_unit)})",
                      unit_label(flow_unit), "gat_esc_plot", show_band=False)

    # --- Tabla diaria ---
    st.markdown("### 📋 Tabla diaria DSS")
    with st.expander("Ver tabla", expanded=False):
        st.dataframe(filtered, use_container_width=True, height=420)
        csv = filtered.to_csv(index=False).encode("utf-8-sig")
        st.download_button(f"⬇️ Descargar CSV — {cfg['name']}",
                           csv, f"{res_key}_dss_diario.csv", "text/csv", key=f"{res_key}_dl")


# ─────────────────────────────────────────────────────────────────────
# PESTAÑA 3 — MANEJO DE EMBALSES (decisión integrada)
# ─────────────────────────────────────────────────────────────────────
WEEKDAY_ES = {0:"Lunes",1:"Martes",2:"Miércoles",3:"Jueves",4:"Viernes",5:"Sábado",6:"Domingo"}


def _fmt(v, d: int = 3) -> str:
    try:
        return f"{float(v):,.{d}f}" if pd.notna(v) else "—"
    except Exception:
        return "—"


def _semaforo(diff_abs: float, warn: float, alert: float) -> str:
    if pd.isna(diff_abs):
        return "⚪ Sin dato"
    if diff_abs >= alert:
        return "🔴 Revisar"
    if diff_abs >= warn:
        return "🟠 Atención"
    return "🟢 En rango"


def tab_manejo(dss_bytes: bytes, flow_unit: str, pct_ref_gat: int, pct_ref_alh: int,
               obs_gat: Optional[pd.DataFrame], obs_alh: Optional[pd.DataFrame]) -> None:
    st.subheader("🧭 Manejo de embalses — apoyo a la decisión")
    st.caption(
        f"{PROJ_NOTE} · Gatún y Alhajuela/Madden se evalúan por separado. "
        f"Referencia: Gatún P{pct_ref_gat} · Alhajuela/Madden P{pct_ref_alh}."
    )

    c1, c2, c3 = st.columns(3)
    gat_threshold = c1.number_input(
        "Umbral operativo Gatún Δ nivel (ft)",
        min_value=0.01, value=0.60, step=0.05, key="mj_thr_gat"
    )
    alh_threshold = c2.number_input(
        "Umbral operativo Alhajuela / Madden Δ nivel (ft)",
        min_value=0.01, value=0.10, step=0.05, key="mj_thr_alh"
    )
    horizon  = c3.selectbox("Horizonte (días)", [7, 15, 30, 60, 90], index=2, key="mj_horiz")
    st.caption(
        "Criterio operativo: 🟠 Atención cuando |Δ nivel| alcanza 70% del umbral del embalse; "
        "🔴 Revisar cuando iguala o supera el umbral completo."
    )

    rows = []
    ts_map = {}
    for res_key, obs_df in [("gatun", obs_gat), ("alhajuela", obs_alh)]:
        cfg = RESERVOIR_CONFIG[res_key]
        pct_ref = int(pct_ref_gat if res_key == "gatun" else pct_ref_alh)
        try:
            raw    = load_dss_sheet(dss_bytes, cfg["sheet"])
            daily  = to_daily(raw, cfg)
        except Exception as exc:
            st.warning(f"{cfg['name']}: error DSS — {exc}")
            continue
        if daily.empty:
            continue

        token   = cfg["token"]
        np_cols = cols_by_prefix(daily, "NP", token)
        ap_cols = cols_by_prefix(daily, "AP", token)
        v_cols  = cols_by_prefix(daily, "V",  token)
        hp_cols = cols_by_prefix(daily, "HP", token)

        np_col = next((c for c in np_cols if exceedance_pct(c) == pct_ref), np_cols[0] if np_cols else None)
        ap_col = next((c for c in ap_cols if exceedance_pct(c) == pct_ref), ap_cols[0] if ap_cols else None)
        v_col  = next((c for c in v_cols  if exceedance_pct(c) == pct_ref), v_cols[0]  if v_cols  else None)
        hp_col = next((c for c in hp_cols if exceedance_pct(c) == pct_ref), hp_cols[0] if hp_cols else None)

        # Último observado
        obs_val, obs_date = None, None
        if obs_df is not None and not obs_df.empty:
            valid = obs_df[obs_df["Valor"].notna()].sort_values("Fecha_dia")
            if not valid.empty:
                obs_val  = float(valid.iloc[-1]["Valor"])
                obs_date = pd.to_datetime(valid.iloc[-1]["Fecha_dia"])

        closest = closest_np(daily, cfg, obs_date, obs_val) if obs_val is not None else None

        # Fila DSS más cercana al observado (o último)
        today = pd.Timestamp.today().normalize()
        ref_date = obs_date.normalize() if obs_date is not None else today
        base = daily.sort_values("Fecha_dia")
        exact = base[base["Fecha_dia"] == ref_date]
        row_dss = exact.iloc[0] if not exact.empty else base.loc[(base["Fecha_dia"] - ref_date).abs().idxmin()]

        np_v  = float(row_dss.get(np_col, np.nan))  if np_col  else np.nan
        ap_v  = convert_flow(pd.Series([float(row_dss.get(ap_col, np.nan))]), flow_unit).iloc[0] if ap_col else np.nan
        v_v   = convert_flow(pd.Series([float(row_dss.get(v_col, np.nan))]), flow_unit).iloc[0]  if v_col  else np.nan
        hp_v  = float(row_dss.get(hp_col, np.nan))  if hp_col  else np.nan

        diff_np = float(obs_val) - np_v if obs_val is not None and pd.notna(np_v) else np.nan
        threshold_ft = gat_threshold if res_key == "gatun" else alh_threshold
        semaforo = _semaforo(
            abs(diff_np) if pd.notna(diff_np) else np.nan,
            threshold_ft * 0.70,
            threshold_ft,
        )

        # Métricas del horizonte
        today_dt = pd.Timestamp.today().normalize()
        future = base[base["Fecha_dia"] >= today_dt].head(horizon)
        if future.empty:
            future = base.tail(horizon)
        ap_prom = convert_flow(future[ap_col], flow_unit).mean() if ap_col and ap_col in future else np.nan
        v_prom  = convert_flow(future[v_col], flow_unit).mean()  if v_col and v_col in future else np.nan
        hp_prom = future[hp_col].mean() if hp_col and hp_col in future else np.nan
        np_start = float(future[np_col].iloc[0])  if np_col and np_col in future and not future.empty else np.nan
        np_end   = float(future[np_col].iloc[-1]) if np_col and np_col in future and not future.empty else np.nan

        rows.append({
            "Embalse":                   cfg["name"],
            "Estado":                    semaforo,
            "Obs. LKH (ft)":             _fmt(obs_val),
            "Fecha obs.":                f"{obs_date:%d-%m-%Y}" if obs_date else "—",
            f"NP{pct_ref} DSS (ft)":     _fmt(np_v),
            "Percentil más cercano":     closest["label"] if closest else "—",
            "Umbral embalse (ft)":      _fmt(threshold_ft, 3),
            "Umbral embalse (ft)":      _fmt(threshold_ft, 3),
            f"Δ Obs-NP{pct_ref} (ft)":   _fmt(diff_np, 3),
            f"AP{pct_ref} ({unit_label(flow_unit)})": _fmt(ap_v, 2),
            f"V{pct_ref} ({unit_label(flow_unit)})":  _fmt(v_v, 2),
            f"HP{pct_ref} (MW)":         _fmt(hp_v, 2),
            f"AP prom. {horizon}d ({unit_label(flow_unit)})": _fmt(ap_prom, 2),
            f"V prom. {horizon}d ({unit_label(flow_unit)})":  _fmt(v_prom, 2),
            f"HP prom. {horizon}d (MW)": _fmt(hp_prom, 2),
            f"NP inicio horiz. (ft)":    _fmt(np_start, 3),
            f"NP fin horiz. (ft)":       _fmt(np_end, 3),
            f"Δ NP horiz. (ft)":         _fmt(np_end - np_start, 3) if pd.notna(np_start) and pd.notna(np_end) else "—",
        })
        ts_map[cfg["name"]] = (daily, obs_df, cfg)

    if rows:
        st.markdown("#### Estado ejecutivo")
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # Gráficas individuales
    st.markdown("---")
    st.markdown("#### Tendencia por embalse")
    foco = st.selectbox("Embalse a graficar", ["Ambos", "Gatún", "Alhajuela / Madden"], key="mj_foco")

    with st.expander("🗓️ Filtro de período para gráficas", expanded=True):
        all_dates = []
        for name, (d, _, _) in ts_map.items():
            if not d.empty:
                all_dates.extend([d["Fecha_dia"].min(), d["Fecha_dia"].max()])
        if all_dates:
            mn, mx = min(all_dates).date(), max(all_dates).date()
            fc1, fc2 = st.columns(2)
            s = fc1.date_input("Desde", value=mn, min_value=mn, max_value=mx, key="mj_s")
            e = fc2.date_input("Hasta", value=mx, min_value=mn, max_value=mx, key="mj_e")

    for name, (daily, obs_df, cfg) in ts_map.items():
        if foco not in ("Ambos", name):
            continue
        pct_ref = int(pct_ref_gat if cfg.get("token") == "GAT" else pct_ref_alh)
        token = cfg["token"]
        np_cols = cols_by_prefix(daily, "NP", token)
        np_col  = next((c for c in np_cols if exceedance_pct(c) == pct_ref), np_cols[0] if np_cols else None)
        if not np_col:
            continue

        try:
            filt = daily[(daily["Fecha_dia"].dt.date >= s) & (daily["Fecha_dia"].dt.date <= e)].copy()
        except Exception:
            filt = daily.copy()

        # Merge observado
        obs_col_in_df = None
        if obs_df is not None and not obs_df.empty:
            om = obs_df[["Fecha_dia", "Valor"]].rename(columns={"Valor": "Nivel obs."})
            filt = filt.merge(om, on="Fecha_dia", how="left")
            obs_col_in_df = "Nivel obs."

        if not PLOTLY_OK:
            st.line_chart(filt.set_index("Fecha_dia")[[np_col]])
            continue

        fig = go.Figure()
        # Todos los NP en gris fino, el de referencia en azul, observado en rojo
        for col in np_cols:
            pct = exceedance_pct(col)
            is_ref = (pct == pct_ref)
            fig.add_trace(go.Scatter(
                x=filt["Fecha_dia"], y=filt[col], mode="lines",
                name=f"P{pct}",
                line=dict(
                    color=EXCEEDANCE_COLORS.get(pct, "#aaa"),
                    width=2.5 if is_ref else 0.8,
                    dash="solid" if is_ref else "dot",
                ),
                opacity=1.0 if is_ref else 0.4,
            ))

        if obs_col_in_df and obs_col_in_df in filt.columns:
            obs_v = filt[filt[obs_col_in_df].notna()].copy()
            if not obs_v.empty:
                labels = [""] * len(obs_v)
                labels[-1] = f"{obs_v[obs_col_in_df].iloc[-1]:,.2f} ft"
                fig.add_trace(go.Scatter(
                    x=obs_v["Fecha_dia"], y=obs_v[obs_col_in_df],
                    mode="lines+markers+text", name="🔴 Nivel obs.",
                    text=labels, textposition="top right",
                    line=dict(color="#d90429", width=5),
                    marker=dict(size=9, color="#d90429", line=dict(width=2, color="white")),
                    connectgaps=True,
                ))
                fig.add_trace(go.Scatter(
                    x=[obs_v["Fecha_dia"].iloc[-1]], y=[obs_v[obs_col_in_df].iloc[-1]],
                    mode="markers", name="📍 Último obs.",
                    marker=dict(size=22, color="#d90429", symbol="star",
                                line=dict(width=2, color="white")),
                ))

        _today_line(fig, filt["Fecha_dia"])
        fig.update_layout(**_base_layout(
            f"{name} · Nivel proyectado P{pct_ref} vs observado (ft PLD)",
            "ft PLD", height=580,
        ))
        st.plotly_chart(fig, use_container_width=True, key=f"mj_np_{cfg['token']}")


# ─────────────────────────────────────────────────────────────────────
# PESTAÑA 4 — APORTES OBSERVADOS vs DSS
# ─────────────────────────────────────────────────────────────────────

def _valid_df(df: Optional[pd.DataFrame]) -> bool:
    """Evita errores de evaluación booleana de DataFrame."""
    return df is not None and isinstance(df, pd.DataFrame) and not df.empty


def _df_or_empty(df: Optional[pd.DataFrame]) -> pd.DataFrame:
    """Devuelve un DataFrame válido sin usar `df or DataFrame()`."""
    return df.copy() if _valid_df(df) else pd.DataFrame()



def _nearest_ap_percentile(
    daily: pd.DataFrame,
    cfg: Dict,
    ref_date: pd.Timestamp,
    obs_total_cfs: float,
    dss_add_cfs: float = 0.0,
) -> Optional[Dict]:
    """Busca el percentil AP DSS TOTAL más cercano al aporte observado total.

    El DSS trae AP neto. Para comparar contra un aporte total observado:
        AP total DSS estimado = AP neto DSS + evaporación (p³/s)
    """
    if daily is None or daily.empty or ref_date is None or pd.isna(obs_total_cfs):
        return None
    ap_cols = cols_by_prefix(daily, "AP", cfg["token"])
    if not ap_cols:
        return None

    base = daily.copy()
    base["Fecha_dia"] = pd.to_datetime(base["Fecha_dia"], errors="coerce").dt.normalize()
    base = base[base["Fecha_dia"].notna()].sort_values("Fecha_dia")
    if base.empty:
        return None

    ref_ts = pd.to_datetime(ref_date).normalize()
    exact = base[base["Fecha_dia"] == ref_ts]
    if not exact.empty:
        row = exact.iloc[0]
        exact_date = True
    else:
        row = base.loc[(base["Fecha_dia"] - ref_ts).abs().idxmin()]
        exact_date = False

    candidates = []
    evap = max(float(dss_add_cfs or 0.0), 0.0)
    for col in ap_cols:
        val = pd.to_numeric(pd.Series([row.get(col, np.nan)]), errors="coerce").iloc[0]
        if pd.notna(val):
            dss_total = float(val) + evap
            candidates.append((col, dss_total, abs(float(obs_total_cfs) - dss_total)))
    if not candidates:
        return None

    best_col, best_val, abs_diff = min(candidates, key=lambda x: x[2])
    display_pct = exceedance_pct(best_col)
    diff = float(obs_total_cfs) - best_val
    rel = abs(diff) / max(abs(float(obs_total_cfs)), 1e-9) * 100
    estado = "🟢 Muy cercano" if rel <= 10 else ("🟠 Seguimiento" if rel <= 25 else "🔴 Revisar")
    return {
        "column": best_col,
        "raw_percentile": exceedance_pct(best_col),
        "percentile": int(display_pct),
        "label": f"P{int(display_pct)}",
        "dss_total_cfs": best_val,
        "dss_cfs": best_val,  # compatibilidad
        "diff_cfs": diff,
        "rel_pct": rel,
        "estado": estado,
        "date": pd.to_datetime(row["Fecha_dia"]),
        "exact_date": exact_date,
        "evap_cfs": evap,
    }



def tab_aporte_obs_embalse(
    res_key: str,
    dss_bytes: bytes,
    flow_unit: str,
    pct_ref: int,
    obs_df: Optional[pd.DataFrame],
    evap_cfs: float = 0.0,
) -> None:
    """Pestaña individual: aporte total observado vs AP total DSS estimado.

    El DSS se maneja como AP neto. Para comparar con los BulkExport de aportes
    totales, el usuario ingresa el caudal evaporado en p³/s y la app calcula:
        AP total DSS estimado = AP neto DSS + evaporación
    """
    cfg = RESERVOIR_CONFIG[res_key]
    embalse = cfg["name"]
    token = cfg["token"]
    st.subheader(f"🌧️ Aporte observado {token} — {embalse}")
    st.caption(
        "Comparación simple en **aportes totales**: "
        "**AP total DSS estimado = AP neto DSS + evaporación**."
    )
    st.caption(SIMULATION_NOTE)
    st.caption("Se conserva el orden original de percentiles del DSS: P95 representa menor aporte y P5 mayor aporte, si así viene en la simulación.")

    try:
        raw = load_dss_sheet(dss_bytes, cfg["sheet"])
        daily = to_daily(raw, cfg)
    except Exception as exc:
        st.error(f"Error cargando DSS {embalse}: {exc}")
        return

    if daily is None or daily.empty:
        st.warning("No se pudo construir el diario DSS.")
        return

    ap_cols = cols_by_prefix(daily, "AP", token)
    if not ap_cols:
        st.warning(f"No se encontraron columnas AP para {embalse}.")
        return

    st.markdown("#### AP neto DSS ajustado con caudal evaporado")
    show_obs_total = st.checkbox("Mostrar aporte observado", value=True, key=f"show_obs_total_{res_key}")
    show_dss_neto = st.checkbox("Mostrar AP neto DSS de referencia", value=False, key=f"show_dss_neto_{res_key}")
    st.info(
        f"Caudal evaporado aplicado desde la barra lateral: **{float(evap_cfs or 0.0):,.3f} p³/s**. "
        f"Fórmula: **AP total DSS estimado = AP neto DSS + caudal evaporado**."
    )

    # Período recomendado: si hay observado, enfocar la gráfica alrededor del observado.
    date_parts = [daily["Fecha_dia"]]
    obs_dates = None
    if _valid_df(obs_df):
        obs_dates = pd.to_datetime(obs_df["Fecha_dia"], errors="coerce").dropna()
        if not obs_dates.empty:
            date_parts.append(obs_dates)
    all_dates = pd.concat(date_parts)
    mn, mx = all_dates.min().date(), all_dates.max().date()

    if obs_dates is not None and not obs_dates.empty:
        obs_max = obs_dates.max().date()
        default_s = max(mn, (pd.Timestamp(obs_max) - pd.Timedelta(days=45)).date())
        default_e = min(mx, max(obs_max, min(mx, (pd.Timestamp(obs_max) + pd.Timedelta(days=30)).date())))
    else:
        default_s, default_e = mn, mx

    c1, c2 = st.columns(2)
    s = c1.date_input("Desde", value=default_s, min_value=mn, max_value=mx, key=f"ao_{res_key}_s")
    e = c2.date_input("Hasta", value=default_e, min_value=mn, max_value=mx, key=f"ao_{res_key}_e")
    if s > e:
        st.warning("Fecha inicial mayor que final. Se usa todo el período disponible.")
        s, e = mn, mx

    try:
        daily_f = daily[(daily["Fecha_dia"].dt.date >= s) & (daily["Fecha_dia"].dt.date <= e)].copy()
    except Exception:
        daily_f = daily.copy()

    obs_f = pd.DataFrame(columns=["Fecha_dia", "Valor", "Fuente"])
    if _valid_df(obs_df):
        try:
            obs_f = obs_df[(obs_df["Fecha_dia"].dt.date >= s) & (obs_df["Fecha_dia"].dt.date <= e)].copy()
        except Exception:
            obs_f = obs_df.copy()

    if not obs_f.empty:
        obs_f["Fecha_dia"] = pd.to_datetime(obs_f["Fecha_dia"], errors="coerce").dt.normalize()
        obs_f["Aporte total observado (p³/s)"] = pd.to_numeric(obs_f["Valor"], errors="coerce")
        obs_f = obs_f.dropna(subset=["Fecha_dia", "Aporte total observado (p³/s)"]).sort_values("Fecha_dia")

    ap_pct_map = ordered_percentile_map_by_value(daily, ap_cols)
    pcts_available = sorted(set(ap_pct_map.values()), reverse=True)
    default_p = [p for p in [90, 50, 10] if p in pcts_available] or pcts_available[:3]
    sel_pcts = st.multiselect(
        f"Percentiles AP total DSS estimado — {embalse}",
        pcts_available,
        default=default_p,
        format_func=lambda x: f"P{x}",
        key=f"ap_obs_{res_key}",
    )

    # Métricas del último observado total.
    if not obs_f.empty and obs_f["Aporte total observado (p³/s)"].notna().any():
        valid_obs = obs_f.dropna(subset=["Aporte total observado (p³/s)"]).sort_values("Fecha_dia")
        last = valid_obs.iloc[-1]
        last_total_cfs = float(last["Aporte total observado (p³/s)"])
        last_date = pd.to_datetime(last["Fecha_dia"])
        nearest = _nearest_ap_percentile(daily, cfg, last_date, last_total_cfs, dss_add_cfs=float(evap_cfs))

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Último aporte total obs. (p³/s)", f"{last_total_cfs:,.1f}")
        m2.metric("Evap. sumada al DSS (p³/s)", f"{evap_cfs:,.1f}")
        if nearest:
            m3.metric("AP total DSS cercano (p³/s)", f"{nearest['dss_total_cfs']:,.1f}")
        else:
            m3.metric("AP total DSS cercano (p³/s)", "—")
        m4.metric("Fecha obs.", f"{last_date:%d-%m-%Y}")
        if nearest:
            m5.metric(
                "Percentil DSS cercano",
                nearest["label"],
                delta=f"Obs-DSS total: {nearest['diff_cfs']:+,.1f} p³/s",
                delta_color="inverse",
                help=f"{nearest['estado']} · AP total DSS {nearest['label']}: {nearest['dss_total_cfs']:,.1f} p³/s · "
                     f"Fecha DSS: {nearest['date']:%d-%m-%Y}",
            )
    else:
        st.warning(
            f"No hay aportes observados para {embalse}. Cargue un BulkExport de aporte "
            "o use la entrada manual opcional."
        )

    if not PLOTLY_OK:
        st.info("Plotly no disponible.")
        return

    fig = go.Figure()

    # AP total DSS estimado = AP neto DSS + evaporación.
    # Se usa etiqueta operativa por magnitud: P alto arriba, P bajo abajo.
    for col in ap_cols:
        pct = ap_pct_map.get(col, exceedance_pct(col))
        if pct not in sel_pcts:
            continue
        dss_total_cfs = pd.to_numeric(daily_f[col], errors="coerce") + float(evap_cfs or 0.0)
        vals_total = convert_flow(dss_total_cfs, flow_unit)
        fig.add_trace(go.Scatter(
            x=daily_f["Fecha_dia"],
            y=vals_total,
            mode="lines",
            name=f"AP total DSS est. P{pct}",
            line=dict(
                width=3.2 if pct == pct_ref else (2.5 if pct == 50 else 1.4),
                dash="solid" if pct in (pct_ref, 50) else "dot",
                color=EXCEEDANCE_COLORS.get(pct, "#aaa"),
            ),
            hovertemplate="Fecha: %{x|%d-%m-%Y}<br>AP total DSS: %{y:,.2f}<extra></extra>",
        ))

    if show_dss_neto:
        ref_col = next((c for c in ap_cols if exceedance_pct(c) == pct_ref), None)
        if ref_col and ref_col in daily_f.columns:
            vals_net = convert_flow(daily_f[ref_col], flow_unit)
            fig.add_trace(go.Scatter(
                x=daily_f["Fecha_dia"],
                y=vals_net,
                mode="lines",
                name=f"AP neto DSS P{pct_ref}",
                line=dict(color="#64748b", width=1.8, dash="dash"),
                opacity=0.7,
            ))

    if show_obs_total and not obs_f.empty:
        obs_v = obs_f.dropna(subset=["Aporte total observado (p³/s)"]).sort_values("Fecha_dia")
        if not obs_v.empty:
            y_total = convert_flow(obs_v["Aporte total observado (p³/s)"], flow_unit)
            labels_total = [""] * len(obs_v)
            labels_total[-1] = f"Obs {y_total.iloc[-1]:,.1f}"
            fig.add_trace(go.Scatter(
                x=obs_v["Fecha_dia"],
                y=y_total,
                mode="lines+markers+text",
                name="🔴 Aporte total observado",
                text=labels_total,
                textposition="top right",
                line=dict(color="#d90429", width=5),
                marker=dict(size=9, color="#d90429", line=dict(width=2, color="white")),
                connectgaps=True,
                hovertemplate="Fecha: %{x|%d-%m-%Y}<br>Aporte observado: %{y:,.2f}<extra></extra>",
            ))
            fig.add_trace(go.Scatter(
                x=[obs_v["Fecha_dia"].iloc[-1]],
                y=[y_total.iloc[-1]],
                mode="markers",
                name="📍 Último observado",
                marker=dict(size=22, color="#d90429", symbol="star", line=dict(width=2, color="white")),
            ))

    # Ajuste de eje Y para que ALHA y GAT no se aplasten por valores extremos aislados.
    y_sources = []
    for tr in fig.data:
        try:
            y_arr = pd.to_numeric(pd.Series(tr.y), errors="coerce").dropna()
            if not y_arr.empty:
                y_sources.append(y_arr)
        except Exception:
            pass
    if y_sources:
        y_all = pd.concat(y_sources)
        if not y_all.empty:
            y_min = float(y_all.quantile(0.02))
            y_max = float(y_all.quantile(0.98))
            if y_max > y_min:
                pad = max((y_max - y_min) * 0.12, 1.0)
                fig.update_yaxes(range=[max(0, y_min - pad), y_max + pad])

    _today_line(fig, daily_f["Fecha_dia"])
    fig.update_layout(**_base_layout(
        f"{embalse} · Aporte total observado vs AP total DSS estimado ({unit_label(flow_unit)})",
        unit_label(flow_unit),
        height=650,
    ))
    st.plotly_chart(fig, use_container_width=True, key=f"ao_{res_key}_plot")

    with st.expander("📋 Tabla de aporte observado y AP total DSS estimado", expanded=False):
        rows = []
        if not obs_f.empty:
            table = obs_f.copy()
            table["Aporte total observado ({})".format(unit_label(flow_unit))] = convert_flow(
                table["Aporte total observado (p³/s)"], flow_unit
            )
            table["Evaporación sumada al DSS (p³/s)"] = float(evap_cfs)
            table = table.rename(columns={"Fecha_dia": "Fecha"})
            for _, r in table.iterrows():
                rows.append({
                    "Fecha": r.get("Fecha"),
                    "Fuente": r.get("Fuente", "—"),
                    "Aporte total observado (p³/s)": r.get("Aporte total observado (p³/s)", np.nan),
                    f"Aporte total observado ({unit_label(flow_unit)})": r.get(
                        "Aporte total observado ({})".format(unit_label(flow_unit)), np.nan
                    ),
                    "Evaporación sumada al DSS (p³/s)": float(evap_cfs),
                })
        if rows:
            out = pd.DataFrame(rows)
            for c in out.columns:
                if c not in ("Fecha", "Fuente"):
                    out[c] = pd.to_numeric(out[c], errors="coerce").round(3)
            st.dataframe(out, use_container_width=True, hide_index=True, height=420)
            csv = out.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                f"⬇️ Descargar CSV aporte {token}",
                csv,
                f"aporte_{token}_total_observado_vs_dss.csv",
                "text/csv",
                key=f"ao_{res_key}_dl",
            )
        else:
            st.info("Sin datos observados para mostrar en tabla.")


def tab_aportes_obs(dss_bytes: bytes, flow_unit: str, pct_ref: int,
                    obs_gat: Optional[pd.DataFrame], obs_alh: Optional[pd.DataFrame]) -> None:
    """Vista contenedora conservada por compatibilidad: una subpestaña por embalse."""
    st.subheader("🌧️ Aportes observados separados por embalse")
    sub = st.tabs(["GAT · Gatún", "ALHA · Alhajuela/Madden"])
    with sub[0]:
        tab_aporte_obs_embalse("gatun", dss_bytes, flow_unit, pct_ref, obs_gat)
    with sub[1]:
        tab_aporte_obs_embalse("alhajuela", dss_bytes, flow_unit, pct_ref, obs_alh)


# ─────────────────────────────────────────────────────────────────────
# PESTAÑA 5 — NIVELES OBSERVADOS
# ─────────────────────────────────────────────────────────────────────
def tab_niveles_obs(obs_gat: Optional[pd.DataFrame], obs_alh: Optional[pd.DataFrame]) -> None:
    st.subheader("🔴 Niveles observados — Gatún y Alhajuela/Madden")
    st.caption("Cargados desde BulkExport-GAT y BulkExport-MAD.")

    if (obs_gat is None or obs_gat.empty) and (obs_alh is None or obs_alh.empty):
        st.warning("No hay datos de nivel observado. Cargue BulkExport-GAT.csv y BulkExport-MAD.csv.")
        return

    # Métricas
    m1, m2, m3, m4 = st.columns(4)
    for metric_cols, obs_df, label, color in [
        ((m1, m2), obs_gat, "Gatún", "#d90429"),
        ((m3, m4), obs_alh, "Alhajuela/Madden", "#f97316"),
    ]:
        if obs_df is not None and not obs_df.empty:
            valid = obs_df[obs_df["Valor"].notna()].sort_values("Fecha_dia")
            if not valid.empty:
                last_v    = float(valid.iloc[-1]["Valor"])
                last_d    = pd.to_datetime(valid.iloc[-1]["Fecha_dia"])
                prev_v    = float(valid.iloc[-2]["Valor"]) if len(valid) >= 2 else np.nan
                cambio    = last_v - prev_v if pd.notna(prev_v) else None
                metric_cols[0].metric(f"🔴 {label} (ft)", f"{last_v:,.3f}",
                                      delta=f"{cambio:+.3f} ft/día" if cambio is not None else None)
                metric_cols[1].metric("Fecha", f"{last_d:%d-%m-%Y}")
        else:
            metric_cols[0].metric(label, "—")
            metric_cols[1].metric("Fecha", "—")

    # Filtro
    all_dates = []
    for obs_df in [obs_gat, obs_alh]:
        if obs_df is not None and not obs_df.empty:
            all_dates.extend([obs_df["Fecha_dia"].min(), obs_df["Fecha_dia"].max()])
    if not all_dates:
        return
    mn, mx = min(all_dates).date(), max(all_dates).date()
    default_s = max(mn, (pd.Timestamp(mx) - pd.Timedelta(days=60)).date())
    c1, c2 = st.columns(2)
    s = c1.date_input("Desde", value=default_s, min_value=mn, max_value=mx, key="nobs_s")
    e = c2.date_input("Hasta", value=mx, min_value=mn, max_value=mx, key="nobs_e")

    def _filt_obs(df):
        if df is None or df.empty:
            return None
        return df[(df["Fecha_dia"].dt.date >= s) & (df["Fecha_dia"].dt.date <= e)].copy()

    obs_gat_f = _filt_obs(obs_gat)
    obs_alh_f = _filt_obs(obs_alh)

    if not PLOTLY_OK:
        st.info("Instala plotly para ver las gráficas.")
        return

    # Vista conjunta (dos ejes)
    st.markdown("### Vista conjunta — ejes separados")
    fig = go.Figure()
    for obs_df, label, color, yaxis in [
        (obs_gat_f, "Gatún", "#d90429", "y"),
        (obs_alh_f, "Alhajuela/Madden", "#f97316", "y2"),
    ]:
        if obs_df is not None and not obs_df.empty:
            valid = obs_df[obs_df["Valor"].notna()].sort_values("Fecha_dia")
            labels = [""] * len(valid)
            if len(labels):
                labels[-1] = f"{label} {valid['Valor'].iloc[-1]:,.2f} ft"
            fig.add_trace(go.Scatter(
                x=valid["Fecha_dia"], y=valid["Valor"],
                mode="lines+markers+text", name=f"🔴 {label}",
                text=labels, textposition="top left",
                line=dict(color=color, width=6),
                marker=dict(size=9, color=color, line=dict(width=2, color="white")),
                connectgaps=True, yaxis=yaxis,
            ))
            fig.add_trace(go.Scatter(
                x=[valid["Fecha_dia"].iloc[-1]], y=[valid["Valor"].iloc[-1]],
                mode="markers", name=f"📍 Último {label}",
                marker=dict(size=22, color=color, symbol="star",
                            line=dict(width=2, color="white")),
                yaxis=yaxis,
            ))

    all_obs = pd.concat([_df_or_empty(obs_gat_f), _df_or_empty(obs_alh_f)], ignore_index=True)
    _today_line(fig, all_obs.get("Fecha_dia", pd.Series(dtype="datetime64[ns]")))
    fig.update_layout(
        title="Niveles observados — Gatún y Alhajuela/Madden",
        height=650, hovermode="x unified",
        yaxis=dict(title="Gatún (ft PLD)", gridcolor="rgba(0,0,0,0.07)"),
        yaxis2=dict(title="Alhajuela/Madden (ft PLD)", overlaying="y", side="right", showgrid=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        plot_bgcolor="rgba(250,252,255,1)", paper_bgcolor="rgba(250,252,255,0)",
        margin=dict(l=10, r=10, t=80, b=10),
    )
    st.plotly_chart(fig, use_container_width=True, key="nobs_two")

    # Tabla
    with st.expander("📋 Tabla de niveles observados", expanded=False):
        frames = []
        for obs_df, label in [(obs_gat, "Gatún"), (obs_alh, "Alhajuela/Madden")]:
            if obs_df is not None and not obs_df.empty:
                tmp = obs_df[obs_df["Valor"].notna()].copy()
                tmp["Embalse"] = label
                tmp["Cambio (ft/día)"] = tmp["Valor"].diff()
                tmp = tmp.rename(columns={"Valor": "Nivel obs. (ft)", "Fecha_dia": "Fecha"})
                frames.append(tmp[["Fecha", "Embalse", "Nivel obs. (ft)", "Cambio (ft/día)"]].tail(30))
        if frames:
            t = pd.concat(frames, ignore_index=True).sort_values("Fecha")
            for col in ["Nivel obs. (ft)", "Cambio (ft/día)"]:
                t[col] = pd.to_numeric(t[col], errors="coerce").round(3)
            st.dataframe(t, use_container_width=True, hide_index=True, height=420)
            csv = t.to_csv(index=False).encode("utf-8-sig")
            st.download_button("⬇️ CSV niveles observados", csv,
                               "niveles_observados.csv", "text/csv", key="nobs_dl")


# ─────────────────────────────────────────────────────────────────────
# PESTAÑA 6 — COMPARATIVO rápido
# ─────────────────────────────────────────────────────────────────────
def tab_comparativo(dss_bytes: bytes, flow_unit: str, pct_ref_gat: int, pct_ref_alh: int,
                    obs_gat: Optional[pd.DataFrame], obs_alh: Optional[pd.DataFrame],
                    obs_gat_aporte: Optional[pd.DataFrame] = None,
                    obs_alh_aporte: Optional[pd.DataFrame] = None,
                    evap_gat_cfs: float = 0.0,
                    evap_alh_cfs: float = 0.0) -> None:
    st.subheader("🔀 Comparativo Gatún vs Alhajuela")
    st.caption("Comparación visual por embalse. En AP se incorporan los aportes observados disponibles.")

    var_choice = st.selectbox("Variable", ["NP (Nivel)", "AP (Aportes)", "V (Vertidos)", "HP (Hidrogeneración)"],
                              key="cmp_var")
    prefix = var_choice.split()[0]
    default_cmp_pcts = []
    for p in [int(pct_ref_gat), int(pct_ref_alh), 90, 10]:
        if p in PERCENTILE_ORDER and p not in default_cmp_pcts:
            default_cmp_pcts.append(p)
    pcts   = st.multiselect("Probabilidades", PERCENTILE_ORDER, default=default_cmp_pcts or [50, 90, 10],
                             format_func=lambda x: f"P{x}", key="cmp_pcts")

    try:
        gat_raw = load_dss_sheet(dss_bytes, RESERVOIR_CONFIG["gatun"]["sheet"])
        alh_raw = load_dss_sheet(dss_bytes, RESERVOIR_CONFIG["alhajuela"]["sheet"])
    except Exception as exc:
        st.error(f"Error: {exc}")
        return

    gat_d = to_daily(gat_raw, RESERVOIR_CONFIG["gatun"])
    alh_d = to_daily(alh_raw, RESERVOIR_CONFIG["alhajuela"])
    if gat_d.empty or alh_d.empty:
        st.warning("No hay datos DSS suficientes para el comparativo.")
        return

    with st.expander("🗓️ Filtro de período", expanded=True):
        date_series = [gat_d["Fecha_dia"], alh_d["Fecha_dia"]]
        for odf in [obs_gat, obs_alh, obs_gat_aporte, obs_alh_aporte]:
            if _valid_df(odf) and "Fecha_dia" in odf.columns:
                date_series.append(odf["Fecha_dia"])
        all_dates = pd.concat(date_series)
        all_min = all_dates.min()
        all_max = all_dates.max()
        c1, c2 = st.columns(2)
        s = c1.date_input("Desde", value=all_min.date(), min_value=all_min.date(), max_value=all_max.date(), key="cmp_s")
        e = c2.date_input("Hasta", value=all_max.date(), min_value=all_min.date(), max_value=all_max.date(), key="cmp_e")
    gat_f = gat_d[(gat_d["Fecha_dia"].dt.date >= s) & (gat_d["Fecha_dia"].dt.date <= e)].copy()
    alh_f = alh_d[(alh_d["Fecha_dia"].dt.date >= s) & (alh_d["Fecha_dia"].dt.date <= e)].copy()

    gat_cols = [c for c in cols_by_prefix(gat_f, prefix, "GAT") if exceedance_pct(c) in pcts]
    alh_cols = [c for c in cols_by_prefix(alh_f, prefix, "ALH") if exceedance_pct(c) in pcts]

    is_flow = prefix in ("AP", "V")
    y_lbl   = unit_label(flow_unit) if is_flow else ("ft PLD" if prefix == "NP" else "MW")

    gat_plot = gat_f.copy()
    alh_plot = alh_f.copy()
    gat_obs_col = alh_obs_col = None

    if prefix == "NP":
        if _valid_df(obs_gat):
            om = obs_gat[["Fecha_dia", "Valor"]].rename(columns={"Valor": "Nivel obs. Gatún"})
            gat_plot = gat_plot.merge(om, on="Fecha_dia", how="left")
            gat_obs_col = "Nivel obs. Gatún"
        if _valid_df(obs_alh):
            om = obs_alh[["Fecha_dia", "Valor"]].rename(columns={"Valor": "Nivel obs. Alhajuela"})
            alh_plot = alh_plot.merge(om, on="Fecha_dia", how="left")
            alh_obs_col = "Nivel obs. Alhajuela"

    # En AP, mostrar y graficar aportes observados disponibles.
    if prefix == "AP":
        obs_rows = []
        for label, odf in [("Gatún", obs_gat_aporte), ("Alhajuela / Madden", obs_alh_aporte)]:
            if _valid_df(odf):
                tmp = clamp_observed_future_dates(odf, "Fecha_dia")
                tmp = tmp[(tmp["Fecha_dia"].dt.date >= s) & (tmp["Fecha_dia"].dt.date <= e)].copy()
                tmp = tmp.dropna(subset=["Valor"]).sort_values("Fecha_dia")
                if not tmp.empty:
                    last = tmp.iloc[-1]
                    obs_conv = convert_flow(pd.Series([float(last["Valor"])]), flow_unit).iloc[0]
                    obs_rows.append({
                        "Embalse": label,
                        "Fecha último aporte observado": pd.to_datetime(last["Fecha_dia"]).strftime("%d-%m-%Y"),
                        f"Aporte observado ({unit_label(flow_unit)})": round(float(obs_conv), 3),
                        "Aporte observado (p³/s)": round(float(last["Valor"]), 3),
                        "Fuente": last.get("Fuente", "—"),
                    })
        if obs_rows:
            st.markdown("#### Valores de aportes observados")
            st.dataframe(pd.DataFrame(obs_rows), use_container_width=True, hide_index=True)

        if _valid_df(obs_gat_aporte):
            om = clamp_observed_future_dates(obs_gat_aporte, "Fecha_dia")[["Fecha_dia", "Valor"]].copy()
            om["Aporte obs. Gatún"] = convert_flow(om["Valor"], flow_unit)
            gat_plot = gat_plot.merge(om[["Fecha_dia", "Aporte obs. Gatún"]], on="Fecha_dia", how="left")
            gat_obs_col = "Aporte obs. Gatún"
        if _valid_df(obs_alh_aporte):
            om = clamp_observed_future_dates(obs_alh_aporte, "Fecha_dia")[["Fecha_dia", "Valor"]].copy()
            om["Aporte obs. Alhajuela"] = convert_flow(om["Valor"], flow_unit)
            alh_plot = alh_plot.merge(om[["Fecha_dia", "Aporte obs. Alhajuela"]], on="Fecha_dia", how="left")
            alh_obs_col = "Aporte obs. Alhajuela"

    # Convertir flujos DSS en la copia de gráfica.
    if is_flow:
        for df, cols, evap in [(gat_plot, gat_cols, evap_gat_cfs), (alh_plot, alh_cols, evap_alh_cfs)]:
            for c in cols:
                base_series = pd.to_numeric(df[c], errors="coerce")
                if prefix == "AP":
                    base_series = base_series + float(evap or 0.0)
                df[c] = convert_flow(base_series, flow_unit)

    c_gat, c_alh = st.columns(2)
    with c_gat:
        st.caption("**Gatún**")
        fan_chart(gat_plot, gat_cols, f"Gatún · {var_choice}", y_lbl, "cmp_gat",
                  obs_col=gat_obs_col,
                  obs_label="Aporte obs. Gatún" if prefix == "AP" else "Nivel obs. Gatún")
    with c_alh:
        st.caption("**Alhajuela / Madden**")
        fan_chart(alh_plot, alh_cols, f"Alhajuela · {var_choice}", y_lbl, "cmp_alh",
                  obs_col=alh_obs_col,
                  obs_label="Aporte obs. ALHA" if prefix == "AP" else "Nivel obs. Alhajuela")


# ─────────────────────────────────────────────────────────────────────
# PESTAÑA 7
# PESTAÑA 7 — APORTE INSTANTÁNEO
# ─────────────────────────────────────────────────────────────────────

def tab_aporte_instantaneo(dss_bytes: bytes, flow_unit: str, pct_ref: int = 50) -> None:
    """Pestaña de aporte instantáneo.

    Mantiene el radar como referencia visual, pero el foco de la pestaña es
    comparar aportes instantáneos totales contra AP total DSS estimado:
        AP total DSS estimado = AP neto DSS + evaporación
    """
    st.subheader("⚡ Aporte instantáneo")
    st.caption(
        "Ingrese el aporte total observado/estimado y el caudal evaporado en p³/s. "
        "La comparación se hace contra **AP total DSS estimado = AP neto DSS + evaporación**."
    )
    st.caption(SIMULATION_NOTE)

    c_img, c_ctrl = st.columns([1.15, 1.25])
    with c_img:
        st.markdown("#### Aporte instantáneo meteorológico de referencia")
        try:
            ts = pd.Timestamp.utcnow().strftime("%Y%m%d%H%M%S")
            components.html(f"""
            <div style="border:1px solid rgba(0,62,105,.18);border-radius:14px;padding:10px;background:#f8fafc">
                <img src="{RADAR_URL}?t={ts}" style="width:100%;border-radius:10px;" />
                <div style="font-size:12px;color:#667085;margin-top:6px;">
                    Aporte instantáneo Canal · {pd.Timestamp.now():%d-%m-%Y %H:%M}
                </div>
            </div>""", height=560)
            if st.checkbox("Auto-recargar cada 5 min", key="ap_inst_auto"):
                components.html("<script>setTimeout(()=>window.parent.location.reload(),300000);</script>", height=0)
        except Exception as exc:
            st.warning(f"No se pudo mostrar el radar: {exc}")

    with c_ctrl:
        st.markdown("#### Comparar aporte instantáneo con DSS")
        ref_date = st.date_input("Fecha de referencia DSS", value=today_panama().date(), key="apinst_ref")
        unit_obs = st.selectbox("Unidad del aporte observado", ["cfs", "m³/s", "hm³/d"],
                                format_func=unit_label, key="apinst_unit")
        st.markdown("##### Aportes totales observados")
        g1, g2 = st.columns(2)
        obs_g = g1.number_input(f"GAT total obs. ({unit_label(unit_obs)})", min_value=0.0, step=10.0, key="apinst_g")
        obs_a = g2.number_input(f"ALHA total obs. ({unit_label(unit_obs)})", min_value=0.0, step=10.0, key="apinst_a")
        st.markdown("##### Evaporación a sumar al AP neto DSS")
        e1, e2 = st.columns(2)
        evap_g = e1.number_input("Evap. GAT (p³/s)", min_value=0.0, value=0.0, step=10.0, format="%.3f", key="apinst_evap_g")
        evap_a = e2.number_input("Evap. ALHA (p³/s)", min_value=0.0, value=0.0, step=10.0, format="%.3f", key="apinst_evap_a")
        st.info("Fórmula: **AP total DSS estimado = AP neto DSS + evaporación**.")

        if obs_g > 0 or obs_a > 0:
            try:
                gat_raw = load_dss_sheet(dss_bytes, RESERVOIR_CONFIG["gatun"]["sheet"])
                alh_raw = load_dss_sheet(dss_bytes, RESERVOIR_CONFIG["alhajuela"]["sheet"])
                gat_d = to_daily(gat_raw, RESERVOIR_CONFIG["gatun"])
                alh_d = to_daily(alh_raw, RESERVOIR_CONFIG["alhajuela"])
            except Exception as exc:
                st.error(f"Error DSS: {exc}")
                return

            results = []
            for obs_val, evap_cfs, daily, cfg, nombre in [
                (obs_g, evap_g, gat_d, RESERVOIR_CONFIG["gatun"],     "Gatún"),
                (obs_a, evap_a, alh_d, RESERVOIR_CONFIG["alhajuela"], "Alhajuela / Madden"),
            ]:
                if obs_val <= 0:
                    continue
                obs_cfs = scalar_to_cfs(obs_val, unit_obs)
                nearest = _nearest_ap_percentile(
                    daily, cfg, pd.to_datetime(ref_date), obs_cfs, dss_add_cfs=float(evap_cfs)
                )
                if not nearest:
                    results.append({
                        "Embalse": nombre,
                        "Estado": "⚪ Sin AP DSS",
                    })
                    continue
                obs_converted = convert_flow(pd.Series([obs_cfs]), flow_unit).iloc[0]
                dss_converted = convert_flow(pd.Series([nearest["dss_total_cfs"]]), flow_unit).iloc[0]
                results.append({
                    "Embalse": nombre,
                    f"Aporte total obs. ({unit_label(flow_unit)})": round(float(obs_converted), 3),
                    "Evap. sumada al DSS (p³/s)": round(float(evap_cfs), 3),
                    "Percentil AP total DSS más cercano": nearest["label"],
                    f"AP total DSS ({unit_label(flow_unit)})": round(float(dss_converted), 3),
                    "Diferencia Obs-DSS (p³/s)": round(float(nearest["diff_cfs"]), 3),
                    "Dif. relativa (%)": round(float(nearest["rel_pct"]), 2),
                    "Estado": nearest["estado"],
                    "Fecha DSS usada": nearest["date"].strftime("%d-%m-%Y"),
                })
            if results:
                st.dataframe(pd.DataFrame(results), use_container_width=True, hide_index=True)
        else:
            st.caption("Ingrese un aporte observado mayor que cero para calcular el percentil DSS más cercano.")


# Alias para compatibilidad con versiones anteriores
def tab_radar(dss_bytes: bytes, flow_unit: str) -> None:
    tab_aporte_instantaneo(dss_bytes, flow_unit, pct_ref=50)


# ─────────────────────────────────────────────────────────────────────
# CARGA MASIVA DE BulkExports (CSVs locales + upload)
# ─────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────
# CARGA MASIVA DE BulkExports (CSVs locales + upload)
# ─────────────────────────────────────────────────────────────────────
def load_observed_data() -> Tuple[
    Optional[pd.DataFrame],  # obs_gat_nivel
    Optional[pd.DataFrame],  # obs_alh_nivel
    Optional[pd.DataFrame],  # obs_gat_aporte
    Optional[pd.DataFrame],  # obs_alh_aporte
]:
    """
    Carga todos los BulkExport disponibles (locales + subidos).
    Clasifica por embalse y tipo (nivel / aporte).
    Retorna DataFrames diarios con columnas: Fecha_dia, Valor, Fuente
    """
    # Uploads manuales en sidebar
    st.sidebar.header("📂 BulkExport observados (CSV)")
    uploaded = st.sidebar.file_uploader(
        "CSV BulkExport (GAT, MAD, TstCHCP, etc.)",
        type=["csv"], accept_multiple_files=True, key="bulk_up",
    )
    use_local = st.sidebar.checkbox("Usar CSV locales desde carpeta data", value=True, key="bulk_local")

    sources: List[Tuple[bytes, str]] = []

    if use_local:
        for p in discover_local_bulk_csvs()[:20]:
            try:
                sources.append((p.read_bytes(), p.name))
            except Exception:
                pass

    for uf in (uploaded or []):
        sources.append((uf.getvalue(), uf.name))

    # Separate containers
    gat_nivel  = []
    alh_nivel  = []
    gat_aporte = []
    alh_aporte = []

    file_info = []
    for fbytes, fname in sources:
        try:
            daily, embalse, variable, serie = read_bulk_csv(fbytes, fname)
        except Exception as exc:
            file_info.append({"Archivo": fname, "Estado": f"Error: {exc}"})
            continue
        if daily.empty:
            file_info.append({"Archivo": fname, "Embalse": embalse, "Variable": variable, "Estado": "Sin datos"})
            continue
        file_info.append({
            "Archivo": fname, "Embalse": embalse, "Variable": variable,
            "Serie": serie, "Registros": len(daily),
            "Inicio": daily["Fecha_dia"].min(), "Fin": daily["Fecha_dia"].max(),
        })
        if embalse == "Gatún":
            (gat_nivel if variable == "nivel" else gat_aporte).append(daily)
        elif embalse == "Alhajuela / Madden":
            (alh_nivel if variable == "nivel" else alh_aporte).append(daily)

    if file_info:
        with st.sidebar.expander("📋 Archivos BulkExport leídos", expanded=False):
            st.dataframe(pd.DataFrame(file_info), use_container_width=True, hide_index=True)

    def _concat(lst: List[pd.DataFrame]) -> Optional[pd.DataFrame]:
        if not lst:
            return None
        out = pd.concat(lst, ignore_index=True)
        # Keep last valid value per day
        out = out.sort_values("Fecha_dia")
        out = out.groupby("Fecha_dia", as_index=False).agg(
            Valor=("Valor", "mean"), Fuente=("Fuente", "last")
        )
        return out

    return _concat(gat_nivel), _concat(alh_nivel), _concat(gat_aporte), _concat(alh_aporte)



# ─────────────────────────────────────────────────────────────────────
# SEMANA OPERATIVA SÁBADO-VIERNES / HP SEMANAL / INSTRUCTIVO
# ─────────────────────────────────────────────────────────────────────
def operational_week_info(date_value) -> Tuple[int, pd.Timestamp, pd.Timestamp]:
    """Semana operativa sábado-viernes.

    Para 2026: 30-may al 05-jun = semana 23; desde 06-jun inicia semana 24.
    """
    d = pd.to_datetime(date_value, errors="coerce")
    if pd.isna(d):
        return 0, pd.NaT, pd.NaT
    d = d.normalize()
    year_start = pd.Timestamp(year=d.year, month=1, day=1)
    days_to_saturday = (5 - year_start.weekday()) % 7
    first_saturday = year_start + pd.Timedelta(days=days_to_saturday)
    if d < first_saturday:
        return 1, year_start, first_saturday - pd.Timedelta(days=1)
    week = 2 + int((d - first_saturday).days // 7)
    start = first_saturday + pd.Timedelta(days=(week - 2) * 7)
    end = start + pd.Timedelta(days=6)
    return week, start, end


def add_operational_week_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty or "Fecha_dia" not in df.columns:
        return df
    out = df.copy()
    info = out["Fecha_dia"].apply(operational_week_info)
    out["Semana operativa"] = [x[0] for x in info]
    out["Inicio semana"] = [x[1] for x in info]
    out["Fin semana"] = [x[2] for x in info]
    return out


def tab_hp_semanal(dss_bytes: bytes) -> None:
    st.subheader("⚡ Hidrogeneración DSS")
    st.caption("Promedio semanal de HP del DSS. Semana operativa sábado-viernes.")

    rows = []
    for res_key, cfg in RESERVOIR_CONFIG.items():
        try:
            raw = load_dss_sheet(dss_bytes, cfg["sheet"])
            daily = to_daily(raw, cfg)
        except Exception as exc:
            st.warning(f"{cfg['name']}: no se pudo cargar HP — {exc}")
            continue
        if daily.empty:
            continue
        hp_cols = cols_by_prefix(daily, "HP", cfg["token"])
        if not hp_cols:
            continue
        daily = add_operational_week_columns(daily)
        group_cols = ["Semana operativa", "Inicio semana", "Fin semana"]
        weekly = daily.groupby(group_cols, as_index=False)[hp_cols].mean()
        for _, r in weekly.iterrows():
            row = {
                "Variable": "Hidrogeneración DSS",
                "Embalse": cfg["name"],
                "Semana": int(r["Semana operativa"]),
                "Inicio semana": pd.to_datetime(r["Inicio semana"]).strftime("%d-%m-%Y"),
                "Fin semana": pd.to_datetime(r["Fin semana"]).strftime("%d-%m-%Y"),
            }
            for c in hp_cols:
                row[f"HP P{exceedance_pct(c)} (MW)"] = round(float(r[c]), 3) if pd.notna(r[c]) else np.nan
            rows.append(row)

    if not rows:
        st.warning("No se encontraron columnas HP en el DSS.")
        return

    df = pd.DataFrame(rows).sort_values(["Embalse", "Semana"])
    min_week = max(23, int(df["Semana"].min()))
    max_week = int(df["Semana"].max())
    df = df[df["Semana"] >= 23].copy()
    c1, c2 = st.columns(2)
    w1 = c1.number_input("Semana inicial", min_value=min_week, max_value=max_week, value=min_week, step=1, key="hpw_s")
    w2 = c2.number_input("Semana final", min_value=min_week, max_value=max_week, value=max_week, step=1, key="hpw_e")
    if w1 > w2:
        w1, w2 = min_week, max_week
        st.warning("Semana inicial mayor que final. Se muestra todo el período.")
    show = df[(df["Semana"] >= int(w1)) & (df["Semana"] <= int(w2))].copy()

    st.markdown("#### Tabla semanal de Hidrogeneración DSS")
    st.caption("La variable **Hidrogeneración DSS** inicia en la semana operativa 23.")
    st.dataframe(show, use_container_width=True, hide_index=True, height=520)
    csv = show.to_csv(index=False).encode("utf-8-sig")
    st.download_button("⬇️ Descargar CSV HP semanal", csv, "hidrogeneracion_dss_semanal.csv", "text/csv", key="hpw_dl")

    # Gráfica simple P50 si existe
    if PLOTLY_OK:
        p50_cols = [c for c in show.columns if c == "HP P50 (MW)"]
        if p50_cols:
            plot = show.copy()
            plot["Etiqueta semana"] = plot["Semana"].astype(str) + " · " + plot["Inicio semana"].astype(str)
            fig = px.line(plot, x="Semana", y="HP P50 (MW)", color="Embalse", markers=True,
                          title="HP P50 semanal por embalse")
            fig.update_layout(height=520, hovermode="x unified")
            st.plotly_chart(fig, use_container_width=True, key="hpw_plot")


def tab_instructivo() -> None:
    st.subheader("📘 Instructivo rápido del dashboard")
    st.markdown("""
**Objetivo:** apoyar la revisión operativa de las proyecciones DSS 2026 para Gatún y Alhajuela/Madden, usando percentiles, aportes, vertidos, hidrogeneración y datos observados BulkExport.

**1. Cargar información**
- Coloca `SimulacionDSS_2026.xlsx` en la carpeta `data` o cárgalo desde la barra lateral.
- Coloca los `BulkExport*.csv` o los CSV normalizados en la carpeta `data` o súbelos desde la barra lateral.
- Usa **Recargar archivos** cuando cambies un Excel o CSV.

**2. Pestañas principales**
- **GATÚN DSS / ALHAJUELA DSS:** revisión por embalse de nivel, HP, AP y vertidos.
- **Manejo / Decisión:** resume diferencias entre observado y DSS, estado tipo semáforo y horizonte de decisión.
- **Aporte GAT obs / Aporte ALHA obs:** compara aporte total observado con AP total DSS estimado usando el caudal evaporado ingresado en la barra lateral.
- **Comparativo:** permite ver ambos embalses lado a lado; en AP incluye los valores observados disponibles.
- **Hidrogeneración DSS:** resume la variable Hidrogeneración DSS por semana operativa sábado-viernes.

**3. Aportes totales vs DSS**
El DSS se interpreta como **AP neto**. Para comparar con aportes totales observados:

`AP total DSS estimado = AP neto DSS + caudal evaporado`

Ingresa el caudal evaporado en **p³/s** en cada pestaña de aporte.

**4. Semana operativa**
La semana se calcula de **sábado a viernes**. Para 2026, el 30-may al 05-jun corresponde a la **semana 23** y desde el 06-jun inicia la **semana 24**.

**5. Recomendación de uso**
Primero revisa **Manejo / Decisión**, luego valida detalle en **GATÚN DSS** o **ALHAJUELA DSS**, y finalmente compara aportes observados en las pestañas de aporte.
""")

# ─────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────

def _run_tab(label: str, func, *args, **kwargs) -> None:
    """Ejecuta una pestaña sin tumbar toda la aplicación si algo falla."""
    try:
        func(*args, **kwargs)
    except Exception as exc:
        st.error(f"⚠️ Error en la pestaña **{label}**: {exc}")
        with st.expander("Detalle técnico", expanded=False):
            st.exception(exc)


def main() -> None:
    inject_css()
    view_count = get_view_count()

    st.markdown(f"<div class='main-title'>💧 {APP_TITLE}</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='sub-title'>{PROJ_NOTE} · ACP HIMH</div>", unsafe_allow_html=True)
    st.markdown(
        f"<div style='color:#003E69;font-weight:700;margin-bottom:.7rem'>"
        f"ACP-HIMH"
        f"<span class='badge' style='margin-left:10px'>👁️ {view_count:,}</span></div>",
        unsafe_allow_html=True,
    )

    cfg = sidebar()
    dss_bytes = cfg["dss_bytes"]
    flow_unit = cfg["flow_unit"]
    pct_ref_gat = int(cfg.get("pct_ref_gat", cfg.get("pct_ref", 50)))
    pct_ref_alh = int(cfg.get("pct_ref_alh", cfg.get("pct_ref", 50)))
    evap_gat_cfs = cfg.get("evap_gat_cfs", 0.0)
    evap_alh_cfs = cfg.get("evap_alh_cfs", 0.0)

    if dss_bytes is None:
        st.error(
            "⚠️ No se pudo cargar el archivo DSS. "
            "Coloque `SimulacionDSS_2026.xlsx` en la carpeta `data` o cárguelo desde el panel lateral."
        )
        return
    st.sidebar.success("✅ DSS cargado")

    # Cargar observados sin detener la app si un CSV viene con problema
    try:
        obs_gat_nivel, obs_alh_nivel, obs_gat_aporte, obs_alh_aporte = load_observed_data()
    except Exception as exc:
        st.sidebar.error(f"Error cargando observados: {exc}")
        obs_gat_nivel = obs_alh_nivel = obs_gat_aporte = obs_alh_aporte = None

    tabs = st.tabs([
        "🌊 GATÚN DSS",
        "🏔️ ALHAJUELA DSS",
        "🧭 Manejo / Decisión",
        "🌧️ Aporte GAT obs",
        "🌧️ Aporte ALHA obs",
        "🔀 Comparativo",
        "⚡ Hidrogeneración DSS",
        "📘 Instructivo",
    ])

    with tabs[0]:
        _run_tab("GATÚN DSS", tab_reservoir, "gatun", dss_bytes, flow_unit, pct_ref_gat, obs_gat_nivel, obs_gat_aporte, evap_gat_cfs)
    with tabs[1]:
        _run_tab("ALHAJUELA DSS", tab_reservoir, "alhajuela", dss_bytes, flow_unit, pct_ref_alh, obs_alh_nivel, obs_alh_aporte, evap_alh_cfs)
    with tabs[2]:
        _run_tab("Manejo / Decisión", tab_manejo, dss_bytes, flow_unit, pct_ref_gat, pct_ref_alh, obs_gat_nivel, obs_alh_nivel)
    with tabs[3]:
        _run_tab("Aporte GAT obs", tab_aporte_obs_embalse, "gatun", dss_bytes, flow_unit, pct_ref_gat, obs_gat_aporte, evap_gat_cfs)
    with tabs[4]:
        _run_tab("Aporte ALHA obs", tab_aporte_obs_embalse, "alhajuela", dss_bytes, flow_unit, pct_ref_alh, obs_alh_aporte, evap_alh_cfs)
    with tabs[5]:
        _run_tab("Comparativo", tab_comparativo, dss_bytes, flow_unit, pct_ref_gat, pct_ref_alh, obs_gat_nivel, obs_alh_nivel, obs_gat_aporte, obs_alh_aporte, evap_gat_cfs, evap_alh_cfs)
    with tabs[6]:
        _run_tab("Hidrogeneración DSS", tab_hp_semanal, dss_bytes)
    with tabs[7]:
        _run_tab("Instructivo", tab_instructivo)

    st.markdown(
        f"<div class='footer'>{SIMULATION_NOTE} · {AUTHOR_NOTE} · Vistas acumuladas: {view_count:,}</div>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
