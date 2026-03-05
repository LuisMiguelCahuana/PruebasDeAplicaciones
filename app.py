import streamlit as st
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
from io import BytesIO
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from openpyxl import load_workbook
from openpyxl.styles import PatternFill, Font, Border, Side

# ================= CONFIG =================
login_url = "http://sigof.distriluz.com.pe/plus/usuario/login"
FILE_ID = "1td-2WGFN0FUlas0Vx8yYUSb7EZc7MbGWjHDtJYhEY-0"

headers = {
    "User-Agent": "Mozilla/5.0",
    "Referer": login_url
}

CAMBIAR_UNIDAD_URL = "http://sigof.distriluz.com.pe/plus/usuario/ajax_cambiar_sesion"

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

def login_and_get_defecto_iduunn(session, usuario, password):
    credentials = {
        "data[Usuario][usuario]": usuario,
        "data[Usuario][pass]": password
    }

    login_page = session.get(login_url, headers=headers)
    soup = BeautifulSoup(login_page.text, "html.parser")

    csrf_token = soup.find("input", {"name": "_csrf_token"})
    if csrf_token:
        credentials["_csrf_token"] = csrf_token["value"]

    response = session.post(login_url, data=credentials, headers=headers)

    match_iduunn = re.search(r"var DEFECTO_IDUUNN\s*=\s*'(\d+)'", response.text)
    if not match_iduunn:
        return None, False

    defecto_iduunn = int(match_iduunn.group(1))

    dashboard_response = session.get(
        "http://sigof.distriluz.com.pe/plus/dashboard/modulos",
        headers=headers
    )

    if "login" in dashboard_response.text:
        return None, False

    return defecto_iduunn, True


# ================= CAMBIAR UNIDAD =================
def cambiar_unidad_sigof(session, iduunn):

    payload = {
        "idempresa": 4,
        "iduunn": iduunn
    }

    session.post(CAMBIAR_UNIDAD_URL, data=payload, headers=headers)

    test = session.get(
        "http://sigof.distriluz.com.pe/plus/dashboard/modulos",
        headers=headers
    )

    return str(iduunn) in test.text


@st.cache_data(ttl=600)
def download_excel_from_drive(file_id):
    url = f"https://docs.google.com/spreadsheets/d/{file_id}/export?format=xlsx"
    response = requests.get(url)

    if response.status_code == 200:
        return pd.read_excel(BytesIO(response.content))

    return None


#@st.cache_data(ttl=600)
def descargar_archivo_paralelo(session, codigo, periodo="0"):
    zona = ZoneInfo("America/Lima")
    hoy = datetime.now(zona).strftime("%Y-%m-%d")

    url = (
        f"http://sigof.distriluz.com.pe/plus/Reportes/ajax_ordenes_historico_xls/"
        f"U/{hoy}/{hoy}/0/{codigo}/0/0/0/0/0/0/0/0/9/{periodo}"
    )

    try:
        response = session.get(url, headers=headers)

        if response.headers.get("Content-Type") == \
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":

            df = pd.read_excel(
                BytesIO(response.content),
                engine="openpyxl",
                dtype={
                    "suministro": "string",
                    "lectura": "float64",
                    "consumo": "float64"
                }
            )
            df["PERIODO_DESCARGADO"] = periodo
            return df

    except Exception:
        return None

    return None


