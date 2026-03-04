import streamlit as st
import pandas as pd
import requests
import re
from bs4 import BeautifulSoup
import time

# ================= CONFIG =================
LOGIN_URL = "http://sigof.distriluz.com.pe/plus/usuario/login"
DASH_URL = "http://sigof.distriluz.com.pe/plus/dashboard/modulos"
ASIGNAR_URL = "http://sigof.distriluz.com.pe/plus/ComrepOrdenrepartos/ajax_guardarlecturistalibro"
CAMBIAR_UNIDAD_URL = "http://sigof.distriluz.com.pe/plus/usuario/ajax_cambiar_sesion"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": LOGIN_URL,
}

# =========================
# UNIDADES SIGOF
# =========================
UNIDADES = {
    "Ayacucho": 76,
    "Huancayo": 77,
    "Huancavelica": 78,
    "Tarma": 79,
    "Selva Central": 80,
    "Pasco": 81,
    "Huánuco": 82,
    "Valle Mantaro": 83,
    "Tingo María": 84
}

# ================= LOGIN REAL SIGOF =================
def login_sigof_real(session, usuario, password):
    credentials = {
        "data[Usuario][usuario]": usuario,
        "data[Usuario][pass]": password
    }

    login_page = session.get(LOGIN_URL, headers=HEADERS)
    soup = BeautifulSoup(login_page.text, "html.parser")
    csrf_token = soup.find("input", {"name": "_csrf_token"})
    if csrf_token:
        credentials["_csrf_token"] = csrf_token["value"]

    response = session.post(LOGIN_URL, data=credentials, headers=HEADERS)

    match = re.search(r"var DEFECTO_IDUUNN\s*=\s*'(\d+)'", response.text)
    if not match:
        return False

    dash = session.get(DASH_URL, headers=HEADERS)
    if "login" in dash.text.lower():
        return False

    return True

# ================= CAMBIO DE UNIDAD =================
def cambiar_unidad_sigof(session, iduunn):
    payload = {
        "idempresa": 4,
        "iduunn": iduunn
    }
    session.post(CAMBIAR_UNIDAD_URL, data=payload, headers=HEADERS)
    test = session.get(DASH_URL, headers=HEADERS)
    return str(iduunn) in test.text

# ================= STREAMLIT =================
def run():

    st.set_page_config(page_title="Lmc Asig Lect", layout="wide")
#st.set_page_config(page_title="Lmc Asig Reparto", layout="wide")

    st.markdown("""
    <h3 style="text-align:center;color:#05DF72">
    🤖 ASIGNACIÓN AUTOMÁTICA v2 DE OTs REPARTO
    </h3>
    """, unsafe_allow_html=True)
    
    # ================= ESTADOS =================
    if "session" not in st.session_state:
        st.session_state.session = None
    if "login_ok" not in st.session_state:
        st.session_state.login_ok = False
    if "unidad_actual" not in st.session_state:
        st.session_state.unidad_actual = None
    
    # ================= LOGIN =================
    if not st.session_state.login_ok:
        usuario = st.text_input(
            "🤵 Humano ingrese su usuario SIGOF",
            placeholder="Usuario SIGOF",
            max_chars=20
        )
        password = st.text_input(
            "🔑 Humano ingrese su contraseña SIGOF",
            placeholder="Contraseña SIGOF",
            type="password",
            max_chars=26
        )
    
        if st.button("🔓 Humano inicie sesión"):
            session = requests.Session()
    
            if not login_sigof_real(session, usuario, password):
                st.error("❌ Humano credenciales incorrectas")
            else:
                dash = session.get(DASH_URL, headers=HEADERS)
                match = re.search(r"var DEFECTO_IDUUNN\s*=\s*'(\d+)'", dash.text)
                if match:
                    st.session_state.unidad_actual = int(match.group(1))
    
                st.session_state.session = session
                st.session_state.login_ok = True
                st.success("✔ Login correcto")
                st.rerun()
    
    # ================= ASIGNACIÓN =================
    if st.session_state.login_ok:
    
        nombre_actual = {v: k for k, v in UNIDADES.items()}.get(
            st.session_state.unidad_actual, "Ayacucho"
        )
    
        unidad = st.selectbox(
            "🏢 Unidad Operativa",
            list(UNIDADES.keys()),
            index=list(UNIDADES.keys()).index(nombre_actual)
        )
    
        if st.button("🔄 Cambiar Unidad"):
            nueva = UNIDADES[unidad]
            if nueva != st.session_state.unidad_actual:
                ok = cambiar_unidad_sigof(st.session_state.session, nueva)
    
                if not ok:
                    st.error("❌ SIGOF rechazó el cambio de unidad")
                    st.stop()
    
                st.session_state.unidad_actual = nueva
                st.success(f"Humano unidad cambiada a {unidad}")
                time.sleep(2)
                st.rerun()
    
        # ----------- SUBIR ARCHIVO REPARTO ------------
        st.markdown("""
            <div style="display: flex; justify-content: left; align-items: left; width: 100%;">
                <h5 style="font-size: clamp(12px, 5vw, 22px); text-align: center; color: #05DF72;">
                    📤 Humano subir archivo de asignaciones reparto:
                </h5>
            </div>
            """, unsafe_allow_html=True)
    
        file = st.file_uploader("Seleccione Asignaciones_Reparto.xlsx", type="xlsx")
    
        if file:
            df = pd.read_excel(file)
        
            columnas = ["repartidor","ciclo","sector","ruta","suministro_inicio","suministro_fin"]
            for c in columnas:
                if c not in df.columns:
                    st.error(f"Falta columna: {c}")
                    st.stop()
        
            # ================= VALIDACIÓN REPARTIDOR =================
            # Verifica que no haya vacíos
            if df["repartidor"].isna().any():
                st.error("❌ Humano verifica tu excel de asignacion el campo del repartidor es incorrecto")
                st.stop()
        
            # Convertir a string para validar caracteres
            df["repartidor"] = df["repartidor"].astype(str).str.strip()
        
            # Validar que solo tenga números
            if not df["repartidor"].str.fullmatch(r"\d+").all():
                st.error("❌ Humano verifica tu excel de asignacion el campo del repartidor es incorrecto")
                st.stop()
    
            if st.button("🚀 Ejecutar Asignación Reparto"):
    
                resultados = []
    
                for _, row in df.iterrows():
                    payload = {
                        "repartidor": int(row["repartidor"]),
                        "ciclo": int(row["ciclo"]),
                        "sector": int(row["sector"]),
                        "ruta": int(row["ruta"]),
                        "negocio": st.session_state.unidad_actual,
                        "suministro_inicio": int(row["suministro_inicio"]),
                        "suministro_fin": int(row["suministro_fin"]),
                    }
    
                    r = st.session_state.session.post(ASIGNAR_URL, data=payload, headers=HEADERS)
    
                    estado = "✔ OK" if r.status_code == 200 else "❌ ERROR"
    
                    resultados.append({
                        "sector": row["sector"],
                        "ruta": row["ruta"],
                        "repartidor": row["repartidor"],
                        "estado": estado
                    })
    
                st.success("🎉 Asignación finalizada")
                st.dataframe(pd.DataFrame(resultados))
    
        # 🔒 BOTÓN PARA CERRAR SESIÓN
        if st.session_state.session is not None:
            if st.button("🔒 Cerrar sesión"):
                st.session_state.session = None
                st.session_state.login_ok = False   # 👈 ESTA LÍNEA FALTABA
                st.session_state.unidad_actual = None
                st.rerun()
if __name__ == "__main__":
    run()
