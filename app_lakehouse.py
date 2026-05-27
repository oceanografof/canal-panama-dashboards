
import os
import base64
from datetime import timedelta
from io import BytesIO

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

# =========================================================
# CONFIGURACIÓN GENERAL
# =========================================================
st.set_page_config(
    page_title="Lake_House — HIMH Dashboard",
    page_icon="💧",
    layout="wide",
    initial_sidebar_state="expanded",
)

BASE_DIR = os.path.dirname(__file__)
DATA_FILE = os.path.join(BASE_DIR, "LakeHouse_Data.xlsx")
LOGO_FILE = os.path.join(BASE_DIR, "LOGO_HIMH.jpg")

HM3D_TO_M3S = 1_000_000 / 86400
M3S_TO_CFS = 35.3146667

CHART_CONFIG = {
    "displaylogo": False,
    "responsive": True,
    "modeBarButtonsToRemove": ["lasso2d", "select2d"],
}

# Columnas críticas que sostienen los indicadores principales.
CRITICAL_COLS = [
    "actdate", "actgatel", "actmadel", "aportes_netos_chcp_hm3",
    "usos_hm3", "madmwh", "gatmwh", "madhm3", "gathm3",
    "gatlockhm3", "pmlockhm3", "aclockhm3", "ccllockhm3",
]

NEEDED_COLS = [
    "actgatel", "actmadel", "madmwh", "gatmwh", "madhm3", "gathm3",
    "munic_mad_hm3", "munic_gat_hm3", "gatlockhm3", "pmlockhm3",
    "aclockhm3", "ccllockhm3", "aportes_netos_chcp_hm3", "usos_hm3",
    "tempereture_ama", "tempereture_lmb", "channel_salinity",
    "agua_almacenada_gat_porc", "agua_almacenada_ala_porc",
    "agua_almacenada_ala_gat_porc", "madmcf", "gatmcf",
    "tofmd", "tofgl", "gatspill", "madspill", "TOTAL TODOS LOS ESCLUSAJES HEC",
    "numlockgat", "numlockpm", "numlockac", "numlockccl",
    "TOTAL PNX", "TOTAL NPX", "saving_water_ac_hm3",
    "saving_water_cc_hm3", "total_saving_water_neo_hm3",
    "capgat_hm3", "capmad_hm3", "diffgat", "diffmad",
    "aportes_netos_ala_hm3", "aportes_netos_gat_hm3",
    "evap_gatun_mm", "evap_alaj_mm", "vol_evap_gat_hm3", "vol_evap_ala_hm3",
    "munic_mad", "munic_gat", "leak_mad", "leak_gat",
    "gatlockHEC", "pmlockHEC", "aclockHEC", "ccllockHEC"
]


# =========================================================
# ESTILOS
# =========================================================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

html, body, [class*="css"]  {
    font-family: 'Inter', sans-serif;
}

.block-container{
    padding-top: .8rem;
    padding-bottom: .6rem;
}

[data-testid="stSidebar"]{
    background:#0a1628;
}
[data-testid="stSidebar"] *{
    color:#d9e6f2 !important;
}
[data-testid="stSidebar"] .stSelectbox label,
[data-testid="stSidebar"] .stSlider label,
[data-testid="stSidebar"] .stDateInput label{
    color:#7ec8e3 !important;
    font-weight:600;
}

