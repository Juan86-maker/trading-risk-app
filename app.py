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

SHEET_ID = st.secrets["private_gsheets"]["sheet_id"]
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
        st.session_state[key] = def_
