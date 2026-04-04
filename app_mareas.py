"""
🌊 Dashboard Avanzado de Mareas — Canal de Panamá
===================================================
Incluye planos de referencia de mareas (HAT, MHHW, MHW, MSL, MLW, MLLW, LAT),
predicción de mareas astronómicas con constituyentes armónicas,
y análisis avanzado.

v2.0 — Corregido: auto-detección de unidades (m/ft), predicción astronómica,
       plano de referencia Ciclo Nodal con offsets.

INSTALACIÓN:
    pip install streamlit pandas numpy plotly scipy openpyxl

EJECUCIÓN:
    py -m streamlit run app_mareas.py
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy import signal, stats as sp_stats
from scipy.fft import fft, fftfreq
import glob, os, calendar, io
from datetime import datetime, timedelta

# ══════════════════════════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════════════════════════
st.set_page_config(page_title="🌊 Mareas — Canal de Panamá", page_icon="🌊", layout="wide")

COLORES = {
    "LMB": {"linea": "#2980b9", "fill": "rgba(41,128,185,0.08)",
            "pico": "#e74c3c", "valle": "#27ae60"},
    "DHT": {"linea": "#8e44ad", "fill": "rgba(142,68,173,0.08)",
            "pico": "#e67e22", "valle": "#16a085"},
    "AMA": {"linea": "#e67e22", "fill": "rgba(230,126,34,0.08)",
            "pico": "#c0392b", "valle": "#1abc9c"},
}
NOMBRES = {"LMB": "Limon Bay (Atlántico)", "DHT": "Diablo Heights (Pacífico)",
           "AMA": "Amador (Pacífico)"}
MESES = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"]

# Factor de conversión
FT_TO_M = 0.3048
M_TO_FT = 3.28084
_dir = os.path.dirname(__file__) or "."

# ══════════════════════════════════════════════════════════════
# PLANOS DE REFERENCIA — CICLO NODAL (Mar Caribe / Limon Bay)
# Valores en pies desde la imagen de referencia NOAA CO-OPS
# Tidal Epoch 1992-2010
# ══════════════════════════════════════════════════════════════
DATUMS_CICLO_NODAL = {
    "MSL": {
        "nombre": "Mean Sea Level",
        "desc": "Nivel medio del mar (Ciclo Nodal — Tidal Epoch 1992-2010)",
        "offset_ft_desde_cero": 2.010 + 0.710,   # Cero→LLW + LLW→MSL  = 2.720'
        "color": "#1a5276"
    },
    "MLW": {
        "nombre": "Mean Low Water",
        "desc": "Referencia Tabla de mareas y Carta Náutica",
        "offset_ft_desde_cero": 2.000 + 0.710,   # ~2.710'
        "color": "#2563EB"
    },
    "PLD": {
        "nombre": "Precise Level Datum",
        "desc": "Nivel de referencia preciso del Canal de Panamá",
        "offset_ft_desde_cero": 2.000 + 0.710 - 0.010,  # MLW - 0.010 = 2.700'
        "color": "#7f8c8d"
    },
    "REF_RP": {
        "nombre": "Referencia Oficial Rep. Panamá",
        "desc": "Nivel medio del mar Caribe en Cristóbal (1959)",
        "offset_ft_desde_cero": 1.290 + 0.710,   # 2.000'
        "color": "#95a5a6"
    },
    "LLW": {
        "nombre": "Lowest Low Water",
        "desc": "Bajamar histórica más baja",
        "offset_ft_desde_cero": 0.710,
        "color": "#e74c3c"
    },
    "CERO_REGLA": {
        "nombre": "Cero Regla de Marea",
        "desc": "Referencia de los mareógrafos (entrada norte Canal de Panamá)",
        "offset_ft_desde_cero": 0.0,
        "color": "#0b5345"
    },
}
STATION_NODAL_DATUMS = {"LMB": DATUMS_CICLO_NODAL}


# ══════════════════════════════════════════════════════════════
# FUNCIONES — CARGA Y DETECCIÓN DE UNIDADES
# ══════════════════════════════════════════════════════════════

def detectar_unidad_csv(fuente):
    """
    Lee la fila de encabezado del CSV para detectar si los datos están en
    metros o pies. Busca 'Value (m)' o 'Value (ft)' en la fila 5 (skiprows=4).
    Retorna 'm', 'ft' o 'desconocido'.
    """
    try:
        if hasattr(fuente, 'read'):
            pos = fuente.tell() if hasattr(fuente, 'tell') else 0
            fuente.seek(0)
            lineas = []
            for i, line in enumerate(fuente):
                if isinstance(line, bytes):
                    line = line.decode('utf-8', errors='replace')
                lineas.append(line.strip())
                if i >= 5:
                    break
            fuente.seek(pos)
        else:
            with open(fuente, 'r', encoding='utf-8', errors='replace') as f:
                lineas = [f.readline().strip() for _ in range(6)]

        for linea in lineas:
            lower = linea.lower().replace('\r', '')
            if 'value (m)' in lower or 'value(m)' in lower:
                return 'm'
            if 'value (ft)' in lower or 'value(ft)' in lower:
                return 'ft'

        # Heurística: si no se encontró en header, intentar con los datos
        return 'desconocido'
    except Exception:
        return 'desconocido'


def heuristica_unidad(valores):
    """
    Si no se pudo detectar la unidad por el encabezado, usa heurística:
    - Limon Bay en metros: rango típico 0.3 - 1.2 m
    - Limon Bay en pies:  rango típico 1.0 - 4.0 ft
    - Pacífico en metros: rango típico -2.5 a +3.0 m
    - Pacífico en pies:   rango típico -8 a +10 ft
    """
    med = valores.median()
    rng = valores.max() - valores.min()

    if med < 2.0 and rng < 2.5:
        return 'm'    # Muy probablemente metros (Atlántico)
    elif med > 1.5 and rng < 5.0:
        return 'ft'   # Probablemente pies (Atlántico)
    elif rng > 5.0:
        return 'ft'   # Probablemente pies (Pacífico)
    else:
        return 'm'    # Por defecto metros


@st.cache_data(show_spinner="Cargando datos...")
def cargar_csv(fuente, unidad_forzada=None):
    """
    Carga un CSV de exportación ACP, detecta automáticamente la unidad
    de medida y crea ambas columnas (nivel_ft y nivel_m) correctamente.

    Parámetros:
    -----------
    fuente : str o file-like
        Ruta al archivo o archivo subido.
    unidad_forzada : str o None
        'm', 'ft' o None (auto-detectar).

    Retorna:
    --------
    df : DataFrame con columnas [fecha, nivel_ft, nivel_m, unidad_original]
    unidad_detectada : str ('m' o 'ft')
    """
    # Detectar unidad
    if unidad_forzada and unidad_forzada != 'auto':
        unidad = unidad_forzada
    else:
        unidad = detectar_unidad_csv(fuente)

    # Leer datos
    df = pd.read_csv(fuente, skiprows=4, names=["fecha", "valor_raw"])
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    df["valor_raw"] = pd.to_numeric(df["valor_raw"], errors="coerce")
    df = df.dropna(subset=["fecha", "valor_raw"]).sort_values("fecha").reset_index(drop=True)

    # Si unidad sigue desconocida, usar heurística
    if unidad == 'desconocido':
        unidad = heuristica_unidad(df["valor_raw"])

    # Crear ambas columnas correctamente
    if unidad == 'ft':
        df["nivel_ft"] = df["valor_raw"].round(4)
        df["nivel_m"]  = (df["valor_raw"] * FT_TO_M).round(4)
    else:  # metros
        df["nivel_m"]  = df["valor_raw"].round(4)
        df["nivel_ft"] = (df["valor_raw"] * M_TO_FT).round(4)

    df["unidad_original"] = unidad
    df.drop(columns=["valor_raw"], inplace=True)

    return df, unidad


def detectar_estacion(nombre):
    n = nombre.upper()
    if "LMB" in n: return "LMB"
    if "DHT" in n: return "DHT"
    if "AMA" in n: return "AMA"
    return "Desconocida"


def resolver_archivos_locales(patrones):
    archivos = []
    for patron in patrones:
        archivos.extend(glob.glob(os.path.join(_dir, patron)))
    return sorted(archivos)


def obtener_firma_fuente(fuente):
    if fuente is None:
        return "none"
    if hasattr(fuente, "name"):
        size = getattr(fuente, "size", None)
        if size is None and hasattr(fuente, "getbuffer"):
            try:
                size = fuente.getbuffer().nbytes
            except Exception:
                size = None
        return f"{fuente.name}:{size}"
    return os.path.abspath(str(fuente))


def obtener_offset_datum(estacion, datum):
    offsets_m = {
        "LMB": {
            "MSL (nivel medio)": 0.0,
            "MLW (carta náutica)": -(0.390 * FT_TO_M),
        }
    }
    return offsets_m.get(estacion, {}).get(datum)


def normalizar_df_pred(df_pred, station, source, unidad_base="m"):
    pred = df_pred.copy()
    pred["fecha"] = pd.to_datetime(pred["fecha"], errors="coerce")

    if "nivel_pred" in pred.columns:
        valores = pd.to_numeric(pred["nivel_pred"], errors="coerce")
    elif "nivel_pred_m" in pred.columns:
        valores = pd.to_numeric(pred["nivel_pred_m"], errors="coerce")
        unidad_base = "m"
    elif "nivel_pred_ft" in pred.columns:
        valores = pd.to_numeric(pred["nivel_pred_ft"], errors="coerce")
        unidad_base = "ft"
    else:
        raise ValueError("La predicción debe incluir 'nivel_pred', 'nivel_pred_m' o 'nivel_pred_ft'.")

    if unidad_base == "ft":
        pred["nivel_pred_ft"] = valores
        pred["nivel_pred_m"] = valores * FT_TO_M
    else:
        pred["nivel_pred_m"] = valores
        pred["nivel_pred_ft"] = valores * M_TO_FT

    pred["unidad_base"] = unidad_base
    pred["source"] = source
    pred["station"] = station

    cols = ["fecha", "nivel_pred_m", "nivel_pred_ft", "unidad_base", "source", "station"]
    return pred[cols].dropna(subset=["fecha", "nivel_pred_m", "nivel_pred_ft"]).reset_index(drop=True)


def limpiar_prediccion_cache(station, source, pred_unit, signature):
    contexto_actual = (
        st.session_state.get("pred_station"),
        st.session_state.get("pred_source"),
        st.session_state.get("pred_unit"),
        st.session_state.get("pred_signature"),
    )
    contexto_nuevo = (station, source, pred_unit, signature)

    if "df_pred" in st.session_state and contexto_actual != contexto_nuevo:
        for key in ["df_pred", "pred_station", "pred_source", "pred_unit", "pred_signature"]:
            st.session_state.pop(key, None)
        return True
    return False


def encontrar_picos(df, col, prom, dist):
    v = df[col].values
    ix, _ = signal.find_peaks(v, prominence=prom, distance=dist)
    im, _ = signal.find_peaks(-v, prominence=prom, distance=dist)
    p = df.iloc[ix][["fecha", col]].copy(); p["tipo"] = "Pleamar"
    b = df.iloc[im][["fecha", col]].copy(); b["tipo"] = "Bajamar"
    return p, b


def resam(df, col, limite=12000, freq="1h"):
    if len(df) <= limite: return df, False
    r = df.set_index("fecha")[[col]].resample(freq).mean().dropna().reset_index()
    return r, True


@st.cache_data
def calcular_datums(df, col, _plea, _baja):
    plea = _plea.copy()
    baja = _baja.copy()
    plea["date"] = plea["fecha"].dt.date
    baja["date"] = baja["fecha"].dt.date
    hhw_daily = plea.groupby("date")[col].max()
    lhw_daily = plea.groupby("date")[col].min()
    hlw_daily = baja.groupby("date")[col].max()
    llw_daily = baja.groupby("date")[col].min()

    datums = {
        "HAT":  {"valor": df[col].max(),
                 "nombre": "Highest Astronomical Tide",
                 "desc": "Nivel más alto observado",
                 "color": "#922b21"},
        "MHHW": {"valor": hhw_daily.mean() if len(hhw_daily) > 0 else np.nan,
                 "nombre": "Mean Higher High Water",
                 "desc": "Promedio de las pleamares más altas diarias",
                 "color": "#e74c3c"},
        "MHW":  {"valor": plea[col].mean() if len(plea) > 0 else np.nan,
                 "nombre": "Mean High Water",
                 "desc": "Promedio de todas las pleamares",
                 "color": "#e67e22"},
        "DTL":  {"valor": (plea[col].mean() + baja[col].mean()) / 2 if len(plea) > 0 and len(baja) > 0 else np.nan,
                 "nombre": "Diurnal Tide Level",
                 "desc": "Promedio entre MHW y MLW",
                 "color": "#f39c12"},
        "MSL":  {"valor": df[col].mean(),
                 "nombre": "Mean Sea Level",
                 "desc": "Nivel medio del mar (promedio de todos los datos)",
                 "color": "#2ecc71"},
        "MTL":  {"valor": (plea[col].mean() + baja[col].mean()) / 2 if len(plea) > 0 and len(baja) > 0 else np.nan,
                 "nombre": "Mean Tide Level",
                 "desc": "Promedio aritmético de MHW y MLW",
                 "color": "#1abc9c"},
        "MLW":  {"valor": baja[col].mean() if len(baja) > 0 else np.nan,
                 "nombre": "Mean Low Water",
                 "desc": "Promedio de todas las bajamares",
                 "color": "#2980b9"},
        "MLLW": {"valor": llw_daily.mean() if len(llw_daily) > 0 else np.nan,
                 "nombre": "Mean Lower Low Water",
                 "desc": "Promedio de las bajamares más bajas diarias",
                 "color": "#1a5276"},
        "LAT":  {"valor": df[col].min(),
                 "nombre": "Lowest Astronomical Tide",
                 "desc": "Nivel más bajo observado",
                 "color": "#0b5345"},
    }

    MHW = datums["MHW"]["valor"]
    MLW = datums["MLW"]["valor"]
    MHHW = datums["MHHW"]["valor"]
    MLLW = datums["MLLW"]["valor"]

    rangos = {}
    if not np.isnan(MHW) and not np.isnan(MLW):
        rangos["MN (Mean Range)"] = MHW - MLW
    if not np.isnan(MHHW) and not np.isnan(MLLW):
        rangos["GT (Great Diurnal Range)"] = MHHW - MLLW
        rangos["DHQ (Diurnal HW Ineq.)"] = MHHW - MHW
        rangos["DLQ (Diurnal LW Ineq.)"] = MLW - MLLW

    return datums, rangos


# ══════════════════════════════════════════════════════════════
# FUNCIONES — PREDICCIÓN ASTRONÓMICA (V₀ + correcciones nodales)
# ══════════════════════════════════════════════════════════════

@st.cache_data
def cargar_constituyentes(fuente):
    """Carga constituyentes armónicas desde Excel o CSV."""
    if hasattr(fuente, 'name') and fuente.name.endswith('.xlsx'):
        df = pd.read_excel(fuente)
    elif isinstance(fuente, str) and fuente.endswith('.xlsx'):
        df = pd.read_excel(fuente)
    else:
        df = pd.read_csv(fuente)
    col_map = {}
    for c in df.columns:
        cl = c.strip().lower()
        if 'name' in cl or 'nombre' in cl: col_map[c] = 'Name'
        elif 'amplitude' in cl or 'amplitud' in cl: col_map[c] = 'Amplitude'
        elif 'phase' in cl or 'fase' in cl: col_map[c] = 'Phase'
        elif 'speed' in cl or 'velocidad' in cl: col_map[c] = 'Speed'
        elif 'description' in cl or 'desc' in cl: col_map[c] = 'Description'
    df = df.rename(columns=col_map)
    for r in ['Name', 'Amplitude', 'Phase', 'Speed']:
        if r not in df.columns:
            st.error(f"Columna '{r}' no encontrada en constituyentes.")
            return None
    return df


@st.cache_data
def cargar_prediccion_utide(fuente):
    """Carga predicción pre-calculada con UTide (CSV del notebook)."""
    df = pd.read_csv(fuente, parse_dates=[0])
    df.columns = df.columns.str.strip().str.lower()
    rn = {}
    for c in df.columns:
        if any(k in c for k in ['time','fecha','date']): rn[c] = 'fecha'
        elif any(k in c for k in ['tide','nivel','level','pred']): rn[c] = 'nivel_pred'
    df = df.rename(columns=rn)
    if 'fecha' not in df.columns: df['fecha'] = pd.to_datetime(df.iloc[:, 0])
    if 'nivel_pred' not in df.columns: df['nivel_pred'] = pd.to_numeric(df.iloc[:, 1], errors='coerce')
    return df[['fecha', 'nivel_pred']].dropna()


def _astro_args(dt):
    """Argumentos astronómicos s, h, p, N, pp en grados — Schureman (1958)."""
    if hasattr(dt, 'timestamp'):
        jd = dt.timestamp() / 86400.0 + 2440587.5
    else:
        jd = (np.datetime64(dt) - np.datetime64('1970-01-01T00:00:00')
              ) / np.timedelta64(1, 's') / 86400.0 + 2440587.5
    T = (jd - 2451545.0) / 36525.0
    s = (218.3165 + 481267.8813 * T) % 360
    h = (280.4661 + 36000.7698 * T) % 360
    p = (83.3535 + 4069.0137 * T) % 360
    N = (125.0445 - 1934.1363 * T) % 360
    pp = (282.9404 + 1.7195 * T) % 360
    return s, h, p, N, pp

_V0 = {
    'M2': lambda s,h,p,N,pp: 2*h-2*s, 'S2': lambda s,h,p,N,pp: 0.0,
    'N2': lambda s,h,p,N,pp: 2*h-3*s+p, 'K1': lambda s,h,p,N,pp: h+90,
    'O1': lambda s,h,p,N,pp: h-2*s-90, 'P1': lambda s,h,p,N,pp: -h+270,
    'K2': lambda s,h,p,N,pp: 2*h, 'Q1': lambda s,h,p,N,pp: h-3*s+p-90,
    'M4': lambda s,h,p,N,pp: 4*h-4*s, 'MS4': lambda s,h,p,N,pp: 2*h-2*s,
    'MF': lambda s,h,p,N,pp: 2*s, 'MM': lambda s,h,p,N,pp: s-p,
    'SA': lambda s,h,p,N,pp: h, 'SSA': lambda s,h,p,N,pp: 2*h,
    'J1': lambda s,h,p,N,pp: h+s-p+90, 'L2': lambda s,h,p,N,pp: 2*h-s+p,
    'NU2': lambda s,h,p,N,pp: 2*h-3*s+4*p-N, 'S1': lambda s,h,p,N,pp: h,
    'OO1': lambda s,h,p,N,pp: h+2*s+90, '2N2': lambda s,h,p,N,pp: 2*h-4*s+2*p,
    'M3': lambda s,h,p,N,pp: 3*h-3*s, 'RHO1': lambda s,h,p,N,pp: h-3*s+3*p-90,
    'NO1': lambda s,h,p,N,pp: h-3*s+p+90, 'MK3': lambda s,h,p,N,pp: 3*h-2*s,
}

def _nodal(N_deg):
    Nr = np.radians(N_deg)
    return {
        'M2': (1.0-0.0373*np.cos(Nr), -2.14*np.sin(Nr)),
        'S2': (1.0, 0.0), 'N2': (1.0-0.0373*np.cos(Nr), -2.14*np.sin(Nr)),
        'K1': (1.006+0.115*np.cos(Nr), -8.86*np.sin(Nr)),
        'O1': (1.009+0.187*np.cos(Nr), 10.80*np.sin(Nr)),
        'P1': (1.0, 0.0), 'K2': (1.024+0.286*np.cos(Nr), -17.74*np.sin(Nr)),
        'Q1': (1.009+0.187*np.cos(Nr), 10.80*np.sin(Nr)),
        'MF': (1.043+0.414*np.cos(Nr), -23.74*np.sin(Nr)),
        'MM': (1.0-0.130*np.cos(Nr), 0.0), 'SA': (1.0, 0.0),
    }


def predecir_marea(constituyentes, fecha_inicio, fecha_fin,
                   intervalo_min=15, z0=0.0, datum_offset_m=0.0):
    """
    Predicción astronómica: h(t) = Z₀ + offset + Σ fᵢ·Aᵢ·cos(V₀ᵢ + ωᵢ·Δt + uᵢ − gᵢ)
    Incluye argumentos astronómicos V₀ y correcciones nodales (Schureman 1958).
    Para máxima precisión, usar predicción UTide (cargar_prediccion_utide).
    """
    fechas = pd.date_range(start=fecha_inicio, end=fecha_fin, freq=f'{intervalo_min}min')
    t_ref = fechas[0].to_pydatetime()
    s, h, p, N, pp = _astro_args(t_ref)
    nodal = _nodal(N)
    t_hours = (fechas - fechas[0]).total_seconds().values / 3600.0
    nivel = np.full(len(fechas), z0 + datum_offset_m, dtype=np.float64)
    for _, row in constituyentes.iterrows():
        name, A, omega, g = row['Name'], row['Amplitude'], row['Speed'], row['Phase']
        v0f = _V0.get(name)
        V0 = v0f(s, h, p, N, pp) % 360 if v0f else 0.0
        f_n, u_n = nodal.get(name, (1.0, 0.0))
        nivel += f_n * A * np.cos(np.radians(V0 + omega * t_hours + u_n - g))
    return pd.DataFrame({'fecha': fechas, 'nivel_pred': nivel})


def renderizar_prediccion(df_pred, df_all, est_activa, color, unidad_display,
                          source_label, pred_inicio=None, pred_fin=None):
    if df_pred.empty:
        st.warning("La predicción no contiene datos.")
        return

    u_pl = "ft" if "Pies" in unidad_display else "m"
    col_pred_display = "nivel_pred_ft" if u_pl == "ft" else "nivel_pred_m"

    st.caption(f"Fuente activa: {source_label}")

    fig_pred = go.Figure()
    fig_pred.add_trace(go.Scattergl(
        x=df_pred["fecha"], y=df_pred[col_pred_display],
        mode="lines", name="Predicción astronómica",
        line=dict(color="#e74c3c", width=1.5),
        fill="tozeroy", fillcolor="rgba(231,76,60,0.08)",
    ))

    obs_mask = (df_all["fecha"] >= df_pred["fecha"].min()) & \
               (df_all["fecha"] <= df_pred["fecha"].max())
    df_obs_overlap = df_all[obs_mask]
    if len(df_obs_overlap) > 0:
        col_obs = "nivel_ft" if u_pl == "ft" else "nivel_m"
        dp_obs, _ = resam(df_obs_overlap, col_obs)
        fig_pred.add_trace(go.Scattergl(
            x=dp_obs["fecha"], y=dp_obs[col_obs],
            mode="lines", name="Observado",
            line=dict(color=color["linea"], width=1.2),
            opacity=0.7,
        ))

    fig_pred.update_layout(
        yaxis_title=f"Nivel ({u_pl})",
        xaxis_title="Fecha",
        template="plotly_white", height=500,
        hovermode="x unified",
        margin=dict(l=50, r=20, t=30, b=50),
        legend=dict(x=0, y=1),
    )
    st.plotly_chart(fig_pred, use_container_width=True)

    prom_pred = 0.01 if est_activa == "LMB" else 0.1
    if u_pl == "ft":
        prom_pred *= M_TO_FT

    try:
        plea_pred, baja_pred = encontrar_picos(df_pred, col_pred_display, prom_pred, 20)

        ev_col1, ev_col2 = st.columns(2)
        with ev_col1:
            st.subheader("🔴 Pleamares predichas")
            if len(plea_pred) > 0:
                plea_show = plea_pred.copy()
                plea_show.columns = ["Fecha/Hora", f"Nivel ({u_pl})", "Tipo"]
                st.dataframe(plea_show.head(100), use_container_width=True, hide_index=True)
                st.caption(f"Total: {len(plea_pred)} pleamares")
            else:
                st.info("No se detectaron pleamares con la prominencia actual.")
        with ev_col2:
            st.subheader("🟢 Bajamares predichas")
            if len(baja_pred) > 0:
                baja_show = baja_pred.copy()
                baja_show.columns = ["Fecha/Hora", f"Nivel ({u_pl})", "Tipo"]
                st.dataframe(baja_show.head(100), use_container_width=True, hide_index=True)
                st.caption(f"Total: {len(baja_pred)} bajamares")
            else:
                st.info("No se detectaron bajamares con la prominencia actual.")
    except Exception:
        st.info("Ajusta la prominencia si no se detectan bien los picos.")

    if len(df_obs_overlap) > 100:
        st.markdown("---")
        st.subheader("📉 Residual (Observado − Predicho)")

        df_merge = pd.merge_asof(
            df_obs_overlap.sort_values("fecha")[["fecha", "nivel_m"]],
            df_pred.sort_values("fecha")[["fecha", "nivel_pred_m"]],
            on="fecha", direction="nearest", tolerance=pd.Timedelta("30min")
        ).dropna()

        if len(df_merge) > 0:
            df_merge["residual"] = df_merge["nivel_m"] - df_merge["nivel_pred_m"]
            if u_pl == "ft":
                df_merge["residual_display"] = df_merge["residual"] * M_TO_FT
            else:
                df_merge["residual_display"] = df_merge["residual"]

            fig_res = go.Figure()
            fig_res.add_trace(go.Scattergl(
                x=df_merge["fecha"], y=df_merge["residual_display"],
                mode="lines", name="Residual",
                line=dict(color="#e67e22", width=1),
            ))
            fig_res.add_hline(y=0, line_dash="dash", line_color="gray")
            fig_res.update_layout(
                yaxis_title=f"Residual ({u_pl})",
                template="plotly_white", height=300,
                margin=dict(l=50, r=20, t=20, b=50),
            )
            st.plotly_chart(fig_res, use_container_width=True)

            rc1, rc2, rc3, rc4 = st.columns(4)
            rc1.metric("RMSE", f"{np.sqrt((df_merge['residual']**2).mean()):.4f} m")
            rc2.metric("MAE", f"{df_merge['residual'].abs().mean():.4f} m")
            rc3.metric("Bias", f"{df_merge['residual'].mean():+.4f} m")
            rc4.metric("Max |error|", f"{df_merge['residual'].abs().max():.4f} m")

    st.markdown("---")
    csv_pred = df_pred[["fecha", "nivel_pred_m", "nivel_pred_ft"]].copy()
    csv_pred.columns = ["Fecha", "Nivel_pred_m", "Nivel_pred_ft"]
    nombre_ini = pred_inicio or df_pred["fecha"].min().date()
    nombre_fin = pred_fin or df_pred["fecha"].max().date()
    st.download_button(
        "⬇️ Descargar predicción (CSV)",
        csv_pred.to_csv(index=False).encode("utf-8"),
        f"prediccion_{est_activa}_{nombre_ini}_{nombre_fin}.csv",
        "text/csv"
    )


# Datos de puentes del Canal de Panamá
PUENTES = {
    "Puente de las Américas": {"clearance_m": 61.3, "datum_ref": "MHW", "lado": "Pacífico"},
    "Puente Atlántico": {"clearance_m": 75.0, "datum_ref": "MSL", "lado": "Atlántico"},
    "Puente Centenario": {"clearance_m": 80.0, "datum_ref": "MSL", "lado": "Pacífico"},
}
TIPOS_BUQUES = {
    "Neopanamax (contenedores)": 57.91, "Panamax clásico": 54.0,
    "Post-Panamax": 62.0, "Granelero Capesize": 45.0,
    "Crucero grande": 55.0, "LNG Carrier": 48.0, "Personalizado": 0.0,
}

PUENTE_ESTACION_PREF = {
    "Puente Atlántico": ["LMB"],
    "Puente de las Américas": ["AMA", "DHT"],
    "Puente Centenario": ["AMA", "DHT"],
}

# ══════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════
_logo_himh = os.path.join(_dir, "LOGO_HIMH.jpg")
_logo_eidemar = os.path.join(_dir, "LOGO_EIDEMAR.png")

_sb_cols = st.sidebar.columns(2)
if os.path.exists(_logo_himh):
    _sb_cols[0].image(_logo_himh, width=100)
if os.path.exists(_logo_eidemar):
    _sb_cols[1].image(_logo_eidemar, width=100)
st.sidebar.markdown("## 🌊 Mareas — Canal de Panamá")
st.sidebar.caption("HIMH · EIDEMAR")
st.sidebar.markdown("---")

archivos_locales = resolver_archivos_locales(["BulkExport-*.csv"])

st.sidebar.markdown("### 📂 Datos de Marea")
metodo = st.sidebar.radio("Fuente", ["Subir archivo(s)", "Archivos locales"], horizontal=True)

# ── Opción de unidades de entrada ──
st.sidebar.markdown("### 📐 Unidades de Entrada")
st.sidebar.caption("Define cómo interpretar los datos crudos de cada archivo.")
unidad_entrada_opcion = st.sidebar.radio(
    "Detección de unidades",
    ["🔍 Auto-detectar", "📏 Forzar Metros (m)", "📏 Forzar Pies (ft)"],
    index=0,
    help="Auto-detectar lee la cabecera del CSV ('Value (m)' o 'Value (ft)'). "
         "Si no la encuentra, usa heurística basada en los rangos de valores."
)

if "Auto" in unidad_entrada_opcion:
    unidad_forzada = 'auto'
elif "Metros" in unidad_entrada_opcion:
    unidad_forzada = 'm'
else:
    unidad_forzada = 'ft'

st.sidebar.markdown("---")

datasets = {}
unidades_detectadas = {}

if metodo == "Archivos locales":
    if archivos_locales:
        st.sidebar.markdown("**Selecciona estaciones:**")
        for arc in archivos_locales:
            est = detectar_estacion(arc)
            nombre_disp = NOMBRES.get(est, est)
            if st.sidebar.checkbox(nombre_disp, value=True, key=f"chk_{arc}"):
                try:
                    df_cargado, u_det = cargar_csv(arc, unidad_forzada)
                    datasets[est] = df_cargado
                    unidades_detectadas[est] = u_det
                    emoji_u = "📏" if u_det == 'm' else "📐"
                    st.sidebar.success(f"✅ {est}: {len(df_cargado):,} reg. · {emoji_u} Origen: {u_det}")
                except Exception as ex:
                    st.sidebar.error(str(ex))
    else:
        st.sidebar.warning("No hay archivos `BulkExport-*.csv` en la carpeta.")
else:
    archivos = st.sidebar.file_uploader("CSV de exportación ACP", type=["csv"],
                                         accept_multiple_files=True)
    for a in archivos:
        e = detectar_estacion(a.name)
        try:
            df_cargado, u_det = cargar_csv(a, unidad_forzada)
            datasets[e] = df_cargado
            unidades_detectadas[e] = u_det
            emoji_u = "📏" if u_det == 'm' else "📐"
            st.sidebar.success(f"✅ {e}: {len(df_cargado):,} reg. · {emoji_u} Origen: {u_det}")
        except Exception as ex:
            st.sidebar.error(str(ex))

# ── Constituyentes armónicas ──
st.sidebar.markdown("---")
st.sidebar.markdown("### 🔮 Constituyentes Armónicas")
const_local = os.path.join(_dir, "Constituents_limon_2025.xlsx")
const_source = None

const_metodo = st.sidebar.radio(
    "Fuente constituyentes",
    ["Subir archivo", "Archivo local"],
    horizontal=True,
    key="const_metodo"
)

if const_metodo == "Archivo local":
    if os.path.exists(const_local):
        const_source = const_local
        st.sidebar.success("✅ Constituyentes cargadas (local)")
    else:
        xlsx_files = resolver_archivos_locales(["Constituents*.xlsx", "constituents*.xlsx"])
        if xlsx_files:
            const_source = xlsx_files[0]
            st.sidebar.success(f"✅ {os.path.basename(xlsx_files[0])}")
        else:
            st.sidebar.info("No se encontró archivo de constituyentes local.")
else:
    const_file = st.sidebar.file_uploader(
        "Excel/CSV de constituyentes", type=["xlsx", "csv"],
        key="const_upload"
    )
    if const_file:
        const_source = const_file
        st.sidebar.success(f"✅ Constituyentes cargadas")


if not datasets:
    st.markdown(
        "<h1 style='color:#1a5276; text-align:center; margin-top:80px;'>"
        "🌊 Mareas — Canal de Panamá</h1>"
        "<p style='text-align:center; color:#5d6d7e; font-size:1.2rem;'>"
        "Sube tu archivo <b>BulkExport-LMB/DHT-*.csv</b> en la barra lateral.<br>"
        "<small>v2.0 — Auto-detección de unidades · Predicción astronómica · Ciclo Nodal</small></p>",
        unsafe_allow_html=True,
    )
    st.stop()

estaciones = list(datasets.keys())
est_activa = st.sidebar.selectbox("Estación", estaciones,
    format_func=lambda x: NOMBRES.get(x, x)) if len(estaciones) > 1 else estaciones[0]

df_all = datasets[est_activa]
color = COLORES.get(est_activa, COLORES["LMB"])
u_original = unidades_detectadas.get(est_activa, 'ft')

st.sidebar.markdown("---")
st.sidebar.markdown("### ⚙️ Opciones de Visualización")
unidad = st.sidebar.radio("Unidad de visualización", ["Pies (ft)", "Metros (m)"], horizontal=True)
col = "nivel_ft" if "Pies" in unidad else "nivel_m"
u = "ft" if "Pies" in unidad else "m"

fmin = df_all["fecha"].min().date()
fmax = df_all["fecha"].max().date()
rango = st.sidebar.date_input("Rango", value=(max(fmin, fmax - pd.Timedelta(days=90)), fmax),
                               min_value=fmin, max_value=fmax)
f_ini, f_fin = (rango if isinstance(rango, (list,tuple)) and len(rango)==2 else (fmin, fmax))

mask = (df_all["fecha"].dt.date >= f_ini) & (df_all["fecha"].dt.date <= f_fin)
df = df_all[mask].copy()
if df.empty:
    st.warning("Sin datos en rango."); st.stop()

st.sidebar.markdown("---")
st.sidebar.markdown(f"**Total:** {len(df_all):,} · **Filtro:** {len(df):,}")
st.sidebar.markdown(f"**Período:** {fmin} → {fmax}")
st.sidebar.markdown(f"**Unidad original del archivo:** `{u_original}`")

prom_d = 0.15 if est_activa == "LMB" else 2.0
if "Metros" in unidad: prom_d *= 0.3048
plea_all, baja_all = encontrar_picos(df, col, prom_d, 20)


# ══════════════════════════════════════════════════════════════
# HEADER + KPIs
# ══════════════════════════════════════════════════════════════
import base64 as _b64

def _img_b64(path, h=55):
    if os.path.exists(path):
        with open(path, "rb") as _f:
            ext = "jpeg" if path.endswith(".jpg") else "png"
            return f'<img src="data:image/{ext};base64,{_b64.b64encode(_f.read()).decode()}" style="height:{h}px;margin-right:10px;vertical-align:middle;">'
    return ""

_logos = _img_b64(_logo_himh, 55) + _img_b64(_logo_eidemar, 55)

# Badge de unidad original
badge_color = "#27ae60" if u_original == 'm' else "#2980b9"
badge_txt = "metros" if u_original == 'm' else "pies"

st.markdown(
    f"""
    <div style="display:flex; align-items:center; justify-content:space-between; gap:16px; margin-bottom:10px;">
        <div style="display:flex; align-items:center; gap:10px; min-width:180px;">{_logos}</div>
        <div style="flex:1; text-align:center;">
            <div style="font-size:2.0rem; font-weight:700; color:#1a5276; line-height:1.1;">🌊 Mareas — Canal de Panamá</div>
            <div style="font-size:1.05rem; color:#5d6d7e; margin-top:4px;">
                <b>{NOMBRES.get(est_activa, est_activa)}</b> · HIMH · EIDEMAR · {f_ini} → {f_fin}
            </div>
            <div style="font-size:0.92rem; color:#7f8c8d; margin-top:2px;">Creador: JFRodriguez</div>
        </div>
        <div style="background:{badge_color};color:white;padding:8px 14px;border-radius:12px;text-align:center;font-size:0.90rem; min-width:150px;">
            📐 Archivo en <b>{badge_txt}</b>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

