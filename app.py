# app.py
import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import math
import string

st.set_page_config(page_title="Trading Risk App", layout="wide")

# ---------------------------
# Helpers
# ---------------------------
def colnum_to_letters(n: int) -> str:
    """Convierte número de columna (1-index) a letra (A, B, ..., Z, AA, AB, ...)"""
    result = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        result = chr(65 + rem) + result
    return result

def parse_decimal(s):
    """Acepta None, '', '0,02', '0.02' y devuelve float o None."""
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

def parse_margin_pct(v):
    """Convierte '0,50%' o '0.50%' o 0.5 a fracción (0.005)."""
    if v is None:
        return 0.0
    s = str(v).strip()
    if s == "":
        return 0.0
    s = s.replace("%", "").replace(",", ".").strip()
    try:
        # Si el valor en hoja está '0.50' entendemos que es porcentaje (0.50%) según tu ejemplo
        # pero si ya está como '0.005' (raro) se toma tal cual. Asumimos que se usa formato 0,50%
        val = float(s)
        # si val > 1 interpretamos que user puso 0.5% como '0.50', entonces /100
        if val > 1 or val <= 1:
            # interpretar siempre como porcentaje: dividir entre 100
            return val / 100.0
    except Exception:
        return 0.0

def safe_div(a, b):
    try:
        if a is None or b is None:
            return None
        if b == 0:
            return None
        return a / b
    except Exception:
        return None

# ---------------------------
# Google Sheets connection (reads st.secrets)
# ---------------------------
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPES)
gc = gspread.authorize(creds)

# Spreadsheet ID fallback: accept both st.secrets["private_gsheets"]["sheet_id"] or st.secrets["sheet_id"]
if st.secrets.get("private_gsheets") and st.secrets["private_gsheets"].get("sheet_id"):
    SHEET_ID = st.secrets["private_gsheets"]["sheet_id"]
elif st.secrets.get("sheet_id"):
    SHEET_ID = st.secrets["sheet_id"]
else:
    st.error("No se ha encontrado el ID del Google Sheet en secrets. Añade private_gsheets.sheet_id o sheet_id.")
    st.stop()

try:
    sh = gc.open_by_key(SHEET_ID)
except Exception as e:
    st.error(f"No se puede abrir el Google Sheet con ese ID: {e}")
    st.stop()

# Worksheet names (must exist)
WS_OPER = "Operaciones"
WS_HIST = "Historial"
WS_CFG = "Config"

try:
    ws_ops = sh.worksheet(WS_OPER)
except Exception:
    st.error(f"No se encuentra la hoja '{WS_OPER}'. Crea la hoja con ese nombre y las cabeceras correspondientes.")
    st.stop()

# create Hist and Config if not exist
try:
    ws_hist = sh.worksheet(WS_HIST)
except Exception:
    # crear la hoja Historial con cabecera básica
    ws_hist = sh.add_worksheet(WS_HIST, rows=1000, cols=20)
    ws_hist.append_row(["UID","Fecha apertura","Fecha cierre","Símbolo","Tipo","Lote","Precio entrada",
                        "Stop Loss","Take Profit","Precio cierre","Margen","Riesgo","Beneficio","R/B","Estado cierre","Justificación"])

try:
    ws_cfg = sh.worksheet(WS_CFG)
except Exception:
    st.error(f"No se encuentra la hoja '{WS_CFG}'. Crea la hoja Config con columnas Symbol | LotSize | MarginPct")
    st.stop()

# ---------------------------
# Read Config
# ---------------------------
cfg_records = ws_cfg.get_all_records()
df_cfg = pd.DataFrame(cfg_records)
required_cfg_cols = {"Symbol", "LotSize", "MarginPct"}
if not required_cfg_cols.issubset(set(df_cfg.columns)):
    st.error(f"La hoja '{WS_CFG}' debe contener las columnas: Symbol, LotSize, MarginPct. Columnas actuales: {list(df_cfg.columns)}")
    st.stop()

