"""
💧 Dashboard Demandas de Agua por Embalse — Canal de Panamá
Creador: JFRodriguez
pip install streamlit pandas numpy plotly openpyxl pillow pyxlsb
streamlit run app_demandas.py
"""
import streamlit as st, pandas as pd, numpy as np, datetime, io, base64, os
import plotly.graph_objects as go
from plotly.subplots import make_subplots

st.set_page_config(page_title="💧 Demandas — Canal de Panamá", page_icon="💧", layout="wide")

# ═══ CONSTANTES ═══
CFS2HM3  = 1 / 408.68
CFS2M3S  = 1 / 35.3147
M3S2CFS  = 35.3147
HM3D2M3S = 1e6 / 86400
AHORA    = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

COL = {"alhajuela":"#3498db","gatun":"#1a5276","esclusas":"#2980b9",
       "potable":"#27ae60","fugas":"#e67e22","vertidos":"#9b59b6",
       "generacion":"#f39c12","flush":"#1abc9c","pnx":"#2c3e50",
       "npx":"#16a085","total":"#c0392b","tambor":"#d35400",
       "evap":"#e74c3c","gatgen":"#f1c40f"}

# ── Curvas hipsométricas (nivel ft → área km²) ──────────────────────────────
_NV_GAT  = np.array([55, 60, 65, 70, 75, 79, 82, 84, 85, 86, 87, 88, 89])
_AR_GAT  = np.array([220,255,285,318,350,375,394,408,414,420,425,430,436])

_NV_ALH  = np.array([180,190,200,210,220,228,235,240,245,248,252,255])
_AR_ALH  = np.array([ 10, 14, 19, 25, 31, 36, 40, 43, 46, 47, 49, 51])

# ── Constantes físicas del modelo de esclusajes (ConsumodeAguaEsclusas.xlsb) ─
# Fuente: hoja NeoPanamax (CC=Cocolí, AC=Agua Clara)
AC_NPX      = 26841.0       # m²  Área de cámara NPX
EQ_CC_m     = 18.407        # m   Nivel equivalente de equilibrio — Cocolí
EQ_AC_m     = 17.679        # m   Nivel equivalente de equilibrio — Agua Clara
FRAC_TINAS  = 0.60          # 60% de ahorro por tránsito con tinas activas
# Fuente: hoja Panamax
AC_PNX_REG  = 11132.878     # m²  Área cámara PNX Regular
AC_PNX_COR  = 10136.590     # m²  Área cámara PNX Corta
EQ_PM_ft    = 16.611        # ft  Nivel equiv. PedroMiguel (PNX)
EQ_GA_ft    = 17.830        # ft  Nivel equiv. Gatún (PNX)
CALIB_VPX   = 0.21407       # hm³ Vol/tránsito PNX regular @ H=87.5 ft (calibrado)
CALIB_H_REF = 87.5          # ft  Nivel de referencia de calibración PNX

def _npx_vol_base(H_ft: float) -> float:
    """Volumen base por tránsito NPX sin tinas (hm³) — función del nivel Gatún."""
    H_m = H_ft * 0.3048
    return AC_NPX * (max(H_m - EQ_CC_m, 0) + max(H_m - EQ_AC_m, 0)) * 1e-6

def _pnx_vol_base(H_ft: float) -> float:
    """Volumen base por tránsito PNX con cámara Regular (hm³) — escala lineal con nivel."""
    return max(CALIB_VPX * H_ft / CALIB_H_REF, 0.001)

def _pnx_ahorro_cc_per_transit(H_ft: float) -> float:
    """Ahorro por tránsito usando Cámara Corta vs Regular (hm³)."""
    # ΔAc × (EqPM + EqGA) × conversión ft→m (verif. vs xlsb: ≈0.01003 @ 87.5 ft)
    return (AC_PNX_REG - AC_PNX_COR) * (EQ_PM_ft + EQ_GA_ft) * 0.3048 * 1e-6

def area_desde_nivel_gat(nivel_ft: float) -> float:
    return float(np.interp(nivel_ft, _NV_GAT, _AR_GAT))

def area_desde_nivel_alh(nivel_ft: float) -> float:
    return float(np.interp(nivel_ft, _NV_ALH, _AR_ALH))

# ── Logo helper ──────────────────────────────────────────────────────────────
def _logo_b64(path: str):
    if os.path.exists(path):
        ext = path.rsplit(".", 1)[-1].lower()
        mime = "image/png" if ext == "png" else "image/jpeg"
        with open(path, "rb") as f:
            return mime, base64.b64encode(f.read()).decode()
    return None, None

def _img_tag(mime, b64, style=""):
    if b64:
        return f"<img src='data:{mime};base64,{b64}' style='{style}'/>"
    return ""

_logo_mime, _logo       = _logo_b64("LOGO_HIMH.jpg")
_logo_cp_mime, _logo_cp = _logo_b64("CP_RGB_p_Ver.jpg")

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
# Logos: Canal de Panamá + HIMH
_sb_logos = ""
if _logo_cp:
    _sb_logos += _img_tag(_logo_cp_mime, _logo_cp, "max-width:110px;margin:0 6px;")
if _logo:
    _sb_logos += _img_tag(_logo_mime, _logo, "max-width:90px;margin:0 6px;")
if _sb_logos:
    st.sidebar.markdown(
        f"<div style='text-align:center;margin-bottom:8px;display:flex;"
        f"align-items:center;justify-content:center;gap:8px;'>{_sb_logos}</div>",
        unsafe_allow_html=True)
st.sidebar.markdown("## 💧 Demandas de Agua\nCanal de Panamá\n---")

st.sidebar.markdown("**🧮 Fuente de consumo para el balance principal**")
modo_balance_esclusajes = st.sidebar.radio(
    "Usar en el balance:",
    ["Manual sidebar", "Sidebar + ahorro", "Modelo físico base", "Modelo físico + ahorro"],
    index=1,
    key="modo_balance_esclusajes",
    help="Define qué consumo de esclusajes alimenta los balances principales del dashboard."
)

st.sidebar.markdown("### 🚢 Esclusajes")
n_pnx = st.sidebar.slider("PNX/día", 0.0, 40.0, 28.0, 0.5, format="%.1f")
n_npx = st.sidebar.slider("NPX/día", 0.0, 20.0, 11.0, 0.5, format="%.1f")
n_t   = n_pnx + n_npx

st.sidebar.markdown("### 📐 Consumo por esclusaje")
modo = st.sidebar.radio("Entrada", ["hm³/escl", "cfs equiv", "m³/s equiv"], horizontal=True)
if modo == "hm³/escl":
    vp = st.sidebar.number_input("Vol PNX (hm³)", 0.05, 0.5, 0.2000, 0.001, format="%.4f")
    vn = st.sidebar.number_input("Vol NPX (hm³)", 0.1,  0.8, 0.4000, 0.001, format="%.4f")
elif modo == "cfs equiv":
    vp_c = st.sidebar.number_input("PNX (cfs/escl)", 20.0, 300.0, 81.7, 0.1)
    vn_c = st.sidebar.number_input("NPX (cfs/escl)", 50.0, 500.0, 163.5, 0.1)
    vp = vp_c*CFS2HM3; vn = vn_c*CFS2HM3
else:
    vp_m = st.sidebar.number_input("PNX (m³/s equiv)", 0.5, 10.0, 2.31, 0.01)
    vn_m = st.sidebar.number_input("NPX (m³/s equiv)", 1.0, 15.0, 4.63, 0.01)
    vp = vp_m/HM3D2M3S; vn = vn_m/HM3D2M3S
st.sidebar.caption(f"**PNX:** {vp:.3f} hm³ = {vp*HM3D2M3S:.2f} m³/s = {vp/CFS2HM3:.1f} cfs")
st.sidebar.caption(f"**NPX:** {vn:.3f} hm³ = {vn*HM3D2M3S:.2f} m³/s = {vn/CFS2HM3:.1f} cfs")

st.sidebar.markdown("### ⚡ Generación")
st.sidebar.markdown("Factores de conversión (cfs/MW):")
mw_madden = st.sidebar.number_input("Factor Madden (cfs/MW)", 50.0, 1200.0, 100.00, 0.01, format="%.2f")
mw_gatun  = st.sidebar.number_input("Factor Gatún (cfs/MW)", 100.0, 250.0, 200.00, 0.01, format="%.2f")
if mw_madden != 100.00 or mw_gatun != 200.00:
    st.sidebar.warning(f"⚠️ Factores modificados · {AHORA}")
else:
    st.sidebar.caption("Factores iniciales de la app")
gm_mw = st.sidebar.slider("Madden (MW)", 0, 36, 19)
gg_mw = st.sidebar.slider("Gatún (MW)",  0, 30,  0)

st.sidebar.markdown("### 🚰 Potable (cfs)")
pot_alh = st.sidebar.number_input("Alhajuela", 0, 800, 377)
pot_gat = st.sidebar.number_input("Gatún",     0, 600, 264)

st.sidebar.markdown("### 💨 Fugas (cfs)")
fug_alh = st.sidebar.number_input("Alhajuela ", 0, 300, 71)
fug_gat = st.sidebar.number_input("Gatún ",     0, 400, 159)

st.sidebar.markdown("### 🌊 Vertidos Alhajuela (cfs)")
v_fondo  = st.sidebar.number_input("Fondo Madden",       0,  5000,     0)
v_tambor = st.sidebar.number_input("Compuertas Tambor",  0, 30000,     0, 100)
v_libre  = st.sidebar.number_input("Libre (overflow)",   0, 20000,     0, 100)

st.sidebar.markdown("### 🌊 Vertidos Gatún (cfs)")
v_gatun  = st.sidebar.number_input("Vertido Gatún",      0, 20000,     0, 100)

st.sidebar.markdown("### 🔄 ZZ-Flush")
flush_cc = st.sidebar.number_input("Cocolí (hrs)",  0.0, 8.0, 0.0, 0.5)
flush_ac = st.sidebar.number_input("A.Clara (hrs)", 0.0, 8.0, 0.0, 0.5)

# ── Evaporación con opción de área desde nivel ───────────────────────────────
st.sidebar.markdown("### 💾 Ahorro de Agua — Esclusajes")
st.sidebar.caption("Modelo físico · ConsumodeAguaEsclusas.xlsb")
nivel_modelo_ft = st.sidebar.number_input(
    "Nivel lago Gatún (ft)", 55.0, 89.0, 87.0, 0.1, format="%.2f", key="nm_ahorro",
    help="Nivel actual del lago Gatún para el modelo físico de consumo de esclusas")
_H_m = nivel_modelo_ft * 0.3048
_vn_fis = _npx_vol_base(nivel_modelo_ft)
_vp_fis = _pnx_vol_base(nivel_modelo_ft)
st.sidebar.caption(
    f"Vol/tránsito modelo: **NPX** {_vn_fis:.4f} hm³ · **PNX** {_vp_fis:.4f} hm³")

