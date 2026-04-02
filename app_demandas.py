"""
💧 Dashboard Demandas de Agua por Embalse — Canal de Panamá
Creador: JFRodriguez
pip install streamlit pandas numpy plotly openpyxl
streamlit run app_demandas.py
"""
import streamlit as st, pandas as pd, numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
st.set_page_config(page_title="💧 Demandas — Canal de Panamá", page_icon="💧", layout="wide")
CFS2HM3=1/408.68; CFS2M3S=1/35.3147; M3S2CFS=35.3147; MW_M=80.71; MW_G=185.4
COL={"alhajuela":"#3498db","gatun":"#1a5276","esclusas":"#2980b9","potable":"#27ae60","fugas":"#e67e22","vertidos":"#9b59b6","generacion":"#f39c12","flush":"#1abc9c","pnx":"#2c3e50","npx":"#16a085","total":"#c0392b","tambor":"#d35400"}

def tbl(usos, total, nombre, dem_t):
    f=[]
    for nm,(h,c,_) in usos.items():
        f.append({"Uso":nm,"hm³/día":round(h,4),"cfs":round(c,1),"m³/s":round(c*CFS2M3S,2),f"% {nombre}":round(h/max(total,.001)*100,1),"% Sistema":round(h/max(dem_t,.001)*100,1)})
    f.append({"Uso":f"TOTAL","hm³/día":round(total,4),"cfs":round(total/CFS2HM3,1),"m³/s":round(total*1e6/86400,2),f"% {nombre}":100.0,"% Sistema":round(total/max(dem_t,.001)*100,1)})
    return pd.DataFrame(f)

# SIDEBAR
st.sidebar.markdown("## 💧 Demandas de Agua\nCanal de Panamá\n---")
st.sidebar.markdown("### 🚢 Esclusajes")
n_pnx=st.sidebar.slider("PNX/día",0,40,28); n_npx=st.sidebar.slider("NPX/día",0,20,11); n_t=n_pnx+n_npx
st.sidebar.markdown("### 📐 Consumo por esclusaje")
modo=st.sidebar.radio("Entrada",["hm³/escl","m³/s equiv","cfs equiv"],horizontal=True)
if modo=="hm³/escl":
    vp=st.sidebar.number_input("Vol PNX (hm³)",0.05,0.5,0.201,0.001,format="%.3f")
    vn=st.sidebar.number_input("Vol NPX (hm³)",0.1,0.8,0.450,0.001,format="%.3f")
elif modo=="m³/s equiv":
    vp_m=st.sidebar.number_input("PNX (m³/s)",0.5,10.0,2.33,0.01); vn_m=st.sidebar.number_input("NPX (m³/s)",1.0,15.0,5.21,0.01)
    vp=vp_m*86400/1e6/max(n_pnx,1); vn=vn_m*86400/1e6/max(n_npx,1)
else:
    vp_c=st.sidebar.number_input("PNX (cfs)",20.0,300.0,82.2,0.1); vn_c=st.sidebar.number_input("NPX (cfs)",50.0,500.0,184.0,0.1)
    vp=vp_c*CFS2HM3/max(n_pnx,1); vn=vn_c*CFS2HM3/max(n_npx,1)
