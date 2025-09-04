import streamlit as st
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
from datetime import datetime

st.set_page_config(page_title="Trading Risk App", layout="wide")

# ===== Conexión Google Sheets =====
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

# ===== Config desde hoja Config =====
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
    if v is None or str(v).strip() == "":
        return 0.0
    s = str(v).replace("%", "").replace(",", ".").strip()
    try:
        return float(s) / 100.0
    except Exception:
        return 0.0

LOT_SIZES = dict(zip(df_cfg["Symbol"], df_cfg["LotSize"]))
MARGIN_PCTS = dict(zip(df_cfg["Symbol"], [limpiar_margin(x) for x in df_cfg["MarginPct"]]))

# ===== Helpers: parseo y formateo =====
def parse_decimal_input(s):
    """Acepta texto con coma o punto, devuelve float o None."""
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

def format_money(v):
    if v is None:
        return "-"
    try:
        return f"{v:,.2f}"
    except Exception:
        return str(v)

def format_rb(riesgo, beneficio):
    if riesgo is None or beneficio is None:
        return "-"
    try:
        if riesgo > 0:
            return f"{beneficio / riesgo:.2f} : 1"
        return "Incoherente"
    except Exception:
        return "-"

# ===== Cálculos basados en tipo (Compra/Venta) =====
def calcular_metricas(simbolo, lote, precio, sl, tp):
    """
    Devuelve (margen, riesgo, beneficio, rb, coherente_flag)
    donde riesgo y beneficio pueden ser negativos si los datos son incoherentes.
    """
    try:
        lot_size = float(LOT_SIZES.get(simbolo, 1) or 1)
        margin_pct = float(MARGIN_PCTS.get(simbolo, 0.0) or 0.0)

        # Margen igual en ambos casos
        margen = margin_pct * float(lote) * float(precio) * lot_size

        # según tipo, riesgo y beneficio usando diferencias (no absolutos) y dividiendo por tamaño de lote
        if tipo == "Compra":
            riesgo = float(lote) * (float(precio) - float(sl)) / lot_size
            beneficio = float(lote) * (float(tp) - float(precio)) / lot_size
        else:  # Venta
            riesgo = float(lote) * (float(sl) - float(precio)) / lot_size
            beneficio = float(lote) * (float(precio) - float(tp)) / lot_size

        # coherente: ambos > 0
        coherente = (riesgo is not None and beneficio is not None and riesgo > 0 and beneficio > 0)
        rb = (beneficio / riesgo) if (riesgo and riesgo > 0) else None

        return margen, riesgo, beneficio, rb, coherente
    except Exception:
        return None, None, None, None, False

# ===== UI =====
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
    precio_str = st.text_input("Precio (usa coma o punto)", value=st.session_state.get("precio_str", ""), key="precio_str")
    sl_str = st.text_input("Stop Loss (usa coma o punto)", value=st.session_state.get("sl_str", ""), key="sl_str")
    tp_str = st.text_input("Take Profit (usa coma o punto)", value=st.session_state.get("tp_str", ""), key="tp_str")

    precio = parse_decimal_input(precio_str)
    sl = parse_decimal_input(sl_str)
    tp = parse_decimal_input(tp_str)

    if precio is None:
        st.info("Introduce un Precio válido.")
    if sl is None:
        st.info("Introduce Stop Loss válido.")
    if tp is None:
        st.info("Introduce Take Profit válido.")

# ===== Cálculos en vivo =====
margen, riesgo, beneficio, rb, coherente = (None, None, None, None, False)
if lote is not None and precio is not None and sl is not None and tp is not None:
    margen, riesgo, beneficio, rb, coherente = calcular_metricas(simbolo, lote, precio, sl, tp)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Margen [$]", format_money(round(margen, 2) if margen is not None else None))
m2.metric("Riesgo de pérdida [$]", format_money(round(riesgo, 2) if riesgo is not None else None))
m3.metric("Posible beneficio [$]", format_money(round(beneficio, 2) if beneficio is not None else None))
m4.metric("Relación riesgo/beneficio", format_rb(riesgo if riesgo is not None else None, beneficio if beneficio is not None else None))