k1,k2,k3,k4,k5,k6 = st.columns(6)
k1.metric("Máximo", f"{df[col].max():.2f} {u}")
k2.metric("Mínimo", f"{df[col].min():.2f} {u}")
k3.metric("Promedio", f"{df[col].mean():.2f} {u}")
k4.metric("Rango", f"{df[col].max()-df[col].min():.2f} {u}")
k5.metric("Pleamares", f"{len(plea_all)}")
k6.metric("Bajamares", f"{len(baja_all)}")
st.markdown("---")


# ══════════════════════════════════════════════════════════════
# TABS
# ══════════════════════════════════════════════════════════════
tab_names = [
    "🏠 Resumen",
    "📐 Planos de Referencia",
    "🌐 Ciclo Nodal",
    "🔮 Predicción Astronómica",
    "📈 Serie Temporal",
    "🔴 Pleamares / Bajamares",
    "📊 Espectro",
    "📅 Estadísticas",
    "🗺️ Heatmap",
    "📉 Tendencia",
    "⚠️ Niveles Críticos",
    "🔧 Calidad",
    "📅 Comparar Años",
    "🚢 Paso bajo puentes",
]
if len(datasets) > 1:
    tab_names.append("🔀 Comparar")
tab_names.append("📥 Exportar")
tabs = st.tabs(tab_names)