# Build dicts
LOT_SIZES = dict(zip(df_cfg["Symbol"], df_cfg["LotSize"]))
MARGIN_PCTS = dict(zip(df_cfg["Symbol"], [parse_margin_pct(x) for x in df_cfg["MarginPct"]]))

# ---------------------------
# UI: Inputs (text_input for comma/dot)
# ---------------------------
st.title("📈 Calculadora de Riesgo & Gestor de Operaciones")

# Reset-on-next-run mechanism:
if st.session_state.get("_clear_after_save"):
    # set default values for widget keys BEFORE widgets are created
    st.session_state["lote_str"] = ""
    st.session_state["precio_str"] = ""
    st.session_state["sl_str"] = ""
    st.session_state["tp_str"] = ""
    st.session_state["_clear_after_save"] = False

# Left column: input form
col1, col2 = st.columns([1, 1])
with col1:
    symbol = st.selectbox("Símbolo", options=list(LOT_SIZES.keys()))
    side = st.radio("Compra / Venta", options=["Compra", "Venta"], horizontal=True)
    lote_str = st.text_input("Lote (coma o punto)", value=st.session_state.get("lote_str", ""), key="lote_str")
    precio_str = st.text_input("Precio (coma o punto)", value=st.session_state.get("precio_str", ""), key="precio_str")
with col2:
    sl_str = st.text_input("Stop Loss (coma o punto)", value=st.session_state.get("sl_str", ""), key="sl_str")
    tp_str = st.text_input("Take Profit (coma o punto)", value=st.session_state.get("tp_str", ""), key="tp_str")

# Parse inputs
lote = parse_decimal(lote_str)
precio = parse_decimal(precio_str)
sl = parse_decimal(sl_str)
tp = parse_decimal(tp_str)

# ---------------------------
# Calculations (partial allowed)
# ---------------------------
lot_size = float(LOT_SIZES.get(symbol, 1) or 1)
margin_pct = float(MARGIN_PCTS.get(symbol, 0.0) or 0.0)

margen = None
riesgo = None
beneficio = None
rb = None
incoherente = False

if lote is not None and precio is not None:
    margen = margin_pct * lote * precio * lot_size

# Formulas per your spec:
# For compra:
# Riesgo = lote*(SL - Precio)/tamaño_lote
# Beneficio = lote*(TP - Precio)/tamaño_lote
# For venta:
# Riesgo = lote*(Precio - SL)/tamaño_lote
# Beneficio = lote*(Precio - TP)/tamaño_lote

if lote is not None and precio is not None and sl is not None:
    if side == "Compra":
        riesgo = lote * (sl - precio) / lot_size
    else:
        riesgo = lote * (precio - sl) / lot_size

if lote is not None and precio is not None and tp is not None:
    if side == "Compra":
        beneficio = lote * (tp - precio) / lot_size
    else:
        beneficio = lote * (precio - tp) / lot_size

# Marcador de incoherencia (mantén la lógica que prefieras).
# Ejemplo simple: incoherente si ambos valores existen y uno no cumple la regla esperada.
# (Puedes ajustar la condición a tu preferencia.)
if (riesgo is not None and beneficio is not None):
    # Si quieres marcar incoherencia cuando riesgo no es del signo esperado:
    #   para Compra: riesgo debería ser < 0 y beneficio > 0
    if not (riesgo < 0 and beneficio > 0):
            incoherente = True

# --- R/B: usar valores absolutos y calcular siempre que ambos existan y riesgo distinto de 0 ---
if (riesgo is not None) and (beneficio is not None):
    denom = abs(riesgo)
    numer = abs(beneficio)
    if denom != 0:
        rb = numer / denom
    else:
        rb = None

# Display metrics (allow partial)
m1, m2, m3, m4 = st.columns(4)
m1.metric("Margen [$]", f"{margen:,.2f}" if margen is not None else "-")
m2.metric("Riesgo [$]", f"{riesgo:,.2f}" if riesgo is not None else "-")
m3.metric("Beneficio [$]", f"{beneficio:,.2f}" if beneficio is not None else "-")
m4.metric("R/B", f"{rb:.2f}:1" if rb is not None else "-")