# Si hay valores negativos o cero, mostrar advertencia
if (riesgo is not None and riesgo <= 0) or (beneficio is not None and beneficio <= 0):
    st.warning(
        "⚠️ Valores incoherentes detectados según el tipo de operación.\n\n"
        "Para **Compra** debe cumplirse: SL < Precio < TP (riesgo = Precio - SL ; beneficio = TP - Precio).\n"
        "Para **Venta** debe cumplirse: TP < Precio < SL (riesgo = SL - Precio ; beneficio = Precio - TP).\n\n"
        "Si quieres, pulsa **Invertir SL y TP** para cambiar sus valores."
    )

# ===== Registro del suceso (con opción invertir / forzar) =====
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

    # Botón invertir SL/TP
    if st.button("Invertir SL y TP (intercambiar valores)"):
        # intercambiar las cadenas para mantener el formato del usuario
        prev_sl = st.session_state.get("sl_str", sl_str)
        prev_tp = st.session_state.get("tp_str", tp_str)
        st.session_state["sl_str"] = prev_tp
        st.session_state["tp_str"] = prev_sl
        st.experimental_rerun()

    # Si lote o precios no parsean, impedir guardado
    if lote is None or precio is None or sl is None or tp is None:
        st.error("Corrige los campos Lote/Precio/SL/TP (deben ser números con coma o punto).")
    else:
        if coherente:
            if st.button("Aceptar y Guardar"):
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
                    "R/B": f"{(beneficio/riesgo):.2f}:1" if (riesgo and riesgo > 0) else "Incoherente",
                    "Relación": f"{(beneficio/riesgo):.2f}:1" if (riesgo and riesgo > 0) else "Incoherente",
                    "Orden": orden_tipo,
                    "Orden Tipo": orden_tipo,
                    "Comentario": comentario or "",
                }
                fila = [datos.get(h, "") for h in headers] if headers else [
                    now, simbolo, tipo, lote, precio, sl, tp,
                    round(margen or 0.0, 2), round(riesgo or 0.0, 2), round(beneficio or 0.0, 2),
                    f"{(beneficio/riesgo):.2f}:1" if (riesgo and riesgo > 0) else "Incoherente",
                    orden_tipo, comentario or ""
                ]
                ws_ops.append_row(fila)
                st.success("✅ Operación registrada en Google Sheets.")
                st.session_state.show_reg = False
        else:
            st.warning("Los cálculos indican inconsistencia (riesgo o beneficio no positivos).")
            force = st.checkbox("Forzar guardado aun siendo inconsistente (no recomendado)")
            if force and st.button("Guardar forzado"):
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
                    "Riesgo": round(riesgo or 0.0, 2) if riesgo is not None else "",
                    "Riesgo de pérdida": round(riesgo or 0.0, 2) if riesgo is not None else "",
                    "Beneficio": round(beneficio or 0.0, 2) if beneficio is not None else "",
                    "R/B": f"{(beneficio/riesgo):.2f}:1" if (riesgo and riesgo > 0) else "Incoherente",
                    "Relación": f"{(beneficio/riesgo):.2f}:1" if (riesgo and riesgo > 0) else "Incoherente",
                    "Orden": orden_tipo,
                    "Orden Tipo": orden_tipo,
                    "Comentario": comentario or "",
                }
                fila = [datos.get(h, "") for h in headers] if headers else [
                    now, simbolo, tipo, lote, precio, sl, tp,
                    round(margen or 0.0, 2), round(riesgo or 0.0, 2) if riesgo is not None else "",
                    round(beneficio or 0.0, 2) if beneficio is not None else "",
                    f"{(beneficio/riesgo):.2f}:1" if (riesgo and riesgo > 0) else "Incoherente",
                    orden_tipo, comentario or ""
                ]
                ws_ops.append_row(fila)
                st.success("✅ Operación (forzada) registrada en Google Sheets.")
                st.session_state.show_reg = False

# ===== Lista de operaciones =====
st.markdown("---")
st.subheader("📋 Lista de operaciones")
try:
    records = ws_ops.get_all_records()
    df_ops = pd.DataFrame(records)
    if df_ops.empty:
        st.info("No hay operaciones registradas.")
    else:
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