st.sidebar.markdown("**🌊 NPX — Tinas de ahorro**")
pct_tinas_cc = st.sidebar.slider("Tinas Cocolí (%)",     0, 100,  0, 5, key="ptcc")
pct_tinas_ac = st.sidebar.slider("Tinas Agua Clara (%)", 0, 100,  0, 5, key="ptac")

st.sidebar.markdown("**↔️ NPX — Turn Around**")
n_turnaround_npx = st.sidebar.number_input(
    "Turn Around NPX/día", 0.0, 10.0, 0.0, 1.0, key="turn_npx",
    help="Cantidad diaria de eventos Turn Around NPX a considerar en el ahorro."
)
usar_turnaround_npx = st.sidebar.checkbox(
    "Aplicar ahorro Turn Around NPX", value=False, key="usar_turn_npx",
    help="Basado en el workbook: el ahorro del Turn Around NPX equivale a ~5% del volumen sin tinas."
)

st.sidebar.markdown("**🚢 PNX — Eficiencia operativa**")
pct_cam_corta   = st.sidebar.slider("Cámaras Cortas (%)", 0, 100, 0, 1, key="pcc")
pct_crossfill   = st.sidebar.slider("CrossFilling (%)",   0, 100,  0, 5, key="pxf")

# ── Cálculos de ahorro (se usan en la pestaña Ahorro) ─────────────────────────
_V_CC = AC_NPX * max(_H_m - EQ_CC_m, 0) * 1e-6   # hm³ / tránsito lado CC
_V_AC = AC_NPX * max(_H_m - EQ_AC_m, 0) * 1e-6   # hm³ / tránsito lado AC

ahorro_tinas_cc  = n_npx * 0.5 * _V_CC * FRAC_TINAS * pct_tinas_cc / 100
ahorro_tinas_ac  = n_npx * 0.5 * _V_AC * FRAC_TINAS * pct_tinas_ac / 100
_sav_cc_tr       = _pnx_ahorro_cc_per_transit(nivel_modelo_ft)
ahorro_cam_corta = n_pnx * _sav_cc_tr * pct_cam_corta / 100
ahorro_xfill_tr  = (pct_crossfill/100) * AC_PNX_REG * EQ_PM_ft * 0.3048 * 1e-6 * 0.5
ahorro_xfill     = n_pnx * ahorro_xfill_tr

# Turn Around NPX
TURN_NPX_SAVING_PCT = 0.05  # 5% del volumen de Turn Around sin tinas, consistente con el workbook
turnaround_npx_base_tr_modelo = 2.0 * _vn_fis
turnaround_npx_ahorro_tr_modelo = turnaround_npx_base_tr_modelo * TURN_NPX_SAVING_PCT
ahorro_turnaround_npx_modelo = (
    n_turnaround_npx * turnaround_npx_ahorro_tr_modelo if usar_turnaround_npx else 0.0
)

turnaround_npx_base_tr_sidebar = 2.0 * vn
turnaround_npx_ahorro_tr_sidebar = turnaround_npx_base_tr_sidebar * TURN_NPX_SAVING_PCT
ahorro_turnaround_npx_sidebar = (
    n_turnaround_npx * turnaround_npx_ahorro_tr_sidebar if usar_turnaround_npx else 0.0
)

ahorro_total_esc = (
    ahorro_tinas_cc + ahorro_tinas_ac + ahorro_cam_corta + ahorro_xfill
    + ahorro_turnaround_npx_modelo
)

# Vol/tránsito efectivo con estrategias activas
frac_ahorro_npx = max(0.0,
    1.0
    - 0.5 * FRAC_TINAS * pct_tinas_cc/100
    - 0.5 * FRAC_TINAS * pct_tinas_ac/100
)
vn_efectivo = max(_vn_fis * frac_ahorro_npx, 0.001)
vp_efectivo = max(_vp_fis - _sav_cc_tr * pct_cam_corta/100 - ahorro_xfill_tr, 0.001)

# Variante híbrida: consumo manual del sidebar aplicando los mismos porcentajes/ahorros
vn_sidebar_ahorro = max(vn * frac_ahorro_npx, 0.001)
vp_sidebar_ahorro = max(vp - _sav_cc_tr * pct_cam_corta/100 - ahorro_xfill_tr, 0.001)

dem_escl_modelo         = n_npx * _vn_fis + n_pnx * _vp_fis
dem_escl_efectivo       = max(n_npx * vn_efectivo + n_pnx * vp_efectivo - ahorro_turnaround_npx_modelo, 0.0)
dem_escl_sidebar_ahorro = max(n_npx * vn_sidebar_ahorro + n_pnx * vp_sidebar_ahorro - ahorro_turnaround_npx_sidebar, 0.0)

st.sidebar.markdown("### ☀️ Evaporación")
evap_gat_mm = st.sidebar.number_input("Lámina Gatún (mm/día)",      0.0, 15.0, 4.0, 0.1)
evap_alh_mm = st.sidebar.number_input("Lámina Alhajuela (mm/día)",  0.0, 15.0, 4.0, 0.1)

st.sidebar.markdown("**Área espejo de embalse**")
area_modo_gat = st.sidebar.radio("Área Gatún", ["Manual", "Calcular desde nivel (ft)"],
                                  horizontal=True, key="amg")
if area_modo_gat == "Manual":
    area_gat = st.sidebar.number_input("Área espejo Gatún (km²)", 0.0, 500.0, 425.0, 1.0)
    nivel_gat_ft = None
else:
    nivel_gat_ft = st.sidebar.number_input("Nivel Gatún (ft)", 55.0, 89.0, 87.0, 0.1, format="%.2f")
    area_gat = area_desde_nivel_gat(nivel_gat_ft)
    st.sidebar.caption(f"📐 Área calculada: **{area_gat:.1f} km²** @ {nivel_gat_ft:.2f} ft")

area_modo_alh = st.sidebar.radio("Área Alhajuela", ["Manual", "Calcular desde nivel (ft)"],
                                   horizontal=True, key="ama")
if area_modo_alh == "Manual":
    area_alh = st.sidebar.number_input("Área espejo Alhajuela (km²)", 0.0, 100.0, 49.0, 1.0)
    nivel_alh_ft = None
else:
    nivel_alh_ft = st.sidebar.number_input("Nivel Alhajuela (ft)", 180.0, 255.0, 252.0, 0.1, format="%.2f")
    area_alh = area_desde_nivel_alh(nivel_alh_ft)
    st.sidebar.caption(f"📐 Área calculada: **{area_alh:.1f} km²** @ {nivel_alh_ft:.2f} ft")

st.sidebar.markdown("---")
unidad  = st.sidebar.radio("Unidad visual", ["hm³/día", "cfs", "m³/s"], horizontal=True)
u_label = unidad
u_cv    = 1 if unidad == "hm³/día" else (1/CFS2HM3 if unidad == "cfs" else HM3D2M3S)
st.sidebar.markdown("---")
st.sidebar.caption(f"📅 Sesión: {AHORA}")


# ═══ CÁLCULOS ═══
if modo_balance_esclusajes == "Manual sidebar":
    vp_balance = vp
    vn_balance = vn
    ahorro_turnaround_aplicado = 0.0
    balance_escl_label = "Manual sidebar"
elif modo_balance_esclusajes == "Sidebar + ahorro":
    vp_balance = vp_sidebar_ahorro
    vn_balance = vn_sidebar_ahorro
    ahorro_turnaround_aplicado = ahorro_turnaround_npx_sidebar
    balance_escl_label = "Sidebar + ahorro"
elif modo_balance_esclusajes == "Modelo físico base":
    vp_balance = _vp_fis
    vn_balance = _vn_fis
    ahorro_turnaround_aplicado = 0.0
    balance_escl_label = "Modelo físico base"
else:
    vp_balance = vp_efectivo
    vn_balance = vn_efectivo
    ahorro_turnaround_aplicado = ahorro_turnaround_npx_modelo
    balance_escl_label = "Modelo físico + ahorro"

dem_pnx       = n_pnx * vp_balance
dem_npx_bruto = n_npx * vn_balance
dem_npx       = max(dem_npx_bruto - ahorro_turnaround_aplicado, 0.0)
dem_escl      = dem_pnx + dem_npx
gen_alh   = gm_mw*mw_madden*CFS2HM3
gen_gat   = gg_mw*mw_gatun *CFS2HM3
gen_tot   = gen_alh+gen_gat
alh_pot   = pot_alh*CFS2HM3; gat_pot = pot_gat*CFS2HM3
alh_fug   = fug_alh*CFS2HM3; gat_fug = fug_gat*CFS2HM3
alh_vf    = v_fondo*CFS2HM3; alh_vt = v_tambor*CFS2HM3; alh_vl = v_libre*CFS2HM3
alh_vert  = alh_vf+alh_vt+alh_vl
gat_ver   = v_gatun*CFS2HM3
dem_flush = 333.5*(flush_cc+flush_ac)*3600/1e6
evap_gat  = evap_gat_mm*area_gat*1e-3
evap_alh  = evap_alh_mm*area_alh*1e-3
evap_tot  = evap_gat+evap_alh

alh_total = gen_alh+alh_pot+alh_fug+alh_vert+evap_alh
gat_total = gen_gat+gat_pot+gat_fug+gat_ver+dem_escl+dem_flush+evap_gat
dem_total = alh_total+gat_total

alh_usos = {
    "Generación Madden":  (gen_alh,  gm_mw*mw_madden,     COL["generacion"]),
    "Agua Potable":       (alh_pot,  pot_alh,              COL["potable"]),
    "Fugas":              (alh_fug,  fug_alh,              COL["fugas"]),
    "Vertido fondo":      (alh_vf,   v_fondo,              "#7f8c8d"),
    "Compuertas Tambor":  (alh_vt,   v_tambor,             COL["tambor"]),
    "Vertido libre":      (alh_vl,   v_libre,              COL["vertidos"]),
    "Evaporación":        (evap_alh, evap_alh/CFS2HM3,     COL["evap"]),
}
gat_usos = {
    "Esclusajes PNX":  (dem_pnx,  dem_pnx/CFS2HM3,         COL["pnx"]),
    "Esclusajes NPX":  (dem_npx,  dem_npx/CFS2HM3,         COL["npx"]),
    "ZZ-Flush":        (dem_flush, dem_flush/CFS2HM3,       COL["flush"]),
    "Generación Gatún":(gen_gat,  gg_mw*mw_gatun,          COL["gatgen"]),
    "Agua Potable":    (gat_pot,  pot_gat,                  COL["potable"]),
    "Fugas":           (gat_fug,  fug_gat,                  COL["fugas"]),
    "Vertido Gatún":   (gat_ver,  v_gatun,                  COL["vertidos"]),
    "Evaporación":     (evap_gat, evap_gat/CFS2HM3,         COL["evap"]),
}


