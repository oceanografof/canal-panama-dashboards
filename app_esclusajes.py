"""
🚢 Dashboard de Consumo de Esclusajes — Canal de Panamá
========================================================
Análisis comparativo del consumo de agua por esclusas.

INSTALACIÓN:
    pip install streamlit pandas numpy plotly scipy openpyxl

EJECUCIÓN:
    py -m streamlit run app_esclusajes.py

Creador: JFRodriguez
"""

import glob
import os
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots
from scipy import stats as sp_stats

st.set_page_config(page_title="🚢 Esclusajes — Canal de Panamá", page_icon="🚢", layout="wide")

MESES_FISCALES = ["Oct", "Nov", "Dic", "Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep"]
MESES_CAL = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
MESES_NUM_A_NOMBRE = {
    1: "Ene", 2: "Feb", 3: "Mar", 4: "Abr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Ago", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dic"
}
DOW_NOMBRE = {0: "Lun", 1: "Mar", 2: "Mié", 3: "Jue", 4: "Vie", 5: "Sáb", 6: "Dom"}
DOW_ORDEN = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
FACTOR_HM3_A_MCF = 35314.6667  # 1 hm³ = 35,314.6667 mil pies³

COL = {
    "Gatún": "#2980b9",
    "Pedro Miguel": "#e67e22",
    "Agua Clara": "#27ae60",
    "Cocolí": "#8e44ad",
    "Total PNX": "#2c3e50",
    "Total NPX": "#16a085",
    "Total": "#c0392b",
    "Tránsitos": "#34495e",
}


def encontrar_logo():
    candidatos = [
        "LOGO HIMH.jpg",
        "LOGO HIMH.jpeg",
        "LOGO HIMH.png",
        "LOGO%20HIMH.jpg",
        "LOGO%20HIMH.jpeg",
        "LOGO%20HIMH.png",
    ]
    for nombre in candidatos:
        if Path(nombre).exists():
            return nombre
        full = Path("/mnt/data") / nombre
        if full.exists():
            return str(full)
    return None


@st.cache_data(show_spinner="Cargando datos de esclusajes...")
def cargar_datos(fuente):
    try:
        df = pd.read_excel(fuente, sheet_name="Data")
    except ValueError:
        df = pd.read_excel(fuente)

    if "actdate" not in df.columns:
        raise ValueError("No se encontró la columna 'actdate' en la hoja de datos.")

    df["fecha"] = pd.to_datetime(df["actdate"], errors="coerce")
    df = df.dropna(subset=["fecha"]).copy()

    num_cols = [
        "gatlockhm3", "pmlockhm3", "aclockhm3", "ccllockhm3",
        "numlockgat", "numlockpm", "numlockac", "numlockccl",
        "gatlockmcf", "pmlockmcf", "aclockmcf", "ccllockmcf",
    ]
    for c in num_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    hm3_to_mcf = {
        "gatlockhm3": "gatlockmcf",
        "pmlockhm3": "pmlockmcf",
        "aclockhm3": "aclockmcf",
        "ccllockhm3": "ccllockmcf",
    }
    for hm3_col, mcf_col in hm3_to_mcf.items():
        if hm3_col in df.columns and mcf_col not in df.columns:
            df[mcf_col] = df[hm3_col] * FACTOR_HM3_A_MCF

    # Volúmenes
    df["total_hm3"] = df[["gatlockhm3", "pmlockhm3", "aclockhm3", "ccllockhm3"]].sum(axis=1, min_count=1)
    df["total_pnx_hm3"] = df[["gatlockhm3", "pmlockhm3"]].sum(axis=1, min_count=1)
    df["total_npx_hm3"] = df[["aclockhm3", "ccllockhm3"]].sum(axis=1, min_count=1)

    df["total_mcf"] = df[["gatlockmcf", "pmlockmcf", "aclockmcf", "ccllockmcf"]].sum(axis=1, min_count=1)
    df["total_pnx_mcf"] = df[["gatlockmcf", "pmlockmcf"]].sum(axis=1, min_count=1)
    df["total_npx_mcf"] = df[["aclockmcf", "ccllockmcf"]].sum(axis=1, min_count=1)

    # Tránsitos por complejo
    df["pnx_transitos"] = df[["numlockgat", "numlockpm"]].mean(axis=1, skipna=True)
    df["npx_transitos"] = df[["numlockac", "numlockccl"]].mean(axis=1, skipna=True)
    df["total_transitos"] = df[["pnx_transitos", "npx_transitos"]].sum(axis=1, min_count=1)

    # Año fiscal correcto: AF 2019 = Oct 2018 ... Sep 2019
    df["anio"] = df["fecha"].dt.year
    df["mes"] = df["fecha"].dt.month
    df["mes_nombre"] = df["mes"].map(MESES_NUM_A_NOMBRE)
    df["af"] = np.where(df["mes"] >= 10, df["anio"] + 1, df["anio"]).astype(int)
    df["af_label"] = df["af"].astype(str)
    df["mes_af"] = ((df["mes"] - 10) % 12).astype(int)
    df["dow"] = df["fecha"].dt.dayofweek
    df["dow_nombre"] = df["dow"].map(DOW_NOMBRE)

    return df.sort_values("fecha").reset_index(drop=True)


def ordenar_periodos(periodos):
    try:
        return sorted(periodos, key=lambda x: int(str(x)))
    except Exception:
        return sorted(periodos)


def figura_vacia(titulo):
    fig = go.Figure()
    fig.update_layout(
        template="plotly_white",
        title=titulo,
        height=320,
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        annotations=[dict(text="Sin datos suficientes", x=0.5, y=0.5, showarrow=False, font=dict(size=16))],
    )
    return fig


logo_path = encontrar_logo()

# SIDEBAR
if logo_path:
    st.sidebar.image(logo_path, use_container_width=True)

st.sidebar.markdown("## 🚢 Consumo de Esclusajes")
st.sidebar.markdown("Canal de Panamá")
st.sidebar.markdown("---")

df = None
error_carga = None
archivos = sorted(glob.glob("Promedio_de_Consumos*.xlsx"))