st.sidebar.caption(f"**PNX:** {vp:.3f} hm³ = {vp*1e6/86400:.2f} m³/s = {vp/CFS2HM3:.1f} cfs")
st.sidebar.caption(f"**NPX:** {vn:.3f} hm³ = {vn*1e6/86400:.2f} m³/s = {vn/CFS2HM3:.1f} cfs")
st.sidebar.markdown("### ⚡ Generación")
gm=st.sidebar.slider("Madden (MW)",0,36,19); gg=st.sidebar.slider("Gatún (MW)",0,30,0)
st.sidebar.markdown("### 🚰 Potable (cfs)")
pa=st.sidebar.number_input("Alhajuela",0,800,377); pg=st.sidebar.number_input("Gatún",0,600,264)
st.sidebar.markdown("### 💨 Fugas (cfs)")
fa=st.sidebar.number_input("Alhajuela ",0,300,71); fg=st.sidebar.number_input("Gatún ",0,400,159)
st.sidebar.markdown("### 🌊 Vertidos Alhajuela (cfs)")
vf=st.sidebar.number_input("Fondo Madden",0,5000,0); vta=st.sidebar.number_input("Compuertas Tambor",0,30000,0,100); vli=st.sidebar.number_input("Libre (overflow)",0,20000,0,100)
st.sidebar.markdown("### 🌊 Vertidos Gatún (cfs)")
vga=st.sidebar.number_input("Vertido Gatún",0,20000,0,100)
st.sidebar.markdown("### 🔄 ZZ-Flush")
fcc=st.sidebar.number_input("Cocolí (hrs)",0.0,8.0,0.0,0.5); fac=st.sidebar.number_input("A.Clara (hrs)",0.0,8.0,0.0,0.5)
st.sidebar.markdown("---")
unidad=st.sidebar.radio("Unidad visual",["hm³/día","cfs","m³/s"],horizontal=True)
u=unidad; cv=1 if u=="hm³/día" else (1/CFS2HM3 if u=="cfs" else 1e6/86400)

# CÁLCULOS
a_gen=gm*MW_M*CFS2HM3; a_pot=pa*CFS2HM3; a_fug=fa*CFS2HM3; a_vf=vf*CFS2HM3; a_vt=vta*CFS2HM3; a_vl=vli*CFS2HM3
a_tot=a_gen+a_pot+a_fug+a_vf+a_vt+a_vl
a_u={"Generación Madden":(a_gen,gm*MW_M,COL["generacion"]),"Agua Potable":(a_pot,pa,COL["potable"]),"Fugas":(a_fug,fa,COL["fugas"]),"Vertido fondo":(a_vf,vf,"#7f8c8d"),"Compuertas Tambor":(a_vt,vta,COL["tambor"]),"Vertido libre":(a_vl,vli,COL["vertidos"])}
g_gen=gg*MW_G*CFS2HM3; g_pot=pg*CFS2HM3; g_fug=fg*CFS2HM3; g_ver=vga*CFS2HM3
g_ep=n_pnx*vp; g_en=n_npx*vn; g_et=g_ep+g_en; g_fl=333.5*(fcc+fac)*3600/1e6
g_tot=g_gen+g_pot+g_fug+g_ver+g_et+g_fl
g_u={"Esclusajes PNX":(g_ep,g_ep/CFS2HM3,COL["pnx"]),"Esclusajes NPX":(g_en,g_en/CFS2HM3,COL["npx"]),"ZZ-Flush":(g_fl,g_fl/CFS2HM3,COL["flush"]),"Generación Gatún":(g_gen,gg*MW_G,COL["generacion"]),"Agua Potable":(g_pot,pg,COL["potable"]),"Fugas":(g_fug,fg,COL["fugas"]),"Vertido Gatún":(g_ver,vga,COL["vertidos"])}
dt=a_tot+g_tot

# HEADER
st.markdown("<h1 style='color:#1a5276;'>💧 Demandas de Agua por Embalse</h1><p style='color:#5d6d7e;margin-top:-12px;'>Canal de Panamá · <b>Creador: JFRodriguez</b></p>",unsafe_allow_html=True)
k1,k2,k3,k4,k5,k6=st.columns(6)
k1.metric("Total",f"{dt*cv:.2f} {u}"); k2.metric("Alhajuela",f"{a_tot*cv:.2f} {u}"); k3.metric("Gatún",f"{g_tot*cv:.2f} {u}")
k4.metric("Esclusajes",f"{n_t}/día"); k5.metric("Vol PNX",f"{vp:.3f} hm³"); k6.metric("Vol NPX",f"{vn:.3f} hm³")
st.markdown("---")

tabs=st.tabs(["📊 Balance","🏔️ Alhajuela","🌊 Gatún","🔀 Comparar","🎯 Escenarios","🔄 Conversor","📂 Datos Operativos"])