# ═══ HEADER ═══
hdr_c1, hdr_c2, hdr_c3 = st.columns([1, 5, 1])
with hdr_c1:
    # Logo Canal de Panamá — izquierda
    _cp_tag = _img_tag(_logo_cp_mime, _logo_cp, "width:110px;margin-top:4px;")
    if _cp_tag:
        st.markdown(_cp_tag, unsafe_allow_html=True)
with hdr_c2:
    st.markdown(
        "<h1 style='color:#1a5276;margin-bottom:0;text-align:center;'>"
        "💧 Demandas de Agua por Embalse</h1>"
        "<p style='color:#5d6d7e;margin-top:-4px;text-align:center;'>"
        "Canal de Panamá · <b>HIMH — Sección de Hidrología</b> · Creador: JFRodriguez</p>",
        unsafe_allow_html=True)
with hdr_c3:
    # Logo HIMH — derecha
    _himh_tag = _img_tag(_logo_mime, _logo, "width:80px;margin-top:4px;float:right;")
    if _himh_tag:
        st.markdown(_himh_tag, unsafe_allow_html=True)

k1,k2,k3,k4,k5,k6 = st.columns(6)
k1.metric("Total",       f"{dem_total*u_cv:.2f} {u_label}")
k2.metric("Alhajuela",   f"{alh_total*u_cv:.2f} {u_label}")
k3.metric("Gatún",       f"{gat_total*u_cv:.2f} {u_label}")
k4.metric("Esclusajes",  f"{n_t}/día")
k5.metric("Generación",  f"{gm_mw+gg_mw} MW")
k6.metric("Evaporación", f"{evap_tot:.2f} hm³/d")
st.caption(
    f"Balance de esclusajes: **{balance_escl_label}** · "
    f"PNX {vp_balance:.4f} hm³/escl · NPX {vn_balance:.4f} hm³/escl · "
    f"Ahorro Turn Around NPX aplicado: {ahorro_turnaround_aplicado:.4f} hm³/d"
)
st.markdown("---")


# ═══ TABS ═══
tabs = st.tabs(["📊 Balance", "🏔️ Alhajuela", "🌊 Gatún", "🔀 Comparar",
                "🚢 Esclusajes", "⚡ Generación", "🎯 Escenarios",
                "💾 Ahorro de Agua",
                "📐 Área Espejo", "🔄 Conversor", "📤 Exportar", "📂 Datos Operativos"])


# ═══ TAB 0 — BALANCE ═══
with tabs[0]:
    b1, b2 = st.columns(2)
    with b1:
        st.subheader("Por embalse")
        fig_b1 = go.Figure(go.Bar(x=["Alhajuela","Gatún","Total"],
            y=[alh_total*u_cv, gat_total*u_cv, dem_total*u_cv],
            marker_color=[COL["alhajuela"],COL["gatun"],COL["total"]],
            text=[f"{alh_total*u_cv:.2f}",f"{gat_total*u_cv:.2f}",f"{dem_total*u_cv:.2f}"],
            textposition="auto"))
        fig_b1.update_layout(yaxis_title=u_label, template="plotly_white", height=400,
            margin=dict(l=50,r=20,t=20,b=50))
        st.plotly_chart(fig_b1, use_container_width=True)
    with b2:
        st.subheader("Por uso")
        todos = {"Esclusajes":dem_escl,"Potable":alh_pot+gat_pot,"Generación":gen_tot,
                 "Fugas":alh_fug+gat_fug,"Vertidos":alh_vert+gat_ver,
                 "ZZ-Flush":dem_flush,"Evaporación":evap_tot}
        tf     = {k:v for k,v in todos.items() if v > 0.001}
        cols_t = [COL["esclusas"],COL["potable"],COL["generacion"],COL["fugas"],
                  COL["vertidos"],COL["flush"],COL["evap"]]
        fig_b2 = go.Figure(go.Pie(labels=list(tf.keys()),
            values=[v*u_cv for v in tf.values()],
            marker_colors=cols_t[:len(tf)], hole=0.45,
            textinfo="percent+label", textposition="outside"))
        fig_b2.update_layout(height=400, template="plotly_white",
            margin=dict(l=10,r=10,t=20,b=10), showlegend=False)
        st.plotly_chart(fig_b2, use_container_width=True)

    gauge_cols = st.columns(6)
    gauge_data = [
        ("Esclusajes", dem_escl,            COL["esclusas"]),
        ("Potable",    alh_pot+gat_pot,      COL["potable"]),
        ("Generación", gen_tot,              COL["generacion"]),
        ("Fugas",      alh_fug+gat_fug,      COL["fugas"]),
        ("Vertidos",   alh_vert+gat_ver+dem_flush, COL["vertidos"]),
        ("Evaporación",evap_tot,             COL["evap"]),
    ]
    for col_g, (nm, val, cl) in zip(gauge_cols, gauge_data):
        with col_g:
            pct = val/max(dem_total,.001)*100
            fig_gauge = go.Figure(go.Indicator(mode="gauge+number", value=pct,
                title={"text": nm, "font":{"size":11}},
                number={"suffix":"%","font":{"size":18}},
                gauge={"axis":{"range":[0,100]},"bar":{"color":cl}}))
            fig_gauge.update_layout(height=160, margin=dict(l=10,r=10,t=35,b=5))
            st.plotly_chart(fig_gauge, use_container_width=True)

    st.subheader("Tabla completa (hm³/día · cfs · m³/s)")
    rows = []
    all_usos = {**{f"[ALH] {k}":v for k,v in alh_usos.items()},
                **{f"[GAT] {k}":v for k,v in gat_usos.items()}}
    for nm,(h,cf,_) in all_usos.items():
        if h > 0.0001:
            rows.append({"Uso":nm,"hm³/día":round(h,4),"cfs":round(cf,1),
                         "m³/s":round(cf*CFS2M3S,2),"%":round(h/max(dem_total,.001)*100,1)})
    rows.append({"Uso":"TOTAL","hm³/día":round(dem_total,4),"cfs":round(dem_total/CFS2HM3,1),
                 "m³/s":round(dem_total*HM3D2M3S,2),"%":100.0})
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# ═══ TAB 1 — ALHAJUELA ═══
with tabs[1]:
    st.subheader("🏔️ Embalse Alhajuela"); st.metric("Total", f3u(alh_total))
    c1,c2 = st.columns(2)
    with c1:
        af = {k:v[0] for k,v in alh_usos.items() if v[0]>0.001}
        if af:
            fig_a1 = go.Figure(go.Pie(labels=list(af.keys()),
                values=[v*u_cv for v in af.values()],
                marker_colors=[alh_usos[k][2] for k in af], hole=0.45, textinfo="percent+label"))
            fig_a1.update_layout(height=400, template="plotly_white",
                margin=dict(l=10,r=10,t=20,b=10), showlegend=False)
            st.plotly_chart(fig_a1, use_container_width=True)
    with c2:
        fig_a2 = go.Figure()
        for nm,(h,cf,cl) in alh_usos.items():
            if h>0.001:
                fig_a2.add_trace(go.Bar(y=[nm],x=[h*u_cv],orientation="h",marker_color=cl,
                    text=[f"{h*u_cv:.3f}"],textposition="auto",showlegend=False))
        fig_a2.update_layout(xaxis_title=u_label,template="plotly_white",height=400,
            margin=dict(l=10,r=20,t=20,b=50))
        st.plotly_chart(fig_a2, use_container_width=True)
    st.dataframe(tbl(alh_usos,alh_total,"Alhajuela",dem_total), use_container_width=True, hide_index=True)


# ═══ TAB 2 — GATÚN ═══
with tabs[2]:
    st.subheader("🌊 Embalse Gatún"); st.metric("Total", f3u(gat_total))
    c1,c2 = st.columns(2)
    with c1:
        gf = {k:v[0] for k,v in gat_usos.items() if v[0]>0.001}
        fig_g1 = go.Figure(go.Pie(labels=list(gf.keys()),
            values=[v*u_cv for v in gf.values()],
            marker_colors=[gat_usos[k][2] for k in gf], hole=0.45, textinfo="percent+label"))
        fig_g1.update_layout(height=400,template="plotly_white",
            margin=dict(l=10,r=10,t=20,b=10),showlegend=False)
        st.plotly_chart(fig_g1, use_container_width=True)
    with c2:
        fig_g2 = go.Figure()
        for nm,(h,cf,cl) in gat_usos.items():
            if h>0.001:
                fig_g2.add_trace(go.Bar(y=[nm],x=[h*u_cv],orientation="h",marker_color=cl,
                    text=[f"{h*u_cv:.3f}"],textposition="auto",showlegend=False))
        fig_g2.update_layout(xaxis_title=u_label,template="plotly_white",height=400,
            margin=dict(l=10,r=20,t=20,b=50))
        st.plotly_chart(fig_g2, use_container_width=True)
    st.dataframe(tbl(gat_usos,gat_total,"Gatún",dem_total), use_container_width=True, hide_index=True)


# ═══ TAB 3 — COMPARAR ═══
with tabs[3]:
    st.subheader("Alhajuela vs Gatún")
    uc  = ["Generación","Potable","Fugas","Vertidos","Esclusajes","Flush","Evaporación"]
    va2 = [gen_alh,alh_pot,alh_fug,alh_vert,0,0,evap_alh]
    vg2 = [gen_gat,gat_pot,gat_fug,gat_ver,dem_escl,dem_flush,evap_gat]

    fig_comp = go.Figure()
    fig_comp.add_trace(go.Bar(x=uc,y=[v*u_cv for v in va2],name="Alhajuela",marker_color=COL["alhajuela"]))
    fig_comp.add_trace(go.Bar(x=uc,y=[v*u_cv for v in vg2],name="Gatún",marker_color=COL["gatun"]))
    fig_comp.update_layout(barmode="group",yaxis_title=u_label,template="plotly_white",
        height=450,margin=dict(l=50,r=20,t=20,b=50))
    st.plotly_chart(fig_comp, use_container_width=True)

    cc1,cc2 = st.columns(2)
    with cc1:
        fig_comp2 = go.Figure(go.Pie(labels=["Alhajuela","Gatún"],values=[alh_total,gat_total],
            marker_colors=[COL["alhajuela"],COL["gatun"]],hole=0.5,
            textinfo="percent+label+value",texttemplate="%{label}<br>%{percent}<br>%{value:.2f} hm³/d"))
        fig_comp2.update_layout(height=350,template="plotly_white",margin=dict(l=10,r=10,t=20,b=10))
        st.plotly_chart(fig_comp2, use_container_width=True)
    with cc2:
        comp_rows = []
        for uso_n,va_v,vg_v in zip(uc,va2,vg2):
            comp_rows.append({"Uso":uso_n,
                "Alh (hm³/d)":round(va_v,3),"Alh (cfs)":round(va_v/CFS2HM3,1),
                "Gat (hm³/d)":round(vg_v,3),"Gat (cfs)":round(vg_v/CFS2HM3,1),
                "Total (m³/s)":round((va_v+vg_v)*HM3D2M3S,2)})
        comp_rows.append({"Uso":"TOTAL",
            "Alh (hm³/d)":round(alh_total,3),"Alh (cfs)":round(alh_total/CFS2HM3,1),
            "Gat (hm³/d)":round(gat_total,3),"Gat (cfs)":round(gat_total/CFS2HM3,1),
            "Total (m³/s)":round(dem_total*HM3D2M3S,2)})
        st.dataframe(pd.DataFrame(comp_rows), use_container_width=True, hide_index=True)