if archivos:
    try:
        df = cargar_datos(archivos[0])
        st.sidebar.success(f"✅ {len(df):,} registros cargados desde {os.path.basename(archivos[0])}")
    except PermissionError:
        error_carga = (
            f"No se pudo abrir el archivo local '{os.path.basename(archivos[0])}'. "
            "Puede estar abierto en Excel o bloqueado por OneDrive."
        )
    except Exception as e:
        error_carga = f"No se pudo abrir el archivo local: {e}"

f_up = st.sidebar.file_uploader("Sube el Excel de consumos", type=["xlsx", "xls"])
if df is None and f_up is not None:
    try:
        df = cargar_datos(f_up)
        st.sidebar.success(f"✅ {len(df):,} registros cargados desde archivo subido")
        error_carga = None
    except Exception as e:
        st.sidebar.error(f"No se pudo leer el archivo subido: {e}")

if error_carga and df is None:
    st.sidebar.warning(error_carga)

if df is None:
    st.markdown(
        "<div style='text-align:center; margin-top:60px;'>"
        "<h1 style='color:#1a5276;'>🚢 Consumo de Esclusajes</h1>"
        "<p style='font-size:1.2rem; color:#5d6d7e;'>Sube tu archivo Excel en la barra lateral.</p>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.stop()

# Filtros
st.sidebar.markdown("---")
st.sidebar.markdown("### ⚙️ Filtros")

tipo_anio = st.sidebar.radio(
    "Agrupar por",
    ["Año Fiscal (Oct–Sep)", "Año Calendario (Ene–Dic)"],
    horizontal=True,
)
usa_af = "Fiscal" in tipo_anio

if usa_af:
    anios_disp = ordenar_periodos(df["af"].dropna().astype(int).unique().tolist())
    anio_sel = st.sidebar.multiselect("Años fiscales", anios_disp, default=anios_disp)
    df = df[df["af"].isin(anio_sel)].copy()
    df["periodo_label"] = df["af"].astype(str)
    periodo_nombre = "Año Fiscal"
else:
    anios_disp = ordenar_periodos(df["anio"].dropna().astype(int).unique().tolist())
    anio_sel = st.sidebar.multiselect("Años calendario", anios_disp, default=anios_disp)
    df = df[df["anio"].isin(anio_sel)].copy()
    df["periodo_label"] = df["anio"].astype(str)
    periodo_nombre = "Año Calendario"

if df.empty:
    st.warning("Sin datos para los años seleccionados.")
    st.stop()

unidad = st.sidebar.radio("Unidad de volumen", ["hm³", "MCF (mil pies³)"], horizontal=True)
if unidad == "hm³":
    cols_vol = {
        "Gatún": "gatlockhm3",
        "Pedro Miguel": "pmlockhm3",
        "Agua Clara": "aclockhm3",
        "Cocolí": "ccllockhm3",
        "Total": "total_hm3",
        "Total PNX": "total_pnx_hm3",
        "Total NPX": "total_npx_hm3",
    }
    uv = "hm³"
else:
    cols_vol = {
        "Gatún": "gatlockmcf",
        "Pedro Miguel": "pmlockmcf",
        "Agua Clara": "aclockmcf",
        "Cocolí": "ccllockmcf",
        "Total": "total_mcf",
        "Total PNX": "total_pnx_mcf",
        "Total NPX": "total_npx_mcf",
    }
    uv = "MCF"

cols_num = {
    "Gatún": "numlockgat",
    "Pedro Miguel": "numlockpm",
    "Agua Clara": "numlockac",
    "Cocolí": "numlockccl",
}
esclusas = ["Gatún", "Pedro Miguel", "Agua Clara", "Cocolí"]
cols_esc = {e: cols_vol[e] for e in esclusas}

overall_consumo_por_transito = (
    df[cols_vol["Total"]].sum() / df["total_transitos"].sum()
    if df["total_transitos"].sum() > 0 else np.nan
)

df["consumo_por_transito_total"] = df[cols_vol["Total"]] / df["total_transitos"].replace(0, np.nan)

st.sidebar.markdown("---")
st.sidebar.markdown(f"**Registros:** {len(df):,}")
st.sidebar.markdown(f"**Período:** {df['fecha'].min().date()} → {df['fecha'].max().date()}")

# HEADER
if logo_path:
    h1, h2 = st.columns([1, 8], vertical_alignment="center")
    with h1:
        st.image(logo_path, width=100)
    with h2:
        st.markdown(
            "<h1 style='color:#1a5276; margin-bottom:0;'>🚢 Consumo de Agua por Esclusajes</h1>"
            "<p style='color:#5d6d7e; margin-top:0;'>Canal de Panamá · Datos diarios · <b>Creador: JFRodriguez</b></p>",
            unsafe_allow_html=True,
        )
else:
    st.markdown(
        "<h1 style='color:#1a5276;'>🚢 Consumo de Agua por Esclusajes</h1>"
        "<p style='color:#5d6d7e; margin-top:-12px;'>Canal de Panamá · Datos diarios · <b>Creador: JFRodriguez</b></p>",
        unsafe_allow_html=True,
    )

k1, k2, k3, k4, k5, k6, k7 = st.columns(7)
k1.metric("Consumo diario prom.", f"{df[cols_vol['Total']].mean():.2f} {uv}")
k2.metric("Consumo diario máx.", f"{df[cols_vol['Total']].max():.2f} {uv}")
k3.metric("Tránsitos/día prom.", f"{df['total_transitos'].mean():.1f}")
k4.metric("Tránsitos/día máx.", f"{df['total_transitos'].max():.1f}")
k5.metric("Tránsitos/día min.", f"{df['total_transitos'].min():.1f}")
k6.metric("Consumo prom./tránsito", f"{overall_consumo_por_transito:.3f} {uv}" if pd.notna(overall_consumo_por_transito) else "NA")
k7.metric(periodo_nombre + "s", f"{df['periodo_label'].nunique()}")
st.caption("PNX y NPX se calculan por promedio entre las esclusas del complejo. Todas las métricas del tablero se presentan en función de tránsitos, consumo y consumo por tránsito.")
st.markdown("---")

tabs = st.tabs([
    "🏠 Resumen",
    "📈 Serie Temporal",
    "🔀 Comparar Esclusas",
    "📅 Por Período",
    "📊 Mensual",
    "🏗️ PNX vs NPX",
    "🗺️ Heatmap",
    "⚡ Eficiencia",
    "🏆 Rankings",
    "🧩 Operación",
    "📅 Patrón semanal",
    "🔮 Proyecciones",
    "📥 Exportar",
])

# TAB 0 RESUMEN
with tabs[0]:
    st.subheader("Resumen operativo")
    r0a, r0b, r0c, r0d = st.columns(4)
    r0a.metric("Tránsitos/día prom.", f"{df['total_transitos'].mean():.1f}")
    r0b.metric("Tránsitos/día máx.", f"{df['total_transitos'].max():.1f}")
    r0c.metric("Tránsitos/día min.", f"{df['total_transitos'].min():.1f}")
    r0d.metric("Consumo prom./tránsito", f"{overall_consumo_por_transito:.3f} {uv}" if pd.notna(overall_consumo_por_transito) else "NA")

    st.subheader("Consumo mensual por esclusa")
    mensual = df.assign(ym=df["fecha"].dt.to_period("M")).groupby("ym", as_index=False).agg(
        **{cols_esc[esc]: (cols_esc[esc], "sum") for esc in esclusas}
    )
    mensual["fecha"] = mensual["ym"].dt.to_timestamp()

    fig0 = go.Figure()
    for esc in esclusas:
        fig0.add_trace(
            go.Bar(
                x=mensual["fecha"],
                y=mensual[cols_esc[esc]],
                name=esc,
                marker_color=COL[esc],
            )
        )
    fig0.update_layout(
        barmode="stack",
        yaxis_title=f"Consumo ({uv})",
        template="plotly_white",
        height=450,
        hovermode="x unified",
        margin=dict(l=50, r=20, t=20, b=50),
    )
    st.plotly_chart(fig0, use_container_width=True)

    c1, c2 = st.columns(2)

    with c1:
        st.subheader("Proporción del volumen total")
        totales = {esc: df[cols_esc[esc]].sum() for esc in esclusas}
        fig_pie = go.Figure(
            go.Pie(
                labels=list(totales.keys()),
                values=list(totales.values()),
                marker_colors=[COL[e] for e in totales.keys()],
                hole=0.4,
                textinfo="percent+label",
            )
        )
        fig_pie.update_layout(height=350, template="plotly_white", margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(fig_pie, use_container_width=True)

    with c2:
        st.subheader("Tránsitos por complejo")
        vals = {
            "PNX": df["pnx_transitos"].sum(),
            "NPX": df["npx_transitos"].sum(),
        }
        fig_pie2 = go.Figure(
            go.Pie(
                labels=list(vals.keys()),
                values=list(vals.values()),
                marker_colors=[COL["Total PNX"], COL["Total NPX"]],
                hole=0.4,
                textinfo="percent+label",
            )
        )
        fig_pie2.update_layout(height=350, template="plotly_white", margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(fig_pie2, use_container_width=True)

    st.subheader("Resumen por esclusa")
    filas = []
    for esc in esclusas:
        cv = cols_esc[esc]
        cn = cols_num[esc]
        filas.append(
            {
                "Esclusa": esc,
                "Tipo": "Panamax" if esc in ["Gatún", "Pedro Miguel"] else "Neopanamax",
                f"Consumo diario prom. ({uv})": round(df[cv].mean(), 3),
                f"Consumo diario máx. ({uv})": round(df[cv].max(), 3),
                "Tránsitos/día prom.": round(df[cn].mean(), 2),
                f"Consumo/tránsito ({uv})": round(df[cv].sum() / max(df[cn].sum(), 1), 3),
            }
        )
    st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)

# TAB 1 SERIE TEMPORAL
with tabs[1]:
    st.subheader("Serie temporal de consumo diario")
    esc_sel = st.multiselect("Esclusas", esclusas, default=esclusas, key="serie_esclusas")
    fig1 = go.Figure()
    for esc in esc_sel:
        c = cols_esc[esc]
        roll = df.set_index("fecha")[[c]].rolling("30D").mean().reset_index()
        fig1.add_trace(
            go.Scattergl(x=roll["fecha"], y=roll[c], mode="lines", name=esc, line=dict(color=COL[esc], width=2))
        )
    fig1.update_layout(
        yaxis_title=f"Consumo ({uv}) — media 30d",
        template="plotly_white",
        height=500,
        hovermode="x unified",
        margin=dict(l=50, r=20, t=30, b=50),
    )
    st.plotly_chart(fig1, use_container_width=True)

    st.subheader("Tránsitos diarios por complejo")
    roll_t = df.set_index("fecha")[["total_transitos", "pnx_transitos", "npx_transitos"]].rolling("30D").mean().reset_index()
    fig1b = go.Figure()
    fig1b.add_trace(go.Scattergl(
        x=roll_t["fecha"], y=roll_t["total_transitos"], mode="lines",
        name="Total", line=dict(color=COL["Tránsitos"], width=3)
    ))
    fig1b.add_trace(go.Scattergl(
        x=roll_t["fecha"], y=roll_t["pnx_transitos"], mode="lines",
        name="PNX", line=dict(color=COL["Total PNX"], width=2)
    ))
    fig1b.add_trace(go.Scattergl(
        x=roll_t["fecha"], y=roll_t["npx_transitos"], mode="lines",
        name="NPX", line=dict(color=COL["Total NPX"], width=2)
    ))
    fig1b.update_layout(
        yaxis_title="Promedio 30d",
        template="plotly_white",
        height=380,
        hovermode="x unified",
        margin=dict(l=50, r=20, t=20, b=50),
    )
    st.plotly_chart(fig1b, use_container_width=True)

# TAB 2 COMPARAR ESCLUSAS
with tabs[2]:
    st.subheader("Comparación directa entre esclusas")
    cc1, cc2 = st.columns(2)
    with cc1:
        esc_a = st.selectbox("Esclusa A", esclusas, index=0)
    with cc2:
        esc_b = st.selectbox("Esclusa B", esclusas, index=2)

    ca = cols_esc[esc_a]
    cb = cols_esc[esc_b]

    fig2 = make_subplots(rows=2, cols=2, subplot_titles=["Serie temporal (30d)", "Scatter", "Box plot", "Histograma"])
    for esc, c, color in [(esc_a, ca, COL[esc_a]), (esc_b, cb, COL[esc_b])]:
        roll = df.set_index("fecha")[[c]].rolling("30D").mean().reset_index()
        fig2.add_trace(go.Scatter(x=roll["fecha"], y=roll[c], mode="lines", name=esc, line=dict(color=color, width=2)), row=1, col=1)

    fig2.add_trace(
        go.Scattergl(
            x=df[ca], y=df[cb], mode="markers",
            marker=dict(color=COL["Total"], size=4, opacity=0.35),
            name=f"{esc_a} vs {esc_b}", showlegend=False
        ),
        row=1, col=2
    )
    corr = df[ca].corr(df[cb])

    fig2.add_trace(go.Box(y=df[ca], name=esc_a, marker_color=COL[esc_a]), row=2, col=1)
    fig2.add_trace(go.Box(y=df[cb], name=esc_b, marker_color=COL[esc_b]), row=2, col=1)
    fig2.add_trace(go.Histogram(x=df[ca], name=esc_a, opacity=0.60, marker_color=COL[esc_a], nbinsx=40), row=2, col=2)
    fig2.add_trace(go.Histogram(x=df[cb], name=esc_b, opacity=0.60, marker_color=COL[esc_b], nbinsx=40), row=2, col=2)
    fig2.update_layout(
        barmode="overlay",
        template="plotly_white",
        height=700,
        margin=dict(l=50, r=20, t=40, b=50),
    )
    fig2.update_xaxes(title_text=f"{esc_a} ({uv})", row=1, col=2)
    fig2.update_yaxes(title_text=f"{esc_b} ({uv})", row=1, col=2)
    st.plotly_chart(fig2, use_container_width=True)
    st.info(f"Correlación entre {esc_a} y {esc_b}: r = {corr:.3f}")

# TAB 3 POR PERIODO
with tabs[3]:
    st.subheader(f"Comparación por {periodo_nombre}")
    per_total = df.groupby("periodo_label", as_index=False).agg(
        consumo_total=(cols_vol["Total"], "sum"),
        prom_diario=(cols_vol["Total"], "mean"),
        transitos=("total_transitos", "sum"),
        dias=("fecha", "count"),
    )
    per_total["periodo_sort"] = per_total["periodo_label"].astype(int)
    per_total = per_total.sort_values("periodo_sort")
    per_total["consumo_por_transito"] = per_total["consumo_total"] / per_total["transitos"].replace(0, np.nan)

    p1, p2 = st.columns(2)
    with p1:
        fig3a = go.Figure()
        fig3a.add_trace(go.Bar(
            x=per_total["periodo_label"], y=per_total["consumo_total"],
            marker_color=COL["Total"], text=[f"{v:.0f}" for v in per_total["consumo_total"]], textposition="auto"
        ))
        fig3a.update_layout(
            template="plotly_white", height=380, yaxis_title=f"Consumo total ({uv})",
            margin=dict(l=50, r=20, t=40, b=50)
        )
        st.plotly_chart(fig3a, use_container_width=True)

    with p2:
        fig3b = go.Figure()
        fig3b.add_trace(go.Bar(
            x=per_total["periodo_label"], y=per_total["transitos"],
            marker_color=COL["Tránsitos"], text=[f"{v:,.0f}" for v in per_total["transitos"]], textposition="auto"
        ))
        fig3b.update_layout(
            template="plotly_white", height=380, yaxis_title="Tránsitos totales",
            margin=dict(l=50, r=20, t=40, b=50)
        )
        st.plotly_chart(fig3b, use_container_width=True)

    st.subheader("Consumo acumulado")
    fig3c = go.Figure()
    colores = ["#e74c3c", "#3498db", "#2ecc71", "#e67e22", "#9b59b6", "#1abc9c", "#f39c12", "#34495e"]
    for i, per in enumerate(ordenar_periodos(df["periodo_label"].unique())):
        sub = df[df["periodo_label"] == str(per)].sort_values("fecha").copy()
        sub["cumsum"] = sub[cols_vol["Total"]].cumsum()
        if usa_af:
            inicio = pd.Timestamp(year=int(sub["af"].iloc[0]) - 1, month=10, day=1)
            sub["dia_periodo"] = (sub["fecha"] - inicio).dt.days + 1
            xlabel = "Día del año fiscal"
        else:
            inicio = pd.Timestamp(year=int(sub["anio"].iloc[0]), month=1, day=1)
            sub["dia_periodo"] = (sub["fecha"] - inicio).dt.days + 1
            xlabel = "Día del año"
        fig3c.add_trace(go.Scatter(
            x=sub["dia_periodo"], y=sub["cumsum"], mode="lines", name=str(per),
            line=dict(color=colores[i % len(colores)], width=2)
        ))
    fig3c.update_layout(
        template="plotly_white", height=450, hovermode="x unified",
        xaxis_title=xlabel, yaxis_title=f"Acumulado ({uv})",
        margin=dict(l=50, r=20, t=20, b=50)
    )
    st.plotly_chart(fig3c, use_container_width=True)

# TAB 4 MENSUAL
with tabs[4]:
    st.subheader("Promedio por mes")
    if usa_af:
        df_mes = df.groupby(["mes_af", "mes_nombre"], as_index=False).agg(
            **{f"{esc}_prom": (cols_esc[esc], "mean") for esc in esclusas},
            total_prom=(cols_vol["Total"], "mean"),
            transitos_prom=("total_transitos", "mean"),
        ).sort_values("mes_af")
        xvals = df_mes["mes_nombre"]
        orden_mostrar = MESES_FISCALES
    else:
        df_mes = df.groupby(["mes", "mes_nombre"], as_index=False).agg(
            **{f"{esc}_prom": (cols_esc[esc], "mean") for esc in esclusas},
            total_prom=(cols_vol["Total"], "mean"),
            transitos_prom=("total_transitos", "mean"),
        ).sort_values("mes")
        xvals = df_mes["mes_nombre"]
        orden_mostrar = MESES_CAL

    fig4a = go.Figure()
    for esc in esclusas:
        fig4a.add_trace(go.Bar(x=xvals, y=df_mes[f"{esc}_prom"], name=esc, marker_color=COL[esc]))
    fig4a.update_layout(
        barmode="stack",
        template="plotly_white",
        height=420,
        yaxis_title=f"Consumo diario prom. ({uv})",
        xaxis=dict(categoryorder="array", categoryarray=orden_mostrar),
        margin=dict(l=50, r=20, t=20, b=50),
    )
    st.plotly_chart(fig4a, use_container_width=True)

    st.subheader("Variabilidad mensual del consumo total")
    fig4b = go.Figure()
    category_order = MESES_FISCALES if usa_af else MESES_CAL
    for mes_nom in category_order:
        sub = df[df["mes_nombre"] == mes_nom]
        fig4b.add_trace(go.Box(y=sub[cols_vol["Total"]], name=mes_nom, boxmean=True))
    fig4b.update_layout(
        template="plotly_white",
        height=400,
        showlegend=False,
        yaxis_title=f"Consumo total diario ({uv})",
        xaxis=dict(categoryorder="array", categoryarray=category_order),
        margin=dict(l=50, r=20, t=20, b=50),
    )
    st.plotly_chart(fig4b, use_container_width=True)

# TAB 5 PNX VS NPX
with tabs[5]:
    st.subheader("Panamax (PNX) vs Neopanamax (NPX)")
    st.caption("Tránsitos calculados por promedio entre las esclusas del complejo.")

    p1, p2 = st.columns(2)
    with p1:
        mensual = df.assign(ym=df["fecha"].dt.to_period("M")).groupby("ym", as_index=False).agg(
            pnx_vol=(cols_vol["Total PNX"], "sum"),
            npx_vol=(cols_vol["Total NPX"], "sum"),
            pnx_trans=("pnx_transitos", "mean"),
            npx_trans=("npx_transitos", "mean"),
        )
        mensual["fecha"] = mensual["ym"].dt.to_timestamp()
        mensual["pct_pnx"] = mensual["pnx_vol"] / (mensual["pnx_vol"] + mensual["npx_vol"]) * 100
        mensual["pct_npx"] = 100 - mensual["pct_pnx"]
        fig5a = go.Figure()
        fig5a.add_trace(go.Bar(x=mensual["fecha"], y=mensual["pct_pnx"], name="PNX %", marker_color=COL["Total PNX"]))
        fig5a.add_trace(go.Bar(x=mensual["fecha"], y=mensual["pct_npx"], name="NPX %", marker_color=COL["Total NPX"]))
        fig5a.update_layout(
            barmode="stack", template="plotly_white", height=400, yaxis_title="% del consumo",
            margin=dict(l=50, r=20, t=40, b=50)
        )
        st.plotly_chart(fig5a, use_container_width=True)

    with p2:
        roll = df.set_index("fecha")[["pnx_transitos", "npx_transitos"]].rolling("30D").mean().reset_index()
        fig5b = go.Figure()
        fig5b.add_trace(go.Scatter(x=roll["fecha"], y=roll["pnx_transitos"], mode="lines", name="PNX", line=dict(color=COL["Total PNX"], width=2)))
        fig5b.add_trace(go.Scatter(x=roll["fecha"], y=roll["npx_transitos"], mode="lines", name="NPX", line=dict(color=COL["Total NPX"], width=2)))
        fig5b.update_layout(
            template="plotly_white", height=400, yaxis_title="Tránsitos/día — media 30d",
            margin=dict(l=50, r=20, t=40, b=50), hovermode="x unified"
        )
        st.plotly_chart(fig5b, use_container_width=True)

    r1, r2 = st.columns([2, 1])
    with r1:
        fig5c = go.Figure()
        fig5c.add_trace(go.Scattergl(
            x=df["pnx_transitos"], y=df["npx_transitos"], mode="markers",
            marker=dict(color=df["fecha"].astype(np.int64), colorscale="Viridis", size=4, opacity=0.4,
                        colorbar=dict(title="Fecha"))
        ))
        fig5c.update_layout(
            template="plotly_white", height=400, xaxis_title="PNX tránsitos", yaxis_title="NPX tránsitos",
            margin=dict(l=50, r=20, t=20, b=50)
        )
        st.plotly_chart(fig5c, use_container_width=True)
    with r2:
        corr_pn = df["pnx_transitos"].corr(df["npx_transitos"])
        st.metric("Correlación PNX-NPX", f"{corr_pn:.3f}")
        st.metric("PNX prom/día", f"{df['pnx_transitos'].mean():.2f}")
        st.metric("NPX prom/día", f"{df['npx_transitos'].mean():.2f}")
        st.metric("Consumo prom./tránsito", f"{overall_consumo_por_transito:.3f} {uv}" if pd.notna(overall_consumo_por_transito) else "NA")

# TAB 6 HEATMAP
with tabs[6]:
    st.subheader("Mapa de calor")
    if usa_af:
        st.caption("Modo fiscal: columnas de octubre a septiembre y el año corresponde al cierre del año fiscal.")
        hm = df.groupby(["af", "mes_af"], as_index=False)[cols_vol["Total"]].mean()
        pt = hm.pivot(index="af", columns="mes_af", values=cols_vol["Total"]).sort_index()
        pt = pt.reindex(columns=range(12))
        pt.columns = MESES_FISCALES
        yvals = pt.index.astype(str)
        xvals = MESES_FISCALES
    else:
        hm = df.groupby(["anio", "mes"], as_index=False)[cols_vol["Total"]].mean()
        pt = hm.pivot(index="anio", columns="mes", values=cols_vol["Total"]).sort_index()
        pt = pt.reindex(columns=range(1, 13))
        pt.columns = MESES_CAL
        yvals = pt.index.astype(str)
        xvals = MESES_CAL

    fig6a = go.Figure(data=go.Heatmap(
        z=pt.values, x=xvals, y=yvals,
        colorscale="YlOrRd", colorbar_title=uv, hoverongaps=False
    ))
    fig6a.update_layout(
        template="plotly_white",
        height=max(320, len(pt) * 45),
        margin=dict(l=60, r=20, t=20, b=50),
        xaxis=dict(categoryorder="array", categoryarray=xvals),
        yaxis_title=periodo_nombre,
    )
    st.plotly_chart(fig6a, use_container_width=True)

    st.subheader("Heatmap por esclusa")
    esc_hm = st.selectbox("Esclusa", esclusas, key="hm_esclusa")
    c_hm = cols_esc[esc_hm]
    if usa_af:
        hm2 = df.groupby(["af", "mes_af"], as_index=False)[c_hm].mean()
        pt2 = hm2.pivot(index="af", columns="mes_af", values=c_hm).sort_index()
        pt2 = pt2.reindex(columns=range(12))
        pt2.columns = MESES_FISCALES
        xvals2 = MESES_FISCALES
        yvals2 = pt2.index.astype(str)
    else:
        hm2 = df.groupby(["anio", "mes"], as_index=False)[c_hm].mean()
        pt2 = hm2.pivot(index="anio", columns="mes", values=c_hm).sort_index()
        pt2 = pt2.reindex(columns=range(1, 13))
        pt2.columns = MESES_CAL
        xvals2 = MESES_CAL
        yvals2 = pt2.index.astype(str)

    fig6b = go.Figure(data=go.Heatmap(
        z=pt2.values, x=xvals2, y=yvals2,
        colorscale="Blues", colorbar_title=uv, hoverongaps=False
    ))
    fig6b.update_layout(
        template="plotly_white",
        height=max(320, len(pt2) * 45),
        margin=dict(l=60, r=20, t=20, b=50),
        xaxis=dict(categoryorder="array", categoryarray=xvals2),
        yaxis_title=periodo_nombre,
    )
    st.plotly_chart(fig6b, use_container_width=True)

# TAB 7 EFICIENCIA
with tabs[7]:
    st.subheader("Eficiencia: consumo por tránsito")
    st.caption("Para PNX y NPX la eficiencia se calcula usando tránsitos por complejo.")

    df["efic_pnx"] = df[cols_vol["Total PNX"]] / df["pnx_transitos"].replace(0, np.nan)
    df["efic_npx"] = df[cols_vol["Total NPX"]] / df["npx_transitos"].replace(0, np.nan)

    e1, e2 = st.columns(2)
    with e1:
        fig7a = go.Figure()
        for esc in esclusas:
            col_ef = f"efic_{esc}"
            df[col_ef] = df[cols_esc[esc]] / df[cols_num[esc]].replace(0, np.nan)
            roll = df.set_index("fecha")[[col_ef]].rolling("30D").mean().reset_index()
            fig7a.add_trace(go.Scatter(x=roll["fecha"], y=roll[col_ef], mode="lines", name=esc, line=dict(color=COL[esc], width=2)))
        fig7a.update_layout(
            template="plotly_white", height=420, hovermode="x unified",
            yaxis_title=f"Consumo/tránsito ({uv})", margin=dict(l=50, r=20, t=40, b=50)
        )
        st.plotly_chart(fig7a, use_container_width=True)

    with e2:
        fig7b = go.Figure()
        fig7b.add_trace(go.Box(y=df["efic_pnx"].dropna(), name="PNX", marker_color=COL["Total PNX"], boxmean=True))
        fig7b.add_trace(go.Box(y=df["efic_npx"].dropna(), name="NPX", marker_color=COL["Total NPX"], boxmean=True))
        fig7b.update_layout(
            template="plotly_white", height=420, showlegend=False,
            yaxis_title=f"Consumo/tránsito ({uv})", margin=dict(l=50, r=20, t=40, b=50)
        )
        st.plotly_chart(fig7b, use_container_width=True)

    ep, en = df["efic_pnx"].mean(), df["efic_npx"].mean()
    ahorro = ((ep - en) / ep * 100) if pd.notna(ep) and ep > 0 else np.nan
    m1, m2, m3 = st.columns(3)
    m1.metric("PNX prom.", f"{ep:.3f} {uv}/tránsito" if pd.notna(ep) else "NA")
    m2.metric("NPX prom.", f"{en:.3f} {uv}/tránsito" if pd.notna(en) else "NA")
    m3.metric("Ahorro NPX vs PNX", f"{ahorro:.1f}%" if pd.notna(ahorro) else "NA")

    for esc in esclusas:
        df.drop(columns=[f"efic_{esc}"], inplace=True, errors="ignore")
    df.drop(columns=["efic_pnx", "efic_npx"], inplace=True, errors="ignore")

# TAB 8 RANKINGS
with tabs[8]:
    st.subheader("Rankings operativos")
    r1, r2 = st.columns(2)

    with r1:
        st.markdown("#### Días con mayor consumo total")
        top_consumo = df[["fecha", cols_vol["Total"], "total_transitos", "consumo_por_transito_total"]].sort_values(cols_vol["Total"], ascending=False).head(15).copy()
        top_consumo["fecha"] = top_consumo["fecha"].dt.strftime("%Y-%m-%d")
        top_consumo = top_consumo.rename(columns={"consumo_por_transito_total": f"Consumo/tránsito ({uv})"})
        st.dataframe(top_consumo, use_container_width=True, hide_index=True)

    with r2:
        st.markdown("#### Días con más tránsitos por complejo")
        top_trans = df[["fecha", "pnx_transitos", "npx_transitos", "total_transitos", "consumo_por_transito_total"]].sort_values("total_transitos", ascending=False).head(15).copy()
        top_trans["fecha"] = top_trans["fecha"].dt.strftime("%Y-%m-%d")
        top_trans = top_trans.rename(columns={"consumo_por_transito_total": f"Consumo/tránsito ({uv})"})
        st.dataframe(top_trans, use_container_width=True, hide_index=True)

# TAB 9 OPERACION
with tabs[9]:
    st.subheader("Relación entre operación y consumo")
    st.caption("Vista integrada del consumo total frente a los tránsitos por complejo y el consumo promedio por tránsito.")

    o1, o2 = st.columns(2)

    with o1:
        fig9a = go.Figure()
        fig9a.add_trace(go.Scattergl(
            x=df["total_transitos"],
            y=df[cols_vol["Total"]],
            mode="markers",
            marker=dict(
                color=df["consumo_por_transito_total"],
                colorscale="Viridis",
                size=7,
                opacity=0.55,
                colorbar=dict(title=f"{uv}/tránsito"),
            ),
            text=df["fecha"].dt.strftime("%Y-%m-%d"),
            hovertemplate=f"Fecha: %{{text}}<br>Tránsitos: %{{x:.1f}}<br>Consumo: %{{y:.2f}} {uv}<br>Consumo/tránsito: %{{marker.color:.3f}} {uv}<extra></extra>",
            name="Días observados",
        ))

        if df[["total_transitos", cols_vol["Total"]]].dropna().shape[0] >= 2:
            x_valid = df["total_transitos"]
            y_valid = df[cols_vol["Total"]]
            mask = x_valid.notna() & y_valid.notna()
            slope, intercept, r_val, _, _ = sp_stats.linregress(x_valid[mask], y_valid[mask])
            x_line = np.linspace(x_valid[mask].min(), x_valid[mask].max(), 100)
            y_line = intercept + slope * x_line
            fig9a.add_trace(go.Scatter(
                x=x_line, y=y_line, mode="lines",
                name=f"Ajuste lineal (r={r_val:.2f})",
                line=dict(color=COL["Total"], width=2, dash="dash"),
            ))

        fig9a.update_layout(
            template="plotly_white",
            height=430,
            xaxis_title="Tránsitos/día por complejo",
            yaxis_title=f"Consumo total ({uv})",
            margin=dict(l=50, r=20, t=20, b=50),
        )
        st.plotly_chart(fig9a, use_container_width=True)

    with o2:
        mensual_op = df.assign(ym=df["fecha"].dt.to_period("M")).groupby("ym", as_index=False).agg(
            consumo_prom=(cols_vol["Total"], "mean"),
            transitos_prom=("total_transitos", "mean"),
        )
        mensual_op["fecha"] = mensual_op["ym"].dt.to_timestamp()
        mensual_op["consumo_por_transito"] = mensual_op["consumo_prom"] / mensual_op["transitos_prom"].replace(0, np.nan)

        fig9b = go.Figure()
        fig9b.add_trace(go.Bar(
            x=mensual_op["fecha"],
            y=mensual_op["transitos_prom"],
            name="Tránsitos/día prom.",
            marker_color=COL["Tránsitos"],
            opacity=0.75,
            yaxis="y1",
        ))
        fig9b.add_trace(go.Scatter(
            x=mensual_op["fecha"],
            y=mensual_op["consumo_por_transito"],
            name=f"Consumo prom./tránsito ({uv})",
            mode="lines+markers",
            line=dict(color=COL["Total"], width=3),
            yaxis="y2",
        ))
        fig9b.update_layout(
            template="plotly_white",
            height=430,
            margin=dict(l=50, r=50, t=20, b=50),
            hovermode="x unified",
            yaxis=dict(title="Tránsitos/día"),
            yaxis2=dict(title=f"{uv}/tránsito", overlaying="y", side="right"),
        )
        st.plotly_chart(fig9b, use_container_width=True)

    st.subheader("Indicadores rápidos de operación")
    q1, q2, q3, q4 = st.columns(4)
    q1.metric("Tránsitos/día min.", f"{df['total_transitos'].min():.1f}")
    q2.metric("Tránsitos/día mediana", f"{df['total_transitos'].median():.1f}")
    q3.metric("Consumo/tránsito prom.", f"{overall_consumo_por_transito:.3f} {uv}" if pd.notna(overall_consumo_por_transito) else "NA")
    q4.metric("Consumo/tránsito máx.", f"{df['consumo_por_transito_total'].max():.3f} {uv}" if df['consumo_por_transito_total'].notna().any() else "NA")

# TAB 10 PATRON SEMANAL
with tabs[10]:
    st.subheader("Patrón semanal de operación")
    st.caption("Este tablero muestra cómo cambian los tránsitos y el consumo por día de la semana.")

    semanal = df.groupby(["dow", "dow_nombre"], as_index=False).agg(
        transitos_prom=("total_transitos", "mean"),
        consumo_prom=(cols_vol["Total"], "mean"),
        consumo_trans_prom=("consumo_por_transito_total", "mean"),
    ).sort_values("dow")

    s1, s2 = st.columns(2)

    with s1:
        fig10a = go.Figure()
        fig10a.add_trace(go.Bar(
            x=semanal["dow_nombre"],
            y=semanal["transitos_prom"],
            name="Tránsitos/día prom.",
            marker_color=COL["Tránsitos"],
            yaxis="y1",
        ))
        fig10a.add_trace(go.Scatter(
            x=semanal["dow_nombre"],
            y=semanal["consumo_prom"],
            name=f"Consumo diario prom. ({uv})",
            mode="lines+markers",
            line=dict(color=COL["Total"], width=3),
            yaxis="y2",
        ))
        fig10a.update_layout(
            template="plotly_white",
            height=420,
            hovermode="x unified",
            xaxis=dict(categoryorder="array", categoryarray=DOW_ORDEN),
            yaxis=dict(title="Tránsitos/día"),
            yaxis2=dict(title=f"Consumo ({uv})", overlaying="y", side="right"),
            margin=dict(l=50, r=50, t=20, b=50),
        )
        st.plotly_chart(fig10a, use_container_width=True)

    with s2:
        fig10b = go.Figure()
        for dia in DOW_ORDEN:
            sub = df[df["dow_nombre"] == dia]
            fig10b.add_trace(go.Box(
                y=sub["consumo_por_transito_total"],
                name=dia,
                boxmean=True,
            ))
        fig10b.update_layout(
            template="plotly_white",
            height=420,
            yaxis_title=f"Consumo por tránsito ({uv})",
            xaxis=dict(categoryorder="array", categoryarray=DOW_ORDEN),
            margin=dict(l=50, r=20, t=20, b=50),
            showlegend=False,
        )
        st.plotly_chart(fig10b, use_container_width=True)

    mejor_dia = semanal.loc[semanal["transitos_prom"].idxmax(), "dow_nombre"] if not semanal.empty else "NA"
    menor_dia = semanal.loc[semanal["transitos_prom"].idxmin(), "dow_nombre"] if not semanal.empty else "NA"
    a1, a2, a3 = st.columns(3)
    a1.metric("Día con más tránsitos", mejor_dia)
    a2.metric("Día con menos tránsitos", menor_dia)
    a3.metric("Consumo/tránsito semanal prom.", f"{df['consumo_por_transito_total'].mean():.3f} {uv}" if df['consumo_por_transito_total'].notna().any() else "NA")

# TAB 11 PROYECCIONES
with tabs[11]:
    st.subheader("Proyecciones simples de esclusajes")
    st.caption("Proyección exploratoria basada en tendencia lineal del promedio mensual de tránsitos por complejo. Úsala como referencia visual, no como pronóstico operativo formal.")

    mensual_t = df.assign(ym=df["fecha"].dt.to_period("M")).groupby("ym", as_index=False).agg(
        total_transitos=("total_transitos", "mean"),
        pnx_transitos=("pnx_transitos", "mean"),
        npx_transitos=("npx_transitos", "mean"),
    )
    mensual_t["fecha"] = mensual_t["ym"].dt.to_timestamp()
    mensual_t["x"] = np.arange(len(mensual_t))

    horizonte = st.slider("Meses a proyectar", min_value=3, max_value=12, value=6, step=1)

    if len(mensual_t) >= 3:
        future_x = np.arange(len(mensual_t) + horizonte)
        future_dates = pd.date_range(mensual_t["fecha"].min(), periods=len(mensual_t) + horizonte, freq="MS")
        fig11 = go.Figure()

        for col, nombre, color in [
            ("total_transitos", "Total", COL["Tránsitos"]),
            ("pnx_transitos", "PNX", COL["Total PNX"]),
            ("npx_transitos", "NPX", COL["Total NPX"]),
        ]:
            slope, intercept, _, _, _ = sp_stats.linregress(mensual_t["x"], mensual_t[col])
            yhat = intercept + slope * future_x

            fig11.add_trace(go.Scatter(
                x=mensual_t["fecha"], y=mensual_t[col], mode="lines+markers",
                name=f"{nombre} observado", line=dict(color=color, width=2)
            ))
            fig11.add_trace(go.Scatter(
                x=future_dates, y=yhat, mode="lines",
                name=f"{nombre} proyectado", line=dict(color=color, width=2, dash="dash")
            ))

        fig11.update_layout(
            template="plotly_white",
            height=500,
            hovermode="x unified",
            yaxis_title="Tránsitos/día",
            margin=dict(l=50, r=20, t=20, b=50),
        )
        st.plotly_chart(fig11, use_container_width=True)
    else:
        st.plotly_chart(figura_vacia("Proyecciones"), use_container_width=True)

# TAB 12 EXPORTAR
with tabs[12]:
    st.subheader("Exportar")

    ex1, ex2, ex3 = st.columns(3)
    with ex1:
        st.markdown("#### Datos diarios")
        st.download_button(
            "⬇️ CSV diario",
            df.to_csv(index=False).encode("utf-8"),
            "consumo_diario_esclusajes.csv",
            "text/csv",
        )

    with ex2:
        st.markdown("#### Promedios mensuales")
        mens = df.assign(ym=df["fecha"].dt.to_period("M")).groupby("ym", as_index=False).agg(
            **{f"{esc}_prom": (cols_esc[esc], "mean") for esc in esclusas},
            total_prom=(cols_vol["Total"], "mean"),
            pnx_trans_prom=("pnx_transitos", "mean"),
            npx_trans_prom=("npx_transitos", "mean"),
            total_trans_prom=("total_transitos", "mean"),
        )
        mens["fecha"] = mens["ym"].dt.to_timestamp()
        mens["consumo_trans_prom"] = mens["total_prom"] / mens["total_trans_prom"].replace(0, np.nan)
        st.download_button(
            "⬇️ CSV mensual",
            mens.drop(columns=["ym"]).to_csv(index=False).encode("utf-8"),
            "consumo_mensual_esclusajes.csv",
            "text/csv",
        )

    with ex3:
        st.markdown(f"#### Resumen por {periodo_nombre}")
        resumen_per = df.groupby("periodo_label", as_index=False).agg(
            **{f"{esc}_prom": (cols_esc[esc], "mean") for esc in esclusas},
            total_prom=(cols_vol["Total"], "mean"),
            pnx_trans_prom=("pnx_transitos", "mean"),
            npx_trans_prom=("npx_transitos", "mean"),
            total_trans_prom=("total_transitos", "mean"),
        )
        resumen_per["consumo_trans_prom"] = resumen_per["total_prom"] / resumen_per["total_trans_prom"].replace(0, np.nan)
        st.download_button(
            f"⬇️ CSV por {periodo_nombre}",
            resumen_per.to_csv(index=False).encode("utf-8"),
            "consumo_por_periodo.csv",
            "text/csv",
        )

    st.markdown("---")
    mostrar = df[[
        "fecha", "af", "anio", "mes_nombre",
        cols_vol["Total"], "pnx_transitos", "npx_transitos", "total_transitos", "consumo_por_transito_total"
    ]].copy()
    mostrar = mostrar.rename(columns={"consumo_por_transito_total": f"Consumo/tránsito ({uv})"})
    st.dataframe(mostrar.head(200), use_container_width=True, height=320)

st.markdown("---")
st.markdown(
    "<div style='text-align:center; color:#aab7b8; font-size:0.85rem;'>"
    "🚢 Consumo de Esclusajes · Canal de Panamá · Datos: Autoridad del Canal de Panamá (ACP)<br>"
    "Creador: JFRodriguez</div>",
    unsafe_allow_html=True,
)
