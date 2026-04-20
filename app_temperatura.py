from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
import tempfile

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots
from scipy import stats as sp_stats

# ============================================================
# CONFIG GENERAL
# ============================================================
st.set_page_config(
    page_title="Dashboard Integrado de Temperatura y Surgencias",
    page_icon="🌡️",
    layout="wide",
)

C = {
    "rojo": "#e74c3c",
    "rojo_suave": "rgba(231,76,60,0.10)",
    "azul": "#2980b9",
    "azul_suave": "rgba(41,128,185,0.10)",
    "verde": "#27ae60",
    "naranja": "#e67e22",
    "morado": "#8e44ad",
    "gris": "#95a5a6",
    "oscuro": "#2c3e50",
    "turquesa": "#16a085",
}

MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
SECA_MESES = {12, 1, 2, 3, 4}
AUTHOR_FOOTER = "JFRodriguez Hidrologo/Oceanografo Fisico"
RHO_AIR = 1.225
CD_BULK = 1.3e-3


@dataclass
class SourceFile:
    path: str
    variable: str
    sensor: str
    station: str
    label: str


# ============================================================
# UTILIDADES
# ============================================================
def safe_filename(text: str) -> str:
    text = re.sub(r"[^\w\-.]+", "_", str(text).strip(), flags=re.UNICODE)
    return re.sub(r"_+", "_", text).strip("_")


