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