.mc{
    background:linear-gradient(135deg,#0f2439,#1a3a5c);
    border:1px solid #1e4d7a;
    border-radius:14px;
    padding:14px 16px;
    text-align:center;
    box-shadow:0 4px 14px rgba(0,0,0,.22);
    min-height:112px;
}
.mc .lb{
    color:#7ec8e3;
    font-size:.72rem;
    font-weight:700;
    text-transform:uppercase;
    letter-spacing:.45px;
    margin-bottom:4px;
}
.mc .vl{
    color:#ffffff;
    font-size:1.48rem;
    font-weight:800;
    line-height:1.15;
}
.mc .sub{
    color:#c8d6e5;
    font-size:.77rem;
    font-weight:500;
    margin-top:4px;
}
.mc .dl{
    font-size:.77rem;
    font-weight:600;
    margin-top:5px;
}
.du{color:#2ecc71}
.dd{color:#ff7675}
.dn{color:#b2bec3}

.st{
    color:#154360;
    font-size:1.08rem;
    font-weight:800;
    border-bottom:3px solid #2980b9;
    padding-bottom:6px;
    margin:18px 0 10px;
}
.hdr{
    display:flex;
    align-items:center;
    gap:16px;
    padding:8px 0 6px;
    border-bottom:3px solid #2980b9;
    margin-bottom:12px;
}
.hdr img{
    height:68px;
    width:auto;
}
.hdr .tb h1{
    margin:0;
    color:#0a3d62;
    font-size:1.55rem;
    font-weight:800;
}
.hdr .tb p{
    margin:0;
    color:#5a8ca8;
    font-size:.84rem;
}
.note-box{
    background:#f7fbff;
    border:1px solid #d6eaf8;
    border-radius:12px;
    padding:10px 14px;
    color:#2c3e50;
    font-size:.88rem;
}
.footer{
    text-align:center;
    color:#7f8c8d;
    font-size:.80rem;
    padding:4px 0 12px;
}


[data-testid="stMetric"]{
    background:#ffffff;
    border:1px solid #e6eef6;
    border-radius:14px;
    padding:10px 12px;
    box-shadow:0 2px 10px rgba(15,35,65,.06);
}
.stPlotlyChart{
    background:#ffffff;
    border:1px solid #e7eef7;
    border-radius:14px;
    padding:6px;
    box-shadow:0 2px 10px rgba(15,35,65,.05);
}
button[data-baseweb="tab"]{
    font-size:.92rem;
    font-weight:700;
}
.small-muted{
    color:#607d8b;
    font-size:.82rem;
}

</style>
""", unsafe_allow_html=True)


# =========================================================
# FUNCIONES AUXILIARES
# =========================================================
def hm3d_to_m3s(series):
    return series * HM3D_TO_M3S

def hm3d_to_cfs(series):
    return hm3d_to_m3s(series) * M3S_TO_CFS

def mwhd_to_mw(series):
    return series / 24

def safe_numeric(df, col):
    if col not in df.columns:
        df[col] = np.nan
    df[col] = pd.to_numeric(df[col], errors="coerce")
    return df

@st.cache_data(show_spinner="Cargando y validando LakeHouse...")
def load_data(data_bytes=None, uploaded_name=None):
    """Carga, normaliza y valida el archivo LakeHouse_Data.

    El app puede trabajar con el archivo local LakeHouse_Data.xlsx o con un
    archivo cargado manualmente desde la barra lateral. Si faltan columnas,
    se crean como NaN para evitar que el app se caiga, pero se reportan en
    el panel de calidad de datos.
    """
    quality = {
        "source": "",
        "error": None,
        "rows_raw": 0,
        "rows_final": 0,
        "columns": 0,
        "date_min": None,
        "date_max": None,
        "invalid_dates": 0,
        "duplicate_dates": 0,
        "missing_cols": [],
        "critical_missing": [],
    }

    try:
        if data_bytes is not None:
            quality["source"] = f"Archivo cargado: {uploaded_name or 'LakeHouse cargado'}"
            d = pd.read_excel(BytesIO(data_bytes))
        else:
            quality["source"] = f"Archivo local: {os.path.basename(DATA_FILE)}"
            if not os.path.exists(DATA_FILE):
                quality["error"] = f"No se encontró {DATA_FILE}. Cargue el Excel desde la barra lateral o coloque LakeHouse_Data.xlsx junto al app."
                return pd.DataFrame(), quality
            d = pd.read_excel(DATA_FILE)
    except Exception as exc:
        quality["error"] = f"No fue posible leer el Excel: {exc}"
        return pd.DataFrame(), quality

    if d.empty:
        quality["error"] = "El archivo cargado no contiene registros."
        return pd.DataFrame(), quality

    d.columns = [str(c).strip() for c in d.columns]
    quality["rows_raw"] = len(d)
    quality["columns"] = len(d.columns)

    # Alias tolerantes para archivos con nombres levemente diferentes.
    aliases = {
        "temperature_ama": "tempereture_ama",
        "temperatura_ama": "tempereture_ama",
        "temp_ama": "tempereture_ama",
        "temperature_lmb": "tempereture_lmb",
        "temperatura_lmb": "tempereture_lmb",
        "temp_lmb": "tempereture_lmb",
        "salinidad_canal": "channel_salinity",
        "fecha": "actdate",
        "date": "actdate",
        "datetime": "actdate",
    }
    lower_to_original = {c.lower(): c for c in d.columns}
    for alias, target in aliases.items():
        if target not in d.columns and alias in lower_to_original:
            d[target] = d[lower_to_original[alias]]

    present_before_fill = set(d.columns)
    quality["missing_cols"] = [c for c in NEEDED_COLS if c not in present_before_fill]
    quality["critical_missing"] = [c for c in CRITICAL_COLS if c not in present_before_fill]

    if "actdate" not in d.columns:
        quality["error"] = "No se encontró la columna de fecha 'actdate'. Revise el nombre de la columna en el Excel."
        return pd.DataFrame(), quality

    d["actdate"] = pd.to_datetime(d["actdate"], errors="coerce")
    quality["invalid_dates"] = int(d["actdate"].isna().sum())
    d = d.dropna(subset=["actdate"])

    if d.empty:
        quality["error"] = "No quedaron registros válidos después de interpretar la columna actdate como fecha."
        return pd.DataFrame(), quality

    d = d.sort_values("actdate").reset_index(drop=True)
    quality["duplicate_dates"] = int(d.duplicated(subset=["actdate"]).sum())
    if quality["duplicate_dates"]:
        d = d.drop_duplicates(subset=["actdate"], keep="last").reset_index(drop=True)

    skip = [
        "actdate", "cocoli_water_usage_comment", "hydrology_comments",
        "Column1", "Column2", "Column3", "Column4", "Column5", "Column6",
        "Column7", "Column8", "Column9", "Column10", "Column11", "Column12"
    ]

    for c in d.columns:
        if c not in skip:
            d[c] = pd.to_numeric(d[c], errors="coerce")

    for col in NEEDED_COLS:
        safe_numeric(d, col)

    # Derivadas operativas
    d["hidro_total_mwh"] = d[["madmwh", "gatmwh"]].fillna(0).sum(axis=1)
    d["mad_mw"] = mwhd_to_mw(d["madmwh"])
    d["gat_mw"] = mwhd_to_mw(d["gatmwh"])
    d["hidro_total_mw"] = mwhd_to_mw(d["hidro_total_mwh"])

    d["hidro_agua_total_hm3"] = d[["madhm3", "gathm3"]].fillna(0).sum(axis=1)
    d["municipal_total_hm3"] = d[["munic_mad_hm3", "munic_gat_hm3"]].fillna(0).sum(axis=1)
    d["locks_total_hm3"] = d[["gatlockhm3", "pmlockhm3", "aclockhm3", "ccllockhm3"]].fillna(0).sum(axis=1)

    for base in ["usos_hm3", "aportes_netos_chcp_hm3", "hidro_agua_total_hm3", "municipal_total_hm3", "locks_total_hm3"]:
        d[f"{base}_m3s"] = hm3d_to_m3s(d[base])
        d[f"{base}_cfs"] = hm3d_to_cfs(d[base])

    d["mad_hm3_m3s"] = hm3d_to_m3s(d["madhm3"])
    d["mad_hm3_cfs"] = hm3d_to_cfs(d["madhm3"])
    d["gat_hm3_m3s"] = hm3d_to_m3s(d["gathm3"])
    d["gat_hm3_cfs"] = hm3d_to_cfs(d["gathm3"])

    d["locks_per_day_total"] = d[["numlockgat", "numlockpm", "numlockac", "numlockccl"]].fillna(0).sum(axis=1)
    d["consumo_por_esclusaje_hm3"] = d["locks_total_hm3"] / d["locks_per_day_total"].replace(0, np.nan)

    d["ef_madden_mwh_hm3"] = d["madmwh"] / d["madhm3"].replace(0, np.nan)
    d["ef_gatun_mwh_hm3"] = d["gatmwh"] / d["gathm3"].replace(0, np.nan)
    d["ef_total_mwh_hm3"] = d["hidro_total_mwh"] / d["hidro_agua_total_hm3"].replace(0, np.nan)

    quality["rows_final"] = len(d)
    quality["date_min"] = d["actdate"].min()
    quality["date_max"] = d["actdate"].max()

    return d, quality

def get_logo_b64(path):
    if os.path.exists(path):
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    return None

def base_layout(title="", yaxis_title=None, height=390, showlegend=True, **kwargs):
    layout = dict(
        template="plotly_white",
        margin=dict(l=50, r=25, t=68, b=48),
        height=height,
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        font=dict(family="Inter, sans-serif", size=13, color="#243447"),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
            bgcolor="rgba(255,255,255,.85)", bordercolor="#e6eef6", borderwidth=1,
        ),
        hovermode="x unified",
        title=dict(text=title, font=dict(size=17, color="#12324a")),
        showlegend=showlegend,
        xaxis=dict(showgrid=True, gridcolor="#edf2f7", zeroline=False, tickfont=dict(size=12)),
        yaxis=dict(showgrid=True, gridcolor="#edf2f7", zeroline=False, tickfont=dict(size=12)),
    )
    if yaxis_title is not None:
        layout["yaxis_title"] = yaxis_title
    layout.update(kwargs)
    return layout

def mcard(label, value, delta=None, fmt="{:.2f}", unit="", invert=False, subtitle=""):
    val = "N/D" if pd.isna(value) else f"{fmt.format(value)}{unit}"
    dh = ""
    if delta is not None and pd.notna(delta):
        up_is_good = (delta > 0 and not invert) or (delta < 0 and invert)
        down_is_good = (delta < 0 and not invert) or (delta > 0 and invert)
        cls = "du" if up_is_good else "dd" if down_is_good else "dn"
        arrow = "▲" if delta > 0 else "▼" if delta < 0 else "●"
        dh = f'<div class="dl {cls}">{arrow} {fmt.format(abs(delta))}{unit}</div>'
    sub = f'<div class="sub">{subtitle}</div>' if subtitle else ""
    return f'<div class="mc"><div class="lb">{label}</div><div class="vl">{val}</div>{sub}{dh}</div>'

def gl(data, col):
    if col not in data.columns:
        return None
    v = data[col].dropna()
    return v.iloc[-1] if len(v) else None

def gd(data, col):
    if col not in data.columns:
        return None
    v = data[col].dropna()
    return v.iloc[-1] - v.iloc[-2] if len(v) >= 2 else None

def ga(data, col, rolling_window):
    if col not in data.columns:
        return None
    v = data[col].dropna()
    if len(v) >= rolling_window:
        return v.iloc[-rolling_window:].mean()
    return v.mean() if len(v) else None

def roll(data, col, rolling_window):
    if col not in data.columns:
        return pd.DataFrame({"actdate": data["actdate"], col: np.nan})
    return data.set_index("actdate")[col].rolling(f"{rolling_window}D").mean().reset_index()

def add_cmp(fig, df_full, col, name, compare_year, last_year):
    if compare_year is None or col not in df_full.columns:
        return
    cmp_df = df_full[df_full["actdate"].dt.year == compare_year].copy()
    if cmp_df.empty:
        return
    cmp_df["actdate"] = cmp_df["actdate"] + pd.DateOffset(years=last_year - compare_year)
    fig.add_trace(
        go.Scatter(
            x=cmp_df["actdate"],
            y=cmp_df[col],
            name=f"{name} {compare_year}",
            line=dict(color="#95a5a6", width=1.2, dash="dot")
        )
    )

def metric_row(cols, cards):
    st_cols = st.columns(cols, gap="small")
    for box, html in zip(st_cols, cards):
        with box:
            st.markdown(html, unsafe_allow_html=True)


# =========================================================
# FUENTE DE DATOS
# =========================================================
with st.sidebar:
    st.markdown("### 📂 Fuente de datos")
    uploaded_data = st.file_uploader(
        "Cargar LakeHouse_Data.xlsx",
        type=["xlsx", "xls"],
        help="Opcional. Si no carga un archivo, el app usará LakeHouse_Data.xlsx en la carpeta del script.",
    )
    if uploaded_data is None:
        st.caption("Usando archivo local por defecto, si existe.")
    else:
        st.success(f"Archivo cargado: {uploaded_data.name}")

# =========================================================
# CARGA DE DATOS
# =========================================================
uploaded_bytes = uploaded_data.getvalue() if uploaded_data is not None else None
df, quality_info = load_data(uploaded_bytes, uploaded_data.name if uploaded_data is not None else None)
logo_b64 = get_logo_b64(LOGO_FILE)

if quality_info.get("error"):
    st.error(quality_info["error"])
    st.info("Verifique que el archivo tenga la columna `actdate` y las columnas operativas del LakeHouse.")
    st.stop()

if df.empty:
    st.error("No hay datos disponibles para mostrar en el dashboard.")
    st.stop()

last_date = df["actdate"].max()

# =========================================================
# ENCABEZADO
# =========================================================
if logo_b64:
    st.markdown(f"""
    <div class="hdr">
        <img src="data:image/jpeg;base64,{logo_b64}"/>
        <div class="tb">
            <h1>Lake_House — Dashboard Hidrológico</h1>
            <p>Sección de Hidrología · HIMH | Última fecha: {last_date.strftime('%d %b %Y')} | Fuente: {quality_info.get("source", "LakeHouse")} | Creado por JFRodriguez</p>
        </div>
    </div>
    """, unsafe_allow_html=True)
else:
    st.markdown(f"""
    <div class="hdr">
        <div class="tb">
            <h1>Lake_House — Dashboard Hidrológico</h1>
            <p>Sección de Hidrología · HIMH | Última fecha: {last_date.strftime('%d %b %Y')} | Fuente: {quality_info.get("source", "LakeHouse")} | Creado por JFRodriguez</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

# =========================================================
# SIDEBAR
# =========================================================
with st.sidebar:
    if os.path.exists(LOGO_FILE):
        st.image(LOGO_FILE, width=110)
    st.markdown("### ⚙️ Configuración")
    st.caption("Creado por: JFRodriguez")

    rolling_window = st.slider("Ventana promedio móvil (días)", 3, 30, 7, 1)

    st.markdown("---")
    date_opt = st.selectbox(
        "📅 Período",
        ["Último mes", "Últimos 3 meses", "Últimos 6 meses", "Último año", "Últimos 2 años", "Todo", "Personalizado"]
    )

    rmap = {
        "Último mes": 30,
        "Últimos 3 meses": 90,
        "Últimos 6 meses": 180,
        "Último año": 365,
        "Últimos 2 años": 730,
    }

    min_date = df["actdate"].min()
    max_date = last_date
    if date_opt == "Personalizado":
        default_start = max(min_date, last_date - timedelta(days=90))
        custom_range = st.date_input(
            "Rango personalizado",
            value=(default_start.date(), max_date.date()),
            min_value=min_date.date(),
            max_value=max_date.date(),
        )
        if isinstance(custom_range, tuple) and len(custom_range) == 2:
            sd = pd.Timestamp(custom_range[0])
            ed = pd.Timestamp(custom_range[1])
        else:
            sd = default_start
            ed = max_date
            st.info("Seleccione fecha inicial y fecha final para aplicar el rango personalizado.")
    elif date_opt == "Todo":
        sd = min_date
        ed = max_date
    else:
        sd = max(min_date, last_date - timedelta(days=rmap[date_opt]))
        ed = max_date

    if sd > ed:
        st.warning("La fecha inicial no puede ser mayor que la fecha final.")
        st.stop()

    dff = df[(df["actdate"] >= sd) & (df["actdate"] <= ed)].copy()

    if dff.empty:
        st.warning("El período seleccionado no contiene registros. Cambie el rango de fechas.")
        st.stop()

    st.markdown("---")
    compare_year = st.selectbox(
        "📊 Comparar con año",
        [None] + list(range(last_date.year - 1, 1999, -1)),
        format_func=lambda x: "Ninguno" if x is None else str(x)
    )

    st.markdown("---")
    st.caption(f"**Registros filtrados:** {len(dff):,} · **Prom. móvil:** {rolling_window}d")
    st.caption(f"**Rango:** {sd.strftime('%Y-%m-%d')} a {ed.strftime('%Y-%m-%d')}")
    if quality_info.get("critical_missing"):
        st.warning("Faltan columnas críticas. Revise la pestaña Datos.")

# =========================================================
# TABS
# =========================================================
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9 = st.tabs([
    "📊 Resumen",
    "🌊 Niveles y Almacenamiento",
    "⚖️ Balance Hídrico",
    "⚡ Hidrogeneración",
    "🚰 Usos y Consumos",
    "🚢 Esclusajes",
    "🔄 Conversiones Operativas",
    "🌡️ Temperatura y Salinidad",
    "📋 Datos"
])

# =========================================================
# TAB 1: RESUMEN
# =========================================================
with tab1:
    st.markdown('<div class="st">Indicadores Principales</div>', unsafe_allow_html=True)

    cards_1 = [
        mcard("Nivel Gatún", gl(dff, "actgatel"), gd(dff, "actgatel"), unit=" pies"),
        mcard("Nivel Alhajuela", gl(dff, "actmadel"), gd(dff, "actmadel"), unit=" pies"),
        mcard("Aportes Netos", gl(dff, "aportes_netos_chcp_hm3"), gd(dff, "aportes_netos_chcp_hm3"), unit=" hm³"),
        mcard("Usos Totales", gl(dff, "usos_hm3"), gd(dff, "usos_hm3"), unit=" hm³", invert=True),
        mcard("Hidrogeneración Total", gl(dff, "hidro_total_mw"), gd(dff, "hidro_total_mw"), fmt="{:.1f}", unit=" MW", subtitle="Promedio diario"),
        mcard("HEC Total", gl(dff, "TOTAL TODOS LOS ESCLUSAJES HEC"), gd(dff, "TOTAL TODOS LOS ESCLUSAJES HEC"), fmt="{:.1f}")
    ]
    metric_row(6, cards_1)

    cards_2 = [
        mcard("Almacenamiento Gatún", gl(dff, "agua_almacenada_gat_porc"), gd(dff, "agua_almacenada_gat_porc"), unit="%"),
        mcard("Almacenamiento Alhajuela", gl(dff, "agua_almacenada_ala_porc"), gd(dff, "agua_almacenada_ala_porc"), unit="%"),
        mcard("Usos Totales", gl(dff, "usos_hm3_m3s"), gd(dff, "usos_hm3_m3s"), fmt="{:.1f}", unit=" m³/s", subtitle="Equivalente de caudal"),
        mcard("Usos Totales", gl(dff, "usos_hm3_cfs"), gd(dff, "usos_hm3_cfs"), fmt="{:.0f}", unit=" pies³/s", subtitle="Equivalente de caudal"),
        mcard("Madden", gl(dff, "mad_mw"), gd(dff, "mad_mw"), fmt="{:.1f}", unit=" MW"),
        mcard("Gatún", gl(dff, "gat_mw"), gd(dff, "gat_mw"), fmt="{:.1f}", unit=" MW")
    ]
    metric_row(6, cards_2)

    st.markdown('<div class="st">Vista Rápida — Niveles</div>', unsafe_allow_html=True)
    ca, cb = st.columns(2)

    with ca:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=dff["actdate"], y=dff["actgatel"], name="Diario",
            line=dict(color="#2980b9", width=1), opacity=.35
        ))
        r = roll(dff, "actgatel", rolling_window)
        fig.add_trace(go.Scatter(
            x=r["actdate"], y=r["actgatel"], name=f"Prom. {rolling_window}d",
            line=dict(color="#e74c3c", width=2.6)
        ))
        add_cmp(fig, df, "actgatel", "Gatún", compare_year, last_date.year)
        fig.update_layout(**base_layout(title="Lago Gatún (pies)", yaxis_title="pies"))
        st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

    with cb:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=dff["actdate"], y=dff["actmadel"], name="Diario",
            line=dict(color="#27ae60", width=1), opacity=.35
        ))
        r = roll(dff, "actmadel", rolling_window)
        fig.add_trace(go.Scatter(
            x=r["actdate"], y=r["actmadel"], name=f"Prom. {rolling_window}d",
            line=dict(color="#e74c3c", width=2.6)
        ))
        add_cmp(fig, df, "actmadel", "Alhajuela", compare_year, last_date.year)
        fig.update_layout(**base_layout(title="Lago Alhajuela (pies)", yaxis_title="pies"))
        st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

    st.markdown('<div class="st">Balance y Potencia</div>', unsafe_allow_html=True)
    ca, cb = st.columns(2)

    with ca:
        fig = go.Figure()
        ra = roll(dff, "aportes_netos_chcp_hm3", rolling_window)
        ru = roll(dff, "usos_hm3", rolling_window)
        fig.add_trace(go.Scatter(
            x=ra["actdate"], y=ra["aportes_netos_chcp_hm3"], name="Aportes",
            line=dict(color="#2ecc71", width=2.4), fill="tozeroy",
            fillcolor="rgba(46,204,113,.10)"
        ))
        fig.add_trace(go.Scatter(
            x=ru["actdate"], y=ru["usos_hm3"], name="Usos",
            line=dict(color="#e74c3c", width=2.4), fill="tozeroy",
            fillcolor="rgba(231,76,60,.08)"
        ))
        fig.update_layout(**base_layout(title=f"Aportes vs Usos (Prom. {rolling_window}d)", yaxis_title="hm³/día"))
        st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

    with cb:
        fig = go.Figure()
        rm = roll(dff, "mad_mw", rolling_window)
        rg = roll(dff, "gat_mw", rolling_window)
        rt = roll(dff, "hidro_total_mw", rolling_window)
        fig.add_trace(go.Scatter(x=rm["actdate"], y=rm["mad_mw"], name="Madden", line=dict(color="#f39c12", width=2.2)))
        fig.add_trace(go.Scatter(x=rg["actdate"], y=rg["gat_mw"], name="Gatún", line=dict(color="#3498db", width=2.2)))
        fig.add_trace(go.Scatter(x=rt["actdate"], y=rt["hidro_total_mw"], name="Total", line=dict(color="#2c3e50", width=2.8, dash="dash")))
        fig.update_layout(**base_layout(title=f"Hidrogeneración Media (Prom. {rolling_window}d)", yaxis_title="MW"))
        st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

