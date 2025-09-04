import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# ==============================
# 🔑 Conexión con Google Sheets
# ==============================
scope = ["https://www.googleapis.com/auth/spreadsheets"]
creds = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"], scopes=scope
)
client = gspread.authorize(creds)

SHEET_ID = st.secrets[default]["sheet_id"]
sh = client.open_by_key(SHEET_ID)

ws_ops = sh.worksheet("Operaciones")
ws_hist = sh.worksheet("Historial")
ws_cfg = sh.worksheet("Config")

# ==============================
# 📊 Configuración desde hoja
# ==============================
df_cfg = pd.DataFrame(ws_cfg.get_all_records())

def limpiar_margin(valor):
    if valor is None or str(valor).strip() == "":
        return 0.0
    v = str(valor).replace("%", "").replace(",", ".").strip()
    try:
        return float(v) / 100
    except:
        return 0.0

MARGIN_PCTS = dict(zip(df_cfg["Symbol"], [limpiar_margin(x) for x in df_cfg["MarginPct"]]))

# ==============================
# ⚙️ Inicialización de estados
# ==============================
for key, default in {
    "lote": 0.0,
    "precio": 0.0,
    "sl": 0.0,
    "tp": 0.0,
    "orden_tipo": "Mercado",
    "justificacion": "",
    "show_extra_fields": False,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# ==============================
# 🖥️ Interfaz
# ==============================
st.title("📈 Trading Risk App")

# ---- Formulario de parámetros ----
st.header("➕ Nuevo Suceso")

col1, col2 = st.columns(2)
with col1:
    symbol = st.selectbox("Símbolo", list(MARGIN_PCTS.keys()))
    lote = st.number_input("Lote", min_value=0.0, step=0.01, key="lote")
    precio = st.number_input("Precio de entrada", min_value=0.0, step=0.0001, key="precio")

with col2:
    sl = st.number_input("Stop Loss", min_value=0.0, step=0.0001, key="sl")
    tp = st.number_input("Take Profit", min_value=0.0, step=0.0001, key="tp")
    tipo = st.radio("Tipo de operación", ["Compra", "Venta"])

# ---- Cálculos dinámicos ----
margen = riesgo = beneficio = rb = None
if precio and lote:
    margen = lote * precio * MARGIN_PCTS.get(symbol, 0)

if sl and precio and lote:
    if tipo == "Compra":
        riesgo = lote * (precio - sl)
    else:
        riesgo = lote * (sl - precio)
    if riesgo < 0:
        st.warning("⚠️ Stop Loss incongruente con el tipo de operación.")

if tp and precio and lote:
    if tipo == "Compra":
        beneficio = lote * (tp - precio)
    else:
        beneficio = lote * (precio - tp)
    if beneficio < 0:
        st.warning("⚠️ Take Profit incongruente con el tipo de operación.")

if riesgo and beneficio and riesgo > 0:
    rb = beneficio / riesgo

# ---- Mostrar resultados parciales ----
st.subheader("📊 Resultados de la Calculadora")
if margen is not None:
    st.write(f"**Margen estimado:** {margen:.2f} $")
if riesgo is not None:
    st.write(f"**Riesgo estimado:** {riesgo:.2f} $")
if beneficio is not None:
    st.write(f"**Beneficio estimado:** {beneficio:.2f} $")
if rb is not None:
    st.write(f"**R/B:** {rb:.2f}:1")

# ---- Panel de detalles adicionales ----
with st.expander("Detalles de la orden", expanded=st.session_state["show_extra_fields"]):
    st.session_state["orden_tipo"] = st.radio("Tipo de orden", ["Mercado", "Pendiente"], key="orden_tipo")
    st.session_state["justificacion"] = st.text_area("Justificación", key="justificacion")

# ---- Botón para guardar ----
if st.button("✅ Registrar Suceso"):
    ws_ops.append_row(
        [
            datetime.now().strftime("%Y-%m-%d"),
            datetime.now().strftime("%H:%M:%S"),
            symbol,
            lote,
            precio,
            sl,
            tp,
            tipo,
            st.session_state["orden_tipo"],
            st.session_state["justificacion"],
            f"{margen:.2f}" if margen else "",
            f"{riesgo:.2f}" if riesgo else "",
            f"{beneficio:.2f}" if beneficio else "",
            f"{(beneficio / riesgo):.2f}:1" if (riesgo and beneficio and riesgo > 0) else "",
        ]
    )
    st.success("✅ Suceso registrado correctamente.")

    # Reset de algunos campos
    st.session_state["lote"] = 0.0
    st.session_state["precio"] = 0.0
    st.session_state["sl"] = 0.0
    st.session_state["tp"] = 0.0
    st.session_state["justificacion"] = ""
    st.session_state["orden_tipo"] = "Mercado"
    st.session_state["show_extra_fields"] = False

    st.experimental_rerun()

# ==============================
# 📋 Lista de sucesos
# ==============================
st.header("📋 Lista de Sucesos")

try:
    registros = ws_ops.get_all_records()
    df_ops = pd.DataFrame(registros)

    if not df_ops.empty:
        def highlight_row(row):
            if "Orden" in df_ops.columns:
                if row["Orden"] == "Pendiente":
                    return ["background-color: #fff3cd"] * len(row)  # amarillo
                else:
                    return ["background-color: #d4edda"] * len(row)  # verde
            return [""] * len(row)

        st.dataframe(
            df_ops.style.apply(highlight_row, axis=1),
            use_container_width=True,
            height=400,
        )
    else:
        st.info("Aún no hay operaciones registradas.")

except Exception as e:
    st.error(f"No se pudo leer la hoja de sucesos: {e}")