# ═══ TAB 4 — ESCLUSAJES ═══
with tabs[4]:
    st.subheader("🚢 Dashboard de Esclusajes")
    ek1,ek2,ek3,ek4 = st.columns(4)
    ek1.metric("Total esclusajes",f"{n_t}/día")
    ek2.metric("Consumo total",   f3u(dem_escl))
    ek3.metric("% de demanda",    f"{dem_escl/max(dem_total,.001)*100:.1f}%")
    ek4.metric("Vol prom/escl",   f"{dem_escl/max(n_t,1):.3f} hm³")

    ec1,ec2 = st.columns(2)
    with ec1:
        fig_e1 = go.Figure(go.Bar(x=["Panamax","Neopanamax","Total"],
            y=[dem_pnx*u_cv,dem_npx*u_cv,dem_escl*u_cv],
            marker_color=[COL["pnx"],COL["npx"],COL["esclusas"]],
            text=[f"{dem_pnx*u_cv:.2f}",f"{dem_npx*u_cv:.2f}",f"{dem_escl*u_cv:.2f}"],
            textposition="auto"))
        fig_e1.update_layout(yaxis_title=u_label,template="plotly_white",height=380,
            margin=dict(l=50,r=20,t=20,b=50))
        st.plotly_chart(fig_e1, use_container_width=True)
    with ec2:
        fig_e2 = go.Figure(go.Pie(labels=["Panamax","Neopanamax"],values=[dem_pnx,dem_npx],
            marker_colors=[COL["pnx"],COL["npx"]],hole=0.45,
            textinfo="percent+label+value",
            texttemplate="%{label}<br>%{percent}<br>%{value:.2f} hm³/d"))
        fig_e2.update_layout(height=380,template="plotly_white",
            margin=dict(l=10,r=10,t=20,b=10),showlegend=False)
        st.plotly_chart(fig_e2, use_container_width=True)

    st.subheader("Detalle (3 unidades)")
    ed = []
    for tipo,n,v,th in [("Panamax",n_pnx,vp,dem_pnx),("Neopanamax",n_npx,vn,dem_npx)]:
        ed.append({"Tipo":tipo,"N/día":n,
            "hm³/escl":round(v,3),"cfs/escl":round(v/CFS2HM3,1),"m³/s/escl":round(v*HM3D2M3S,2),
            "hm³/día":round(th,2),"cfs":round(th/CFS2HM3,0),"m³/s":round(th*HM3D2M3S,1)})
    ed.append({"Tipo":"TOTAL","N/día":n_t,
        "hm³/escl":round(dem_escl/max(n_t,1),3),"cfs/escl":round(dem_escl/max(n_t,1)/CFS2HM3,1),
        "m³/s/escl":round(dem_escl/max(n_t,1)*HM3D2M3S,2),
        "hm³/día":round(dem_escl,2),"cfs":round(dem_escl/CFS2HM3,0),"m³/s":round(dem_escl*HM3D2M3S,1)})
    st.dataframe(pd.DataFrame(ed), use_container_width=True, hide_index=True)

    st.subheader("Proyección acumulada")
    pr1,pr2,pr3 = st.columns(3)
    pr1.metric("Diario",     f"{dem_escl:.2f} hm³ · {dem_escl/CFS2HM3:.0f} cfs")
    pr2.metric("Mensual (30d)", f"{dem_escl*30:.1f} hm³")
    pr3.metric("Anual (365d)",  f"{dem_escl*365:.0f} hm³")


# ═══ TAB 5 — GENERACIÓN ═══
with tabs[5]:
    st.subheader("⚡ Dashboard de Hidrogeneración")
    hk1,hk2,hk3,hk4 = st.columns(4)
    hk1.metric("Madden",    f"{gm_mw} MW")
    hk2.metric("Gatún",     f"{gg_mw} MW")
    hk3.metric("Total",     f"{gm_mw+gg_mw} MW")
    hk4.metric("Agua usada",f3u(gen_tot))

    hc1,hc2 = st.columns(2)
    with hc1:
        fig_h1 = go.Figure(go.Bar(x=["Madden","Gatún","Total"],
            y=[gen_alh*u_cv,gen_gat*u_cv,gen_tot*u_cv],
            marker_color=[COL["generacion"],COL["gatgen"],COL["total"]],
            text=[f"{gen_alh*u_cv:.2f}",f"{gen_gat*u_cv:.2f}",f"{gen_tot*u_cv:.2f}"],
            textposition="auto"))
        fig_h1.update_layout(yaxis_title=u_label,template="plotly_white",height=380,
            margin=dict(l=50,r=20,t=20,b=50))
        st.plotly_chart(fig_h1, use_container_width=True)
    with hc2:
        st.markdown(f"""
**Factores de conversión actuales:**

| Central | cfs/MW | m³/s por MW | Estado |
|---------|--------|-------------|--------|
| Madden | **{mw_madden:.2f}** | {mw_madden*CFS2M3S:.2f} | {"⚠️ Modificado" if mw_madden!=100.00 else "✅ Inicial"} |
| Gatún  | **{mw_gatun:.2f}**  | {mw_gatun*CFS2M3S:.2f}  | {"⚠️ Modificado" if mw_gatun!=200.00 else "✅ Inicial"} |

**Consumo actual:**

| Central | MW | cfs | m³/s | hm³/día |
|---------|-----|------|------|---------|
| Madden | {gm_mw} | {gm_mw*mw_madden:.1f} | {gm_mw*mw_madden*CFS2M3S:.1f} | {gen_alh:.3f} |
| Gatún  | {gg_mw} | {gg_mw*mw_gatun:.1f}  | {gg_mw*mw_gatun*CFS2M3S:.1f}  | {gen_gat:.3f} |
| **Total** | **{gm_mw+gg_mw}** | **{gm_mw*mw_madden+gg_mw*mw_gatun:.1f}** | **{(gm_mw*mw_madden+gg_mw*mw_gatun)*CFS2M3S:.1f}** | **{gen_tot:.3f}** |
        """)
    st.metric("% del sistema",f"{gen_tot/max(dem_total,.001)*100:.1f}%")
    if mw_madden!=100.00 or mw_gatun!=200.00:
        st.warning(f"⚠️ Factores de conversión modificados el {AHORA}. "
                   f"Base inicial de la app: Madden=100.0, Gatún=200.0 cfs/MW")


# ═══ TAB 6 — ESCENARIOS (con fecha + nombre personalizables) ═══
with tabs[6]:
    st.subheader("🎯 Comparación de Escenarios")
    st.info("Define nombre y fecha para cada escenario y ajusta sus parámetros.", icon="ℹ️")

    def calc_esc(p):
        a = p["gm"]*p["mw_m"]*CFS2HM3 + p["pa"]*CFS2HM3 + p["fa"]*CFS2HM3 + p["va"]*CFS2HM3 + p["ea"]
        e = p["np"]*p["vp"] + p["nn"]*p["vn"]
        g = p["gg"]*p["mw_g"]*CFS2HM3 + p["pg"]*CFS2HM3 + p["fg_val"]*CFS2HM3 + p["vg"]*CFS2HM3 + e + p["eg"]
        return {"A":a,"G":g,"T":a+g,"E":e,"N":p["np"]+p["nn"]}

    # Valores por defecto de los 3 escenarios
    presets_default = [
        {"emoji":"🟡","def_name":"Probable",   "def_date":datetime.date.today(),
         "np":n_pnx,"nn":n_npx,"vp":vp,"vn":vn,
         "gm":gm_mw,"gg":gg_mw,"mw_m":mw_madden,"mw_g":mw_gatun,
         "pa":pot_alh,"pg":pot_gat,"fa":fug_alh,"fg_val":fug_gat,
         "va":v_fondo+v_tambor+v_libre,"vg":v_gatun,"ea":evap_alh,"eg":evap_gat},
        {"emoji":"🟢","def_name":"Optimista",  "def_date":datetime.date.today()+datetime.timedelta(days=7),
         "np":30,"nn":14,"vp":0.190,"vn":0.397,
         "gm":20,"gg":5,"mw_m":mw_madden,"mw_g":mw_gatun,
         "pa":350,"pg":250,"fa":50,"fg_val":120,
         "va":0,"vg":0,"ea":evap_alh,"eg":evap_gat},
        {"emoji":"🔴","def_name":"Pesimista",  "def_date":datetime.date.today()+datetime.timedelta(days=14),
         "np":22,"nn":7,"vp":0.210,"vn":0.450,
         "gm":10,"gg":0,"mw_m":mw_madden,"mw_g":mw_gatun,
         "pa":420,"pg":300,"fa":90,"fg_val":200,
         "va":0,"vg":0,"ea":evap_alh,"eg":evap_gat},
    ]

    esc_results  = {}
    esc_labels   = {}      # key → "nombre (fecha)"
    esc_cols_ui  = st.columns(3)

    for idx, (pre, col_e) in enumerate(zip(presets_default, esc_cols_ui)):
        with col_e:
            # ── Nombre y fecha ──
            esc_name = st.text_input(f"{pre['emoji']} Nombre escenario {idx+1}",
                                     value=pre["def_name"], key=f"esc_nombre_{idx}")
            esc_date = st.date_input(f"📅 Fecha escenario {idx+1}",
                                     value=pre["def_date"], key=f"esc_fecha_{idx}")
            label    = f"{esc_name}\n({esc_date.strftime('%d/%m/%Y')})"
            st.markdown(f"#### {pre['emoji']} {esc_name} — {esc_date.strftime('%d/%m/%Y')}")
            st.markdown("---")

            p = dict(pre)
            p["np"]     = st.number_input("PNX/día",      0.0, 40.0, float(pre["np"]), 0.5, key=f"e1_{idx}", format="%.1f")
            p["nn"]     = st.number_input("NPX/día",      0.0, 20.0, float(pre["nn"]), 0.5, key=f"e2_{idx}", format="%.1f")
            p["vp"]     = st.number_input("Vol PNX (hm³)",0.1,0.4, pre["vp"], 0.001, key=f"e3_{idx}", format="%.3f")
            p["vn"]     = st.number_input("Vol NPX (hm³)",0.1,0.6, pre["vn"], 0.001, key=f"e4_{idx}", format="%.3f")
            p["gm"]     = st.number_input("Gen Mad (MW)", 0, 36,   pre["gm"],     key=f"e5_{idx}")
            p["gg"]     = st.number_input("Gen Gat (MW)", 0, 30,   pre["gg"],     key=f"e6_{idx}")
            p["pa"]     = st.number_input("Potable Alh (cfs)", 0, 800, pre["pa"],key=f"e7_{idx}")
            p["pg"]     = st.number_input("Potable Gat (cfs)", 0, 600, pre["pg"],key=f"e8_{idx}")

            esc_results[label] = calc_esc(p)
            esc_labels[idx]    = label

    st.markdown("---")
    xlabels = list(esc_results.keys())

    fig_esc = go.Figure()
    fig_esc.add_trace(go.Bar(x=xlabels,
        y=[r["E"]*u_cv for r in esc_results.values()],
        name="Esclusajes", marker_color=COL["esclusas"]))
    fig_esc.add_trace(go.Bar(x=xlabels,
        y=[(r["T"]-r["E"])*u_cv for r in esc_results.values()],
        name="Otros usos", marker_color=COL["alhajuela"]))
    fig_esc.update_layout(barmode="stack",yaxis_title=u_label,template="plotly_white",
        height=420,margin=dict(l=50,r=20,t=20,b=80),xaxis_tickangle=-10)
    st.plotly_chart(fig_esc, use_container_width=True)

    esc_tbl = []
    for lbl, r in esc_results.items():
        esc_tbl.append({"Escenario":lbl,"N/día":r["N"],
            "hm³/día":round(r["T"],2),"cfs":round(r["T"]/CFS2HM3,0),
            "m³/s":round(r["T"]*HM3D2M3S,1)})
    st.dataframe(pd.DataFrame(esc_tbl), use_container_width=True, hide_index=True)

    prob_t = list(esc_results.values())[0]["T"]
    for lbl, r in list(esc_results.items())[1:]:
        d = r["T"]-prob_t
        st.markdown(f"**{lbl}:** {d:+.2f} hm³/d ({d/max(prob_t,.001)*100:+.1f}% vs Escenario 1)")

    # Guardar en session_state para exportación
    st.session_state["esc_results"] = esc_results
    st.session_state["esc_tbl"]     = esc_tbl