def metric_card(title: str, value: str, subtitle: str = "", color: str = "#f8f9fa"):
    st.markdown(
        f"""
        <div style="
            background:{color};
            border-radius:14px;
            padding:16px 18px;
            border:1px solid rgba(0,0,0,0.06);
            min-height:108px;">
            <div style="font-size:0.88rem;color:#566573;">{title}</div>
            <div style="font-size:1.85rem;font-weight:700;color:#1f2d3d;line-height:1.2;">{value}</div>
            <div style="font-size:0.78rem;color:#7b8a8b;">{subtitle}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def infer_station_from_name(name: str) -> str:
    n = name.upper()
    if "AMA" in n:
        return "AMA"
    if "LMB" in n:
        return "LMB"
    if "DHT" in n:
        return "DHT"
    if "FLC" in n:
        return "FLC"
    return "N/D"


def infer_temp_sensor(name: str) -> str:
    n = name.upper()
    if "TELEMETRIA" in n or "TEMP@" in n:
        return "Telemetría"
    if "LAN WT" in n or "LAN_WT" in n:
        return "LAN"
    return "Temperatura"


def source_label(variable: str, sensor: str, station: str, path: str) -> str:
    return f"{variable} · {sensor} · {station} · {Path(path).name}"


def resample_if_needed(df: pd.DataFrame, col: str, limit: int = 12000, freq: str = "1h"):
    if len(df) <= limit:
        return df.copy(), False
    out = (
        df.set_index("fecha")[[col]]
        .resample(freq)
        .mean()
        .dropna()
        .reset_index()
    )
    return out, True


def monthly_climatology(df: pd.DataFrame, col: str) -> pd.DataFrame:
    out = df.copy()
    out["mes"] = out["fecha"].dt.month
    return out.groupby("mes")[col].agg(["mean", "std", "min", "max"]).reset_index()


def combine_temperature_sources(temp_frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    if "Telemetría" in temp_frames and "LAN" in temp_frames:
        tele = temp_frames["Telemetría"][["fecha", "temp_c"]].rename(columns={"temp_c": "tele"})
        lan = temp_frames["LAN"][["fecha", "temp_c"]].rename(columns={"temp_c": "lan"})
        merged = pd.merge(tele, lan, on="fecha", how="outer").sort_values("fecha")
        merged["temp_c"] = merged["tele"].combine_first(merged["lan"])
        df = merged[["fecha", "temp_c"]].dropna().reset_index(drop=True)
        df["temp_f"] = df["temp_c"] * 9 / 5 + 32
        return df
    first_key = next(iter(temp_frames))
    return temp_frames[first_key].copy()


def detect_upwelling_events(df: pd.DataFrame, col: str, threshold: float, min_hours: int) -> pd.DataFrame:
    work = df[["fecha", col]].copy().dropna().sort_values("fecha")
    work["below"] = work[col] < threshold
    work["grp"] = (work["below"] != work["below"].shift()).cumsum()
    ev = (
        work[work["below"]]
        .groupby("grp")
        .agg(
            inicio=("fecha", "min"),
            fin=("fecha", "max"),
            duracion_h=("fecha", "count"),
            temp_min=(col, "min"),
            temp_media=(col, "mean"),
        )
        .reset_index(drop=True)
    )
    if ev.empty:
        return ev
    ev = ev[ev["duracion_h"] >= min_hours].copy()
    if ev.empty:
        return ev
    ev["intensidad"] = threshold - ev["temp_min"]
    ev["anio"] = ev["inicio"].dt.year
    ev["mes"] = ev["inicio"].dt.month
    ev["temporada"] = np.where(ev["mes"].isin(list(SECA_MESES)), "Seca", "Lluviosa")
    return ev.reset_index(drop=True)


def sensor_overlap_metrics(df_a: pd.DataFrame, df_b: pd.DataFrame) -> pd.DataFrame:
    a = df_a[["fecha", "temp_c"]].rename(columns={"temp_c": "tele"})
    b = df_b[["fecha", "temp_c"]].rename(columns={"temp_c": "lan"})
    merged = pd.merge(a, b, on="fecha", how="inner").sort_values("fecha")
    if merged.empty:
        return merged
    merged["delta"] = merged["tele"] - merged["lan"]
    return merged


def to_hourly(df: pd.DataFrame, value_cols: list[str]) -> pd.DataFrame:
    return df.set_index("fecha")[value_cols].resample("1h").mean().dropna().reset_index()


def lag_correlation(df: pd.DataFrame, x_col: str, y_col: str, lags: list[int]) -> tuple[list[float], int]:
    vals = [df[x_col].shift(l).corr(df[y_col]) for l in lags]
    finite = np.isfinite(vals)
    if not finite.any():
        return vals, 0
    best = lags[int(np.nanargmax(np.abs(vals)))]
    return vals, best


def wind_stress_from_speed(speed_ms: pd.Series | np.ndarray | float, rho_air: float = RHO_AIR, cd: float = CD_BULK):
    return rho_air * cd * np.square(speed_ms)


def build_temp_wind_diagnostics(temp_df: pd.DataFrame, wind_df: pd.DataFrame, temp_col: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    temp_h = temp_df.set_index("fecha")[[temp_col]].resample("1h").mean()
    wind_h = wind_df.set_index("fecha")[["viento_ms"]].resample("1h").mean()
    mv = temp_h.join(wind_h, how="inner").dropna().reset_index()
    if mv.empty:
        return mv, pd.DataFrame()

    mv["tau_n_m2"] = wind_stress_from_speed(mv["viento_ms"])
    p95_tau = float(mv["tau_n_m2"].quantile(0.95)) if len(mv) >= 10 else float(mv["tau_n_m2"].max())
    scale_tau = p95_tau if np.isfinite(p95_tau) and p95_tau > 0 else 1.0
    mv["factor_intensidad"] = (mv["tau_n_m2"] / scale_tau).clip(lower=0, upper=1.5)

    daily = (
        mv.set_index("fecha")[[temp_col, "viento_ms", "tau_n_m2", "factor_intensidad"]]
        .resample("1D")
        .mean()
        .dropna()
        .reset_index()
    )
    if daily.empty:
        return mv, daily

    daily["delta_temp_1d"] = daily[temp_col].diff()
    daily["delta_temp_fut_1d"] = daily[temp_col].shift(-1) - daily[temp_col]
    daily["delta_temp_fut_3d"] = daily[temp_col].shift(-3) - daily[temp_col]
    daily["delta_temp_fut_5d"] = daily[temp_col].shift(-5) - daily[temp_col]

    try:
        cats = pd.qcut(daily["tau_n_m2"], 3, labels=["Baja", "Media", "Alta"], duplicates="drop")
        daily["categoria_intensidad"] = cats.astype(str)
    except Exception:
        daily["categoria_intensidad"] = "N/D"

    return mv, daily


def infer_active_temp_station(temp_key: str, temp_paths_by_key: dict[str, str]) -> str:
    ref = f"{temp_key} {temp_paths_by_key.get(temp_key, '')}"
    station = infer_station_from_name(ref)
    if station != "N/D":
        return station

    if temp_key.upper().startswith("COMBINADO"):
        blob = " ".join(str(v) for k, v in temp_paths_by_key.items() if k != "Combinado")
        station = infer_station_from_name(blob)
        if station != "N/D":
            return station

    blob = " ".join(str(v) for v in temp_paths_by_key.values())
    station = infer_station_from_name(blob)
    return station


def classify_recent_ocean_phase(df_phase: pd.DataFrame, station: str) -> tuple[str, str, str]:
    if df_phase.empty or "temp_c" not in df_phase.columns:
        return "N/D", "Sin datos suficientes para clasificar el estado reciente.", "#f7f9fa"

    daily_c = (
        df_phase.set_index("fecha")[["temp_c"]]
        .resample("1D")
        .mean()
        .dropna()
        .reset_index()
    )
    if daily_c.empty:
        return "N/D", "Sin datos diarios válidos para clasificar el estado reciente.", "#f7f9fa"

    last_date = daily_c["fecha"].max()
    t7 = float(daily_c.tail(7)["temp_c"].mean())
    mmdd = last_date.month * 100 + last_date.day

    recent_delta = np.nan
    if len(daily_c) >= 6:
        recent_delta = float(daily_c["temp_c"].tail(3).mean() - daily_c["temp_c"].iloc[-6:-3].mean())
    elif len(daily_c) >= 4:
        recent_delta = float(daily_c["temp_c"].tail(2).mean() - daily_c["temp_c"].iloc[-4:-2].mean())

    def recent_trend_text(delta: float) -> str:
        if np.isnan(delta):
            return "sin una tendencia corta suficientemente robusta"
        if delta >= 0.35:
            return "se observa un aumento térmico reciente"
        if delta >= 0.10:
            return "se observa un leve aumento térmico reciente"
        if delta <= -0.35:
            return "se observa un descenso térmico reciente"
        if delta <= -0.10:
            return "se observa un leve descenso térmico reciente"
        return "la señal térmica reciente se mantiene relativamente estable"

    trend_text = recent_trend_text(recent_delta)

    if station == "AMA":
        # Referencias operativas aportadas por el usuario:
        # Afloramiento ~20 Ene–25 Mar (18–26 °C)
        # Transición ~5 Abr–31 May (25–29 °C)
        # Temporada cálida Jun–Dic (27–32 °C)
        if mmdd <= 404:
            if t7 < 25.0:
                return "Afloramiento activo", f"AMA · últimos 7 días: {t7:.2f} °C · {trend_text}; la señal fría aún persiste bajo 25 °C.", "#eaf3ff"
            if t7 < 27.0:
                return "Afloramiento débil / transición temprana", f"AMA · últimos 7 días {t7:.2f} °C · aún en ventana estacional fría, pero ya con calentamiento.", "#eef7ff"
            return "Señal cálida atípica", f"AMA · últimos 7 días {t7:.2f} °C · más cálido de lo esperado para la fase fría.", "#fff0ef"

        if 405 <= mmdd <= 531:
            if t7 < 25.0:
                return "Transición retrasada con afloramiento", f"AMA · últimos 7 días: {t7:.2f} °C · {trend_text}; sin embargo, la señal térmica aún se mantiene por debajo de 25 °C, consistente con una transición retrasada y persistencia de condiciones de afloramiento.", "#eaf3ff"
            if t7 <= 29.0:
                return "Transición térmica", f"AMA · últimos 7 días {t7:.2f} °C · coherente con la ventana típica de transición (~5 abril–31 mayo).", "#fff7ed"
            return "Temporada cálida temprana", f"AMA · últimos 7 días {t7:.2f} °C · por encima del rango típico de transición.", "#fff0ef"

        if t7 >= 27.0:
            return "Temporada cálida", f"AMA · últimos 7 días {t7:.2f} °C · coherente con la fase cálida de junio a diciembre.", "#edf9f0"
        if t7 >= 25.0:
            return "Transición tardía / enfriamiento moderado", f"AMA · últimos 7 días {t7:.2f} °C · más fresca de lo usual para la fase cálida.", "#f7f9fa"
        return "Enfriamiento anómalo", f"AMA · últimos 7 días {t7:.2f} °C · enfriamiento fuerte fuera de la ventana típica.", "#eaf3ff"

    return "Referencia no calibrada", f"La clasificación estacional detallada fue configurada para AMA; estación activa: {station}.", "#f7f9fa"



def assign_climatology_stage(fecha: pd.Timestamp, station: str) -> str:
    fecha = pd.Timestamp(fecha)
    mmdd = fecha.month * 100 + fecha.day

    if station == "AMA":
        if 120 <= mmdd <= 325:
            return "Afloramiento"
        if 326 <= mmdd <= 531:
            return "Transición"
        return "Temporada cálida"

    return "Etapa no calibrada"


def candidate_directories() -> list[Path]:
    app_dir = Path(__file__).resolve().parent
    tmp_dir = Path(tempfile.gettempdir())

    # Detectar dinámicamente todos los subdirectorios de /mount/src (Streamlit Cloud)
    streamlit_cloud_roots: list[Path] = []
    mount_src = Path("/mount/src")
    if mount_src.exists():
        try:
            for child in mount_src.iterdir():
                if child.is_dir():
                    streamlit_cloud_roots.extend([
                        child,
                        child / "data",
                        child / "fuentes",
                    ])
        except Exception:
            pass

    roots = [
        app_dir,
        app_dir / "data",
        app_dir / "fuentes",
        app_dir.parent,
        app_dir.parent / "data",
        app_dir.parent / "fuentes",
        Path.cwd(),
        Path.cwd() / "data",
        Path.cwd() / "fuentes",
        Path("/mnt/data"),
        Path("/mnt/data/data"),
        Path("/mnt/data/fuentes"),
        mount_src,
        mount_src / "data",
        mount_src / "fuentes",
        tmp_dir,
        tmp_dir / "data",
        tmp_dir / "fuentes",
    ] + streamlit_cloud_roots
    seen = set()
    out = []
    for p in roots:
        if p.exists():
            rp = p.resolve()
            if rp not in seen:
                seen.add(rp)
                out.append(rp)
    return out


def read_head_text(path: Path, n_lines: int = 3) -> str:
    try:
        if path.suffix.lower() in {".csv", ".txt"}:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                return "\n".join(fh.readline().strip() for _ in range(n_lines))
        if path.suffix.lower() in {".xlsx", ".xls"}:
            sample = pd.read_excel(path, nrows=5, header=None)
            return " ".join(sample.astype(str).fillna("").stack().tolist())
    except Exception:
        return ""
    return ""


def classify_source_file(path: Path) -> tuple[str | None, str, str]:
    name = path.name.upper()
    head = read_head_text(path).upper()
    blob = f"{name} {head}"

    station = infer_station_from_name(path.name + " " + head)
    sensor = ""

    temp_markers = [
        "WATER TEMP", "TEMP@", "TEMP.", "LAN WT", "WT AVG", "TEMPERATURA",
        "VALOR (°C)", "VALOR (DEGC)", "DEGC", "TEMP TELEMETRIA", "TELEMETRIA TEMP",
    ]
    wind_markers = [
        "WIND SPEED", "WS AVG", "WIND", "VIENTO", "VALOR (M/S)",
        "WIND SPEED@", "WIND SPEED.", "WS@", "WS.",
    ]
    tide_markers = [
        "WATER LEVEL", "LEVEL@", "TIDE", "MAREA", "NIVEL", "BULKEXPORT",
        "NIVEL_FT", "VALOR (FT)", "LEVEL.",
    ]

    if any(m in blob for m in temp_markers):
        sensor = infer_temp_sensor(blob)
        return "Temperatura", sensor, station

    if any(m in blob for m in wind_markers):
        sensor = "WS AVG"
        return "Viento", sensor, station

    if any(m in blob for m in tide_markers):
        sensor = "Nivel"
        return "Marea", sensor, station

    # ── Fallback por nombre de archivo (clasificación ampliada) ──────────
    fname_up = path.stem.upper()
    # Temperatura: nombre contiene TEMP, AGUA, SST, OCEAN o similar
    TEMP_NAME = {"TEMP", "TEMPERATURA", "SST", "AGUA", "WATER", "WT_"}
    WIND_NAME = {"WIND", "VIENTO", "WS_", "WSP", "ANEM"}
    TIDE_NAME = {"TIDE", "MAREA", "LEVEL", "NIVEL", "WL_"}
    if any(t in fname_up for t in TEMP_NAME):
        sensor = infer_temp_sensor(fname_up)
        if sensor == "Temperatura":
            sensor = "Telemetría"
        return "Temperatura", sensor, station
    if any(t in fname_up for t in WIND_NAME):
        return "Viento", "WS AVG", station
    if any(t in fname_up for t in TIDE_NAME):
        return "Marea", "Nivel", station

    return None, "", station


def discover_source_files() -> list[SourceFile]:
    found: list[SourceFile] = []
    valid_ext = {".csv", ".txt", ".xlsx", ".xls"}
    for root in candidate_directories():
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in valid_ext:
                continue
            variable, sensor, station = classify_source_file(path)
            if variable is None:
                continue
            found.append(
                SourceFile(
                    str(path),
                    variable,
                    sensor,
                    station,
                    source_label(variable, sensor or "N/D", station, str(path)),
                )
            )
    uniq = {}
    for item in found:
        uniq[os.path.realpath(item.path)] = item
    return sorted(uniq.values(), key=lambda x: (x.variable, x.station, x.sensor, x.path))


def discover_all_data_files() -> list[Path]:
    """Devuelve todos los archivos CSV/TXT/Excel encontrados, sin clasificar."""
    valid_ext = {".csv", ".txt", ".xlsx", ".xls"}
    seen: set[str] = set()
    result: list[Path] = []
    for root in candidate_directories():
        try:
            for path in root.rglob("*"):
                if not path.is_file() or path.suffix.lower() not in valid_ext:
                    continue
                rp = os.path.realpath(path)
                if rp not in seen:
                    seen.add(rp)
                    result.append(path)
        except Exception:
            continue
    return sorted(result, key=lambda p: str(p))


def persist_uploaded_source_files(uploaded_files) -> list[SourceFile]:
    if not uploaded_files:
        return []

    upload_dir = Path(tempfile.gettempdir()) / "dashboard_fuentes_subidas"
    upload_dir.mkdir(parents=True, exist_ok=True)
    found: list[SourceFile] = []

    for up in uploaded_files:
        raw_name = Path(up.name).name
        safe_name = safe_filename(raw_name) or "fuente.csv"
        suffix = Path(raw_name).suffix.lower() or ".csv"
        target = upload_dir / f"{Path(safe_name).stem}_{len(up.getvalue())}{suffix}"
        target.write_bytes(up.getbuffer())

        variable, sensor, station = classify_source_file(target)
        upper_name = raw_name.upper()
        if variable is None:
            if "TEMP" in upper_name or "WATER TEMP" in upper_name:
                variable = "Temperatura"
                sensor = infer_temp_sensor(upper_name)
                station = infer_station_from_name(upper_name)
            elif "WIND" in upper_name or "WS" in upper_name or "VIENTO" in upper_name:
                variable = "Viento"
                sensor = "WS AVG"
                station = infer_station_from_name(upper_name)
            elif "LEVEL" in upper_name or "TIDE" in upper_name or "NIVEL" in upper_name:
                variable = "Marea"
                sensor = "Nivel"
                station = infer_station_from_name(upper_name)

        if variable is None:
            continue

        found.append(
            SourceFile(
                str(target),
                variable,
                sensor,
                station,
                source_label(variable, sensor or "N/D", station, str(target)),
            )
        )

    uniq = {}
    for item in found:
        uniq[os.path.realpath(item.path)] = item
    return sorted(uniq.values(), key=lambda x: (x.variable, x.station, x.sensor, x.path))
# ============================================================
# CARGA DE DATOS
# ============================================================

def _parse_interval_series_text(path: str) -> pd.DataFrame:
    encodings = ["utf-8", "utf-8-sig", "latin-1", "cp1252"]
    text = None
    for enc in encodings:
        try:
            text = Path(path).read_text(encoding=enc)
            break
        except Exception:
            continue
    if text is None:
        raise ValueError("No se pudo leer el archivo como texto.")

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        raise ValueError("El archivo está vacío.")

    def parse_line(line: str, delimiter: str):
        parts = [p.strip().strip('"') for p in line.split(delimiter)]
        if len(parts) < 3:
            return None
        fecha = pd.to_datetime(parts[0], errors="coerce")
        fecha_fin = pd.to_datetime(parts[1], errors="coerce")
        if pd.isna(fecha):
            return None
        value = None
        for token in parts[2:]:
            cleaned = token.replace(" ", "")
            if delimiter != ",":
                cleaned = cleaned.replace(",", ".")
            try:
                value = float(cleaned)
                break
            except Exception:
                continue
        if value is None:
            return None
        return fecha, fecha_fin, value

    best_rows = []
    for delimiter in [";", "	", ","]:
        rows = []
        for line in lines:
            parsed = parse_line(line, delimiter)
            if parsed is not None:
                rows.append(parsed)
        if len(rows) > len(best_rows):
            best_rows = rows

    if not best_rows:
        raise ValueError("No se pudieron identificar filas válidas de fecha, fin de intervalo y valor.")

    return pd.DataFrame(best_rows, columns=["fecha_inicio", "fecha_fin", "valor_raw"])


@st.cache_data(show_spinner="Cargando temperatura...")
def load_temperature_file(path: str) -> pd.DataFrame:
    p = Path(path)
    if p.suffix.lower() in {".xlsx", ".xls"}:
        df = pd.read_excel(path, skiprows=1)
        if df.shape[1] < 3:
            df = pd.read_excel(path)
            if df.shape[1] < 3:
                raise ValueError("El archivo de temperatura no tiene al menos tres columnas.")
    else:
        df = None
        last_error = None
        for kwargs in [
            {"sep": ";", "skiprows": 1, "engine": "python"},
            {"sep": "	", "skiprows": 1, "engine": "python"},
            {"sep": None, "skiprows": 1, "engine": "python"},
        ]:
            try:
                raw = pd.read_csv(path, **kwargs)
                if raw.shape[1] >= 3:
                    df = raw.iloc[:, :3].copy()
                    break
            except Exception as exc:
                last_error = exc
        if df is None:
            try:
                df = _parse_interval_series_text(path)
            except Exception as exc:
                if last_error is not None:
                    raise ValueError(f"No se pudo interpretar el archivo de temperatura. Último error tabular: {last_error}. Error robusto: {exc}")
                raise

    if list(df.columns[:3]) != ["fecha_inicio", "fecha_fin", "valor_raw"]:
        df = df.iloc[:, :3].copy()
        df.columns = ["fecha_inicio", "fecha_fin", "valor_raw"]

    df["fecha"] = pd.to_datetime(df["fecha_inicio"], errors="coerce")
    df["temp_c"] = pd.to_numeric(df["valor_raw"].astype(str).str.replace(",", ".", regex=False), errors="coerce")
    df = df.dropna(subset=["fecha", "temp_c"])
    df = df[(df["temp_c"] >= 0) & (df["temp_c"] <= 45)].copy()
    df = df[["fecha", "temp_c"]].sort_values("fecha").drop_duplicates("fecha").reset_index(drop=True)
    df["temp_f"] = (df["temp_c"] * 9 / 5 + 32).round(2)
    return df


def _parse_delimited_tide_text(path: str) -> pd.DataFrame:
    encodings = ["utf-8", "utf-8-sig", "latin-1", "cp1252"]
    text = None
    for enc in encodings:
        try:
            text = Path(path).read_text(encoding=enc)
            break
        except Exception:
            continue
    if text is None:
        raise ValueError("No se pudo leer el archivo de marea como texto.")

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        raise ValueError("El archivo de marea está vacío.")

    def parse_line(line: str, delimiter: str):
        parts = [p.strip().strip('"') for p in line.split(delimiter)]
        if len(parts) < 2:
            return None
        fecha = pd.to_datetime(parts[0], errors="coerce")
        if pd.isna(fecha):
            return None
        numeric_candidates = []
        for token in parts[1:]:
            cleaned = token.replace(" ", "")
            if delimiter != ",":
                cleaned = cleaned.replace(",", ".")
            try:
                val = float(cleaned)
                numeric_candidates.append(val)
            except Exception:
                continue
        if not numeric_candidates:
            return None
        return fecha, numeric_candidates[-1]

    best_rows = []
    for delimiter in [";", "	", ","]:
        rows = []
        for line in lines:
            parsed = parse_line(line, delimiter)
            if parsed is not None:
                rows.append(parsed)
        if len(rows) > len(best_rows):
            best_rows = rows

    if not best_rows:
        raise ValueError("No se pudieron identificar filas válidas de fecha y nivel en el archivo de marea.")

    return pd.DataFrame(best_rows, columns=["fecha", "nivel_ft"])


@st.cache_data(show_spinner="Cargando marea...")
def load_tide_file(path: str) -> pd.DataFrame:
    p = Path(path)
    if p.suffix.lower() in {".xlsx", ".xls"}:
        df = pd.read_excel(path)
        if df.shape[1] < 2:
            raise ValueError("El archivo Excel de marea no tiene al menos dos columnas.")
        df = df.iloc[:, :2].copy()
        df.columns = ["fecha", "nivel_ft"]
    else:
        last_error = None
        df = None
        for kwargs in [
            {"sep": ";", "engine": "python"},
            {"sep": "	", "engine": "python"},
            {"sep": None, "engine": "python"},
        ]:
            try:
                raw = pd.read_csv(path, **kwargs)
                if raw.shape[1] >= 2:
                    candidate = raw.iloc[:, [0, raw.shape[1] - 1]].copy()
                    candidate.columns = ["fecha", "nivel_ft"]
                    test = candidate.copy()
                    test["fecha"] = pd.to_datetime(test["fecha"], errors="coerce")
                    test["nivel_ft"] = pd.to_numeric(test["nivel_ft"].astype(str).str.replace(",", ".", regex=False), errors="coerce")
                    valid = test.dropna(subset=["fecha", "nivel_ft"])
                    if len(valid) >= 5:
                        df = candidate
                        break
            except Exception as exc:
                last_error = exc
        if df is None:
            try:
                df = _parse_delimited_tide_text(path)
            except Exception as exc:
                if last_error is not None:
                    raise ValueError(f"No se pudo interpretar el archivo de marea. Último error tabular: {last_error}. Error robusto: {exc}")
                raise

    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    df["nivel_ft"] = pd.to_numeric(df["nivel_ft"].astype(str).str.replace(",", ".", regex=False), errors="coerce")
    df = df.dropna(subset=["fecha", "nivel_ft"]).sort_values("fecha")
    df = df.drop_duplicates("fecha").reset_index(drop=True)
    df["nivel_m"] = df["nivel_ft"] * 0.3048
    return df


@st.cache_data(show_spinner="Cargando viento...")
def load_wind_file(path: str) -> pd.DataFrame:
    p = Path(path)
    if p.suffix.lower() in {".xlsx", ".xls"}:
        df = pd.read_excel(path, skiprows=1)
        if df.shape[1] < 3:
            df = pd.read_excel(path)
            if df.shape[1] < 3:
                raise ValueError("El archivo de viento no tiene al menos tres columnas.")
    else:
        df = None
        last_error = None
        for kwargs in [
            {"sep": ";", "skiprows": 1, "engine": "python"},
            {"sep": "	", "skiprows": 1, "engine": "python"},
            {"sep": None, "skiprows": 1, "engine": "python"},
        ]:
            try:
                raw = pd.read_csv(path, **kwargs)
                if raw.shape[1] >= 3:
                    df = raw.iloc[:, :3].copy()
                    break
            except Exception as exc:
                last_error = exc
        if df is None:
            try:
                df = _parse_interval_series_text(path)
            except Exception as exc:
                if last_error is not None:
                    raise ValueError(f"No se pudo interpretar el archivo de viento. Último error tabular: {last_error}. Error robusto: {exc}")
                raise

    if list(df.columns[:3]) != ["fecha_inicio", "fecha_fin", "valor_raw"]:
        df = df.iloc[:, :3].copy()
        df.columns = ["fecha_inicio", "fecha_fin", "valor_raw"]

    df["fecha"] = pd.to_datetime(df["fecha_inicio"], errors="coerce")
    df["viento_ms"] = pd.to_numeric(df["valor_raw"].astype(str).str.replace(",", ".", regex=False), errors="coerce")
    df = df.dropna(subset=["fecha", "viento_ms"])
    df = df[(df["viento_ms"] >= 0) & (df["viento_ms"] <= 80)].copy()
    df = df[["fecha", "viento_ms"]].sort_values("fecha").drop_duplicates("fecha").reset_index(drop=True)
    df["viento_kt"] = df["viento_ms"] * 1.94384
    df["viento_kmh"] = df["viento_ms"] * 3.6
    return df
# ============================================================
# DESCUBRIMIENTO Y CARGA AUTOMÁTICA
# ============================================================
st.sidebar.markdown("## 📂 Fuentes de datos")
st.sidebar.caption("Si el despliegue no trae los CSV dentro del repo, súbalos aquí y el tablero seguirá igual.")
uploaded_runtime_files = st.sidebar.file_uploader(
    "Respaldo: subir archivos fuente si el entorno no los detecta automáticamente",
    type=["csv", "txt", "xlsx", "xls"],
    accept_multiple_files=True,
    help="Puede subir archivos de temperatura, viento y marea. El app los copiará a una carpeta temporal y los integrará sin cambiar el resto del tablero.",
)
uploaded_sources_meta = persist_uploaded_source_files(uploaded_runtime_files)
auto_sources = discover_source_files()
all_sources_map = {os.path.realpath(item.path): item for item in auto_sources}
for item in uploaded_sources_meta:
    all_sources_map[os.path.realpath(item.path)] = item
all_sources = sorted(all_sources_map.values(), key=lambda x: (x.variable, x.station, x.sensor, x.path))

temp_sources_meta = [s for s in all_sources if s.variable == "Temperatura"]
tide_sources_meta = [s for s in all_sources if s.variable == "Marea"]
wind_sources_meta = [s for s in all_sources if s.variable == "Viento"]

if uploaded_sources_meta:
    st.sidebar.success(f"Se integraron {len(uploaded_sources_meta)} archivo(s) subidos manualmente.")

if not temp_sources_meta:
    # ══════════════════════════════════════════════════════════════
    # PANTALLA DE CARGA — se muestra cuando no hay datos en el repo
    # ══════════════════════════════════════════════════════════════
    st.markdown(
        """
        <div style="text-align:center; padding: 40px 0 10px 0;">
            <h1 style="color:#c0392b;">🌡️ Dashboard de Temperatura · Canal de Panamá</h1>
            <p style="font-size:1.15rem; color:#5d6d7e;">HIMH · ACP</p>
        </div>
        """, unsafe_allow_html=True
    )

    col_l, col_c, col_r = st.columns([1, 3, 1])
    with col_c:
        st.markdown(
            """
            <div style="background:#fff8e1; border:2px solid #f39c12; border-radius:12px;
                        padding:22px 28px; margin-bottom:18px;">
                <h3 style="margin:0 0 8px 0; color:#e67e22;">📂 No se encontraron archivos de datos</h3>
                <p style="margin:0; color:#5d6d7e; font-size:0.97rem;">
                    Los archivos de datos <b>no están en el repositorio de GitHub</b>.<br>
                    Súbalos aquí directamente — el tablero cargará de inmediato.
                </p>
            </div>
            """, unsafe_allow_html=True
        )

        uploaded_main = st.file_uploader(
            "📤 Subir archivos de datos (temperatura, viento, marea)",
            type=["csv", "txt", "xlsx", "xls"],
            accept_multiple_files=True,
            help=(
                "Suba uno o más archivos Excel/CSV. "
                "El app detecta automáticamente si son temperatura, viento o marea "
                "por el nombre del archivo o su contenido."
            ),
            key="main_uploader",
        )

        if uploaded_main:
            extra_meta = persist_uploaded_source_files(uploaded_main)
            for item in extra_meta:
                all_sources_map[os.path.realpath(item.path)] = item
            all_sources = sorted(all_sources_map.values(),
                                 key=lambda x: (x.variable, x.station, x.sensor, x.path))
            temp_sources_meta  = [s for s in all_sources if s.variable == "Temperatura"]
            tide_sources_meta  = [s for s in all_sources if s.variable == "Marea"]
            wind_sources_meta  = [s for s in all_sources if s.variable == "Viento"]

            if temp_sources_meta:
                st.success(f"✅ {len(temp_sources_meta)} archivo(s) de temperatura cargado(s). Recargando tablero…")
                st.rerun()
            else:
                det_names = [Path(u.name).name for u in uploaded_main]
                st.error(
                    f"No se pudo identificar ningún archivo de temperatura entre los subidos: "
                    f"{', '.join(det_names)}. "
                    "Asegúrese que el nombre contenga TEMP, AGUA, WATER o SST, "
                    "o que el contenido tenga encabezados como 'Valor (°C)', 'DEGC', 'Water Temp'."
                )

        st.markdown("---")
        st.markdown(
            """
            **💡 Nombres de archivo recomendados para detección automática:**
            | Tipo | Ejemplos válidos |
            |---|---|
            | 🌡️ Temperatura | `TEMP_AMA.xlsx`, `Water_Temp_AMA.csv`, `temperatura_LMB.xlsx` |
            | 💨 Viento | `Wind_LMB.xlsx`, `Viento_LMB.csv`, `WS_AVG_LMB.xlsx` |
            | 🌊 Marea | `Marea_AMA.xlsx`, `Tide_LMB.csv`, `Nivel_AMA.xlsx` |

            Los archivos actuales del sistema (`DataSetExport-Water_Temp_...xlsx`) **también son compatibles**.
            """
        )

        with st.expander("🔍 Rutas revisadas automáticamente"):
            for p in candidate_directories():
                st.code(str(p))

    st.stop()

temp_frames: dict[str, pd.DataFrame] = {}
temp_paths_by_key: dict[str, str] = {}
for src in temp_sources_meta:
    try:
        df_temp = load_temperature_file(src.path)
        if not df_temp.empty:
            key = src.sensor if src.sensor not in temp_frames else f"{src.sensor} ({Path(src.path).name})"
            temp_frames[key] = df_temp
            temp_paths_by_key[key] = src.path
    except Exception as exc:
        st.warning(f"No se pudo cargar {Path(src.path).name}: {exc}")

if not temp_frames:
    st.error("Se detectaron archivos de temperatura, pero ninguno pudo cargarse correctamente.")
    st.stop()

if "Telemetría" in temp_frames or "LAN" in temp_frames:
    temp_frames["Combinado"] = combine_temperature_sources({k: v for k, v in temp_frames.items() if k in {"Telemetría", "LAN"}})
    temp_paths_by_key["Combinado"] = "Combinado (Telemetría priorizada; completa con LAN)"

tide_frames: dict[str, pd.DataFrame] = {}  # Desactivado

wind_frames: dict[str, pd.DataFrame] = {}
for src in wind_sources_meta:
    try:
        df_w = load_wind_file(src.path)
        if not df_w.empty:
            key = src.station if src.station not in wind_frames else f"{src.station} ({Path(src.path).stem})"
            wind_frames[key] = df_w
    except Exception as exc:
        st.warning(f"No se pudo cargar viento {Path(src.path).name}: {exc}")


# ============================================================
# SIDEBAR
# ============================================================
logo_candidates = [
    Path(__file__).resolve().parent / "LOGO_HIMH.jpg",
    Path.cwd() / "LOGO_HIMH.jpg",
    Path("/mnt/data/LOGO_HIMH.jpg"),
]
for logo in logo_candidates:
    if logo.exists():
        st.sidebar.image(str(logo), width=120)
        break

st.sidebar.markdown("## 🌡️ Dashboard Integrado")
st.sidebar.markdown("**Canal de Panamá · HIMH**")
st.sidebar.markdown("---")

temp_option_keys = list(temp_frames.keys())
default_temp = "Combinado" if "Combinado" in temp_frames else ("Telemetría" if "Telemetría" in temp_frames else temp_option_keys[0])
temp_key = st.sidebar.selectbox("Fuente principal de temperatura", temp_option_keys, index=temp_option_keys.index(default_temp))
df_temp_main = temp_frames[temp_key].copy()

unidad = st.sidebar.radio("Unidad", ["°C", "°F"], horizontal=True)
col_t = "temp_c" if unidad == "°C" else "temp_f"

fmin = df_temp_main["fecha"].min().date()
fmax = df_temp_main["fecha"].max().date()
default_ini = max(fmin, fmax - pd.Timedelta(days=365))
rango = st.sidebar.date_input("Rango de fechas", value=(default_ini, fmax), min_value=fmin, max_value=fmax)
if isinstance(rango, (list, tuple)) and len(rango) == 2:
    f_ini, f_fin = rango
else:
    f_ini, f_fin = fmin, fmax

mask = (df_temp_main["fecha"].dt.date >= f_ini) & (df_temp_main["fecha"].dt.date <= f_fin)
df = df_temp_main.loc[mask].copy().sort_values("fecha").reset_index(drop=True)
if df.empty:
    st.warning("No hay datos de temperatura en el rango seleccionado.")
    st.stop()

# Series complementarias activas
selected_tide_key = None
selected_wind_key = None
if wind_frames:
    wind_keys = list(wind_frames.keys())
    pref_wind = "LMB" if "LMB" in wind_keys else wind_keys[0]
    selected_wind_key = st.sidebar.selectbox("Serie de viento integrada", wind_keys, index=wind_keys.index(pref_wind))

st.sidebar.markdown("---")
st.sidebar.markdown("### 📦 Archivos integrados")
st.sidebar.caption("El app usa archivos CSV/TXT/Excel que estén dentro del proyecto, en la carpeta del script, /data, /fuentes o /mnt/data.")
st.sidebar.markdown(f"**Temperatura:** {len(temp_sources_meta)} archivo(s)")
st.sidebar.markdown(f"**Viento:** {len(wind_frames)} serie(s)")
st.sidebar.markdown(f"**Subidos manualmente:** {len(uploaded_sources_meta)} archivo(s)")

with st.sidebar.expander("Ver rutas detectadas"):
    st.write(f"Temperatura activa: {temp_paths_by_key.get(temp_key, 'N/D')}")
    if selected_wind_key:
        st.write(f"Viento activo: {selected_wind_key}")
    st.write("Rutas revisadas automáticamente:")
    for p in candidate_directories():
        st.write(f"- {p}")

if not wind_frames:
    st.sidebar.info("No se detectó archivo de viento. Colócalo dentro de /data o /fuentes para activarlo automáticamente.")

# ── Indicador de último dato y extensión de cada serie ────────────────────
import datetime as _dt

st.sidebar.markdown("---")
st.sidebar.markdown("### 🕐 Estado de las series")

_now_pan = _dt.datetime.utcnow() - _dt.timedelta(hours=5)  # UTC-5 Panamá

def _serie_card(label: str, df_s: pd.DataFrame, fecha_col: str = "fecha") -> None:
    """Muestra último dato, extensión temporal, total de registros y semáforo."""
    try:
        fechas = df_s[fecha_col].dropna()
        if fechas.empty:
            st.sidebar.caption(f"**{label}** — sin datos")
            return
        ultimo  = fechas.max()
        primero = fechas.min()
        n_total = len(fechas)
        lag_h   = max(0, (_now_pan - ultimo.replace(tzinfo=None)).total_seconds() / 3600)
        anos    = (ultimo - primero).days / 365.25
        dot     = "🟢" if lag_h < 6 else ("🟡" if lag_h < 48 else "🔴")
        color   = "#27ae60" if lag_h < 6 else ("#e67e22" if lag_h < 48 else "#e74c3c")
        lag_str = f"{int(lag_h)} h atrás" if lag_h < 48 else f"{lag_h/24:.1f} días atrás"
        st.sidebar.markdown(
            f"{dot} **{label}**  \n"
            f"<span style='font-size:0.88rem;color:{color};font-weight:600;'>"
            f"Último: {ultimo.strftime('%Y-%m-%d  %H:%M')} &nbsp;·&nbsp; {lag_str}"
            f"</span>  \n"
            f"<span style='font-size:0.78rem;color:#5d6d7e;'>"
            f"Desde {primero.strftime('%Y-%m-%d')} &nbsp;·&nbsp; "
            f"{anos:.1f} años &nbsp;·&nbsp; {n_total:,} registros"
            f"</span>",
            unsafe_allow_html=True,
        )
    except Exception:
        st.sidebar.caption(f"**{label}** — error al leer")

# Temperatura — todas las fuentes
for _k, _df_k in temp_frames.items():
    _serie_card(f"🌡️ Temp · {_k}", _df_k, "fecha")

# Viento — todas las series
for _wk, _df_w in wind_frames.items():
    _serie_card(f"💨 Viento · {_wk}", _df_w, "fecha")


# ============================================================
# HEADER
# ============================================================
header_logo_path = None
for logo in logo_candidates:
    if logo.exists():
        header_logo_path = str(logo)
        break

header_col1, header_col2 = st.columns([1, 5])
with header_col1:
    if header_logo_path:
        st.image(header_logo_path, width=140)

with header_col2:
    # Construir etiqueta de estaciones activas
    _active_stations_parts = []
    _temp_st = infer_active_temp_station(temp_key, temp_paths_by_key)
    _STATION_NAMES = {"AMA": "AMA · Amador", "LMB": "LMB · Limon Bay", "DHT": "DHT", "FLC": "FLC"}
    if _temp_st != "N/D":
        _active_stations_parts.append(f"Temp: <b>{_STATION_NAMES.get(_temp_st, _temp_st)}</b>")
    if selected_wind_key:
        _wst = _STATION_NAMES.get(selected_wind_key.upper().replace(" ", ""), selected_wind_key)
        _active_stations_parts.append(f"Viento: <b>{_wst}</b>")
    _stations_html = " &nbsp;|&nbsp; ".join(_active_stations_parts) if _active_stations_parts else "N/D"

    st.markdown(
        f"""
        <div style="display:flex; align-items:center; justify-content:space-between; gap:16px;">
            <div>
                <h1 style="margin:0; color:#c0392b;">🌡️ Dashboard Integrado de Temperatura, Viento y Surgencias</h1>
                <p style="margin:4px 0 0 0; color:#5d6d7e; font-size:1.05rem;">
                    Canal de Panamá · HIMH · Fuente principal: <b>{temp_key}</b>
                </p>
                <p style="margin:4px 0 0 0; color:#2c3e50; font-size:0.97rem; background:#eaf3ff; display:inline-block; padding:3px 10px; border-radius:6px;">
                    📍 Estaciones activas: {_stations_html}
                    &nbsp;&nbsp;<span style="color:#7f8c8d; font-size:0.85rem;">(AMA = Amador &nbsp;|&nbsp; LMB = Limon Bay)</span>
                </p>
            </div>
            <div style="text-align:right; color:#5d6d7e; font-size:0.95rem;">
                <div><b>Período:</b> {f_ini} → {f_fin}</div>
                <div><b>Registros:</b> {len(df):,}</div>
                <div><b>Creador:</b> {AUTHOR_FOOTER}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("Actual", f"{df[col_t].iloc[-1]:.1f} {unidad}")
k2.metric("Promedio", f"{df[col_t].mean():.1f} {unidad}")
k3.metric("Máxima", f"{df[col_t].max():.1f} {unidad}")
k4.metric("Mínima", f"{df[col_t].min():.1f} {unidad}")
k5.metric("Desv. Est.", f"{df[col_t].std():.2f} {unidad}")
k6.metric("Período", f"{(df['fecha'].max() - df['fecha'].min()).days} días")

st.markdown("---")

# ============================================================
# TABS
# ============================================================
tab_names = [
    "🧭 Panel ejecutivo",
    "🏠 Resumen",
    "📈 Serie temporal",
    "📅 Ciclos",
    "🧩 Climatología de etapas",
    "🗺️ Heatmap",
    "🌀 Surgencias",
    "🔍 Anomalías",
    "📉 Cambio térmico",
    "🧾 Seguimiento térmico",
]
if selected_wind_key:
    tab_names.append("💨 Temp vs viento")
if "Telemetría" in temp_frames and "LAN" in temp_frames:
    tab_names.append("🧪 Comparación de sensores")
tab_names.append("📊 Comparación anual")
tab_names.append("📥 Exportar")

tabs = st.tabs(tab_names)
tab_i = 0

# ============================================================
# TAB 0 — PANEL EJECUTIVO
# ============================================================
with tabs[tab_i]:
    st.subheader("Estado reciente y señal operativa")
    daily = df.set_index("fecha")[[col_t]].resample("1D").mean().dropna().reset_index()
    recent_7 = daily.tail(7)[col_t].mean() if len(daily) >= 1 else np.nan
    recent_30 = daily.tail(30)[col_t].mean() if len(daily) >= 1 else np.nan
    recent_90 = daily.tail(90)[col_t].mean() if len(daily) >= 1 else np.nan
    active_station = infer_active_temp_station(temp_key, temp_paths_by_key)
    phase_label, phase_msg, phase_color = classify_recent_ocean_phase(df, active_station)

    clima_mensual = monthly_climatology(df_temp_main, col_t)
    mes_actual = df["fecha"].max().month
    clima_row = clima_mensual[clima_mensual["mes"] == mes_actual]
    mes_clima = float(clima_row["mean"].iloc[0]) if not clima_row.empty else np.nan
    actual = float(df[col_t].iloc[-1])
    anom = actual - mes_clima if not np.isnan(mes_clima) else np.nan

    e1, e2, e3, e4 = st.columns(4)
    with e1:
        metric_card("Actual", f"{actual:.2f} {unidad}", "último dato", "#fff5f5")
    with e2:
        metric_card("Media 7 días", f"{recent_7:.2f} {unidad}", "promedio reciente", "#eef7ff")
    with e3:
        metric_card("Media 30 días", f"{recent_30:.2f} {unidad}", "referencia reciente", "#f2fbf7")
    with e4:
        metric_card("Anomalía mensual", f"{anom:+.2f} {unidad}" if not np.isnan(anom) else "N/D", f"vs climatología de {MESES[mes_actual-1]}", "#fbf3ff")

    sev_col1, sev_col2, sev_col3 = st.columns([1.1, 2, 2])
    with sev_col1:
        p10 = df[col_t].quantile(0.10)
        p90 = df[col_t].quantile(0.90)
        if actual <= p10:
            estado = "Bajo"
            color_box = "#eaf3ff"
            msg = "Temperatura en banda fría del período seleccionado."
        elif actual >= p90:
            estado = "Alto"
            color_box = "#fff0ef"
            msg = "Temperatura en banda cálida del período seleccionado."
        else:
            estado = "Normal"
            color_box = "#edf9f0"
            msg = "Temperatura dentro del rango central del período."
        metric_card("Estado térmico", estado, msg, color_box)

        diff_7_30 = recent_7 - recent_30
        trend_txt = "Enfriamiento" if diff_7_30 < -0.2 else "Calentamiento" if diff_7_30 > 0.2 else "Estable"
        metric_card("Pulso reciente", trend_txt, f"Δ 7d vs 30d = {diff_7_30:+.2f} {unidad}", "#f7f9fa")
        metric_card("Fase reciente", phase_label, phase_msg, phase_color)

    with sev_col2:
        st.markdown("#### Últimos 90 días")
        last90 = df[df["fecha"] >= df["fecha"].max() - timedelta(days=90)].copy()
        plot90 = last90.set_index("fecha")[[col_t]].resample("1D").mean().dropna().reset_index()
        fig90 = go.Figure()
        fig90.add_trace(go.Scatter(x=plot90["fecha"], y=plot90[col_t], mode="lines", line=dict(color=C["rojo"], width=2), fill="tozeroy", fillcolor=C["rojo_suave"], name="Temp diaria"))
        if not np.isnan(mes_clima):
            fig90.add_hline(y=mes_clima, line_dash="dash", line_color=C["azul"], annotation_text=f"Clima mes: {mes_clima:.1f} {unidad}")
        fig90.update_layout(template="plotly_white", height=340, yaxis_title=f"Temperatura ({unidad})", margin=dict(l=40, r=20, t=10, b=40))
        st.plotly_chart(fig90, use_container_width=True)

    with sev_col3:
        st.markdown("#### Climatología mensual")
        fig_clima = go.Figure()
        fig_clima.add_trace(go.Bar(x=[MESES[m-1] for m in clima_mensual["mes"]], y=clima_mensual["mean"], marker_color=[C["naranja"] if m in SECA_MESES else C["azul"] for m in clima_mensual["mes"]], error_y=dict(type="data", array=clima_mensual["std"], visible=True), name="Promedio"))
        fig_clima.add_hline(y=actual, line_color=C["rojo"], line_dash="dot", annotation_text=f"Actual: {actual:.1f} {unidad}")
        fig_clima.update_layout(template="plotly_white", height=340, yaxis_title=f"Temperatura media ({unidad})", margin=dict(l=40, r=20, t=10, b=40))
        st.plotly_chart(fig_clima, use_container_width=True)

    st.markdown("---")
    r1, r2 = st.columns(2)
    with r1:
        q = {"P10": df[col_t].quantile(0.10), "P25": df[col_t].quantile(0.25), "P50": df[col_t].quantile(0.50), "P75": df[col_t].quantile(0.75), "P90": df[col_t].quantile(0.90)}
        table_q = pd.DataFrame({"Percentil": list(q.keys()), f"Valor ({unidad})": [round(v, 2) for v in q.values()]})
        st.dataframe(table_q, use_container_width=True, hide_index=True)
    with r2:
        bullets = [
            f"Fuente principal activa: **{temp_key}**.",
            f"Temperatura actual: **{actual:.2f} {unidad}**, con media de **{df[col_t].mean():.2f} {unidad}** en el período.",
            f"La señal reciente muestra **{trend_txt.lower()}** respecto a la media de 30 días ({diff_7_30:+.2f} {unidad}).",
            f"Clasificación reciente: **{phase_label}**. {phase_msg}",
        ]
        if selected_wind_key:
            bullets.append(f"Serie de viento integrada: **{selected_wind_key}**.")
        bullets.append(f"Crédito del tablero: **{AUTHOR_FOOTER}**.")
        st.markdown("\n".join([f"- {b}" for b in bullets]))
tab_i += 1

# ============================================================
# TAB 1 — RESUMEN
# ============================================================
with tabs[tab_i]:
    st.subheader("Resumen estadístico del período")
    c1, c2, c3 = st.columns(3)

    with c1:
        ult30 = df[df["fecha"] >= df["fecha"].max() - timedelta(days=30)].copy()
        d30 = ult30.set_index("fecha")[[col_t]].resample("1D").mean().dropna().reset_index()
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=d30["fecha"], y=d30[col_t], mode="lines", line=dict(color=C["rojo"], width=2), fill="tozeroy", fillcolor=C["rojo_suave"]))
        fig.update_layout(template="plotly_white", height=240, title="Últimos 30 días", margin=dict(l=40, r=20, t=35, b=30))
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        dist = go.Figure()
        dist.add_trace(go.Histogram(x=df[col_t], nbinsx=70, marker_color=C["azul"]))
        dist.add_vline(x=df[col_t].mean(), line_dash="dash", line_color=C["rojo"], annotation_text=f"Media {df[col_t].mean():.1f}")
        dist.update_layout(template="plotly_white", height=240, title="Distribución", margin=dict(l=40, r=20, t=35, b=30))
        st.plotly_chart(dist, use_container_width=True)

    with c3:
        aux = df.copy()
        aux["mes"] = aux["fecha"].dt.month
        box = go.Figure()
        for m in sorted(aux["mes"].unique()):
            box.add_trace(go.Box(y=aux.loc[aux["mes"] == m, col_t], name=MESES[m-1], boxmean=True))
        box.update_layout(template="plotly_white", height=240, title="Box plot mensual", showlegend=False, margin=dict(l=40, r=20, t=35, b=30))
        st.plotly_chart(box, use_container_width=True)

    st.markdown("---")
    t1, t2 = st.columns(2)
    with t1:
        summary = pd.DataFrame({
            "Indicador": ["Registros", "Promedio", "Desv. est.", "Mínima", "Máxima", "Rango", "Percentil 90"],
            "Valor": [
                f"{len(df):,}",
                f"{df[col_t].mean():.2f} {unidad}",
                f"{df[col_t].std():.2f} {unidad}",
                f"{df[col_t].min():.2f} {unidad}",
                f"{df[col_t].max():.2f} {unidad}",
                f"{(df[col_t].max()-df[col_t].min()):.2f} {unidad}",
                f"{df[col_t].quantile(0.90):.2f} {unidad}",
            ],
        })
        st.dataframe(summary, use_container_width=True, hide_index=True)

    with t2:
        m = df.copy()
        m["anio"] = m["fecha"].dt.year
        m["mes"] = m["fecha"].dt.month
        monthly = m.groupby(["anio", "mes"])[col_t].mean().reset_index()
        monthly["Mes"] = monthly["mes"].map(lambda x: MESES[x-1])
        st.dataframe(monthly.rename(columns={"anio": "Año", col_t: f"Promedio ({unidad})"})[["Año", "Mes", f"Promedio ({unidad})"]], use_container_width=True, hide_index=True, height=320)
