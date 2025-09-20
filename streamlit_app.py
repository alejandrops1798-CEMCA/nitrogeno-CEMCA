# streamlit_app.py (ES)
from __future__ import annotations
import streamlit as st
import pandas as pd
from datetime import date
from db import init_db, seed_tanks, get_all_tanks, get_movements, create_movement

# ----- Inicialización DB -----
init_db()
# Si ya sembraste los 30 tanques, puedes comentar la siguiente línea.
seed_tanks([f"TNK-{i:03d}" for i in range(1, 31)])

st.set_page_config(page_title="Seguimiento de Tanques de Nitrógeno", layout="wide")
st.title("🌡️ Seguimiento de Tanques de Nitrógeno")

# Mapeos UI (ES) -> valores internos (EN)
MOVIMIENTO_UI = ["Despacho", "Recepción"]
MOVIMIENTO_MAP = {"Despacho": "dispatch", "Recepción": "receipt"}

# Pestañas
tabs = st.tabs(["📦 Tanques", "✈️ Nuevo Movimiento", "📜 Bitácora", "📊 Reportes"])

# ---------- Pestaña: Tanques ----------
with tabs[0]:
    st.header("Inventario de tanques")
    tanks = get_all_tanks()
    df = pd.DataFrame([{
        "Serie": t.serial,
        "Estado": "fuera" if t.status == "out" else "en almacén",
        "Último movimiento": t.last_movement_date
    } for t in tanks])
    if not df.empty and "Último movimiento" in df.columns:
        df["Último movimiento"] = pd.to_datetime(df["Último movimiento"])
    st.dataframe(df, use_container_width=True)

# ---------- Pestaña: Nuevo Movimiento ----------
with tabs[1]:
    st.header("Registrar movimiento")

    tanks = get_all_tanks()
    seriales = [t.serial for t in tanks]

    col1, col2 = st.columns(2)
    with col1:
        serial = st.selectbox("Serie del tanque", seriales, placeholder="TNK-001")
        movimiento_ui = st.radio("Tipo de movimiento", MOVIMIENTO_UI, horizontal=True)
        movimiento_tipo = MOVIMIENTO_MAP[movimiento_ui]
        fecha_mov = st.date_input("Fecha del movimiento", date.today(), max_value=date.today())
    with col2:
        proyecto = st.text_input("Proyecto (obligatorio en despacho)", placeholder="Proyecto Atlas")
        ingeniero = st.text_input("Ingeniero responsable (obligatorio en despacho)", placeholder="Jane Doe")

    if st.button("Guardar movimiento", type="primary"):
        try:
            mov = create_movement(
                serial=serial,
                movement_type=movimiento_tipo,
                movement_date=fecha_mov,
                project=proyecto or None,
                engineer=ingeniero or None
            )
            st.success(f"Movimiento registrado: {serial} — {movimiento_ui.lower()} — {fecha_mov.isoformat()}")
        except Exception as e:
            st.error(str(e))

# ---------- Pestaña: Bitácora ----------
with tabs[2]:
    st.header("Bitácora de movimientos")

    tanks = get_all_tanks()
    filtro_serial = st.selectbox("Filtrar por tanque", ["Todos"] + [t.serial for t in tanks])

    movimientos = get_movements(None if filtro_serial == "Todos" else filtro_serial)
    df = pd.DataFrame([{
        "ID": m.id,
        "Serie": m.serial,
        "Tipo": "Despacho" if m.movement_type == "dispatch" else "Recepción",
        "Fecha": m.movement_date,
        "Proyecto": m.project,
        "Ingeniero": m.responsible_engineer,
        "Creado": m.created_at,
    } for m in movimientos])

    if not df.empty:
        for c in ["Fecha", "Creado"]:
            if c in df.columns:
                df[c] = pd.to_datetime(df[c])
    st.dataframe(df, use_container_width=True)

# ---------- Pestaña: Reportes ----------
with tabs[3]:
    st.header("Reportes")

    # Actualmente fuera
    st.subheader("Tanques actualmente fuera")
    tanks = get_all_tanks()
    fuera = [t for t in tanks if t.status == "out"]
    df_out = pd.DataFrame([{
        "Serie": t.serial,
        "Estado": "fuera",
        "Desde": t.last_movement_date
    } for t in fuera])
    if not df_out.empty and "Desde" in df_out.columns:
        df_out["Desde"] = pd.to_datetime(df_out["Desde"])
    st.dataframe(df_out, use_container_width=True)

    # Conteo de movimientos por tanque
    st.subheader("Conteo de movimientos por tanque")
    movimientos = get_movements()
    df_mov = pd.DataFrame([{
        "Serie": m.serial,
        "Tipo": "Despacho" if m.movement_type == "dispatch" else "Recepción"
    } for m in movimientos])
    if not df_mov.empty:
        conteos = df_mov.groupby(["Serie", "Tipo"]).size().unstack(fill_value=0)
        st.dataframe(conteos, use_container_width=True)
    else:
        st.info("Aún no hay movimientos registrados.")