# ═══ TAB 7 — AHORRO DE AGUA ═══
with tabs[7]:
    st.subheader("💾 Dashboard de Ahorro de Agua en Esclusajes")
    st.markdown(
        "Modelo físico basado en **ConsumodeAguaEsclusas.xlsb** · "
        f"Nivel de referencia: **{nivel_modelo_ft:.2f} ft** ({nivel_modelo_ft*0.3048:.3f} m)")

    # ── KPIs ──────────────────────────────────────────────────────────────────
    ah1,ah2,ah3,ah4,ah5,ah6 = st.columns(6)
    ah1.metric("Ahorro total", f"{ahorro_total_esc:.3f} hm³/d",
               delta=f"{ahorro_total_esc*365:.0f} hm³/año")
    ah2.metric("Tinas NPX (CC+AC)",
               f"{(ahorro_tinas_cc+ahorro_tinas_ac):.3f} hm³/d",
               delta=f"{(ahorro_tinas_cc+ahorro_tinas_ac)/CFS2HM3:.0f} cfs")
    ah3.metric("Turn Around NPX",
               f"{ahorro_turnaround_npx_modelo:.3f} hm³/d",
               delta=f"{ahorro_turnaround_npx_modelo/CFS2HM3:.0f} cfs")
    ah4.metric("Cámaras Cortas PNX",
               f"{ahorro_cam_corta:.3f} hm³/d",
               delta=f"{ahorro_cam_corta/CFS2HM3:.0f} cfs")
    ah5.metric("CrossFilling PNX",
               f"{ahorro_xfill:.3f} hm³/d",
               delta=f"{ahorro_xfill/CFS2HM3:.0f} cfs")
    _equiv_transitos = ahorro_total_esc / max(_vn_fis, 0.001)
    ah6.metric("Tránsitos equiv. ahorrados", f"{_equiv_transitos:.1f}/d")

    st.markdown("---")

    # ── Gráfico comparativo: Base vs Efectivo ──────────────────────────────────
    col_ah1, col_ah2 = st.columns(2)

    with col_ah1:
        st.markdown("#### Comparación vol/tránsito vs nivel actual")
        bar_x   = ["Vol/tránsito\nNPX base", "Vol/tránsito\nNPX efectivo",
                   "Vol/tránsito\nPNX base",  "Vol/tránsito\nPNX efectivo"]
        bar_y   = [_vn_fis, vn_efectivo, _vp_fis, vp_efectivo]
        bar_clr = [COL["npx"], COL["flush"], COL["pnx"], COL["esclusas"]]
        fig_cmp = go.Figure(go.Bar(
            x=bar_x, y=bar_y, marker_color=bar_clr,
            text=[f"{v:.4f}" for v in bar_y], textposition="auto"))
        fig_cmp.update_layout(
            yaxis_title="hm³/tránsito", template="plotly_white",
            height=380, margin=dict(l=50,r=20,t=20,b=60))
        st.plotly_chart(fig_cmp, use_container_width=True)

    with col_ah2:
        st.markdown("#### Ahorro diario por mecanismo (hm³/d)")
        mec_lbl = ["Tinas Cocolí\n(NPX)", "Tinas A.Clara\n(NPX)",
                   "Turn Around\n(NPX)", "Cámaras Cortas\n(PNX)", "CrossFilling\n(PNX)"]
        mec_val = [ahorro_tinas_cc, ahorro_tinas_ac, ahorro_turnaround_npx_modelo, ahorro_cam_corta, ahorro_xfill]
        mec_clr = [COL["npx"], COL["flush"], COL["gatun"], COL["pnx"], COL["esclusas"]]
        fig_mec = go.Figure(go.Bar(
            x=mec_lbl, y=mec_val, marker_color=mec_clr,
            text=[f"{v:.4f}" for v in mec_val], textposition="auto"))
        fig_mec.add_hline(y=ahorro_total_esc, line_dash="dash",
                          line_color=COL["total"],
                          annotation_text=f"Total: {ahorro_total_esc:.3f} hm³/d")
        fig_mec.update_layout(
            yaxis_title="hm³/día", template="plotly_white",
            height=380, margin=dict(l=50,r=20,t=30,b=60))
        st.plotly_chart(fig_mec, use_container_width=True)

    st.markdown("---")

    # ── Sensibilidad al nivel del lago ─────────────────────────────────────────
    st.markdown("#### Sensibilidad del ahorro al nivel del lago Gatún")
    _nv_sens = np.linspace(75, 89, 80)
    _aho_cc  = [n_npx * 0.5 * (AC_NPX * max(n*0.3048 - EQ_CC_m, 0) * 1e-6)
                * FRAC_TINAS * pct_tinas_cc/100 for n in _nv_sens]
    _aho_ac  = [n_npx * 0.5 * (AC_NPX * max(n*0.3048 - EQ_AC_m, 0) * 1e-6)
                * FRAC_TINAS * pct_tinas_ac/100 for n in _nv_sens]
    _aho_c   = [n_pnx * _pnx_ahorro_cc_per_transit(n) * pct_cam_corta/100  for n in _nv_sens]
    _aho_xf  = [n_pnx * (pct_crossfill/100) * AC_PNX_REG * EQ_PM_ft * 0.3048 * 1e-6 * 0.5
                for n in _nv_sens]
    _aho_ta  = [n_turnaround_npx * (2.0 * _npx_vol_base(n)) * TURN_NPX_SAVING_PCT if usar_turnaround_npx else 0.0
                for n in _nv_sens]
    _aho_tot = [a+b+c+d+e for a,b,c,d,e in zip(_aho_cc, _aho_ac, _aho_c, _aho_xf, _aho_ta)]

    fig_sen = go.Figure()
    fig_sen.add_trace(go.Scatter(x=_nv_sens, y=_aho_cc, name="Tinas Cocolí",
        stackgroup="one", line=dict(color=COL["npx"]),   fillcolor="rgba(22,160,133,0.55)"))
    fig_sen.add_trace(go.Scatter(x=_nv_sens, y=_aho_ac, name="Tinas A.Clara",
        stackgroup="one", line=dict(color=COL["flush"]),  fillcolor="rgba(26,188,156,0.55)"))
    fig_sen.add_trace(go.Scatter(x=_nv_sens, y=_aho_ta, name="Turn Around NPX",
        stackgroup="one", line=dict(color=COL["gatun"]),  fillcolor="rgba(26,82,118,0.45)"))
    fig_sen.add_trace(go.Scatter(x=_nv_sens, y=_aho_c,  name="Cámaras Cortas",
        stackgroup="one", line=dict(color=COL["pnx"]),    fillcolor="rgba(44,62,80,0.55)"))
    fig_sen.add_trace(go.Scatter(x=_nv_sens, y=_aho_xf, name="CrossFilling",
        stackgroup="one", line=dict(color=COL["esclusas"]),fillcolor="rgba(41,128,185,0.55)"))
    fig_sen.add_vline(x=nivel_modelo_ft, line_dash="dot", line_color="red",
        annotation_text=f"Nivel actual\n{nivel_modelo_ft:.1f} ft", annotation_position="top right")
    fig_sen.update_layout(
        xaxis_title="Nivel lago Gatún (ft)", yaxis_title="Ahorro (hm³/d)",
        template="plotly_white", height=380, hovermode="x unified",
        margin=dict(l=50,r=20,t=20,b=50))
    st.plotly_chart(fig_sen, use_container_width=True)

    # ── Consumo diario total: Dashboard vs Modelo físico ──────────────────────
    st.markdown("---")
    st.markdown("#### Comparación consumo diario de esclusajes")
    cmp_cols = st.columns(4)
    cmp_cols[0].metric("Modelo físico base\n(nivel actual)",
                       f"{dem_escl_modelo:.3f} hm³/d",
                       delta=f"{dem_escl_modelo/CFS2HM3:.0f} cfs")
    cmp_cols[1].metric("Modelo físico + ahorro",
                       f"{dem_escl_efectivo:.3f} hm³/d",
                       delta=f"−{(dem_escl_modelo-dem_escl_efectivo):.3f} hm³/d vs base")
    cmp_cols[2].metric(f"Balance seleccionado\n({balance_escl_label})",
                       f"{dem_escl:.3f} hm³/d",
                       delta=f"{dem_escl/CFS2HM3:.0f} cfs")
    _dif = dem_escl - dem_escl_efectivo
    cmp_cols[3].metric("Potencial ahorro adicional",
                       f"{max(_dif,0):.3f} hm³/d",
                       delta=f"{max(_dif,0)*365:.0f} hm³/año")

    # ── Tabla de parámetros del modelo ────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### Parámetros del modelo físico (ConsumodeAguaEsclusas.xlsb)")
    tbl_fis = pd.DataFrame([
        {"Parámetro":"Nivel lago Gatún","Valor":f"{nivel_modelo_ft:.2f} ft = {nivel_modelo_ft*0.3048:.3f} m","Fuente":"Input"},
        {"Parámetro":"Área cámara NPX","Valor":f"{AC_NPX:,.0f} m²","Fuente":"Hoja NeoPanamax"},
        {"Parámetro":"Nivel equiv. Cocolí (NPX)","Valor":f"{EQ_CC_m:.3f} m","Fuente":"Hoja NeoPanamax"},
        {"Parámetro":"Nivel equiv. Agua Clara (NPX)","Valor":f"{EQ_AC_m:.3f} m","Fuente":"Hoja NeoPanamax"},
        {"Parámetro":"Ahorro con tinas (frac/tránsito)","Valor":f"{FRAC_TINAS*100:.0f}%","Fuente":"Hoja NeoPanamax"},
        {"Parámetro":"Vol/tránsito NPX base","Valor":f"{_vn_fis:.4f} hm³","Fuente":"Cálculo físico"},
        {"Parámetro":"Vol/tránsito NPX con tinas","Valor":f"{vn_efectivo:.4f} hm³","Fuente":"Cálculo físico"},
        {"Parámetro":"Turn Around NPX/día","Valor":f"{n_turnaround_npx:.1f}","Fuente":"Sidebar"},
        {"Parámetro":"Ahorro Turn Around NPX por evento","Valor":f"{turnaround_npx_ahorro_tr_modelo:.5f} hm³","Fuente":"Workbook / cálculo"},
        {"Parámetro":"Ahorro Turn Around NPX total","Valor":f"{ahorro_turnaround_npx_modelo:.4f} hm³/d","Fuente":"Cálculo físico"},
        {"Parámetro":"Área cámara PNX Regular","Valor":f"{AC_PNX_REG:,.1f} m²","Fuente":"Hoja Panamax"},
        {"Parámetro":"Área cámara PNX Corta","Valor":f"{AC_PNX_COR:,.1f} m²","Fuente":"Hoja Panamax"},
        {"Parámetro":"Nivel equiv. PedroMiguel","Valor":f"{EQ_PM_ft:.3f} ft","Fuente":"Hoja Panamax"},
        {"Parámetro":"Nivel equiv. Gatún (PNX)","Valor":f"{EQ_GA_ft:.3f} ft","Fuente":"Hoja Panamax"},
        {"Parámetro":"Vol/tránsito PNX base","Valor":f"{_vp_fis:.4f} hm³","Fuente":"Cálculo físico"},
        {"Parámetro":"Ahorro/tránsito Cámara Corta","Valor":f"{_sav_cc_tr:.5f} hm³","Fuente":"Cálculo físico"},
        {"Parámetro":"% Tinas Cocolí activas","Valor":f"{pct_tinas_cc}%","Fuente":"Sidebar"},
        {"Parámetro":"% Tinas Agua Clara activas","Valor":f"{pct_tinas_ac}%","Fuente":"Sidebar"},
        {"Parámetro":"% Cámaras Cortas activas","Valor":f"{pct_cam_corta}%","Fuente":"Sidebar"},
        {"Parámetro":"% CrossFilling activo","Valor":f"{pct_crossfill}%","Fuente":"Sidebar"},
    ])
    st.dataframe(tbl_fis, use_container_width=True, hide_index=True)