tab_i += 1

# ============================================================
# TAB 2 — SERIE TEMPORAL
# ============================================================
with tabs[tab_i]:
    st.subheader("Serie temporal")
    plot_df, reduced = resample_if_needed(df, col_t)
    if reduced:
        st.caption(f"Visualización resumida para mejorar desempeño ({len(plot_df):,} puntos).")

    fig = go.Figure()
    fig.add_trace(go.Scattergl(x=plot_df["fecha"], y=plot_df[col_t], mode="lines", line=dict(color=C["rojo"], width=1), fill="tozeroy", fillcolor=C["rojo_suave"], name="Temperatura"))
    fig.add_hline(y=df[col_t].mean(), line_dash="dash", line_color=C["azul"], annotation_text=f"Promedio {df[col_t].mean():.1f} {unidad}")
    fig.update_layout(template="plotly_white", height=500, hovermode="x unified", yaxis_title=f"Temperatura ({unidad})", margin=dict(l=45, r=20, t=20, b=40))
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### Promedio móvil")
    window_days = st.slider("Ventana (días)", 1, 180, 30, key="ma_days")
    hourly = df.set_index("fecha")[[col_t]].resample("1h").mean()
    w = window_days * 24
    hourly["media"] = hourly[col_t].rolling(w, min_periods=24).mean()
    hourly["std"] = hourly[col_t].rolling(w, min_periods=24).std()
    hourly["upper"] = hourly["media"] + hourly["std"]
    hourly["lower"] = hourly["media"] - hourly["std"]
    roll = hourly.dropna().reset_index()
    if len(roll) > 12000:
        roll = roll.set_index("fecha")[["media", "upper", "lower"]].resample("6h").mean().dropna().reset_index()

    fig_roll = go.Figure()
    fig_roll.add_trace(go.Scatter(x=list(roll["fecha"]) + list(roll["fecha"][::-1]), y=list(roll["upper"]) + list(roll["lower"][::-1]), fill="toself", fillcolor="rgba(52,152,219,0.12)", line=dict(color="rgba(0,0,0,0)"), showlegend=False))
    fig_roll.add_trace(go.Scatter(x=roll["fecha"], y=roll["media"], mode="lines", line=dict(color=C["morado"], width=2.2), name=f"Media {window_days}d"))
    fig_roll.update_layout(template="plotly_white", height=360, yaxis_title=f"Temperatura ({unidad})", margin=dict(l=45, r=20, t=20, b=40))
    st.plotly_chart(fig_roll, use_container_width=True)
