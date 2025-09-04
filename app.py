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
    try:
        lot_size = float(LOT_SIZES.get(simbolo, 1) or 1)
        margin_pct = float(MARGIN_PCTS.get(simbolo, 0.0) or 0.0)
        if lote is None or precio is None:
            return None
        return margin_pct * float(lote) * float(precio) * lot_size
    except Exception:
        return None

def calc_riesgo(simbolo, lote, precio, sl):
    try:
        lot_size = float(LOT_SIZES.get(simbolo, 1) or 1)
        if lote is None or precio is None or sl is None:
            return None
        return float(lote) * abs(float(precio) - float(sl)) * lot_size
    except Exception:
        return None

def calc_beneficio(simbolo, lote, precio, tp):
    try:
        lot_size = float(LOT_SIZES.get(simbolo, 1) or 1)
        if lote is None or precio is None or tp is None:
            return None
        return float(lote) * abs(float(tp) - float(precio)) * lot_size
    except Exception:
        return None

def format_money(v):
    if v is None:
        return "-"
    try:
        # formato con separador de miles y 2 decimales
        return f"{v:,.2f}"
    except Exception:
        return str(v)

def format_rb(riesgo, beneficio):
    try:
        if riesgo and riesgo > 0 and beneficio is not None:
            return f"{beneficio/riesgo:.2f} : 1"
        return "0.00 : 1"
    except Exception:
        return "0.00 : 1"

def parse_decimal_input(s):
    """Parsea texto que puede usar coma o punto en decimal. Devuelve float o None si vacío."""
    if s is None:
        return None
    s = str(s).strip()
    if s == "":
        return None
    s = s.replace(",", ".")
    try:
        return float(s)
    except Exception:
        return None

def sl_tp_consistente(tipo, precio, sl, tp):
    """Comprueba consistencia: Compra -> SL < Precio < TP ; Venta -> TP < Precio < SL"""
    if precio is None or sl is None or tp is None:
        return False
    try:
        p = float(precio); s = float(sl); t = float(tp)
    except Exception:
        return False
    if tipo == "Compra":
        return (s < p) and (t > p)
    else:
        return (s > p) and (t < p)

# ========= UI: Entradas =========
st.title("📈 Calculadora de Riesgo & Gestor de Operaciones")

colA, colB = st.columns([1, 1])
with colA:
    simbolo = st.selectbox("Símbolo", options=df_cfg["Symbol"].tolist(), key="sym")
    tipo = st.selectbox("Tipo", ["Compra", "Venta"], key="side")
    lote_str = st.text_input("Lote (usa coma o punto, p.ej. 0,02 ó 0.02)", value=st.session_state.get("lote_str", "0,10"), key="lote_str")
    lote = parse_decimal_input(lote_str)
    if lote is None:
        st.info("Introduce un lote válido (ej. 0,02 o 0.02).")
with colB:
    precio = st.number_input("Precio", min_value=0.0, value=float(st.session_state.get("precio", 0.0)), step=0.01, key="precio")
    sl = st.number_input("Stop Loss", min_value=0.0, value=float(st.session_state.get("sl", 0.0)), step=0.01, key="sl")
    tp = st.number_input("Take Profit", min_value=0.0, value=float(st.session_state.get("tp", 0.0)), step=0.01, key="tp")

# Cálculo en vivo (si los valores son interpretables)
margen = calc_margen(simbolo, lote, precio)
riesgo = calc_riesgo(simbolo, lote, precio, sl)
beneficio = calc_beneficio(simbolo, lote, precio, tp)
rb_text = format_rb(riesgo, beneficio)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Margen [$]", format_money(margen))
m2.metric("Riesgo de pérdida [$]", format_money(riesgo))
m3.metric("Posible beneficio [$]", format_money(beneficio))
m4.metric("Relación riesgo/beneficio", rb_text)

# Validación SL/TP según tipo
consistente = sl_tp_consistente(tipo, precio, sl, tp)

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

    # Si no hay lote válido, mostrar error
    if lote is None:
        st.error("El campo 'Lote' no es válido. Corrígelo antes de guardar.")
    else:
        # Si SL/TP no son coherentes con el tipo, mostrar advertencia y ofrecer invertir
        if not consistente:
            st.warning(
                f"Los valores SL/TP no son consistentes con una operación de tipo **{tipo}**.\n\n"
                "Para **Compra**: SL < Precio < TP. \n"
                "Para **Venta**: TP < Precio < SL."
            )
            if st.button("Invertir SL y TP (hacer consistentes)"):
                # Intercambiar valores en session_state para que los widgets se actualicen al rerun
                current_sl = st.session_state.get("sl", 0.0)
                current_tp = st.session_state.get("tp", 0.0)
                st.session_state["sl"] = current_tp
                st.session_state["tp"] = current_sl
                st.experimental_rerun()

            st.info("Corrige SL/TP o pulsa 'Invertir SL y TP' para adaptar los valores al tipo seleccionado.")
        else:
            # Mostrar botón aceptar solo si es consistente
            if st.button("Aceptar y Guardar"):
                # Obtener la primera fila (cabeceras) para respetar orden
                headers = ws_ops.row_values(1)
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                datos = {
                    "Fecha": now,
                    "Símbolo": simbolo,
                    "Simbolo": simbolo,
                    "Tipo": tipo,
                    "Lote": lote,
                    "Precio": precio,
                    "Stop Loss": sl,
                    "StopLose": sl,
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
                    "Comentario": comentario or "",
                }

                fila = [datos.get(h, "") for h in headers] if headers else [
                    now, simbolo, tipo, lote, precio, sl, tp,
                    round(margen or 0.0, 2), round(riesgo or 0.0, 2), round(beneficio or 0.0, 2),
                    rb_text, orden_tipo, comentario or ""
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
