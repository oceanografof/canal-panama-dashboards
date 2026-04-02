"""
🌊 Dashboard Avanzado de Mareas — Canal de Panamá
===================================================
Incluye planos de referencia de mareas (HAT, MHHW, MHW, MSL, MLW, MLLW, LAT)
y análisis avanzado.

INSTALACIÓN:
    pip install streamlit pandas numpy plotly scipy

EJECUCIÓN:
    streamlit run app_mareas.py
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy import signal, stats as sp_stats
from scipy.fft import fft, fftfreq
import glob, os, calendar

# ══════════════════════════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════════════════════════
st.set_page_config(page_title="🌊 Mareas — Canal de Panamá", page_icon="🌊", layout="wide")

COLORES = {
    "LMB": {"linea": "#2980b9", "fill": "rgba(41,128,185,0.08)",
            "pico": "#e74c3c", "valle": "#27ae60"},
    "DHT": {"linea": "#8e44ad", "fill": "rgba(142,68,173,0.08)",
            "pico": "#e67e22", "valle": "#16a085"},
}
NOMBRES = {"LMB": "Limon Bay (Atlántico)", "DHT": "Diablo Heights (Pacífico)"}
MESES = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"]


# ══════════════════════════════════════════════════════════════
# FUNCIONES
# ══════════════════════════════════════════════════════════════
@st.cache_data(show_spinner="Cargando datos...")
def cargar_csv(fuente):
    df = pd.read_csv(fuente, skiprows=4, names=["fecha", "nivel_ft"])
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    df["nivel_ft"] = pd.to_numeric(df["nivel_ft"], errors="coerce")
    df = df.dropna(subset=["fecha", "nivel_ft"]).sort_values("fecha").reset_index(drop=True)
    df["nivel_m"] = (df["nivel_ft"] * 0.3048).round(4)
    return df


def detectar_estacion(nombre):
    n = nombre.upper()
    if "LMB" in n: return "LMB"
    if "DHT" in n: return "DHT"
    return "Desconocida"


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
    """
    Calcula los planos de referencia de mareas estándar (Tidal Datums).
    Basado en definiciones de NOAA/IHO.
    """
    plea = _plea.copy()
    baja = _baja.copy()

    # Separar pleamares y bajamares diarias (higher high, lower high, etc.)
    plea["date"] = plea["fecha"].dt.date
    baja["date"] = baja["fecha"].dt.date

    # Higher High Water (HHW) y Lower High Water (LHW) por día
    hhw_daily = plea.groupby("date")[col].max()
    lhw_daily = plea.groupby("date")[col].min()

    # Higher Low Water (HLW) y Lower Low Water (LLW) por día
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

    # Rangos derivados
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
# SIDEBAR
# ══════════════════════════════════════════════════════════════
st.sidebar.markdown("## 🌊 Mareas — Canal de Panamá")
st.sidebar.markdown("---")

archivos_locales = sorted(glob.glob("BulkExport-*.csv"))
st.sidebar.markdown("### 📂 Datos")
metodo = st.sidebar.radio(
    "Fuente",
    ["Subir archivo(s)", "Archivos locales"] if archivos_locales else ["Subir archivo(s)"],
    horizontal=True,
)

datasets = {}
if metodo == "Subir archivo(s)":
    archivos = st.sidebar.file_uploader("CSV de exportación ACP", type=["csv"],
                                         accept_multiple_files=True)
    for a in archivos:
        e = detectar_estacion(a.name)
        try:
            datasets[e] = cargar_csv(a)
            st.sidebar.success(f"✅ {e}: {len(datasets[e]):,} reg.")
        except Exception as ex:
            st.sidebar.error(str(ex))
else:
    for p in archivos_locales:
        e = detectar_estacion(p)
        try:
            datasets[e] = cargar_csv(p)
            st.sidebar.success(f"✅ {e}: {len(datasets[e]):,} reg.")
        except Exception as ex:
            st.sidebar.error(str(ex))

if not datasets:
    st.markdown(
        "<h1 style='color:#1a5276; text-align:center; margin-top:80px;'>"
        "🌊 Mareas — Canal de Panamá</h1>"
        "<p style='text-align:center; color:#5d6d7e; font-size:1.2rem;'>"
        "Sube tu archivo <b>BulkExport-LMB/DHT-*.csv</b> en la barra lateral.</p>",
        unsafe_allow_html=True,
    )
    st.stop()

estaciones = list(datasets.keys())
est_activa = st.sidebar.selectbox("Estación", estaciones,
    format_func=lambda x: NOMBRES.get(x, x)) if len(estaciones) > 1 else estaciones[0]

df_all = datasets[est_activa]
color = COLORES.get(est_activa, COLORES["LMB"])

st.sidebar.markdown("---")
st.sidebar.markdown("### ⚙️ Opciones")
unidad = st.sidebar.radio("Unidad", ["Pies (ft)", "Metros (m)"], horizontal=True)
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

# Calcular picos globales para datums
prom_d = 0.15 if est_activa == "LMB" else 2.0
if "Metros" in unidad: prom_d *= 0.3048
plea_all, baja_all = encontrar_picos(df, col, prom_d, 20)


# ══════════════════════════════════════════════════════════════
# HEADER + KPIs
# ══════════════════════════════════════════════════════════════
st.markdown(
    f"<h1 style='color:#1a5276;'>🌊 {NOMBRES.get(est_activa, est_activa)}</h1>"
    f"<p style='color:#5d6d7e; margin-top:-12px;'>Sensor Radar Telemétrico · {f_ini} → {f_fin} · "
    f"<b>Creador: JFRodriguez</b></p>",
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
    "📈 Serie Temporal",
    "🔴 Pleamares / Bajamares",
    "📊 Espectro",
    "📅 Estadísticas",
    "🗺️ Heatmap",
    "📉 Tendencia",
    "⚠️ Niveles Críticos",
    "🔧 Calidad",
]
if len(datasets) > 1:
    tab_names.append("🔀 Comparar")
tab_names.append("📥 Exportar")
tabs = st.tabs(tab_names)


# ═══════════════════════════════════════════════════════════════
# TAB 0 — RESUMEN
# ═══════════════════════════════════════════════════════════════
with tabs[0]:
    # Sparklines últimos 7 días
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

    # Datums rápidos
    st.subheader("Planos de referencia (resumen)")
    datums, rangos = calcular_datums(df, col, plea_all, baja_all)

    dc1,dc2,dc3 = st.columns(3)
    items = list(datums.items())
    for i, (key, d) in enumerate(items[:3]):
        with dc1:
            st.markdown(f"<div style='background:{d['color']}15; border-left:4px solid {d['color']};"
                f"border-radius:8px; padding:10px; margin:4px 0;'>"
                f"<b style='color:{d['color']};'>{key}</b> = {d['valor']:.2f} {u}"
                f"<br><small>{d['desc']}</small></div>", unsafe_allow_html=True)
    for i, (key, d) in enumerate(items[3:6]):
        with dc2:
            st.markdown(f"<div style='background:{d['color']}15; border-left:4px solid {d['color']};"
                f"border-radius:8px; padding:10px; margin:4px 0;'>"
                f"<b style='color:{d['color']};'>{key}</b> = {d['valor']:.2f} {u}"
                f"<br><small>{d['desc']}</small></div>", unsafe_allow_html=True)
    for i, (key, d) in enumerate(items[6:]):
        with dc3:
            st.markdown(f"<div style='background:{d['color']}15; border-left:4px solid {d['color']};"
                f"border-radius:8px; padding:10px; margin:4px 0;'>"
                f"<b style='color:{d['color']};'>{key}</b> = {d['valor']:.2f} {u}"
                f"<br><small>{d['desc']}</small></div>", unsafe_allow_html=True)

    # Distribución rápida
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

    # ── Diagrama visual de planos ──
    fig_d = go.Figure()

    # Serie temporal de fondo (muestra de 7 días)
    muestra = df[df["fecha"] >= df["fecha"].max() - pd.Timedelta(days=5)]
    if len(muestra) > 0:
        fig_d.add_trace(go.Scatter(
            x=muestra["fecha"], y=muestra[col],
            mode="lines", name="Nivel observado",
            line=dict(color=color["linea"], width=1.5),
            fill="tozeroy", fillcolor=color["fill"],
        ))

    # Líneas horizontales de datums
    for key, d in datums.items():
        if np.isnan(d["valor"]): continue
        fig_d.add_hline(
            y=d["valor"], line_dash="solid" if key == "MSL" else "dash",
            line_color=d["color"],
            line_width=2 if key == "MSL" else 1.5,
            annotation_text=f"{key}: {d['valor']:.2f} {u}",
            annotation_position="right",
            annotation_font_size=11,
            annotation_font_color=d["color"],
        )

    fig_d.update_layout(
        yaxis_title=f"Nivel ({u})",
        template="plotly_white", height=550,
        hovermode="x unified",
        margin=dict(l=50, r=150, t=30, b=50),
    )
    st.plotly_chart(fig_d, use_container_width=True)

    # ── Tabla de datums ──
    st.subheader("Tabla de planos de referencia")
    filas_d = []
    for key, d in datums.items():
        if np.isnan(d["valor"]): continue
        filas_d.append({
            "Sigla": key,
            "Nombre": d["nombre"],
            f"Nivel ({u})": round(d["valor"], 3),
            "Descripción": d["desc"],
        })
    st.dataframe(pd.DataFrame(filas_d), use_container_width=True, hide_index=True)

    # ── Rangos derivados ──
    st.subheader("Rangos de marea derivados")
    rc1, rc2 = st.columns(2)
    for i, (nombre, valor) in enumerate(rangos.items()):
        target = rc1 if i % 2 == 0 else rc2
        with target:
            st.metric(nombre, f"{valor:.3f} {u}")

    # ── Tipo de marea ──
    if "MN (Mean Range)" in rangos and "GT (Great Diurnal Range)" in rangos:
        F = rangos.get("GT (Great Diurnal Range)", 0)
        mn = rangos.get("MN (Mean Range)", 1)
        ratio = F / mn if mn > 0 else 0

        if ratio < 0.25:
            tipo = "Semidiurna"
            desc_tipo = "Dos pleamares y dos bajamares por día, similares en altura."
        elif ratio < 1.5:
            tipo = "Mixta (predominio semidiurno)"
            desc_tipo = "Dos pleamares y bajamares por día, con alturas desiguales."
        elif ratio < 3.0:
            tipo = "Mixta (predominio diurno)"
            desc_tipo = "Desigualdad notable entre pleamares/bajamares sucesivas."
        else:
            tipo = "Diurna"
            desc_tipo = "Una pleamar y una bajamar por día."

        st.subheader("Clasificación de la marea")
        st.info(f"**Tipo:** {tipo} (F = GT/MN = {ratio:.2f})\n\n{desc_tipo}")

    # ── Datums por año ──
    st.subheader("Evolución de planos por año")
    df["anio"] = df["fecha"].dt.year
    anios = sorted(df["anio"].unique())

    evol = []
    for a in anios:
        sub = df[df["anio"] == a]
        p_a, b_a = encontrar_picos(sub, col, prom_d, 20)
        if len(p_a) > 5 and len(b_a) > 5:
            p_a["date"] = p_a["fecha"].dt.date
            b_a["date"] = b_a["fecha"].dt.date
            evol.append({
                "Año": a,
                "HAT": sub[col].max(),
                "MHHW": p_a.groupby("date")[col].max().mean(),
                "MHW": p_a[col].mean(),
                "MSL": sub[col].mean(),
                "MLW": b_a[col].mean(),
                "MLLW": b_a.groupby("date")[col].min().mean(),
                "LAT": sub[col].min(),
            })
    df.drop(columns=["anio"], inplace=True, errors="ignore")

    if evol:
        df_evol = pd.DataFrame(evol)
        fig_ev = go.Figure()
        colores_ev = {"HAT":"#922b21","MHHW":"#e74c3c","MHW":"#e67e22",
                      "MSL":"#2ecc71","MLW":"#2980b9","MLLW":"#1a5276","LAT":"#0b5345"}
        for datum_key in ["HAT","MHHW","MHW","MSL","MLW","MLLW","LAT"]:
            if datum_key in df_evol.columns:
                fig_ev.add_trace(go.Scatter(
                    x=df_evol["Año"], y=df_evol[datum_key],
                    mode="lines+markers", name=datum_key,
                    line=dict(color=colores_ev.get(datum_key, "#333"), width=2),
                    marker=dict(size=5),
                ))
        fig_ev.update_layout(
            yaxis_title=f"Nivel ({u})", xaxis_title="Año",
            template="plotly_white", height=500,
            hovermode="x unified",
            margin=dict(l=50, r=20, t=20, b=50),
        )
        st.plotly_chart(fig_ev, use_container_width=True)

        with st.expander("📋 Tabla de datums por año"):
            st.dataframe(df_evol.round(3), use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════════
# TAB 2 — SERIE TEMPORAL
# ═══════════════════════════════════════════════════════════════
with tabs[2]:
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
                    annotation_text=f"{key}: {d['valor']:.2f}",
                    annotation_font_size=10, line_width=1)

    fig1.update_layout(yaxis_title=f"Nivel ({u})", template="plotly_white",
        height=500, hovermode="x unified", margin=dict(l=50,r=20,t=30,b=50))
    st.plotly_chart(fig1, use_container_width=True)

    # Media móvil
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
# TAB 3 — PLEAMARES / BAJAMARES
# ═══════════════════════════════════════════════════════════════
with tabs[3]:
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

    # Histogramas de alturas
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
# TAB 4 — ESPECTRO
# ═══════════════════════════════════════════════════════════════
with tabs[4]:
    st.caption("FFT para identificar componentes armónicas.")
    df_sp = df.set_index("fecha")[[col]].resample("15min").mean().interpolate()
    vals = df_sp[col].values; vals = vals - vals.mean(); N = len(vals)

    if N < 200:
        st.warning("Necesitas ≥3 días de datos.")
    else:
        yf = fft(vals); xf = fftfreq(N, d=0.25)
        mp = xf > 0; freqs = xf[mp]; amps = 2.0/N*np.abs(yf[mp]); periodos = 1.0/freqs

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
# TAB 5 — ESTADÍSTICAS
# ═══════════════════════════════════════════════════════════════
with tabs[5]:
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
        df["mn"] = df["fecha"].dt.month
        fig_bx = go.Figure()
        for m in sorted(df["mn"].unique()):
            s = df[df["mn"]==m]
            fig_bx.add_trace(go.Box(y=s[col], name=MESES[m-1],
                marker_color=f"hsl({(m-1)*30},65%,50%)", boxmean=True))
        fig_bx.update_layout(yaxis_title=f"Nivel ({u})", template="plotly_white",
            height=350, showlegend=False, margin=dict(l=50,r=20,t=20,b=50))
        st.plotly_chart(fig_bx, use_container_width=True)
        df.drop(columns=["mn"], inplace=True, errors="ignore")

    # Mensual
    st.subheader("Promedios mensuales")
    df["mes"] = df["fecha"].dt.month
    pm = df.groupby("mes")[col].agg(["mean","min","max"]).reset_index()
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
    df.drop(columns=["mes"], inplace=True, errors="ignore")


# ═══════════════════════════════════════════════════════════════
# TAB 6 — HEATMAP
# ═══════════════════════════════════════════════════════════════
with tabs[6]:
    st.subheader("Mapa de calor: Mes × Año")
    df["anio"]=df["fecha"].dt.year; df["mes"]=df["fecha"].dt.month
    pv = df.groupby(["anio","mes"])[col].mean().reset_index()
    pt = pv.pivot(index="anio", columns="mes", values=col)
    pt.columns = [MESES[m-1] for m in pt.columns]
    fig_hm = go.Figure(data=go.Heatmap(z=pt.values, x=pt.columns, y=pt.index,
        colorscale="Blues", colorbar_title=u, hoverongaps=False))
    fig_hm.update_layout(yaxis_title="Año", template="plotly_white",
        height=max(350, len(pt)*22), margin=dict(l=60,r=20,t=20,b=50))
    st.plotly_chart(fig_hm, use_container_width=True)

    st.subheader("Mapa de calor: Hora × Mes (rango de marea)")
    df["hora"]=df["fecha"].dt.hour
    pv2 = df.groupby(["hora","mes"])[col].agg(lambda x: x.max()-x.min()).reset_index()
    pt2 = pv2.pivot(index="hora", columns="mes", values=col)
    pt2.columns = [MESES[m-1] for m in pt2.columns]
    fig_hm2 = go.Figure(data=go.Heatmap(z=pt2.values, x=pt2.columns, y=pt2.index,
        colorscale="YlOrRd", colorbar_title=f"Rango ({u})", hoverongaps=False))
    fig_hm2.update_layout(yaxis_title="Hora", template="plotly_white",
        height=450, margin=dict(l=60,r=20,t=20,b=50))
    st.plotly_chart(fig_hm2, use_container_width=True)
    df.drop(columns=["anio","mes","hora"], inplace=True, errors="ignore")


# ═══════════════════════════════════════════════════════════════
# TAB 7 — TENDENCIA
# ═══════════════════════════════════════════════════════════════
with tabs[7]:
    st.subheader("Tendencia del nivel medio anual")
    df["anio"]=df["fecha"].dt.year
    pa = df.groupby("anio")[col].agg(["mean","std","min","max"]).reset_index()

    fig_t = go.Figure()
    fig_t.add_trace(go.Scatter(
        x=list(pa["anio"])+list(pa["anio"][::-1]),
        y=list(pa["max"])+list(pa["min"][::-1]),
        fill="toself", fillcolor=color["fill"],
        line=dict(color="rgba(0,0,0,0)"), name="Rango"))
    fig_t.add_trace(go.Scatter(x=pa["anio"], y=pa["mean"], mode="lines+markers",
        name="Promedio", line=dict(color=color["linea"], width=2.5), marker=dict(size=6),
        error_y=dict(type="data", array=pa["std"], visible=True, color="rgba(0,0,0,0.1)")))

    if len(pa) >= 3:
        slope, intercept, r_val, p_val, std_err = sp_stats.linregress(pa["anio"], pa["mean"])
        fig_t.add_trace(go.Scatter(x=pa["anio"],
            y=intercept + slope*pa["anio"],
            mode="lines", name=f"Tendencia: {slope:+.4f} {u}/año",
            line=dict(color="#e74c3c", dash="dash", width=2)))
        tc1,tc2,tc3,tc4 = st.columns(4)
        tc1.metric("Pendiente", f"{slope:+.4f} {u}/año")
        tc2.metric("Por década", f"{slope*10:+.3f} {u}")
        tc3.metric("R²", f"{r_val**2:.3f}")
        sig = "✅ Significativa" if p_val < 0.05 else "⚠️ No significativa"
        tc4.metric("p-valor", f"{p_val:.4f} ({sig})")

    fig_t.update_layout(xaxis_title="Año", yaxis_title=f"Nivel ({u})",
        template="plotly_white", height=500, margin=dict(l=50,r=20,t=30,b=50))
    st.plotly_chart(fig_t, use_container_width=True)
    df.drop(columns=["anio"], inplace=True, errors="ignore")


# ═══════════════════════════════════════════════════════════════
# TAB 8 — NIVELES CRÍTICOS
# ═══════════════════════════════════════════════════════════════
with tabs[8]:
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

    # Excedencia por año
    st.subheader("Excedencia por año")
    df["anio"] = df["fecha"].dt.year
    if modo == "Sobre un nivel":
        exc_a = df.groupby("anio").apply(lambda g: (g[col] > nivel_critico).sum()).reset_index(name="horas")
    else:
        exc_a = df.groupby("anio").apply(lambda g: (g[col] < nivel_critico).sum()).reset_index(name="horas")

    fig_ea = go.Figure()
    fig_ea.add_trace(go.Bar(x=exc_a["anio"], y=exc_a["horas"],
        marker_color=color["linea"], opacity=0.8))
    fig_ea.update_layout(yaxis_title="Horas", xaxis_title="Año",
        template="plotly_white", height=350, margin=dict(l=50,r=20,t=20,b=50))
    st.plotly_chart(fig_ea, use_container_width=True)
    df.drop(columns=["anio"], inplace=True, errors="ignore")


# ═══════════════════════════════════════════════════════════════
# TAB 9 — CALIDAD
# ═══════════════════════════════════════════════════════════════
with tabs[9]:
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
    df["anio"]=df["fecha"].dt.year
    esp_anio = 365.25 * (pd.Timedelta("1D") / freq_esp) if freq_esp > pd.Timedelta(0) else 8766
    cob = df.groupby("anio").size().reset_index(name="n")
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
    df["mes"]=df["fecha"].dt.month
    cm = df.groupby(["anio","mes"]).size().reset_index(name="n")
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
    df.drop(columns=["anio","mes"], inplace=True, errors="ignore")


# ═══════════════════════════════════════════════════════════════
# TAB — COMPARAR (si hay 2+ estaciones)
# ═══════════════════════════════════════════════════════════════
idx_tab = 10
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
    "🌊 Mareas del Canal de Panamá · Dashboard Avanzado · "
    "Datos: Autoridad del Canal de Panamá (ACP)<br>"
    "Creador: JFRodriguez</div>",
    unsafe_allow_html=True,
)