tab_i += 1

# ============================================================
# TAB 3 — CICLOS
# ============================================================
with tabs[tab_i]:
    st.subheader("Ciclos diarios y estacionales")
    aux = df.copy()
    aux["hora"] = aux["fecha"].dt.hour
    aux["mes"] = aux["fecha"].dt.month
    c1, c2 = st.columns(2)

    with c1:
        ph = aux.groupby("hora")[col_t].agg(["mean", "std", "min", "max"]).reset_index()
        fig_h = go.Figure()
        fig_h.add_trace(go.Scatter(x=list(ph["hora"]) + list(ph["hora"][::-1]), y=list(ph["max"]) + list(ph["min"][::-1]), fill="toself", fillcolor="rgba(231,76,60,0.10)", line=dict(color="rgba(0,0,0,0)"), name="Rango"))
        fig_h.add_trace(go.Scatter(x=ph["hora"], y=ph["mean"], mode="lines+markers", line=dict(color=C["rojo"], width=2.5), name="Promedio", error_y=dict(type="data", array=ph["std"], visible=True)))
        fig_h.update_layout(template="plotly_white", height=380, xaxis_title="Hora", yaxis_title=f"Temperatura ({unidad})", margin=dict(l=45, r=20, t=20, b=40))
        st.plotly_chart(fig_h, use_container_width=True)

    with c2:
        pm = aux.groupby("mes")[col_t].agg(["mean", "std", "min", "max"]).reset_index()
        fig_m = go.Figure()
        fig_m.add_trace(go.Bar(x=[MESES[m-1] for m in pm["mes"]], y=pm["mean"], marker_color=[C["naranja"] if m in SECA_MESES else C["azul"] for m in pm["mes"]], error_y=dict(type="data", array=pm["std"], visible=True), name="Promedio"))
        fig_m.add_trace(go.Scatter(x=[MESES[m-1] for m in pm["mes"]], y=pm["max"], mode="lines+markers", line=dict(color=C["rojo"], dash="dot"), name="Máx"))
        fig_m.add_trace(go.Scatter(x=[MESES[m-1] for m in pm["mes"]], y=pm["min"], mode="lines+markers", line=dict(color=C["azul"], dash="dot"), name="Mín"))
        fig_m.update_layout(template="plotly_white", height=380, yaxis_title=f"Temperatura ({unidad})", margin=dict(l=45, r=20, t=20, b=40))
        st.plotly_chart(fig_m, use_container_width=True)

    st.markdown("#### Seca vs lluviosa")
    aux["temporada"] = np.where(aux["mes"].isin(list(SECA_MESES)), "Seca", "Lluviosa")
    box = go.Figure()
    box.add_trace(go.Box(y=aux.loc[aux["temporada"] == "Seca", col_t], name="Seca", boxmean=True, marker_color=C["naranja"]))
    box.add_trace(go.Box(y=aux.loc[aux["temporada"] == "Lluviosa", col_t], name="Lluviosa", boxmean=True, marker_color=C["azul"]))
    box.update_layout(template="plotly_white", height=360, yaxis_title=f"Temperatura ({unidad})", showlegend=False, margin=dict(l=45, r=20, t=20, b=40))
    st.plotly_chart(box, use_container_width=True)
