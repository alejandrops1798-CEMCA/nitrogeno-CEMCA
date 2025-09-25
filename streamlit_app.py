# streamlit_app.py (ES, con Login y Reportes público)
from __future__ import annotations
import streamlit as st
import pandas as pd
from datetime import date
from db import (
    init_db,
    seed_tanks,
    get_all_tanks,
    get_movements,
    create_movement,
    summary_current_out_by_engineer,
)
import os

# Mostrar qué DB se usa
db_url = os.getenv("DATABASE_URL", "sqlite:///tanks.db")
st.caption("🔗 DB: Neon Postgres" if db_url.startswith("postgresql") else "💾 DB: SQLite")

# ========= Config =========
VALID_USER = "inspectordespachos@grupocemca.com"
VALID_PASS = "12345"

MOVIMIENTO_UI = ["Despacho", "Recepción"]
MOVIMIENTO_MAP = {"Despacho": "dispatch", "Recepción": "receipt"}

INGENIEROS = [
    "Victor de Leon", "Pablo Castillo", "Roberto de Jesus", "Rayner Drullard",
    "Lenny Ramirez", "Fausto Huerta", "Alfredo Matos", "Luilly Lima",
    "Fantino Suarez", "Jhonatan Perez", "Sarah Bonilla", "Julian Barcelo", "Otro",
]

SERIALES_PERSONALIZADOS = [
    "AIRLIQUIDE-1","AIRLIQUIDE-2","AIRLIQUIDE-3","AIRLIQUIDE-4","AIRLIQUIDE-5",
    "GC-TAZUL-01","GC-TAZUL-02","GC-TAZUL-03","GC-TAZUL-04","GC-TAZUL-05",
    "GC-TAZUL-06","GC-TAZUL-07","GC-TAZUL-08","GC-TAZUL-09","GC-TAZUL-10",
    "GC-TAZUL-11","GC-TAZUL-12","GC-TAZUL-13","GC-TAZUL-14","GC-TAZUL-15",
    "GC-TAZUL-16","GC-TAZUL-17","GC-TAZUL-18","GC-TAZUL-19","GC-TAZUL-20",
    "GC-TORIGINAL-01","GC-TORIGINAL-02","GC-TORIGINAL-03","GC-TORIGINAL-04","GC-TORIGINAL-05",
]

# ========= Setup página/DB =========
st.set_page_config(page_title="Seguimiento de Tanques de Nitrógeno", layout="wide")
st.title("🌡️ Seguimiento de Tanques de Nitrógeno")

init_db()
# (Si no quieres re-sembrar en cada arranque, comenta esta línea.)
seed_tanks(SERIALES_PERSONALIZADOS)

# ========= Estado de sesión (auth) =========
if "auth_ok" not in st.session_state:
    st.session_state["auth_ok"] = False
if "auth_user" not in st.session_state:
    st.session_state["auth_user"] = None

def do_login(user: str, pwd: str) -> bool:
    return (user.strip().lower() == VALID_USER) and (pwd == VALID_PASS)

def logout():
    st.session_state["auth_ok"] = False
    st.session_state["auth_user"] = None
    st.rerun()

# ========= UI de Login (si no autenticado) =========
def login_box():
    with st.sidebar:
        st.subheader("🔐 Acceso")
        u = st.text_input("Usuario", placeholder="correo@empresa.com")
        p = st.text_input("Contraseña", type="password")
        if st.button("Iniciar sesión"):
            if do_login(u, p):
                st.session_state["auth_ok"] = True
                st.session_state["auth_user"] = u.strip().lower()
                st.success("Acceso concedido.")
                st.rerun()
            else:
                st.error("Credenciales inválidas.")

# ========= Contenido de Reportes (siempre visible) =========
def render_reportes():
    st.header("Reportes")

    # Actualmente fuera
    st.subheader("Tanques actualmente fuera")
    tanks = get_all_tanks()
    fuera = [t for t in tanks if t.status == "out"]
    df_out = pd.DataFrame(
        [{"Serie": t.serial, "Estado": "fuera", "Desde": t.last_movement_date} for t in fuera]
    )
    if not df_out.empty and "Desde" in df_out.columns:
        df_out["Desde"] = pd.to_datetime(df_out["Desde"])
    st.dataframe(df_out, use_container_width=True)

    # Resumen por Ingeniero
    st.subheader("Resumen por Ingeniero (tanques actualmente fuera)")
    resumen = summary_current_out_by_engineer()
    df_sum = pd.DataFrame(resumen)
    if df_sum.empty:
        st.info("No hay tanques fuera actualmente.")
    else:
        df_sum = df_sum.rename(columns={"responsible_engineer": "Ingeniero", "count": "Tanques fuera"})
        st.dataframe(df_sum, use_container_width=True)

