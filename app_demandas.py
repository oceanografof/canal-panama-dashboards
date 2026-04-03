"""
💧 Dashboard Demandas de Agua por Embalse — Canal de Panamá
Creador: JFRodriguez
pip install streamlit pandas numpy plotly openpyxl
streamlit run app_demandas.py
"""
import streamlit as st, pandas as pd, numpy as np, datetime
import plotly.graph_objects as go
from plotly.subplots import make_subplots

st.set_page_config(page_title="💧 Demandas — Canal de Panamá", page_icon="💧", layout="wide")

# ═══ CONSTANTES ═══
CFS2HM3 = 1 / 408.68
CFS2M3S = 1 / 35.3147
M3S2CFS = 35.3147
HM3D2M3S = 1e6 / 86400
AHORA = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

COL = {"alhajuela":"#3498db","gatun":"#1a5276","esclusas":"#2980b9",
       "potable":"#27ae60","fugas":"#e67e22","vertidos":"#9b59b6",
       "generacion":"#f39c12","flush":"#1abc9c","pnx":"#2c3e50",
       "npx":"#16a085","total":"#c0392b","tambor":"#d35400",
       "evap":"#e74c3c","gatgen":"#f1c40f"}


def f3u(hm3):
    return f"{hm3:.3f} hm³/d · {hm3/CFS2HM3:.0f} cfs · {hm3*HM3D2M3S:.1f} m³/s"


def tbl(usos, total, nombre, dem_t):
    rows = []
    for nm, (h, c, _) in usos.items():
        rows.append({"Uso": nm, "hm³/día": round(h, 4), "cfs": round(c, 1),
                     "m³/s": round(c*CFS2M3S, 2),
                     f"% {nombre}": round(h/max(total,.001)*100, 1),
                     "% Sistema": round(h/max(dem_t,.001)*100, 1)})
    rows.append({"Uso": "TOTAL", "hm³/día": round(total, 4),
                 "cfs": round(total/CFS2HM3, 1), "m³/s": round(total*HM3D2M3S, 2),
                 f"% {nombre}": 100.0, "% Sistema": round(total/max(dem_t,.001)*100, 1)})
    return pd.DataFrame(rows)


# ═══ SIDEBAR ═══
st.sidebar.markdown("## 💧 Demandas de Agua\nCanal de Panamá\n---")

st.sidebar.markdown("### 🚢 Esclusajes")
n_pnx = st.sidebar.slider("PNX/día", 0, 40, 28)
n_npx = st.sidebar.slider("NPX/día", 0, 20, 11)
n_t = n_pnx + n_npx

st.sidebar.markdown("### 📐 Consumo por esclusaje")
modo = st.sidebar.radio("Entrada", ["hm³/escl", "cfs equiv", "m³/s equiv"], horizontal=True)
if modo == "hm³/escl":
    vp = st.sidebar.number_input("Vol PNX (hm³)", 0.05, 0.5, 0.201, 0.001, format="%.3f")
    vn = st.sidebar.number_input("Vol NPX (hm³)", 0.1, 0.8, 0.450, 0.001, format="%.3f")
elif modo == "cfs equiv":
    vp_c = st.sidebar.number_input("PNX (cfs/escl)", 20.0, 300.0, 82.2, 0.1)
    vn_c = st.sidebar.number_input("NPX (cfs/escl)", 50.0, 500.0, 184.0, 0.1)
    vp = vp_c * CFS2HM3; vn = vn_c * CFS2HM3
else:
    vp_m = st.sidebar.number_input("PNX (m³/s equiv)", 0.5, 10.0, 2.33, 0.01)
    vn_m = st.sidebar.number_input("NPX (m³/s equiv)", 1.0, 15.0, 5.21, 0.01)
    vp = vp_m / HM3D2M3S; vn = vn_m / HM3D2M3S
st.sidebar.caption(f"**PNX:** {vp:.3f} hm³ = {vp*HM3D2M3S:.2f} m³/s = {vp/CFS2HM3:.1f} cfs")
st.sidebar.caption(f"**NPX:** {vn:.3f} hm³ = {vn*HM3D2M3S:.2f} m³/s = {vn/CFS2HM3:.1f} cfs")

st.sidebar.markdown("### ⚡ Generación")
st.sidebar.markdown("Factores de conversión (cfs/MW):")
mw_madden = st.sidebar.number_input("Factor Madden (cfs/MW)", 50.0, 120.0, 80.71, 0.01, format="%.2f")
mw_gatun = st.sidebar.number_input("Factor Gatún (cfs/MW)", 100.0, 250.0, 185.40, 0.01, format="%.2f")
if mw_madden != 80.71 or mw_gatun != 185.40:
    st.sidebar.warning(f"⚠️ Factores modificados · {AHORA}")
else:
    st.sidebar.caption("Factores estándar ACP")
gm_mw = st.sidebar.slider("Madden (MW)", 0, 36, 19)
gg_mw = st.sidebar.slider("Gatún (MW)", 0, 30, 0)

st.sidebar.markdown("### 🚰 Potable (cfs)")
pot_alh = st.sidebar.number_input("Alhajuela", 0, 800, 377)
pot_gat = st.sidebar.number_input("Gatún", 0, 600, 264)

st.sidebar.markdown("### 💨 Fugas (cfs)")
fug_alh = st.sidebar.number_input("Alhajuela ", 0, 300, 71)
fug_gat = st.sidebar.number_input("Gatún ", 0, 400, 159)

st.sidebar.markdown("### 🌊 Vertidos Alhajuela (cfs)")
v_fondo = st.sidebar.number_input("Fondo Madden", 0, 5000, 0)
v_tambor = st.sidebar.number_input("Compuertas Tambor", 0, 30000, 0, 100)
v_libre = st.sidebar.number_input("Libre (overflow)", 0, 20000, 0, 100)

st.sidebar.markdown("### 🌊 Vertidos Gatún (cfs)")
v_gatun = st.sidebar.number_input("Vertido Gatún", 0, 20000, 0, 100)