tab_i += 1

# ============================================================
# TAB — CLIMATOLOGÍA DE ETAPAS
# ============================================================
with tabs[tab_i]:
    st.subheader("Climatología de etapas")
    active_station = infer_active_temp_station(temp_key, temp_paths_by_key)

    if active_station != "AMA":
        st.info(f"La climatología de etapas está calibrada para AMA. Estación activa detectada: {active_station}.")
    else:
        stage_base = df_temp_main.copy()
        if unidad == "°C":
            stage_col = "temp_c"
        else:
            stage_col = "temp_f"

        daily_stage = (
            stage_base.set_index("fecha")[[stage_col]]
            .resample("1D")
            .mean()
            .dropna()
            .reset_index()
        )
        daily_stage["etapa"] = daily_stage["fecha"].apply(lambda x: assign_climatology_stage(x, active_station))
        daily_stage["anio"] = daily_stage["fecha"].dt.year

        resumen_etapas = (
            daily_stage.groupby("etapa")[stage_col]
            .agg(["mean", "std", "min", "max", "count"])
            .reset_index()
        )
        orden = ["Afloramiento", "Transición", "Temporada cálida"]
        resumen_etapas["orden"] = resumen_etapas["etapa"].map({k: i for i, k in enumerate(orden)})
        resumen_etapas = resumen_etapas.sort_values("orden").drop(columns="orden")
        resumen_etapas = resumen_etapas.rename(
            columns={
                "etapa": "Etapa",
                "mean": f"Promedio ({unidad})",
                "std": f"Desv. est. ({unidad})",
                "min": f"Mínimo ({unidad})",
                "max": f"Máximo ({unidad})",
                "count": "Días",
            }
        )

        c1, c2 = st.columns(2)
        with c1:
            fig_stage = go.Figure()
            fig_stage.add_trace(
                go.Bar(
                    x=resumen_etapas["Etapa"],
                    y=resumen_etapas[f"Promedio ({unidad})"],
                    marker_color=[C["azul"], C["naranja"], C["verde"]],
                    error_y=dict(type="data", array=resumen_etapas[f"Desv. est. ({unidad})"], visible=True),
                )
            )
            fig_stage.update_layout(template="plotly_white", height=360, yaxis_title=f"Temperatura ({unidad})", margin=dict(l=45, r=20, t=20, b=40))
            st.plotly_chart(fig_stage, use_container_width=True)

        with c2:
            stage_year = (
                daily_stage.groupby(["anio", "etapa"])[stage_col]
                .mean()
                .reset_index()
            )
            pivot_stage = stage_year.pivot(index="anio", columns="etapa", values=stage_col)
            pivot_stage = pivot_stage.reindex(columns=orden)
            fig_heat = go.Figure(
                data=go.Heatmap(
                    z=pivot_stage.values,
                    x=pivot_stage.columns,
                    y=pivot_stage.index,
                    colorscale="RdYlBu_r",
                    colorbar_title=unidad,
                    hovertemplate="Año %{y}<br>Etapa %{x}<br>Temp %{z:.2f}<extra></extra>",
                )
            )
            fig_heat.update_layout(template="plotly_white", height=360, margin=dict(l=45, r=20, t=20, b=40))
            st.plotly_chart(fig_heat, use_container_width=True)

        st.markdown("#### Tabla resumen por etapa")
        st.dataframe(resumen_etapas.round(2), use_container_width=True, hide_index=True)

        st.markdown("#### Seguimiento anual por etapa")
        fig_lines = go.Figure()
        colores_etapas = {"Afloramiento": C["azul"], "Transición": C["naranja"], "Temporada cálida": C["verde"]}
        for etapa in orden:
            sub = stage_year[stage_year["etapa"] == etapa]
            if not sub.empty:
                fig_lines.add_trace(go.Scatter(x=sub["anio"], y=sub[stage_col], mode="lines+markers", name=etapa, line=dict(color=colores_etapas[etapa], width=2)))
        fig_lines.update_layout(template="plotly_white", height=360, yaxis_title=f"Temperatura media ({unidad})", xaxis_title="Año", margin=dict(l=45, r=20, t=20, b=40))
        st.plotly_chart(fig_lines, use_container_width=True)

tab_i += 1

# ============================================================
# TAB 4 — HEATMAP
# ============================================================
with tabs[tab_i]:
    st.subheader("Mapas de calor")
    aux = df.copy()
    aux["anio"] = aux["fecha"].dt.year
    aux["mes"] = aux["fecha"].dt.month
    aux["hora"] = aux["fecha"].dt.hour

    pt = aux.groupby(["anio", "mes"])[col_t].mean().reset_index().pivot(index="anio", columns="mes", values=col_t)
    pt = pt.reindex(columns=sorted(pt.columns))
    pt.columns = [MESES[m-1] for m in pt.columns]
    fig1 = go.Figure(data=go.Heatmap(z=pt.values, x=pt.columns, y=pt.index, colorscale="RdYlBu_r", colorbar_title=unidad, hovertemplate="Año %{y}<br>Mes %{x}<br>Temp %{z:.2f}<extra></extra>"))
    fig1.update_layout(template="plotly_white", height=max(350, len(pt) * 26), margin=dict(l=55, r=20, t=20, b=40))
    st.plotly_chart(fig1, use_container_width=True)

    pt2 = aux.groupby(["hora", "mes"])[col_t].mean().reset_index().pivot(index="hora", columns="mes", values=col_t)
    pt2 = pt2.reindex(columns=sorted(pt2.columns))
    pt2.columns = [MESES[m-1] for m in pt2.columns]
    fig2 = go.Figure(data=go.Heatmap(z=pt2.values, x=pt2.columns, y=pt2.index, colorscale="RdYlBu_r", colorbar_title=unidad, hovertemplate="Hora %{y}<br>Mes %{x}<br>Temp %{z:.2f}<extra></extra>"))
    fig2.update_layout(template="plotly_white", height=430, margin=dict(l=55, r=20, t=20, b=40))
    st.plotly_chart(fig2, use_container_width=True)
tab_i += 1

