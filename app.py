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
WS_CONFIG = "Config"

sheet = client.open_by_key(SPREADSHEET_ID)
ws_ops = sheet.worksheet(WS_OPERACIONES)
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
    s = str(v).replace("%", "").replace(",", ".").strip()
    try:
        return float(s) / 100.0
    except:
        return 0.0

LOT_SIZES = dict(zip(df_cfg["Symbol"], df_cfg["LotSize"]))
MARGIN_PCTS = dict(zip(df_cfg["Symbol"], [limpiar_margin(x) for x in df_cfg["MarginPct"]]))

# ===== Helpers =====
def parse_decimal_input(s):
    if s is None:
        return None
    s = str(s).strip().replace(",", ".")
    if s == "":
        return None
    try:
        return float(s)
    except:
        return None

def format_money(v):
    return "-" if v is None else f"{v:,.2f}"

def format_rb(riesgo, beneficio):
    if riesgo is None or beneficio is None:
        return "-"
    if riesgo > 0:
        return f"{beneficio / riesgo:.2f} : 1"
    return "Incoherente"

# ===== UI =====
st.title("📈 Calculadora de Riesgo & Gestor de Operaciones")

colA, colB = st.columns([1, 1])
with colA:
    simbolo = st.selectbox("Símbolo", options=df_cfg["Symbol"].tolist())
    tipo = st.selectbox("Tipo", ["Compra", "Venta"])
    lote = parse_decimal_input(st.text_input("Lote", "0,10"))

with colB:
    precio = parse_decimal_input(st.text_input("Precio", ""))
    sl = parse_decimal_input(st.text_input("Stop Loss", ""))
    tp = parse_decimal_input(st.text_input("Take Profit", ""))

# ===== Cálculos dinámicos =====
margen = riesgo = beneficio = rb = None
coherente = True

if lote is not None and precio is not None:
    lot_size = float(LOT_SIZES.get(simbolo, 1) or 1)
    margin_pct = float(MARGIN_PCTS.get(simbolo, 0.0) or 0.0)
    margen = margin_pct * lote * precio * lot_size

if lote is not None and precio is not None and sl is not None:
    lot_size = float(LOT_SIZES.get(simbolo, 1) or 1)
    if tipo == "Compra":
        riesgo = lote * (precio - sl) / lot_size
    else:
        riesgo = lote * (sl - precio) / lot_size
    if riesgo <= 0:
        coherente = False

if lote is not None and precio is not None and tp is not None:
    lot_size = float(LOT_SIZES.get(simbolo, 1) or 1)
    if tipo == "Compra":
        beneficio = lote * (tp - precio) / lot_size
    else:
        beneficio = lote * (precio - tp) / lot_size
    if beneficio <= 0:
        coherente = False

if riesgo and beneficio and riesgo > 0:
    rb = beneficio / riesgo

# ===== Mostrar métricas =====
m1, m2, m3, m4 = st.columns(4)
m1.metric("Margen [$]", format_money(margen))
m2.metric("Riesgo de pérdida [$]", format_money(riesgo))
m3.metric("Posible beneficio [$]", format_money(beneficio))
m4.metric("Relación riesgo/beneficio", format_rb(riesgo, beneficio))

if not coherente and (riesgo is not None or beneficio is not None):
    st.warning("⚠️ Los valores parecen incoherentes para el tipo de operación.")

# ===== Registro del suceso =====
st.markdown("---")
if st.button("Registrar Suceso"):
    headers = ws_ops.row_values(1)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    datos = {
        "Fecha": now,
        "Símbolo": simbolo,
        "Tipo": tipo,
        "Lote": lote or "",
        "Precio": precio or "",
        "Stop Loss": sl or "",
        "Take Profit": tp or "",
        "Margen": round(margen, 2) if margen is not None else "",
        "Riesgo": round(riesgo, 2) if riesgo is not None else "",
        "Beneficio": round(beneficio, 2) if beneficio is not None else "",
        "R/B": f"{rb:.2f}:1" if rb is not None else "",
    }
    fila = [datos.get(h, "") for h in headers] if headers else list(datos.values())
    ws_ops.append_row(fila)
    st.success("✅ Operación registrada en Google Sheets.")
    
    # ===== Mostrar lista de sucesos =====
st.markdown("## 📋 Lista de Sucesos")

try:
    registros = ws_ops.get_all_records()
    df_ops = pd.DataFrame(registros)

    if not df_ops.empty:
        # Colorear según tipo de orden (Mercado vs Pendiente)
        def highlight_row(row):
            if "Orden" in df_ops.columns:
                if row["Orden"] == "Pendiente":
                    return ["background-color: #fff3cd"] * len(row)  # amarillo suave
                else:
                    return ["background-color: #d4edda"] * len(row)  # verde suave
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