st.sidebar.markdown("### 🔄 ZZ-Flush")
flush_cc = st.sidebar.number_input("Cocolí (hrs)", 0.0, 8.0, 0.0, 0.5)
flush_ac = st.sidebar.number_input("A.Clara (hrs)", 0.0, 8.0, 0.0, 0.5)

st.sidebar.markdown("### ☀️ Evaporación")
evap_gat_mm = st.sidebar.number_input("Lámina Gatún (mm/día)", 0.0, 15.0, 4.0, 0.1)
evap_alh_mm = st.sidebar.number_input("Lámina Alhajuela (mm/día)", 0.0, 15.0, 4.0, 0.1)
area_gat = st.sidebar.number_input("Área espejo Gatún (km²)", 0.0, 500.0, 425.0, 1.0)
area_alh = st.sidebar.number_input("Área espejo Alhajuela (km²)", 0.0, 100.0, 49.0, 1.0)

st.sidebar.markdown("---")
unidad = st.sidebar.radio("Unidad visual", ["hm³/día", "cfs", "m³/s"], horizontal=True)
u_label = unidad
u_cv = 1 if unidad == "hm³/día" else (1/CFS2HM3 if unidad == "cfs" else HM3D2M3S)

st.sidebar.markdown("---")
st.sidebar.caption(f"📅 Sesión: {AHORA}")


# ═══ CÁLCULOS ═══
# Esclusajes
dem_pnx = n_pnx * vp; dem_npx = n_npx * vn; dem_escl = dem_pnx + dem_npx
# Generación
gen_alh = gm_mw * mw_madden * CFS2HM3; gen_gat = gg_mw * mw_gatun * CFS2HM3; gen_tot = gen_alh + gen_gat
# Potable y fugas
alh_pot = pot_alh * CFS2HM3; gat_pot = pot_gat * CFS2HM3
alh_fug = fug_alh * CFS2HM3; gat_fug = fug_gat * CFS2HM3
# Vertidos Alhajuela
alh_vf = v_fondo * CFS2HM3; alh_vt = v_tambor * CFS2HM3; alh_vl = v_libre * CFS2HM3
alh_vert = alh_vf + alh_vt + alh_vl
# Vertidos Gatún
gat_ver = v_gatun * CFS2HM3
# ZZ-Flush
dem_flush = 333.5 * (flush_cc + flush_ac) * 3600 / 1e6
# Evaporación (mm × km² × 1e-3 = hm³)
evap_gat = evap_gat_mm * area_gat * 1e-3
evap_alh = evap_alh_mm * area_alh * 1e-3
evap_tot = evap_gat + evap_alh

# Totales por embalse
alh_total = gen_alh + alh_pot + alh_fug + alh_vert + evap_alh
gat_total = gen_gat + gat_pot + gat_fug + gat_ver + dem_escl + dem_flush + evap_gat
dem_total = alh_total + gat_total

# Diccionarios de usos
alh_usos = {
    "Generación Madden": (gen_alh, gm_mw*mw_madden, COL["generacion"]),
    "Agua Potable": (alh_pot, pot_alh, COL["potable"]),
    "Fugas": (alh_fug, fug_alh, COL["fugas"]),
    "Vertido fondo": (alh_vf, v_fondo, "#7f8c8d"),
    "Compuertas Tambor": (alh_vt, v_tambor, COL["tambor"]),
    "Vertido libre": (alh_vl, v_libre, COL["vertidos"]),
    "Evaporación": (evap_alh, evap_alh/CFS2HM3, COL["evap"]),
}
gat_usos = {
    "Esclusajes PNX": (dem_pnx, dem_pnx/CFS2HM3, COL["pnx"]),
    "Esclusajes NPX": (dem_npx, dem_npx/CFS2HM3, COL["npx"]),
    "ZZ-Flush": (dem_flush, dem_flush/CFS2HM3, COL["flush"]),
    "Generación Gatún": (gen_gat, gg_mw*mw_gatun, COL["gatgen"]),
    "Agua Potable": (gat_pot, pot_gat, COL["potable"]),
    "Fugas": (gat_fug, fug_gat, COL["fugas"]),
    "Vertido Gatún": (gat_ver, v_gatun, COL["vertidos"]),
    "Evaporación": (evap_gat, evap_gat/CFS2HM3, COL["evap"]),
}


# ═══ HEADER ═══
st.markdown(
    "<h1 style='color:#1a5276;'>💧 Demandas de Agua por Embalse</h1>"
    "<p style='color:#5d6d7e;margin-top:-12px;'>"
    "Canal de Panamá · <b>Creador: JFRodriguez</b></p>",
    unsafe_allow_html=True,
)
k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("Total", f"{dem_total*u_cv:.2f} {u_label}")
k2.metric("Alhajuela", f"{alh_total*u_cv:.2f} {u_label}")
k3.metric("Gatún", f"{gat_total*u_cv:.2f} {u_label}")
k4.metric("Esclusajes", f"{n_t}/día")
k5.metric("Generación", f"{gm_mw+gg_mw} MW")
k6.metric("Evaporación", f"{evap_tot:.2f} hm³/d")
st.markdown("---")


# ═══ TABS ═══
tabs = st.tabs(["📊 Balance", "🏔️ Alhajuela", "🌊 Gatún", "🔀 Comparar",
    "🚢 Esclusajes", "⚡ Generación", "🎯 Escenarios", "🔄 Conversor", "📂 Datos Operativos"])