# =========================================================
# TAB 2: NIVELES Y ALMACENAMIENTO
# =========================================================
with tab2:
    st.markdown('<div class="st">Niveles de Lagos</div>', unsafe_allow_html=True)
    ca, cb = st.columns(2)

    with ca:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=dff["actdate"], y=dff["actgatel"], name="Diario", line=dict(color="#2980b9", width=1), opacity=.35))
        r = roll(dff, "actgatel", rolling_window)
        fig.add_trace(go.Scatter(x=r["actdate"], y=r["actgatel"], name=f"Prom. {rolling_window}d", line=dict(color="#e74c3c", width=2.5)))
        add_cmp(fig, df, "actgatel", "Gatún", compare_year, last_date.year)
        fig.update_layout(**base_layout(title="Lago Gatún (pies)", yaxis_title="pies"))
        st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

    with cb:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=dff["actdate"], y=dff["actmadel"], name="Diario", line=dict(color="#27ae60", width=1), opacity=.35))
        r = roll(dff, "actmadel", rolling_window)
        fig.add_trace(go.Scatter(x=r["actdate"], y=r["actmadel"], name=f"Prom. {rolling_window}d", line=dict(color="#e74c3c", width=2.5)))
        add_cmp(fig, df, "actmadel", "Alhajuela", compare_year, last_date.year)
        fig.update_layout(**base_layout(title="Lago Alhajuela (pies)", yaxis_title="pies"))
        st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

    st.markdown('<div class="st">Almacenamiento</div>', unsafe_allow_html=True)
    ca, cb = st.columns(2)

    with ca:
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(go.Scatter(
            x=dff["actdate"], y=dff["capgat_hm3"], name="Vol. Gatún",
            fill="tozeroy", line=dict(color="#3498db", width=1.2), fillcolor="rgba(52,152,219,.12)"
        ), secondary_y=False)
        fig.add_trace(go.Scatter(
            x=dff["actdate"], y=dff["capmad_hm3"], name="Vol. Alhajuela",
            fill="tozeroy", line=dict(color="#2ecc71", width=1.2), fillcolor="rgba(46,204,113,.12)"
        ), secondary_y=False)
        fig.add_trace(go.Scatter(
            x=dff["actdate"], y=dff["agua_almacenada_ala_gat_porc"], name="% combinado",
            line=dict(color="#e74c3c", width=2.5)
        ), secondary_y=True)
        fig.update_layout(**base_layout(title="Volúmenes Almacenados"))
        fig.update_yaxes(title_text="hm³", secondary_y=False)
        fig.update_yaxes(title_text="%", secondary_y=True)
        st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

    with cb:
        fig = go.Figure()
        rg = roll(dff, "agua_almacenada_gat_porc", rolling_window)
        ra = roll(dff, "agua_almacenada_ala_porc", rolling_window)
        rc = roll(dff, "agua_almacenada_ala_gat_porc", rolling_window)
        fig.add_trace(go.Scatter(x=rg["actdate"], y=rg["agua_almacenada_gat_porc"], name="Gatún %", line=dict(color="#3498db", width=2.4)))
        fig.add_trace(go.Scatter(x=ra["actdate"], y=ra["agua_almacenada_ala_porc"], name="Alhajuela %", line=dict(color="#2ecc71", width=2.4)))
        fig.add_trace(go.Scatter(x=rc["actdate"], y=rc["agua_almacenada_ala_gat_porc"], name="Combinado %", line=dict(color="#2c3e50", width=2.8, dash="dash")))
        fig.add_hline(y=80, line_dash="dash", line_color="#e67e22", annotation_text="80%")
        fig.add_hline(y=50, line_dash="dash", line_color="#e74c3c", annotation_text="50% alerta")
        fig.update_layout(**base_layout(title=f"Porcentaje de Almacenamiento (Prom. {rolling_window}d)", yaxis_title="%", height=380))
        st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

    st.markdown('<div class="st">Variación Diaria del Volumen</div>', unsafe_allow_html=True)
    fig = go.Figure()
    rdg = roll(dff, "diffgat", rolling_window)
    rdm = roll(dff, "diffmad", rolling_window)
    fig.add_trace(go.Bar(x=rdg["actdate"], y=rdg["diffgat"], name="Δ Gatún", marker_color="#3498db", opacity=.75))
    fig.add_trace(go.Bar(x=rdm["actdate"], y=rdm["diffmad"], name="Δ Alhajuela", marker_color="#2ecc71", opacity=.75))
    fig.add_hline(y=0, line_color="#2c3e50", line_width=1)
    fig.update_layout(**base_layout(title=f"Cambio Diario de Volumen (Prom. {rolling_window}d)", yaxis_title="Δ volumen", height=390, barmode="group"))
    st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