# ═══ TAB 8 — ÁREA ESPEJO ═══
with tabs[8]:
    st.subheader("📐 Área Espejo de Embalse desde Nivel")
    st.markdown(
        "Calcula el área espejo (superficie libre del agua) a partir del nivel del embalse "
        "usando la curva hipsométrica de cada lago.")

    ae1, ae2 = st.columns(2)

    with ae1:
        st.markdown("#### 🌊 Lago Gatún")
        nv_g = st.slider("Nivel Gatún (ft)", 55.0, 89.0, 87.0, 0.1, key="ae_gat")
        ar_g = area_desde_nivel_gat(nv_g)
        st.metric("Área espejo Gatún", f"{ar_g:.1f} km²",
                  delta=f"{ar_g-425:.1f} km² vs NFS (87 ft)")
        evap_g_calc = evap_gat_mm * ar_g * 1e-3
        st.info(f"Evaporación estimada con lámina actual ({evap_gat_mm} mm/d): **{evap_g_calc:.3f} hm³/d**")

        # Curva Gatún
        nv_rng  = np.linspace(55, 89, 200)
        ar_rng  = [area_desde_nivel_gat(n) for n in nv_rng]
        fig_cg  = go.Figure()
        fig_cg.add_trace(go.Scatter(x=nv_rng, y=ar_rng, mode="lines",
            line=dict(color=COL["gatun"], width=2), name="Curva Gatún"))
        fig_cg.add_trace(go.Scatter(x=[nv_g], y=[ar_g], mode="markers",
            marker=dict(color="red",size=12,symbol="star"), name=f"{nv_g:.1f} ft"))
        fig_cg.update_layout(xaxis_title="Nivel (ft)", yaxis_title="Área (km²)",
            template="plotly_white", height=350, margin=dict(l=50,r=20,t=20,b=50))
        st.plotly_chart(fig_cg, use_container_width=True)

    with ae2:
        st.markdown("#### 🏔️ Lago Alhajuela")
        nv_a = st.slider("Nivel Alhajuela (ft)", 180.0, 255.0, 252.0, 0.1, key="ae_alh")
        ar_a = area_desde_nivel_alh(nv_a)
        st.metric("Área espejo Alhajuela", f"{ar_a:.1f} km²",
                  delta=f"{ar_a-49:.1f} km² vs NFS (252 ft)")
        evap_a_calc = evap_alh_mm * ar_a * 1e-3
        st.info(f"Evaporación estimada con lámina actual ({evap_alh_mm} mm/d): **{evap_a_calc:.3f} hm³/d**")

        nv_rng2 = np.linspace(180, 255, 200)
        ar_rng2 = [area_desde_nivel_alh(n) for n in nv_rng2]
        fig_ca  = go.Figure()
        fig_ca.add_trace(go.Scatter(x=nv_rng2, y=ar_rng2, mode="lines",
            line=dict(color=COL["alhajuela"], width=2), name="Curva Alhajuela"))
        fig_ca.add_trace(go.Scatter(x=[nv_a], y=[ar_a], mode="markers",
            marker=dict(color="red",size=12,symbol="star"), name=f"{nv_a:.1f} ft"))
        fig_ca.update_layout(xaxis_title="Nivel (ft)", yaxis_title="Área (km²)",
            template="plotly_white", height=350, margin=dict(l=50,r=20,t=20,b=50))
        st.plotly_chart(fig_ca, use_container_width=True)

    st.markdown("---")
    st.markdown("**Tabla de áreas y evaporación combinadas**")
    ae_rows = []
    for nv in np.arange(55,90,1):
        ar = area_desde_nivel_gat(float(nv))
        ae_rows.append({"Nivel Gatún (ft)":nv,"Área Gatún (km²)":round(ar,1),
            f"Evap {evap_gat_mm}mm (hm³/d)":round(evap_gat_mm*ar*1e-3,3)})
    ae_tbl_g = pd.DataFrame(ae_rows)
    ae_rows2  = []
    for nv in np.arange(180,256,2):
        ar = area_desde_nivel_alh(float(nv))
        ae_rows2.append({"Nivel Alhajuela (ft)":nv,"Área Alh (km²)":round(ar,1),
            f"Evap {evap_alh_mm}mm (hm³/d)":round(evap_alh_mm*ar*1e-3,3)})
    ae_tbl_a = pd.DataFrame(ae_rows2)
    tc1,tc2 = st.columns(2)
    with tc1:
        st.markdown("Gatún")
        st.dataframe(ae_tbl_g, use_container_width=True, hide_index=True, height=300)
    with tc2:
        st.markdown("Alhajuela")
        st.dataframe(ae_tbl_a, use_container_width=True, hide_index=True, height=300)


# ═══ TAB 9 — CONVERSOR ═══
with tabs[9]:
    st.subheader("🔄 Conversor de unidades")
    cv1,cv2 = st.columns(2)
    with cv1:
        st.markdown("### Caudal")
        m1 = st.radio("Desde:",["cfs","m³/s","hm³/día"],horizontal=True,key="mq")
        v1 = st.number_input("Valor",0.0,999999.0,100.0,key="vq")
        if m1=="cfs":
            st.success(f"**{v1:.2f} cfs** = **{v1*CFS2M3S:.4f} m³/s** = **{v1*CFS2HM3:.4f} hm³/día**")
        elif m1=="m³/s":
            st.success(f"**{v1:.4f} m³/s** = **{v1*M3S2CFS:.2f} cfs** = **{v1*M3S2CFS*CFS2HM3:.4f} hm³/día**")
        else:
            st.success(f"**{v1:.4f} hm³/día** = **{v1/CFS2HM3:.2f} cfs** = **{v1*HM3D2M3S:.4f} m³/s**")
    with cv2:
        st.markdown("### Volumen")
        m2 = st.radio("Desde:",["hm³","MPC","acre-ft"],horizontal=True,key="mv")
        v2 = st.number_input("Valor ",0.0,999999.0,1.0,key="vv")
        if m2=="hm³":
            st.success(f"**{v2:.4f} hm³** = {v2*1e6/28.3168:.0f} MPC = {v2*810.71:.1f} acre-ft")
        elif m2=="MPC":
            h=v2*28.3168/1e6
            st.success(f"**{v2:.0f} MPC** = {h:.4f} hm³ = {h*810.71:.1f} acre-ft")
        else:
            h=v2/810.71
            st.success(f"**{v2:.1f} acre-ft** = {h:.4f} hm³")
    st.markdown("---")
    st.dataframe(pd.DataFrame([
        {"cfs":r,"m³/s":round(r*CFS2M3S,3),"hm³/día":round(r*CFS2HM3,4),"hm³/mes":round(r*CFS2HM3*30,2)}
        for r in [1,10,50,100,500,1000,2000,4000,5000]
    ]), use_container_width=True, hide_index=True)