# ═══ TAB 0 — BALANCE ═══
with tabs[0]:
    b1, b2 = st.columns(2)
    with b1:
        st.subheader("Por embalse")
        fig_b1 = go.Figure(go.Bar(x=["Alhajuela","Gatún","Total"],
            y=[alh_total*u_cv, gat_total*u_cv, dem_total*u_cv],
            marker_color=[COL["alhajuela"], COL["gatun"], COL["total"]],
            text=[f"{alh_total*u_cv:.2f}", f"{gat_total*u_cv:.2f}", f"{dem_total*u_cv:.2f}"],
            textposition="auto"))
        fig_b1.update_layout(yaxis_title=u_label, template="plotly_white", height=400,
            margin=dict(l=50,r=20,t=20,b=50))
        st.plotly_chart(fig_b1, use_container_width=True)
    with b2:
        st.subheader("Por uso")
        todos = {"Esclusajes":dem_escl, "Potable":alh_pot+gat_pot, "Generación":gen_tot,
                 "Fugas":alh_fug+gat_fug, "Vertidos":alh_vert+gat_ver,
                 "ZZ-Flush":dem_flush, "Evaporación":evap_tot}
        tf = {k:v for k,v in todos.items() if v > 0.001}
        cols_t = [COL["esclusas"],COL["potable"],COL["generacion"],COL["fugas"],
                  COL["vertidos"],COL["flush"],COL["evap"]]
        fig_b2 = go.Figure(go.Pie(labels=list(tf.keys()), values=[v*u_cv for v in tf.values()],
            marker_colors=cols_t[:len(tf)], hole=0.45, textinfo="percent+label", textposition="outside"))
        fig_b2.update_layout(height=400, template="plotly_white",
            margin=dict(l=10,r=10,t=20,b=10), showlegend=False)
        st.plotly_chart(fig_b2, use_container_width=True)

    # Gauges
    gauge_cols = st.columns(6)
    gauge_data = [
        ("Esclusajes", dem_escl, COL["esclusas"]),
        ("Potable", alh_pot+gat_pot, COL["potable"]),
        ("Generación", gen_tot, COL["generacion"]),
        ("Fugas", alh_fug+gat_fug, COL["fugas"]),
        ("Vertidos", alh_vert+gat_ver+dem_flush, COL["vertidos"]),
        ("Evaporación", evap_tot, COL["evap"]),
    ]
    for col_g, (nm, val, cl) in zip(gauge_cols, gauge_data):
        with col_g:
            pct = val / max(dem_total, .001) * 100
            fig_gauge = go.Figure(go.Indicator(mode="gauge+number", value=pct,
                title={"text": nm, "font": {"size": 11}},
                number={"suffix": "%", "font": {"size": 18}},
                gauge={"axis": {"range": [0, 100]}, "bar": {"color": cl}}))
            fig_gauge.update_layout(height=160, margin=dict(l=10,r=10,t=35,b=5))
            st.plotly_chart(fig_gauge, use_container_width=True)

    # Tabla completa
    st.subheader("Tabla completa (hm³/día · cfs · m³/s)")
    rows = []
    all_usos = {**{f"[ALH] {k}": v for k, v in alh_usos.items()},
                **{f"[GAT] {k}": v for k, v in gat_usos.items()}}
    for nm, (h, cf, _) in all_usos.items():
        if h > 0.0001:
            rows.append({"Uso": nm, "hm³/día": round(h, 4), "cfs": round(cf, 1),
                         "m³/s": round(cf*CFS2M3S, 2), "%": round(h/max(dem_total,.001)*100, 1)})
    rows.append({"Uso": "TOTAL", "hm³/día": round(dem_total, 4), "cfs": round(dem_total/CFS2HM3, 1),
                 "m³/s": round(dem_total*HM3D2M3S, 2), "%": 100.0})
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# ═══ TAB 1 — ALHAJUELA ═══
with tabs[1]:
    st.subheader("🏔️ Embalse Alhajuela"); st.metric("Total", f3u(alh_total))
    c1, c2 = st.columns(2)
    with c1:
        af = {k: v[0] for k, v in alh_usos.items() if v[0] > 0.001}
        if af:
            fig_a1 = go.Figure(go.Pie(labels=list(af.keys()), values=[v*u_cv for v in af.values()],
                marker_colors=[alh_usos[k][2] for k in af], hole=0.45, textinfo="percent+label"))
            fig_a1.update_layout(height=400, template="plotly_white",
                margin=dict(l=10,r=10,t=20,b=10), showlegend=False)
            st.plotly_chart(fig_a1, use_container_width=True)
    with c2:
        fig_a2 = go.Figure()
        for nm, (h, cf, cl) in alh_usos.items():
            if h > 0.001:
                fig_a2.add_trace(go.Bar(y=[nm], x=[h*u_cv], orientation="h", marker_color=cl,
                    text=[f"{h*u_cv:.3f}"], textposition="auto", showlegend=False))
        fig_a2.update_layout(xaxis_title=u_label, template="plotly_white", height=400,
            margin=dict(l=10,r=20,t=20,b=50))
        st.plotly_chart(fig_a2, use_container_width=True)
    st.dataframe(tbl(alh_usos, alh_total, "Alhajuela", dem_total), use_container_width=True, hide_index=True)


# ═══ TAB 2 — GATÚN ═══
with tabs[2]:
    st.subheader("🌊 Embalse Gatún"); st.metric("Total", f3u(gat_total))
    c1, c2 = st.columns(2)
    with c1:
        gf = {k: v[0] for k, v in gat_usos.items() if v[0] > 0.001}
        fig_g1 = go.Figure(go.Pie(labels=list(gf.keys()), values=[v*u_cv for v in gf.values()],
            marker_colors=[gat_usos[k][2] for k in gf], hole=0.45, textinfo="percent+label"))
        fig_g1.update_layout(height=400, template="plotly_white",
            margin=dict(l=10,r=10,t=20,b=10), showlegend=False)
        st.plotly_chart(fig_g1, use_container_width=True)
    with c2:
        fig_g2 = go.Figure()
        for nm, (h, cf, cl) in gat_usos.items():
            if h > 0.001:
                fig_g2.add_trace(go.Bar(y=[nm], x=[h*u_cv], orientation="h", marker_color=cl,
                    text=[f"{h*u_cv:.3f}"], textposition="auto", showlegend=False))
        fig_g2.update_layout(xaxis_title=u_label, template="plotly_white", height=400,
            margin=dict(l=10,r=20,t=20,b=50))
        st.plotly_chart(fig_g2, use_container_width=True)
    st.dataframe(tbl(gat_usos, gat_total, "Gatún", dem_total), use_container_width=True, hide_index=True)


