import streamlit as st
import pandas as pd
import datetime

# ================================
# Helper para convertir coma/punto
# ================================
def parse_float(value: str) -> float:
    if not value:
        return None
    try:
        return float(value.replace(",", "."))
    except ValueError:
        return None

# ================================
# Inicialización de session_state
# ================================
if "sucesos" not in st.session_state:
    st.session_state["sucesos"] = []

if "mostrar_form" not in st.session_state:
    st.session_state["mostrar_form"] = False

if "orden_tipo" not in st.session_state:
    st.session_state["orden_tipo"] = "Mercado"

if "justificacion" not in st.session_state:
    st.session_state["justificacion"] = ""

# ================================
# Panel principal
# ================================
st.title("Gestor de Riesgo y Registro de Sucesos")

# Formulario principal
with st.form("registro_form"):
    st.subheader("Registrar operación")

    # Campos numéricos (aceptan , o .)
    lote = parse_float(st.text_input("Lote", value=""))
    precio = parse_float(st.text_input("Precio de entrada", value=""))
    sl = parse_float(st.text_input("Stop Loss", value=""))
    tp = parse_float(st.text_input("Take Profit", value=""))

    submitted = st.form_submit_button("Aceptar y Guardar")

    if submitted:
        # Calcular riesgo/beneficio (si hay valores válidos)
        riesgo = abs(precio - sl) if (precio and sl) else None
        beneficio = abs(tp - precio) if (precio and tp) else None

        # Guardar en sucesos
        st.session_state["sucesos"].append({
            "Fecha": datetime.date.today().strftime("%Y-%m-%d"),
            "Hora": datetime.datetime.now().strftime("%H:%M:%S"),
            "Tipo": st.session_state["orden_tipo"],
            "Justificación": st.session_state["justificacion"],
            "Lote": lote,
            "Precio": precio,
            "SL": sl,
            "TP": tp,
            "Riesgo": riesgo,
            "Beneficio": beneficio,
            "R/B": f"{(beneficio / riesgo):.2f}:1" if (riesgo and beneficio and riesgo > 0) else ""
        })

        # Reset de campos del formulario
        st.session_state["mostrar_form"] = False
        st.session_state["justificacion"] = ""
        st.session_state["orden_tipo"] = "Mercado"
        st.rerun()

# ================================
# Panel de preguntas extra
# ================================
if st.session_state["mostrar_form"]:
    st.subheader("Detalles adicionales")

    st.session_state["orden_tipo"] = st.radio(
        "Tipo de orden", ["Mercado", "Pendiente"], index=0
    )

    st.session_state["justificacion"] = st.text_area(
        "Justificación de la operación",
        value=st.session_state["justificacion"]
    )

else:
    if st.button("Añadir detalles (Pendiente/Mercado y Justificación)"):
        st.session_state["mostrar_form"] = True
        st.rerun()

# ================================
# Mostrar sucesos registrados
# ================================
st.subheader("Lista de sucesos")

if st.session_state["sucesos"]:
    df = pd.DataFrame(st.session_state["sucesos"])
    st.dataframe(df, use_container_width=True)
else:
    st.info("Aún no hay sucesos registrados.")