# TAB 0 BALANCE
with tabs[0]:
    b1,b2=st.columns(2)
    with b1:
        st.subheader("Por embalse")
        fig=go.Figure(); fig.add_trace(go.Bar(x=["Alhajuela","Gatún","Total"],y=[a_tot*cv,g_tot*cv,dt*cv],marker_color=[COL["alhajuela"],COL["gatun"],COL["total"]],text=[f"{a_tot*cv:.2f}",f"{g_tot*cv:.2f}",f"{dt*cv:.2f}"],textposition="auto"))
        fig.update_layout(yaxis_title=u,template="plotly_white",height=400,margin=dict(l=50,r=20,t=20,b=50)); st.plotly_chart(fig,use_container_width=True)
    with b2:
        st.subheader("Por uso")
        td={**{k:v[0] for k,v in a_u.items()},**{k:v[0] for k,v in g_u.items()}}; tf={k:v for k,v in td.items() if v>0.001}
        fig2=go.Figure(go.Pie(labels=list(tf.keys()),values=[v*cv for v in tf.values()],hole=0.45,textinfo="percent+label",textposition="outside"))
        fig2.update_layout(height=400,template="plotly_white",margin=dict(l=10,r=10,t=20,b=10),showlegend=False); st.plotly_chart(fig2,use_container_width=True)
    g1,g2,g3,g4,g5=st.columns(5)
    for c,nm,vl,cl in [(g1,"Esclusajes",g_et/max(dt,.001)*100,COL["esclusas"]),(g2,"Potable",(a_pot+g_pot)/max(dt,.001)*100,COL["potable"]),(g3,"Generación",(a_gen+g_gen)/max(dt,.001)*100,COL["generacion"]),(g4,"Fugas",(a_fug+g_fug)/max(dt,.001)*100,COL["fugas"]),(g5,"Vertidos",(a_vf+a_vt+a_vl+g_ver+g_fl)/max(dt,.001)*100,COL["vertidos"])]:
        with c:
            f3=go.Figure(go.Indicator(mode="gauge+number",value=vl,title={"text":nm,"font":{"size":12}},number={"suffix":"%","font":{"size":20}},gauge={"axis":{"range":[0,100]},"bar":{"color":cl}})); f3.update_layout(height=170,margin=dict(l=15,r=15,t=35,b=5)); st.plotly_chart(f3,use_container_width=True)
    st.subheader("Tabla completa (hm³/día · cfs · m³/s)")
    r=[]
    for nm,(h,cf,_) in {**a_u,**g_u}.items():
        if h>0.0001: r.append({"Uso":nm,"hm³/día":round(h,4),"cfs":round(cf,1),"m³/s":round(cf*CFS2M3S,2),"%":round(h/max(dt,.001)*100,1)})
    r.append({"Uso":"TOTAL","hm³/día":round(dt,4),"cfs":round(dt/CFS2HM3,1),"m³/s":round(dt*1e6/86400,2),"%":100.0})
    st.dataframe(pd.DataFrame(r),use_container_width=True,hide_index=True)

# TAB 1 ALHAJUELA
with tabs[1]:
    st.subheader("🏔️ Embalse Alhajuela"); st.metric("Total",f"{a_tot*cv:.3f} {u}")
    c1,c2=st.columns(2)
    with c1:
        af={k:v[0] for k,v in a_u.items() if v[0]>0.001}
        if af:
            fig=go.Figure(go.Pie(labels=list(af.keys()),values=[v*cv for v in af.values()],marker_colors=[a_u[k][2] for k in af],hole=0.45,textinfo="percent+label"))
            fig.update_layout(height=400,template="plotly_white",margin=dict(l=10,r=10,t=20,b=10),showlegend=False); st.plotly_chart(fig,use_container_width=True)
    with c2:
        fig=go.Figure()
        for nm,(h,cf,cl) in a_u.items(): fig.add_trace(go.Bar(y=[nm],x=[h*cv],orientation="h",marker_color=cl,text=[f"{h*cv:.3f}"],textposition="auto",showlegend=False))
        fig.update_layout(xaxis_title=u,template="plotly_white",height=400,margin=dict(l=10,r=20,t=20,b=50)); st.plotly_chart(fig,use_container_width=True)
    if a_vf+a_vt+a_vl>0.001:
        st.subheader("Vertidos Alhajuela")
        v1,v2,v3=st.columns(3)
        v1.metric("Fondo",f"{vf} cfs · {vf*CFS2M3S:.1f} m³/s"); v2.metric("Tambor",f"{vta} cfs · {vta*CFS2M3S:.1f} m³/s"); v3.metric("Libre",f"{vli} cfs · {vli*CFS2M3S:.1f} m³/s")
    st.dataframe(tbl(a_u,a_tot,"Alhajuela",dt),use_container_width=True,hide_index=True)