# ═══ TAB 3 — COMPARAR ═══
with tabs[3]:
    st.subheader("Alhajuela vs Gatún")
    uc = ["Generación", "Potable", "Fugas", "Vertidos", "Esclusajes", "Flush", "Evaporación"]
    va2 = [gen_alh, alh_pot, alh_fug, alh_vert, 0, 0, evap_alh]
    vg2 = [gen_gat, gat_pot, gat_fug, gat_ver, dem_escl, dem_flush, evap_gat]

    fig_comp = go.Figure()
    fig_comp.add_trace(go.Bar(x=uc, y=[v*u_cv for v in va2], name="Alhajuela", marker_color=COL["alhajuela"]))
    fig_comp.add_trace(go.Bar(x=uc, y=[v*u_cv for v in vg2], name="Gatún", marker_color=COL["gatun"]))
    fig_comp.update_layout(barmode="group", yaxis_title=u_label, template="plotly_white",
        height=450, margin=dict(l=50,r=20,t=20,b=50))
    st.plotly_chart(fig_comp, use_container_width=True)

    cc1, cc2 = st.columns(2)
    with cc1:
        fig_comp2 = go.Figure(go.Pie(labels=["Alhajuela","Gatún"], values=[alh_total, gat_total],
            marker_colors=[COL["alhajuela"],COL["gatun"]], hole=0.5,
            textinfo="percent+label+value", texttemplate="%{label}<br>%{percent}<br>%{value:.2f} hm³/d"))
        fig_comp2.update_layout(height=350, template="plotly_white", margin=dict(l=10,r=10,t=20,b=10))
        st.plotly_chart(fig_comp2, use_container_width=True)
    with cc2:
        # Tabla comparativa
        comp_rows = []
        for uso_n, va_v, vg_v in zip(uc, va2, vg2):
            comp_rows.append({"Uso": uso_n,
                "Alh (hm³/d)": round(va_v, 3), "Alh (cfs)": round(va_v/CFS2HM3, 1),
                "Gat (hm³/d)": round(vg_v, 3), "Gat (cfs)": round(vg_v/CFS2HM3, 1),
                "Total (m³/s)": round((va_v+vg_v)*HM3D2M3S, 2)})
        comp_rows.append({"Uso": "TOTAL",
            "Alh (hm³/d)": round(alh_total, 3), "Alh (cfs)": round(alh_total/CFS2HM3, 1),
            "Gat (hm³/d)": round(gat_total, 3), "Gat (cfs)": round(gat_total/CFS2HM3, 1),
            "Total (m³/s)": round(dem_total*HM3D2M3S, 2)})
        st.dataframe(pd.DataFrame(comp_rows), use_container_width=True, hide_index=True)


# ═══ TAB 4 — ESCLUSAJES ═══
with tabs[4]:
    st.subheader("🚢 Dashboard de Esclusajes")
    ek1, ek2, ek3, ek4 = st.columns(4)
    ek1.metric("Total esclusajes", f"{n_t}/día")
    ek2.metric("Consumo total", f3u(dem_escl))
    ek3.metric("% de demanda", f"{dem_escl/max(dem_total,.001)*100:.1f}%")
    ek4.metric("Vol prom/escl", f"{dem_escl/max(n_t,1):.3f} hm³")

    ec1, ec2 = st.columns(2)
    with ec1:
        fig_e1 = go.Figure(go.Bar(x=["Panamax","Neopanamax","Total"],
            y=[dem_pnx*u_cv, dem_npx*u_cv, dem_escl*u_cv],
            marker_color=[COL["pnx"], COL["npx"], COL["esclusas"]],
            text=[f"{dem_pnx*u_cv:.2f}", f"{dem_npx*u_cv:.2f}", f"{dem_escl*u_cv:.2f}"],
            textposition="auto"))
        fig_e1.update_layout(yaxis_title=u_label, template="plotly_white", height=380,
            margin=dict(l=50,r=20,t=20,b=50))
        st.plotly_chart(fig_e1, use_container_width=True)
    with ec2:
        fig_e2 = go.Figure(go.Pie(labels=["Panamax","Neopanamax"], values=[dem_pnx, dem_npx],
            marker_colors=[COL["pnx"],COL["npx"]], hole=0.45,
            textinfo="percent+label+value",
            texttemplate="%{label}<br>%{percent}<br>%{value:.2f} hm³/d"))
        fig_e2.update_layout(height=380, template="plotly_white",
            margin=dict(l=10,r=10,t=20,b=10), showlegend=False)
        st.plotly_chart(fig_e2, use_container_width=True)

    st.subheader("Detalle (3 unidades)")
    ed = []
    for tipo, n, v, th in [("Panamax",n_pnx,vp,dem_pnx), ("Neopanamax",n_npx,vn,dem_npx)]:
        ed.append({"Tipo": tipo, "N/día": n,
            "hm³/escl": round(v, 3), "cfs/escl": round(v/CFS2HM3, 1), "m³/s/escl": round(v*HM3D2M3S, 2),
            "hm³/día": round(th, 2), "cfs": round(th/CFS2HM3, 0), "m³/s": round(th*HM3D2M3S, 1)})
    ed.append({"Tipo": "TOTAL", "N/día": n_t,
        "hm³/escl": round(dem_escl/max(n_t,1), 3), "cfs/escl": round(dem_escl/max(n_t,1)/CFS2HM3, 1),
        "m³/s/escl": round(dem_escl/max(n_t,1)*HM3D2M3S, 2),
        "hm³/día": round(dem_escl, 2), "cfs": round(dem_escl/CFS2HM3, 0), "m³/s": round(dem_escl*HM3D2M3S, 1)})
    st.dataframe(pd.DataFrame(ed), use_container_width=True, hide_index=True)

    st.subheader("Proyección acumulada")
    pr1, pr2, pr3 = st.columns(3)
    pr1.metric("Diario", f"{dem_escl:.2f} hm³ · {dem_escl/CFS2HM3:.0f} cfs")
    pr2.metric("Mensual (30d)", f"{dem_escl*30:.1f} hm³")
    pr3.metric("Anual (365d)", f"{dem_escl*365:.0f} hm³")