# ============================================================
# TAB 5 — SURGENCIAS
# ============================================================
with tabs[tab_i]:
    st.subheader("Tablero de surgencias / afloramiento")
    st.caption("Este tablero se orienta a identificar pulsos fríos persistentes, su intensidad, su distribución estacional y su relación con forzantes oceanográficos y atmosféricos.")
    active_station = infer_active_temp_station(temp_key, temp_paths_by_key)
    phase_label, phase_msg, phase_color = classify_recent_ocean_phase(df, active_station)

    s1, s2 = st.columns([1.15, 3])
    with s1:
        if unidad == "°C":
            umbral = st.slider("Umbral térmico de surgencia", 18.0, 30.0, 25.0, 0.5)
        else:
            umbral = st.slider("Umbral térmico de surgencia", 64.0, 86.0, 77.0, 0.5)
        min_h = st.slider("Duración mínima (horas)", 1, 72, 6)
        rolling_ref = st.slider("Referencia móvil (días)", 3, 45, 15)

    eventos = detect_upwelling_events(df, col_t, umbral, min_h)

    with s1:
        total_h = int(eventos["duracion_h"].sum()) if not eventos.empty else 0
        pct = (eventos["duracion_h"].sum() / len(df) * 100) if not eventos.empty else 0
        metric_card("Fase reciente", phase_label, phase_msg, phase_color)
        metric_card("Eventos detectados", f"{len(eventos):,}", "episodios con persistencia", "#eef7ff")
        metric_card("Horas totales", f"{total_h:,}", "duración acumulada", "#f4fbf6")
        metric_card("% del período", f"{pct:.1f}%", "proporción bajo umbral", "#fff7ed")
        if not eventos.empty:
            metric_card("Temp mínima", f"{eventos['temp_min'].min():.2f} {unidad}", "mínimo en eventos", "#fff2f2")
            metric_card("Intensidad máxima", f"{eventos['intensidad'].max():.2f} {unidad}", "umbral - mínimo", "#f7f1ff")
            metric_card("Mayor duración", f"{int(eventos['duracion_h'].max())} h", "episodio más persistente", "#eef8fb")

    with s2:
        plot_s, _ = resample_if_needed(df, col_t)
        ref = df.set_index("fecha")[[col_t]].resample("1h").mean().dropna()
        ref["media_movil"] = ref[col_t].rolling(rolling_ref * 24, min_periods=24).mean()
        ref = ref.reset_index()

        fig = go.Figure()
        for _, ev in eventos.iterrows():
            fig.add_vrect(x0=ev["inicio"], x1=ev["fin"], fillcolor="rgba(41,128,185,0.16)", line_width=0)
        fig.add_trace(go.Scattergl(x=plot_s["fecha"], y=plot_s[col_t], mode="lines", line=dict(color=C["rojo"], width=1), name="Temperatura"))
        if not ref.empty:
            ref_plot, _ = resample_if_needed(ref.dropna(), "media_movil")
            fig.add_trace(go.Scatter(x=ref_plot["fecha"], y=ref_plot["media_movil"], mode="lines", line=dict(color=C["morado"], width=2), name=f"Media {rolling_ref}d"))
        fig.add_hline(y=umbral, line_color=C["azul"], line_dash="dash", annotation_text=f"Umbral {umbral:.1f} {unidad}")
        fig.update_layout(template="plotly_white", height=470, yaxis_title=f"Temperatura ({unidad})", hovermode="x unified", margin=dict(l=45, r=20, t=20, b=40))
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")
    c1, c2, c3 = st.columns(3)
    with c1:
        if not eventos.empty:
            by_month = eventos.groupby("mes")["duracion_h"].sum().reindex(range(1, 13), fill_value=0)
            fig_m = go.Figure(go.Bar(x=MESES, y=by_month.values, marker_color=[C["azul"] if i + 1 in SECA_MESES else C["gris"] for i in range(12)]))
            fig_m.update_layout(template="plotly_white", height=320, yaxis_title="Horas de surgencia", margin=dict(l=45, r=20, t=20, b=40))
            st.plotly_chart(fig_m, use_container_width=True)
        else:
            st.info("Sin eventos detectados con el criterio seleccionado.")

    with c2:
        if not eventos.empty:
            by_year = eventos.groupby("anio")["duracion_h"].sum().reset_index()
            fig_y = go.Figure()
            fig_y.add_trace(go.Bar(x=by_year["anio"], y=by_year["duracion_h"], marker_color=C["turquesa"]))
            if len(by_year) >= 3:
                slope, intercept, r, p, _ = sp_stats.linregress(by_year["anio"], by_year["duracion_h"])
                fig_y.add_trace(go.Scatter(x=by_year["anio"], y=slope * by_year["anio"] + intercept, mode="lines", line=dict(color=C["rojo"], dash="dash"), name=f"Tendencia p={p:.3f}"))
            fig_y.update_layout(template="plotly_white", height=320, yaxis_title="Horas de surgencia", margin=dict(l=45, r=20, t=20, b=40))
            st.plotly_chart(fig_y, use_container_width=True)
        else:
            st.empty()

    with c3:
        if not eventos.empty:
            ranking = eventos.sort_values(["intensidad", "duracion_h"], ascending=[False, False]).head(10).copy()
            ranking["evento"] = ranking["inicio"].dt.strftime("%Y-%m-%d")
            fig_r = go.Figure(go.Bar(x=ranking["intensidad"], y=ranking["evento"], orientation="h", marker_color=C["morado"]))
            fig_r.update_layout(template="plotly_white", height=320, xaxis_title=f"Intensidad ({unidad})", yaxis_title="Evento", margin=dict(l=45, r=20, t=20, b=40))
            st.plotly_chart(fig_r, use_container_width=True)
        else:
            st.empty()

    if selected_wind_key and selected_wind_key in wind_frames:
        st.markdown("#### Apoyo del viento sobre el tablero de surgencias")
        wind_use = wind_frames[selected_wind_key].copy()
        temp_h = to_hourly(df, [col_t])
        wind_h = to_hourly(wind_use, ["viento_ms"])
        sw = temp_h.merge(wind_h, on="fecha", how="inner")
        if not sw.empty:
            sw["below"] = sw[col_t] < umbral
            wind_ev = sw.groupby("below")["viento_ms"].mean().reset_index()
            frio = float(wind_ev.loc[wind_ev["below"] == True, "viento_ms"].iloc[0]) if (wind_ev["below"] == True).any() else np.nan
            normal = float(wind_ev.loc[wind_ev["below"] == False, "viento_ms"].iloc[0]) if (wind_ev["below"] == False).any() else np.nan
            g1, g2 = st.columns(2)
            with g1:
                fig_w = go.Figure()
                fig_w.add_trace(go.Box(y=sw.loc[sw["below"], "viento_ms"], name="Bajo umbral", boxmean=True, marker_color=C["azul"]))
                fig_w.add_trace(go.Box(y=sw.loc[~sw["below"], "viento_ms"], name="Sobre umbral", boxmean=True, marker_color=C["naranja"]))
                fig_w.update_layout(template="plotly_white", height=320, yaxis_title="Viento (m/s)", margin=dict(l=45, r=20, t=20, b=40))
                st.plotly_chart(fig_w, use_container_width=True)
            with g2:
                bullets = [
                    f"Serie de viento integrada al tablero: **{selected_wind_key}**.",
                    f"Viento medio con temperatura bajo umbral: **{frio:.2f} m/s**." if np.isfinite(frio) else "No se pudo estimar el viento medio bajo umbral.",
                    f"Viento medio sobre umbral: **{normal:.2f} m/s**." if np.isfinite(normal) else "No se pudo estimar el viento medio sobre umbral.",
                    "Esto permite usar el tablero de surgencias no solo como pantalla térmica, sino como referencia operativa de forzamiento atmosférico.",
                ]
                st.markdown("\n".join([f"- {b}" for b in bullets]))

    if not eventos.empty:
        with st.expander("Ver tabla de eventos de surgencia"):
            view = eventos.copy()
            for c in ["temp_min", "temp_media", "intensidad"]:
                view[c] = view[c].round(2)
            st.dataframe(view, use_container_width=True, hide_index=True, height=320)
    else:
        st.info("No se detectaron eventos con el umbral y duración seleccionados.")
tab_i += 1

# ============================================================
# TAB 6 — ANOMALÍAS
# ============================================================
with tabs[tab_i]:
    st.subheader("Detección de anomalías")
    a1, a2 = st.columns([1, 3])
    with a1:
        metodo = st.radio("Método", ["Z-score", "Percentiles", "Media móvil"])
        if metodo == "Z-score":
            zthr = st.slider("Umbral Z", 1.0, 4.0, 2.5, 0.1)
        elif metodo == "Percentiles":
            pl = st.slider("Percentil inferior", 1, 20, 5)
            ph = st.slider("Percentil superior", 80, 99, 95)
        else:
            vdays = st.slider("Ventana (días)", 7, 90, 30)
            sig = st.slider("Sigmas", 1.0, 4.0, 2.0, 0.1)

    an = df.copy()
    if metodo == "Z-score":
        z = np.abs((an[col_t] - an[col_t].mean()) / an[col_t].std())
        an["anom"] = z > zthr
    elif metodo == "Percentiles":
        low = an[col_t].quantile(pl / 100)
        high = an[col_t].quantile(ph / 100)
        an["anom"] = (an[col_t] < low) | (an[col_t] > high)
    else:
        roll = an.set_index("fecha")[[col_t]].resample("1h").mean()
        w = vdays * 24
        roll["mu"] = roll[col_t].rolling(w, min_periods=24).mean()
        roll["sd"] = roll[col_t].rolling(w, min_periods=24).std()
        roll["upper"] = roll["mu"] + sig * roll["sd"]
        roll["lower"] = roll["mu"] - sig * roll["sd"]
        roll = roll.dropna().reset_index()
        an = an.merge(roll[["fecha", "upper", "lower"]], on="fecha", how="inner")
        an["anom"] = (an[col_t] > an["upper"]) | (an[col_t] < an["lower"])

    anomalies = an[an["anom"]].copy()
    normals = an[~an["anom"]].copy()
    with a1:
        st.metric("Anomalías", f"{len(anomalies):,}")
        st.metric("% del total", f"{(len(anomalies)/len(an)*100):.2f}%")

    with a2:
        plot_n, _ = resample_if_needed(normals[["fecha", col_t]], col_t)
        fig = go.Figure()
        fig.add_trace(go.Scattergl(x=plot_n["fecha"], y=plot_n[col_t], mode="lines", line=dict(color=C["gris"], width=0.8), name="Normal"))
        fig.add_trace(go.Scattergl(x=anomalies["fecha"], y=anomalies[col_t], mode="markers", marker=dict(color=C["rojo"], size=4, opacity=0.6), name="Anomalía"))
        fig.update_layout(template="plotly_white", height=450, yaxis_title=f"Temperatura ({unidad})", hovermode="x unified", margin=dict(l=45, r=20, t=20, b=40))
        st.plotly_chart(fig, use_container_width=True)

    if not anomalies.empty:
        with st.expander("Ver anomalías"):
            st.dataframe(anomalies[["fecha", col_t]].rename(columns={"fecha": "Fecha", col_t: f"Temp ({unidad})"}), use_container_width=True, hide_index=True, height=300)
tab_i += 1

# ============================================================
# TAB 7 — CAMBIO TÉRMICO
# ============================================================
with tabs[tab_i]:
    st.subheader("Cambio térmico")
    daily_change = df.set_index("fecha")[[col_t]].resample("1D").mean().dropna().reset_index()
    if len(daily_change) < 8:
        st.info("Se requieren más datos diarios para evaluar cambios de temperatura.")
    else:
        daily_change["delta_1d"] = daily_change[col_t].diff()
        daily_change["delta_7d"] = daily_change[col_t] - daily_change[col_t].shift(7)
        daily_change["delta_30d"] = daily_change[col_t] - daily_change[col_t].shift(30)
        last30 = daily_change.tail(min(30, len(daily_change))).dropna(subset=[col_t])
        slope30 = np.polyfit(np.arange(len(last30)), last30[col_t], 1)[0] if len(last30) >= 5 else np.nan
        up_days = int((daily_change["delta_1d"] > 0).sum())
        down_days = int((daily_change["delta_1d"] < 0).sum())
        flat_days = int((daily_change["delta_1d"].abs() <= 0.05).sum())

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Δ 1 día", f"{daily_change['delta_1d'].iloc[-1]:+.2f} {unidad}" if pd.notna(daily_change['delta_1d'].iloc[-1]) else "N/D")
        c2.metric("Δ 7 días", f"{daily_change['delta_7d'].iloc[-1]:+.2f} {unidad}" if pd.notna(daily_change['delta_7d'].iloc[-1]) else "N/D")
        c3.metric("Δ 30 días", f"{daily_change['delta_30d'].iloc[-1]:+.2f} {unidad}" if pd.notna(daily_change['delta_30d'].iloc[-1]) else "N/D")
        c4.metric("Pendiente 30d", f"{slope30:+.3f} {unidad}/día" if np.isfinite(slope30) else "N/D")

        g1, g2 = st.columns(2)
        with g1:
            recent = daily_change.tail(120).copy()
            fig_delta = go.Figure()
            fig_delta.add_trace(go.Bar(x=recent["fecha"], y=recent["delta_1d"], name="Δ diaria"))
            fig_delta.add_hline(y=0, line_dash="dash", line_color=C["gris"])
            fig_delta.update_layout(template="plotly_white", height=340, yaxis_title=f"Cambio diario ({unidad})", margin=dict(l=45, r=20, t=20, b=40))
            st.plotly_chart(fig_delta, use_container_width=True)
        with g2:
            fig_rollchg = go.Figure()
            plot_chg = daily_change.dropna(subset=["delta_7d", "delta_30d"]).copy()
            fig_rollchg.add_trace(go.Scatter(x=plot_chg["fecha"], y=plot_chg["delta_7d"], mode="lines", line=dict(color=C["rojo"], width=2), name="Δ 7d"))
            fig_rollchg.add_trace(go.Scatter(x=plot_chg["fecha"], y=plot_chg["delta_30d"], mode="lines", line=dict(color=C["azul"], width=2), name="Δ 30d"))
            fig_rollchg.add_hline(y=0, line_dash="dash", line_color=C["gris"])
            fig_rollchg.update_layout(template="plotly_white", height=340, yaxis_title=f"Cambio acumulado ({unidad})", margin=dict(l=45, r=20, t=20, b=40))
            st.plotly_chart(fig_rollchg, use_container_width=True)

        st.markdown("#### Balance de días con aumento o disminución")
        balance = pd.DataFrame({
            "Condición": ["Días con aumento", "Días con disminución", "Días casi estables (±0.05)"] ,
            "Cantidad": [up_days, down_days, flat_days],
        })
        st.dataframe(balance, use_container_width=True, hide_index=True)

tab_i += 1

# ============================================================
# TAB 8 — SEGUIMIENTO TÉRMICO
# ============================================================
with tabs[tab_i]:
    st.subheader("Seguimiento térmico")
    weekly = df.set_index("fecha")[[col_t]].resample("1W").agg(["mean", "min", "max"]).dropna().reset_index()
    weekly.columns = ["fecha", "promedio", "minimo", "maximo"]
    if weekly.empty:
        st.info("Se requieren más datos para generar el seguimiento térmico.")
    else:
        weekly["delta_vs_semana_previa"] = weekly["promedio"].diff()
        weekly["media_4s"] = weekly["promedio"].rolling(4, min_periods=1).mean()

        s1, s2 = st.columns(2)
        with s1:
            fig_week = go.Figure()
            fig_week.add_trace(go.Scatter(x=weekly["fecha"], y=weekly["promedio"], mode="lines+markers", line=dict(color=C["rojo"], width=2), name="Promedio semanal"))
            fig_week.add_trace(go.Scatter(x=weekly["fecha"], y=weekly["media_4s"], mode="lines", line=dict(color=C["azul"], width=2, dash="dash"), name="Media 4 semanas"))
            fig_week.update_layout(template="plotly_white", height=340, yaxis_title=f"Temperatura ({unidad})", margin=dict(l=45, r=20, t=20, b=40))
            st.plotly_chart(fig_week, use_container_width=True)
        with s2:
            recentw = weekly.tail(16).copy()
            fig_band = go.Figure()
            fig_band.add_trace(go.Scatter(x=list(recentw["fecha"]) + list(recentw["fecha"][::-1]), y=list(recentw["maximo"]) + list(recentw["minimo"][::-1]), fill="toself", fillcolor="rgba(41,128,185,0.12)", line=dict(color="rgba(0,0,0,0)"), showlegend=False))
            fig_band.add_trace(go.Scatter(x=recentw["fecha"], y=recentw["promedio"], mode="lines+markers", line=dict(color=C["morado"], width=2), name="Promedio semanal"))
            fig_band.update_layout(template="plotly_white", height=340, yaxis_title=f"Rango semanal ({unidad})", margin=dict(l=45, r=20, t=20, b=40))
            st.plotly_chart(fig_band, use_container_width=True)

        st.markdown("#### Últimas semanas")
        show_weekly = weekly.tail(12).copy()
        for c in ["promedio", "minimo", "maximo", "delta_vs_semana_previa", "media_4s"]:
            show_weekly[c] = show_weekly[c].round(2)
        show_weekly = show_weekly.rename(columns={
            "fecha": "Semana",
            "promedio": f"Promedio ({unidad})",
            "minimo": f"Mínimo ({unidad})",
            "maximo": f"Máximo ({unidad})",
            "delta_vs_semana_previa": f"Δ vs semana previa ({unidad})",
            "media_4s": f"Media 4 semanas ({unidad})",
        })
        st.dataframe(show_weekly, use_container_width=True, hide_index=True, height=320)

tab_i += 1