def run():
    st.set_page_config(page_title="Lmc Refacturados", layout="wide")

    st.markdown("""
        <div style="display: flex; justify-content: center; align-items: center; width: 100%;">
            <h1 style="font-size: clamp(18px, 5vw, 35px); text-align: center; color: #0078D7;">
                🤖 REPORTE DE SUMINISTROS REFACTURADOS v2 (999999)
            </h1>
        </div>
    """, unsafe_allow_html=True)

    if "session" not in st.session_state:
        st.session_state.session = None

    if "defecto_iduunn" not in st.session_state:
        st.session_state.defecto_iduunn = None

    if "ciclos_disponibles" not in st.session_state:
        st.session_state.ciclos_disponibles = {}

    # ================= LOGIN =================
    if st.session_state.session is None:

        usuario = st.text_input(
            "🤵 Humano ingrese su usuario sigof",
            placeholder="Usuario sigof",
            max_chars=20
        )

        password = st.text_input(
            "🔑 Humano ingrese su contraseña sigof",
            placeholder="Contraseña sigof",
            type="password",
            max_chars=26
        )

        if st.button("🔓 Humano inicie sesión"):

            if not usuario or not password:
                st.warning("⚠️ Humano ingrese usuario y contraseña.")
            else:
                session = requests.Session()
                defecto_iduunn, login_ok = login_and_get_defecto_iduunn(
                    session, usuario, password
                )

                if not login_ok:
                    st.error("❌ Humano tu usuario o contraseña incorrectos.")
                else:
                    st.session_state.session = session
                    st.session_state.defecto_iduunn = defecto_iduunn

                    df_ciclos = download_excel_from_drive(FILE_ID)

                    if df_ciclos is None:
                        st.error("❌ Humano no se pudo descargar el Excel de ciclos.")
                        return

                    df_ciclos['id_unidad'] = (
                        pd.to_numeric(df_ciclos['id_unidad'], errors='coerce')
                        .fillna(-1)
                        .astype(int)
                    )

                    df_ciclos = df_ciclos[
                        df_ciclos['id_unidad'] == defecto_iduunn
                    ]

                    if df_ciclos.empty:
                        st.error("⚠️ Humano no tienes ciclos asignados.")
                        return

                    ciclos_dict = {
                        f"{r['Id_ciclo']} {r['nombre_ciclo']}": str(r['Id_ciclo'])
                        for _, r in df_ciclos.iterrows()
                    }

                    st.session_state.ciclos_disponibles = ciclos_dict
                    st.rerun()
    # ================= CAMBIO DE UNIDAD =================
    if st.session_state.session is not None:    
        nombre_actual = {v: k for k, v in UNIDADES.items()}.get(
            st.session_state.defecto_iduunn, "Ayacucho"
        )    
        unidad = st.selectbox(
            "🏢 Humano elija su unidad empresarial o operativa",
            list(UNIDADES.keys()),
            index=list(UNIDADES.keys()).index(nombre_actual)
        )    
        if st.button("🔄 Cambiar Unidad"):    
            nueva = UNIDADES[unidad]    
            if nueva != st.session_state.defecto_iduunn:    
                ok = cambiar_unidad_sigof(st.session_state.session, nueva)    
                if not ok:
                    st.error("❌ SIGOF rechazó el cambio de unidad")
                    st.stop()    
                st.session_state.defecto_iduunn = nueva    
                df_ciclos = download_excel_from_drive(FILE_ID)    
                df_ciclos['id_unidad'] = (
                    pd.to_numeric(df_ciclos['id_unidad'], errors='coerce')
                    .fillna(-1)
                    .astype(int)
                )    
                df_ciclos = df_ciclos[
                    df_ciclos['id_unidad'] == nueva
                ]    
                ciclos_dict = {
                    f"{r['Id_ciclo']} {r['nombre_ciclo']}": str(r['Id_ciclo'])
                    for _, r in df_ciclos.iterrows()
                }    
                st.session_state.ciclos_disponibles = ciclos_dict    
                st.success(f"Humano unidad cambiada a {unidad}")    
                time.sleep(2)    
                st.rerun()
    # ================= DESCARGA =================
    if st.session_state.ciclos_disponibles:

        opciones = list(st.session_state.ciclos_disponibles.keys())
        seleccionar_todos = st.checkbox(
            "Humano con esta opción puedes seleccionar todos los ciclos"
        )

        col1, col2 = st.columns([3, 0.4])

        with col1:
            if seleccionar_todos:
                seleccionados = st.multiselect(
                    "Humano elija sus ciclos:",
                    options=opciones,
                    default=opciones
                )
            else:
                seleccionados = st.multiselect(
                    "Humano elija sus ciclos:",
                    options=opciones
                )

        with col2:
            periodo_anterior = st.text_input(
                "Periodo Ant👉(Ej: 202601)",
                placeholder="Ej: 202601",
                max_chars=6
            )

        if periodo_anterior and (
                not periodo_anterior.isdigit() or len(periodo_anterior) != 6):
            st.error("⚠️ Debe ser exactamente 6 dígitos numéricos (ej: 202511)")
            periodo_anterior = ""

        if st.button("Humano Procesar Suministros Refacturado"):

            if not seleccionados:
                st.warning("⚠️ Humano seleccione al menos un ciclo.")
                return

            if not periodo_anterior:
                st.warning("⚠️ Humano debes ingresar el período anterior (6 dígitos).")
                return

            periodos = [("0", "Actual"), (periodo_anterior, "Anterior")]
            df_total = []
            session = st.session_state.session
            
            max_hilos = min(8, len(seleccionados) * 2)
            
            tareas = []   # 🔥 AGREGAR ESTA LÍNEA
            
            with ThreadPoolExecutor(max_workers=max_hilos) as executor:

                for nombre_concatenado in seleccionados:
                    codigo = st.session_state.ciclos_disponibles[nombre_concatenado]

                    for periodo_valor, _ in periodos:
                        tareas.append(
                            executor.submit(
                                descargar_archivo_paralelo,
                                session,
                                codigo,
                                periodo_valor
                            )
                        )

                for future in as_completed(tareas):
                    df = future.result()
                    if df is not None:
                        df_total.append(df)

            if not df_total:
                st.info("ℹ️ Humano no se descargaron datos.")
                return

            df_final = pd.concat(df_total, ignore_index=True, copy=False)
            del df_total

            # ================= CÁLCULO REFACCTURADOS =================
            df_actual = df_final[df_final["PERIODO_DESCARGADO"] == "0"].copy()
            df_anterior = df_final[
                df_final["PERIODO_DESCARGADO"] == periodo_anterior
            ].copy()

            df_anterior = df_anterior[df_anterior["obs"] != 30]
            df_actual = df_actual[df_actual["consumo"] > 9999]
            df_actual = df_actual[df_actual["obs"] != 30]

            # 🔥 AGREGAR AQUÍ
            df_actual["suministro"] = df_actual["suministro"].astype("string")
            df_anterior["suministro"] = df_anterior["suministro"].astype("string")

            df_anterior_small = df_anterior[["suministro", "lectura"]]

            df_comparacion = pd.merge(
                df_actual,
                df_anterior_small,
                on="suministro",
                how="inner",
                suffixes=("_actual", "_anterior"),
                sort=False
            )

            df_comparacion["Diferencia Lectura"] = (
                df_comparacion["lectura_actual"]
                - df_comparacion["lectura_anterior"]
            )

            df_refacturados = df_comparacion[
                df_comparacion["Diferencia Lectura"] < 0
            ].copy()

            # ================= PREPARAR ARCHIVO =================
            df_descarga = pd.DataFrame({
                "Uu.ee - Uu.oo":
                    df_refacturados["id"]
                    if "id" in df_refacturados.columns else None,
                "Mes Refacturado": df_refacturados["pfactura"],
                "Suministro": df_refacturados["suministro"],
                "Medidor": df_refacturados["medidor"],
                "Lecturista": df_refacturados["lecturista"],
                "Ciclo": df_refacturados["ciclo"],
                "Sector": df_refacturados["sector"],
                "Ruta": df_refacturados["ruta"],
                "Consumo": df_refacturados["consumo"],
                "Diferencia Lectura":
                    df_refacturados["Diferencia Lectura"]
            })

            # ================= EXPORTAR =================
            output = BytesIO()

            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                df_descarga.to_excel(
                    writer,
                    index=False,
                    sheet_name="SuministrosRefacturados"
                )

            output.seek(0)

            st.download_button(
                label="📁 Humano Descargar Suministros Refacturados",
                data=output,
                #file_name="LMC_Suministros_Refacturados_v2.xlsx",
                file_name=f"LMC_Suministros_Refacturados_v2_{unidad}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    # ================= LOGOUT =================
    if st.session_state.session is not None:
        if st.button("🔒 Cerrar sesión"):
            st.session_state.session = None
            st.session_state.defecto_iduunn = None
            st.session_state.ciclos_disponibles = {}
            st.rerun()

    # ================= FOOTER =================
    st.markdown("""
        <style>
        .footer {
            position: fixed;
            bottom: 0;
            width: 100%;
            background-color: white;
            padding: 10px 8px;
            text-align: center;
            font-size: 14px;
            color: gray;
            z-index: 9999;
            border-top: 1px solid #ddd;
        }
        </style>
        <div class="footer">
            Desarrollado por Luis M. Cahuana F.
        </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    run()