# ═══ TAB 5 — GENERACIÓN ═══
with tabs[5]:
    st.subheader("⚡ Dashboard de Hidrogeneración")

    hk1, hk2, hk3, hk4 = st.columns(4)
    hk1.metric("Madden", f"{gm_mw} MW")
    hk2.metric("Gatún", f"{gg_mw} MW")
    hk3.metric("Total", f"{gm_mw+gg_mw} MW")
    hk4.metric("Agua usada", f3u(gen_tot))

    hc1, hc2 = st.columns(2)
    with hc1:
        fig_h1 = go.Figure(go.Bar(x=["Madden","Gatún","Total"],
            y=[gen_alh*u_cv, gen_gat*u_cv, gen_tot*u_cv],
            marker_color=[COL["generacion"], COL["gatgen"], COL["total"]],
            text=[f"{gen_alh*u_cv:.2f}", f"{gen_gat*u_cv:.2f}", f"{gen_tot*u_cv:.2f}"],
            textposition="auto"))
        fig_h1.update_layout(yaxis_title=u_label, template="plotly_white", height=380,
            margin=dict(l=50,r=20,t=20,b=50))
        st.plotly_chart(fig_h1, use_container_width=True)
    with hc2:
        st.markdown(f"""
**Factores de conversión actuales:**

| Central | cfs/MW | m³/s por MW | Estado |
|---------|--------|-------------|--------|
| Madden | **{mw_madden:.2f}** | {mw_madden*CFS2M3S:.2f} | {"⚠️ Modificado" if mw_madden != 80.71 else "✅ Estándar"} |
| Gatún | **{mw_gatun:.2f}** | {mw_gatun*CFS2M3S:.2f} | {"⚠️ Modificado" if mw_gatun != 185.40 else "✅ Estándar"} |

**Consumo actual:**

| Central | MW | cfs | m³/s | hm³/día |
|---------|-----|------|------|---------|
| Madden | {gm_mw} | {gm_mw*mw_madden:.1f} | {gm_mw*mw_madden*CFS2M3S:.1f} | {gen_alh:.3f} |
| Gatún | {gg_mw} | {gg_mw*mw_gatun:.1f} | {gg_mw*mw_gatun*CFS2M3S:.1f} | {gen_gat:.3f} |
| **Total** | **{gm_mw+gg_mw}** | **{gm_mw*mw_madden+gg_mw*mw_gatun:.1f}** | **{(gm_mw*mw_madden+gg_mw*mw_gatun)*CFS2M3S:.1f}** | **{gen_tot:.3f}** |
        """)

    st.metric("% del sistema", f"{gen_tot/max(dem_total,.001)*100:.1f}%")
    if mw_madden != 80.71 or mw_gatun != 185.40:
        st.warning(f"⚠️ Factores de conversión modificados el {AHORA}. "
                   f"Estándar ACP: Madden=80.71, Gatún=185.4 cfs/MW")


# ═══ TAB 6 — ESCENARIOS ═══
with tabs[6]:
    st.subheader("🎯 Probable · Optimista · Pesimista")

    def calc_esc(p):
        a = p["gm"]*p["mw_m"]*CFS2HM3 + p["pa"]*CFS2HM3 + p["fa"]*CFS2HM3 + p["va"]*CFS2HM3 + p["ea"]
        e = p["np"]*p["vp"] + p["nn"]*p["vn"]
        g = p["gg"]*p["mw_g"]*CFS2HM3 + p["pg"]*CFS2HM3 + p["fg_val"]*CFS2HM3 + p["vg"]*CFS2HM3 + e + p["eg"]
        return {"A": a, "G": g, "T": a+g, "E": e, "N": p["np"]+p["nn"]}

    presets = {
        "🟡 Probable": {"np":n_pnx,"nn":n_npx,"vp":vp,"vn":vn,
            "gm":gm_mw,"gg":gg_mw,"mw_m":mw_madden,"mw_g":mw_gatun,
            "pa":pot_alh,"pg":pot_gat,"fa":fug_alh,"fg_val":fug_gat,
            "va":v_fondo+v_tambor+v_libre,"vg":v_gatun,"ea":evap_alh,"eg":evap_gat},
        "🟢 Optimista": {"np":30,"nn":14,"vp":0.190,"vn":0.397,
            "gm":20,"gg":5,"mw_m":mw_madden,"mw_g":mw_gatun,
            "pa":350,"pg":250,"fa":50,"fg_val":120,
            "va":0,"vg":0,"ea":evap_alh,"eg":evap_gat},
        "🔴 Pesimista": {"np":22,"nn":7,"vp":0.210,"vn":0.450,
            "gm":10,"gg":0,"mw_m":mw_madden,"mw_g":mw_gatun,
            "pa":420,"pg":300,"fa":90,"fg_val":200,
            "va":0,"vg":0,"ea":evap_alh,"eg":evap_gat},
    }

    esc_results = {}
    esc_cols = st.columns(3)
    for (nombre, pre), col_e in zip(presets.items(), esc_cols):
        with col_e:
            st.markdown(f"#### {nombre}")
            p = dict(pre)  # copia
            p["np"] = st.number_input("PNX", 0, 40, pre["np"], key=f"e1{nombre}")
            p["nn"] = st.number_input("NPX", 0, 20, pre["nn"], key=f"e2{nombre}")
            p["vp"] = st.number_input("Vol PNX", 0.1, 0.4, pre["vp"], 0.001, key=f"e3{nombre}", format="%.3f")
            p["vn"] = st.number_input("Vol NPX", 0.1, 0.6, pre["vn"], 0.001, key=f"e4{nombre}", format="%.3f")
            p["gm"] = st.number_input("Gen Mad MW", 0, 36, pre["gm"], key=f"e5{nombre}")
            esc_results[nombre] = calc_esc(p)

    st.markdown("---")
    fig_esc = go.Figure()
    fig_esc.add_trace(go.Bar(x=list(esc_results.keys()),
        y=[r["E"]*u_cv for r in esc_results.values()], name="Esclusajes", marker_color=COL["esclusas"]))
    fig_esc.add_trace(go.Bar(x=list(esc_results.keys()),
        y=[(r["T"]-r["E"])*u_cv for r in esc_results.values()], name="Otros usos", marker_color=COL["alhajuela"]))
    fig_esc.update_layout(barmode="stack", yaxis_title=u_label, template="plotly_white",
        height=400, margin=dict(l=50,r=20,t=20,b=50))
    st.plotly_chart(fig_esc, use_container_width=True)

    st.dataframe(pd.DataFrame([
        {"Escenario": n, "N/día": r["N"],
         "hm³/día": round(r["T"], 2), "cfs": round(r["T"]/CFS2HM3, 0),
         "m³/s": round(r["T"]*HM3D2M3S, 1)}
        for n, r in esc_results.items()
    ]), use_container_width=True, hide_index=True)

    prob_t = list(esc_results.values())[0]["T"]
    for n, r in list(esc_results.items())[1:]:
        d = r["T"] - prob_t
        st.markdown(f"**{n}:** {d:+.2f} hm³/d ({d/max(prob_t,.001)*100:+.1f}% vs Probable)")