# ═══ TAB 10 — EXPORTAR ═══
with tabs[10]:
    st.subheader("📤 Exportar compilado de usos del dashboard")
    st.markdown("Descarga el estado actual del dashboard en Excel con múltiples hojas.")

    # ── Construir Excel en memoria ────────────────────────────────────────────
    def build_export_excel() -> bytes:
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:

            # Hoja 1: Resumen general
            resumen = pd.DataFrame([
                {"Parámetro":"Fecha de sesión","Valor":AHORA,"Unidad":""},
                {"Parámetro":"Unidad visual","Valor":unidad,"Unidad":""},
                {"Parámetro":"Fuente balance esclusajes","Valor":balance_escl_label,"Unidad":""},
                {"Parámetro":"Turn Around NPX/día","Valor":n_turnaround_npx,"Unidad":"eventos/día"},
                {"Parámetro":"Ahorro Turn Around aplicado","Valor":round(ahorro_turnaround_aplicado,4),"Unidad":"hm³/día"},
                {"Parámetro":"PNX/día","Valor":n_pnx,"Unidad":"esclusajes"},
                {"Parámetro":"NPX/día","Valor":n_npx,"Unidad":"esclusajes"},
                {"Parámetro":"Vol PNX","Valor":round(vp,4),"Unidad":"hm³/escl"},
                {"Parámetro":"Vol NPX","Valor":round(vn,4),"Unidad":"hm³/escl"},
                {"Parámetro":"Gen Madden","Valor":gm_mw,"Unidad":"MW"},
                {"Parámetro":"Gen Gatún","Valor":gg_mw,"Unidad":"MW"},
                {"Parámetro":"Factor Madden","Valor":mw_madden,"Unidad":"cfs/MW"},
                {"Parámetro":"Factor Gatún","Valor":mw_gatun,"Unidad":"cfs/MW"},
                {"Parámetro":"Potable Alhajuela","Valor":pot_alh,"Unidad":"cfs"},
                {"Parámetro":"Potable Gatún","Valor":pot_gat,"Unidad":"cfs"},
                {"Parámetro":"Fugas Alhajuela","Valor":fug_alh,"Unidad":"cfs"},
                {"Parámetro":"Fugas Gatún","Valor":fug_gat,"Unidad":"cfs"},
                {"Parámetro":"Vertido Fondo Madden","Valor":v_fondo,"Unidad":"cfs"},
                {"Parámetro":"Compuertas Tambor","Valor":v_tambor,"Unidad":"cfs"},
                {"Parámetro":"Vertido Libre","Valor":v_libre,"Unidad":"cfs"},
                {"Parámetro":"Vertido Gatún","Valor":v_gatun,"Unidad":"cfs"},
                {"Parámetro":"ZZ-Flush Cocolí","Valor":flush_cc,"Unidad":"hrs"},
                {"Parámetro":"ZZ-Flush A.Clara","Valor":flush_ac,"Unidad":"hrs"},
                {"Parámetro":"Evap lámina Gatún","Valor":evap_gat_mm,"Unidad":"mm/día"},
                {"Parámetro":"Evap lámina Alhajuela","Valor":evap_alh_mm,"Unidad":"mm/día"},
                {"Parámetro":"Área espejo Gatún","Valor":round(area_gat,2),"Unidad":"km²"},
                {"Parámetro":"Área espejo Alhajuela","Valor":round(area_alh,2),"Unidad":"km²"},
                {"Parámetro":"Modo área Gatún","Valor":area_modo_gat,"Unidad":""},
                {"Parámetro":"Modo área Alhajuela","Valor":area_modo_alh,"Unidad":""},
            ])
            resumen.to_excel(writer, sheet_name="Parámetros", index=False)

            # Hoja 2: Demandas por embalse
            dem_rows = []
            for nm,(h,cf,_) in all_usos.items():
                dem_rows.append({"Uso":nm,
                    "hm³/día":round(h,4),"cfs":round(cf,1),"m³/s":round(cf*CFS2M3S,2),
                    "% Sistema":round(h/max(dem_total,.001)*100,2)})
            dem_rows.append({"Uso":"TOTAL SISTEMA",
                "hm³/día":round(dem_total,4),"cfs":round(dem_total/CFS2HM3,1),
                "m³/s":round(dem_total*HM3D2M3S,2),"% Sistema":100.0})
            pd.DataFrame(dem_rows).to_excel(writer, sheet_name="Demandas Sistema", index=False)

            # Hoja 3: Alhajuela detalle
            tbl(alh_usos, alh_total, "Alhajuela", dem_total).to_excel(
                writer, sheet_name="Alhajuela Detalle", index=False)

            # Hoja 4: Gatún detalle
            tbl(gat_usos, gat_total, "Gatún", dem_total).to_excel(
                writer, sheet_name="Gatún Detalle", index=False)

            # Hoja 5: Escenarios (si existen)
            if "esc_tbl" in st.session_state and st.session_state["esc_tbl"]:
                pd.DataFrame(st.session_state["esc_tbl"]).to_excel(
                    writer, sheet_name="Escenarios", index=False)

            # Hoja 6: Curva área espejo Gatún
            ae_tbl_g.to_excel(writer, sheet_name="Área Espejo Gatún", index=False)
            ae_tbl_a.to_excel(writer, sheet_name="Área Espejo Alhajuela", index=False)

        buf.seek(0)
        return buf.read()

    # ── Vista previa ─────────────────────────────────────────────────────────
    exp_c1, exp_c2 = st.columns(2)
    with exp_c1:
        st.markdown("**📋 Resumen de demandas (sistema)**")
        rows_exp = []
        for nm,(h,cf,_) in all_usos.items():
            if h>0.0001:
                rows_exp.append({"Uso":nm,"hm³/día":round(h,4),
                    "cfs":round(cf,1),"m³/s":round(cf*CFS2M3S,2),
                    "%":round(h/max(dem_total,.001)*100,1)})
        rows_exp.append({"Uso":"TOTAL","hm³/día":round(dem_total,4),
            "cfs":round(dem_total/CFS2HM3,1),
            "m³/s":round(dem_total*HM3D2M3S,2),"%":100.0})
        st.dataframe(pd.DataFrame(rows_exp), use_container_width=True, hide_index=True)
    with exp_c2:
        st.markdown("**⚙️ Parámetros actuales**")
        params_prev = pd.DataFrame([
            {"Parámetro":"PNX/día",       "Valor":n_pnx},
            {"Parámetro":"NPX/día",       "Valor":n_npx},
            {"Parámetro":"Vol PNX (hm³)", "Valor":round(vp,4)},
            {"Parámetro":"Vol NPX (hm³)", "Valor":round(vn,4)},
            {"Parámetro":"Gen Madden (MW)","Valor":gm_mw},
            {"Parámetro":"Gen Gatún (MW)","Valor":gg_mw},
            {"Parámetro":"Área Gatún (km²)","Valor":round(area_gat,1)},
            {"Parámetro":"Área Alh (km²)","Valor":round(area_alh,1)},
            {"Parámetro":"Demanda total (hm³/d)","Valor":round(dem_total,3)},
            {"Parámetro":"Demanda total (cfs)",  "Valor":round(dem_total/CFS2HM3,1)},
            {"Parámetro":"Demanda total (m³/s)", "Valor":round(dem_total*HM3D2M3S,2)},
        ])
        st.dataframe(params_prev, use_container_width=True, hide_index=True)

    st.markdown("---")
    fname = f"demandas_ACP_{datetime.date.today().isoformat()}.xlsx"
    st.download_button(
        label="⬇️ Descargar compilado Excel (.xlsx)",
        data=build_export_excel(),
        file_name=fname,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
        type="primary",
    )
    st.caption(f"El archivo incluye hojas: Parámetros · Demandas Sistema · "
               f"Alhajuela Detalle · Gatún Detalle · Escenarios · Área Espejo Gatún · Área Espejo Alhajuela")