# TAB 2 GATÚN
with tabs[2]:
    st.subheader("🌊 Embalse Gatún"); st.metric("Total",f"{g_tot*cv:.3f} {u}")
    c1,c2=st.columns(2)
    with c1:
        gf={k:v[0] for k,v in g_u.items() if v[0]>0.001}
        fig=go.Figure(go.Pie(labels=list(gf.keys()),values=[v*cv for v in gf.values()],marker_colors=[g_u[k][2] for k in gf],hole=0.45,textinfo="percent+label"))
        fig.update_layout(height=400,template="plotly_white",margin=dict(l=10,r=10,t=20,b=10),showlegend=False); st.plotly_chart(fig,use_container_width=True)
    with c2:
        fig=go.Figure()
        for nm,(h,cf,cl) in g_u.items(): fig.add_trace(go.Bar(y=[nm],x=[h*cv],orientation="h",marker_color=cl,text=[f"{h*cv:.3f}"],textposition="auto",showlegend=False))
        fig.update_layout(xaxis_title=u,template="plotly_white",height=400,margin=dict(l=10,r=20,t=20,b=50)); st.plotly_chart(fig,use_container_width=True)
    st.subheader("Esclusajes (3 unidades)")
    ed=[]
    for t,n,v in [("Panamax",n_pnx,vp),("Neopanamax",n_npx,vn)]:
        th=n*v; ed.append({"Tipo":t,"N/día":n,"hm³/escl":round(v,3),"m³/s":round(v*1e6/86400,2),"cfs/escl":round(v/CFS2HM3,1),"Total hm³/d":round(th,2),"Total cfs":round(th/CFS2HM3,0),"Total m³/s":round(th*1e6/86400,2)})
    ed.append({"Tipo":"TOTAL","N/día":n_t,"hm³/escl":round(g_et/max(n_t,1),3),"m³/s":round(g_et/max(n_t,1)*1e6/86400,2),"cfs/escl":round(g_et/max(n_t,1)/CFS2HM3,1),"Total hm³/d":round(g_et,2),"Total cfs":round(g_et/CFS2HM3,0),"Total m³/s":round(g_et*1e6/86400,2)})
    st.dataframe(pd.DataFrame(ed),use_container_width=True,hide_index=True)
    st.dataframe(tbl(g_u,g_tot,"Gatún",dt),use_container_width=True,hide_index=True)