# ═══════════════════════════════════════════════════════════════
# TAB 0 — RESUMEN
# ═══════════════════════════════════════════════════════════════
with tabs[0]:
    st.subheader("Últimos 7 días")
    ult7 = df[df["fecha"] >= df["fecha"].max() - pd.Timedelta(days=7)]
    s1,s2,s3 = st.columns(3)

    with s1:
        fig_s = go.Figure()
        fig_s.add_trace(go.Scattergl(x=ult7["fecha"], y=ult7[col],
            mode="lines", line=dict(color=color["linea"], width=1.5),
            fill="tozeroy", fillcolor=color["fill"]))
        fig_s.update_layout(height=200, template="plotly_white",
            margin=dict(l=10,r=10,t=30,b=10), showlegend=False,
            title=dict(text="Nivel de marea", font_size=13))
        st.plotly_chart(fig_s, use_container_width=True)

    with s2:
        d7 = ult7.set_index("fecha")[[col]].resample("1D").agg(["max","min"]).dropna()
        d7.columns = ["max","min"]; d7["rango"] = d7["max"] - d7["min"]
        fig_r = go.Figure()
        fig_r.add_trace(go.Bar(x=d7.index, y=d7["rango"], marker_color=color["pico"], opacity=0.7))
        fig_r.update_layout(height=200, template="plotly_white",
            margin=dict(l=10,r=10,t=30,b=10), showlegend=False,
            title=dict(text="Rango diario", font_size=13))
        st.plotly_chart(fig_r, use_container_width=True)

    with s3:
        ult7h = ult7.copy(); ult7h["hora"] = ult7h["fecha"].dt.hour
        ch = ult7h.groupby("hora")[col].mean()
        fig_c = go.Figure()
        fig_c.add_trace(go.Scatter(x=ch.index, y=ch.values,
            mode="lines+markers", line=dict(color=color["linea"], width=2), marker=dict(size=3)))
        fig_c.update_layout(height=200, template="plotly_white",
            margin=dict(l=10,r=10,t=30,b=10), showlegend=False,
            title=dict(text="Ciclo diario", font_size=13), xaxis_title="Hora")
        st.plotly_chart(fig_c, use_container_width=True)

    st.subheader("Planos de referencia (resumen)")
    datums, rangos = calcular_datums(df, col, plea_all, baja_all)

    items = list(datums.items())
    dc1,dc2,dc3 = st.columns(3)
    _col_map = {0: dc1, 1: dc2, 2: dc3}
    for idx, (key, d) in enumerate(items):
        col_target = _col_map[idx % 3]
        with col_target:
            st.metric(label=f"{key} — {d['desc'][:40]}", value=f"{d['valor']:.2f} {u}")

    st.subheader("Distribución de niveles")
    fig_dist = go.Figure()
    fig_dist.add_trace(go.Histogram(x=df[col], nbinsx=80,
        marker_color=color["linea"], opacity=0.7))
    for key in ["MHHW","MHW","MSL","MLW","MLLW"]:
        d = datums[key]
        if not np.isnan(d["valor"]):
            fig_dist.add_vline(x=d["valor"], line_dash="dash", line_color=d["color"],
                annotation_text=key, annotation_font_size=10)
    fig_dist.update_layout(xaxis_title=f"Nivel ({u})", yaxis_title="Frecuencia",
        template="plotly_white", height=350, margin=dict(l=50,r=20,t=20,b=50))
    st.plotly_chart(fig_dist, use_container_width=True)


