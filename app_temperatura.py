"""
🌡️ Dashboard Avanzado — Temperatura del Agua
Canal de Panamá · Estación AMA
==============================================
INSTALACIÓN:
    pip install streamlit pandas numpy plotly scipy openpyxl

EJECUCIÓN:
    streamlit run app_temperatura.py
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy import stats as sp_stats
from datetime import timedelta
import glob, os, calendar

# ══════════════════════════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="🌡️ Temperatura — Canal de Panamá",
    page_icon="🌡️",
    layout="wide",
)

# Paleta de colores
C = {
    "rojo": "#e74c3c", "rojo_claro": "rgba(231,76,60,0.08)",
    "azul": "#2980b9", "azul_claro": "rgba(41,128,185,0.08)",
    "naranja": "#e67e22", "verde": "#27ae60", "morado": "#8e44ad",
    "gris": "#95a5a6", "oscuro": "#2c3e50",
    "amarillo": "#f1c40f", "turquesa": "#1abc9c",
}

MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
         "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]


# ══════════════════════════════════════════════════════════════
# FUNCIONES
# ══════════════════════════════════════════════════════════════
@st.cache_data(show_spinner="Cargando datos de temperatura...")
def cargar_excel(fuente):
    df = pd.read_excel(fuente, skiprows=1)
    df.columns = ["fecha_inicio", "fecha_fin", "temp_raw"]
    df["temp_c"] = (
        df["temp_raw"].astype(str).str.replace(",", ".", regex=False)
    )
    df["temp_c"] = pd.to_numeric(df["temp_c"], errors="coerce")
    df["fecha"] = pd.to_datetime(df["fecha_inicio"], errors="coerce")
    df = df.dropna(subset=["fecha", "temp_c"])
    df = df[(df["temp_c"] >= 10) & (df["temp_c"] <= 45)]
    df = df[["fecha", "temp_c"]].sort_values("fecha").reset_index(drop=True)
    df["temp_f"] = (df["temp_c"] * 9 / 5 + 32).round(2)
    return df


@st.cache_data(show_spinner="Cargando CSV de mareas...")
def cargar_csv_mareas(fuente):
    df = pd.read_csv(fuente, skiprows=4, names=["fecha", "nivel_ft"])
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    df["nivel_ft"] = pd.to_numeric(df["nivel_ft"], errors="coerce")
    df = df.dropna(subset=["fecha", "nivel_ft"]).sort_values("fecha").reset_index(drop=True)
    df["nivel_m"] = (df["nivel_ft"] * 0.3048).round(4)
    return df


@st.cache_data(show_spinner="Cargando datos de viento...")
def cargar_excel_viento(fuente):
    """Lee Excel de exportación ACP de velocidad de viento."""
    df = pd.read_excel(fuente, skiprows=1)
    df.columns = ["fecha_inicio", "fecha_fin", "viento_raw"]
    df["viento_ms"] = (
        df["viento_raw"].astype(str).str.replace(",", ".", regex=False)
    )
    df["viento_ms"] = pd.to_numeric(df["viento_ms"], errors="coerce")
    df["fecha"] = pd.to_datetime(df["fecha_inicio"], errors="coerce")
    df = df.dropna(subset=["fecha", "viento_ms"])
    df = df[(df["viento_ms"] >= 0) & (df["viento_ms"] <= 50)]
    df = df[["fecha", "viento_ms"]].sort_values("fecha").reset_index(drop=True)
    # Conversiones
    df["viento_kt"] = (df["viento_ms"] * 1.94384).round(2)    # nudos
    df["viento_kmh"] = (df["viento_ms"] * 3.6).round(2)        # km/h
    return df


def resam(df, col, limite=12000, freq="1h"):
    if len(df) <= limite:
        return df, False
    r = df.set_index("fecha")[[col]].resample(freq).mean().dropna().reset_index()
    return r, True


def color_temp(val, vmin, vmax):
    """Retorna un color entre azul y rojo según valor."""
    ratio = (val - vmin) / (vmax - vmin) if vmax > vmin else 0.5
    ratio = max(0, min(1, ratio))
    r = int(41 + (231 - 41) * ratio)
    g = int(128 + (76 - 128) * ratio)
    b = int(185 + (60 - 185) * ratio)
    return f"rgb({r},{g},{b})"


# ══════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════
st.sidebar.markdown("## 🌡️ Dashboard de Temperatura")
st.sidebar.markdown("Canal de Panamá")
st.sidebar.markdown("---")

# Carga de datos
df_temp = None
df_marea = None
df_viento = None

archivos_temp = sorted(glob.glob("DataSetExport-Water_Temp*.xlsx"))
archivos_mareas = sorted(glob.glob("BulkExport-*.csv"))
archivos_viento = sorted(glob.glob("DataSetExport-Wind_Speed*.xlsx"))

if archivos_temp:
    df_temp = cargar_excel(archivos_temp[0])
    st.sidebar.success(f"✅ Temperatura: {len(df_temp):,} reg.")
else:
    f_up = st.sidebar.file_uploader("Sube Excel de temperatura", type=["xlsx", "xls"], key="t")
    if f_up:
        df_temp = cargar_excel(f_up)
        st.sidebar.success(f"✅ {len(df_temp):,} registros")

st.sidebar.markdown("---")
st.sidebar.caption("Mareas (opcional, para correlación)")
if archivos_mareas:
    for p in archivos_mareas:
        try:
            df_marea = cargar_csv_mareas(p)
            st.sidebar.success(f"✅ Marea: {len(df_marea):,} reg.")
        except Exception:
            pass
else:
    f_m = st.sidebar.file_uploader("Sube CSV de mareas", type=["csv"], key="m")
    if f_m:
        try:
            df_marea = cargar_csv_mareas(f_m)
            st.sidebar.success(f"✅ {len(df_marea):,} registros")
        except Exception as e:
            st.sidebar.error(str(e))

st.sidebar.markdown("---")
st.sidebar.caption("Viento (opcional, para correlación)")
if archivos_viento:
    try:
        df_viento = cargar_excel_viento(archivos_viento[0])
        st.sidebar.success(f"✅ Viento: {len(df_viento):,} reg.")
    except Exception:
        pass
else:
    f_v = st.sidebar.file_uploader("Sube Excel de viento", type=["xlsx", "xls"], key="v")
    if f_v:
        try:
            df_viento = cargar_excel_viento(f_v)
            st.sidebar.success(f"✅ Viento: {len(df_viento):,} registros")
        except Exception as e:
            st.sidebar.error(str(e))

if df_temp is None:
    st.markdown(
        "<div style='text-align:center; margin-top:100px;'>"
        "<h1 style='color:#c0392b;'>🌡️ Dashboard de Temperatura</h1>"
        "<p style='font-size:1.2rem; color:#5d6d7e;'>"
        "Sube tu archivo Excel en la barra lateral para comenzar.</p></div>",
        unsafe_allow_html=True,
    )
    st.stop()

# Opciones
st.sidebar.markdown("---")
st.sidebar.markdown("### ⚙️ Opciones")
unidad = st.sidebar.radio("Unidad", ["°C", "°F"], horizontal=True)
col_t = "temp_c" if unidad == "°C" else "temp_f"

fmin = df_temp["fecha"].min().date()
fmax = df_temp["fecha"].max().date()
default_ini = max(fmin, fmax - pd.Timedelta(days=365))

rango = st.sidebar.date_input("Rango de fechas", value=(default_ini, fmax),
                               min_value=fmin, max_value=fmax)
if isinstance(rango, (list, tuple)) and len(rango) == 2:
    f_ini, f_fin = rango
else:
    f_ini, f_fin = fmin, fmax

mask = (df_temp["fecha"].dt.date >= f_ini) & (df_temp["fecha"].dt.date <= f_fin)
df = df_temp[mask].copy()

if df.empty:
    st.warning("No hay datos en el rango.")
    st.stop()

st.sidebar.markdown("---")
st.sidebar.markdown(f"**Total:** {len(df_temp):,} registros")
st.sidebar.markdown(f"**Período:** {fmin} → {fmax}")
st.sidebar.markdown(f"**Filtro:** {len(df):,} registros")


# ══════════════════════════════════════════════════════════════
# HEADER
# ══════════════════════════════════════════════════════════════
st.markdown(
    "<h1 style='color:#c0392b;'>🌡️ Dashboard — Temperatura del Agua</h1>"
    "<p style='color:#5d6d7e; margin-top:-12px;'>"
    "Canal de Panamá · Estación AMA · Telemetría Horaria · "
    "<b>Creador: JFRodriguez</b></p>",
    unsafe_allow_html=True,
)

# ── KPIs principales ──
k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("Actual", f"{df[col_t].iloc[-1]:.1f} {unidad}")
k2.metric("Máxima", f"{df[col_t].max():.1f} {unidad}")
k3.metric("Mínima", f"{df[col_t].min():.1f} {unidad}")
k4.metric("Promedio", f"{df[col_t].mean():.1f} {unidad}")
k5.metric("Desv. Est.", f"{df[col_t].std():.2f} {unidad}")
dias_total = (df["fecha"].max() - df["fecha"].min()).days
k6.metric("Período", f"{dias_total} días")

st.markdown("---")


# ══════════════════════════════════════════════════════════════
# TABS
# ══════════════════════════════════════════════════════════════
tab_names = [
    "🏠 Resumen",
    "📈 Serie Temporal",
    "📅 Ciclos",
    "🗺️ Heatmap",
    "🌊 Surgencia",
    "🔍 Anomalías",
    "📉 Tendencia",
    "📊 Comparar Años",
    "⚠️ Umbrales",
    "🔧 Calidad",
]
if df_marea is not None:
    tab_names.append("🌊 Temp vs Marea")
if df_viento is not None:
    tab_names.append("💨 Temp vs Viento")
tab_names.append("📥 Exportar")

tabs = st.tabs(tab_names)


# ═══════════════════════════════════════════════════════════════
# TAB 0 — RESUMEN / DASHBOARD PRINCIPAL
# ═══════════════════════════════════════════════════════════════
with tabs[0]:
    # ── Fila 1: Sparklines últimos 30 días ──
    st.subheader("Últimos 30 días")
    ultimos_30 = df[df["fecha"] >= df["fecha"].max() - timedelta(days=30)]

    r1c1, r1c2, r1c3 = st.columns(3)

    with r1c1:
        daily_30 = ultimos_30.set_index("fecha")[[col_t]].resample("1D").mean().dropna()
        fig_spark = go.Figure()
        fig_spark.add_trace(go.Scatter(
            x=daily_30.index, y=daily_30[col_t],
            mode="lines", fill="tozeroy",
            line=dict(color=C["rojo"], width=2),
            fillcolor=C["rojo_claro"],
        ))
        fig_spark.update_layout(
            height=180, margin=dict(l=10, r=10, t=30, b=10),
            template="plotly_white", showlegend=False,
            title=dict(text="Temperatura diaria", font_size=14),
            yaxis=dict(visible=True, showticklabels=True),
            xaxis=dict(visible=True, showticklabels=True),
        )
        st.plotly_chart(fig_spark, use_container_width=True)

    with r1c2:
        daily_range = ultimos_30.set_index("fecha")[[col_t]].resample("1D").agg(["max", "min"]).dropna()
        daily_range.columns = ["max", "min"]
        daily_range["rango"] = daily_range["max"] - daily_range["min"]
        fig_rng = go.Figure()
        fig_rng.add_trace(go.Bar(
            x=daily_range.index, y=daily_range["rango"],
            marker_color=C["naranja"], opacity=0.7,
        ))
        fig_rng.update_layout(
            height=180, margin=dict(l=10, r=10, t=30, b=10),
            template="plotly_white", showlegend=False,
            title=dict(text="Rango diario", font_size=14),
        )
        st.plotly_chart(fig_rng, use_container_width=True)

    with r1c3:
        hora_30 = ultimos_30.copy()
        hora_30["hora"] = hora_30["fecha"].dt.hour
        ciclo = hora_30.groupby("hora")[col_t].mean()
        fig_ciclo = go.Figure()
        fig_ciclo.add_trace(go.Scatter(
            x=ciclo.index, y=ciclo.values,
            mode="lines+markers",
            line=dict(color=C["morado"], width=2),
            marker=dict(size=4),
        ))
        fig_ciclo.update_layout(
            height=180, margin=dict(l=10, r=10, t=30, b=10),
            template="plotly_white", showlegend=False,
            title=dict(text="Ciclo diario promedio", font_size=14),
            xaxis_title="Hora",
        )
        st.plotly_chart(fig_ciclo, use_container_width=True)

    # ── Fila 2: Indicadores rápidos ──
    st.subheader("Indicadores del período seleccionado")
    r2c1, r2c2, r2c3, r2c4 = st.columns(4)

    # Días calientes (> percentil 90)
    p90 = df[col_t].quantile(0.90)
    p10 = df[col_t].quantile(0.10)
    dias_calientes = df[df[col_t] > p90]["fecha"].dt.date.nunique()
    dias_frios = df[df[col_t] < p10]["fecha"].dt.date.nunique()

    with r2c1:
        st.markdown(
            f"<div style='background:linear-gradient(135deg,#fdedec,#f5b7b1);"
            f"border-radius:12px; padding:20px; text-align:center;'>"
            f"<div style='font-size:2rem; font-weight:700; color:#c0392b;'>{dias_calientes}</div>"
            f"<div style='font-size:0.85rem; color:#922b21;'>Días calientes (>{p90:.1f}{unidad})</div>"
            f"</div>", unsafe_allow_html=True,
        )

    with r2c2:
        st.markdown(
            f"<div style='background:linear-gradient(135deg,#ebf5fb,#aed6f1);"
            f"border-radius:12px; padding:20px; text-align:center;'>"
            f"<div style='font-size:2rem; font-weight:700; color:#2471a3;'>{dias_frios}</div>"
            f"<div style='font-size:0.85rem; color:#1a5276;'>Días fríos (<{p10:.1f}{unidad})</div>"
            f"</div>", unsafe_allow_html=True,
        )

    with r2c3:
        # Variabilidad (coeficiente de variación)
        cv = (df[col_t].std() / df[col_t].mean() * 100)
        st.markdown(
            f"<div style='background:linear-gradient(135deg,#fef9e7,#f9e79f);"
            f"border-radius:12px; padding:20px; text-align:center;'>"
            f"<div style='font-size:2rem; font-weight:700; color:#7d6608;'>{cv:.1f}%</div>"
            f"<div style='font-size:0.85rem; color:#7d6608;'>Coef. de variación</div>"
            f"</div>", unsafe_allow_html=True,
        )

    with r2c4:
        rango_total = df[col_t].max() - df[col_t].min()
        st.markdown(
            f"<div style='background:linear-gradient(135deg,#eafaf1,#abebc6);"
            f"border-radius:12px; padding:20px; text-align:center;'>"
            f"<div style='font-size:2rem; font-weight:700; color:#1e8449;'>{rango_total:.1f}{unidad}</div>"
            f"<div style='font-size:0.85rem; color:#1e8449;'>Rango total</div>"
            f"</div>", unsafe_allow_html=True,
        )

    # ── Fila 3: Distribución + Box por mes ──
    st.markdown("---")
    r3c1, r3c2 = st.columns(2)

    with r3c1:
        st.subheader("Distribución")
        fig_dist = go.Figure()
        fig_dist.add_trace(go.Histogram(
            x=df[col_t], nbinsx=80,
            marker_color=C["rojo"], opacity=0.7,
        ))
        fig_dist.add_vline(x=df[col_t].mean(), line_dash="dash", line_color=C["oscuro"],
                           annotation_text=f"μ={df[col_t].mean():.1f}")
        fig_dist.add_vline(x=p90, line_dash="dot", line_color=C["naranja"],
                           annotation_text=f"P90={p90:.1f}")
        fig_dist.add_vline(x=p10, line_dash="dot", line_color=C["azul"],
                           annotation_text=f"P10={p10:.1f}")
        fig_dist.update_layout(
            xaxis_title=f"Temperatura ({unidad})", yaxis_title="Frecuencia",
            template="plotly_white", height=350,
            margin=dict(l=50, r=20, t=20, b=50),
        )
        st.plotly_chart(fig_dist, use_container_width=True)

    with r3c2:
        st.subheader("Box plot mensual")
        df["mes_num"] = df["fecha"].dt.month
        fig_box = go.Figure()
        for m in sorted(df["mes_num"].unique()):
            sub = df[df["mes_num"] == m]
            fig_box.add_trace(go.Box(
                y=sub[col_t], name=MESES[m - 1],
                marker_color=f"hsl({(m - 1) * 30}, 65%, 50%)",
                boxmean=True,
            ))
        fig_box.update_layout(
            yaxis_title=f"Temperatura ({unidad})",
            template="plotly_white", height=350,
            showlegend=False,
            margin=dict(l=50, r=20, t=20, b=50),
        )
        st.plotly_chart(fig_box, use_container_width=True)
        df.drop(columns=["mes_num"], inplace=True, errors="ignore")


# ═══════════════════════════════════════════════════════════════
# TAB 1 — SERIE TEMPORAL
# ═══════════════════════════════════════════════════════════════
with tabs[1]:
    st.subheader("Serie temporal completa")
    df_plot, resumido = resam(df, col_t)
    if resumido:
        st.caption(f"Vista resumida · {len(df_plot):,} puntos")

    fig1 = go.Figure()
    fig1.add_trace(go.Scattergl(
        x=df_plot["fecha"], y=df_plot[col_t],
        mode="lines", name="Temperatura",
        line=dict(color=C["rojo"], width=1),
        fill="tozeroy", fillcolor=C["rojo_claro"],
    ))
    fig1.add_hline(y=df[col_t].mean(), line_dash="dash", line_color=C["azul"],
                   annotation_text=f"Promedio: {df[col_t].mean():.1f} {unidad}")
    fig1.update_layout(
        yaxis_title=f"Temperatura ({unidad})", template="plotly_white",
        height=500, hovermode="x unified",
        margin=dict(l=50, r=20, t=30, b=50),
    )
    st.plotly_chart(fig1, use_container_width=True)

    # Media móvil
    st.subheader("Promedio móvil")
    vc1, vc2 = st.columns([1, 3])
    with vc1:
        ventana = st.slider("Ventana (días)", 1, 180, 30)
        mostrar_bandas = st.checkbox("Mostrar banda ± 1σ", value=True)

    df_ma = df.set_index("fecha")[[col_t]].resample("1h").mean()
    w = ventana * 24
    df_ma["media"] = df_ma[col_t].rolling(w, min_periods=1).mean()
    df_ma["std"] = df_ma[col_t].rolling(w, min_periods=1).std()
    df_ma["upper"] = df_ma["media"] + df_ma["std"]
    df_ma["lower"] = df_ma["media"] - df_ma["std"]
    df_ma = df_ma.dropna(subset=["media"]).reset_index()

    # resamplear para graficar
    if len(df_ma) > 12000:
        df_ma_p = df_ma.set_index("fecha")[["media", "upper", "lower"]].resample("6h").mean().dropna().reset_index()
    else:
        df_ma_p = df_ma

    fig1b = go.Figure()
    if mostrar_bandas:
        fig1b.add_trace(go.Scatter(
            x=list(df_ma_p["fecha"]) + list(df_ma_p["fecha"][::-1]),
            y=list(df_ma_p["upper"]) + list(df_ma_p["lower"][::-1]),
            fill="toself", fillcolor="rgba(231,76,60,0.1)",
            line=dict(color="rgba(0,0,0,0)"), name="± 1σ",
        ))
    fig1b.add_trace(go.Scattergl(
        x=df_ma_p["fecha"], y=df_ma_p["media"],
        mode="lines", name=f"Media {ventana}d",
        line=dict(color=C["rojo"], width=2),
    ))
    fig1b.update_layout(
        yaxis_title=f"Temperatura ({unidad})", template="plotly_white",
        height=380, hovermode="x unified",
        margin=dict(l=50, r=20, t=20, b=50),
    )
    st.plotly_chart(fig1b, use_container_width=True)


# ═══════════════════════════════════════════════════════════════
# TAB 2 — CICLOS Y PATRONES
# ═══════════════════════════════════════════════════════════════
with tabs[2]:
    cc1, cc2 = st.columns(2)

    with cc1:
        st.subheader("Ciclo diario")
        df["hora"] = df["fecha"].dt.hour
        ph = df.groupby("hora")[col_t].agg(["mean", "std", "min", "max"]).reset_index()
        fig2a = go.Figure()
        fig2a.add_trace(go.Scatter(
            x=list(ph["hora"]) + list(ph["hora"][::-1]),
            y=list(ph["max"]) + list(ph["min"][::-1]),
            fill="toself", fillcolor="rgba(231,76,60,0.08)",
            line=dict(color="rgba(0,0,0,0)"), name="Min-Max",
        ))
        fig2a.add_trace(go.Scatter(
            x=ph["hora"], y=ph["mean"], mode="lines+markers",
            line=dict(color=C["rojo"], width=2.5), name="Promedio",
            error_y=dict(type="data", array=ph["std"], visible=True,
                         color="rgba(231,76,60,0.2)"),
        ))
        fig2a.update_layout(
            xaxis_title="Hora", yaxis_title=f"Temp ({unidad})",
            template="plotly_white", height=380,
            margin=dict(l=50, r=20, t=20, b=50),
        )
        st.plotly_chart(fig2a, use_container_width=True)
        df.drop(columns=["hora"], inplace=True, errors="ignore")

    with cc2:
        st.subheader("Ciclo estacional")
        df["mes"] = df["fecha"].dt.month
        pm = df.groupby("mes")[col_t].agg(["mean", "min", "max", "std"]).reset_index()
        fig2b = go.Figure()
        fig2b.add_trace(go.Bar(
            x=[MESES[m - 1] for m in pm["mes"]], y=pm["mean"],
            marker_color=[f"hsl({(m-1)*30}, 65%, 50%)" for m in pm["mes"]],
            name="Promedio",
            error_y=dict(type="data", array=pm["std"], visible=True),
        ))
        fig2b.add_trace(go.Scatter(
            x=[MESES[m - 1] for m in pm["mes"]], y=pm["max"],
            mode="lines+markers", name="Máx",
            line=dict(color=C["naranja"], dash="dot"),
        ))
        fig2b.add_trace(go.Scatter(
            x=[MESES[m - 1] for m in pm["mes"]], y=pm["min"],
            mode="lines+markers", name="Mín",
            line=dict(color=C["azul"], dash="dot"),
        ))
        fig2b.update_layout(
            yaxis_title=f"Temp ({unidad})", template="plotly_white",
            height=380, margin=dict(l=50, r=20, t=20, b=50),
        )
        st.plotly_chart(fig2b, use_container_width=True)
        df.drop(columns=["mes"], inplace=True, errors="ignore")

    # Día de la semana
    st.subheader("¿Hay patrón por día de la semana?")
    df["dow"] = df["fecha"].dt.dayofweek
    dow_names = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
    pdow = df.groupby("dow")[col_t].agg(["mean", "std"]).reset_index()
    fig2c = go.Figure()
    fig2c.add_trace(go.Bar(
        x=[dow_names[d] for d in pdow["dow"]], y=pdow["mean"],
        marker_color=C["turquesa"],
        error_y=dict(type="data", array=pdow["std"], visible=True,
                     color="rgba(0,0,0,0.15)"),
    ))
    fig2c.update_layout(
        yaxis_title=f"Temp ({unidad})", template="plotly_white",
        height=300, margin=dict(l=50, r=20, t=20, b=50),
    )
    st.plotly_chart(fig2c, use_container_width=True)
    st.caption("Si las barras son casi iguales, la temperatura no depende del día — lo esperado para un fenómeno natural.")
    df.drop(columns=["dow"], inplace=True, errors="ignore")


# ═══════════════════════════════════════════════════════════════
# TAB 3 — HEATMAP
# ═══════════════════════════════════════════════════════════════
with tabs[3]:
    st.subheader("Mapa de calor: Mes × Año")
    df["anio"] = df["fecha"].dt.year
    df["mes"] = df["fecha"].dt.month
    pivot = df.groupby(["anio", "mes"])[col_t].mean().reset_index()
    pt = pivot.pivot(index="anio", columns="mes", values=col_t)
    pt.columns = [MESES[m - 1] for m in pt.columns]

    fig3a = go.Figure(data=go.Heatmap(
        z=pt.values, x=pt.columns, y=pt.index,
        colorscale="RdYlBu_r", colorbar_title=unidad,
        hoverongaps=False,
        hovertemplate="Año: %{y}<br>Mes: %{x}<br>Temp: %{z:.1f}" + unidad + "<extra></extra>",
    ))
    fig3a.update_layout(
        yaxis_title="Año", template="plotly_white",
        height=max(350, len(pt) * 22),
        margin=dict(l=60, r=20, t=20, b=50),
    )
    st.plotly_chart(fig3a, use_container_width=True)

    # Heatmap Hora × Mes
    st.subheader("Mapa de calor: Hora × Mes")
    df["hora"] = df["fecha"].dt.hour
    pivot2 = df.groupby(["hora", "mes"])[col_t].mean().reset_index()
    pt2 = pivot2.pivot(index="hora", columns="mes", values=col_t)
    pt2.columns = [MESES[m - 1] for m in pt2.columns]

    fig3b = go.Figure(data=go.Heatmap(
        z=pt2.values, x=pt2.columns, y=pt2.index,
        colorscale="RdYlBu_r", colorbar_title=unidad,
        hoverongaps=False,
    ))
    fig3b.update_layout(
        yaxis_title="Hora del día", template="plotly_white",
        height=450, margin=dict(l=60, r=20, t=20, b=50),
    )
    st.plotly_chart(fig3b, use_container_width=True)
    st.caption("Este heatmap muestra cuándo el agua está más caliente (hora + mes). Útil para planificar muestreos.")

    df.drop(columns=["anio", "mes", "hora"], inplace=True, errors="ignore")


# ═══════════════════════════════════════════════════════════════
# TAB 4 — SURGENCIA / AFLORAMIENTO
# ═══════════════════════════════════════════════════════════════
with tabs[4]:
    st.subheader("🌊 Análisis de Surgencia / Afloramiento Costero")
    st.caption(
        "La surgencia (upwelling) se detecta cuando la temperatura del agua "
        "cae por debajo de un umbral de afloramiento, indicando ascenso de aguas profundas frías. "
        "El umbral estándar es ~25°C pero puede ajustarse."
    )

    # ── Controles interactivos ──
    su1, su2 = st.columns([1, 3])

    with su1:
        st.markdown("### ⚙️ Parámetros")
        if unidad == "°C":
            umbral_surgencia = st.slider(
                "Umbral de afloramiento (°C)", 18.0, 30.0, 25.0, 0.5,
                help="Temperatura bajo la cual se considera evento de surgencia. "
                     "25°C es el valor de referencia estándar.",
            )
        else:
            umbral_surgencia = st.slider(
                "Umbral de afloramiento (°F)", 64.0, 86.0, 77.0, 0.5,
                help="77°F = 25°C. Umbral estándar de afloramiento.",
            )

        duracion_min = st.slider(
            "Duración mínima (horas)", 1, 48, 6,
            help="Nº mínimo de horas consecutivas bajo el umbral "
                 "para considerarlo un evento de surgencia.",
        )

        st.markdown("---")
        st.markdown(f"**Umbral:** {umbral_surgencia:.1f} {unidad}")

    # ── Detectar eventos de surgencia ──
    df_surg = df.copy()
    df_surg["bajo_umbral"] = df_surg[col_t] < umbral_surgencia

    # Identificar eventos consecutivos
    df_surg["grupo"] = (df_surg["bajo_umbral"] != df_surg["bajo_umbral"].shift()).cumsum()
    eventos_raw = df_surg[df_surg["bajo_umbral"]].groupby("grupo").agg(
        inicio=("fecha", "min"),
        fin=("fecha", "max"),
        duracion_h=("fecha", "count"),
        temp_min=(col_t, "min"),
        temp_media=(col_t, "mean"),
        intensidad=(col_t, lambda x: umbral_surgencia - x.min()),
    ).reset_index(drop=True)

    # Filtrar por duración mínima
    eventos = eventos_raw[eventos_raw["duracion_h"] >= duracion_min].reset_index(drop=True)

    # Estadísticas
    total_horas_surg = eventos["duracion_h"].sum() if len(eventos) > 0 else 0
    pct_surg = total_horas_surg / len(df_surg) * 100 if len(df_surg) > 0 else 0

    with su1:
        st.markdown("### 📊 Resultados")
        st.metric("Eventos detectados", f"{len(eventos)}")
        st.metric("Horas totales", f"{total_horas_surg:,}")
        st.metric("% del período", f"{pct_surg:.1f}%")
        if len(eventos) > 0:
            st.metric("Duración prom.", f"{eventos['duracion_h'].mean():.0f} h")
            st.metric("Máx duración", f"{eventos['duracion_h'].max()} h")
            st.metric("Temp. mín. alcanzada", f"{eventos['temp_min'].min():.1f} {unidad}")

    # ── Gráfico principal: serie temporal con zonas de surgencia ──
    with su2:
        st.markdown("### Serie temporal con eventos de surgencia")
        dp_s, resumido_s = resam(df_surg, col_t)
        if resumido_s:
            st.caption(f"Vista resumida · {len(dp_s):,} puntos")

        fig_surg = go.Figure()

        # Zonas de surgencia (rectángulos)
        for _, ev in eventos.iterrows():
            fig_surg.add_vrect(
                x0=ev["inicio"], x1=ev["fin"],
                fillcolor="rgba(41,128,185,0.2)",
                line_width=0,
                annotation_text="" ,
            )

        # Serie de temperatura
        fig_surg.add_trace(go.Scattergl(
            x=dp_s["fecha"], y=dp_s[col_t],
            mode="lines", name="Temperatura",
            line=dict(color=C["rojo"], width=1),
        ))

        # Línea de umbral
        fig_surg.add_hline(
            y=umbral_surgencia, line_dash="solid", line_color=C["azul"],
            line_width=2,
            annotation_text=f"Umbral: {umbral_surgencia:.1f} {unidad}",
            annotation_font_size=12,
            annotation_font_color=C["azul"],
        )

        # Zona sombreada bajo el umbral
        fig_surg.add_hrect(
            y0=df[col_t].min() - 1, y1=umbral_surgencia,
            fillcolor="rgba(41,128,185,0.05)", line_width=0,
        )

        fig_surg.update_layout(
            yaxis_title=f"Temperatura ({unidad})",
            template="plotly_white", height=500,
            hovermode="x unified",
            margin=dict(l=50, r=20, t=30, b=50),
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
        st.plotly_chart(fig_surg, use_container_width=True)

    # ── Estacionalidad de la surgencia ──
    st.markdown("---")
    st.subheader("Estacionalidad de la surgencia")

    if len(eventos) > 0:
        eventos["mes"] = eventos["inicio"].dt.month

        se1, se2 = st.columns(2)

        with se1:
            # Eventos por mes
            ev_mes = eventos.groupby("mes").agg(
                n_eventos=("duracion_h", "count"),
                horas_total=("duracion_h", "sum"),
                intensidad_media=("intensidad", "mean"),
            ).reindex(range(1, 13), fill_value=0).reset_index()

            fig_em = go.Figure()
            fig_em.add_trace(go.Bar(
                x=[MESES[m - 1] for m in ev_mes["mes"]],
                y=ev_mes["n_eventos"],
                marker_color=[C["azul"] if v > 0 else C["gris"] for v in ev_mes["n_eventos"]],
                name="Eventos",
            ))
            fig_em.update_layout(
                yaxis_title="Nº de eventos",
                template="plotly_white", height=350,
                title="Eventos de surgencia por mes",
                margin=dict(l=50, r=20, t=40, b=50),
            )
            st.plotly_chart(fig_em, use_container_width=True)

        with se2:
            # Horas de surgencia por mes
            fig_hm = go.Figure()
            fig_hm.add_trace(go.Bar(
                x=[MESES[m - 1] for m in ev_mes["mes"]],
                y=ev_mes["horas_total"],
                marker_color=[C["turquesa"] if v > 0 else C["gris"] for v in ev_mes["horas_total"]],
                name="Horas",
            ))
            fig_hm.update_layout(
                yaxis_title="Horas totales de surgencia",
                template="plotly_white", height=350,
                title="Horas de surgencia por mes",
                margin=dict(l=50, r=20, t=40, b=50),
            )
            st.plotly_chart(fig_hm, use_container_width=True)

        # ── Intensidad por mes ──
        st.subheader("Intensidad de la surgencia por mes")
        st.caption(
            "La intensidad se mide como la diferencia entre el umbral y la temperatura "
            "mínima alcanzada durante cada evento."
        )

        ev_con_mes = eventos[eventos["intensidad"] > 0].copy()
        if len(ev_con_mes) > 0:
            fig_int = go.Figure()
            for m in sorted(ev_con_mes["mes"].unique()):
                sub = ev_con_mes[ev_con_mes["mes"] == m]
                fig_int.add_trace(go.Box(
                    y=sub["intensidad"],
                    name=MESES[m - 1],
                    marker_color=f"hsl({(m - 1) * 30}, 65%, 50%)",
                    boxmean=True,
                ))
            fig_int.update_layout(
                yaxis_title=f"Intensidad (Δ{unidad} bajo umbral)",
                template="plotly_white", height=350,
                showlegend=False,
                margin=dict(l=50, r=20, t=20, b=50),
            )
            st.plotly_chart(fig_int, use_container_width=True)

        # ── Tendencia interanual ──
        st.subheader("Tendencia interanual de la surgencia")
        eventos["anio"] = eventos["inicio"].dt.year
        surg_anual = eventos.groupby("anio").agg(
            n_eventos=("duracion_h", "count"),
            horas_total=("duracion_h", "sum"),
            duracion_media=("duracion_h", "mean"),
            intensidad_media=("intensidad", "mean"),
            temp_min_anual=("temp_min", "min"),
        ).reset_index()

        ta1, ta2 = st.columns(2)

        with ta1:
            fig_ta = make_subplots(specs=[[{"secondary_y": True}]])
            fig_ta.add_trace(go.Bar(
                x=surg_anual["anio"], y=surg_anual["n_eventos"],
                name="Nº eventos", marker_color=C["azul"], opacity=0.7,
            ), secondary_y=False)
            fig_ta.add_trace(go.Scatter(
                x=surg_anual["anio"], y=surg_anual["horas_total"],
                name="Horas totales", mode="lines+markers",
                line=dict(color=C["rojo"], width=2),
            ), secondary_y=True)
            fig_ta.update_yaxes(title_text="Nº eventos", secondary_y=False)
            fig_ta.update_yaxes(title_text="Horas totales", secondary_y=True)
            fig_ta.update_layout(
                template="plotly_white", height=380,
                title="Frecuencia y duración por año",
                margin=dict(l=50, r=50, t=40, b=50),
            )
            st.plotly_chart(fig_ta, use_container_width=True)

        with ta2:
            fig_ta2 = go.Figure()
            fig_ta2.add_trace(go.Scatter(
                x=surg_anual["anio"], y=surg_anual["intensidad_media"],
                mode="lines+markers", name="Intensidad media",
                line=dict(color=C["morado"], width=2),
                marker=dict(size=7),
            ))
            fig_ta2.add_trace(go.Scatter(
                x=surg_anual["anio"], y=surg_anual["temp_min_anual"],
                mode="lines+markers", name=f"Temp. mín ({unidad})",
                line=dict(color=C["azul"], width=2, dash="dot"),
            ))
            fig_ta2.update_layout(
                yaxis_title=f"Temperatura / Intensidad ({unidad})",
                template="plotly_white", height=380,
                title="Intensidad y temperatura mínima por año",
                margin=dict(l=50, r=20, t=40, b=50),
            )
            st.plotly_chart(fig_ta2, use_container_width=True)

        # Tendencia estadística
        if len(surg_anual) >= 5:
            slope_ev, _, r_ev, p_ev, _ = sp_stats.linregress(
                surg_anual["anio"], surg_anual["horas_total"])
            st.info(
                f"**Tendencia horas de surgencia:** {slope_ev:+.1f} horas/año "
                f"(R²={r_ev**2:.3f}, p={p_ev:.4f}) — "
                f"{'✅ Significativa' if p_ev < 0.05 else '⚠️ No significativa'}"
            )

        # ── Heatmap Mes × Año de horas de surgencia ──
        st.subheader("Mapa de calor: Horas de surgencia (Mes × Año)")
        eventos["mes_ev"] = eventos["inicio"].dt.month
        hm_surg = eventos.groupby(["anio", "mes_ev"])["duracion_h"].sum().reset_index()
        pt_surg = hm_surg.pivot(index="anio", columns="mes_ev", values="duracion_h").fillna(0)
        # Asegurar todos los meses
        for m in range(1, 13):
            if m not in pt_surg.columns:
                pt_surg[m] = 0
        pt_surg = pt_surg[sorted(pt_surg.columns)]
        pt_surg.columns = [MESES[m - 1] for m in pt_surg.columns]

        fig_hms = go.Figure(data=go.Heatmap(
            z=pt_surg.values, x=pt_surg.columns, y=pt_surg.index,
            colorscale=[[0, "#ffffff"], [0.3, "#aed6f1"], [0.6, "#2980b9"], [1, "#1a5276"]],
            colorbar_title="Horas",
            hoverongaps=False,
            hovertemplate="Año: %{y}<br>Mes: %{x}<br>Horas: %{z:.0f}<extra></extra>",
        ))
        fig_hms.update_layout(
            yaxis_title="Año", template="plotly_white",
            height=max(300, len(pt_surg) * 22),
            margin=dict(l=60, r=20, t=20, b=50),
        )
        st.plotly_chart(fig_hms, use_container_width=True)

        # ── Tabla de eventos ──
        with st.expander(f"📋 Ver todos los {len(eventos)} eventos de surgencia"):
            tabla_ev = eventos[["inicio", "fin", "duracion_h", "temp_min", "temp_media", "intensidad"]].copy()
            tabla_ev.columns = [
                "Inicio", "Fin", "Duración (h)",
                f"Temp. mín ({unidad})", f"Temp. media ({unidad})",
                f"Intensidad (Δ{unidad})",
            ]
            for c in tabla_ev.columns[3:]:
                tabla_ev[c] = tabla_ev[c].round(2)
            st.dataframe(tabla_ev, use_container_width=True, height=400)

        # ── Descargar eventos ──
        st.markdown("---")
        csv_surg = eventos.to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇️ Descargar eventos de surgencia (CSV)",
            csv_surg,
            f"surgencia_{umbral_surgencia}{unidad}_{f_ini}_{f_fin}.csv",
            "text/csv",
        )

    else:
        st.info(
            f"No se detectaron eventos de surgencia con umbral {umbral_surgencia:.1f} {unidad} "
            f"y duración mínima de {duracion_min} horas en el período seleccionado. "
            f"Prueba ajustando el umbral o el rango de fechas."
        )


# ═══════════════════════════════════════════════════════════════
# TAB 5 — ANOMALÍAS
# ═══════════════════════════════════════════════════════════════
with tabs[5]:
    st.subheader("Detección de anomalías")
    st.caption("Identifica valores que se desvían significativamente de la media climatológica.")

    ac1, ac2 = st.columns([1, 3])
    with ac1:
        metodo = st.radio("Método", ["Z-score", "Percentiles", "Media móvil"])
        if metodo == "Z-score":
            umbral_z = st.slider("Umbral Z", 1.0, 4.0, 2.5, 0.1)
        elif metodo == "Percentiles":
            p_low = st.slider("Percentil inferior", 1, 20, 5)
            p_high = st.slider("Percentil superior", 80, 99, 95)
        else:
            ventana_anom = st.slider("Ventana (días)", 7, 90, 30)
            sigma_anom = st.slider("Nº de sigmas", 1.0, 4.0, 2.0, 0.1)

    df_anom = df.copy()

    if metodo == "Z-score":
        z_scores = np.abs((df_anom[col_t] - df_anom[col_t].mean()) / df_anom[col_t].std())
        df_anom["es_anomalia"] = z_scores > umbral_z
    elif metodo == "Percentiles":
        low = df_anom[col_t].quantile(p_low / 100)
        high = df_anom[col_t].quantile(p_high / 100)
        df_anom["es_anomalia"] = (df_anom[col_t] < low) | (df_anom[col_t] > high)
    else:
        w = ventana_anom * 24
        roll = df_anom.set_index("fecha")[[col_t]].resample("1h").mean()
        roll["media"] = roll[col_t].rolling(w, min_periods=24).mean()
        roll["std"] = roll[col_t].rolling(w, min_periods=24).std()
        roll["upper"] = roll["media"] + sigma_anom * roll["std"]
        roll["lower"] = roll["media"] - sigma_anom * roll["std"]
        roll = roll.dropna().reset_index()
        df_anom = df_anom.merge(roll[["fecha", "upper", "lower"]], on="fecha", how="inner")
        df_anom["es_anomalia"] = (df_anom[col_t] > df_anom["upper"]) | (df_anom[col_t] < df_anom["lower"])

    n_anom = df_anom["es_anomalia"].sum()
    pct_anom = n_anom / len(df_anom) * 100

    with ac1:
        st.metric("Anomalías", f"{n_anom:,}")
        st.metric("% del total", f"{pct_anom:.2f}%")

    with ac2:
        anomalias = df_anom[df_anom["es_anomalia"]]
        normales = df_anom[~df_anom["es_anomalia"]]
        norm_plot, _ = resam(normales, col_t)

        fig4 = go.Figure()
        fig4.add_trace(go.Scattergl(
            x=norm_plot["fecha"], y=norm_plot[col_t],
            mode="lines", name="Normal",
            line=dict(color=C["gris"], width=0.8),
        ))
        fig4.add_trace(go.Scattergl(
            x=anomalias["fecha"], y=anomalias[col_t],
            mode="markers", name="Anomalía",
            marker=dict(color=C["rojo"], size=4, opacity=0.6),
        ))
        fig4.update_layout(
            yaxis_title=f"Temp ({unidad})", template="plotly_white",
            height=450, hovermode="x unified",
            margin=dict(l=50, r=20, t=20, b=50),
        )
        st.plotly_chart(fig4, use_container_width=True)

    # Tabla de anomalías
    with st.expander(f"📋 Ver {min(n_anom, 500)} anomalías"):
        st.dataframe(
            anomalias[["fecha", col_t]].head(500).rename(
                columns={"fecha": "Fecha", col_t: f"Temp ({unidad})"}
            ),
            use_container_width=True, height=300,
        )


# ═══════════════════════════════════════════════════════════════
# TAB 6 — TENDENCIA
# ═══════════════════════════════════════════════════════════════
with tabs[6]:
    st.subheader("Tendencia interanual")

    df["anio"] = df["fecha"].dt.year
    pa = df.groupby("anio")[col_t].agg(["mean", "std", "min", "max", "count"]).reset_index()

    fig5 = go.Figure()
    fig5.add_trace(go.Scatter(
        x=list(pa["anio"]) + list(pa["anio"][::-1]),
        y=list(pa["max"]) + list(pa["min"][::-1]),
        fill="toself", fillcolor="rgba(231,76,60,0.08)",
        line=dict(color="rgba(0,0,0,0)"), name="Rango",
    ))
    fig5.add_trace(go.Scatter(
        x=pa["anio"], y=pa["mean"],
        mode="lines+markers", name="Promedio",
        line=dict(color=C["rojo"], width=2.5), marker=dict(size=7),
        error_y=dict(type="data", array=pa["std"], visible=True,
                     color="rgba(0,0,0,0.1)"),
    ))

    if len(pa) >= 3:
        z = np.polyfit(pa["anio"], pa["mean"], 1)
        p_line = np.poly1d(z)
        fig5.add_trace(go.Scatter(
            x=pa["anio"], y=p_line(pa["anio"]),
            mode="lines",
            name=f"Tendencia: {z[0]:+.4f} {unidad}/año",
            line=dict(color=C["oscuro"], dash="dash", width=2),
        ))

        # Test de significancia estadística
        slope, intercept, r_val, p_val, std_err = sp_stats.linregress(pa["anio"], pa["mean"])
        sig = "✅ Significativa" if p_val < 0.05 else "⚠️ No significativa"

        tc1, tc2, tc3, tc4 = st.columns(4)
        tc1.metric("Pendiente", f"{slope:+.4f} {unidad}/año")
        tc2.metric("Por década", f"{slope * 10:+.3f} {unidad}")
        tc3.metric("R²", f"{r_val**2:.3f}")
        tc4.metric("p-valor", f"{p_val:.4f} ({sig})")

    fig5.update_layout(
        xaxis_title="Año", yaxis_title=f"Temp ({unidad})",
        template="plotly_white", height=500,
        margin=dict(l=50, r=20, t=30, b=50),
    )
    st.plotly_chart(fig5, use_container_width=True)

    # Tendencia por estación (seca vs lluviosa)
    st.subheader("Tendencia por temporada")
    st.caption("Panamá: Seca (Dic–Abr) vs Lluviosa (May–Nov)")
    df["mes"] = df["fecha"].dt.month
    df["temporada"] = df["mes"].apply(lambda m: "Seca (Dic-Abr)" if m <= 4 or m == 12 else "Lluviosa (May-Nov)")

    fig5b = go.Figure()
    colores_temp = {"Seca (Dic-Abr)": C["naranja"], "Lluviosa (May-Nov)": C["azul"]}
    for temp_name in ["Seca (Dic-Abr)", "Lluviosa (May-Nov)"]:
        sub = df[df["temporada"] == temp_name]
        pa_t = sub.groupby("anio")[col_t].mean().reset_index()
        fig5b.add_trace(go.Scatter(
            x=pa_t["anio"], y=pa_t[col_t],
            mode="lines+markers", name=temp_name,
            line=dict(color=colores_temp[temp_name], width=2),
        ))
        if len(pa_t) >= 3:
            zt = np.polyfit(pa_t["anio"], pa_t[col_t], 1)
            pt = np.poly1d(zt)
            fig5b.add_trace(go.Scatter(
                x=pa_t["anio"], y=pt(pa_t["anio"]),
                mode="lines", showlegend=False,
                line=dict(color=colores_temp[temp_name], dash="dot", width=1.5),
            ))

    fig5b.update_layout(
        xaxis_title="Año", yaxis_title=f"Temp ({unidad})",
        template="plotly_white", height=400,
        margin=dict(l=50, r=20, t=20, b=50),
    )
    st.plotly_chart(fig5b, use_container_width=True)

    df.drop(columns=["anio", "mes", "temporada"], inplace=True, errors="ignore")


# ═══════════════════════════════════════════════════════════════
# TAB 7 — COMPARAR AÑOS
# ═══════════════════════════════════════════════════════════════
with tabs[7]:
    st.subheader("Comparación año a año")

    df["anio"] = df["fecha"].dt.year
    anios_disponibles = sorted(df["anio"].unique())

    anios_sel = st.multiselect(
        "Selecciona años a comparar",
        anios_disponibles,
        default=anios_disponibles[-3:] if len(anios_disponibles) >= 3 else anios_disponibles,
    )

    if anios_sel:
        fig6 = go.Figure()
        colores_anio = [C["rojo"], C["azul"], C["verde"], C["naranja"],
                        C["morado"], C["turquesa"], C["oscuro"], C["amarillo"]]

        for i, anio in enumerate(sorted(anios_sel)):
            sub = df[df["anio"] == anio].copy()
            sub["dia_anio"] = sub["fecha"].dt.dayofyear
            diario = sub.groupby("dia_anio")[col_t].mean().reset_index()
            # suavizar
            diario["smooth"] = diario[col_t].rolling(7, center=True, min_periods=1).mean()

            fig6.add_trace(go.Scatter(
                x=diario["dia_anio"], y=diario["smooth"],
                mode="lines", name=str(anio),
                line=dict(color=colores_anio[i % len(colores_anio)], width=2),
            ))

        # Eje X con nombres de mes
        tickvals = [1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335]
        fig6.update_layout(
            xaxis=dict(
                title="Mes",
                tickvals=tickvals,
                ticktext=MESES,
            ),
            yaxis_title=f"Temp ({unidad})",
            template="plotly_white", height=500,
            hovermode="x unified",
            margin=dict(l=50, r=20, t=20, b=50),
        )
        st.plotly_chart(fig6, use_container_width=True)

        # Tabla comparativa
        st.subheader("Tabla comparativa")
        filas = []
        for anio in sorted(anios_sel):
            sub = df[df["anio"] == anio]
            filas.append({
                "Año": anio,
                f"Promedio ({unidad})": round(sub[col_t].mean(), 2),
                f"Máx ({unidad})": round(sub[col_t].max(), 2),
                f"Mín ({unidad})": round(sub[col_t].min(), 2),
                f"Rango ({unidad})": round(sub[col_t].max() - sub[col_t].min(), 2),
                f"Desv.Est.": round(sub[col_t].std(), 2),
                "Registros": len(sub),
            })
        st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)

    df.drop(columns=["anio"], inplace=True, errors="ignore")


# ═══════════════════════════════════════════════════════════════
# TAB 8 — UMBRALES
# ═══════════════════════════════════════════════════════════════
with tabs[8]:
    st.subheader("Análisis de excedencia de umbrales")
    st.caption("¿Cuánto tiempo la temperatura supera o cae por debajo de ciertos valores críticos?")

    uc1, uc2 = st.columns([1, 3])
    with uc1:
        umbral_alto = st.number_input(
            f"Umbral alto ({unidad})",
            value=round(df[col_t].quantile(0.9), 1),
            step=0.5,
        )
        umbral_bajo = st.number_input(
            f"Umbral bajo ({unidad})",
            value=round(df[col_t].quantile(0.1), 1),
            step=0.5,
        )

    sobre = df[df[col_t] > umbral_alto]
    bajo = df[df[col_t] < umbral_bajo]
    pct_sobre = len(sobre) / len(df) * 100
    pct_bajo = len(bajo) / len(df) * 100
    horas_sobre = len(sobre)  # cada registro ≈ 1 hora
    horas_bajo = len(bajo)

    with uc1:
        st.markdown("---")
        st.metric(f"Sobre {umbral_alto}{unidad}", f"{pct_sobre:.1f}% ({horas_sobre:,}h)")
        st.metric(f"Bajo {umbral_bajo}{unidad}", f"{pct_bajo:.1f}% ({horas_bajo:,}h)")

    with uc2:
        fig7 = go.Figure()
        df_p, _ = resam(df, col_t)
        fig7.add_trace(go.Scattergl(
            x=df_p["fecha"], y=df_p[col_t],
            mode="lines", name="Temperatura",
            line=dict(color=C["gris"], width=0.8),
        ))
        fig7.add_hrect(y0=umbral_alto, y1=df[col_t].max() + 1,
                       fillcolor="rgba(231,76,60,0.15)", line_width=0)
        fig7.add_hrect(y0=df[col_t].min() - 1, y1=umbral_bajo,
                       fillcolor="rgba(41,128,185,0.15)", line_width=0)
        fig7.add_hline(y=umbral_alto, line_dash="dash", line_color=C["rojo"],
                       annotation_text=f"Alto: {umbral_alto}{unidad}")
        fig7.add_hline(y=umbral_bajo, line_dash="dash", line_color=C["azul"],
                       annotation_text=f"Bajo: {umbral_bajo}{unidad}")
        fig7.update_layout(
            yaxis_title=f"Temp ({unidad})", template="plotly_white",
            height=450, hovermode="x unified",
            margin=dict(l=50, r=20, t=20, b=50),
        )
        st.plotly_chart(fig7, use_container_width=True)

    # Exceedance por año
    st.subheader("Horas de excedencia por año")
    df["anio"] = df["fecha"].dt.year
    exc_anio = df.groupby("anio").apply(
        lambda g: pd.Series({
            f"Horas > {umbral_alto}{unidad}": (g[col_t] > umbral_alto).sum(),
            f"Horas < {umbral_bajo}{unidad}": (g[col_t] < umbral_bajo).sum(),
            "Total registros": len(g),
        })
    ).reset_index()

    fig7b = make_subplots(specs=[[{"secondary_y": True}]])
    fig7b.add_trace(go.Bar(
        x=exc_anio["anio"], y=exc_anio[f"Horas > {umbral_alto}{unidad}"],
        name=f"> {umbral_alto}{unidad}", marker_color=C["rojo"], opacity=0.7,
    ))
    fig7b.add_trace(go.Bar(
        x=exc_anio["anio"], y=exc_anio[f"Horas < {umbral_bajo}{unidad}"],
        name=f"< {umbral_bajo}{unidad}", marker_color=C["azul"], opacity=0.7,
    ))
    fig7b.update_layout(
        barmode="group", template="plotly_white",
        yaxis_title="Horas", height=380,
        margin=dict(l=50, r=20, t=20, b=50),
    )
    st.plotly_chart(fig7b, use_container_width=True)
    df.drop(columns=["anio"], inplace=True, errors="ignore")


# ═══════════════════════════════════════════════════════════════
# TAB 9 — CALIDAD DE DATOS
# ═══════════════════════════════════════════════════════════════
with tabs[9]:
    st.subheader("Diagnóstico de calidad de datos")

    # Gaps (vacíos)
    df_sorted = df.sort_values("fecha")
    deltas = df_sorted["fecha"].diff()
    freq_esperada = deltas.median()
    gaps = deltas[deltas > freq_esperada * 3]  # gap = más de 3x la frecuencia normal

    qc1, qc2, qc3, qc4 = st.columns(4)
    qc1.metric("Registros", f"{len(df):,}")
    qc2.metric("Frecuencia", f"{freq_esperada}")
    qc3.metric("Vacíos detectados", f"{len(gaps)}")
    qc4.metric("Mayor vacío", f"{gaps.max()}" if len(gaps) > 0 else "N/A")

    # Cobertura por año
    st.subheader("Cobertura de datos por año")
    df["anio"] = df["fecha"].dt.year
    registros_esperados_anio = 365.25 * 24  # ~8766 por año
    cob = df.groupby("anio").size().reset_index(name="registros")
    cob["cobertura_pct"] = (cob["registros"] / registros_esperados_anio * 100).clip(upper=100).round(1)

    fig8a = go.Figure()
    fig8a.add_trace(go.Bar(
        x=cob["anio"], y=cob["cobertura_pct"],
        marker_color=[C["verde"] if v >= 90 else C["naranja"] if v >= 50 else C["rojo"]
                      for v in cob["cobertura_pct"]],
        text=[f"{v}%" for v in cob["cobertura_pct"]],
        textposition="auto",
    ))
    fig8a.add_hline(y=90, line_dash="dash", line_color=C["verde"],
                    annotation_text="90% (buena cobertura)")
    fig8a.update_layout(
        yaxis_title="Cobertura (%)", yaxis_range=[0, 105],
        template="plotly_white", height=350,
        margin=dict(l=50, r=20, t=20, b=50),
    )
    st.plotly_chart(fig8a, use_container_width=True)

    # Cobertura por mes (heatmap)
    st.subheader("Cobertura por mes × año")
    df["mes"] = df["fecha"].dt.month
    cob_m = df.groupby(["anio", "mes"]).size().reset_index(name="n")
    # horas esperadas por mes
    cob_m["esperado"] = cob_m["mes"].apply(lambda m: calendar.monthrange(2024, m)[1] * 24)
    cob_m["pct"] = (cob_m["n"] / cob_m["esperado"] * 100).clip(upper=100).round(0)
    pt_cob = cob_m.pivot(index="anio", columns="mes", values="pct")
    pt_cob.columns = [MESES[m - 1] for m in pt_cob.columns]

    fig8b = go.Figure(data=go.Heatmap(
        z=pt_cob.values, x=pt_cob.columns, y=pt_cob.index,
        colorscale=[[0, "#e74c3c"], [0.5, "#f39c12"], [0.9, "#f9e79f"], [1, "#27ae60"]],
        colorbar_title="%",
        hoverongaps=False,
        zmin=0, zmax=100,
    ))
    fig8b.update_layout(
        yaxis_title="Año", template="plotly_white",
        height=max(300, len(pt_cob) * 20),
        margin=dict(l=60, r=20, t=20, b=50),
    )
    st.plotly_chart(fig8b, use_container_width=True)
    st.caption("🟢 Verde = buena cobertura, 🟡 Amarillo = parcial, 🔴 Rojo = poca o sin datos")

    # Timeline de gaps grandes
    if len(gaps) > 0:
        st.subheader("Vacíos más grandes")
        gap_indices = gaps.index.tolist()
        gap_rows = []
        for gi in gap_indices:
            pos = df_sorted.index.get_loc(gi) if gi in df_sorted.index else None
            if pos is not None and pos > 0:
                gap_rows.append({
                    "Inicio": df_sorted["fecha"].iloc[pos - 1],
                    "Fin": df_sorted["fecha"].iloc[pos],
                    "Duración": str(gaps.loc[gi]),
                })
        if gap_rows:
            gap_df = pd.DataFrame(gap_rows).sort_values("Duración", ascending=False).head(20).reset_index(drop=True)
            st.dataframe(gap_df, use_container_width=True, hide_index=True)

    df.drop(columns=["anio", "mes"], inplace=True, errors="ignore")


# ═══════════════════════════════════════════════════════════════
# TAB — TEMP VS MAREA
# ═══════════════════════════════════════════════════════════════
idx_tab = 10
if df_marea is not None:
    with tabs[idx_tab]:
        st.subheader("Correlación: Temperatura vs Nivel de marea")

        temp_h = df.set_index("fecha")[[col_t]].resample("1h").mean()
        marea_h = df_marea.set_index("fecha")[["nivel_ft"]].resample("1h").mean()
        merged = temp_h.join(marea_h, how="inner").dropna().reset_index()

        if len(merged) < 50:
            st.warning("Pocos datos coincidentes.")
        else:
            st.metric("Registros coincidentes", f"{len(merged):,}")

            mc1, mc2 = st.columns(2)
            with mc1:
                # Scatter
                sample = merged.sample(min(5000, len(merged)), random_state=42)
                corr = merged[col_t].corr(merged["nivel_ft"])
                fig_mc = go.Figure()
                fig_mc.add_trace(go.Scattergl(
                    x=sample["nivel_ft"], y=sample[col_t],
                    mode="markers",
                    marker=dict(color=C["rojo"], size=3, opacity=0.3),
                ))
                fig_mc.update_layout(
                    xaxis_title="Nivel (ft)", yaxis_title=f"Temp ({unidad})",
                    title=f"r = {corr:.3f}",
                    template="plotly_white", height=400,
                    margin=dict(l=50, r=20, t=50, b=50),
                )
                st.plotly_chart(fig_mc, use_container_width=True)

            with mc2:
                # Doble eje
                m_plot = merged.set_index("fecha").resample("6h").mean().dropna().reset_index()
                if len(m_plot) > 8000:
                    m_plot = m_plot.set_index("fecha").resample("1D").mean().dropna().reset_index()
                fig_mc2 = make_subplots(specs=[[{"secondary_y": True}]])
                fig_mc2.add_trace(go.Scattergl(
                    x=m_plot["fecha"], y=m_plot[col_t],
                    mode="lines", name=f"Temp ({unidad})",
                    line=dict(color=C["rojo"], width=1),
                ), secondary_y=False)
                fig_mc2.add_trace(go.Scattergl(
                    x=m_plot["fecha"], y=m_plot["nivel_ft"],
                    mode="lines", name="Marea (ft)",
                    line=dict(color=C["azul"], width=1),
                ), secondary_y=True)
                fig_mc2.update_yaxes(title_text=f"Temp ({unidad})", secondary_y=False)
                fig_mc2.update_yaxes(title_text="Nivel (ft)", secondary_y=True)
                fig_mc2.update_layout(
                    template="plotly_white", height=400,
                    hovermode="x unified",
                    margin=dict(l=50, r=60, t=30, b=50),
                )
                st.plotly_chart(fig_mc2, use_container_width=True)

            # Correlación por lag
            st.subheader("Correlación con desfase temporal")
            st.caption("¿La temperatura sigue al nivel de marea con retraso?")
            lags_h = range(-48, 49, 2)
            corrs = []
            for lag in lags_h:
                shifted = merged[col_t].shift(lag)
                corrs.append(shifted.corr(merged["nivel_ft"]))
            fig_lag = go.Figure()
            fig_lag.add_trace(go.Scatter(
                x=list(lags_h), y=corrs,
                mode="lines+markers",
                line=dict(color=C["morado"], width=2),
                marker=dict(size=3),
            ))
            fig_lag.add_vline(x=0, line_dash="dash", line_color=C["gris"])
            best_lag = list(lags_h)[np.argmax(np.abs(corrs))]
            fig_lag.add_vline(x=best_lag, line_dash="dot", line_color=C["rojo"],
                              annotation_text=f"Mejor: {best_lag}h")
            fig_lag.update_layout(
                xaxis_title="Desfase (horas, + = temp adelanta)",
                yaxis_title="Correlación (r)",
                template="plotly_white", height=350,
                margin=dict(l=50, r=20, t=20, b=50),
            )
            st.plotly_chart(fig_lag, use_container_width=True)

    idx_tab += 1


# ═══════════════════════════════════════════════════════════════
# TAB — TEMP VS VIENTO
# ═══════════════════════════════════════════════════════════════
if df_viento is not None:
    with tabs[idx_tab]:
        st.subheader("💨 Correlación: Temperatura del Agua vs Velocidad del Viento")
        st.caption(
            "Analiza la relación entre la temperatura del agua y la velocidad del viento. "
            "El viento fuerte puede inducir mezcla y surgencia, enfriando la superficie."
        )

        # ── Unidad de viento ──
        u_viento = st.radio("Unidad de viento", ["m/s", "km/h", "nudos (kt)"],
                            horizontal=True, key="uviento")
        col_v = {"m/s": "viento_ms", "km/h": "viento_kmh", "nudos (kt)": "viento_kt"}[u_viento]
        uv = u_viento.split(" ")[0]

        # ── Merge por hora ──
        temp_h = df.set_index("fecha")[[col_t]].resample("1h").mean()
        viento_h = df_viento.set_index("fecha")[[col_v]].resample("1h").mean()
        mv = temp_h.join(viento_h, how="inner").dropna().reset_index()

        if len(mv) < 50:
            st.warning("Pocos datos coincidentes entre temperatura y viento.")
        else:
            corr_tv = mv[col_t].corr(mv[col_v])

            # KPIs
            vk1, vk2, vk3, vk4 = st.columns(4)
            vk1.metric("Datos coincidentes", f"{len(mv):,}")
            vk2.metric("Correlación (r)", f"{corr_tv:.3f}")
            vk3.metric(f"Viento promedio", f"{mv[col_v].mean():.1f} {uv}")
            vk4.metric(f"Viento máximo", f"{mv[col_v].max():.1f} {uv}")

            st.markdown("---")

            # ── Scatter plot ──
            vc1, vc2 = st.columns(2)

            with vc1:
                st.markdown("### Dispersión Viento vs Temperatura")
                sample = mv.sample(min(5000, len(mv)), random_state=42)

                fig_vs = go.Figure()
                fig_vs.add_trace(go.Scattergl(
                    x=sample[col_v], y=sample[col_t],
                    mode="markers",
                    marker=dict(
                        color=sample[col_t], colorscale="RdYlBu_r",
                        size=3, opacity=0.4,
                        colorbar=dict(title=unidad),
                    ),
                    name="Datos",
                ))

                # Línea de tendencia
                z_tv = np.polyfit(mv[col_v], mv[col_t], 1)
                x_trend = np.linspace(mv[col_v].min(), mv[col_v].max(), 100)
                fig_vs.add_trace(go.Scatter(
                    x=x_trend, y=np.polyval(z_tv, x_trend),
                    mode="lines", name=f"Tendencia (r={corr_tv:.3f})",
                    line=dict(color=C["rojo"], width=2, dash="dash"),
                ))

                fig_vs.update_layout(
                    xaxis_title=f"Velocidad del viento ({uv})",
                    yaxis_title=f"Temperatura ({unidad})",
                    template="plotly_white", height=450,
                    margin=dict(l=50, r=20, t=20, b=50),
                )
                st.plotly_chart(fig_vs, use_container_width=True)

            with vc2:
                st.markdown("### Serie temporal superpuesta")
                mv_plot = mv.set_index("fecha").resample("6h").mean().dropna().reset_index()
                if len(mv_plot) > 8000:
                    mv_plot = mv_plot.set_index("fecha").resample("1D").mean().dropna().reset_index()

                fig_vt = make_subplots(specs=[[{"secondary_y": True}]])
                fig_vt.add_trace(go.Scattergl(
                    x=mv_plot["fecha"], y=mv_plot[col_t],
                    mode="lines", name=f"Temp ({unidad})",
                    line=dict(color=C["rojo"], width=1.2),
                ), secondary_y=False)
                fig_vt.add_trace(go.Scattergl(
                    x=mv_plot["fecha"], y=mv_plot[col_v],
                    mode="lines", name=f"Viento ({uv})",
                    line=dict(color=C["azul"], width=1.2),
                ), secondary_y=True)
                fig_vt.update_yaxes(title_text=f"Temp ({unidad})", secondary_y=False)
                fig_vt.update_yaxes(title_text=f"Viento ({uv})", secondary_y=True)
                fig_vt.update_layout(
                    template="plotly_white", height=450,
                    hovermode="x unified",
                    margin=dict(l=50, r=60, t=20, b=50),
                )
                st.plotly_chart(fig_vt, use_container_width=True)

            # ── Temperatura por rangos de viento ──
            st.markdown("---")
            st.subheader("Temperatura según intensidad del viento")
            st.caption("¿Cómo cambia la temperatura del agua según qué tan fuerte sopla el viento?")

            # Clasificación Beaufort simplificada
            if col_v == "viento_ms":
                bins = [0, 1.5, 3.3, 5.5, 8.0, 10.8, 50]
                labels = ["Calma (<1.5)", "Brisa ligera (1.5-3.3)", "Brisa suave (3.3-5.5)",
                          "Brisa moderada (5.5-8)", "Brisa fresca (8-10.8)", "Fuerte (>10.8)"]
            elif col_v == "viento_kmh":
                bins = [0, 5.4, 11.9, 19.8, 28.8, 38.9, 200]
                labels = ["Calma (<5.4)", "Brisa ligera (5.4-12)", "Brisa suave (12-20)",
                          "Brisa moderada (20-29)", "Brisa fresca (29-39)", "Fuerte (>39)"]
            else:  # nudos
                bins = [0, 3, 6.5, 10.5, 15.5, 21, 100]
                labels = ["Calma (<3)", "Brisa ligera (3-6.5)", "Brisa suave (6.5-10.5)",
                          "Brisa moderada (10.5-15.5)", "Brisa fresca (15.5-21)", "Fuerte (>21)"]

            mv["rango_viento"] = pd.cut(mv[col_v], bins=bins, labels=labels, include_lowest=True)

            vr1, vr2 = st.columns(2)

            with vr1:
                fig_box_v = go.Figure()
                colores_beaufort = [C["verde"], C["turquesa"], C["azul"],
                                    C["naranja"], C["rojo"], C["morado"]]
                for i, label in enumerate(labels):
                    sub = mv[mv["rango_viento"] == label]
                    if len(sub) > 0:
                        fig_box_v.add_trace(go.Box(
                            y=sub[col_t], name=label.split("(")[0].strip(),
                            marker_color=colores_beaufort[i % len(colores_beaufort)],
                            boxmean=True,
                        ))
                fig_box_v.update_layout(
                    yaxis_title=f"Temperatura ({unidad})",
                    template="plotly_white", height=420,
                    showlegend=False,
                    margin=dict(l=50, r=20, t=20, b=80),
                )
                st.plotly_chart(fig_box_v, use_container_width=True)

            with vr2:
                # Tabla resumen por rango
                resumen_v = mv.groupby("rango_viento", observed=True).agg(
                    n=(col_t, "count"),
                    temp_media=(col_t, "mean"),
                    temp_min=(col_t, "min"),
                    temp_max=(col_t, "max"),
                    viento_medio=(col_v, "mean"),
                ).reset_index()
                resumen_v.columns = [
                    "Rango de viento", "N registros",
                    f"Temp media ({unidad})", f"Temp mín ({unidad})",
                    f"Temp máx ({unidad})", f"Viento medio ({uv})",
                ]
                for c in resumen_v.columns[2:]:
                    resumen_v[c] = resumen_v[c].round(2)
                st.dataframe(resumen_v, use_container_width=True, hide_index=True)

                # Porcentaje de tiempo en cada rango
                fig_pie = go.Figure()
                fig_pie.add_trace(go.Pie(
                    labels=[l.split("(")[0].strip() for l in labels if
                            len(mv[mv["rango_viento"] == l]) > 0],
                    values=[len(mv[mv["rango_viento"] == l]) for l in labels if
                            len(mv[mv["rango_viento"] == l]) > 0],
                    marker_colors=colores_beaufort,
                    hole=0.4,
                ))
                fig_pie.update_layout(
                    height=280, template="plotly_white",
                    margin=dict(l=10, r=10, t=20, b=10),
                    title=dict(text="% de tiempo por intensidad", font_size=13),
                )
                st.plotly_chart(fig_pie, use_container_width=True)

            # ── Ciclos diarios comparados ──
            st.markdown("---")
            st.subheader("Ciclos diarios: Temperatura vs Viento")
            mv["hora"] = mv["fecha"].dt.hour
            ciclo_tv = mv.groupby("hora").agg(
                temp_media=(col_t, "mean"),
                viento_medio=(col_v, "mean"),
            ).reset_index()

            fig_ciclo_tv = make_subplots(specs=[[{"secondary_y": True}]])
            fig_ciclo_tv.add_trace(go.Scatter(
                x=ciclo_tv["hora"], y=ciclo_tv["temp_media"],
                mode="lines+markers", name=f"Temp ({unidad})",
                line=dict(color=C["rojo"], width=2.5), marker=dict(size=6),
            ), secondary_y=False)
            fig_ciclo_tv.add_trace(go.Scatter(
                x=ciclo_tv["hora"], y=ciclo_tv["viento_medio"],
                mode="lines+markers", name=f"Viento ({uv})",
                line=dict(color=C["azul"], width=2.5), marker=dict(size=6),
            ), secondary_y=True)
            fig_ciclo_tv.update_yaxes(title_text=f"Temp ({unidad})", secondary_y=False)
            fig_ciclo_tv.update_yaxes(title_text=f"Viento ({uv})", secondary_y=True)
            fig_ciclo_tv.update_layout(
                xaxis_title="Hora del día", template="plotly_white",
                height=380, margin=dict(l=50, r=60, t=20, b=50),
            )
            st.plotly_chart(fig_ciclo_tv, use_container_width=True)

            # ── Estacional ──
            st.subheader("Ciclos mensuales: Temperatura vs Viento")
            mv["mes"] = mv["fecha"].dt.month
            ciclo_mes_tv = mv.groupby("mes").agg(
                temp_media=(col_t, "mean"),
                viento_medio=(col_v, "mean"),
            ).reset_index()

            fig_mes_tv = make_subplots(specs=[[{"secondary_y": True}]])
            fig_mes_tv.add_trace(go.Bar(
                x=[MESES[m-1] for m in ciclo_mes_tv["mes"]],
                y=ciclo_mes_tv["temp_media"], name=f"Temp ({unidad})",
                marker_color=C["rojo"], opacity=0.7,
            ), secondary_y=False)
            fig_mes_tv.add_trace(go.Scatter(
                x=[MESES[m-1] for m in ciclo_mes_tv["mes"]],
                y=ciclo_mes_tv["viento_medio"], name=f"Viento ({uv})",
                mode="lines+markers",
                line=dict(color=C["azul"], width=2.5), marker=dict(size=8),
            ), secondary_y=True)
            fig_mes_tv.update_yaxes(title_text=f"Temp ({unidad})", secondary_y=False)
            fig_mes_tv.update_yaxes(title_text=f"Viento ({uv})", secondary_y=True)
            fig_mes_tv.update_layout(
                template="plotly_white", height=400,
                margin=dict(l=50, r=60, t=20, b=50),
            )
            st.plotly_chart(fig_mes_tv, use_container_width=True)

            # ── Correlación con desfase ──
            st.subheader("Correlación con desfase temporal")
            st.caption("¿La temperatura responde al viento con retraso?")
            lags_v = range(-48, 49, 2)
            corrs_v = []
            for lag in lags_v:
                shifted = mv[col_t].shift(lag)
                corrs_v.append(shifted.corr(mv[col_v]))
            fig_lag_v = go.Figure()
            fig_lag_v.add_trace(go.Scatter(
                x=list(lags_v), y=corrs_v,
                mode="lines+markers",
                line=dict(color=C["morado"], width=2), marker=dict(size=3),
            ))
            fig_lag_v.add_vline(x=0, line_dash="dash", line_color=C["gris"])
            best_lag_v = list(lags_v)[np.argmin(corrs_v)]  # más negativo = más enfriamiento
            fig_lag_v.add_vline(x=best_lag_v, line_dash="dot", line_color=C["rojo"],
                annotation_text=f"Máx efecto: {best_lag_v}h")
            fig_lag_v.update_layout(
                xaxis_title="Desfase (horas, + = temp adelanta)",
                yaxis_title="Correlación (r)",
                template="plotly_white", height=350,
                margin=dict(l=50, r=20, t=20, b=50),
            )
            st.plotly_chart(fig_lag_v, use_container_width=True)

            # ── Viento y surgencia ──
            st.markdown("---")
            st.subheader("¿El viento fuerte induce enfriamiento?")
            umbral_v_fuerte = st.slider(
                f"Umbral de viento fuerte ({uv})", 
                float(mv[col_v].quantile(0.5)),
                float(mv[col_v].max()),
                float(mv[col_v].quantile(0.75)),
                0.5,
            )

            mv["viento_fuerte"] = mv[col_v] >= umbral_v_fuerte
            temp_con_viento = mv[mv["viento_fuerte"]][col_t].mean()
            temp_sin_viento = mv[~mv["viento_fuerte"]][col_t].mean()
            delta_t = temp_con_viento - temp_sin_viento

            vf1, vf2, vf3 = st.columns(3)
            vf1.metric(f"Temp con viento ≥{umbral_v_fuerte:.1f}",
                       f"{temp_con_viento:.2f} {unidad}")
            vf2.metric(f"Temp con viento <{umbral_v_fuerte:.1f}",
                       f"{temp_sin_viento:.2f} {unidad}")
            vf3.metric("Diferencia", f"{delta_t:+.2f} {unidad}")

            if delta_t < 0:
                st.success(
                    f"El viento fuerte está asociado con una reducción de "
                    f"**{abs(delta_t):.2f} {unidad}** en la temperatura del agua, "
                    f"consistente con mezcla vertical y/o surgencia inducida por viento."
                )
            else:
                st.info(
                    f"No se detecta enfriamiento asociado al viento fuerte en este período. "
                    f"Puede depender de la dirección del viento y la batimetría local."
                )

            # Descargar merge
            st.markdown("---")
            csv_tv = mv[["fecha", col_t, col_v]].to_csv(index=False).encode("utf-8")
            st.download_button(
                "⬇️ Descargar datos temp+viento (CSV)", csv_tv,
                f"temp_viento_{f_ini}_{f_fin}.csv", "text/csv",
            )

    idx_tab += 1


# ═══════════════════════════════════════════════════════════════
# TAB — EXPORTAR
# ═══════════════════════════════════════════════════════════════
with tabs[idx_tab]:
    st.subheader("Exportar resultados")

    ec1, ec2, ec3 = st.columns(3)

    with ec1:
        st.markdown("#### Datos horarios")
        csv1 = df.to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ CSV horario", csv1,
                           f"temp_horaria_{f_ini}_{f_fin}.csv", "text/csv")

    with ec2:
        st.markdown("#### Promedios diarios")
        diario = df.set_index("fecha")[[col_t]].resample("1D").agg(
            ["mean", "min", "max"]).round(2).dropna().reset_index()
        diario.columns = ["Fecha", "Promedio", "Mínimo", "Máximo"]
        csv2 = diario.to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ CSV diario", csv2,
                           f"temp_diaria_{f_ini}_{f_fin}.csv", "text/csv")

    with ec3:
        st.markdown("#### Promedios mensuales")
        mensual = df.set_index("fecha")[[col_t]].resample("1MS").agg(
            ["mean", "min", "max", "std"]).round(2).dropna().reset_index()
        mensual.columns = ["Fecha", "Promedio", "Mínimo", "Máximo", "Desv.Est."]
        csv3 = mensual.to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ CSV mensual", csv3,
                           f"temp_mensual_{f_ini}_{f_fin}.csv", "text/csv")

    st.markdown("---")
    st.dataframe(df.head(200), use_container_width=True, height=300)


# ═══════════════════════════════════════════════════════════════
# FOOTER
# ═══════════════════════════════════════════════════════════════
st.markdown("---")
st.markdown(
    "<div style='text-align:center; color:#aab7b8; font-size:0.85rem;'>"
    "🌡️ Dashboard de Temperatura del Agua · Canal de Panamá · "
    "Datos: Autoridad del Canal de Panamá (ACP)<br>"
    "Creador: JFRodriguez</div>",
    unsafe_allow_html=True,
)