# TAB 3 COMPARAR
with tabs[3]:
    st.subheader("Alhajuela vs Gatún")
    uc=["Generación","Potable","Fugas","Vertidos","Esclusajes","Flush"]
    va2=[a_gen,a_pot,a_fug,a_vf+a_vt+a_vl,0,0]; vg2=[g_gen,g_pot,g_fug,g_ver,g_et,g_fl]
    fig=go.Figure()
    fig.add_trace(go.Bar(x=uc,y=[v*cv for v in va2],name="Alhajuela",marker_color=COL["alhajuela"]))
    fig.add_trace(go.Bar(x=uc,y=[v*cv for v in vg2],name="Gatún",marker_color=COL["gatun"]))
    fig.update_layout(barmode="group",yaxis_title=u,template="plotly_white",height=450,margin=dict(l=50,r=20,t=20,b=50)); st.plotly_chart(fig,use_container_width=True)
    c1,c2=st.columns(2)
    with c1:
        fig=go.Figure(go.Pie(labels=["Alhajuela","Gatún"],values=[a_tot,g_tot],marker_colors=[COL["alhajuela"],COL["gatun"]],hole=0.5,textinfo="percent+label+value",texttemplate="%{label}<br>%{percent}<br>%{value:.2f} hm³/d"))
        fig.update_layout(height=300,template="plotly_white",margin=dict(l=10,r=10,t=20,b=10)); st.plotly_chart(fig,use_container_width=True)
    with c2:
        ca=["Gen","Pot","Fug","Vert","Escl"]; ra2=[a_gen,a_pot,a_fug,a_vf+a_vt+a_vl,0]; rg2=[g_gen,g_pot,g_fug,g_ver,g_et]
        mx=[max(a,g,.001) for a,g in zip(ra2,rg2)]
        fig=go.Figure()
        fig.add_trace(go.Scatterpolar(r=[a/m*100 for a,m in zip(ra2,mx)]+[ra2[0]/mx[0]*100],theta=ca+[ca[0]],fill="toself",name="Alh",fillcolor="rgba(52,152,219,0.2)",line_color=COL["alhajuela"]))
        fig.add_trace(go.Scatterpolar(r=[g/m*100 for g,m in zip(rg2,mx)]+[rg2[0]/mx[0]*100],theta=ca+[ca[0]],fill="toself",name="Gat",fillcolor="rgba(26,82,118,0.2)",line_color=COL["gatun"]))
        fig.update_layout(polar=dict(radialaxis=dict(visible=True,range=[0,110])),height=350,template="plotly_white",margin=dict(l=40,r=40,t=20,b=10)); st.plotly_chart(fig,use_container_width=True)
    st.dataframe(pd.DataFrame([{"Uso":us,f"Alh (hm³/d)":round(a,3),f"Alh (cfs)":round(a/CFS2HM3,1),f"Gat (hm³/d)":round(g,3),f"Gat (cfs)":round(g/CFS2HM3,1),f"Total (m³/s)":round((a+g)*1e6/86400,2)} for us,a,g in zip(uc,va2,vg2)]),use_container_width=True,hide_index=True)

# TAB 4 ESCENARIOS
with tabs[4]:
    st.subheader("🎯 Probable · Optimista · Pesimista")
    def ce(p):
        a=p["gm"]*MW_M*CFS2HM3+p["pa"]*CFS2HM3+p["fa"]*CFS2HM3+p["va"]*CFS2HM3
        e=p["np"]*p["vp"]+p["nn"]*p["vn"]; g=p["gg"]*MW_G*CFS2HM3+p["pg"]*CFS2HM3+p["fg"]*CFS2HM3+p["vg"]*CFS2HM3+e
        return {"A":a,"G":g,"T":a+g,"E":e,"N":p["np"]+p["nn"]}
    pr={"🟡 Probable":{"np":n_pnx,"nn":n_npx,"vp":vp,"vn":vn,"gm":gm,"gg":gg,"pa":pa,"pg":pg,"fa":fa,"fg":fg,"va":vf+vta+vli,"vg":vga},
        "🟢 Optimista":{"np":30,"nn":14,"vp":0.190,"vn":0.397,"gm":20,"gg":5,"pa":350,"pg":250,"fa":50,"fg":120,"va":0,"vg":0},
        "🔴 Pesimista":{"np":22,"nn":7,"vp":0.210,"vn":0.450,"gm":10,"gg":0,"pa":420,"pg":300,"fa":90,"fg":200,"va":0,"vg":0}}
    er={}; ec=st.columns(3)
    for (nm,pre),col in zip(pr.items(),ec):
        with col:
            st.markdown(f"#### {nm}"); p={}
            p["np"]=st.number_input("PNX",0,40,pre["np"],key=f"e1{nm}"); p["nn"]=st.number_input("NPX",0,20,pre["nn"],key=f"e2{nm}")
            p["vp"]=st.number_input("Vol PNX",0.1,0.4,pre["vp"],0.001,key=f"e3{nm}",format="%.3f"); p["vn"]=st.number_input("Vol NPX",0.1,0.6,pre["vn"],0.001,key=f"e4{nm}",format="%.3f")
            p["gm"]=st.number_input("Gen Mad",0,36,pre["gm"],key=f"e5{nm}"); p["gg"]=pre["gg"]
            p["pa"]=st.number_input("Pot Alh",0,800,pre["pa"],key=f"e6{nm}"); p["pg"]=st.number_input("Pot Gat",0,600,pre["pg"],key=f"e7{nm}")
            p["fa"]=pre["fa"]; p["fg"]=pre["fg"]; p["va"]=pre["va"]; p["vg"]=pre["vg"]
            er[nm]=ce(p)
    st.markdown("---")
    fig=go.Figure()
    for nm,r in er.items():
        fig.add_trace(go.Bar(x=[nm],y=[r["A"]*cv],name="Alh",marker_color=COL["alhajuela"],showlegend=nm==list(er)[0]))
        fig.add_trace(go.Bar(x=[nm],y=[r["G"]*cv],name="Gat",marker_color=COL["gatun"],showlegend=nm==list(er)[0]))
    fig.update_layout(barmode="stack",yaxis_title=u,template="plotly_white",height=420,margin=dict(l=50,r=20,t=20,b=50)); st.plotly_chart(fig,use_container_width=True)
    st.dataframe(pd.DataFrame([{"Escenario":n,"N/día":r["N"],"Alh hm³/d":round(r["A"],2),"Gat hm³/d":round(r["G"],2),"Total hm³/d":round(r["T"],2),"Total cfs":round(r["T"]/CFS2HM3,0),"Total m³/s":round(r["T"]*1e6/86400,2)} for n,r in er.items()]),use_container_width=True,hide_index=True)
    pt=list(er.values())[0]["T"]
    for n,r in list(er.items())[1:]:
        d=r["T"]-pt; st.markdown(f"**{n}:** {d*cv:+.2f} {u} ({d/max(pt,.001)*100:+.1f}% vs Probable)")

