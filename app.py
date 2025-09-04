# app.py
import streamlit as st
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
from datetime import datetime

st.set_page_config(page_title="Trading Risk App", layout="wide")

# ----------------- Conexión Google Sheets -----------------
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
WS_CONFIG = "Config"

sheet = client.open_by_key(SPREADSHEET_ID)
ws_ops = sheet.worksheet(WS_OPERACIONES)
ws_cfg = sheet.worksheet(WS_CONFIG)

# ----------------- Leer Config -----------------
cfg_records = ws_cfg.get_all_records()
df_cfg = pd.DataFrame(cfg_records)

required_cols = {"Symbol", "LotSize", "MarginPct"}
if not required_cols.issubset(set(df_cfg.columns)):
    st.error(
        "La hoja 'Config' debe tener las columnas: Symbol | LotSize | MarginPct. "
        f"Columnas actuales: {list(df_cfg.columns)}"
    )
    st.stop()

def limpiar_margin(v):
    if v is None:
        return 0.0
    s = str(v).replace("%", "").replace(",", ".").strip()
    try:
        return float(s) / 100.0
    except Exception:
        return 0.0

LOT_SIZES = dict(zip(df_cfg["Symbol"], df_cfg["LotSize"]))
MARGIN_PCTS = dict(zip(df_cfg["Symbol"], [limpiar_margin(x) for x in df_cfg["MarginPct"]]))

# ----------------- Helpers -----------------
def parse_decimal_input(s):
    """Acepta coma o punto. Devuelve float o None."""
    if s is None:
        return None
    s = str(s).strip().replace(",", ".")
    if s == "":
        return None
    try:
        return float(s)
    except Exception:
        return None

def format_money(v):
    return "-" if v is None else f"{v:,.2f}"

def format_rb(riesgo, beneficio):
    if riesgo is None or beneficio is None:
        return "-"
    try:
        if riesgo > 0:
            return f"{beneficio / riesgo:.2f} : 1"
        return "Incoherente"
    except Exception:
        return "-"

# ----------------- Cálculo (según tu fórmula solicitada) -----------------
def calcular_metricas(seg_tipo, simbolo, lote, precio, sl, tp):
    """
    Retorna margen, riesgo, beneficio, rb, coherente_flag
    - Margen: %margen * lote * precio * tamaño_lote
    - Riesgo/Beneficio según Compra/Venta sin valores absolutos
    """
    try:
        lot_size = float(LOT_SIZES.get(simbolo, 1) or 1)
        margin_pct = float(MARGIN_PCTS.get(simbolo, 0.0) or 0.0)

        margen = None
        riesgo = None
        beneficio = None
        rb = None
        coherente = True

        if lote is not None and precio is not None:
            margen = margin_pct * float(lote) * float(precio) * lot_size

        if lote is not None and precio is not None and sl is not None:
            if seg_tipo == "Compra":
                riesgo = float(lote) * (float(precio) - float(sl)) / lot_size
            else:  # Venta
                riesgo = float(lote) * (float(sl) - float(precio)) / lot_size
            if riesgo is not None and riesgo <= 0:
                coherente = False

        if lote is not None and precio is not None and tp is not None:
            if seg_tipo == "Compra":
                beneficio = float(lote) * (float(tp) - float(precio)) / lot_size
            else:
                beneficio = float(lote) * (float(precio) - float(tp)) / lot_size
            if beneficio is not None and beneficio <= 0:
                coherente = False

        if riesgo and beneficio and riesgo > 0:
            rb = beneficio / riesgo

        return margen, riesgo, beneficio, rb, coherente
    except Exception:
        return None, None, None, None, False

# ----------------- UI: Entradas -----------------
st.title("📈 Calculadora de Riesgo & Gestor de Operaciones")

# inicializar estado
if "show_reg" not in st.session_state:
    st.session_state.show_reg = False

colA, colB = st.columns([1, 1])
with colA:
    simbolo = st.selectbox("Símbolo", options=df_cfg["Symbol"].tolist())
    tipo = st.selectbox("Tipo", ["Compra", "Venta"])
    lote_str = st.text_input("Lote (coma o punto, ej. 0,02)", value=st.session_state.get("lote_str", "0,10"), key="lote_str")
    lote = parse_decimal_input(lote_str)

with colB:
    precio_str = st.text_input("Precio (coma o punto)", value=st.session_state.get("precio_str", ""), key="precio_str")
    sl_str = st.text_input("Stop Loss (coma o punto)", value=st.session_state.get("sl_str", ""), key="sl_str")
    tp_str = st.text_input("Take Profit (coma o punto)", value=st.session_state.get("tp_str", ""), key="tp_str")

    precio = parse_decimal_input(precio_str)
    sl = parse_decimal_input(sl_str)
    tp = parse_decimal_input(tp_str)