# =========================================================
# TAB 3: BALANCE HÍDRICO
# =========================================================
with tab3:
    st.markdown('<div class="st">Aportes Netos por Cuenca</div>', unsafe_allow_html=True)
    ca, cb = st.columns(2)

    with ca:
        fig = go.Figure()
        for col, nm, cl in [
            ("aportes_netos_chcp_hm3", "CHCP Total", "#2980b9"),
            ("aportes_netos_ala_hm3", "Alhajuela", "#27ae60"),
            ("aportes_netos_gat_hm3", "Gatún", "#8e44ad"),
        ]:
            r = roll(dff, col, rolling_window)
            fig.add_trace(go.Scatter(x=r["actdate"], y=r[col], name=nm, line=dict(color=cl, width=2.2)))
        fig.update_layout(**base_layout(title=f"Aportes Netos (Prom. {rolling_window}d)", yaxis_title="hm³/día"))
        st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

    with cb:
        fig = go.Figure()
        ra = roll(dff, "aportes_netos_chcp_hm3_m3s", rolling_window)
        ru = roll(dff, "usos_hm3_m3s", rolling_window)
        fig.add_trace(go.Scatter(x=ra["actdate"], y=ra["aportes_netos_chcp_hm3_m3s"], name="Aportes", line=dict(color="#2ecc71", width=2.4)))
        fig.add_trace(go.Scatter(x=ru["actdate"], y=ru["usos_hm3_m3s"], name="Usos", line=dict(color="#e74c3c", width=2.4)))
        fig.update_layout(**base_layout(title=f"Aportes vs Usos Equivalentes (Prom. {rolling_window}d)", yaxis_title="m³/s"))
        st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

    st.markdown('<div class="st">Balance Neto</div>', unsafe_allow_html=True)
    tmp = dff.copy()
    tmp["balance_hm3"] = tmp["aportes_netos_chcp_hm3"] - tmp["usos_hm3"]
    tmp["balance_m3s"] = hm3d_to_m3s(tmp["balance_hm3"])
    rb = tmp.set_index("actdate")["balance_hm3"].rolling(f"{rolling_window}D").mean().reset_index()
    colors = ["#2ecc71" if pd.notna(v) and v >= 0 else "#e74c3c" for v in rb["balance_hm3"].fillna(0)]

    ca, cb = st.columns(2)
    with ca:
        fig = go.Figure()
        fig.add_trace(go.Bar(x=rb["actdate"], y=rb["balance_hm3"], marker_color=colors, name="Balance"))
        fig.add_hline(y=0, line_color="#2c3e50", line_width=1)
        fig.update_layout(**base_layout(title=f"Balance Neto (Prom. {rolling_window}d)", yaxis_title="hm³/día", height=390, showlegend=False))
        st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

    with cb:
        rb2 = tmp.set_index("actdate")["balance_m3s"].rolling(f"{rolling_window}D").mean().reset_index()
        colors2 = ["#2ecc71" if pd.notna(v) and v >= 0 else "#e74c3c" for v in rb2["balance_m3s"].fillna(0)]
        fig = go.Figure()
        fig.add_trace(go.Bar(x=rb2["actdate"], y=rb2["balance_m3s"], marker_color=colors2, name="Balance"))
        fig.add_hline(y=0, line_color="#2c3e50", line_width=1)
        fig.update_layout(**base_layout(title=f"Balance Neto Equivalente (Prom. {rolling_window}d)", yaxis_title="m³/s", height=390, showlegend=False))
        st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

    st.markdown('<div class="st">Evaporación y Vertidos</div>', unsafe_allow_html=True)
    ca, cb = st.columns(2)

    with ca:
        fig = go.Figure()
        for col, nm, cl in [
            ("evap_gatun_mm", "Evap. Gatún", "#e74c3c"),
            ("evap_alaj_mm", "Evap. Alhajuela", "#f39c12"),
            ("vol_evap_gat_hm3", "Vol. Evap. Gatún", "#c0392b"),
            ("vol_evap_ala_hm3", "Vol. Evap. Alhajuela", "#d35400"),
        ]:
            r = roll(dff, col, rolling_window)
            dash = "dot" if "Vol." in nm else None
            fig.add_trace(go.Scatter(x=r["actdate"], y=r[col], name=nm, line=dict(color=cl, width=2, dash=dash)))
        fig.update_layout(**base_layout(title=f"Evaporación (Prom. {rolling_window}d)", yaxis_title="mm / hm³"))
        st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

    with cb:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=dff["actdate"], y=dff["gatspill"], name="Vertido Gatún", line=dict(color="#3498db", width=2)))
        fig.add_trace(go.Scatter(x=dff["actdate"], y=dff["madspill"], name="Vertido Madden", line=dict(color="#e67e22", width=2)))
        fig.update_layout(**base_layout(title="Vertidos", yaxis_title="MCF"))
        st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