# TAB 5 CONVERSOR
with tabs[5]:
    st.subheader("🔄 Conversor de unidades")
    c1,c2=st.columns(2)
    with c1:
        st.markdown("### Caudal"); m=st.radio("Desde:",["cfs","m³/s","hm³/día"],horizontal=True,key="mc"); v=st.number_input("Valor",0.0,999999.0,100.0,key="vc")
        if m=="cfs": st.success(f"**{v:.2f} cfs** = **{v*CFS2M3S:.4f} m³/s** = **{v*CFS2HM3:.4f} hm³/día**")
        elif m=="m³/s": st.success(f"**{v:.4f} m³/s** = **{v*M3S2CFS:.2f} cfs** = **{v*86400/1e6:.4f} hm³/día**")
        else: st.success(f"**{v:.4f} hm³/día** = **{v/CFS2HM3:.2f} cfs** = **{v*1e6/86400:.4f} m³/s**")
    with c2:
        st.markdown("### Volumen"); m2=st.radio("Desde:",["hm³","MPC","acre-ft"],horizontal=True,key="mv"); v2=st.number_input("Valor ",0.0,999999.0,1.0,key="vv")
        if m2=="hm³": st.success(f"**{v2:.4f} hm³** = {v2*1e6/28.3168:.0f} MPC = {v2*810.71:.1f} acre-ft")
        elif m2=="MPC": h=v2*28.3168/1e6; st.success(f"**{v2:.0f} MPC** = {h:.4f} hm³ = {h*810.71:.1f} acre-ft")
        else: h=v2/810.71; st.success(f"**{v2:.1f} acre-ft** = {h:.4f} hm³")
    st.markdown("---"); st.subheader("Tabla de referencia")
    st.dataframe(pd.DataFrame([{"cfs":r,"m³/s":round(r*CFS2M3S,3),"hm³/día":round(r*CFS2HM3,4),"hm³/mes":round(r*CFS2HM3*30,2)} for r in [1,10,50,100,500,1000,2000,4000,5000]]),use_container_width=True,hide_index=True)