# ═══ TAB 7 — CONVERSOR ═══
with tabs[7]:
    st.subheader("🔄 Conversor de unidades")
    cv1, cv2 = st.columns(2)
    with cv1:
        st.markdown("### Caudal")
        m1 = st.radio("Desde:", ["cfs","m³/s","hm³/día"], horizontal=True, key="mq")
        v1 = st.number_input("Valor", 0.0, 999999.0, 100.0, key="vq")
        if m1 == "cfs":
            st.success(f"**{v1:.2f} cfs** = **{v1*CFS2M3S:.4f} m³/s** = **{v1*CFS2HM3:.4f} hm³/día**")
        elif m1 == "m³/s":
            st.success(f"**{v1:.4f} m³/s** = **{v1*M3S2CFS:.2f} cfs** = **{v1*M3S2CFS*CFS2HM3:.4f} hm³/día**")
        else:
            st.success(f"**{v1:.4f} hm³/día** = **{v1/CFS2HM3:.2f} cfs** = **{v1*HM3D2M3S:.4f} m³/s**")
    with cv2:
        st.markdown("### Volumen")
        m2 = st.radio("Desde:", ["hm³","MPC","acre-ft"], horizontal=True, key="mv")
        v2 = st.number_input("Valor ", 0.0, 999999.0, 1.0, key="vv")
        if m2 == "hm³":
            st.success(f"**{v2:.4f} hm³** = {v2*1e6/28.3168:.0f} MPC = {v2*810.71:.1f} acre-ft")
        elif m2 == "MPC":
            h = v2*28.3168/1e6
            st.success(f"**{v2:.0f} MPC** = {h:.4f} hm³ = {h*810.71:.1f} acre-ft")
        else:
            h = v2/810.71
            st.success(f"**{v2:.1f} acre-ft** = {h:.4f} hm³")
    st.markdown("---")
    st.dataframe(pd.DataFrame([
        {"cfs": r, "m³/s": round(r*CFS2M3S, 3), "hm³/día": round(r*CFS2HM3, 4), "hm³/mes": round(r*CFS2HM3*30, 2)}
        for r in [1,10,50,100,500,1000,2000,4000,5000]
    ]), use_container_width=True, hide_index=True)