# =========================================================
# TAB 4: HIDROGENERACIÓN
# =========================================================
with tab4:
    st.markdown('<div class="st">Indicadores de Hidrogeneración</div>', unsafe_allow_html=True)

    cards_h = [
        mcard("Madden", gl(dff, "madmwh"), gd(dff, "madmwh"), fmt="{:.0f}", unit=" MWh/d"),
        mcard("Gatún", gl(dff, "gatmwh"), gd(dff, "gatmwh"), fmt="{:.0f}", unit=" MWh/d"),
        mcard("Total", gl(dff, "hidro_total_mwh"), gd(dff, "hidro_total_mwh"), fmt="{:.0f}", unit=" MWh/d"),
        mcard("Madden", gl(dff, "mad_mw"), gd(dff, "mad_mw"), fmt="{:.1f}", unit=" MW"),
        mcard("Gatún", gl(dff, "gat_mw"), gd(dff, "gat_mw"), fmt="{:.1f}", unit=" MW"),
        mcard("Total", gl(dff, "hidro_total_mw"), gd(dff, "hidro_total_mw"), fmt="{:.1f}", unit=" MW")
    ]
    metric_row(6, cards_h)

    st.markdown('<div class="st">Generación y Potencia</div>', unsafe_allow_html=True)
    ca, cb = st.columns(2)

    with ca:
        fig = go.Figure()
        for col, nm, cl in [
            ("madmwh", "Madden", "#f39c12"),
            ("gatmwh", "Gatún", "#3498db"),
            ("hidro_total_mwh", "Total", "#2c3e50"),
        ]:
            r = roll(dff, col, rolling_window)
            dash = "dash" if nm == "Total" else None
            width = 2.8 if nm == "Total" else 2.2
            fig.add_trace(go.Scatter(x=r["actdate"], y=r[col], name=nm, line=dict(color=cl, width=width, dash=dash)))
        fig.update_layout(**base_layout(title=f"Hidrogeneración (Prom. {rolling_window}d)", yaxis_title="MWh/día"))
        st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

    with cb:
        fig = go.Figure()
        for col, nm, cl in [
            ("mad_mw", "Madden", "#f39c12"),
            ("gat_mw", "Gatún", "#3498db"),
            ("hidro_total_mw", "Total", "#2c3e50"),
        ]:
            r = roll(dff, col, rolling_window)
            dash = "dash" if nm == "Total" else None
            width = 2.8 if nm == "Total" else 2.2
            fig.add_trace(go.Scatter(x=r["actdate"], y=r[col], name=nm, line=dict(color=cl, width=width, dash=dash)))
        fig.update_layout(**base_layout(title=f"Potencia Media Equivalente (Prom. {rolling_window}d)", yaxis_title="MW"))
        st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

    st.markdown('<div class="st">Agua para Hidrogeneración</div>', unsafe_allow_html=True)
    ca, cb = st.columns(2)

    with ca:
        fig = go.Figure()
        for col, nm, cl in [
            ("madhm3", "Madden", "#f39c12"),
            ("gathm3", "Gatún", "#3498db"),
            ("hidro_agua_total_hm3", "Total", "#2c3e50"),
        ]:
            r = roll(dff, col, rolling_window)
            dash = "dash" if nm == "Total" else None
            width = 2.8 if nm == "Total" else 2.2
            fig.add_trace(go.Scatter(x=r["actdate"], y=r[col], name=nm, line=dict(color=cl, width=width, dash=dash)))
        fig.update_layout(**base_layout(title=f"Agua Utilizada (Prom. {rolling_window}d)", yaxis_title="hm³/día"))
        st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

    with cb:
        fig = go.Figure()
        for col, nm, cl in [
            ("mad_hm3_m3s", "Madden", "#f39c12"),
            ("gat_hm3_m3s", "Gatún", "#3498db"),
            ("hidro_agua_total_hm3_m3s", "Total", "#2c3e50"),
        ]:
            r = roll(dff, col, rolling_window)
            dash = "dash" if nm == "Total" else None
            width = 2.8 if nm == "Total" else 2.2
            fig.add_trace(go.Scatter(x=r["actdate"], y=r[col], name=nm, line=dict(color=cl, width=width, dash=dash)))
        fig.update_layout(**base_layout(title=f"Agua para Hidrogeneración (Prom. {rolling_window}d)", yaxis_title="m³/s"))
        st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

    st.markdown('<div class="st">Eficiencia Energética del Agua</div>', unsafe_allow_html=True)
    fig = go.Figure()
    for col, nm, cl in [
        ("ef_madden_mwh_hm3", "Madden", "#f39c12"),
        ("ef_gatun_mwh_hm3", "Gatún", "#3498db"),
        ("ef_total_mwh_hm3", "Total", "#2c3e50"),
    ]:
        r = roll(dff, col, rolling_window)
        dash = "dash" if nm == "Total" else None
        fig.add_trace(go.Scatter(x=r["actdate"], y=r[col], name=nm, line=dict(color=cl, width=2.4, dash=dash)))
    fig.update_layout(**base_layout(title=f"MWh por hm³ (Prom. {rolling_window}d)", yaxis_title="MWh/hm³", height=390))
    st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