# TAB 6 DATOS OPERATIVOS
with tabs[6]:
    st.subheader("📂 Datos Operativos — LakeHouse")
    @st.cache_data(show_spinner="Cargando...")
    def clkh(src,sh):
        df=pd.read_excel(src,sheet_name=sh); cf=None
        for c in df.columns:
            if "date" in str(c).lower(): cf=c; break
        if cf is None: cf=df.columns[1]
        df["fecha"]=pd.to_datetime(df[cf],errors="coerce"); df=df.dropna(subset=["fecha"]).sort_values("fecha").reset_index(drop=True)
        rn={}
        for c in df.columns:
            cl=str(c).upper()
            if "MADEL" in cl: rn[c]="nv_a"
            elif "GATEL" in cl: rn[c]="nv_g"
            elif cl=="NUMLOCKGAT": rn[c]="ng"
            elif "GATLOCKMCF" in cl: rn[c]="gm"
            elif cl=="NUMLOCKPM": rn[c]="np"
            elif "PMLOCKMCF" in cl: rn[c]="pm"
            elif cl=="NUMLOCKACL": rn[c]="na"
            elif "ACLOCKMCF" in cl: rn[c]="am"
            elif cl=="NUMLOCKCCL": rn[c]="nc"
            elif "CCLLOCKMCF" in cl: rn[c]="cm"
            elif cl=="GATSPILL": rn[c]="vg"
            elif "MUNIC" in cl and "MAD" in cl: rn[c]="mm"
            elif "MUNIC" in cl and "GAT" in cl: rn[c]="mg"
            elif "LEAK" in cl and "MAD" in cl: rn[c]="lm"
            elif "LEAK" in cl and "GAT" in cl: rn[c]="lg"
            elif "PANAMAX" in cl and "AAP" in cl: rn[c]="ap"
            elif "NEOPANAMAX" in cl and "CCA" in cl: rn[c]="an"
        df=df.rename(columns=rn)
        for c in rn.values():
            if c in df: df[c]=pd.to_numeric(df[c],errors="coerce")
        if "gm" in df and "pm" in df: df["pnx_m"]=df["gm"].fillna(0)+df["pm"].fillna(0)
        if "am" in df and "cm" in df: df["npx_m"]=df["am"].fillna(0)+df["cm"].fillna(0)
        if "ng" in df and "np" in df: df["npnx"]=df["ng"].fillna(0)+df["np"].fillna(0)
        if "na" in df and "nc" in df: df["nnpx"]=df["na"].fillna(0)+df["nc"].fillna(0)
        if "pnx_m" in df and "npx_m" in df:
            df["tot_m"]=df["pnx_m"]+df["npx_m"]; df["ph"]=df["pnx_m"]*CFS2HM3; df["nh"]=df["npx_m"]*CFS2HM3; df["th"]=df["tot_m"]*CFS2HM3
        return df
    import glob as _g; lf=sorted(_g.glob("LakeHouse*.xlsx")); dl=None
    if lf:
        try:
            hs=pd.ExcelFile(lf[0]).sheet_names; h=st.selectbox("Hoja",[x for x in hs if x not in ["Sheet1","Para BalanceH"]]); dl=clkh(lf[0],h); st.success(f"✅ {len(dl)} registros")
        except Exception as e: st.error(str(e))
    else:
        fl=st.file_uploader("Sube LakeHouse_NEW.xlsx",type=["xlsx"],key="lk")
        if fl:
            try:
                hs=pd.ExcelFile(fl).sheet_names; h=st.selectbox("Hoja",[x for x in hs if x not in ["Sheet1","Para BalanceH"]]); dl=clkh(fl,h); st.success(f"✅ {len(dl)} registros")
            except Exception as e: st.error(str(e))
    if dl is not None and len(dl)>0:
        l1,l2,l3,l4=st.columns(4)
        if "nv_g" in dl: l1.metric("Gatún",f"{dl['nv_g'].iloc[-1]:.2f} ft")
        if "nv_a" in dl: l2.metric("Alhajuela",f"{dl['nv_a'].iloc[-1]:.2f} ft")
        if "npnx" in dl: l3.metric("PNX/d",f"{dl['npnx'].mean():.0f}")
        if "nnpx" in dl: l4.metric("NPX/d",f"{dl['nnpx'].mean():.0f}")
        if "nv_g" in dl and "nv_a" in dl:
            st.subheader("Niveles")
            fig=make_subplots(specs=[[{"secondary_y":True}]])
            fig.add_trace(go.Scatter(x=dl["fecha"],y=dl["nv_g"],name="Gatún",line=dict(color=COL["gatun"],width=2)),secondary_y=False)
            fig.add_trace(go.Scatter(x=dl["fecha"],y=dl["nv_a"],name="Alhajuela",line=dict(color=COL["alhajuela"],width=2)),secondary_y=True)
            fig.update_yaxes(title_text="Gatún ft",secondary_y=False); fig.update_yaxes(title_text="Alhajuela ft",secondary_y=True)
            fig.update_layout(template="plotly_white",height=380,hovermode="x unified",margin=dict(l=50,r=60,t=20,b=50)); st.plotly_chart(fig,use_container_width=True)
        if "th" in dl:
            st.subheader("Consumo esclusajes (hm³/d)")
            fig=go.Figure()
            if "ph" in dl: fig.add_trace(go.Bar(x=dl["fecha"],y=dl["ph"],name="PNX",marker_color=COL["pnx"]))
            if "nh" in dl: fig.add_trace(go.Bar(x=dl["fecha"],y=dl["nh"],name="NPX",marker_color=COL["npx"]))
            fig.add_hline(y=g_et,line_dash="dash",line_color=COL["total"],annotation_text=f"Modelo: {g_et:.2f}")
            fig.update_layout(barmode="stack",yaxis_title="hm³/día",template="plotly_white",height=380,margin=dict(l=50,r=20,t=20,b=50)); st.plotly_chart(fig,use_container_width=True)
            rp=dl["th"].mean(); md=g_et-rp
            m1,m2,m3=st.columns(3)
            m1.metric("Real",f"{rp:.2f} hm³/d · {rp/CFS2HM3:.0f} cfs · {rp*1e6/86400:.1f} m³/s")
            m2.metric("Modelo",f"{g_et:.2f} hm³/d · {g_et/CFS2HM3:.0f} cfs · {g_et*1e6/86400:.1f} m³/s")
            m3.metric("Dif",f"{md:+.2f} hm³/d ({md/max(rp,.001)*100:+.1f}%)")
        if "mm" in dl:
            st.subheader("Balance hídrico (MCF/día)")
            fig=go.Figure()
            for cn,nm,cl in [("pnx_m","PNX",COL["pnx"]),("npx_m","NPX",COL["npx"]),("mm","Pot Alh",COL["potable"]),("mg","Pot Gat","#2ecc71"),("lm","Fug Alh",COL["fugas"]),("lg","Fug Gat","#f39c12"),("vg","Vert Gat",COL["vertidos"])]:
                if cn in dl: fig.add_trace(go.Bar(x=dl["fecha"],y=dl[cn],name=nm,marker_color=cl))
            fig.update_layout(barmode="stack",yaxis_title="MCF",template="plotly_white",height=420,hovermode="x unified",margin=dict(l=50,r=20,t=20,b=50)); st.plotly_chart(fig,use_container_width=True)
        if "an" in dl:
            st.subheader("Ahorro en esclusas (EE)")
            fig=go.Figure()
            if "ap" in dl: fig.add_trace(go.Bar(x=dl["fecha"],y=dl["ap"],name="PNX",marker_color=COL["pnx"]))
            fig.add_trace(go.Bar(x=dl["fecha"],y=dl["an"],name="NPX",marker_color=COL["npx"]))
            fig.update_layout(barmode="group",yaxis_title="EE",template="plotly_white",height=350,margin=dict(l=50,r=20,t=20,b=50)); st.plotly_chart(fig,use_container_width=True)
        st.download_button("⬇️ CSV",dl.to_csv(index=False).encode("utf-8"),"lakehouse.csv","text/csv")
    else: st.info("Sube **LakeHouse_NEW.xlsx** o colócalo en la carpeta.")

st.markdown("---")
st.markdown("<div style='text-align:center;color:#aab7b8;font-size:0.85rem;'>💧 Demandas de Agua · Canal de Panamá · ACP<br>Creador: JFRodriguez</div>",unsafe_allow_html=True)
