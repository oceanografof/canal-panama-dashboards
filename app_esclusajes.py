"""
🚢 Dashboard de Consumo de Esclusajes — Canal de Panamá
========================================================
Análisis comparativo del consumo de agua por esclusas.

INSTALACIÓN:
    pip install streamlit pandas numpy plotly scipy openpyxl

EJECUCIÓN:
    streamlit run app_esclusajes.py

Creador: JFRodriguez
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy import stats as sp_stats
import glob, os, calendar

st.set_page_config(page_title="🚢 Esclusajes — Canal de Panamá", page_icon="🚢", layout="wide")

MESES = ["Oct","Nov","Dic","Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep"]
MESES_CAL = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"]

# Colores por esclusa
COL = {
    "Gatún": "#2980b9",
    "Pedro Miguel": "#e67e22",
    "Agua Clara": "#27ae60",
    "Cocolí": "#8e44ad",
    "Total PNX": "#2c3e50",
    "Total NPX": "#16a085",
    "Total": "#c0392b",
}


# ══════════════════════════════════════════════════════════════
# FUNCIONES
# ══════════════════════════════════════════════════════════════
@st.cache_data(show_spinner="Cargando datos de esclusajes...")
def cargar_datos(fuente):
    df = pd.read_excel(fuente, sheet_name="Data")
    df["fecha"] = pd.to_datetime(df["actdate"], errors="coerce")
    df = df.dropna(subset=["fecha"])

    # Limpiar columnas numéricas
    for c in ["gatlockhm3","pmlockhm3","aclockhm3","ccllockhm3",
              "numlockgat","numlockpm","numlockac","numlockccl"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df["total_hm3"] = df[["gatlockhm3","pmlockhm3","aclockhm3","ccllockhm3"]].sum(axis=1)
    df["total_pnx_hm3"] = df[["gatlockhm3","pmlockhm3"]].sum(axis=1)
    df["total_npx_hm3"] = df[["aclockhm3","ccllockhm3"]].sum(axis=1)
    df["total_locks"] = df[["numlockgat","numlockpm","numlockac","numlockccl"]].sum(axis=1)

    # Año fiscal (Oct-Sep)
    df["af"] = df["fecha"].apply(lambda x: x.year if x.month >= 10 else x.year - 1)
    df["af_label"] = df["af"].apply(lambda x: f"AF{x}-{x+1}")
    df["mes"] = df["fecha"].dt.month
    df["mes_af"] = df["mes"].apply(lambda m: (m - 10) % 12)  # 0=Oct, 11=Sep
    df["anio"] = df["fecha"].dt.year

    return df.sort_values("fecha").reset_index(drop=True)


def resam(df, col, limite=10000, freq="1D"):
    if len(df) <= limite: return df, False
    r = df.set_index("fecha")[[col]].resample(freq).mean().dropna().reset_index()
    return r, True


# ══════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════
st.sidebar.markdown("## 🚢 Consumo de Esclusajes")
st.sidebar.markdown("Canal de Panamá")
st.sidebar.markdown("---")

df = None
archivos = sorted(glob.glob("Promedio_de_Consumos*.xlsx"))

if archivos:
    df = cargar_datos(archivos[0])
    st.sidebar.success(f"✅ {len(df):,} registros")
else:
    f_up = st.sidebar.file_uploader("Sube el Excel de consumos", type=["xlsx","xls"])
    if f_up:
        df = cargar_datos(f_up)
        st.sidebar.success(f"✅ {len(df):,} registros")

if df is None:
    st.markdown(
        "<div style='text-align:center; margin-top:100px;'>"
        "<h1 style='color:#1a5276;'>🚢 Consumo de Esclusajes</h1>"
        "<p style='font-size:1.2rem; color:#5d6d7e;'>"
        "Sube tu archivo Excel de consumos mensuales en la barra lateral.</p></div>",
        unsafe_allow_html=True)
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
    anios_disp = sorted(df["af_label"].unique())
    anio_sel = st.sidebar.multiselect("Años fiscales", anios_disp, default=anios_disp)
    df = df[df["af_label"].isin(anio_sel)]
else:
    # Año calendario
    df["ac_label"] = df["anio"].astype(str)
    anios_disp = sorted(df["ac_label"].unique())
    anio_sel = st.sidebar.multiselect("Años calendario", anios_disp, default=anios_disp)
    df = df[df["ac_label"].isin(anio_sel)]

# Columna unificada para agrupar
if usa_af:
    df["periodo_label"] = df["af_label"]
    periodo_nombre = "Año Fiscal"
else:
    df["periodo_label"] = df["anio"].astype(str)
    periodo_nombre = "Año Calendario"

if df.empty:
    st.warning("Sin datos para los años seleccionados."); st.stop()

unidad = st.sidebar.radio("Unidad de volumen", ["hm³", "MCF (mil pies³)"], horizontal=True)
if unidad == "hm³":
    cols_vol = {"Gatún":"gatlockhm3","Pedro Miguel":"pmlockhm3",
                "Agua Clara":"aclockhm3","Cocolí":"ccllockhm3",
                "Total":"total_hm3","Total PNX":"total_pnx_hm3","Total NPX":"total_npx_hm3"}
    uv = "hm³"
else:
    cols_vol = {"Gatún":"gatlockmcf","Pedro Miguel":"pmlockmcf",
                "Agua Clara":"aclockmcf","Cocolí":"ccllockmcf"}
    uv = "MCF"
    # Asegurar que existan
    for c in cols_vol.values():
        if c not in df.columns:
            st.sidebar.warning(f"Columna {c} no encontrada.")

st.sidebar.markdown("---")
st.sidebar.markdown(f"**Registros:** {len(df):,}")
st.sidebar.markdown(f"**Período:** {df['fecha'].min().date()} → {df['fecha'].max().date()}")

# Esclusas principales
esclusas = ["Gatún","Pedro Miguel","Agua Clara","Cocolí"]
cols_esc = {e: cols_vol[e] for e in esclusas if e in cols_vol}
cols_num = {"Gatún":"numlockgat","Pedro Miguel":"numlockpm",
            "Agua Clara":"numlockac","Cocolí":"numlockccl"}


# ══════════════════════════════════════════════════════════════
# HEADER
# ══════════════════════════════════════════════════════════════
st.markdown(
    "<h1 style='color:#1a5276;'>🚢 Consumo de Agua por Esclusajes</h1>"
    "<p style='color:#5d6d7e; margin-top:-12px;'>"
    "Canal de Panamá · Datos diarios · <b>Creador: JFRodriguez</b></p>",
    unsafe_allow_html=True,
)

# KPIs
k1,k2,k3,k4,k5,k6 = st.columns(6)
if "total_hm3" in cols_vol:
    k1.metric("Consumo diario prom.", f"{df['total_hm3'].mean():.2f} hm³")
    k2.metric("Consumo diario máx.", f"{df['total_hm3'].max():.2f} hm³")
k3.metric("Esclusajes/día prom.", f"{df['total_locks'].mean():.0f}")
k4.metric("Esclusajes/día máx.", f"{df['total_locks'].max():.0f}")
k5.metric("Días con datos", f"{len(df):,}")
k6.metric(periodo_nombre + "s", f"{df['periodo_label'].nunique()}")
st.markdown("---")


# ══════════════════════════════════════════════════════════════
# TABS
# ══════════════════════════════════════════════════════════════
tabs = st.tabs([
    "🏠 Resumen",
    "📈 Serie Temporal",
    "🔀 Comparar Esclusas",
    "📅 Por Período",
    "📊 Mensual",
    "🏗️ PNX vs NPX",
    "📉 Tendencia",
    "🗺️ Heatmap",
    "⚡ Eficiencia",
    "📥 Exportar",
])


# ═══════════════════════════════════════════════════════════════
# TAB 0 — RESUMEN
# ═══════════════════════════════════════════════════════════════
with tabs[0]:
    # Consumo por esclusa (barras apiladas mensuales)
    st.subheader("Consumo mensual por esclusa")
    df["ym"] = df["fecha"].dt.to_period("M")
    mensual = df.groupby("ym").agg({c: "sum" for c in cols_esc.values()}).reset_index()
    mensual["fecha"] = mensual["ym"].dt.to_timestamp()

    fig0 = go.Figure()
    for esc, c in cols_esc.items():
        fig0.add_trace(go.Bar(x=mensual["fecha"], y=mensual[c],
            name=esc, marker_color=COL[esc]))
    fig0.update_layout(barmode="stack", yaxis_title=f"Consumo ({uv})",
        template="plotly_white", height=450, hovermode="x unified",
        margin=dict(l=50,r=20,t=20,b=50))
    st.plotly_chart(fig0, use_container_width=True)

    # Proporción por esclusa
    st.subheader("Proporción por esclusa")
    p1, p2 = st.columns(2)
    with p1:
        totales = {esc: df[c].sum() for esc, c in cols_esc.items()}
        fig_pie = go.Figure(go.Pie(
            labels=list(totales.keys()), values=list(totales.values()),
            marker_colors=[COL[e] for e in totales.keys()],
            hole=0.4, textinfo="percent+label",
        ))
        fig_pie.update_layout(height=350, template="plotly_white",
            margin=dict(l=10,r=10,t=30,b=10), title="Volumen total")
        st.plotly_chart(fig_pie, use_container_width=True)

    with p2:
        totales_n = {esc: df[c].sum() for esc, c in cols_num.items()}
        fig_pie2 = go.Figure(go.Pie(
            labels=list(totales_n.keys()), values=list(totales_n.values()),
            marker_colors=[COL[e] for e in totales_n.keys()],
            hole=0.4, textinfo="percent+label",
        ))
        fig_pie2.update_layout(height=350, template="plotly_white",
            margin=dict(l=10,r=10,t=30,b=10), title="Nº de esclusajes")
        st.plotly_chart(fig_pie2, use_container_width=True)

    df.drop(columns=["ym"], inplace=True, errors="ignore")

    # Resumen por esclusa
    st.subheader("Resumen por esclusa")
    filas = []
    for esc in esclusas:
        cv = cols_esc.get(esc)
        cn = cols_num.get(esc)
        if cv and cn:
            filas.append({
                "Esclusa": esc,
                "Tipo": "Panamax" if esc in ["Gatún","Pedro Miguel"] else "Neopanamax",
                f"Consumo diario prom. ({uv})": f"{df[cv].mean():.3f}",
                f"Consumo diario máx. ({uv})": f"{df[cv].max():.3f}",
                "Esclusajes/día prom.": f"{df[cn].mean():.1f}",
                f"Consumo/esclusaje ({uv})": f"{(df[cv].sum()/max(df[cn].sum(),1)):.3f}",
            })
    st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════════
# TAB 1 — SERIE TEMPORAL
# ═══════════════════════════════════════════════════════════════
with tabs[1]:
    st.subheader("Serie temporal de consumo diario")
    esc_sel = st.multiselect("Esclusas", esclusas, default=esclusas, key="st1")

    fig1 = go.Figure()
    for esc in esc_sel:
        c = cols_esc.get(esc)
        if c:
            # Media móvil 30 días
            roll = df.set_index("fecha")[[c]].rolling("30D").mean().reset_index()
            fig1.add_trace(go.Scattergl(x=roll["fecha"], y=roll[c],
                mode="lines", name=esc, line=dict(color=COL[esc], width=2)))

    fig1.update_layout(yaxis_title=f"Consumo ({uv}) — media 30d",
        template="plotly_white", height=500, hovermode="x unified",
        margin=dict(l=50,r=20,t=30,b=50))
    st.plotly_chart(fig1, use_container_width=True)

    # Total
    st.subheader("Consumo total diario")
    if "total_hm3" in df.columns:
        roll_t = df.set_index("fecha")[["total_hm3"]].rolling("30D").mean().reset_index()
        fig1b = go.Figure()
        fig1b.add_trace(go.Scattergl(x=roll_t["fecha"], y=roll_t["total_hm3"],
            mode="lines", name="Total", line=dict(color=COL["Total"], width=2),
            fill="tozeroy", fillcolor="rgba(192,57,43,0.08)"))
        fig1b.update_layout(yaxis_title=f"Consumo total ({uv}) — media 30d",
            template="plotly_white", height=380, hovermode="x unified",
            margin=dict(l=50,r=20,t=20,b=50))
        st.plotly_chart(fig1b, use_container_width=True)


# ═══════════════════════════════════════════════════════════════
# TAB 2 — COMPARAR ESCLUSAS
# ═══════════════════════════════════════════════════════════════
with tabs[2]:
    st.subheader("Comparación directa entre esclusas")

    cc1, cc2 = st.columns(2)
    with cc1:
        esc_a = st.selectbox("Esclusa A", esclusas, index=0)
    with cc2:
        esc_b = st.selectbox("Esclusa B", esclusas, index=2)

    ca = cols_esc.get(esc_a)
    cb = cols_esc.get(esc_b)

    if ca and cb:
        fig2 = make_subplots(rows=2, cols=2,
            subplot_titles=["Serie temporal (media 30d)","Scatter","Box plot","Distribución"])

        # Serie temporal
        for esc, c, color in [(esc_a, ca, COL[esc_a]), (esc_b, cb, COL[esc_b])]:
            roll = df.set_index("fecha")[[c]].rolling("30D").mean().reset_index()
            fig2.add_trace(go.Scatter(x=roll["fecha"], y=roll[c],
                mode="lines", name=esc, line=dict(color=color, width=2)),
                row=1, col=1)

        # Scatter
        fig2.add_trace(go.Scattergl(x=df[ca], y=df[cb], mode="markers",
            marker=dict(color=COL["Total"], size=3, opacity=0.3),
            name=f"{esc_a} vs {esc_b}", showlegend=False),
            row=1, col=2)
        corr = df[ca].corr(df[cb])
        fig2.update_xaxes(title_text=f"{esc_a} ({uv})", row=1, col=2)
        fig2.update_yaxes(title_text=f"{esc_b} ({uv})", row=1, col=2)

        # Box plot
        fig2.add_trace(go.Box(y=df[ca], name=esc_a, marker_color=COL[esc_a]),
            row=2, col=1)
        fig2.add_trace(go.Box(y=df[cb], name=esc_b, marker_color=COL[esc_b]),
            row=2, col=1)

        # Histograma
        fig2.add_trace(go.Histogram(x=df[ca], name=esc_a, opacity=0.6,
            marker_color=COL[esc_a], nbinsx=40), row=2, col=2)
        fig2.add_trace(go.Histogram(x=df[cb], name=esc_b, opacity=0.6,
            marker_color=COL[esc_b], nbinsx=40), row=2, col=2)
        fig2.update_layout(barmode="overlay")

        fig2.update_layout(template="plotly_white", height=700, showlegend=True,
            margin=dict(l=50,r=20,t=40,b=50))
        st.plotly_chart(fig2, use_container_width=True)
        st.info(f"**Correlación entre {esc_a} y {esc_b}:** r = {corr:.3f}")


# ═══════════════════════════════════════════════════════════════
# TAB 3 — POR AÑO FISCAL
# ═══════════════════════════════════════════════════════════════
with tabs[3]:
    st.subheader(f"Comparación por {periodo_nombre}")

    # Total por período
    af_total = df.groupby("periodo_label").agg(
        total=("total_hm3","sum"),
        prom_diario=("total_hm3","mean"),
        esclusajes=("total_locks","sum"),
        dias=("fecha","count"),
    ).reset_index()

    fc1, fc2 = st.columns(2)
    with fc1:
        fig3a = go.Figure()
        fig3a.add_trace(go.Bar(x=af_total["periodo_label"], y=af_total["total"],
            marker_color=COL["Total"], text=[f"{v:.0f}" for v in af_total["total"]],
            textposition="auto"))
        fig3a.update_layout(yaxis_title=f"Consumo total ({uv})",
            template="plotly_white", height=380, title=f"Consumo total por {periodo_nombre}",
            margin=dict(l=50,r=20,t=40,b=50))
        st.plotly_chart(fig3a, use_container_width=True)

    with fc2:
        fig3b = go.Figure()
        fig3b.add_trace(go.Bar(x=af_total["periodo_label"], y=af_total["esclusajes"],
            marker_color=COL["Gatún"], text=[f"{v:,.0f}" for v in af_total["esclusajes"]],
            textposition="auto"))
        fig3b.update_layout(yaxis_title="Nº esclusajes",
            template="plotly_white", height=380, title=f"Esclusajes totales por {periodo_nombre}",
            margin=dict(l=50,r=20,t=40,b=50))
        st.plotly_chart(fig3b, use_container_width=True)

    # Desglose por esclusa
    st.subheader("Desglose por esclusa")
    af_esc = df.groupby("periodo_label").agg({c: "mean" for c in cols_esc.values()}).reset_index()

    fig3c = go.Figure()
    for esc, c in cols_esc.items():
        fig3c.add_trace(go.Bar(x=af_esc["periodo_label"], y=af_esc[c],
            name=esc, marker_color=COL[esc]))
    fig3c.update_layout(barmode="group", yaxis_title=f"Consumo diario prom. ({uv})",
        template="plotly_white", height=420,
        margin=dict(l=50,r=20,t=20,b=50))
    st.plotly_chart(fig3c, use_container_width=True)

    # Curvas acumuladas superpuestas
    st.subheader(f"Consumo acumulado por {periodo_nombre}")
    fig3d = go.Figure()
    colores_af = ["#e74c3c","#3498db","#2ecc71","#e67e22","#9b59b6",
                  "#1abc9c","#f39c12","#34495e"]
    for i, per in enumerate(sorted(df["periodo_label"].unique())):
        sub = df[df["periodo_label"]==per].sort_values("fecha").copy()
        sub["cumsum"] = sub["total_hm3"].cumsum()
        sub["dia"] = range(len(sub))
        fig3d.add_trace(go.Scatter(x=sub["dia"], y=sub["cumsum"],
            mode="lines", name=per,
            line=dict(color=colores_af[i%len(colores_af)], width=2)))

    xlabel = "Día del año fiscal" if usa_af else "Día del año"
    fig3d.update_layout(xaxis_title=xlabel, yaxis_title=f"Acumulado ({uv})",
        template="plotly_white", height=450, hovermode="x unified",
        margin=dict(l=50,r=20,t=20,b=50))
    st.plotly_chart(fig3d, use_container_width=True)


# ═══════════════════════════════════════════════════════════════
# TAB 4 — MENSUAL
# ═══════════════════════════════════════════════════════════════
with tabs[4]:
    st.subheader("Análisis mensual")

    df["ym"] = df["fecha"].dt.to_period("M")
    mensual = df.groupby("ym").agg(
        **{c: (c, "mean") for c in cols_esc.values()},
        total=("total_hm3","mean"),
        esclusajes=("total_locks","mean"),
    ).reset_index()
    mensual["fecha"] = mensual["ym"].dt.to_timestamp()

    # Por mes calendario
    st.subheader("Promedio por mes del año")
    df_mes = df.groupby("mes").agg(
        **{f"{esc}_prom": (c, "mean") for esc, c in cols_esc.items()},
        total_prom=("total_hm3","mean"),
    ).reset_index()

    fig4a = go.Figure()
    for esc, c in cols_esc.items():
        fig4a.add_trace(go.Bar(
            x=[MESES_CAL[m-1] for m in df_mes["mes"]],
            y=df_mes[f"{esc}_prom"], name=esc, marker_color=COL[esc]))
    fig4a.update_layout(barmode="stack", yaxis_title=f"Consumo diario prom. ({uv})",
        template="plotly_white", height=420,
        margin=dict(l=50,r=20,t=20,b=50))
    st.plotly_chart(fig4a, use_container_width=True)

    # Box por mes
    st.subheader("Variabilidad mensual del consumo total")
    fig4b = go.Figure()
    for m in range(1,13):
        sub = df[df["mes"]==m]
        fig4b.add_trace(go.Box(y=sub["total_hm3"], name=MESES_CAL[m-1],
            marker_color=f"hsl({(m-1)*30}, 65%, 50%)", boxmean=True))
    fig4b.update_layout(yaxis_title=f"Consumo total diario ({uv})",
        template="plotly_white", height=400, showlegend=False,
        margin=dict(l=50,r=20,t=20,b=50))
    st.plotly_chart(fig4b, use_container_width=True)

    df.drop(columns=["ym"], inplace=True, errors="ignore")


# ═══════════════════════════════════════════════════════════════
# TAB 5 — PNX vs NPX
# ═══════════════════════════════════════════════════════════════
with tabs[5]:
    st.subheader("Panamax (PNX) vs Neopanamax (NPX)")
    st.caption("PNX = Gatún + Pedro Miguel · NPX = Agua Clara + Cocolí")

    pn1, pn2 = st.columns(2)

    with pn1:
        # Proporción temporal
        df["ym"] = df["fecha"].dt.to_period("M")
        m_pnx = df.groupby("ym").agg(
            pnx=("total_pnx_hm3","sum"), npx=("total_npx_hm3","sum")).reset_index()
        m_pnx["fecha"] = m_pnx["ym"].dt.to_timestamp()
        m_pnx["pct_pnx"] = m_pnx["pnx"] / (m_pnx["pnx"]+m_pnx["npx"]) * 100
        m_pnx["pct_npx"] = 100 - m_pnx["pct_pnx"]

        fig5a = go.Figure()
        fig5a.add_trace(go.Bar(x=m_pnx["fecha"], y=m_pnx["pct_pnx"],
            name="PNX %", marker_color=COL["Total PNX"]))
        fig5a.add_trace(go.Bar(x=m_pnx["fecha"], y=m_pnx["pct_npx"],
            name="NPX %", marker_color=COL["Total NPX"]))
        fig5a.update_layout(barmode="stack", yaxis_title="% del consumo",
            template="plotly_white", height=400, title="Proporción mensual",
            margin=dict(l=50,r=20,t=40,b=50))
        st.plotly_chart(fig5a, use_container_width=True)
        df.drop(columns=["ym"], inplace=True, errors="ignore")

    with pn2:
        # Serie temporal
        roll_pnx = df.set_index("fecha")[["total_pnx_hm3","total_npx_hm3"]].rolling("30D").mean().reset_index()
        fig5b = go.Figure()
        fig5b.add_trace(go.Scatter(x=roll_pnx["fecha"], y=roll_pnx["total_pnx_hm3"],
            mode="lines", name="PNX", line=dict(color=COL["Total PNX"], width=2)))
        fig5b.add_trace(go.Scatter(x=roll_pnx["fecha"], y=roll_pnx["total_npx_hm3"],
            mode="lines", name="NPX", line=dict(color=COL["Total NPX"], width=2)))
        fig5b.update_layout(yaxis_title=f"Consumo ({uv}) — media 30d",
            template="plotly_white", height=400, title="Evolución PNX vs NPX",
            margin=dict(l=50,r=20,t=40,b=50), hovermode="x unified")
        st.plotly_chart(fig5b, use_container_width=True)

    # Scatter PNX vs NPX
    st.subheader("Relación PNX vs NPX")
    sc1, sc2 = st.columns([2,1])
    with sc1:
        fig5c = go.Figure()
        fig5c.add_trace(go.Scattergl(x=df["total_pnx_hm3"], y=df["total_npx_hm3"],
            mode="markers", marker=dict(color=df["fecha"].astype(np.int64),
            colorscale="Viridis", size=3, opacity=0.4, colorbar=dict(title="Fecha"))))
        fig5c.update_layout(xaxis_title=f"PNX ({uv})", yaxis_title=f"NPX ({uv})",
            template="plotly_white", height=400,
            margin=dict(l=50,r=20,t=20,b=50))
        st.plotly_chart(fig5c, use_container_width=True)
    with sc2:
        corr_pn = df["total_pnx_hm3"].corr(df["total_npx_hm3"])
        st.metric("Correlación", f"{corr_pn:.3f}")
        st.metric("PNX prom/día", f"{df['total_pnx_hm3'].mean():.2f} {uv}")
        st.metric("NPX prom/día", f"{df['total_npx_hm3'].mean():.2f} {uv}")
        pct_pnx = df["total_pnx_hm3"].sum() / df["total_hm3"].sum() * 100
        st.metric("% PNX del total", f"{pct_pnx:.1f}%")
        st.metric("% NPX del total", f"{100-pct_pnx:.1f}%")


# ═══════════════════════════════════════════════════════════════
# TAB 6 — TENDENCIA
# ═══════════════════════════════════════════════════════════════
with tabs[6]:
    st.subheader("Tendencia del consumo")

    # Promedio mensual
    df["ym"] = df["fecha"].dt.to_period("M")
    m_trend = df.groupby("ym")["total_hm3"].mean().reset_index()
    m_trend["fecha"] = m_trend["ym"].dt.to_timestamp()
    m_trend["x"] = (m_trend["fecha"] - m_trend["fecha"].min()).dt.total_seconds() / (365.25*24*3600)

    fig6 = go.Figure()
    fig6.add_trace(go.Scatter(x=m_trend["fecha"], y=m_trend["total_hm3"],
        mode="lines+markers", name="Promedio mensual",
        line=dict(color=COL["Total"], width=2), marker=dict(size=4)))

    if len(m_trend) >= 6:
        slope, intercept, r_val, p_val, _ = sp_stats.linregress(
            m_trend["x"], m_trend["total_hm3"])
        fig6.add_trace(go.Scatter(x=m_trend["fecha"],
            y=intercept + slope * m_trend["x"],
            mode="lines", name=f"Tendencia: {slope:+.3f} {uv}/año",
            line=dict(color="#2c3e50", dash="dash", width=2)))

        t1,t2,t3 = st.columns(3)
        t1.metric("Pendiente", f"{slope:+.4f} {uv}/año")
        t2.metric("R²", f"{r_val**2:.3f}")
        sig = "✅ Significativa" if p_val < 0.05 else "⚠️ No significativa"
        t3.metric("p-valor", f"{p_val:.4f} ({sig})")

    fig6.update_layout(yaxis_title=f"Consumo diario prom. ({uv})",
        template="plotly_white", height=450, hovermode="x unified",
        margin=dict(l=50,r=20,t=20,b=50))
    st.plotly_chart(fig6, use_container_width=True)

    # Tendencia por esclusa
    st.subheader("Tendencia por esclusa")
    fig6b = go.Figure()
    for esc, c in cols_esc.items():
        m_e = df.groupby("ym")[c].mean().reset_index()
        m_e["fecha"] = m_e["ym"].dt.to_timestamp()
        fig6b.add_trace(go.Scatter(x=m_e["fecha"], y=m_e[c],
            mode="lines", name=esc, line=dict(color=COL[esc], width=2)))
    fig6b.update_layout(yaxis_title=f"Consumo diario prom. ({uv})",
        template="plotly_white", height=400, hovermode="x unified",
        margin=dict(l=50,r=20,t=20,b=50))
    st.plotly_chart(fig6b, use_container_width=True)

    df.drop(columns=["ym"], inplace=True, errors="ignore")


# ═══════════════════════════════════════════════════════════════
# TAB 7 — HEATMAP
# ═══════════════════════════════════════════════════════════════
with tabs[7]:
    st.subheader("Mapa de calor: Consumo total Mes × Año")
    df["anio"] = df["fecha"].dt.year
    df["mes"] = df["fecha"].dt.month
    hm = df.groupby(["anio","mes"])["total_hm3"].mean().reset_index()
    pt = hm.pivot(index="anio", columns="mes", values="total_hm3")
    pt.columns = [MESES_CAL[m-1] for m in pt.columns]

    fig7a = go.Figure(data=go.Heatmap(z=pt.values, x=pt.columns, y=pt.index,
        colorscale="YlOrRd", colorbar_title=uv, hoverongaps=False))
    fig7a.update_layout(yaxis_title="Año", template="plotly_white",
        height=max(300, len(pt)*40), margin=dict(l=60,r=20,t=20,b=50))
    st.plotly_chart(fig7a, use_container_width=True)

    # Heatmap por esclusa
    st.subheader("Heatmap por esclusa (promedio mensual)")
    esc_hm = st.selectbox("Esclusa", esclusas, key="hm_esc")
    c_hm = cols_esc[esc_hm]
    hm2 = df.groupby(["anio","mes"])[c_hm].mean().reset_index()
    pt2 = hm2.pivot(index="anio", columns="mes", values=c_hm)
    pt2.columns = [MESES_CAL[m-1] for m in pt2.columns]

    fig7b = go.Figure(data=go.Heatmap(z=pt2.values, x=pt2.columns, y=pt2.index,
        colorscale="Blues", colorbar_title=uv, hoverongaps=False))
    fig7b.update_layout(yaxis_title="Año", template="plotly_white",
        height=max(300, len(pt2)*40), margin=dict(l=60,r=20,t=20,b=50))
    st.plotly_chart(fig7b, use_container_width=True)

    # Heatmap día de semana × hora... bueno, día de semana × mes
    st.subheader("Consumo por día de la semana")
    df["dow"] = df["fecha"].dt.dayofweek
    dow_n = ["Lun","Mar","Mié","Jue","Vie","Sáb","Dom"]
    dow_m = df.groupby("dow")["total_hm3"].agg(["mean","std"]).reset_index()
    fig7c = go.Figure()
    fig7c.add_trace(go.Bar(x=[dow_n[d] for d in dow_m["dow"]], y=dow_m["mean"],
        marker_color=COL["Gatún"],
        error_y=dict(type="data", array=dow_m["std"], visible=True, color="rgba(0,0,0,0.15)")))
    fig7c.update_layout(yaxis_title=f"Consumo prom. ({uv})",
        template="plotly_white", height=350, margin=dict(l=50,r=20,t=20,b=50))
    st.plotly_chart(fig7c, use_container_width=True)

    df.drop(columns=["anio","mes","dow"], inplace=True, errors="ignore")


# ═══════════════════════════════════════════════════════════════
# TAB 8 — EFICIENCIA
# ═══════════════════════════════════════════════════════════════
with tabs[8]:
    st.subheader("Eficiencia: Consumo por esclusaje")
    st.caption("¿Cuánta agua se usa por cada tránsito?")

    # Consumo por esclusaje por esclusa
    for esc in esclusas:
        cv = cols_esc.get(esc)
        cn = cols_num.get(esc)
        if cv and cn:
            df[f"efic_{esc}"] = df[cv] / df[cn].replace(0, np.nan)

    ef1, ef2 = st.columns(2)

    with ef1:
        fig8a = go.Figure()
        for esc in esclusas:
            col_ef = f"efic_{esc}"
            if col_ef in df.columns:
                roll = df.set_index("fecha")[[col_ef]].rolling("30D").mean().reset_index()
                fig8a.add_trace(go.Scatter(x=roll["fecha"], y=roll[col_ef],
                    mode="lines", name=esc, line=dict(color=COL[esc], width=2)))
        fig8a.update_layout(yaxis_title=f"Consumo/esclusaje ({uv}) — media 30d",
            template="plotly_white", height=420, hovermode="x unified",
            title="Evolución de la eficiencia",
            margin=dict(l=50,r=20,t=40,b=50))
        st.plotly_chart(fig8a, use_container_width=True)

    with ef2:
        fig8b = go.Figure()
        for esc in esclusas:
            col_ef = f"efic_{esc}"
            if col_ef in df.columns:
                fig8b.add_trace(go.Box(y=df[col_ef].dropna(), name=esc,
                    marker_color=COL[esc], boxmean=True))
        fig8b.update_layout(yaxis_title=f"Consumo/esclusaje ({uv})",
            template="plotly_white", height=420, showlegend=False,
            title="Distribución por esclusa",
            margin=dict(l=50,r=20,t=40,b=50))
        st.plotly_chart(fig8b, use_container_width=True)

    # Eficiencia PNX vs NPX
    st.subheader("Eficiencia: PNX vs NPX")
    df["efic_pnx"] = df["total_pnx_hm3"] / (df["numlockgat"]+df["numlockpm"]).replace(0, np.nan)
    df["efic_npx"] = df["total_npx_hm3"] / (df["numlockac"]+df["numlockccl"]).replace(0, np.nan)

    fig8c = go.Figure()
    roll_ep = df.set_index("fecha")[["efic_pnx","efic_npx"]].rolling("30D").mean().reset_index()
    fig8c.add_trace(go.Scatter(x=roll_ep["fecha"], y=roll_ep["efic_pnx"],
        mode="lines", name="PNX", line=dict(color=COL["Total PNX"], width=2)))
    fig8c.add_trace(go.Scatter(x=roll_ep["fecha"], y=roll_ep["efic_npx"],
        mode="lines", name="NPX", line=dict(color=COL["Total NPX"], width=2)))
    fig8c.update_layout(yaxis_title=f"Consumo/esclusaje ({uv}) — media 30d",
        template="plotly_white", height=380, hovermode="x unified",
        margin=dict(l=50,r=20,t=20,b=50))
    st.plotly_chart(fig8c, use_container_width=True)

    ep, en = df["efic_pnx"].mean(), df["efic_npx"].mean()
    ahorro = ((ep - en) / ep * 100) if ep > 0 else 0
    e1, e2, e3 = st.columns(3)
    e1.metric("PNX prom.", f"{ep:.3f} {uv}/esclusaje")
    e2.metric("NPX prom.", f"{en:.3f} {uv}/esclusaje")
    e3.metric("Ahorro NPX vs PNX", f"{ahorro:.1f}%")

    # Limpiar
    for esc in esclusas:
        df.drop(columns=[f"efic_{esc}"], inplace=True, errors="ignore")
    df.drop(columns=["efic_pnx","efic_npx"], inplace=True, errors="ignore")


# ═══════════════════════════════════════════════════════════════
# TAB 9 — EXPORTAR
# ═══════════════════════════════════════════════════════════════
with tabs[9]:
    st.subheader("Exportar")

    ex1, ex2, ex3 = st.columns(3)
    with ex1:
        st.markdown("#### Datos diarios")
        st.download_button("⬇️ CSV diario", df.to_csv(index=False).encode("utf-8"),
            "consumo_diario_esclusajes.csv", "text/csv")

    with ex2:
        st.markdown("#### Promedios mensuales")
        df["ym"] = df["fecha"].dt.to_period("M")
        mens = df.groupby("ym").agg(
            **{c: (c,"mean") for c in cols_esc.values()},
            total=("total_hm3","mean"),
            esclusajes=("total_locks","mean"),
        ).reset_index()
        mens["fecha"] = mens["ym"].dt.to_timestamp()
        st.download_button("⬇️ CSV mensual",
            mens.drop(columns=["ym"]).to_csv(index=False).encode("utf-8"),
            "consumo_mensual_esclusajes.csv", "text/csv")
        df.drop(columns=["ym"], inplace=True, errors="ignore")

    with ex3:
        st.markdown(f"#### Resumen por {periodo_nombre}")
        af_exp = df.groupby("periodo_label").agg(
            **{f"{esc}_prom": (c, "mean") for esc, c in cols_esc.items()},
            total_prom=("total_hm3","mean"),
            esclusajes_dia=("total_locks","mean"),
        ).round(3).reset_index()
        st.download_button(f"⬇️ CSV por {periodo_nombre}",
            af_exp.to_csv(index=False).encode("utf-8"),
            f"consumo_por_periodo.csv", "text/csv")

    st.markdown("---")
    st.dataframe(df.head(200), use_container_width=True, height=300)


# FOOTER
st.markdown("---")
st.markdown(
    "<div style='text-align:center; color:#aab7b8; font-size:0.85rem;'>"
    "🚢 Consumo de Esclusajes · Canal de Panamá · "
    "Datos: Autoridad del Canal de Panamá (ACP)<br>"
    "Creador: JFRodriguez</div>",
    unsafe_allow_html=True,
)