# ============================================================
# TAB — TEMP VS VIENTO
# ============================================================
if selected_wind_key:
    with tabs[tab_i]:
        st.subheader(f"Temperatura vs viento · {selected_wind_key}")
        st.caption("La serie de viento se toma automáticamente desde los archivos integrados dentro del proyecto. Se añade un factor de intensidad del viento basado en esfuerzo del viento: τ = ρ·Cd·U², útil como proxy físico de afloramiento/enfriamiento inducido por viento.")
        df_viento = wind_frames[selected_wind_key].copy()
        uv = st.radio("Unidad de viento", ["m/s", "km/h", "kt"], horizontal=True)
        col_v = {"m/s": "viento_ms", "km/h": "viento_kmh", "kt": "viento_kt"}[uv]

        temp_station = infer_active_temp_station(temp_key, temp_paths_by_key)
        wind_station = selected_wind_key
        if temp_station not in {"N/D", wind_station}:
            st.info(f"Temperatura: {temp_station} · Viento: {wind_station}. Esta lectura es indicativa regional y no estrictamente colocalizada, por lo que conviene interpretarla como forzamiento de gran escala.")

        mv, daily_tw = build_temp_wind_diagnostics(df, df_viento, col_t)
        if not mv.empty:
            mv["viento_kmh"] = mv["viento_ms"] * 3.6
            mv["viento_kt"] = mv["viento_ms"] * 1.94384

        if mv.empty or len(mv) < 50:
            st.warning("No hay suficiente traslape entre temperatura y viento en el rango seleccionado.")
        else:
            corr = mv[col_t].corr(mv[col_v])
            corr_tau = mv[col_t].corr(mv["tau_n_m2"])
            daily_future_corr = daily_tw["tau_n_m2"].corr(daily_tw["delta_temp_fut_3d"]) if len(daily_tw) >= 10 else np.nan
            lags = list(range(-72, 73, 3))
            vals, best = lag_correlation(mv, "tau_n_m2", col_t, lags)

            k1, k2, k3, k4, k5 = st.columns(5)
            k1.metric("Coincidencias", f"{len(mv):,}")
            k2.metric("Correlación T vs V", f"{corr:.3f}")
            k3.metric("Correlación T vs τ", f"{corr_tau:.3f}")
            k4.metric("Mejor desfase τ→T", f"{best} h")
            k5.metric(f"Viento actual ({uv})", f"{mv[col_v].iloc[-1]:.1f} {uv}", f"τ = {mv['tau_n_m2'].iloc[-1]:.4f} N/m²")

            c1, c2 = st.columns(2)
            with c1:
                sample = mv.sample(min(6000, len(mv)), random_state=42)
                fig = go.Figure()
                fig.add_trace(go.Scattergl(x=sample[col_v], y=sample[col_t], mode="markers", marker=dict(size=4, opacity=0.32, color=sample["factor_intensidad"], colorscale="Viridis", colorbar=dict(title="Factor"))))
                z = np.polyfit(mv[col_v], mv[col_t], 1)
                xx = np.linspace(mv[col_v].min(), mv[col_v].max(), 100)
                fig.add_trace(go.Scatter(x=xx, y=np.polyval(z, xx), mode="lines", line=dict(color=C["rojo"], dash="dash"), name="Tendencia"))
                fig.update_layout(template="plotly_white", height=400, xaxis_title=f"Viento ({uv})", yaxis_title=f"Temperatura ({unidad})", margin=dict(l=45, r=20, t=20, b=40))
                st.plotly_chart(fig, use_container_width=True)
            with c2:
                s = mv.set_index("fecha")[[col_t, col_v, "factor_intensidad"]].resample("6h").mean().dropna().reset_index()
                fig2 = make_subplots(specs=[[{"secondary_y": True}]])
                fig2.add_trace(go.Scatter(x=s["fecha"], y=s[col_t], mode="lines", line=dict(color=C["rojo"]), name="Temp"), secondary_y=False)
                fig2.add_trace(go.Scatter(x=s["fecha"], y=s[col_v], mode="lines", line=dict(color=C["azul"]), name=f"Viento ({uv})"), secondary_y=True)
                fig2.update_yaxes(title_text=f"Temp ({unidad})", secondary_y=False)
                fig2.update_yaxes(title_text=f"Velocidad del viento ({uv})", secondary_y=True)
                fig2.update_layout(template="plotly_white", height=400, hovermode="x unified", margin=dict(l=45, r=55, t=20, b=40))
                st.plotly_chart(fig2, use_container_width=True)

            c3, c4 = st.columns(2)
            with c3:
                fig3 = go.Figure()
                fig3.add_trace(go.Scatter(x=lags, y=vals, mode="lines+markers", line=dict(color=C["morado"], width=2)))
                fig3.add_vline(x=0, line_dash="dash", line_color=C["gris"])
                fig3.add_vline(x=best, line_dash="dot", line_color=C["rojo"], annotation_text=f"Mayor relación {best} h")
                fig3.update_layout(template="plotly_white", height=320, xaxis_title="Desfase (horas)", yaxis_title="Correlación τ vs T", margin=dict(l=45, r=20, t=20, b=40))
                st.plotly_chart(fig3, use_container_width=True)
            with c4:
                daily_plot = daily_tw.dropna(subset=["delta_temp_fut_3d"]).copy()
                fig4 = go.Figure()
                fig4.add_trace(go.Scatter(x=daily_plot["tau_n_m2"], y=daily_plot["delta_temp_fut_3d"], mode="markers", marker=dict(size=6, opacity=0.45, color=daily_plot["factor_intensidad"], colorscale="Viridis", colorbar=dict(title="Factor"))))
                if len(daily_plot) >= 5:
                    z2 = np.polyfit(daily_plot["tau_n_m2"], daily_plot["delta_temp_fut_3d"], 1)
                    xx2 = np.linspace(daily_plot["tau_n_m2"].min(), daily_plot["tau_n_m2"].max(), 100)
                    fig4.add_trace(go.Scatter(x=xx2, y=np.polyval(z2, xx2), mode="lines", line=dict(color=C["rojo"], dash="dash"), name="Tendencia"))
                fig4.add_hline(y=0, line_dash="dash", line_color=C["gris"])
                fig4.update_layout(template="plotly_white", height=320, xaxis_title="Esfuerzo del viento τ (N/m²)", yaxis_title=f"Δ Temp futura 3d ({unidad})", margin=dict(l=45, r=20, t=20, b=40))
                st.plotly_chart(fig4, use_container_width=True)

            st.markdown("#### Respuesta térmica por intensidad diaria del viento")
            if not daily_tw.empty and daily_tw["categoria_intensidad"].nunique() >= 2:
                summary_tw = (
                    daily_tw.groupby("categoria_intensidad", dropna=False)[["viento_ms", "tau_n_m2", "delta_temp_1d", "delta_temp_fut_1d", "delta_temp_fut_3d", "delta_temp_fut_5d"]]
                    .mean()
                    .reset_index()
                    .rename(columns={
                        "categoria_intensidad": "Intensidad",
                        "viento_ms": "Viento medio (m/s)",
                        "tau_n_m2": "τ medio (N/m²)",
                        "delta_temp_1d": f"Δ Temp diaria ({unidad})",
                        "delta_temp_fut_1d": f"Δ Temp futura 1d ({unidad})",
                        "delta_temp_fut_3d": f"Δ Temp futura 3d ({unidad})",
                        "delta_temp_fut_5d": f"Δ Temp futura 5d ({unidad})",
                    })
                )
                numeric_cols = [c for c in summary_tw.columns if c != "Intensidad"]
                summary_tw[numeric_cols] = summary_tw[numeric_cols].round(3)
                st.dataframe(summary_tw, use_container_width=True, hide_index=True)
            else:
                st.info("No hay suficiente contraste diario para resumir la respuesta por categorías de intensidad del viento.")

            bullets = [
                "El factor de intensidad del viento usa un proxy físico de esfuerzo del viento (τ) proporcional a U².",
                f"Correlación instantánea T vs τ: **{corr_tau:.3f}**.",
                f"Correlación entre τ diario y cambio futuro de temperatura a 3 días: **{daily_future_corr:.3f}**." if np.isfinite(daily_future_corr) else "No hubo suficientes datos diarios para estimar la relación entre τ y el cambio futuro de temperatura.",
                f"El máximo acoplamiento estadístico apareció con un desfase de **{best} h** (según el rango evaluado).",
                "Valores negativos en Δ Temp futura indican enfriamiento posterior a un pulso de viento más intenso.",
            ]
            st.markdown("\n".join([f"- {b}" for b in bullets]))
    tab_i += 1

# ============================================================
# TAB — COMPARACIÓN DE SENSORES
# ============================================================
if "Telemetría" in temp_frames and "LAN" in temp_frames:
    with tabs[tab_i]:
        st.subheader("Comparación de sensores: Telemetría vs LAN")
        overlap = sensor_overlap_metrics(temp_frames["Telemetría"], temp_frames["LAN"])
        if overlap.empty:
            st.warning("No hay traslape temporal entre las series Telemetría y LAN.")
        else:
            overlap = overlap[(overlap["fecha"].dt.date >= f_ini) & (overlap["fecha"].dt.date <= f_fin)].copy()
            if overlap.empty:
                st.warning("No hay traslape temporal entre Telemetría y LAN dentro del rango seleccionado.")
            else:
                rmse = float(np.sqrt(np.mean((overlap["delta"]) ** 2)))
                bias = float(overlap["delta"].mean())
                mae = float(np.mean(np.abs(overlap["delta"])))
                corr = float(overlap["tele"].corr(overlap["lan"]))
                k1, k2, k3, k4 = st.columns(4)
                k1.metric("Traslape", f"{len(overlap):,} registros")
                k2.metric("Sesgo Tele-LAN", f"{bias:+.3f} °C")
                k3.metric("MAE", f"{mae:.3f} °C")
                k4.metric("RMSE", f"{rmse:.3f} °C")
                st.caption(f"Correlación entre sensores: r = {corr:.4f}")

                c1, c2 = st.columns(2)
                with c1:
                    plot_ol = overlap.set_index("fecha")[["tele", "lan"]].resample("1D").mean().dropna().reset_index()
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(x=plot_ol["fecha"], y=plot_ol["tele"], mode="lines", line=dict(color=C["rojo"]), name="Telemetría"))
                    fig.add_trace(go.Scatter(x=plot_ol["fecha"], y=plot_ol["lan"], mode="lines", line=dict(color=C["azul"]), name="LAN"))
                    fig.update_layout(template="plotly_white", height=380, yaxis_title="Temperatura (°C)", hovermode="x unified", margin=dict(l=45, r=20, t=20, b=40))
                    st.plotly_chart(fig, use_container_width=True)
                with c2:
                    sample = overlap.sample(min(8000, len(overlap)), random_state=42)
                    fig2 = go.Figure()
                    fig2.add_trace(go.Scattergl(x=sample["lan"], y=sample["tele"], mode="markers", marker=dict(size=4, opacity=0.28, color=sample["delta"], colorscale="RdBu")))
                    lo = min(sample["lan"].min(), sample["tele"].min())
                    hi = max(sample["lan"].max(), sample["tele"].max())
                    fig2.add_trace(go.Scatter(x=[lo, hi], y=[lo, hi], mode="lines", line=dict(color=C["oscuro"], dash="dash"), name="1:1"))
                    fig2.update_layout(template="plotly_white", height=380, xaxis_title="LAN (°C)", yaxis_title="Telemetría (°C)", margin=dict(l=45, r=20, t=20, b=40))
                    st.plotly_chart(fig2, use_container_width=True)
    tab_i += 1