if incoherente:
    st.warning("⚠️ Datos incoherentes detectados para el tipo de operación (verifica SL/TP respecto al precio).")

# ---------------------------
# Register Suceso UI
# ---------------------------
st.markdown("---")
st.header("Registrar Suceso")

# Show register panel only after clicking the button (keeps UI clean)
if "show_register_panel" not in st.session_state:
    st.session_state["show_register_panel"] = False

if st.button("Registrar Suceso"):
    st.session_state["show_register_panel"] = True

if st.session_state["show_register_panel"]:
    with st.form("register_form"):
        orden_tipo = st.selectbox("¿Orden pendiente o a mercado?", ["Pendiente", "Mercado"])
        comentario = st.text_area("Comentario / Justificación (opcional)")
        submitted = st.form_submit_button("Aceptar y Guardar")
        if submitted:
            # Basic validation: at least lote and precio
            if lote is None or precio is None:
                st.error("Necesitas al menos Lote y Precio para registrar.")
            else:
                # Read current headers to preserve order (if any)
                try:
                    headers = ws_ops.row_values(1)
                except Exception:
                    headers = []
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                uid = int(datetime.now().timestamp() * 1000)

                datos = {
                    "UID": uid,
                    "Fecha": now,
                    "Símbolo": symbol,
                    "Tipo": side,
                    "Lote": lote,
                    "Precio": precio,
                    "Stop Loss": sl if sl is not None else "",
                    "Take Profit": tp if tp is not None else "",
                    "Margen": round(margen or 0.0, 2),
                    "Riesgo": round(riesgo or 0.0, 2) if riesgo is not None else "",
                    "Beneficio": round(beneficio or 0.0, 2) if beneficio is not None else "",
                    "R/B": f"{rb:.2f}:1" if rb is not None else "",
                    #"Estado": orden_tipo,
                    "Orden Tipo": orden_tipo,
                    "Comentario": comentario or "",
                }

                # If sheet has headers, map into that order; otherwise append default order
                if headers:
                    fila = [datos.get(h, "") for h in headers]
                else:
                    fila = [
                        datos["UID"], datos["Fecha"], datos["Símbolo"], datos["Tipo"],
                        datos["Lote"], datos["Precio"], datos["Stop Loss"], datos["Take Profit"],
                        datos["Margen"], datos["Riesgo"], datos["Beneficio"], datos["R/B"],
                        datos["Estado"], datos["Comentario"]
                    ]
                    # If no headers, add them now (first time)
                    try:
                        if not headers:
                            ws_ops.insert_row(["UID","Fecha","Símbolo","Tipo","Lote","Precio",
                                               "Stop Loss","Take Profit","Margen","Riesgo","Beneficio","R/B","Estado","Comentario"], index=1)
                    except Exception:
                        pass

                # Append row:
                try:
                    ws_ops.append_row(fila)
                    st.success("✅ Suceso guardado en Operaciones.")
                    # close panel and request clearing of fields on next run
                    st.session_state["show_register_panel"] = False
                    st.session_state["_clear_after_save"] = True
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al guardar en Google Sheets: {e}")

# ---------------------------
# List of operations (with selection)
# ---------------------------
st.markdown("---")
st.header("Lista de Sucesos (Operaciones)")

try:
    records = ws_ops.get_all_records()
    df_ops = pd.DataFrame(records)
except Exception as e:
    st.error(f"No se puede leer Operaciones: {e}")
    df_ops = pd.DataFrame()

if df_ops.empty:
    st.info("No hay operaciones registradas.")