# ----------------- Cálculos parciales y visualización -----------------
margen, riesgo, beneficio, rb, coherente = calcular_metricas(tipo, simbolo, lote, precio, sl, tp)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Margen [$]", format_money(round(margen,2) if margen is not None else None))
m2.metric("Riesgo de pérdida [$]", format_money(round(riesgo,2) if riesgo is not None else None))
m3.metric("Posible beneficio [$]", format_money(round(beneficio,2) if beneficio is not None else None))
m4.metric("Relación riesgo/beneficio", format_rb(riesgo if riesgo is not None else None, beneficio if beneficio is not None else None))

# advertencia only cuando hay datos de riesgo o beneficio y alguno es <= 0
if (riesgo is not None and riesgo <= 0) or (beneficio is not None and beneficio <= 0):
    st.warning(
        "⚠️ Valores incoherentes detectados para el tipo de operación.\n"
        "Compra: SL < Precio < TP  → Riesgo = Precio - SL, Beneficio = TP - Precio.\n"
        "Venta: TP < Precio < SL  → Riesgo = SL - Precio, Beneficio = Precio - TP."
    )

# ----------------- Registro del suceso (pregunta Pendiente/Mercado + comentario) -----------------
st.markdown("---")
st.header("Registrar suceso")

if st.button("Registrar Suceso"):
    st.session_state.show_reg = True

if st.session_state.show_reg:
    st.info("Confirma el tipo de orden y añade una justificación (opcional) antes de guardar.")
    orden_tipo = st.selectbox("¿Orden pendiente o a mercado?", ["Pendiente", "Mercado"], key="orden_tipo")
    comentario = st.text_area("Comentario / Justificación (opcional)", key="comentario_text")

    col_ok, col_cancel = st.columns([1,1])
    with col_ok:
        if st.button("Aceptar y Guardar", key="guardar_suceso"):
            # validación mínima: permitir guardar si al menos lote y precio existen
            if lote is None or precio is None:
                st.error("Para guardar debes indicar al menos Lote y Precio.")
            else:
                try:
                    headers = ws_ops.row_values(1)
                except Exception:
                    headers = []

                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                # valores a guardar (ofrecer varias claves por si las cabeceras difieren)
                datos = {
                    "Fecha": now,
                    "Date": now,
                    "Símbolo": simbolo,
                    "Symbol": simbolo,
                    "Tipo": tipo,
                    "Type": tipo,
                    "Lote": lote,
                    "Lot": lote,
                    "Precio": precio,
                    "Price": precio,
                    "Stop Loss": sl if sl is not None else "",
                    "SL": sl if sl is not None else "",
                    "Take Profit": tp if tp is not None else "",
                    "TP": tp if tp is not None else "",
                    "Margen": round(margen or 0.0, 2),
                    "Riesgo": round(riesgo or 0.0, 2) if riesgo is not None else "",
                    "Beneficio": round(beneficio or 0.0, 2) if beneficio is not None else "",
                    "R/B": f"{(beneficio/riesgo):.2f}:1" if (riesgo and riesgo > 0) else "",
                    "Orden": orden_tipo,
                    "Orden Tipo": orden_tipo,
                    "Estado": orden_tipo,
                    "Comentario": comentario or "",
                    "Justificación": comentario or ""
                }

                # construir fila respetando cabeceras existentes cuando sea posible
                if headers:
                    fila = [datos.get(h, "") for h in headers]
                else:
                    # orden por defecto si no hay cabeceras
                    fila = [
                        now, simbolo, tipo, lote, precio,
                        sl if sl is not None else "",
                        tp if tp is not None else "",
                        round(margen or 0.0, 2),
                        round(riesgo or 0.0, 2) if riesgo is not None else "",
                        round(beneficio or 0.0, 2) if beneficio is not None else "",
                        f"{(beneficio/riesgo):.2f}:1" if (riesgo and riesgo > 0) else "",
                        orden_tipo,
                        comentario or ""
                    ]

                # append a la hoja
                ws_ops.append_row(fila)
                st.success("✅ Operación registrada en Google Sheets.")
                st.session_state.show_reg = False

    with col_cancel:
        if st.button("Cancelar", key="cancel_guardar"):
            st.session_state.show_reg = False

# ----------------- Lista de sucesos (actualizada) -----------------
st.markdown("---")
st.subheader("📋 Lista de Sucesos")

try:
    registros = ws_ops.get_all_records()
    df_ops = pd.DataFrame(registros)

    if df_ops.empty:
        st.info("Aún no hay operaciones registradas.")
    else:
        # elegir columna de estado flexible
        estado_col = None
        for c in ["Orden", "Orden Tipo", "Estado", "Order Type"]:
            if c in df_ops.columns:
                estado_col = c
                break

        if estado_col:
            def color_row(row):
                try:
                    v = str(row[estado_col]).strip().lower()
                    if v == "pendiente":
                        return ["background-color: #fff3cd"] * len(row)
                    else:
                        return ["background-color: #d4edda"] * len(row)
                except Exception:
                    return [""] * len(row)
            st.dataframe(df_ops.style.apply(color_row, axis=1), use_container_width=True)
        else:
            st.dataframe(df_ops, use_container_width=True)

except Exception as e:
    st.error(f"No se pudo leer la hoja de sucesos: {e}")