# =========================================================
# TAB 5: USOS Y CONSUMOS
# =========================================================
with tab5:
    st.markdown('<div class="st">Indicadores de Consumo</div>', unsafe_allow_html=True)

    cards_u = [
        mcard("Usos Totales", gl(dff, "usos_hm3"), gd(dff, "usos_hm3"), unit=" hm³", invert=True),
        mcard("Usos Totales", gl(dff, "usos_hm3_m3s"), gd(dff, "usos_hm3_m3s"), fmt="{:.1f}", unit=" m³/s", invert=True),
        mcard("Usos Totales", gl(dff, "usos_hm3_cfs"), gd(dff, "usos_hm3_cfs"), fmt="{:.0f}", unit=" pies³/s", invert=True),
        mcard("Consumo Esclusajes", gl(dff, "locks_total_hm3"), gd(dff, "locks_total_hm3"), unit=" hm³"),
        mcard("Consumo Municipal", gl(dff, "municipal_total_hm3"), gd(dff, "municipal_total_hm3"), unit=" hm³"),
        mcard("Agua para Hidro", gl(dff, "hidro_agua_total_hm3"), gd(dff, "hidro_agua_total_hm3"), unit=" hm³")
    ]
    metric_row(6, cards_u)

    st.markdown('<div class="st">Composición de Usos</div>', unsafe_allow_html=True)
    usage_items = [
        ("gatlockhm3", "Escl. Gatún", "#3498db"),
        ("pmlockhm3", "Escl. Pedro Miguel", "#9b59b6"),
        ("aclockhm3", "Escl. Agua Clara", "#e67e22"),
        ("ccllockhm3", "Escl. Cocolí", "#1abc9c"),
        ("madhm3", "Hidro Madden", "#f39c12"),
        ("gathm3", "Hidro Gatún", "#2980b9"),
        ("munic_mad_hm3", "Munic. Madden", "#c0392b"),
        ("munic_gat_hm3", "Munic. Gatún", "#e74c3c"),
    ]
    fig = go.Figure()
    for col, nm, cl in usage_items:
        r = roll(dff, col, rolling_window)
        fig.add_trace(go.Scatter(
            x=r["actdate"], y=r[col], name=nm, stackgroup="one",
            line=dict(width=.7, color=cl)
        ))
    ru = roll(dff, "usos_hm3", rolling_window)
    fig.add_trace(go.Scatter(
        x=ru["actdate"], y=ru["usos_hm3"], name="Total Usos",
        line=dict(color="#2c3e50", width=2.6, dash="dash")
    ))
    fig.update_layout(**base_layout(title=f"Usos por Componente (Prom. {rolling_window}d)", yaxis_title="hm³/día", height=430))
    st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

    ca, cb = st.columns(2)

    with ca:
        latest = dff.iloc[-1]
        labels = [nm for _, nm, _ in usage_items]
        vals = [0 if pd.isna(latest.get(col, np.nan)) else latest.get(col, 0) for col, _, _ in usage_items]
        clrs = [cl for _, _, cl in usage_items]
        fig = go.Figure(go.Pie(labels=labels, values=vals, hole=.42, marker_colors=clrs))
        fig.update_layout(**base_layout(title=f"Distribución Actual — {latest['actdate'].strftime('%d %b %Y')}", height=400))
        st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

    with cb:
        avg_vals = [(ga(dff, col, rolling_window) or 0) for col, _, _ in usage_items]
        fig = go.Figure(go.Pie(labels=labels, values=avg_vals, hole=.42, marker_colors=clrs))
        fig.update_layout(**base_layout(title=f"Distribución Promedio {rolling_window} días", height=400))
        st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

    st.markdown('<div class="st">Usos en Caudal Equivalente</div>', unsafe_allow_html=True)
    ca, cb = st.columns(2)

    with ca:
        fig = go.Figure()
        for col, nm, cl in [
            ("locks_total_hm3_m3s", "Esclusajes", "#3498db"),
            ("municipal_total_hm3_m3s", "Municipal", "#e74c3c"),
            ("hidro_agua_total_hm3_m3s", "Hidrogeneración", "#f39c12"),
            ("usos_hm3_m3s", "Usos Totales", "#2c3e50"),
        ]:
            r = roll(dff, col, rolling_window)
            dash = "dash" if "Totales" in nm else None
            width = 2.8 if "Totales" in nm else 2.2
            fig.add_trace(go.Scatter(x=r["actdate"], y=r[col], name=nm, line=dict(color=cl, width=width, dash=dash)))
        fig.update_layout(**base_layout(title=f"Consumos en m³/s (Prom. {rolling_window}d)", yaxis_title="m³/s"))
        st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

    with cb:
        fig = go.Figure()
        for col, nm, cl in [
            ("locks_total_hm3_cfs", "Esclusajes", "#3498db"),
            ("municipal_total_hm3_cfs", "Municipal", "#e74c3c"),
            ("hidro_agua_total_hm3_cfs", "Hidrogeneración", "#f39c12"),
            ("usos_hm3_cfs", "Usos Totales", "#2c3e50"),
        ]:
            r = roll(dff, col, rolling_window)
            dash = "dash" if "Totales" in nm else None
            width = 2.8 if "Totales" in nm else 2.2
            fig.add_trace(go.Scatter(x=r["actdate"], y=r[col], name=nm, line=dict(color=cl, width=width, dash=dash)))
        fig.update_layout(**base_layout(title=f"Consumos en pies³/s (Prom. {rolling_window}d)", yaxis_title="pies³/s"))
        st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

    st.markdown('<div class="st">Fugas y Demanda Municipal</div>', unsafe_allow_html=True)
    ca, cb = st.columns(2)

    with ca:
        fig = go.Figure()
        for col, nm, cl in [("leak_mad", "Fugas Madden", "#c0392b"), ("leak_gat", "Fugas Gatún", "#e74c3c")]:
            r = roll(dff, col, rolling_window)
            fig.add_trace(go.Scatter(x=r["actdate"], y=r[col], name=nm, line=dict(color=cl, width=2.2)))
        fig.update_layout(**base_layout(title=f"Fugas (Prom. {rolling_window}d)", yaxis_title="MCF"))
        st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

    with cb:
        fig = go.Figure()
        for col, nm, cl in [("munic_mad_hm3", "Madden", "#c0392b"), ("munic_gat_hm3", "Gatún", "#e74c3c"), ("municipal_total_hm3", "Total", "#2c3e50")]:
            r = roll(dff, col, rolling_window)
            dash = "dash" if nm == "Total" else None
            fig.add_trace(go.Scatter(x=r["actdate"], y=r[col], name=nm, line=dict(color=cl, width=2.4, dash=dash)))
        fig.update_layout(**base_layout(title=f"Agua Municipal (Prom. {rolling_window}d)", yaxis_title="hm³/día"))
        st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