else:
    # create display strings including row number
    # get number of header columns to compute row numbers: records correspond to rows 2..n+1
    options = []
    for i, row in df_ops.iterrows():
        rownum = i + 2
        estado = str(row.get("Estado") or row.get("Orden") or row.get("Orden Tipo") or "").strip()
        display = f"{rownum} | {row.get('Símbolo','')} | {row.get('Tipo','')} | {estado}"
        options.append(display)

    selected = st.selectbox("Selecciona una operación (fila | simb | tipo | estado)", options)
    # show table with color
    def style_rows(r):
        estado = str(r.get("Estado") or r.get("Orden") or r.get("Orden Tipo") or "").strip().lower()
        if estado == "pendiente":
            return ["background-color:#fff3cd"] * len(r)
        else:
            return ["background-color:#d4edda"] * len(r)

    st.dataframe(df_ops.style.apply(style_rows, axis=1), use_container_width=True)

    # buttons for modify / actions
    st.markdown("### Acciones sobre la operación seleccionada")
    colm1, colm2, colm3 = st.columns(3)
    # compute selected rownum
    sel_rownum = int(selected.split("|")[0].strip())

    with colm1:
        if st.button("Modificar operación seleccionada"):
            # load the row into edit area below via session_state
            try:
                row_values = ws_ops.row_values(sel_rownum)
                headers = ws_ops.row_values(1)
                row_dict = {h: (row_values[idx] if idx < len(row_values) else "") for idx, h in enumerate(headers)}
                st.session_state["_edit_rownum"] = sel_rownum
                st.session_state["_edit_row"] = row_dict
            except Exception as e:
                st.error(f"No se pudo cargar la fila: {e}")

    with colm2:
        if st.button("Eliminar operación pendiente"):
            # only allow if pending
            try:
                headers = ws_ops.row_values(1)
                row_values = ws_ops.row_values(sel_rownum)
                row_dict = {h: (row_values[idx] if idx < len(row_values) else "") for idx,h in enumerate(headers)}
                estado = str(row_dict.get("Estado") or row_dict.get("Orden") or row_dict.get("Orden Tipo") or "").strip().lower()
                if estado != "pendiente":
                    st.error("Solo se pueden eliminar operaciones que estén en estado 'Pendiente'.")
                else:
                    justification = st.text_area("Justificación para eliminar (obligatorio)")
                    if st.button("Confirmar eliminación"):
                        # append to historial as cancelled
                        uid = row_dict.get("UID", "")
                        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        hist_row = [
                            uid, row_dict.get("Fecha",""), now, row_dict.get("Símbolo",""), row_dict.get("Tipo",""),
                            row_dict.get("Lote",""), row_dict.get("Precio",""), row_dict.get("Stop Loss",""), row_dict.get("Take Profit",""),
                            "", row_dict.get("Margen",""), row_dict.get("Riesgo",""), row_dict.get("Beneficio",""), row_dict.get("R/B",""),
                            "Eliminada", justification
                        ]
                        ws_hist.append_row(hist_row)
                        ws_ops.delete_rows(sel_rownum + 2)
                        st.success("Operación pendiente eliminada y registrada en Historial.")
                        st.rerun()
            except Exception as e:
                st.error(f"Error al intentar eliminar: {e}")

    with colm3:
        if st.button("Cierre automático (TP/SL)"):
            try:
                headers = ws_ops.row_values(1)
                row_values = ws_ops.row_values(sel_rownum)
                row_dict = {h: (row_values[idx] if idx < len(row_values) else "") for idx,h in enumerate(headers)}
                estado = str(row_dict.get("Estado") or row_dict.get("Orden") or row_dict.get("Orden Tipo") or "").strip().lower()
                if estado == "pendiente":
                    st.error("No se puede efectuar cierre automático sobre operación pendiente. Actívala primero.")
                else:
                    # elegir si fue TP o SL
                    motivo = st.selectbox("¿Cerró por?", ["TP","SL"])
                    if st.button("Confirmar cierre automático"):
                        # determine precio cierre
                        precio_cierre = None
                        if motivo == "TP":
                            precio_cierre = parse_decimal(row_dict.get("Take Profit") or row_dict.get("TP") or "")
                        else:
                            precio_cierre = parse_decimal(row_dict.get("Stop Loss") or row_dict.get("SL") or "")

                        # compute cierre metrics using formulas: use close price as cierre
                        lote_r = parse_decimal(row_dict.get("Lote") or "")
                        precio_ent = parse_decimal(row_dict.get("Precio") or "")
                        sl_r = parse_decimal(row_dict.get("Stop Loss") or row_dict.get("SL") or "")
                        tp_r = parse_decimal(row_dict.get("Take Profit") or row_dict.get("TP") or "")
                        symbol_r = row_dict.get("Símbolo") or row_dict.get("Symbol")
                        tipo_r = row_dict.get("Tipo") or row_dict.get("Type")
                        lot_size_r = float(LOT_SIZES.get(symbol_r, 1) or 1)
                        margin_pct_r = float(MARGIN_PCTS.get(symbol_r, 0.0) or 0.0)
                        margen_r = margin_pct_r * lote_r * precio_ent * lot_size_r if (lote_r and precio_ent) else None

                        # Compute realized riesgo/beneficio relative to close price as new reference:
                        if tipo_r == "Compra":
                            riesgo_r = lote_r * (sl_r - precio_ent) / lot_size_r if (lote_r and precio_ent and sl_r is not None) else None
                            beneficio_r = lote_r * (tp_r - precio_ent) / lot_size_r if (lote_r and precio_ent and tp_r is not None) else None
                        else:
                            riesgo_r = lote_r * (precio_ent - sl_r) / lot_size_r if (lote_r and precio_ent and sl_r is not None) else None
                            beneficio_r = lote_r * (precio_ent - tp_r) / lot_size_r if (lote_r and precio_ent and tp_r is not None) else None

                        rb_r = safe_div(beneficio_r, riesgo_r) if (riesgo_r and beneficio_r) else None

                        # append to historial
                        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        uid = row_dict.get("UID","")
                        hist_row = [
                            uid, row_dict.get("Fecha",""), now, symbol_r, tipo_r, lote_r, precio_ent,
                            sl_r, tp_r, precio_cierre, round(margen_r or 0.0,2), round(riesgo_r or 0.0,2) if riesgo_r is not None else "",
                            round(beneficio_r or 0.0,2) if beneficio_r is not None else "", f"{rb_r:.2f}:1" if rb_r else "", f"Cierre automático {motivo}", ""
                        ]
                        ws_hist.append_row(hist_row)
                        ws_ops.delete_row(sel_rownum)
                        st.success("Cierre automático registrado en Historial y eliminado de Operaciones.")
                        st.rerun()

            except Exception as e:
                st.error(f"Error cierre automático: {e}")