# ========= App (gates por login) =========
if not st.session_state["auth_ok"]:
    # Público: solo Reportes + caja de Login
    login_box()
    tabs = st.tabs(["📊 Reportes", "🔐 Acceso"])
    with tabs[0]:
        render_reportes()
    with tabs[1]:
        st.write("Use la barra lateral para iniciar sesión y acceder al resto del sistema.")
else:
    # Autenticado: todas las pestañas
    with st.sidebar:
        st.caption(f"Conectado como: **{st.session_state['auth_user']}**")
        if st.button("Cerrar sesión"):
            logout()

    tabs = st.tabs(["📦 Tanques", "✈️ Nuevo Movimiento", "📜 Bitácora", "📊 Reportes"])

    # ----- Tanques -----
    with tabs[0]:
        st.header("Inventario de tanques")
        tanks = get_all_tanks()
        df_tanks = pd.DataFrame(
            [{
                "Serie": t.serial,
                "Estado": "fuera" if t.status == "out" else "en almacén",
                "Último movimiento": t.last_movement_date
            } for t in tanks]
        )
        if not df_tanks.empty and "Último movimiento" in df_tanks.columns:
            df_tanks["Último movimiento"] = pd.to_datetime(df_tanks["Último movimiento"])
        st.dataframe(df_tanks, use_container_width=True)

    # ----- Nuevo Movimiento -----
    with tabs[1]:
        st.header("Registrar movimiento")

        tanks = get_all_tanks()
        seriales = [t.serial for t in tanks] or SERIALES_PERSONALIZADOS

        col1, col2 = st.columns(2)
        with col1:
            serial = st.selectbox("Serie del tanque", seriales, placeholder="Selecciona un tanque")
            movimiento_ui = st.radio("Tipo de movimiento", MOVIMIENTO_UI, horizontal=True)
            movimiento_tipo = MOVIMIENTO_MAP[movimiento_ui]
            fecha_mov = st.date_input("Fecha del movimiento", date.today(), max_value=date.today())
            proyecto = st.text_input("Proyecto (obligatorio en despacho)", placeholder="Proyecto Atlas")
            smt = st.text_input("Número de SMT (obligatorio, 5 dígitos)", placeholder="12345")
        with col2:
            ing_sel = st.selectbox("Ingeniero responsable (obligatorio en despacho)", INGENIEROS)
            ing_otro = ""
            if ing_sel == "Otro":
                ing_otro = st.text_input("Especifica otro Ingeniero responsable")
            contratista = st.text_input("Contratista responsable (obligatorio en despacho)", placeholder="ACME Maintenance")

        def _smt_valido(s: str) -> bool:
            s = (s or "").strip()
            return s.isdigit() and len(s) == 5

        def _ingeniero_final() -> str | None:
            if ing_sel == "Otro":
                return (ing_otro or "").strip() or None
            return ing_sel

        if st.button("Guardar movimiento", type="primary"):
            if not serial:
                st.error("Selecciona un tanque.")
            elif not _smt_valido(smt):
                st.error("El Número de SMT es obligatorio y debe tener exactamente 5 dígitos.")
            elif movimiento_tipo == "dispatch" and (not proyecto.strip() or not _ingeniero_final() or not contratista.strip()):
                st.error("Despacho requiere Proyecto, Ingeniero responsable y Contratista responsable.")
            else:
                try:
                    mov = create_movement(
                        serial=serial,
                        movement_type=movimiento_tipo,
                        movement_date=fecha_mov,
                        project=proyecto or None,
                        engineer=_ingeniero_final(),
                        contractor=contratista or None,
                        smt_number=smt.strip(),
                    )
                    st.success(f"Movimiento registrado: {serial} — {movimiento_ui.lower()} — {fecha_mov.isoformat()}")
                    # ✅ Forzar refresco de todas las tablas/reportes
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

    # ----- Bitácora -----
    with tabs[2]:
        st.header("Bitácora de movimientos")

        tanks = get_all_tanks()
        filtro_serial = st.selectbox("Filtrar por tanque", ["Todos"] + [t.serial for t in tanks])

        movimientos = get_movements(None if filtro_serial == "Todos" else filtro_serial)
        df_log = pd.DataFrame(
            [{
                "ID": m.id,
                "Serie": m.serial,
                "Tipo": "Despacho" if m.movement_type == "dispatch" else "Recepción",
                "Fecha": m.movement_date,
                "Proyecto": m.project,
                "Ingeniero": m.responsible_engineer,
                "Contratista": getattr(m, "responsible_contractor", None),
                "SMT": getattr(m, "smt_number", None),
                "Creado": m.created_at,
            } for m in movimientos]
        )
        if not df_log.empty:
            for c in ["Fecha", "Creado"]:
                if c in df_log.columns:
                    df_log[c] = pd.to_datetime(df_log[c])
        st.dataframe(df_log, use_container_width=True, height=420)

    # ----- Reportes -----
    with tabs[3]:
        render_reportes()
