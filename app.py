import streamlit as st
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
from datetime import datetime

st.set_page_config(page_title="Trading Risk App", layout="wide")

# ========= Conexión Google Sheets =========
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
creds = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"], scopes=SCOPES
)
client = gspread.authorize(creds)

SPREADSHEET_ID = st.secrets["default"]["SPREADSHEET_ID"]
WS_OPERACIONES = "Operaciones"
WS_HISTORIAL = "Historial"
WS_CONFIG = "Config"

sheet = client.open_by_key(SPREADSHEET_ID)
ws_ops = sheet.worksheet(WS_OPERACIONES)
ws_hist = sheet.worksheet(WS_HISTORIAL)
ws_cfg = sheet.worksheet(WS_CONFIG)

# ========= Config desde hoja Config =========
cfg_records = ws_cfg.get_all_records()
df_cfg = pd.DataFrame(cfg_records)

# Validaciones mínimas
required_cols = {"Symbol", "LotSize", "MarginPct"}
if not required_cols.issubset(set(df_cfg.columns)):
    st.error(
        "La hoja 'Config' debe tener las columnas: Symbol | LotSize | MarginPct. "
        f"Columnas actuales: {list(df_cfg.columns)}"
    )
    st.stop()

def limpiar_margin(v):
    if v is None or str(v).strip() == "":
        return 0.0
    s = str(v).replace("%", "").replace(",", ".").strip()
    try:
        return float(s) / 100.0
    except Exception:
        return 0.0

# Diccionarios dinámicos
LOT_SIZES = dict(zip(df_cfg["Symbol"], df_cfg["LotSize"]))
MARGIN_PCTS = dict(zip(df_cfg["Symbol"], [limpiar_margin(x) for x in df_cfg["MarginPct"]]))

# ========= Funciones de cálculo =========
def calc_margen(simbolo, lote, precio):
    lot_size = float(LOT_SIZES.get(simbolo, 1) or 1)
    margin_pct = float(MARGIN_PCTS.get(simbolo, 0.0) or 0.0)
    if lote and precio:
        return margin_pct * float(lote) * float(precio) * lot_size
    return None

def calc_riesgo(simbolo, lote, precio, sl):
    lot_size = float(LOT_SIZES.get(simbolo, 1) or 1)
    if lote and precio and sl:
        return float(lote) * abs(float(precio) - float(sl)) * lot_size
    return None

def calc_beneficio(simbolo, lote, precio, tp):
    lot_size = float(LOT_SIZES.get(simbolo, 1) or 1)
    if lote and precio and tp:
        return float(lote) * abs(float(tp) - float(precio)) * lot_size
    return None

def format_money(v):
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", "." ) if v is not None else "-"

def format_rb(riesgo, beneficio):
    if riesgo and riesgo > 0 and beneficio is not None:
        return f"{beneficio/riesgo:.2f} : 1"
    return "0.00 : 1"

# ========= UI: Entradas (sin form, cálculo en vivo) =========
st.title("📈 Calculadora de Riesgo & Gestor de Operaciones")

colA, colB = st.columns([1, 1])
with colA:
    simbolo = st.selectbox("Símbolo", options=df_cfg["Symbol"].tolist(), key="sym")
    tipo = st.selectbox("Tipo", ["Compra", "Venta"], key="side")
    lote = st.number_input("Lote", min_value=0.0, value=0.0, step=0.01, key="lote")
with colB:
    precio = st.number_input("Precio", min_value=0.0, value=0.0, step=0.01, key="precio")
    sl = st.number_input("Stop Loss", min_value=0.0, value=0.0, step=0.01, key="sl")
    tp = st.number_input("Take Profit", min_value=0.0, value=0.0, step=0.01, key="tp")

# Cálculo en vivo (cada métrica si tiene lo necesario)
margen = calc_margen(simbolo, lote, precio)
riesgo = calc_riesgo(simbolo, lote, precio, sl)
beneficio = calc_beneficio(simbolo, lote, precio, tp)
rb_text = format_rb(riesgo, beneficio)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Margen [$]", format_money(margen))
m2.metric("Riesgo de pérdida [$]", format_money(riesgo))
m3.metric("Posible beneficio [$]", format_money(beneficio))
m4.metric("Relación riesgo/beneficio", rb_text)

# ========= Registro del suceso =========
st.markdown("---")
if "show_reg" not in st.session_state:
    st.session_state.show_reg = False

if st.button("Registrar Suceso"):
    st.session_state.show_reg = True

if st.session_state.show_reg:
    st.info("Completa los datos para registrar el suceso:")
    colr1, colr2 = st.columns([1, 2])
    with colr1:
        orden_tipo = st.selectbox("¿Orden pendiente o a mercado?", ["Pendiente", "Mercado"], key="ordentipo")
    with colr2:
        comentario = st.text_area("Comentario de justificación (opcional)", key="comentario")

    if st.button("Aceptar y Guardar"):
        # Obtener el orden real de cabeceras de la hoja Operaciones
        headers = ws_ops.row_values(1)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Preparar campos posibles
        datos = {
            "Fecha": now,
            "Símbolo": simbolo,
            "Simbolo": simbolo,     # por si tus cabeceras usan 'Simbolo' sin acento
            "Tipo": tipo,
            "Lote": lote,
            "Precio": precio,
            "Stop Loss": sl,
            "StopLose": sl,         # tolerancia a variaciones
            "SL": sl,
            "Take Profit": tp,
            "TP": tp,
            "Margen": round(margen or 0.0, 2),
            "Riesgo": round(riesgo or 0.0, 2),
            "Riesgo de pérdida": round(riesgo or 0.0, 2),
            "Beneficio": round(beneficio or 0.0, 2),
            "R/B": rb_text,
            "Relación": rb_text,
            "Orden": orden_tipo,
            "Orden Tipo": orden_tipo,
            "Comentario": comentario,
        }

        # Construir la fila respetando las cabeceras actuales
        fila = [datos.get(h, "") for h in headers] if headers else [
            simbolo, tipo, lote, precio, sl, tp,
            round(margen or 0.0, 2), round(riesgo or 0.0, 2), round(beneficio or 0.0, 2),
            rb_text, orden_tipo, comentario, now
        ]

        ws_ops.append_row(fila)
        st.success("✅ Operación registrada en Google Sheets.")
        st.session_state.show_reg = False

# ========= Lista de operaciones =========
st.markdown("---")
st.subheader("📋 Lista de operaciones")
try:
    records = ws_ops.get_all_records()
    df_ops = pd.DataFrame(records)
    if df_ops.empty:
        st.info("No hay operaciones registradas.")
    else:
        # Detección flexible de columna de estado de orden
        order_col = "Orden" if "Orden" in df_ops.columns else ("Orden Tipo" if "Orden Tipo" in df_ops.columns else None)

        if order_col:
            def color_row(row):
                color = "lightblue" if str(row[order_col]).strip().lower() == "pendiente" else "lightgreen"
                return [f"background-color: {color}"] * len(row)
            st.dataframe(df_ops.style.apply(color_row, axis=1), use_container_width=True)
        else:
            st.dataframe(df_ops, use_container_width=True)
except Exception as e:
    st.error(f"Error al cargar Operaciones: {e}")