# =========================================================
# TAB 6: ESCLUSAJES
# =========================================================
with tab6:
    st.markdown('<div class="st">Esclusajes por Complejo</div>', unsafe_allow_html=True)
    cards_e = [
        mcard("Gatún", gl(dff, "numlockgat"), gd(dff, "numlockgat"), fmt="{:.0f}", unit=" /día"),
        mcard("Pedro Miguel", gl(dff, "numlockpm"), gd(dff, "numlockpm"), fmt="{:.0f}", unit=" /día"),
        mcard("Agua Clara", gl(dff, "numlockac"), gd(dff, "numlockac"), fmt="{:.0f}", unit=" /día"),
        mcard("Cocolí", gl(dff, "numlockccl"), gd(dff, "numlockccl"), fmt="{:.0f}", unit=" /día"),
        mcard("Total Esclusajes", gl(dff, "locks_per_day_total"), gd(dff, "locks_per_day_total"), fmt="{:.0f}", unit=" /día"),
        mcard("Consumo/Esclusaje", gl(dff, "consumo_por_esclusaje_hm3"), gd(dff, "consumo_por_esclusaje_hm3"), fmt="{:.3f}", unit=" hm³")
    ]
    metric_row(6, cards_e)

    ca, cb = st.columns(2)

    with ca:
        fig = go.Figure()
        for col, nm, cl in [
            ("numlockgat", "Gatún", "#3498db"),
            ("numlockpm", "Pedro Miguel", "#9b59b6"),
            ("numlockac", "Agua Clara", "#e67e22"),
            ("numlockccl", "Cocolí", "#1abc9c"),
        ]:
            r = roll(dff, col, rolling_window)
            fig.add_trace(go.Scatter(x=r["actdate"], y=r[col], name=nm, line=dict(color=cl, width=2.2)))
        fig.update_layout(**base_layout(title=f"Esclusajes por Día (Prom. {rolling_window}d)", yaxis_title="esclusajes/día"))
        st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

    with cb:
        fig = go.Figure()
        rh = roll(dff, "TOTAL TODOS LOS ESCLUSAJES HEC", rolling_window)
        fig.add_trace(go.Scatter(
            x=rh["actdate"], y=rh["TOTAL TODOS LOS ESCLUSAJES HEC"],
            name="HEC Total", line=dict(color="#2c3e50", width=2.7),
            fill="tozeroy", fillcolor="rgba(44,62,80,.10)"
        ))
        fig.update_layout(**base_layout(title=f"HEC Total (Prom. {rolling_window}d)", yaxis_title="HEC/día"))
        st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

    st.markdown('<div class="st">Panamax y Neopanamax</div>', unsafe_allow_html=True)
    ca, cb = st.columns(2)

    with ca:
        fig = go.Figure()
        rp = roll(dff, "TOTAL PNX", rolling_window)
        rn = roll(dff, "TOTAL NPX", rolling_window)
        fig.add_trace(go.Scatter(x=rp["actdate"], y=rp["TOTAL PNX"], name="Panamax", line=dict(color="#2980b9", width=2.4)))
        fig.add_trace(go.Scatter(x=rn["actdate"], y=rn["TOTAL NPX"], name="Neopanamax", line=dict(color="#e67e22", width=2.4)))
        fig.update_layout(**base_layout(title=f"PNX vs NPX (Prom. {rolling_window}d)", yaxis_title="coef. HEC"))
        st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

    with cb:
        fig = go.Figure()
        for col, nm, cl in [
            ("gatlockHEC", "Gatún", "#3498db"),
            ("pmlockHEC", "Pedro Miguel", "#9b59b6"),
            ("aclockHEC", "Agua Clara", "#e67e22"),
            ("ccllockHEC", "Cocolí", "#1abc9c"),
        ]:
            r = roll(dff, col, rolling_window)
            fig.add_trace(go.Scatter(x=r["actdate"], y=r[col], name=nm, line=dict(color=cl, width=2.2)))
        fig.update_layout(**base_layout(title=f"HEC por Esclusa (Prom. {rolling_window}d)", yaxis_title="HEC"))
        st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

    st.markdown('<div class="st">Ahorro de Agua Neo</div>', unsafe_allow_html=True)
    ca, cb = st.columns(2)

    with ca:
        fig = go.Figure()
        for col, nm, cl in [
            ("saving_water_ac_hm3", "Agua Clara", "#3498db"),
            ("saving_water_cc_hm3", "Cocolí", "#2ecc71"),
        ]:
            r = roll(dff, col, rolling_window)
            fig.add_trace(go.Scatter(x=r["actdate"], y=r[col], name=nm, line=dict(color=cl, width=2.2)))
        fig.update_layout(**base_layout(title=f"Ahorro por Complejo (Prom. {rolling_window}d)", yaxis_title="hm³/día"))
        st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

    with cb:
        fig = go.Figure()
        r = roll(dff, "total_saving_water_neo_hm3", rolling_window)
        fig.add_trace(go.Scatter(
            x=r["actdate"], y=r["total_saving_water_neo_hm3"], name="Ahorro Total Neo",
            line=dict(color="#16a085", width=2.7), fill="tozeroy",
            fillcolor="rgba(22,160,133,.12)"
        ))
        fig.update_layout(**base_layout(title=f"Ahorro Total Neo (Prom. {rolling_window}d)", yaxis_title="hm³/día"))
        st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

# =========================================================
# TAB 7: CONVERSIONES OPERATIVAS
# =========================================================
with tab7:
    st.markdown('<div class="st">Conversión Rápida de Variables Operativas</div>', unsafe_allow_html=True)

    cards_c = [
        mcard("Aportes", gl(dff, "aportes_netos_chcp_hm3"), fmt="{:.2f}", unit=" hm³/d"),
        mcard("Aportes", gl(dff, "aportes_netos_chcp_hm3_m3s"), fmt="{:.1f}", unit=" m³/s"),
        mcard("Aportes", gl(dff, "aportes_netos_chcp_hm3_cfs"), fmt="{:.0f}", unit=" pies³/s"),
        mcard("Usos", gl(dff, "usos_hm3"), fmt="{:.2f}", unit=" hm³/d"),
        mcard("Usos", gl(dff, "usos_hm3_m3s"), fmt="{:.1f}", unit=" m³/s"),
        mcard("Usos", gl(dff, "usos_hm3_cfs"), fmt="{:.0f}", unit=" pies³/s")
    ]
    metric_row(6, cards_c)

    cards_c2 = [
        mcard("Esclusajes", gl(dff, "locks_total_hm3"), fmt="{:.2f}", unit=" hm³/d"),
        mcard("Esclusajes", gl(dff, "locks_total_hm3_m3s"), fmt="{:.1f}", unit=" m³/s"),
        mcard("Esclusajes", gl(dff, "locks_total_hm3_cfs"), fmt="{:.0f}", unit=" pies³/s"),
        mcard("Agua para Hidro", gl(dff, "hidro_agua_total_hm3"), fmt="{:.2f}", unit=" hm³/d"),
        mcard("Agua para Hidro", gl(dff, "hidro_agua_total_hm3_m3s"), fmt="{:.1f}", unit=" m³/s"),
        mcard("Agua para Hidro", gl(dff, "hidro_agua_total_hm3_cfs"), fmt="{:.0f}", unit=" pies³/s")
    ]
    metric_row(6, cards_c2)

    st.markdown('<div class="note-box">Las conversiones de caudal equivalente se calculan a partir de volúmenes diarios: 1 hm³/día = 11.5741 m³/s = 408.46 pies³/s.</div>', unsafe_allow_html=True)

    st.markdown('<div class="st">Serie de Conversión Operativa</div>', unsafe_allow_html=True)
    ca, cb = st.columns(2)

    with ca:
        fig = go.Figure()
        for col, nm, cl in [
            ("aportes_netos_chcp_hm3_m3s", "Aportes", "#2ecc71"),
            ("usos_hm3_m3s", "Usos", "#e74c3c"),
            ("locks_total_hm3_m3s", "Esclusajes", "#3498db"),
            ("hidro_agua_total_hm3_m3s", "Hidrogeneración", "#f39c12"),
        ]:
            r = roll(dff, col, rolling_window)
            fig.add_trace(go.Scatter(x=r["actdate"], y=r[col], name=nm, line=dict(color=cl, width=2.3)))
        fig.update_layout(**base_layout(title=f"m³/s Equivalentes (Prom. {rolling_window}d)", yaxis_title="m³/s"))
        st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

    with cb:
        fig = go.Figure()
        for col, nm, cl in [
            ("aportes_netos_chcp_hm3_cfs", "Aportes", "#2ecc71"),
            ("usos_hm3_cfs", "Usos", "#e74c3c"),
            ("locks_total_hm3_cfs", "Esclusajes", "#3498db"),
            ("hidro_agua_total_hm3_cfs", "Hidrogeneración", "#f39c12"),
        ]:
            r = roll(dff, col, rolling_window)
            fig.add_trace(go.Scatter(x=r["actdate"], y=r[col], name=nm, line=dict(color=cl, width=2.3)))
        fig.update_layout(**base_layout(title=f"pies³/s Equivalentes (Prom. {rolling_window}d)", yaxis_title="pies³/s"))
        st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

    st.markdown('<div class="st">Relación Agua–Energía</div>', unsafe_allow_html=True)
    ca, cb = st.columns(2)

    with ca:
        fig = go.Figure()
        r = roll(dff, "hidro_total_mw", rolling_window)
        fig.add_trace(go.Scatter(x=r["actdate"], y=r["hidro_total_mw"], name="Potencia total", line=dict(color="#2c3e50", width=2.6)))
        fig.update_layout(**base_layout(title=f"Potencia Media (Prom. {rolling_window}d)", yaxis_title="MW"))
        st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

    with cb:
        fig = go.Figure()
        r = roll(dff, "ef_total_mwh_hm3", rolling_window)
        fig.add_trace(go.Scatter(
            x=r["actdate"], y=r["ef_total_mwh_hm3"], name="MWh/hm³",
            line=dict(color="#8e44ad", width=2.6), fill="tozeroy",
            fillcolor="rgba(142,68,173,.10)"
        ))
        fig.update_layout(**base_layout(title=f"Eficiencia Global (Prom. {rolling_window}d)", yaxis_title="MWh/hm³"))
        st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