# ---------------------------
# Edit panel if loaded
# ---------------------------
if "_edit_rownum" in st.session_state and "_edit_row" in st.session_state:
    st.markdown("---")
    st.header("Modificar operación seleccionada")
    edit_rownum = st.session_state["_edit_rownum"]
    edit = st.session_state["_edit_row"]

    # show editable fields for SL, TP, Comentario and activation if pending
    edit_sl = st.text_input("Stop Loss", value=str(edit.get("Stop Loss","")))
    edit_tp = st.text_input("Take Profit", value=str(edit.get("Take Profit","")))
    edit_comment = st.text_area("Comentario", value=str(edit.get("Comentario","")))
    estado_act = str(edit.get("Estado") or edit.get("Orden") or edit.get("Orden Tipo") or "").strip().lower()
    activar_btn = False
    if estado_act == "pendiente":
        activar_btn = st.checkbox("Activar operación (marcar como Mercado)")

    if st.button("Guardar modificación"):
        try:
            headers = ws_ops.row_values(1)
            # build updated dict
            updated = edit.copy()
            updated["Stop Loss"] = parse_decimal(edit_sl) if edit_sl.strip() != "" else ""
            updated["Take Profit"] = parse_decimal(edit_tp) if edit_tp.strip() != "" else ""
            updated["Comentario"] = edit_comment or ""
            if activar_btn:
                updated["Estado"] = "Mercado"

            # build row following headers
            new_row = [updated.get(h, "") for h in headers]
            # update via range
            last_col = len(headers)
            col_letter = colnum_to_letters(last_col)
            rng = f"A{edit_rownum}:{col_letter}{edit_rownum}"
            ws_ops.update(rng, [new_row])
            st.success("Modificación guardada en Operaciones.")
            # clear edit state and refresh
            del st.session_state["_edit_rownum"]
            del st.session_state["_edit_row"]
            st.rerun()
        except Exception as e:
            st.error(f"Error al guardar modificación: {e}")