# ═══ TAB 11 — DATOS OPERATIVOS ═══
with tabs[11]:
    st.subheader("📂 Datos Operativos — LakeHouse")

    @st.cache_data(show_spinner="Cargando LakeHouse...")
    def cargar_lkh(src, sh):
        df = pd.read_excel(src, sheet_name=sh)
        col_f = None
        for c in df.columns:
            if "date" in str(c).lower(): col_f=c; break
        if col_f is None: col_f=df.columns[1]
        df["fecha"] = pd.to_datetime(df[col_f], errors="coerce")
        df = df.dropna(subset=["fecha"]).sort_values("fecha").reset_index(drop=True)
        rn = {}
        for c in df.columns:
            cl = str(c).lower()
            if "madel" in cl:               rn[c]="nv_a"
            elif "gatel" in cl:             rn[c]="nv_g"
            elif cl=="numlockgat":          rn[c]="n_g"
            elif cl=="numlockpm":           rn[c]="n_p"
            elif cl in ("numlockac","numlockacl"): rn[c]="n_a"
            elif cl=="numlockccl":          rn[c]="n_c"
            elif cl=="gatlockhm3":          rn[c]="gat_hm3"
            elif cl=="pmlockhm3":           rn[c]="pm_hm3"
            elif cl=="aclockhm3":           rn[c]="acl_hm3"
            elif cl=="ccllockhm3":          rn[c]="ccl_hm3"
            elif "gatlockmcf" in cl:        rn[c]="gat_mcf"
            elif "pmlockmcf" in cl:         rn[c]="pm_mcf"
            elif "aclockmcf" in cl:         rn[c]="acl_mcf"
            elif "ccllockmcf" in cl:        rn[c]="ccl_mcf"
            elif cl=="gatspill":            rn[c]="vert_g"
            elif cl=="madspill":            rn[c]="vert_m"
            elif cl=="munic_mad_hm3":       rn[c]="mun_m_hm3"
            elif cl=="munic_gat_hm3":       rn[c]="mun_g_hm3"
            elif cl=="munic_mad":           rn[c]="mun_m"
            elif cl=="munic_gat":           rn[c]="mun_g"
            elif cl=="leak_mad":            rn[c]="leak_m"
            elif cl=="leak_gat":            rn[c]="leak_g"
            elif cl=="evap_gatun_mm":       rn[c]="evap_gat_mm"
            elif cl=="evap_alaj_mm":        rn[c]="evap_alh_mm"
            elif cl=="vol_evap_gat_hm3":    rn[c]="evap_gat_hm3"
            elif cl=="vol_evap_ala_hm3":    rn[c]="evap_alh_hm3"
            elif cl=="saving_water_panamax":rn[c]="ahorro_pnx"
            elif cl in ("total_saving_water_neo_hm3","cca_neo"): rn[c]="ahorro_npx"
            elif cl=="madhm3":              rn[c]="gen_mad_hm3"
            elif cl=="gathm3":              rn[c]="gen_gat_hm3"
            elif cl in ("madmwh",):         rn[c]="mad_mwh"
            elif cl=="gatmwh":              rn[c]="gat_mwh"
            elif "total todos" in cl and "hec" in cl: rn[c]="total_escl_hm3"
            elif cl=="capgat_hm3":          rn[c]="cap_gat_hm3"
            elif cl=="capmad_hm3":          rn[c]="cap_mad_hm3"
        df = df.rename(columns=rn)
        for c in rn.values():
            if c in df: df[c]=pd.to_numeric(df[c],errors="coerce")
        if "gat_hm3" in df and "pm_hm3" in df:
            df["pnx_hm3"]=df["gat_hm3"].fillna(0)+df["pm_hm3"].fillna(0)
        if "acl_hm3" in df and "ccl_hm3" in df:
            df["npx_hm3"]=df["acl_hm3"].fillna(0)+df["ccl_hm3"].fillna(0)
        if "pnx_hm3" in df and "npx_hm3" in df:
            df["total_hm3"]=df["pnx_hm3"]+df["npx_hm3"]
        elif "gat_mcf" in df and "pm_mcf" in df:
            df["pnx_m"]=df["gat_mcf"].fillna(0)+df["pm_mcf"].fillna(0)
            if "acl_mcf" in df and "ccl_mcf" in df:
                df["npx_m"]=df["acl_mcf"].fillna(0)+df["ccl_mcf"].fillna(0)
            if "pnx_m" in df and "npx_m" in df:
                df["pnx_hm3"]=df["pnx_m"]*CFS2HM3
                df["npx_hm3"]=df["npx_m"]*CFS2HM3
                df["total_hm3"]=df["pnx_hm3"]+df["npx_hm3"]
        if "n_g" in df and "n_p" in df: df["n_pnx_r"]=df["n_g"].fillna(0)+df["n_p"].fillna(0)
        if "n_a" in df and "n_c" in df: df["n_npx_r"]=df["n_a"].fillna(0)+df["n_c"].fillna(0)
        return df

    import glob as _g
    lf = sorted(_g.glob("LakeHouse*.xlsx")); dl = None
    if lf:
        try:
            hs = pd.ExcelFile(lf[0]).sheet_names
            hojas_validas = [x for x in hs if x not in ["Sheet1","Para BalanceH"]]
            hoja = st.selectbox("Hoja",hojas_validas) if len(hojas_validas)>1 else hojas_validas[0]
            dl = cargar_lkh(lf[0],hoja)
            st.success(f"✅ {len(dl):,} registros · {dl['fecha'].min().date()} → {dl['fecha'].max().date()}")
        except Exception as e: st.error(str(e))
    else:
        fl = st.file_uploader("Sube LakeHouse (xlsx)",type=["xlsx"],key="lk")
        if fl:
            try:
                fl.seek(0); xls=pd.ExcelFile(fl)
                hojas_validas=[x for x in xls.sheet_names if x not in ["Sheet1","Para BalanceH"]]
                hoja=st.selectbox("Hoja",hojas_validas) if len(hojas_validas)>1 else hojas_validas[0]
                fl.seek(0); dl=cargar_lkh(fl,hoja)
                st.success(f"✅ {len(dl):,} registros · {dl['fecha'].min().date()} → {dl['fecha'].max().date()}")
            except Exception as e: st.error(str(e))

    if dl is not None and len(dl)>0:
        total_dias = (dl["fecha"].max()-dl["fecha"].min()).days
        st.markdown("---")
        dias_sel = st.slider("📅 Promedio de los últimos N días",
            min_value=7,max_value=min(total_dias,365),value=min(30,total_dias),step=1)
        fecha_corte = dl["fecha"].max()-pd.Timedelta(days=dias_sel)
        dv = dl[dl["fecha"]>=fecha_corte].copy()
        st.caption(f"Mostrando: **{len(dv)} días** · {dv['fecha'].min().date()} → {dv['fecha'].max().date()}")

        st.markdown("---")
        lk1,lk2,lk3,lk4,lk5,lk6 = st.columns(6)
        if "nv_g" in dv: lk1.metric("Nivel Gatún",    f"{dv['nv_g'].iloc[-1]:.2f} ft")
        if "nv_a" in dv: lk2.metric("Nivel Alhajuela", f"{dv['nv_a'].iloc[-1]:.2f} ft")
        if "n_pnx_r" in dv: lk3.metric(f"PNX/d ({dias_sel}d)",f"{dv['n_pnx_r'].mean():.0f}")
        if "n_npx_r" in dv: lk4.metric(f"NPX/d ({dias_sel}d)",f"{dv['n_npx_r'].mean():.0f}")
        if "total_hm3" in dv: lk5.metric(f"Consumo ({dias_sel}d)",f"{dv['total_hm3'].mean():.2f} hm³/d")
        if "total_escl_hm3" in dv: lk6.metric(f"Total escl ({dias_sel}d)",f"{dv['total_escl_hm3'].mean():.2f} hm³/d")

        if "nv_g" in dv and "nv_a" in dv:
            st.subheader("Niveles de embalses")
            fig_nv=make_subplots(specs=[[{"secondary_y":True}]])
            fig_nv.add_trace(go.Scatter(x=dv["fecha"],y=dv["nv_g"],name="Gatún (ft)",
                line=dict(color=COL["gatun"],width=2)),secondary_y=False)
            fig_nv.add_trace(go.Scatter(x=dv["fecha"],y=dv["nv_a"],name="Alhajuela (ft)",
                line=dict(color=COL["alhajuela"],width=2)),secondary_y=True)
            fig_nv.update_yaxes(title_text="Gatún ft",secondary_y=False)
            fig_nv.update_yaxes(title_text="Alhajuela ft",secondary_y=True)
            fig_nv.update_layout(template="plotly_white",height=380,hovermode="x unified",
                margin=dict(l=50,r=60,t=20,b=50))
            st.plotly_chart(fig_nv, use_container_width=True)

        if "total_hm3" in dv or "pnx_hm3" in dv:
            st.subheader(f"Consumo de esclusajes — últimos {dias_sel} días")
            fig_lk=go.Figure()
            if "pnx_hm3" in dv:
                fig_lk.add_trace(go.Bar(x=dv["fecha"],y=dv["pnx_hm3"],name="PNX",marker_color=COL["pnx"]))
            if "npx_hm3" in dv:
                fig_lk.add_trace(go.Bar(x=dv["fecha"],y=dv["npx_hm3"],name="NPX",marker_color=COL["npx"]))
            fig_lk.add_hline(y=dem_escl,line_dash="dash",line_color=COL["total"],
                annotation_text=f"Modelo: {dem_escl:.2f} hm³/d")
            col_th="total_hm3" if "total_hm3" in dv else "total_escl_hm3"
            if col_th in dv:
                prom_real=dv[col_th].mean()
                fig_lk.add_hline(y=prom_real,line_dash="dot",line_color=COL["esclusas"],
                    annotation_text=f"Real prom {dias_sel}d: {prom_real:.2f}")
            fig_lk.update_layout(barmode="stack",yaxis_title="hm³/día",template="plotly_white",
                height=400,margin=dict(l=50,r=20,t=20,b=50))
            st.plotly_chart(fig_lk, use_container_width=True)
            if col_th in dv:
                real_p=dv[col_th].mean(); dif=dem_escl-real_p
                mr1,mr2,mr3=st.columns(3)
                mr1.metric(f"Real prom ({dias_sel}d)",f3u(real_p))
                mr2.metric("Modelo",f3u(dem_escl))
                mr3.metric("Diferencia",f"{dif:+.3f} hm³/d ({dif/max(real_p,.001)*100:+.1f}%)")

        st.subheader(f"Promedios últimos {dias_sel} días")
        prom_rows=[]
        prom_cols=[
            ("nv_g","Nivel Gatún","ft"),("nv_a","Nivel Alhajuela","ft"),
            ("n_pnx_r","Esclusajes PNX","/día"),("n_npx_r","Esclusajes NPX","/día"),
            ("pnx_hm3","Consumo PNX","hm³/d"),("npx_hm3","Consumo NPX","hm³/d"),
            ("total_hm3","Consumo total escl.","hm³/d"),
            ("gen_mad_hm3","Generación Madden","hm³/d"),("gen_gat_hm3","Generación Gatún","hm³/d"),
            ("mun_m","Potable Alhajuela","MCF"),("mun_g","Potable Gatún","MCF"),
            ("leak_m","Fugas Alhajuela","MCF"),("leak_g","Fugas Gatún","MCF"),
            ("vert_g","Vertido Gatún","MCF"),("vert_m","Vertido Madden","MCF"),
            ("evap_gat_mm","Evaporación Gatún","mm/d"),("evap_alh_mm","Evaporación Alhajuela","mm/d"),
            ("evap_gat_hm3","Vol. evap. Gatún","hm³/d"),("evap_alh_hm3","Vol. evap. Alhajuela","hm³/d"),
            ("ahorro_pnx","Ahorro PNX","hm³/d"),("ahorro_npx","Ahorro NPX","hm³/d"),
        ]
        for col_name,label,unit in prom_cols:
            if col_name in dv and dv[col_name].notna().sum()>0:
                val=dv[col_name].mean()
                prom_rows.append({"Parámetro":label,"Promedio":round(val,3),
                    "Mínimo":round(dv[col_name].min(),3),"Máximo":round(dv[col_name].max(),3),"Unidad":unit})
        if prom_rows:
            st.dataframe(pd.DataFrame(prom_rows), use_container_width=True, hide_index=True)

        if "mun_m" in dv:
            st.subheader(f"Balance hídrico — últimos {dias_sel} días (MCF/día)")
            fig_bal=go.Figure()
            for cn,nm,cl in [
                ("pnx_hm3","Escl. PNX",COL["pnx"]),("npx_hm3","Escl. NPX",COL["npx"]),
                ("mun_m","Pot. Alh",COL["potable"]),("mun_g","Pot. Gat","#2ecc71"),
                ("leak_m","Fug. Alh",COL["fugas"]),("leak_g","Fug. Gat","#f39c12"),
                ("vert_g","Vert. Gat",COL["vertidos"]),
            ]:
                if cn in dv and dv[cn].notna().sum()>0:
                    fig_bal.add_trace(go.Bar(x=dv["fecha"],y=dv[cn],name=nm,marker_color=cl))
            fig_bal.update_layout(barmode="stack",yaxis_title="MCF ó hm³/d",
                template="plotly_white",height=420,hovermode="x unified",
                margin=dict(l=50,r=20,t=20,b=50))
            st.plotly_chart(fig_bal, use_container_width=True)

        st.markdown("---")
        st.download_button("⬇️ Descargar período (CSV)",
            dv.to_csv(index=False).encode("utf-8"),
            f"lakehouse_{dias_sel}dias.csv","text/csv")
    else:
        st.info("Sube **LakeHouse_Data.xlsx** o **LakeHouse_NEW.xlsx**, o colócalo en la carpeta.")


# ═══ FOOTER ═══
st.markdown("---")
ftr_c1, ftr_c2, ftr_c3 = st.columns([1, 6, 1])
with ftr_c1:
    _cp_f = _img_tag(_logo_cp_mime, _logo_cp, "width:65px;opacity:0.75;")
    if _cp_f:
        st.markdown(_cp_f, unsafe_allow_html=True)
with ftr_c2:
    st.markdown(
        "<div style='color:#aab7b8;font-size:0.85rem;padding-top:6px;text-align:center;'>"
        "💧 Demandas de Agua · Canal de Panamá · ACP · HIMH — Sección de Hidrología<br>"
        f"Creador: JFRodriguez · Sesión: {AHORA}</div>",
        unsafe_allow_html=True)
with ftr_c3:
    _himh_f = _img_tag(_logo_mime, _logo, "width:48px;opacity:0.75;float:right;")
    if _himh_f:
        st.markdown(_himh_f, unsafe_allow_html=True)