# ============================================================
# TAB — COMPARACIÓN ANUAL
# ============================================================
with tabs[tab_i]:
    st.subheader("📊 Comparación interanual de temperatura")

    # Usamos la serie completa (sin filtro de fechas) para tener todos los años
    df_all = df_temp_main.copy()
    df_all["anio"] = df_all["fecha"].dt.year
    df_all["mes"]  = df_all["fecha"].dt.month
    df_all["dia_del_anio"] = df_all["fecha"].dt.dayofyear

    anios_disponibles = sorted(df_all["anio"].unique().tolist())

    if len(anios_disponibles) < 2:
        st.info("Se necesitan datos de al menos 2 años distintos para la comparación interanual.")
    else:
        # ── Selectores ─────────────────────────────────────────────────────
        cc1, cc2, cc3 = st.columns([2, 1, 1])
        with cc1:
            anios_sel = st.multiselect(
                "Seleccionar años a comparar",
                options=anios_disponibles,
                default=anios_disponibles[-min(4, len(anios_disponibles)):],
                help="Puedes elegir uno o más años. Se superponen en el mismo eje para facilitar la comparación.",
            )
        with cc2:
            resolucion = st.radio(
                "Resolución de la curva diaria",
                ["Diaria", "Semanal"],
                horizontal=True,
                help="Resolución del promedio para la gráfica de superposición.",
            )
        with cc3:
            mostrar_banda = st.checkbox(
                "Mostrar banda ±1σ del año de referencia",
                value=True,
                help="Muestra la banda de ±1 desviación estándar del primer año seleccionado como referencia.",
            )

        if not anios_sel:
            st.warning("Selecciona al menos un año.")
        else:
            freq_resample = "1D" if resolucion == "Diaria" else "7D"

            # Paleta de colores para los años
            PALETA_ANUAL = [
                "#e74c3c", "#2980b9", "#27ae60", "#e67e22",
                "#8e44ad", "#16a085", "#c0392b", "#2c3e50",
                "#d35400", "#1abc9c", "#f39c12", "#7f8c8d",
            ]

            # ── Pestaña interna ─────────────────────────────────────────────
            sub_t1, sub_t2, sub_t3, sub_t4 = st.tabs([
                "📈 Superposición anual",
                "📅 Promedio mensual",
                "📦 Distribución por mes",
                "📋 Estadísticas por año",
            ])

            # ── Sub-tab 1: Curvas superpuestas ──────────────────────────────
            with sub_t1:
                st.markdown("**Temperatura diaria (o semanal) superpuesta por año — eje X = día del año**")
                fig_sup = go.Figure()

                ref_std_x = None
                ref_std_y_upper = None
                ref_std_y_lower = None

                for idx, anio in enumerate(anios_sel):
                    df_y = df_all[df_all["anio"] == anio].copy()
                    if df_y.empty:
                        continue
                    serie_y = (
                        df_y.set_index("fecha")[[col_t]]
                        .resample(freq_resample)
                        .mean()
                        .dropna()
                        .reset_index()
                    )
                    serie_y["dia_del_anio"] = serie_y["fecha"].dt.dayofyear
                    serie_y_roll = (
                        df_y.set_index("fecha")[[col_t]]
                        .resample("1D").mean().dropna()
                        .rolling(7, center=True).mean()
                        .dropna()
                        .reset_index()
                    )
                    serie_y_roll["dia_del_anio"] = serie_y_roll["fecha"].dt.dayofyear

                    color = PALETA_ANUAL[idx % len(PALETA_ANUAL)]

                    # Banda ±1σ solo para el primer año seleccionado (referencia)
                    if idx == 0 and mostrar_banda:
                        daily_full = (
                            df_y.set_index("fecha")[[col_t]]
                            .resample("1D").agg(["mean", "std"])
                            .dropna()
                            .reset_index()
                        )
                        daily_full.columns = ["fecha", "mean", "std"]
                        daily_full["dia_del_anio"] = daily_full["fecha"].dt.dayofyear
                        ref_std_x = daily_full["dia_del_anio"].tolist()
                        ref_std_y_upper = (daily_full["mean"] + daily_full["std"]).tolist()
                        ref_std_y_lower = (daily_full["mean"] - daily_full["std"]).tolist()

                        fig_sup.add_trace(go.Scatter(
                            x=ref_std_x + ref_std_x[::-1],
                            y=ref_std_y_upper + ref_std_y_lower[::-1],
                            fill="toself",
                            fillcolor=f"rgba{tuple(int(color.lstrip('#')[i:i+2], 16) for i in (0,2,4)) + (0.10,)}",
                            line=dict(color="rgba(0,0,0,0)"),
                            showlegend=False,
                            name=f"±1σ {anio}",
                            hoverinfo="skip",
                        ))

                    # Curva suavizada (rolling 7d)
                    fig_sup.add_trace(go.Scatter(
                        x=serie_y_roll["dia_del_anio"],
                        y=serie_y_roll[col_t],
                        mode="lines",
                        line=dict(color=color, width=2.5),
                        name=f"{anio} (suavizado 7d)",
                    ))

                    # Puntos originales (más transparentes)
                    fig_sup.add_trace(go.Scattergl(
                        x=serie_y["dia_del_anio"],
                        y=serie_y[col_t],
                        mode="markers",
                        marker=dict(size=3, opacity=0.25, color=color),
                        name=f"{anio} (datos)",
                        showlegend=False,
                    ))

                # Líneas verticales para estaciones secas
                fig_sup.add_vrect(x0=1, x1=91, fillcolor="rgba(255,220,0,0.06)", line_width=0, annotation_text="Seca (ene–mar)", annotation_position="top left")
                fig_sup.add_vrect(x0=335, x1=366, fillcolor="rgba(255,220,0,0.06)", line_width=0, annotation_text="Seca (dic)", annotation_position="top right")

                # Marcas de mes en el eje X
                dias_mes = [1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335]
                fig_sup.update_layout(
                    template="plotly_white",
                    height=460,
                    xaxis=dict(
                        title="Día del año",
                        tickmode="array",
                        tickvals=dias_mes,
                        ticktext=MESES,
                        showgrid=True,
                        gridcolor="#eee",
                    ),
                    yaxis_title=f"Temperatura ({unidad})",
                    hovermode="x unified",
                    legend=dict(orientation="h", y=-0.18),
                    margin=dict(l=45, r=20, t=20, b=80),
                )
                st.plotly_chart(fig_sup, use_container_width=True)

                st.caption(
                    "La curva suavizada usa una media móvil de 7 días. "
                    "Los puntos originales (diarios o semanales según la selección) se muestran más transparentes. "
                    "La banda sombreada corresponde a ±1 desviación estándar del primer año seleccionado."
                )

            # ── Sub-tab 2: Promedio mensual por año ─────────────────────────
            with sub_t2:
                st.markdown("**Promedio mensual de temperatura por año seleccionado**")

                monthly_data = []
                for anio in anios_sel:
                    df_y = df_all[df_all["anio"] == anio].copy()
                    if df_y.empty:
                        continue
                    mn = df_y.groupby("mes")[col_t].mean().reset_index()
                    mn["anio"] = anio
                    monthly_data.append(mn)

                if monthly_data:
                    df_monthly = pd.concat(monthly_data, ignore_index=True)

                    # Gráfico de líneas por año
                    fig_mn = go.Figure()
                    for idx, anio in enumerate(anios_sel):
                        sub = df_monthly[df_monthly["anio"] == anio].sort_values("mes")
                        if sub.empty:
                            continue
                        color = PALETA_ANUAL[idx % len(PALETA_ANUAL)]
                        fig_mn.add_trace(go.Scatter(
                            x=[MESES[m-1] for m in sub["mes"]],
                            y=sub[col_t],
                            mode="lines+markers",
                            line=dict(color=color, width=2.5),
                            marker=dict(size=8, color=color),
                            name=str(anio),
                        ))

                    fig_mn.update_layout(
                        template="plotly_white",
                        height=400,
                        yaxis_title=f"Temperatura media ({unidad})",
                        hovermode="x unified",
                        legend=dict(orientation="h", y=-0.18),
                        margin=dict(l=45, r=20, t=20, b=80),
                    )
                    st.plotly_chart(fig_mn, use_container_width=True)

                    # Heatmap de diferencias respecto al primer año
                    if len(anios_sel) >= 2:
                        st.markdown("#### Diferencia de temperatura mensual respecto al año de referencia")
                        anio_ref = anios_sel[0]
                        df_ref = df_monthly[df_monthly["anio"] == anio_ref].set_index("mes")[col_t]
                        pivot_diff = {}
                        for anio in anios_sel[1:]:
                            sub = df_monthly[df_monthly["anio"] == anio].set_index("mes")[col_t]
                            diff = sub - df_ref
                            pivot_diff[str(anio)] = diff

                        if pivot_diff:
                            df_diff = pd.DataFrame(pivot_diff).T
                            df_diff.columns = [MESES[m-1] for m in df_diff.columns]

                            fig_heat = go.Figure(data=go.Heatmap(
                                z=df_diff.values,
                                x=df_diff.columns.tolist(),
                                y=df_diff.index.tolist(),
                                colorscale="RdBu_r",
                                zmid=0,
                                colorbar=dict(title=f"Δ {unidad}"),
                                text=df_diff.round(2).values,
                                texttemplate="%{text}",
                                hoverongaps=False,
                            ))
                            fig_heat.update_layout(
                                template="plotly_white",
                                height=max(200, 60 * len(anios_sel)),
                                xaxis_title="Mes",
                                yaxis_title="Año",
                                margin=dict(l=60, r=20, t=20, b=40),
                            )
                            st.plotly_chart(fig_heat, use_container_width=True)
                            st.caption(f"Azul = más frío que {anio_ref} · Rojo = más cálido que {anio_ref}")

            # ── Sub-tab 3: Boxplots por mes y año ───────────────────────────
            with sub_t3:
                st.markdown("**Distribución mensual de temperatura por año — boxplot superpuesto**")

                mes_box_sel = st.selectbox(
                    "Mes a visualizar",
                    options=list(range(1, 13)),
                    format_func=lambda m: MESES[m-1],
                    index=0,
                )

                fig_box = go.Figure()
                for idx, anio in enumerate(anios_sel):
                    df_y = df_all[(df_all["anio"] == anio) & (df_all["mes"] == mes_box_sel)].copy()
                    if df_y.empty:
                        continue
                    color = PALETA_ANUAL[idx % len(PALETA_ANUAL)]
                    fig_box.add_trace(go.Box(
                        y=df_y[col_t].dropna(),
                        name=str(anio),
                        marker_color=color,
                        boxmean="sd",
                        line=dict(width=1.5),
                    ))

                fig_box.update_layout(
                    template="plotly_white",
                    height=420,
                    yaxis_title=f"Temperatura ({unidad})",
                    title=f"Distribución en {MESES[mes_box_sel-1]} — años seleccionados",
                    showlegend=True,
                    margin=dict(l=45, r=20, t=45, b=40),
                )
                st.plotly_chart(fig_box, use_container_width=True)

                # También mostrar todos los meses como panel de subplots
                st.markdown("#### Distribución completa por mes (todos los años seleccionados)")
                from plotly.subplots import make_subplots as _make_subplots
                fig_all_box = _make_subplots(rows=2, cols=6, subplot_titles=MESES)
                for m_idx, mes in enumerate(range(1, 13)):
                    row = 1 if m_idx < 6 else 2
                    col = (m_idx % 6) + 1
                    for idx, anio in enumerate(anios_sel):
                        df_y = df_all[(df_all["anio"] == anio) & (df_all["mes"] == mes)].copy()
                        if df_y.empty:
                            continue
                        color = PALETA_ANUAL[idx % len(PALETA_ANUAL)]
                        fig_all_box.add_trace(
                            go.Box(
                                y=df_y[col_t].dropna(),
                                name=str(anio),
                                marker_color=color,
                                showlegend=(m_idx == 0),
                                legendgroup=str(anio),
                            ),
                            row=row, col=col,
                        )
                fig_all_box.update_layout(
                    template="plotly_white",
                    height=540,
                    showlegend=True,
                    legend=dict(orientation="h", y=-0.08),
                    margin=dict(l=30, r=20, t=40, b=60),
                )
                fig_all_box.update_yaxes(title_text=unidad)
                st.plotly_chart(fig_all_box, use_container_width=True)

            # ── Sub-tab 4: Tabla de estadísticas ────────────────────────────
            with sub_t4:
                st.markdown("**Estadísticas anuales — comparativo**")

                rows_stats = []
                for anio in anios_sel:
                    df_y = df_all[df_all["anio"] == anio][col_t].dropna()
                    if df_y.empty:
                        continue
                    rows_stats.append({
                        "Año": anio,
                        f"Media ({unidad})": round(df_y.mean(), 2),
                        f"Mediana ({unidad})": round(df_y.median(), 2),
                        f"Mín ({unidad})": round(df_y.min(), 2),
                        f"Máx ({unidad})": round(df_y.max(), 2),
                        f"Desv. Est. ({unidad})": round(df_y.std(), 2),
                        "P10": round(df_y.quantile(0.10), 2),
                        "P90": round(df_y.quantile(0.90), 2),
                        "Registros": len(df_y),
                    })

                if rows_stats:
                    df_stats = pd.DataFrame(rows_stats)
                    st.dataframe(df_stats, use_container_width=True, hide_index=True)

                    # Gráfico de medias anuales con barras de error
                    st.markdown("#### Temperatura media anual con rango percentil P10–P90")
                    fig_bar = go.Figure()
                    for idx, row in enumerate(rows_stats):
                        color = PALETA_ANUAL[idx % len(PALETA_ANUAL)]
                        fig_bar.add_trace(go.Bar(
                            x=[str(row["Año"])],
                            y=[row[f"Media ({unidad})"]],
                            error_y=dict(
                                type="data",
                                symmetric=False,
                                array=[row["P90"] - row[f"Media ({unidad})"]],
                                arrayminus=[row[f"Media ({unidad})"] - row["P10"]],
                                visible=True,
                            ),
                            marker_color=color,
                            name=str(row["Año"]),
                            text=f"{row[f'Media ({unidad})']:.2f}",
                            textposition="outside",
                        ))
                    fig_bar.update_layout(
                        template="plotly_white",
                        height=400,
                        yaxis_title=f"Temperatura media ({unidad})",
                        showlegend=False,
                        bargap=0.35,
                        margin=dict(l=45, r=20, t=20, b=40),
                    )
                    st.plotly_chart(fig_bar, use_container_width=True)
                    st.caption("Las barras de error muestran el rango P10–P90 de cada año.")

tab_i += 1

# ============================================================
# TAB — EXPORTAR
# ============================================================
with tabs[tab_i]:
    st.subheader("Exportar resultados")
    c1, c2, c3 = st.columns(3)
    with c1:
        csv_h = df.to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ CSV horario filtrado", csv_h, safe_filename(f"temp_horaria_{temp_key}_{f_ini}_{f_fin}.csv"), "text/csv")
    with c2:
        daily = df.set_index("fecha")[[col_t]].resample("1D").agg(["mean", "min", "max"]).dropna().reset_index()
        daily.columns = ["fecha", "promedio", "minimo", "maximo"]
        csv_d = daily.to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ CSV diario", csv_d, safe_filename(f"temp_diaria_{temp_key}_{f_ini}_{f_fin}.csv"), "text/csv")
    with c3:
        monthly = df.set_index("fecha")[[col_t]].resample("1MS").agg(["mean", "min", "max", "std"]).dropna().reset_index()
        monthly.columns = ["fecha", "promedio", "minimo", "maximo", "desv_est"]
        csv_m = monthly.to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ CSV mensual", csv_m, safe_filename(f"temp_mensual_{temp_key}_{f_ini}_{f_fin}.csv"), "text/csv")

    st.markdown("---")
    st.dataframe(df.head(500), use_container_width=True, height=300)

st.markdown("---")
st.markdown(
    f"""
    <div style="text-align:center; color:#7f8c8d; font-size:0.90rem;">
        Dashboard Integrado de Temperatura, Viento y Surgencias · Canal de Panamá · HIMH · ACP<br>
        <b>{AUTHOR_FOOTER}</b><br>
        Archivos fuente integrados automáticamente dentro del proyecto
    </div>
    """,
    unsafe_allow_html=True,
)
