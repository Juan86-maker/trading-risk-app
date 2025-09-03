import streamlit as st
import gspread
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# --- Autenticación con Google Sheets ---
scope = ["https://spreadsheets.google.com/feeds",
         "https://www.googleapis.com/auth/drive"]

creds = ServiceAccountCredentials.from_json_keyfile_dict(
    st.secrets["gcp_service_account"], scope
)
client = gspread.authorize(creds)

# --- IDs de hojas ---
SPREADSHEET_ID = st.secrets["default"]["SPREADSHEET_ID"]
WS_OPERACIONES = "Operaciones"
WS_HISTORIAL = "Historial"
WS_CONFIG = "Config"

worksheet_op = client.open_by_key(SPREADSHEET_ID).worksheet(WS_OPERACIONES)
worksheet_hist = client.open_by_key(SPREADSHEET_ID).worksheet(WS_HISTORIAL)
worksheet_cfg = client.open_by_key(SPREADSHEET_ID).worksheet(WS_CONFIG)

# --- Leer parámetros de Config ---
cfg_data = worksheet_cfg.get_all_records()
df_cfg = pd.DataFrame(cfg_data)

LOT_SIZES = dict(zip(df_cfg["Symbol"], df_cfg["LotSize"]))
MARGIN_PCTS = dict(
    zip(df_cfg["Symbol"], [float(str(x).replace("%", "")) / 100 for x in df_cfg["MarginPct"]])
)

# --- Funciones de cálculo ---
def calcular_metricas(simbolo, lote, precio, sl, tp):
    lot_size = LOT_SIZES.get(simbolo, 1)
    margin_pct = MARGIN_PCTS.get(simbolo, 0.01)

    margen = margin_pct * lote * precio * lot_size
    riesgo = lote * abs(precio - sl) * lot_size
    beneficio = lote * abs(tp - precio) * lot_size
    rr = beneficio / riesgo if riesgo != 0 else 0

    return margen, riesgo, beneficio, rr

# --- Interfaz Streamlit ---
st.title("📊 Calculadora de Riesgo de Trading")

# Formulario de entrada
with st.form("registro_operacion"):
    simbolo = st.selectbox("Símbolo", options=df_cfg["Symbol"].tolist())
    tipo = st.selectbox("Tipo", ["Compra", "Venta"])
    lote = st.number_input("Lote", min_value=0.01, value=0.1, step=0.01)
    precio = st.number_input("Precio", min_value=0.0, value=0.0, step=0.01)
    sl = st.number_input("Stop Loss", min_value=0.0, value=0.0, step=0.01)
    tp = st.number_input("Take Profit", min_value=0.0, value=0.0, step=0.01)

    margen, riesgo, beneficio, rr = calcular_metricas(simbolo, lote, precio, sl, tp)

    st.markdown(f"**Margen [$]:** {margen:.2f}")
    st.markdown(f"**Riesgo de pérdida [$]:** {riesgo:.2f}")
    st.markdown(f"**Posible beneficio [$]:** {beneficio:.2f}")
    st.markdown(f"**Relación riesgo/beneficio:** {rr:.2f} : 1")

    registrar = st.form_submit_button("Registrar Suceso")

if registrar:
    # Preguntas adicionales
    orden = st.selectbox("¿Orden pendiente o a mercado?", ["Mercado", "Pendiente"])
    comentario = st.text_area("Comentario de justificación (opcional)")
    aceptar = st.button("Aceptar")

    if aceptar:
        nueva_fila = [
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            simbolo, tipo, lote, precio, sl, tp,
            margen, riesgo, beneficio, f"{rr:.2f}:1",
            orden, comentario
        ]
        worksheet_op.append_row(nueva_fila)
        st.success("✅ Operación registrada correctamente en Google Sheets.")

# --- Mostrar lista de operaciones ---
st.subheader("📋 Lista de Operaciones")

ops = worksheet_op.get_all_records()
df_ops = pd.DataFrame(ops)

if not df_ops.empty:
    def color_row(row):
        return ['background-color: lightgreen' if row["Orden"] == "Mercado" else 'background-color: lightblue'] * len(row)

    st.dataframe(df_ops.style.apply(color_row, axis=1))
else:
    st.info("No hay operaciones registradas.")

# --- Botones de acciones (esqueleto) ---
st.subheader("⚙️ Acciones sobre operaciones")
col1, col2, col3 = st.columns(3)
with col1:
    st.button("Eliminar operación pendiente")
with col2:
    st.button("Cierre automático (TP o SL)")
with col3:
    st.button("Cierre manual")