# ═══ TAB 8 — DATOS OPERATIVOS ═══
with tabs[8]:
    st.subheader("📂 Datos Operativos — LakeHouse")

    @st.cache_data(show_spinner="Cargando LakeHouse...")
    def cargar_lkh(src, sh):
        df = pd.read_excel(src, sheet_name=sh)
        col_f = None
        for c in df.columns:
            if "date" in str(c).lower(): col_f = c; break
        if col_f is None: col_f = df.columns[1]
        df["fecha"] = pd.to_datetime(df[col_f], errors="coerce")
        df = df.dropna(subset=["fecha"]).sort_values("fecha").reset_index(drop=True)
        rn = {}
        for c in df.columns:
            cl = str(c).lower()
            if "madel" in cl: rn[c] = "nv_a"
            elif "gatel" in cl: rn[c] = "nv_g"
            elif cl == "numlockgat": rn[c] = "n_g"
            elif cl == "numlockpm": rn[c] = "n_p"
            elif cl == "numlockac" or cl == "numlockacl": rn[c] = "n_a"
            elif cl == "numlockccl": rn[c] = "n_c"
            elif cl == "gatlockhm3": rn[c] = "gat_hm3"
            elif cl == "pmlockhm3": rn[c] = "pm_hm3"
            elif cl == "aclockhm3": rn[c] = "acl_hm3"
            elif cl == "ccllockhm3": rn[c] = "ccl_hm3"
            elif "gatlockmcf" in cl: rn[c] = "gat_mcf"
            elif "pmlockmcf" in cl: rn[c] = "pm_mcf"
            elif "aclockmcf" in cl: rn[c] = "acl_mcf"
            elif "ccllockmcf" in cl: rn[c] = "ccl_mcf"
            elif cl == "gatspill": rn[c] = "vert_g"
            elif cl == "madspill": rn[c] = "vert_m"
            elif cl == "munic_mad_hm3": rn[c] = "mun_m_hm3"
            elif cl == "munic_gat_hm3": rn[c] = "mun_g_hm3"
            elif cl == "munic_mad": rn[c] = "mun_m"
            elif cl == "munic_gat": rn[c] = "mun_g"
            elif cl == "leak_mad": rn[c] = "leak_m"
            elif cl == "leak_gat": rn[c] = "leak_g"
            elif cl == "evap_gatun_mm": rn[c] = "evap_gat_mm"
            elif cl == "evap_alaj_mm": rn[c] = "evap_alh_mm"
            elif cl == "vol_evap_gat_hm3": rn[c] = "evap_gat_hm3"
            elif cl == "vol_evap_ala_hm3": rn[c] = "evap_alh_hm3"
            elif cl == "saving_water_panamax": rn[c] = "ahorro_pnx"
            elif cl == "total_saving_water_neo_hm3" or cl == "cca_neo": rn[c] = "ahorro_npx"
            elif cl == "madhm3": rn[c] = "gen_mad_hm3"
            elif cl == "gathm3": rn[c] = "gen_gat_hm3"
            elif cl == "madmwh" or cl == "madmwh": rn[c] = "mad_mwh"
            elif cl == "gatmwh": rn[c] = "gat_mwh"
            elif "total todos" in cl and "hec" in cl: rn[c] = "total_escl_hm3"
            elif cl == "agua_disp_ala" or cl == "agua_dip_ala_gat": pass  # skip ambiguous
            elif cl == "capgat_hm3": rn[c] = "cap_gat_hm3"
            elif cl == "capmad_hm3": rn[c] = "cap_mad_hm3"
        df = df.rename(columns=rn)
        for c in rn.values():
            if c in df: df[c] = pd.to_numeric(df[c], errors="coerce")
        # Calcular totales si no existen
        if "gat_hm3" in df and "pm_hm3" in df:
            df["pnx_hm3"] = df["gat_hm3"].fillna(0) + df["pm_hm3"].fillna(0)
        if "acl_hm3" in df and "ccl_hm3" in df:
            df["npx_hm3"] = df["acl_hm3"].fillna(0) + df["ccl_hm3"].fillna(0)
        if "pnx_hm3" in df and "npx_hm3" in df:
            df["total_hm3"] = df["pnx_hm3"] + df["npx_hm3"]
        elif "gat_mcf" in df and "pm_mcf" in df:
            df["pnx_m"] = df["gat_mcf"].fillna(0) + df["pm_mcf"].fillna(0)
            if "acl_mcf" in df and "ccl_mcf" in df:
                df["npx_m"] = df["acl_mcf"].fillna(0) + df["ccl_mcf"].fillna(0)
                df["pnx_hm3"] = df["pnx_m"] * CFS2HM3
                df["npx_hm3"] = df["npx_m"] * CFS2HM3
                df["total_hm3"] = df["pnx_hm3"] + df["npx_hm3"]
        if "n_g" in df and "n_p" in df: df["n_pnx_r"] = df["n_g"].fillna(0) + df["n_p"].fillna(0)
        if "n_a" in df and "n_c" in df: df["n_npx_r"] = df["n_a"].fillna(0) + df["n_c"].fillna(0)
        return df

    import glob as _g
    lf = sorted(_g.glob("LakeHouse*.xlsx")); dl = None
    if lf:
        try:
            hs = pd.ExcelFile(lf[0]).sheet_names
            hojas_validas = [x for x in hs if x not in ["Sheet1", "Para BalanceH"]]
            hoja = st.selectbox("Hoja", hojas_validas) if len(hojas_validas) > 1 else hojas_validas[0]
            dl = cargar_lkh(lf[0], hoja)
            st.success(f"✅ {len(dl):,} registros · {dl['fecha'].min().date()} → {dl['fecha'].max().date()}")
        except Exception as e: st.error(str(e))
    else:
        fl = st.file_uploader("Sube LakeHouse (xlsx)", type=["xlsx"], key="lk")
        if fl:
            try:
                fl.seek(0)
                xls = pd.ExcelFile(fl)
                hojas_validas = [x for x in xls.sheet_names if x not in ["Sheet1", "Para BalanceH"]]
                hoja = st.selectbox("Hoja", hojas_validas) if len(hojas_validas) > 1 else hojas_validas[0]
                fl.seek(0)
                dl = cargar_lkh(fl, hoja)
                st.success(f"✅ {len(dl):,} registros · {dl['fecha'].min().date()} → {dl['fecha'].max().date()}")
            except Exception as e: st.error(str(e))

    if dl is not None and len(dl) > 0:
        # ── Selector de días ──
        total_dias = (dl["fecha"].max() - dl["fecha"].min()).days
        st.markdown("---")
        dias_sel = st.slider(
            "📅 Promedio de los últimos N días (desde el más reciente hacia atrás)",
            min_value=7, max_value=min(total_dias, 365),
            value=min(30, total_dias), step=1,
        )
        fecha_corte = dl["fecha"].max() - pd.Timedelta(days=dias_sel)
        dv = dl[dl["fecha"] >= fecha_corte].copy()  # dv = datos visibles
        st.caption(f"Mostrando: **{len(dv)} días** · {dv['fecha'].min().date()} → {dv['fecha'].max().date()}")

        # ── KPIs con promedio del período seleccionado ──
        st.markdown("---")
        lk1, lk2, lk3, lk4, lk5, lk6 = st.columns(6)
        if "nv_g" in dv: lk1.metric("Nivel Gatún", f"{dv['nv_g'].iloc[-1]:.2f} ft")
        if "nv_a" in dv: lk2.metric("Nivel Alhajuela", f"{dv['nv_a'].iloc[-1]:.2f} ft")
        if "n_pnx_r" in dv: lk3.metric(f"PNX/d ({dias_sel}d)", f"{dv['n_pnx_r'].mean():.0f}")
        if "n_npx_r" in dv: lk4.metric(f"NPX/d ({dias_sel}d)", f"{dv['n_npx_r'].mean():.0f}")
        if "total_hm3" in dv: lk5.metric(f"Consumo ({dias_sel}d)", f"{dv['total_hm3'].mean():.2f} hm³/d")
        if "total_escl_hm3" in dv: lk6.metric(f"Total escl ({dias_sel}d)", f"{dv['total_escl_hm3'].mean():.2f} hm³/d")

        # ── Niveles ──
        if "nv_g" in dv and "nv_a" in dv:
            st.subheader("Niveles de embalses")
            fig_nv = make_subplots(specs=[[{"secondary_y": True}]])
            fig_nv.add_trace(go.Scatter(x=dv["fecha"], y=dv["nv_g"], name="Gatún (ft)",
                line=dict(color=COL["gatun"], width=2)), secondary_y=False)
            fig_nv.add_trace(go.Scatter(x=dv["fecha"], y=dv["nv_a"], name="Alhajuela (ft)",
                line=dict(color=COL["alhajuela"], width=2)), secondary_y=True)
            fig_nv.update_yaxes(title_text="Gatún ft", secondary_y=False)
            fig_nv.update_yaxes(title_text="Alhajuela ft", secondary_y=True)
            fig_nv.update_layout(template="plotly_white", height=380, hovermode="x unified",
                margin=dict(l=50, r=60, t=20, b=50))
            st.plotly_chart(fig_nv, use_container_width=True)

        # ── Esclusajes ──
        if "total_hm3" in dv or "pnx_hm3" in dv:
            st.subheader(f"Consumo de esclusajes — últimos {dias_sel} días")
            fig_lk = go.Figure()
            if "pnx_hm3" in dv:
                fig_lk.add_trace(go.Bar(x=dv["fecha"], y=dv["pnx_hm3"], name="PNX", marker_color=COL["pnx"]))
            if "npx_hm3" in dv:
                fig_lk.add_trace(go.Bar(x=dv["fecha"], y=dv["npx_hm3"], name="NPX", marker_color=COL["npx"]))
            fig_lk.add_hline(y=dem_escl, line_dash="dash", line_color=COL["total"],
                annotation_text=f"Modelo: {dem_escl:.2f} hm³/d")
            col_th = "total_hm3" if "total_hm3" in dv else "total_escl_hm3"
            if col_th in dv:
                prom_real = dv[col_th].mean()
                fig_lk.add_hline(y=prom_real, line_dash="dot", line_color=COL["esclusas"],
                    annotation_text=f"Real prom {dias_sel}d: {prom_real:.2f}")
            fig_lk.update_layout(barmode="stack", yaxis_title="hm³/día", template="plotly_white",
                height=400, margin=dict(l=50, r=20, t=20, b=50))
            st.plotly_chart(fig_lk, use_container_width=True)

            # Modelo vs Real
            if col_th in dv:
                real_p = dv[col_th].mean()
                dif = dem_escl - real_p
                mr1, mr2, mr3 = st.columns(3)
                mr1.metric(f"Real prom ({dias_sel}d)", f3u(real_p))
                mr2.metric("Modelo", f3u(dem_escl))
                mr3.metric("Diferencia", f"{dif:+.3f} hm³/d ({dif/max(real_p,.001)*100:+.1f}%)")

        # ── Tabla de promedios del período ──
        st.subheader(f"Promedios últimos {dias_sel} días")
        prom_rows = []
        prom_cols = [
            ("nv_g", "Nivel Gatún", "ft"),
            ("nv_a", "Nivel Alhajuela", "ft"),
            ("n_pnx_r", "Esclusajes PNX", "/día"),
            ("n_npx_r", "Esclusajes NPX", "/día"),
            ("pnx_hm3", "Consumo PNX", "hm³/d"),
            ("npx_hm3", "Consumo NPX", "hm³/d"),
            ("total_hm3", "Consumo total escl.", "hm³/d"),
            ("gen_mad_hm3", "Generación Madden", "hm³/d"),
            ("gen_gat_hm3", "Generación Gatún", "hm³/d"),
            ("mun_m", "Potable Alhajuela", "MCF"),
            ("mun_g", "Potable Gatún", "MCF"),
            ("leak_m", "Fugas Alhajuela", "MCF"),
            ("leak_g", "Fugas Gatún", "MCF"),
            ("vert_g", "Vertido Gatún", "MCF"),
            ("vert_m", "Vertido Madden", "MCF"),
            ("evap_gat_mm", "Evaporación Gatún", "mm/d"),
            ("evap_alh_mm", "Evaporación Alhajuela", "mm/d"),
            ("evap_gat_hm3", "Vol. evap. Gatún", "hm³/d"),
            ("evap_alh_hm3", "Vol. evap. Alhajuela", "hm³/d"),
            ("ahorro_pnx", "Ahorro PNX", "hm³/d"),
            ("ahorro_npx", "Ahorro NPX", "hm³/d"),
        ]
        for col_name, label, unit in prom_cols:
            if col_name in dv and dv[col_name].notna().sum() > 0:
                val = dv[col_name].mean()
                prom_rows.append({
                    "Parámetro": label,
                    "Promedio": round(val, 3),
                    "Mínimo": round(dv[col_name].min(), 3),
                    "Máximo": round(dv[col_name].max(), 3),
                    "Unidad": unit,
                })
        if prom_rows:
            st.dataframe(pd.DataFrame(prom_rows), use_container_width=True, hide_index=True)

        # ── Balance hídrico ──
        if "mun_m" in dv:
            st.subheader(f"Balance hídrico — últimos {dias_sel} días (MCF/día)")
            fig_bal = go.Figure()
            for cn, nm, cl in [
                ("pnx_hm3", "Escl. PNX", COL["pnx"]),
                ("npx_hm3", "Escl. NPX", COL["npx"]),
                ("mun_m", "Pot. Alh", COL["potable"]),
                ("mun_g", "Pot. Gat", "#2ecc71"),
                ("leak_m", "Fug. Alh", COL["fugas"]),
                ("leak_g", "Fug. Gat", "#f39c12"),
                ("vert_g", "Vert. Gat", COL["vertidos"]),
            ]:
                if cn in dv and dv[cn].notna().sum() > 0:
                    fig_bal.add_trace(go.Bar(x=dv["fecha"], y=dv[cn], name=nm, marker_color=cl))
            fig_bal.update_layout(barmode="stack", yaxis_title="MCF ó hm³/d",
                template="plotly_white", height=420, hovermode="x unified",
                margin=dict(l=50, r=20, t=20, b=50))
            st.plotly_chart(fig_bal, use_container_width=True)

        st.markdown("---")
        st.download_button("⬇️ Descargar período (CSV)",
            dv.to_csv(index=False).encode("utf-8"),
            f"lakehouse_{dias_sel}dias.csv", "text/csv")
    else:
        st.info("Sube **LakeHouse_Data.xlsx** o **LakeHouse_NEW.xlsx**, o colócalo en la carpeta.")


# FOOTER
st.markdown("---")
st.markdown(
    "<div style='text-align:center;color:#aab7b8;font-size:0.85rem;'>"
    "💧 Demandas de Agua · Canal de Panamá · ACP<br>"
    f"Creador: JFRodriguez · Sesión: {AHORA}</div>",
    unsafe_allow_html=True,
)