# ═══════════════════════════════════════════════════════════════
# TAB 1 — PLANOS DE REFERENCIA (TIDAL DATUMS)
# ═══════════════════════════════════════════════════════════════
with tabs[1]:
    st.subheader("Planos de Referencia de Mareas (Tidal Datums)")
    st.caption(
        "Niveles de referencia calculados a partir de los datos observados. "
        "Basado en definiciones NOAA/IHO."
    )
    datums, rangos = calcular_datums(df, col, plea_all, baja_all)

    fig_d = go.Figure()
    muestra = df[df["fecha"] >= df["fecha"].max() - pd.Timedelta(days=5)]
    if len(muestra) > 0:
        fig_d.add_trace(go.Scatter(
            x=muestra["fecha"], y=muestra[col],
            mode="lines", name="Nivel observado",
            line=dict(color=color["linea"], width=1.5),
            fill="tozeroy", fillcolor=color["fill"],
        ))
    for key, d in datums.items():
        if np.isnan(d["valor"]): continue
        fig_d.add_hline(
            y=d["valor"], line_dash="solid" if key == "MSL" else "dash",
            line_color=d["color"], line_width=2 if key == "MSL" else 1.5,
            annotation_text=f"{key}: {d['valor']:.2f} {u}",
            annotation_position="right",
            annotation_font_size=11, annotation_font_color=d["color"],
        )
    fig_d.update_layout(yaxis_title=f"Nivel ({u})", template="plotly_white", height=550,
        hovermode="x unified", margin=dict(l=50, r=150, t=30, b=50))
    st.plotly_chart(fig_d, use_container_width=True)

    st.subheader("Tabla de planos de referencia")
    filas_d = []
    for key, d in datums.items():
        if np.isnan(d["valor"]): continue
        filas_d.append({"Sigla": key, "Nombre": d["nombre"],
            f"Nivel ({u})": round(d["valor"], 3), "Descripción": d["desc"]})
    st.dataframe(pd.DataFrame(filas_d), use_container_width=True, hide_index=True)

    st.subheader("Rangos de marea derivados")
    rc1, rc2 = st.columns(2)
    for i, (nombre, valor) in enumerate(rangos.items()):
        target = rc1 if i % 2 == 0 else rc2
        with target:
            st.metric(nombre, f"{valor:.3f} {u}")

    if "MN (Mean Range)" in rangos and "GT (Great Diurnal Range)" in rangos:
        F = rangos.get("GT (Great Diurnal Range)", 0)
        mn = rangos.get("MN (Mean Range)", 1)
        ratio = F / mn if mn > 0 else 0
        if ratio < 0.25: tipo = "Semidiurna"; desc_tipo = "Dos pleamares y dos bajamares por día, similares en altura."
        elif ratio < 1.5: tipo = "Mixta (predominio semidiurno)"; desc_tipo = "Dos pleamares y bajamares por día, con alturas desiguales."
        elif ratio < 3.0: tipo = "Mixta (predominio diurno)"; desc_tipo = "Desigualdad notable entre pleamares/bajamares sucesivas."
        else: tipo = "Diurna"; desc_tipo = "Una pleamar y una bajamar por día."
        st.subheader("Clasificación de la marea")
        st.info(f"**Tipo:** {tipo} (F = GT/MN = {ratio:.2f})\n\n{desc_tipo}")

    st.subheader("Evolución de planos por año")
    _df_evol_src = df.copy()
    _df_evol_src["anio"] = _df_evol_src["fecha"].dt.year
    anios = sorted(_df_evol_src["anio"].unique())
    evol = []
    for a in anios:
        sub = _df_evol_src[_df_evol_src["anio"] == a]
        p_a, b_a = encontrar_picos(sub, col, prom_d, 20)
        if len(p_a) > 5 and len(b_a) > 5:
            p_a["date"] = p_a["fecha"].dt.date
            b_a["date"] = b_a["fecha"].dt.date
            evol.append({"Año": a, "HAT": sub[col].max(),
                "MHHW": p_a.groupby("date")[col].max().mean(),
                "MHW": p_a[col].mean(), "MSL": sub[col].mean(),
                "MLW": b_a[col].mean(),
                "MLLW": b_a.groupby("date")[col].min().mean(),
                "LAT": sub[col].min()})
    if evol:
        df_evol = pd.DataFrame(evol)
        fig_ev = go.Figure()
        colores_ev = {"HAT":"#922b21","MHHW":"#e74c3c","MHW":"#e67e22",
                      "MSL":"#2ecc71","MLW":"#2980b9","MLLW":"#1a5276","LAT":"#0b5345"}
        for dk in ["HAT","MHHW","MHW","MSL","MLW","MLLW","LAT"]:
            if dk in df_evol.columns:
                fig_ev.add_trace(go.Scatter(x=df_evol["Año"], y=df_evol[dk],
                    mode="lines+markers", name=dk,
                    line=dict(color=colores_ev.get(dk, "#333"), width=2), marker=dict(size=5)))
        fig_ev.update_layout(yaxis_title=f"Nivel ({u})", xaxis_title="Año",
            template="plotly_white", height=500, hovermode="x unified",
            margin=dict(l=50, r=20, t=20, b=50))
        st.plotly_chart(fig_ev, use_container_width=True)
        with st.expander("📋 Tabla de datums por año"):
            st.dataframe(df_evol.round(3), use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════════
# TAB 2 — CICLO NODAL / PLANO DE REFERENCIA OFICIAL
# ═══════════════════════════════════════════════════════════════
with tabs[2]:
    st.subheader("🌐 Niveles de Referencia — Ciclo Nodal (Mar Caribe)")
    st.caption(
        "Plano de referencia oficial según NOAA CO-OPS. "
        "Tidal Epoch 1992-2010. Estación: Cristóbal / Limon Bay."
    )

    # Imagen de referencia si existe
    _ciclo_img = os.path.join(_dir, "ciclo_nodal.png")
    if os.path.exists(_ciclo_img):
        with st.expander("📷 Diagrama original de referencia", expanded=False):
            st.image(_ciclo_img, use_container_width=True)

    datum_defs = STATION_NODAL_DATUMS.get(est_activa)
    cn_col1, cn_col2 = st.columns([2, 3])

    if datum_defs is None:
        with cn_col1:
            st.markdown("#### ⚙️ Configuración de Offset")
            st.selectbox(
                "Datum de referencia (cero)",
                ["No disponible para esta estación"],
                disabled=True,
                key=f"cn_ref_disabled_{est_activa}"
            )
            st.radio(
                "Unidad del diagrama",
                ["Pies (ft)", "Metros (m)"],
                disabled=True,
                horizontal=True,
                key=f"cn_u_disabled_{est_activa}"
            )
            st.number_input(
                "Offset adicional",
                value=0.0,
                disabled=True,
                key=f"cn_offset_disabled_{est_activa}"
            )
            st.warning(
                "Los datums oficiales del bloque de Ciclo Nodal solo están definidos para Limon Bay (LMB)."
            )

        with cn_col2:
            st.markdown("#### 📊 Diagrama de Niveles de Referencia")
            st.info(
                f"El diagrama nodal no aplica a {NOMBRES.get(est_activa, est_activa)} hasta contar con offsets oficiales equivalentes."
            )
    else:
        with cn_col1:
            st.markdown("#### ⚙️ Configuración de Offset")
            datum_ref_sel = st.selectbox(
                "Datum de referencia (cero)",
                list(datum_defs.keys()),
                index=list(datum_defs.keys()).index("CERO_REGLA"),
                format_func=lambda x: f"{x} — {datum_defs[x]['nombre']}",
                key="cn_ref"
            )
            u_cn = st.radio("Unidad del diagrama", ["Pies (ft)", "Metros (m)"],
                            horizontal=True, key="cn_u")
            u_cn_label = "ft" if "Pies" in u_cn else "m"

            offset_custom = st.number_input(
                f"Offset adicional ({u_cn_label})", value=0.000, step=0.001, format="%.3f",
                help="Desplazamiento adicional sobre el datum seleccionado.",
                key="cn_offset"
            )

            st.markdown("---")
            st.markdown("#### 📋 Tabla de Datums")

            ref_offset = datum_defs[datum_ref_sel]["offset_ft_desde_cero"]
            offset_custom_ft = offset_custom if u_cn_label == "ft" else offset_custom * M_TO_FT

            tabla_cn = []
            for key, info in datum_defs.items():
                val_ft = info["offset_ft_desde_cero"] - ref_offset + offset_custom_ft
                val_m = val_ft * FT_TO_M

                if u_cn_label == "ft":
                    tabla_cn.append({
                        "Datum": key,
                        "Nombre": info["nombre"],
                        "Nivel (ft)": round(val_ft, 3),
                        "Nivel (m)": round(val_m, 4),
                    })
                else:
                    tabla_cn.append({
                        "Datum": key,
                        "Nombre": info["nombre"],
                        "Nivel (m)": round(val_m, 4),
                        "Nivel (ft)": round(val_ft, 3),
                    })

            df_cn = pd.DataFrame(tabla_cn)
            st.dataframe(df_cn, use_container_width=True, hide_index=True)

        with cn_col2:
            st.markdown("#### 📊 Diagrama de Niveles de Referencia")

            fig_cn = go.Figure()
            for key, info in datum_defs.items():
                val_ft = info["offset_ft_desde_cero"] - ref_offset + offset_custom_ft
                val_display = val_ft if u_cn_label == "ft" else val_ft * FT_TO_M

                fig_cn.add_hline(
                    y=val_display,
                    line_dash="solid" if key in ["MSL", "CERO_REGLA"] else "dash",
                    line_color=info["color"],
                    line_width=3 if key in ["MSL", "MLW"] else 2,
                )
                fig_cn.add_annotation(
                    x=1.02, y=val_display,
                    xref="paper", yref="y",
                    text=f"<b>{key}</b>: {val_display:.3f} {u_cn_label}",
                    showarrow=False,
                    font=dict(size=11, color=info["color"]),
                    xanchor="left",
                )

            if len(df) > 0:
                muestra_cn = df[df["fecha"] >= df["fecha"].max() - pd.Timedelta(days=3)].copy()
                if len(muestra_cn) > 0:
                    muestra_cn["nivel_ref_ft"] = muestra_cn["nivel_ft"] - ref_offset + offset_custom_ft
                    if u_cn_label == "ft":
                        muestra_cn["nivel_ref_display"] = muestra_cn["nivel_ref_ft"]
                    else:
                        muestra_cn["nivel_ref_display"] = muestra_cn["nivel_ref_ft"] * FT_TO_M

                    fig_cn.add_trace(go.Scatter(
                        x=muestra_cn["fecha"], y=muestra_cn["nivel_ref_display"],
                        mode="lines", name="Nivel observado (últimos 3 días)",
                        line=dict(color=color["linea"], width=1.5),
                        opacity=0.5,
                    ))

            fig_cn.update_layout(
                yaxis_title=f"Nivel ({u_cn_label}) ref: {datum_ref_sel}",
                template="plotly_white",
                height=600,
                margin=dict(l=50, r=200, t=30, b=50),
                showlegend=True,
                legend=dict(x=0, y=1),
            )
            st.plotly_chart(fig_cn, use_container_width=True)

        st.markdown("---")
        st.subheader("Diferencias entre Datums")
        st.caption("Separaciones verticales entre los niveles de referencia oficiales.")

        diff_data = [
            ("MSL → MLW", 0.390, 119),
            ("MSL → MLW (NOAA*)", 0.380, 116),
            ("MLW → PLD", 0.010, 3),
            ("PLD → Ref. Oficial RP", 0.164, 50),
            ("MSL → LLW", 2.010, 613),
            ("MLW → LLW", 2.000, 610),
            ("Ref. Oficial → LLW", 1.290, 393),
            ("LLW → Cero Regla", 0.710, 217),
        ]
        df_diff = pd.DataFrame(diff_data, columns=["Separación", "Pies (')", "Milímetros (mm)"])
        df_diff["Metros (m)"] = (df_diff["Pies (')"] * FT_TO_M).round(4)
        st.dataframe(df_diff, use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════════
# TAB 3 — PREDICCIÓN ASTRONÓMICA
# ═══════════════════════════════════════════════════════════════
with tabs[3]:
    st.subheader("🔮 Predicción de Mareas Astronómicas")
    st.caption(
        "Predicción basada en la superposición de constituyentes armónicas. "
        "h(t) = Z₀ + Σ [Aᵢ · cos(ωᵢ · t − φᵢ)]"
    )

    # Opción: cargar predicción pre-calculada UTide
    pred_source_opt = st.radio(
        "Método de predicción",
        ["🔮 Calcular con constituyentes (V₀+nodal)", "📄 Cargar predicción UTide (CSV)"],
        horizontal=True, key="pred_method"
    )

    utide_csv = None
    pred_df_activa = None
    pred_source_label = None
    pred_inicio_render = None
    pred_fin_render = None
    pred_unit_for_render = unidad
    current_pred_source = None
    current_pred_signature = None

    if "Cargar" in pred_source_opt:
        utide_csv = st.file_uploader(
            "CSV de predicción UTide (del notebook)", type=["csv"], key="utide_csv"
        )
        pred_source_name = "utide_csv"
        current_pred_source = pred_source_name
        pred_signature = "|".join([
            est_activa,
            pred_source_name,
            u,
            obtener_firma_fuente(utide_csv),
        ])
        current_pred_signature = pred_signature
        limpiar_prediccion_cache(est_activa, pred_source_name, u, pred_signature)

        if utide_csv:
            try:
                df_utide = cargar_prediccion_utide(utide_csv)
                pred_df_activa = normalizar_df_pred(
                    df_utide, est_activa, pred_source_name, unidad_base="m"
                )
                st.session_state["df_pred"] = pred_df_activa
                st.session_state["pred_station"] = est_activa
                st.session_state["pred_source"] = pred_source_name
                st.session_state["pred_unit"] = u
                st.session_state["pred_signature"] = pred_signature
                pred_source_label = "CSV UTide"
                pred_inicio_render = pred_df_activa["fecha"].min().date()
                pred_fin_render = pred_df_activa["fecha"].max().date()
                st.success(f"✅ Predicción UTide cargada: {len(pred_df_activa):,} puntos")
                st.caption("⚠️ Se asume que la predicción UTide viene en metros y se normaliza internamente.")
            except Exception as ex:
                st.error(f"Error leyendo CSV: {ex}")
        else:
            st.warning("⚠️ Sube un CSV de predicción UTide para visualizar resultados.")

    else:
        if const_source is None:
            limpiar_prediccion_cache(est_activa, "harmonic_constituents", None, "missing_constituents")
            st.warning(
                "⚠️ No se han cargado constituyentes armónicas. "
                "Sube un archivo en la barra lateral."
            )
        else:
            constituents = cargar_constituyentes(const_source)

            if constituents is not None:
                with st.expander("📋 Constituyentes armónicas cargadas", expanded=False):
                    st.dataframe(constituents, use_container_width=True, hide_index=True)
                    st.info(f"**{len(constituents)}** constituyentes · "
                            f"Amplitud máx: {constituents['Amplitude'].max():.4f} m · "
                            f"Amplitud total (suma): {constituents['Amplitude'].sum():.4f} m")

                st.markdown("---")
                pc1, pc2, pc3 = st.columns([1, 1, 1])

                with pc1:
                    pred_inicio = st.date_input("Fecha inicio predicción",
                        value=datetime.now().date(),
                        key="pred_ini")
                with pc2:
                    pred_dias = st.slider("Días a predecir", 1, 365, 30, key="pred_dias")
                with pc3:
                    pred_intervalo = st.selectbox("Intervalo",
                        [6, 10, 15, 30, 60], index=2,
                        format_func=lambda x: f"{x} min", key="pred_int")

                pred_fin = pred_inicio + timedelta(days=pred_dias)

                z0_opts = st.columns([1, 1, 2])
                with z0_opts[0]:
                    z0_mode = st.radio("Z₀ (nivel medio)", ["MSL observado", "Manual"], horizontal=True, key="z0_mode")
                with z0_opts[1]:
                    u_pred = st.radio("Unidad predicción", ["Metros (m)", "Pies (ft)"], horizontal=True, key="u_pred")
                u_pred_label = "m" if "Metros" in u_pred else "ft"
                pred_unit_for_render = u_pred

                msl_obs_m = df_all["nivel_m"].mean()
                msl_obs_ft = df_all["nivel_ft"].mean()

                if z0_mode == "MSL observado":
                    z0_m = msl_obs_m
                    st.info(f"Z₀ = MSL observado = **{msl_obs_m:.4f} m** ({msl_obs_ft:.4f} ft)")
                else:
                    with z0_opts[2]:
                        z0_m = st.number_input("Z₀ (metros)", value=round(msl_obs_m, 4),
                                               step=0.001, format="%.4f", key="z0_val")

                datum_options = ["MSL (nivel medio)", "MLW (carta náutica)"] if est_activa == "LMB" else ["MSL (nivel medio)"]
                datum_pred = st.selectbox("Datum de salida", datum_options, key="datum_pred")
                datum_off_m = obtener_offset_datum(est_activa, datum_pred)
                if datum_off_m is None:
                    datum_off_m = 0.0
                    if est_activa != "LMB":
                        st.info("Para esta estación solo se deja habilitado MSL hasta contar con un offset oficial equivalente.")
                elif "MLW" in datum_pred:
                    st.caption(f"Offset MLW: {datum_off_m:.4f} m (MSL está {abs(datum_off_m):.3f} m sobre MLW)")

                pred_source_name = "harmonic_constituents"
                current_pred_source = pred_source_name
                pred_signature = "|".join([
                    est_activa,
                    pred_source_name,
                    u_pred_label,
                    obtener_firma_fuente(const_source),
                    str(pred_inicio),
                    str(pred_fin),
                    str(pred_intervalo),
                    z0_mode,
                    f"{z0_m:.4f}",
                    datum_pred,
                ])
                current_pred_signature = pred_signature
                limpiar_prediccion_cache(est_activa, pred_source_name, u_pred_label, pred_signature)

                if st.button("🔮 Calcular Predicción", type="primary", key="btn_pred"):
                    with st.spinner("Calculando predicción astronómica..."):
                        df_pred = predecir_marea(
                            constituents,
                            pd.Timestamp(pred_inicio),
                            pd.Timestamp(pred_fin),
                            intervalo_min=pred_intervalo,
                            z0=z0_m,
                            datum_offset_m=datum_off_m
                        )
                        pred_df_activa = normalizar_df_pred(
                            df_pred, est_activa, pred_source_name, unidad_base="m"
                        )
                        st.session_state["df_pred"] = pred_df_activa
                        st.session_state["pred_station"] = est_activa
                        st.session_state["pred_source"] = pred_source_name
                        st.session_state["pred_unit"] = u_pred_label
                        st.session_state["pred_signature"] = pred_signature
                        pred_source_label = "Constituyentes armónicas"
                        pred_inicio_render = pred_inicio
                        pred_fin_render = pred_fin
                        st.success(f"✅ Predicción generada: {len(pred_df_activa):,} puntos · "
                                  f"{pred_inicio} → {pred_fin}")

    if pred_df_activa is None and "df_pred" in st.session_state:
        if (
            st.session_state.get("pred_station") == est_activa
            and st.session_state.get("pred_source") == current_pred_source
            and st.session_state.get("pred_signature") == current_pred_signature
        ):
            pred_df_activa = st.session_state["df_pred"]
            pred_source_label = "CSV UTide" if st.session_state.get("pred_source") == "utide_csv" else "Constituyentes armónicas"
            pred_inicio_render = pred_df_activa["fecha"].min().date()
            pred_fin_render = pred_df_activa["fecha"].max().date()

    if pred_df_activa is not None:
        renderizar_prediccion(
            pred_df_activa,
            df_all,
            est_activa,
            color,
            pred_unit_for_render,
            pred_source_label,
            pred_inicio_render,
            pred_fin_render,
        )


# ═══════════════════════════════════════════════════════════════
# TAB 4 — SERIE TEMPORAL
# ═══════════════════════════════════════════════════════════════
with tabs[4]:
    st.subheader("Serie temporal")
    mostrar_datums = st.checkbox("Mostrar planos de referencia", value=True)
    dp, resumido = resam(df, col)
    if resumido: st.caption(f"Vista resumida · {len(dp):,} puntos")

    fig1 = go.Figure()
    fig1.add_trace(go.Scattergl(x=dp["fecha"], y=dp[col],
        mode="lines", name="Nivel", line=dict(color=color["linea"], width=1.2),
        fill="tozeroy", fillcolor=color["fill"]))
    if mostrar_datums:
        for key in ["MHHW","MHW","MSL","MLW","MLLW"]:
            d = datums[key]
            if not np.isnan(d["valor"]):
                fig1.add_hline(y=d["valor"], line_dash="dash", line_color=d["color"],
                    annotation_text=f"{key}: {d['valor']:.2f}", annotation_font_size=10, line_width=1)
    fig1.update_layout(yaxis_title=f"Nivel ({u})", template="plotly_white",
        height=500, hovermode="x unified", margin=dict(l=50,r=20,t=30,b=50))
    st.plotly_chart(fig1, use_container_width=True)

    st.subheader("Promedio móvil")
    vc1, vc2 = st.columns([1, 4])
    with vc1:
        vent = st.slider("Ventana (días)", 1, 90, 15)
    df_ma = df.set_index("fecha")[[col]].resample("1h").mean()
    df_ma["media"] = df_ma[col].rolling(vent*24, min_periods=1).mean()
    df_ma = df_ma.dropna(subset=["media"]).reset_index()
    mp, _ = resam(df_ma, "media", freq="6h")

    fig1b = go.Figure()
    fig1b.add_trace(go.Scattergl(x=mp["fecha"], y=mp["media"],
        mode="lines", line=dict(color=color["linea"], width=2), name=f"Media {vent}d"))
    fig1b.update_layout(yaxis_title=f"Nivel ({u})", template="plotly_white",
        height=350, hovermode="x unified", margin=dict(l=50,r=20,t=20,b=50))
    st.plotly_chart(fig1b, use_container_width=True)


# ═══════════════════════════════════════════════════════════════
# TAB 5 — PLEAMARES / BAJAMARES
# ═══════════════════════════════════════════════════════════════
with tabs[5]:
    cc, cg = st.columns([1, 3])
    pd_def = 0.15 if est_activa == "LMB" else 2.0
    if "Metros" in unidad: pd_def *= 0.3048
    with cc:
        prom_sl = st.slider("Prominencia", 0.01, 5.0, round(pd_def, 2), 0.01)
        dist_sl = st.slider("Distancia mín.", 5, 60, 20)
    plea, baja = encontrar_picos(df, col, prom_sl, dist_sl)
    with cc:
        st.metric("Pleamares", len(plea))
        st.metric("Bajamares", len(baja))
        if len(plea): st.metric("Pleamar prom.", f"{plea[col].mean():.2f} {u}")
        if len(baja): st.metric("Bajamar prom.", f"{baja[col].mean():.2f} {u}")

    with cg:
        bg, _ = resam(df, col)
        fig2 = go.Figure()
        fig2.add_trace(go.Scattergl(x=bg["fecha"], y=bg[col],
            mode="lines", name="Nivel", line=dict(color="#bdc3c7", width=0.8)))
        fig2.add_trace(go.Scatter(x=plea["fecha"], y=plea[col],
            mode="markers", name="Pleamar",
            marker=dict(color=color["pico"], size=5, symbol="triangle-up")))
        fig2.add_trace(go.Scatter(x=baja["fecha"], y=baja[col],
            mode="markers", name="Bajamar",
            marker=dict(color=color["valle"], size=5, symbol="triangle-down")))
        for key in ["MHW","MLW"]:
            d = datums[key]
            if not np.isnan(d["valor"]):
                fig2.add_hline(y=d["valor"], line_dash="dot", line_color=d["color"],
                    annotation_text=key, line_width=1)
        fig2.update_layout(yaxis_title=f"Nivel ({u})", template="plotly_white",
            height=480, hovermode="x unified", margin=dict(l=50,r=20,t=20,b=50))
        st.plotly_chart(fig2, use_container_width=True)

    with st.expander("📋 Tabla de eventos"):
        ev = pd.concat([plea, baja]).sort_values("fecha").reset_index(drop=True)
        ev.columns = ["Fecha/Hora", f"Nivel ({u})", "Tipo"]
        st.dataframe(ev, use_container_width=True, height=350)

    st.subheader("Distribución de alturas de pleamares y bajamares")
    hc1, hc2 = st.columns(2)
    with hc1:
        fig_hp = go.Figure()
        fig_hp.add_trace(go.Histogram(x=plea[col], nbinsx=40,
            marker_color=color["pico"], opacity=0.7, name="Pleamares"))
        fig_hp.update_layout(xaxis_title=f"Nivel ({u})", yaxis_title="Frecuencia",
            template="plotly_white", height=300, title="Pleamares",
            margin=dict(l=50,r=20,t=40,b=50))
        st.plotly_chart(fig_hp, use_container_width=True)
    with hc2:
        fig_hb = go.Figure()
        fig_hb.add_trace(go.Histogram(x=baja[col], nbinsx=40,
            marker_color=color["valle"], opacity=0.7, name="Bajamares"))
        fig_hb.update_layout(xaxis_title=f"Nivel ({u})", yaxis_title="Frecuencia",
            template="plotly_white", height=300, title="Bajamares",
            margin=dict(l=50,r=20,t=40,b=50))
        st.plotly_chart(fig_hb, use_container_width=True)


# ═══════════════════════════════════════════════════════════════
# TAB 6 — ESPECTRO
# ═══════════════════════════════════════════════════════════════
with tabs[6]:
    st.caption("FFT para identificar componentes armónicas.")
    df_sp = df.set_index("fecha")[[col]].resample("15min").mean().interpolate()
    vals = df_sp[col].values; vals = vals - vals.mean(); N = len(vals)

    if N < 200:
        st.warning("Necesitas ≥3 días de datos.")
    else:
        yf = fft(vals); xf = fftfreq(N, d=0.25)
        mp_mask = xf > 0; freqs = xf[mp_mask]; amps = 2.0/N*np.abs(yf[mp_mask]); periodos = 1.0/freqs

        comps = {"M2":12.42,"S2":12.00,"N2":12.66,"K1":23.93,
                 "O1":25.82,"P1":24.07,"K2":11.97,"M4":6.21,"MS4":6.10}

        mr = (periodos >= 4) & (periodos <= 30)
        fig3 = go.Figure()
        fig3.add_trace(go.Scatter(x=periodos[mr], y=amps[mr], mode="lines",
            line=dict(color=color["linea"], width=1.5), fill="tozeroy", fillcolor=color["fill"]))
        cc_list = ["#e74c3c","#3498db","#e67e22","#2ecc71","#9b59b6","#1abc9c","#f39c12","#34495e","#c0392b"]
        for i,(n,p) in enumerate(comps.items()):
            fig3.add_vline(x=p, line_dash="dot", line_color=cc_list[i%len(cc_list)],
                annotation_text=n, annotation_position="top", annotation_font_size=10)
        fig3.update_layout(xaxis_title="Período (h)", yaxis_title=f"Amplitud ({u})",
            template="plotly_white", height=500, margin=dict(l=50,r=20,t=30,b=50))
        st.plotly_chart(fig3, use_container_width=True)

        st.subheader("Componentes detectadas")
        res = []
        for nombre, pr in comps.items():
            mc = (periodos > pr-0.5) & (periodos < pr+0.5)
            if mc.any():
                res.append({"Componente": nombre, "Período teórico (h)": pr,
                    "Período detectado (h)": round(periodos[mc][np.argmax(amps[mc])], 2),
                    f"Amplitud ({u})": round(amps[mc].max(), 4)})
        if res:
            st.dataframe(pd.DataFrame(res).sort_values(f"Amplitud ({u})", ascending=False),
                use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════════
# TAB 7 — ESTADÍSTICAS
# ═══════════════════════════════════════════════════════════════
with tabs[7]:
    cs1, cs2 = st.columns(2)
    with cs1:
        st.subheader("Resumen")
        stats = df[col].describe()
        st.dataframe(pd.DataFrame({
            "Estadística": ["N","Media","Desv.Est.","Mín","25%","Mediana","75%","Máx"],
            "Valor": [f"{int(stats['count']):,}"] + [f"{stats[k]:.3f} {u}" for k in
                      ["mean","std","min","25%","50%","75%","max"]],
        }), use_container_width=True, hide_index=True)

    with cs2:
        st.subheader("Box plot mensual")
        _df_box = df.copy()
        _df_box["mn"] = _df_box["fecha"].dt.month
        fig_bx = go.Figure()
        for m in sorted(_df_box["mn"].unique()):
            s = _df_box[_df_box["mn"]==m]
            fig_bx.add_trace(go.Box(y=s[col], name=MESES[m-1],
                marker_color=f"hsl({(m-1)*30},65%,50%)", boxmean=True))
        fig_bx.update_layout(yaxis_title=f"Nivel ({u})", template="plotly_white",
            height=350, showlegend=False, margin=dict(l=50,r=20,t=20,b=50))
        st.plotly_chart(fig_bx, use_container_width=True)

    st.subheader("Promedios mensuales")
    _df_pm = df.copy()
    _df_pm["mes"] = _df_pm["fecha"].dt.month
    pm = _df_pm.groupby("mes")[col].agg(["mean","min","max"]).reset_index()
    fig5 = go.Figure()
    fig5.add_trace(go.Bar(x=[MESES[m-1] for m in pm["mes"]], y=pm["mean"],
        marker_color=color["linea"], name="Promedio"))
    fig5.add_trace(go.Scatter(x=[MESES[m-1] for m in pm["mes"]], y=pm["max"],
        mode="lines+markers", name="Máx", line=dict(color=color["pico"], dash="dot")))
    fig5.add_trace(go.Scatter(x=[MESES[m-1] for m in pm["mes"]], y=pm["min"],
        mode="lines+markers", name="Mín", line=dict(color=color["valle"], dash="dot")))
    fig5.update_layout(yaxis_title=f"Nivel ({u})", template="plotly_white",
        height=380, margin=dict(l=50,r=20,t=20,b=50))
    st.plotly_chart(fig5, use_container_width=True)


# ═══════════════════════════════════════════════════════════════
# TAB 8 — HEATMAP
# ═══════════════════════════════════════════════════════════════
with tabs[8]:
    st.subheader("Mapa de calor: Mes × Año")
    _df_hm = df.copy()
    _df_hm["anio"]=_df_hm["fecha"].dt.year; _df_hm["mes"]=_df_hm["fecha"].dt.month
    pv = _df_hm.groupby(["anio","mes"])[col].mean().reset_index()
    pt = pv.pivot(index="anio", columns="mes", values=col)
    pt.columns = [MESES[m-1] for m in pt.columns]
    fig_hm = go.Figure(data=go.Heatmap(z=pt.values, x=pt.columns, y=pt.index,
        colorscale="Blues", colorbar_title=u, hoverongaps=False))
    fig_hm.update_layout(yaxis_title="Año", template="plotly_white",
        height=max(350, len(pt)*22), margin=dict(l=60,r=20,t=20,b=50))
    st.plotly_chart(fig_hm, use_container_width=True)

    st.subheader("Mapa de calor: Hora × Mes (rango de marea)")
    _df_hm["hora"]=_df_hm["fecha"].dt.hour
    pv2 = _df_hm.groupby(["hora","mes"])[col].agg(lambda x: x.max()-x.min()).reset_index()
    pt2 = pv2.pivot(index="hora", columns="mes", values=col)
    pt2.columns = [MESES[m-1] for m in pt2.columns]
    fig_hm2 = go.Figure(data=go.Heatmap(z=pt2.values, x=pt2.columns, y=pt2.index,
        colorscale="YlOrRd", colorbar_title=f"Rango ({u})", hoverongaps=False))
    fig_hm2.update_layout(yaxis_title="Hora", template="plotly_white",
        height=450, margin=dict(l=60,r=20,t=20,b=50))
    st.plotly_chart(fig_hm2, use_container_width=True)


# ═══════════════════════════════════════════════════════════════
# TAB 9 — TENDENCIA
# ═══════════════════════════════════════════════════════════════
with tabs[9]:
    st.subheader("Tendencia del nivel medio del mar")
    st.caption(
        "La tendencia puede calcularse con promedios mensuales o anuales. "
        "Para redactar resultados como “2004–2023 = +5.07 mm/año”, conviene usar promedios anuales."
    )

    tc1, tc2 = st.columns([1, 3])
    with tc1:
        base_tend = st.radio(
            "Base de cálculo",
            ["Promedios mensuales", "Promedios anuales"],
            horizontal=False,
            key="trend_base"
        )

    _df_tend = df[["fecha", col]].dropna().copy().sort_values("fecha")

    if base_tend == "Promedios anuales":
        serie = _df_tend.set_index("fecha")[col].resample("YE").mean().dropna()
        x_vals = serie.index.year.astype(float)
        etiqueta_serie = "Nivel medio anual observado"
        etiqueta_y = f"Nivel medio anual ({u})"
        texto_base = "anuales"
    else:
        serie = _df_tend.set_index("fecha")[col].resample("ME").mean().dropna()
        x_vals = serie.index.year + (serie.index.dayofyear - 1) / 365.25
        etiqueta_serie = "Nivel medio mensual observado"
        etiqueta_y = f"Nivel medio mensual ({u})"
        texto_base = "mensuales"

    if len(serie) >= 3:
        slope, intercept, r_val, p_val, std_err = sp_stats.linregress(x_vals, serie.values)
        trend_line = intercept + slope * x_vals
        slope_mm_year = slope * 1000 if u == "m" else slope * FT_TO_M * 1000

        periodo_ini = int(serie.index.min().year)
        periodo_fin = int(serie.index.max().year)
        sitio_redaccion = "Bahía Limón" if est_activa == "LMB" else NOMBRES.get(est_activa, est_activa)

        tm1, tm2, tm3, tm4 = st.columns(4)
        tm1.metric("Pendiente", f"{slope:+.5f} {u}/año")
        tm2.metric("Pendiente", f"{slope_mm_year:+.2f} mm/año")
        tm3.metric("R²", f"{r_val**2:.3f}")
        sig = "✅ Significativa" if p_val < 0.05 else "⚠️ No significativa"
        tm4.metric("p-valor", f"{p_val:.4f} ({sig})")

        if base_tend == "Promedios anuales":
            st.info(
                f"La pendiente mostrada en {u}/año y en mm/año representa la misma tendencia expresada en dos unidades. "
                f"Esta es la base recomendable para redactar resultados del tipo {periodo_ini}–{periodo_fin}."
            )
        else:
            st.warning(
                "Esta pendiente corresponde a una regresión hecha sobre promedios mensuales. "
                "Puede servir para exploración del tablero, pero no conviene mezclarla con una redacción formal de tendencia anual sin aclararlo."
            )

        fig_t = go.Figure()
        fig_t.add_trace(go.Scatter(
            x=serie.index,
            y=serie.values,
            mode="lines+markers",
            name=etiqueta_serie,
            line=dict(color=color["linea"], width=2.5),
            marker=dict(size=6),
        ))
        fig_t.add_trace(go.Scatter(
            x=serie.index,
            y=trend_line,
            mode="lines",
            name=f"Tendencia lineal ({slope_mm_year:+.2f} mm/año)",
            line=dict(color="#e74c3c", dash="dash", width=2),
        ))
        fig_t.update_layout(
            xaxis_title="Fecha",
            yaxis_title=etiqueta_y,
            template="plotly_white",
            height=500,
            hovermode="x unified",
            margin=dict(l=50, r=20, t=30, b=50),
        )
        st.plotly_chart(fig_t, use_container_width=True)

        with st.expander("📋 Serie usada en la regresión", expanded=False):
            df_tend_out = pd.DataFrame({
                "Fecha": serie.index,
                etiqueta_y: serie.values,
                f"Tendencia ajustada ({u})": trend_line,
            })
            st.dataframe(df_tend_out, use_container_width=True, hide_index=True)

        if base_tend == "Promedios anuales":
            st.markdown(
                f"**Redacción sugerida para artículo:** El ajuste lineal de los promedios anuales "
                f"del nivel del mar en {sitio_redaccion} para {periodo_ini}–{periodo_fin} arroja "
                f"{slope_mm_year:+.2f} mm/año."
            )
            st.caption(
                "La comparación con estimaciones regionales previas o con el promedio global actual "
                "debe presentarse como contexto bibliográfico externo al app."
            )
        else:
            st.markdown(
                f"**Redacción sugerida para el app:** El ajuste lineal de los promedios mensuales "
                f"del nivel del mar en {sitio_redaccion} para {periodo_ini}–{periodo_fin} "
                f"arroja {slope_mm_year:+.2f} mm/año."
            )
    else:
        st.info("No hay suficientes datos para calcular una tendencia robusta.")


# ═══════════════════════════════════════════════════════════════
# TAB 10 — NIVELES CRÍTICOS
# ═══════════════════════════════════════════════════════════════
with tabs[10]:
    st.subheader("Análisis de niveles críticos y excedencia")

    uc1, uc2 = st.columns([1, 3])
    with uc1:
        ref = st.selectbox("Referencia", list(datums.keys()), index=0)
        modo = st.radio("Modo", ["Sobre un nivel", "Bajo un nivel"])
        offset = st.number_input(f"Offset desde {ref} ({u})", value=0.0, step=0.1)
        nivel_critico = datums[ref]["valor"] + offset
        st.markdown(f"**Nivel crítico:** {nivel_critico:.2f} {u}")

    if modo == "Sobre un nivel":
        excede = df[df[col] > nivel_critico]
    else:
        excede = df[df[col] < nivel_critico]

    pct = len(excede) / len(df) * 100

    with uc1:
        st.metric("Registros", f"{len(excede):,}")
        st.metric("% del total", f"{pct:.2f}%")
        st.metric("Horas aprox.", f"{len(excede):,}")

    with uc2:
        dp2, _ = resam(df, col)
        fig_uc = go.Figure()
        fig_uc.add_trace(go.Scattergl(x=dp2["fecha"], y=dp2[col],
            mode="lines", name="Nivel", line=dict(color="#bdc3c7", width=0.8)))
        if modo == "Sobre un nivel":
            fig_uc.add_hrect(y0=nivel_critico, y1=df[col].max()+1,
                fillcolor="rgba(231,76,60,0.15)", line_width=0)
        else:
            fig_uc.add_hrect(y0=df[col].min()-1, y1=nivel_critico,
                fillcolor="rgba(41,128,185,0.15)", line_width=0)
        fig_uc.add_hline(y=nivel_critico, line_dash="dash", line_color="#e74c3c",
            annotation_text=f"{ref}{'+' if offset>=0 else ''}{offset:.1f}: {nivel_critico:.2f} {u}")
        fig_uc.update_layout(yaxis_title=f"Nivel ({u})", template="plotly_white",
            height=450, hovermode="x unified", margin=dict(l=50,r=20,t=20,b=50))
        st.plotly_chart(fig_uc, use_container_width=True)

    st.subheader("Excedencia por año")
    _df_exc = df.copy()
    _df_exc["anio"] = _df_exc["fecha"].dt.year
    if modo == "Sobre un nivel":
        exc_a = _df_exc.groupby("anio").apply(lambda g: (g[col] > nivel_critico).sum()).reset_index(name="horas")
    else:
        exc_a = _df_exc.groupby("anio").apply(lambda g: (g[col] < nivel_critico).sum()).reset_index(name="horas")

    fig_ea = go.Figure()
    fig_ea.add_trace(go.Bar(x=exc_a["anio"], y=exc_a["horas"],
        marker_color=color["linea"], opacity=0.8))
    fig_ea.update_layout(yaxis_title="Horas", xaxis_title="Año",
        template="plotly_white", height=350, margin=dict(l=50,r=20,t=20,b=50))
    st.plotly_chart(fig_ea, use_container_width=True)


# ═══════════════════════════════════════════════════════════════
# TAB 11 — CALIDAD
# ═══════════════════════════════════════════════════════════════
with tabs[11]:
    st.subheader("Calidad de datos")
    ds = df.sort_values("fecha")
    deltas = ds["fecha"].diff()
    freq_esp = deltas.median()
    gaps = deltas[deltas > freq_esp * 3]

    q1,q2,q3,q4 = st.columns(4)
    q1.metric("Registros", f"{len(df):,}")
    q2.metric("Frecuencia", str(freq_esp))
    q3.metric("Vacíos", f"{len(gaps)}")
    q4.metric("Mayor vacío", str(gaps.max()) if len(gaps) else "N/A")

    st.subheader("Cobertura por año")
    _df_cob = df.copy()
    _df_cob["anio"]=_df_cob["fecha"].dt.year
    esp_anio = 365.25 * (pd.Timedelta("1D") / freq_esp) if freq_esp > pd.Timedelta(0) else 8766
    cob = _df_cob.groupby("anio").size().reset_index(name="n")
    cob["pct"] = (cob["n"] / esp_anio * 100).clip(upper=100).round(1)
    fig_q = go.Figure()
    fig_q.add_trace(go.Bar(x=cob["anio"], y=cob["pct"],
        marker_color=["#27ae60" if v>=90 else "#e67e22" if v>=50 else "#e74c3c" for v in cob["pct"]],
        text=[f"{v}%" for v in cob["pct"]], textposition="auto"))
    fig_q.add_hline(y=90, line_dash="dash", line_color="#27ae60", annotation_text="90%")
    fig_q.update_layout(yaxis_title="Cobertura (%)", yaxis_range=[0,105],
        template="plotly_white", height=350, margin=dict(l=50,r=20,t=20,b=50))
    st.plotly_chart(fig_q, use_container_width=True)

    st.subheader("Cobertura Mes × Año")
    _df_cob["mes"]=_df_cob["fecha"].dt.month
    cm = _df_cob.groupby(["anio","mes"]).size().reset_index(name="n")
    cm["esp"] = cm["mes"].apply(lambda m: calendar.monthrange(2024,m)[1] * (24*60/max(freq_esp.total_seconds()/60,1)))
    cm["pct"] = (cm["n"]/cm["esp"]*100).clip(upper=100).round(0)
    ptc = cm.pivot(index="anio", columns="mes", values="pct")
    ptc.columns = [MESES[m-1] for m in ptc.columns]
    fig_qm = go.Figure(data=go.Heatmap(z=ptc.values, x=ptc.columns, y=ptc.index,
        colorscale=[[0,"#e74c3c"],[0.5,"#f39c12"],[0.9,"#f9e79f"],[1,"#27ae60"]],
        colorbar_title="%", zmin=0, zmax=100, hoverongaps=False))
    fig_qm.update_layout(yaxis_title="Año", template="plotly_white",
        height=max(300, len(ptc)*20), margin=dict(l=60,r=20,t=20,b=50))
    st.plotly_chart(fig_qm, use_container_width=True)


# ═══════════════════════════════════════════════════════════════
# TAB 12 — COMPARAR AÑOS
# ═══════════════════════════════════════════════════════════════
with tabs[12]:
    st.subheader("📅 Comparar niveles de marea por año")

    df_ca = df_all.copy()
    df_ca["anio"] = df_ca["fecha"].dt.year
    df_ca["doy"] = df_ca["fecha"].dt.dayofyear
    anios_disp = sorted(df_ca["anio"].unique())
    if len(anios_disp) > 1:
        anios_sel = st.multiselect("Años a comparar", anios_disp,
            default=anios_disp[-3:] if len(anios_disp) >= 3 else anios_disp, key="ca_sel")

        if anios_sel:
            colores_anio = ["#e74c3c","#3498db","#2ecc71","#e67e22","#9b59b6",
                            "#1abc9c","#f39c12","#34495e","#c0392b","#16a085"]

            st.subheader("Nivel promedio diario por año")
            fig_ca1 = go.Figure()
            for i, yr in enumerate(anios_sel):
                sub = df_ca[df_ca["anio"]==yr].groupby("doy")[col].mean().reset_index()
                fig_ca1.add_trace(go.Scatter(x=sub["doy"], y=sub[col],
                    mode="lines", name=str(yr),
                    line=dict(color=colores_anio[i%len(colores_anio)], width=2)))
            fig_ca1.update_layout(xaxis_title="Día del año", yaxis_title=f"Nivel ({u})",
                template="plotly_white", height=450, hovermode="x unified",
                margin=dict(l=50,r=20,t=20,b=50))
            st.plotly_chart(fig_ca1, use_container_width=True)

            st.subheader("Resumen por año")
            rows_ca = []
            for yr in anios_sel:
                sub = df_ca[df_ca["anio"]==yr]
                prom_yr = 0.15 if est_activa == "LMB" else 2.0
                if "Metros" in unidad: prom_yr *= 0.3048
                pe_yr, be_yr = encontrar_picos(sub, col, prom_yr, 20)
                rows_ca.append({
                    "Año": yr, "Registros": f"{len(sub):,}",
                    f"Máx ({u})": f"{sub[col].max():.2f}",
                    f"Mín ({u})": f"{sub[col].min():.2f}",
                    f"MSL ({u})": f"{sub[col].mean():.2f}",
                    f"Rango ({u})": f"{sub[col].max()-sub[col].min():.2f}",
                    "Pleamares": len(pe_yr), "Bajamares": len(be_yr),
                })
            st.dataframe(pd.DataFrame(rows_ca), use_container_width=True, hide_index=True)

            st.subheader("MSL mensual × año")
            df_ca["mes"] = df_ca["fecha"].dt.month
            hm_ca = df_ca[df_ca["anio"].isin(anios_sel)].groupby(["anio","mes"])[col].mean().reset_index()
            pt_ca = hm_ca.pivot(index="anio", columns="mes", values=col)
            pt_ca.columns = [MESES[m-1] for m in pt_ca.columns]
            fig_ca2 = go.Figure(go.Heatmap(z=pt_ca.values, x=pt_ca.columns, y=pt_ca.index,
                colorscale="RdYlBu_r", colorbar_title=u))
            fig_ca2.update_layout(yaxis_title="Año", template="plotly_white",
                height=max(250, len(pt_ca)*35), margin=dict(l=60,r=20,t=20,b=50))
            st.plotly_chart(fig_ca2, use_container_width=True)

            st.subheader("Tendencia del nivel medio anual")
            msl_anual = df_ca[df_ca["anio"].isin(anios_sel)].groupby("anio")[col].mean().reset_index()
            fig_ca3 = go.Figure()
            fig_ca3.add_trace(go.Scatter(x=msl_anual["anio"], y=msl_anual[col],
                mode="lines+markers", line=dict(color=color["linea"], width=2.5),
                marker=dict(size=8)))
            if len(msl_anual) >= 3:
                z_ca = np.polyfit(msl_anual["anio"], msl_anual[col], 1)
                fig_ca3.add_trace(go.Scatter(x=msl_anual["anio"],
                    y=np.polyval(z_ca, msl_anual["anio"]),
                    mode="lines", name=f"Tendencia: {z_ca[0]*10:+.3f} {u}/década",
                    line=dict(dash="dash", color="#c0392b", width=2)))
            fig_ca3.update_layout(xaxis_title="Año", yaxis_title=f"MSL ({u})",
                template="plotly_white", height=380, margin=dict(l=50,r=20,t=20,b=50))
            st.plotly_chart(fig_ca3, use_container_width=True)
    else:
        st.info("Se necesitan datos de al menos 2 años para comparar.")



# ═══════════════════════════════════════════════════════════════
# TAB 13 — PASO BAJO PUENTES
# ═══════════════════════════════════════════════════════════════
with tabs[13]:
    st.subheader("🚢 Paso bajo puentes")
    st.caption(
        "Evalúa la luz vertical disponible bajo el puente comparando la altura libre "
        "con el calado aéreo del buque (air draft)."
    )

    bc1, bc2 = st.columns([1, 2])

    with bc1:
        puente_sel = st.selectbox("Puente", list(PUENTES.keys()), key="puente_sel")
        info_p = PUENTES[puente_sel]
        st.markdown(f"**Luz vertical nominal del puente:** {info_p['clearance_m']:.1f} m ({info_p['clearance_m']*M_TO_FT:.1f} ft)")
        st.markdown(f"**Nivel de referencia del puente:** {info_p['datum_ref']}")
        st.markdown(f"**Sector:** {info_p['lado']}")
        st.caption(info_p.get("descripcion", ""))

        estaciones_pref = [e for e in PUENTE_ESTACION_PREF.get(puente_sel, []) if e in datasets]
        if not estaciones_pref:
            st.error(
                f"No se encontró la estación adecuada para {puente_sel}. "
                f"Carga la serie correspondiente al sector {info_p['lado']} para estimar la luz disponible."
            )
            st.stop()

        puente_estacion = estaciones_pref[0]
        df_bridge_src = datasets[puente_estacion].copy()
        st.markdown(f"**Estación usada automáticamente:** {NOMBRES.get(puente_estacion, puente_estacion)}")

        st.markdown("---")
        tipo_buque = st.selectbox("Tipo de buque", list(TIPOS_BUQUES.keys()), key="tipo_buque")
        air_draft_default = TIPOS_BUQUES[tipo_buque]
        if tipo_buque == "Personalizado":
            air_draft = st.number_input("Calado aéreo del buque / air draft (m)", value=55.0, step=0.1, key="ad_custom")
        else:
            air_draft = st.number_input("Calado aéreo del buque / air draft (m)", value=air_draft_default, step=0.1, key="ad_val")

        st.markdown("---")
        nivel_actual_mode = st.radio("Nivel de agua a usar", ["Último observado", "Manual"], key="niv_mode")

        prom_bridge = 0.15 if puente_estacion == "LMB" else 2.0
        plea_bridge_m, baja_bridge_m = encontrar_picos(df_bridge_src, "nivel_m", prom_bridge, 20)
        datums_bridge_m, _ = calcular_datums(df_bridge_src, "nivel_m", plea_bridge_m, baja_bridge_m)

        if nivel_actual_mode == "Último observado":
            nivel_marea_m = df_bridge_src["nivel_m"].iloc[-1]
            nivel_marea_ft = df_bridge_src["nivel_ft"].iloc[-1]
            fecha_nivel = df_bridge_src["fecha"].iloc[-1]
            st.info(
                f"Nivel actual en {NOMBRES.get(puente_estacion, puente_estacion)}: **{nivel_marea_m:.3f} m** "
                f"({nivel_marea_ft:.2f} ft)"
            )
            st.caption(f"Hora del dato: {fecha_nivel}")
        else:
            valor_manual_default = float(df_bridge_src["nivel_m"].iloc[-1]) if len(df_bridge_src) else 0.7
            nivel_marea_m = st.number_input("Nivel de agua (m)", value=round(valor_manual_default, 3), step=0.01, key="niv_manual")
            nivel_marea_ft = nivel_marea_m * M_TO_FT
            fecha_nivel = None

        mhw_m = datums_bridge_m.get("MHW", {}).get("valor", np.nan)
        msl_m = datums_bridge_m.get("MSL", {}).get("valor", np.nan)
        ref_nivel = mhw_m if info_p["datum_ref"] == "MHW" else msl_m
        if np.isnan(ref_nivel):
            ref_nivel = df_bridge_src["nivel_m"].mean()

        delta_nivel = nivel_marea_m - ref_nivel
        luz_disponible = info_p["clearance_m"] - delta_nivel
        margen = luz_disponible - air_draft

        st.markdown("---")
        st.metric("🔵 Luz disponible bajo el puente", f"{luz_disponible:.2f} m ({luz_disponible*M_TO_FT:.1f} ft)")
        st.metric("🚢 Calado aéreo del buque", f"{air_draft:.2f} m ({air_draft*M_TO_FT:.1f} ft)")
        st.caption(
            f"Cálculo hecho con la estación **{NOMBRES.get(puente_estacion, puente_estacion)}** del lado **{info_p['lado']}**, "
            f"usando como referencia **{info_p['datum_ref']}**."
        )
        st.markdown(
            f"- Si el nivel del agua sube por encima del datum de referencia, la luz disponible disminuye.\n"
            f"- Si el nivel del agua baja respecto al datum de referencia, la luz disponible aumenta.\n"
            f"- Para **{puente_sel}**, el cálculo no usa estaciones del Pacífico cuando el puente es del Atlántico, ni viceversa."
        )


        if margen >= 3.0:
            st.success(f"✅ Margen: {margen:.2f} m — PASO SEGURO")
        elif margen >= 0:
            st.warning(f"⚠️ Margen: {margen:.2f} m — PASO CON MARGEN REDUCIDO")
        else:
            st.error(f"🚫 Margen: {margen:.2f} m — LUZ INSUFICIENTE")

    with bc2:
        st.markdown(f"#### Luz disponible en el tiempo — {puente_sel}")
        st.caption(f"Serie calculada con {NOMBRES.get(puente_estacion, puente_estacion)} en el lado {info_p['lado']}." )
        _df_bridge = df_bridge_src.copy()
        if info_p["datum_ref"] == "MHW":
            _ref_plot = mhw_m if not np.isnan(mhw_m) else _df_bridge["nivel_m"].mean()
        else:
            _ref_plot = msl_m if not np.isnan(msl_m) else _df_bridge["nivel_m"].mean()

        _df_bridge["delta"] = _df_bridge["nivel_m"] - _ref_plot
        _df_bridge["luz_disponible_m"] = info_p["clearance_m"] - _df_bridge["delta"]

        ult_bridge = _df_bridge[_df_bridge["fecha"] >= _df_bridge["fecha"].max() - pd.Timedelta(days=7)]
        dp_b, _ = resam(ult_bridge, "luz_disponible_m", limite=5000)

        fig_bridge = go.Figure()
        fig_bridge.add_trace(go.Scattergl(
            x=dp_b["fecha"], y=dp_b["luz_disponible_m"],
            mode="lines", name="Luz disponible",
            line=dict(color="#2563EB", width=2),
            fill="tozeroy", fillcolor="rgba(37,99,235,0.08)"
        ))
        fig_bridge.add_hline(y=air_draft, line_dash="dash", line_color="#e74c3c",
            annotation_text=f"Air draft del buque: {air_draft:.1f} m", line_width=2)
        fig_bridge.add_hrect(y0=0, y1=air_draft, fillcolor="rgba(231,76,60,0.1)", line_width=0)
        fig_bridge.add_hline(y=air_draft+3, line_dash="dot", line_color="#f39c12",
            annotation_text=f"Margen recomendado (+3 m): {air_draft+3:.1f} m", line_width=1)

        fig_bridge.update_layout(
            yaxis_title="Luz disponible (m)",
            template="plotly_white", height=450,
            hovermode="x unified",
            margin=dict(l=50, r=20, t=30, b=50),
        )
        st.plotly_chart(fig_bridge, use_container_width=True)

        st.markdown("#### Resumen del período mostrado")
        bc_s1, bc_s2, bc_s3, bc_s4 = st.columns(4)
        bc_s1.metric("Luz mínima", f"{_df_bridge['luz_disponible_m'].min():.2f} m")
        bc_s2.metric("Luz máxima", f"{_df_bridge['luz_disponible_m'].max():.2f} m")
        bc_s3.metric("Luz promedio", f"{_df_bridge['luz_disponible_m'].mean():.2f} m")
        horas_peligro = (_df_bridge["luz_disponible_m"] < air_draft).sum()
        bc_s4.metric("Horas con luz insuficiente", f"{horas_peligro}")

# ═══════════════════════════════════════════════════════════════
# TAB — COMPARAR (si hay 2+ estaciones)
# ═══════════════════════════════════════════════════════════════
idx_tab = 14
if len(datasets) > 1:
    with tabs[idx_tab]:
        st.subheader("Comparación entre estaciones")
        fig_cmp = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08,
            subplot_titles=[NOMBRES.get(e,e) for e in estaciones])
        for i, est in enumerate(estaciones):
            de = datasets[est]
            me = (de["fecha"].dt.date >= f_ini) & (de["fecha"].dt.date <= f_fin)
            def_ = de[me]
            dp_, _ = resam(def_, col, limite=10000)
            c = COLORES.get(est, COLORES["LMB"])
            fig_cmp.add_trace(go.Scattergl(x=dp_["fecha"], y=dp_[col],
                mode="lines", name=NOMBRES.get(est,est),
                line=dict(color=c["linea"], width=1),
                fill="tozeroy", fillcolor=c["fill"]), row=i+1, col=1)
            fig_cmp.update_yaxes(title_text=f"Nivel ({u})", row=i+1, col=1)
        fig_cmp.update_layout(template="plotly_white", height=700,
            hovermode="x unified", margin=dict(l=50,r=20,t=40,b=50))
        st.plotly_chart(fig_cmp, use_container_width=True)

        st.subheader("Resumen comparativo")
        filas = []
        for est in estaciones:
            de = datasets[est]
            me = (de["fecha"].dt.date >= f_ini) & (de["fecha"].dt.date <= f_fin)
            def_ = de[me]
            pe, be = encontrar_picos(def_, col, prom_d, 20)
            filas.append({"Estación": NOMBRES.get(est,est), "Registros": f"{len(def_):,}",
                f"Máx ({u})": f"{def_[col].max():.2f}", f"Mín ({u})": f"{def_[col].min():.2f}",
                f"MSL ({u})": f"{def_[col].mean():.2f}",
                f"MHW ({u})": f"{pe[col].mean():.2f}" if len(pe) else "N/A",
                f"MLW ({u})": f"{be[col].mean():.2f}" if len(be) else "N/A",
                f"Rango ({u})": f"{def_[col].max()-def_[col].min():.2f}"})
        st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)
    idx_tab += 1


# ═══════════════════════════════════════════════════════════════
# TAB — EXPORTAR
# ═══════════════════════════════════════════════════════════════
with tabs[idx_tab]:
    st.subheader("Exportar")
    e1, e2, e3 = st.columns(3)
    with e1:
        st.markdown("#### Datos filtrados")
        st.download_button("⬇️ CSV datos", df.to_csv(index=False).encode("utf-8"),
            f"mareas_{est_activa}_{f_ini}_{f_fin}.csv", "text/csv")
    with e2:
        st.markdown("#### Pleamares/Bajamares")
        ev_exp = pd.concat([plea_all, baja_all]).sort_values("fecha").reset_index(drop=True)
        st.download_button("⬇️ CSV eventos", ev_exp.to_csv(index=False).encode("utf-8"),
            f"eventos_{est_activa}_{f_ini}_{f_fin}.csv", "text/csv")
    with e3:
        st.markdown("#### Planos de referencia")
        d_exp = pd.DataFrame([{"Sigla":k, "Nombre":v["nombre"],
            f"Nivel ({u})": round(v["valor"],3)} for k,v in datums.items() if not np.isnan(v["valor"])])
        st.download_button("⬇️ CSV datums", d_exp.to_csv(index=False).encode("utf-8"),
            f"datums_{est_activa}_{f_ini}_{f_fin}.csv", "text/csv")

    st.markdown("---")
    st.dataframe(df.head(200), use_container_width=True, height=300)


# FOOTER
st.markdown("---")
st.markdown(
    "<div style='text-align:center; color:#aab7b8; font-size:0.85rem;'>"
    "🌊 Mareas del Canal de Panamá · HIMH · EIDEMAR<br>"
    "HIMH Sección de Hidrología · EIDEMAR Escuela Internacional de Doctorado de Estudios del Mar<br>"
    "Datos: Autoridad del Canal de Panamá (ACP) · Creador: JFRodriguez<br>"
    "<b>v2.0</b> — Auto-detección de unidades · Predicción astronómica · Ciclo Nodal</div>",
    unsafe_allow_html=True,
)