# =========================================================
# TAB 8: TEMPERATURA Y SALINIDAD
# =========================================================
with tab8:
    st.markdown('<div class="st">Indicadores de Temperatura y Salinidad</div>', unsafe_allow_html=True)
    cards_t = [
        mcard("AMA", gl(dff, "tempereture_ama"), gd(dff, "tempereture_ama"), fmt="{:.2f}", unit=" °C"),
        mcard("LMB", gl(dff, "tempereture_lmb"), gd(dff, "tempereture_lmb"), fmt="{:.2f}", unit=" °C"),
        mcard("Salinidad Canal", gl(dff, "channel_salinity"), gd(dff, "channel_salinity"), fmt="{:.4f}"),
        mcard(f"AMA Prom. {rolling_window}d", ga(dff, "tempereture_ama", rolling_window), fmt="{:.2f}", unit=" °C"),
        mcard(f"LMB Prom. {rolling_window}d", ga(dff, "tempereture_lmb", rolling_window), fmt="{:.2f}", unit=" °C"),
        mcard(f"Salinidad Prom. {rolling_window}d", ga(dff, "channel_salinity", rolling_window), fmt="{:.4f}")
    ]
    metric_row(6, cards_t)

    ca, cb = st.columns(2)

    with ca:
        fig = go.Figure()
        for col, nm, cl in [
            ("tempereture_ama", "AMA", "#e74c3c"),
            ("tempereture_lmb", "LMB", "#2980b9"),
        ]:
            r = roll(dff, col, rolling_window)
            fig.add_trace(go.Scatter(x=r["actdate"], y=r[col], name=nm, line=dict(color=cl, width=2.4)))
        fig.update_layout(**base_layout(title=f"Temperatura (Prom. {rolling_window}d)", yaxis_title="°C"))
        st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

    with cb:
        fig = go.Figure()
        r = roll(dff, "channel_salinity", rolling_window)
        fig.add_trace(go.Scatter(
            x=r["actdate"], y=r["channel_salinity"], name="Salinidad",
            line=dict(color="#8e44ad", width=2.5), fill="tozeroy",
            fillcolor="rgba(142,68,173,.10)"
        ))
        fig.update_layout(**base_layout(title=f"Salinidad del Canal (Prom. {rolling_window}d)", yaxis_title="salinidad"))
        st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

    st.markdown('<div class="st">Relación Temperatura–Salinidad</div>', unsafe_allow_html=True)
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dff["tempereture_ama"], y=dff["channel_salinity"], mode="markers",
        name="AMA vs salinidad", marker=dict(size=8, opacity=.7, color=dff["tempereture_ama"])
    ))
    fig.update_layout(**base_layout(title="Dispersión: Temperatura AMA vs Salinidad", xaxis_title="Temperatura AMA (°C)", yaxis_title="Salinidad", height=410))
    st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

# =========================================================
# TAB 9: DATOS
# =========================================================
with tab9:
    st.markdown('<div class="st">Calidad y Fuente de Datos</div>', unsafe_allow_html=True)
    qc1, qc2, qc3, qc4 = st.columns(4)
    with qc1:
        st.metric("Registros finales", f"{quality_info.get('rows_final', 0):,}")
    with qc2:
        st.metric("Columnas leídas", f"{quality_info.get('columns', 0):,}")
    with qc3:
        st.metric("Fechas inválidas", f"{quality_info.get('invalid_dates', 0):,}")
    with qc4:
        st.metric("Fechas duplicadas", f"{quality_info.get('duplicate_dates', 0):,}")

    st.markdown(
        f"<div class='note-box'><b>Fuente:</b> {quality_info.get('source', 'N/D')}<br>"
        f"<b>Rango disponible:</b> {df['actdate'].min().strftime('%Y-%m-%d')} a {df['actdate'].max().strftime('%Y-%m-%d')}</div>",
        unsafe_allow_html=True,
    )

    if quality_info.get("critical_missing"):
        st.error("Faltan columnas críticas para algunos indicadores: " + ", ".join(quality_info["critical_missing"]))
    elif quality_info.get("missing_cols"):
        st.warning("El app creó columnas vacías para mantener la ejecución. Columnas faltantes: " + ", ".join(quality_info["missing_cols"][:25]))
        if len(quality_info["missing_cols"]) > 25:
            st.caption(f"... y {len(quality_info['missing_cols']) - 25} columnas adicionales.")
    else:
        st.success("Estructura de columnas operativas validada correctamente.")

    null_cols = [c for c in CRITICAL_COLS if c in df.columns and c != "actdate"]
    if null_cols:
        null_report = (
            df[null_cols]
            .isna()
            .mean()
            .mul(100)
            .round(1)
            .reset_index()
        )
        null_report.columns = ["Columna crítica", "% valores N/D"]
        null_report = null_report[null_report["% valores N/D"] > 0].sort_values("% valores N/D", ascending=False)
        with st.expander("Ver columnas críticas con valores N/D", expanded=False):
            if null_report.empty:
                st.write("No se detectaron valores N/D en las columnas críticas disponibles.")
            else:
                st.dataframe(null_report, use_container_width=True, hide_index=True)

    st.markdown('<div class="st">Tabla de Datos</div>', unsafe_allow_html=True)
    n_rows = st.slider("Filas a mostrar", 5, 120, max(10, rolling_window), key="data_rows")

    dcols = {
        "actdate": "Fecha",
        "actgatel": "Nivel Gatún (pies)",
        "actmadel": "Nivel Alhajuela (pies)",
        "agua_almacenada_gat_porc": "% Gatún",
        "agua_almacenada_ala_porc": "% Alhajuela",
        "aportes_netos_chcp_hm3": "Aportes (hm³)",
        "aportes_netos_chcp_hm3_m3s": "Aportes (m³/s)",
        "aportes_netos_chcp_hm3_cfs": "Aportes (pies³/s)",
        "usos_hm3": "Usos (hm³)",
        "usos_hm3_m3s": "Usos (m³/s)",
        "usos_hm3_cfs": "Usos (pies³/s)",
        "madmwh": "Madden (MWh)",
        "gatmwh": "Gatún (MWh)",
        "hidro_total_mwh": "Total Hidro (MWh)",
        "mad_mw": "Madden (MW)",
        "gat_mw": "Gatún (MW)",
        "hidro_total_mw": "Total Hidro (MW)",
        "locks_total_hm3": "Esclusajes (hm³)",
        "locks_total_hm3_m3s": "Esclusajes (m³/s)",
        "locks_total_hm3_cfs": "Esclusajes (pies³/s)",
        "hidro_agua_total_hm3": "Agua Hidro (hm³)",
        "hidro_agua_total_hm3_m3s": "Agua Hidro (m³/s)",
        "hidro_agua_total_hm3_cfs": "Agua Hidro (pies³/s)",
        "TOTAL TODOS LOS ESCLUSAJES HEC": "Total HEC",
        "tempereture_ama": "Temp AMA (°C)",
        "tempereture_lmb": "Temp LMB (°C)",
        "channel_salinity": "Salinidad",
    }

    present_cols = [c for c in dcols.keys() if c in dff.columns]
    tdf = dff[present_cols].tail(n_rows).copy()
    tdf.columns = [dcols[c] for c in present_cols]
    tdf["Fecha"] = pd.to_datetime(tdf["Fecha"]).dt.strftime("%Y-%m-%d")

    st.dataframe(
        tdf.set_index("Fecha").style.format("{:.2f}", na_rep="N/D"),
        use_container_width=True,
        height=min(42 * n_rows + 40, 650),
    )

    export_df = dff.copy()
    st.download_button(
        "📥 Descargar CSV filtrado",
        export_df.to_csv(index=False).encode("utf-8-sig"),
        "lake_house_filtrado.csv",
        "text/csv",
    )

    excel_buffer = BytesIO()
    with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
        export_df.to_excel(writer, index=False, sheet_name="LakeHouse_filtrado")
    st.download_button(
        "📥 Descargar Excel filtrado",
        excel_buffer.getvalue(),
        "lake_house_filtrado.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

# =========================================================
# FOOTER
# =========================================================
st.markdown("---")
st.markdown(
    '<div class="footer">Lake_House — HIMH · Dashboard Operativo · Datos: AWS LakeHouse Data Catalog · Creado por JFRodriguez</div>',
    unsafe_allow_html=True
)