# ---------------------------
# Manual close action panel
# ---------------------------
st.markdown("---")
st.header("Cierres manuales y utilidades")

col1, col2 = st.columns(2)
with col1:
    if st.button("Cierre manual de selección"):
        try:
            headers = ws_ops.row_values(1)
            row_values = ws_ops.row_values(sel_rownum)
            row_dict = {h: (row_values[idx] if idx < len(row_values) else "") for idx,h in enumerate(headers)}
            estado = str(row_dict.get("Estado") or row_dict.get("Orden") or row_dict.get("Orden Tipo") or "").strip().lower()
            if estado == "pendiente":
                st.error("No se puede cerrar manualmente una operación pendiente; actívala primero.")
            else:
                close_price_input = st.text_input("Introduce precio de cierre (coma/punto)")
                justif_close = st.text_area("Justificación (opcional)")
                if st.button("Confirmar cierre manual"):
                    close_price = parse_decimal(close_price_input)
                    if close_price is None:
                        st.error("Precio de cierre inválido.")
                    else:
                        # compute closure metrics using close_price (similar to auto)
                        symbol_r = row_dict.get("Símbolo") or row_dict.get("Symbol")
                        tipo_r = row_dict.get("Tipo") or row_dict.get("Type")
                        lote_r = parse_decimal(row_dict.get("Lote") or "")
                        precio_ent = parse_decimal(row_dict.get("Precio") or "")
                        sl_r = parse_decimal(row_dict.get("Stop Loss") or row_dict.get("SL") or "")
                        tp_r = parse_decimal(row_dict.get("Take Profit") or row_dict.get("TP") or "")
                        lot_size_r = float(LOT_SIZES.get(symbol_r,1) or 1)
                        margin_pct_r = float(MARGIN_PCTS.get(symbol_r,0.0) or 0.0)
                        margen_r = margin_pct_r * lote_r * precio_ent * lot_size_r if (lote_r and precio_ent) else None

                        if tipo_r == "Compra":
                            riesgo_r = lote_r * (sl_r - precio_ent) / lot_size_r if (lote_r and precio_ent and sl_r is not None) else None
                            beneficio_r = lote_r * (tp_r - precio_ent) / lot_size_r if (lote_r and precio_ent and tp_r is not None) else None
                        else:
                            riesgo_r = lote_r * (precio_ent - sl_r) / lot_size_r if (lote_r and precio_ent and sl_r is not None) else None
                            beneficio_r = lote_r * (precio_ent - tp_r) / lot_size_r if (lote_r and precio_ent and tp_r is not None) else None

                        rb_r = safe_div(beneficio_r, riesgo_r) if (riesgo_r and beneficio_r) else None

                        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        uid = row_dict.get("UID","")
                        hist_row = [uid, row_dict.get("Fecha",""), now, symbol_r, tipo_r, lote_r, precio_ent,
                                    sl_r, tp_r, close_price, round(margen_r or 0.0,2),
                                    round(riesgo_r or 0.0,2) if riesgo_r is not None else "",
                                    round(beneficio_r or 0.0,2) if beneficio_r is not None else "", f"{rb_r:.2f}:1" if rb_r else "",
                                    "Cierre manual", justif_close or ""]
                        ws_hist.append_row(hist_row)
                        ws_ops.delete_row(sel_rownum)
                        st.success("Cierre manual registrado y operación eliminada de Operaciones.")
                        st.rerun()
        except Exception as e:
            st.error(f"Error cierre manual: {e}")

with col2:
    if st.button("Exportar Operaciones a CSV"):
        try:
            df = pd.DataFrame(ws_ops.get_all_records())
            csv = df.to_csv(index=False)
            st.download_button("Descargar CSV", csv, file_name="operaciones.csv")
        except Exception as e:
            st.error(f"Error exportando CSV: {e}")

# END
