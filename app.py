import streamlit as st
import pandas as pd
import os
import json
import altair as alt
from datetime import date, datetime, timedelta
import locale
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from gspread_dataframe import set_with_dataframe, get_as_dataframe
import re
import unicodedata
import difflib

# Απενεργοποίηση του ορίου γραμμών για τα γραφήματα 
alt.data_transformers.disable_max_rows()

# Ρύθμιση για Ελληνικά
try:
    locale.setlocale(locale.LC_TIME, 'el_GR.UTF-8')
except:
    pass 

GREEK_MONTHS = {
    1: "Ιανουάριος", 2: "Φεβρουάριος", 3: "Μάρτιος", 4: "Απρίλιος",
    5: "Μάιος", 6: "Ιούνιος", 7: "Ιούλιος", 8: "Αύγουστος",
    9: "Σεπτέμβριος", 10: "Οκτώβριος", 11: "Νοέμβριος", 12: "Δεκέμβριος"
}

EXPECTED_COLS = ['Date', 'Time', 'Type', 'Sport', 'Event', 'Market', 'Odds', 'Stake', 'Status', 'Profit', 'Legs_Data']
DISPLAY_ORDER = ['Α/Α', 'Status', 'Date', 'Time', 'Type', 'Sport', 'Event', 'Market', 'Odds', 'Stake', 'Profit']

STATUS_LIST = ["⚪ Εκκρεμές", "🟢 Κερδισμένο", "🔴 Χαμένο", "🔵 Ακυρωμένο", "🟡 Cash Out"]
STAKE_PRESETS = [0.30, 0.15, "Χειροκίνητα..."]
BET_TYPES = ["Μονό", "Παρολί", "Bet Builder", "Παρολί με Bet Builders"]

SPORT_ICONS = {
    "Ποδόσφαιρο": "⚽ Ποδόσφαιρο",
    "Μπάσκετ": "🏀 Μπάσκετ",
    "Τένις": "🎾 Τένις",
    "Άλλο": "🎯 Άλλο",
    "Διάφορα": "🌎 Διάφορα"
}

# ==========================================
# 🧠 ΒΑΣΗ ΔΕΔΟΜΕΝΩΝ ΟΜΑΔΩΝ & ΔΙΟΡΓΑΝΩΣΕΩΝ
# ==========================================
SPORTS_HIERARCHY = {
    "⚽ Ποδόσφαιρο": {
        "🇬🇷 Super League": ["Ολυμπιακός", "Παναθηναϊκός", "ΑΕΚ", "ΠΑΟΚ", "Άρης", "ΟΦΗ", "Παναιτωλικός", "Αστέρας Τρίπολης", "Βόλος", "Ατρόμητος", "Λαμία", "Πανσερραϊκός", "Καλλιθέα", "Λεβαδειακός"],
        "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League": ["Άρσεναλ", "Μάντσεστερ Σίτι", "Λίβερπουλ", "Τσέλσι", "Μάντσεστερ Γιουνάιτεντ", "Τότεναμ", "Νιούκαστλ", "Άστον Βίλα", "Έβερτον", "Μπράιτον", "Μπρέντφορντ", "Γουέστ Χαμ", "Φούλαμ", "Μπόρνμουθ", "Κρίσταλ Πάλας"],
        "🇪🇸 La Liga": ["Ρεάλ Μαδρίτης", "Μπαρτσελόνα", "Ατλέτικο Μαδρίτης", "Τζιρόνα", "Μπιλμπάο", "Σοσιεδάδ", "Βιγιαρεάλ", "Βαλένθια", "Μπέτις", "Σεβίλλη", "Θέλτα", "Μαγιόρκα", "Οσασούνα"],
        "🇮🇹 Serie A": ["Ίντερ", "Γιουβέντους", "Μίλαν", "Νάπολι", "Αταλάντα", "Ρόμα", "Λάτσιο", "Φιορεντίνα", "Τορίνο", "Μπολόνια"],
        "🇪🇺 Champions League": ["Ρεάλ Μαδρίτης", "Μπαρτσελόνα", "Μπάγερν Μονάχου", "Λίβερπουλ", "Μάντσεστερ Σίτι", "Άρσεναλ", "Γιουβέντους", "Λεβερκούζεν", "Παρί Σεν Ζερμέν", "Ίντερ", "Μίλαν", "Ντόρτμουντ", "Σπόρτινγκ", "Μονακό", "Άστον Βίλα"],
        "🇪🇺 Europa / Conference": ["Ολυμπιακός", "ΠΑΟΚ", "Παναθηναϊκός", "Μάντσεστερ Γιουνάιτεντ", "Τότεναμ", "Άγιαξ", "Λάτσιο", "Ρόμα", "Μπιλμπάο", "Λυών", "Σοσιεδάδ", "Άιντραχτ", "Γαλατασαράι", "Φενέρμπαχτσε"],
        "Διεθνή (Εθνικές)": ["Ελλάδα", "Αγγλία", "Ισπανία", "Γαλλία", "Γερμανία", "Πορτογαλία", "Ολλανδία", "Ιταλία", "Αργεντινή", "Βραζιλία", "Βέλγιο"],
        "Άλλη Διοργάνωση...": []
    },
    "🏀 Μπάσκετ": {
        "🇪🇺 Euroleague": ["Ολυμπιακός", "Παναθηναϊκός", "Ρεάλ Μαδρίτης", "Μπαρτσελόνα", "Μονακό", "Φενέρμπαχτσε", "Αναντολού Εφές", "Μπάγερν Μονάχου", "Ζαλγκίρις", "Ερυθρός Αστέρας", "Παρτιζάν", "Αρμάνι Μιλάνο", "Βίρτους Μπολόνια", "Μακάμπι Τελ Αβίβ", "Βιλερμπάν", "Μπασκόνια", "Άλμπα Βερολίνου", "Παρί"],
        "🇬🇷 Basket League": ["Ολυμπιακός", "Παναθηναϊκός", "Περιστέρι", "Προμηθέας", "ΑΕΚ", "Άρης", "ΠΑΟΚ", "Κολοσσός Ρόδου", "Μαρούσι", "Καρδίτσα", "Λαύριο", "Πανιώνιος"],
        "🇺🇸 NBA": ["Ατλάντα Χοκς", "Μπόστον Σέλτικς", "Μπρούκλιν Νετς", "Σάρλοτ Χόρνετς", "Σικάγο Μπουλς", "Κλίβελαντ Καβαλίερς", "Ντάλας Μάβερικς", "Ντένβερ Νάγκετς", "Ντιτρόιτ Πίστονς", "Γκόλντεν Στέιτ Γουόριορς", "Χιούστον Ρόκετς", "Ιντιάνα Πέισερς", "Λος Άντζελες Κλίπερς", "Λος Άντζελες Λέικερς", "Μέμφις Γκρίζλις", "Μαϊάμι Χιτ", "Μιλγουόκι Μπακς", "Μινεσότα Τίμπεργουλβς", "Νέα Ορλεάνη Πέλικανς", "Νιου Γιορκ Νικς", "Οκλαχόμα Σίτι Θάντερ", "Ορλάντο Μάτζικ", "Φιλαδέλφεια Σίξερς", "Φοίνιξ Σανς", "Πόρτλαντ Τρέιλ Μπλέιζερς", "Σακραμέντο Κινγκς", "Σαν Αντόνιο Σπερς", "Τορόντο Ράπτορς", "Γιούτα Τζαζ", "Ουάσινγκτον Γουίζαρντς"],
        "🇺🇸 WNBA": ["Λας Βέγκας Έισις (Aces)", "Νιου Γιορκ Λίμπερτι (Liberty)", "Κονέκτικατ Σαν (Sun)", "Μινεσότα Λινξ (Lynx)", "Σιάτλ Στορμ (Storm)", "Ιντιάνα Φίβερ (Fever)", "Φοίνιξ Μέρκιουρι (Mercury)", "Ατλάντα Ντριμ (Dream)", "Σικάγο Σκάι (Sky)", "Λος Άντζελες Σπαρκς (Sparks)", "Ντάλας Γουίνγκς (Wings)", "Ουάσινγκτον Μίστικς (Mystics)", "Γκόλντεν Στέιτ Βαλκίρις (Valkyries)"],
        "🌍 Εθνικές (FIBA / Προκριματικά)": ["Ελλάδα", "ΗΠΑ", "Σερβία", "Γερμανία", "Γαλλία", "Καναδάς", "Ισπανία", "Αυστραλία", "Λιθουανία", "Ιταλία", "Λετονία", "Σλοβενία", "Πουέρτο Ρίκο", "Βραζιλία", "Τουρκία", "Μαυροβούνιο", "Μπαχάμες", "Γεωργία", "Φινλανδία", "Νέα Ζηλανδία"],
        "🇪🇺 Eurocup": ["Χάποελ Τελ Αβίβ", "Μπανταλόνα", "Γκραν Κανάρια", "Βαλένθια", "Μπεσίκτας", "Τουρκ Τέλεκομ", "Μπουργκ", "Τσεντεβίτα", "Άρης", "Τρέντο", "Ουλμ", "Κλουζ", "Γουλβς"],
        "🇪🇺 BCL (Champions League)": ["Τενερίφη", "Ουνικάχα Μάλαγα", "Μούρθια", "Γαλατασαράι", "Καρσίγιακα", "Χάποελ Ιερουσαλήμ", "ΑΕΚ", "Περιστέρι", "Προμηθέας", "Ρίτας Βίλνιους", "Ιγκοκέα", "Ντερτόνα", "Βόννη", "Κέμνιτς"],
        "Άλλη Διοργάνωση...": []
    },
    "🎾 Τένις": {
        "Άνδρες (ATP)": ["Sinner", "Alcaraz", "Djokovic", "Zverev", "Medvedev", "Tsitsipas", "Rublev", "Ruud", "Dimitrov", "De Minaur", "Fritz", "Tiafoe", "Rune", "Shelton", "Hurkacz", "Paul", "Khachanov"],
        "Γυναίκες (WTA)": ["Swiatek", "Sabalenka", "Gauff", "Rybakina", "Pegula", "Zheng", "Sakkari", "Jabeur", "Ostapenko", "Collins", "Navarro", "Paolini", "Krejcikova", "Haddad Maia", "Kasatkina"],
        "Άλλη Διοργάνωση...": []
    }
}

MARKET_GENERAL = {
    "⚽ Ποδόσφαιρο": ["Τελικό Αποτέλεσμα (1X2)", "Over/Under Γκολ", "Goal/Goal ή No Goal", "Διπλή Ευκαιρία", "Ημίχρονο/Τελικό", "Κόρνερ Match", "Κάρτες Match"],
    "🏀 Μπάσκετ": ["Νικητής (Με Παράταση)", "Χάντικαπ (Spread)", "Over/Under Πόντων", "Ημίχρονο/Τελικό"],
    "🎾 Τένις": ["Νικητής Αγώνα", "Over/Under Games", "Χάντικαπ Games", "Ακριβές Σκορ Σετ"]
}

MARKET_PLAYER = {
    "⚽ Ποδόσφαιρο": ["Να Σκοράρει", "Πρώτος Σκόρερ", "Σουτ στην Εστία", "Κάρτα", "Ασίστ", "Τάκλιν", "Πάσες"],
    "🏀 Μπάσκετ": ["Πόντοι", "Ριμπάουντ", "Ασίστ", "Εύστοχα Τρίποντα", "Κλεψίματα", "Κοψίματα", "Λάθη", "Π.Ρ.Α."],
    "🎾 Τένις": ["Άσσοι", "Διπλά Λάθη", "Breaks"]
}

st.set_page_config(page_title="My Bet Tracker", page_icon="📈", layout="wide")

# ==========================================
# 🎨 PREMIUM UI CSS & NEW TYPOGRAPHY
# ==========================================
custom_css = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&display=swap');
html, body, p, h1, h2, h3, h4, h5, h6, label, input, select, textarea, table, button p { font-family: 'Poppins', sans-serif !important; }
.stApp { background-color: #0b172a; }
[data-testid="stSidebar"] { background-color: #060d1a; border-right: 1px solid #1e3a5f; }
.sidebar-header { font-size: 0.8rem; color: #4db8ff; text-transform: uppercase; letter-spacing: 1.5px; font-weight: 700; margin-top: 25px; margin-bottom: 10px; border-bottom: 1px solid #1e3a5f; padding-bottom: 8px; font-family: 'Poppins', sans-serif !important; }
[data-testid="stStatusWidget"] { display: none !important; }
[data-testid="stVerticalBlockBorderWrapper"], div[role="dialog"] { background-color: #0f1c2e !important; border: 1px solid #1e3a5f !important; border-radius: 16px !important; box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5) !important; }
[data-testid="stDialog"] > div { background-color: #0b172a !important; border-radius: 20px !important; border: 1px solid #2a4365 !important; }
[data-testid="stDialog"] header { background-color: #0b172a !important; }
.stTextInput input, .stNumberInput input, [data-baseweb="select"] > div, .stDateInput input, .stTimeInput input, textarea { background-color: #16263b !important; color: #e2e8f0 !important; border: 1px solid #2a4365 !important; border-radius: 8px !important; font-size: 15px !important; letter-spacing: 0.3px !important; }
div[data-baseweb="input"]:focus-within, div[data-baseweb="select"]:focus-within { border-color: #4db8ff !important; box-shadow: inset 0 0 0 1px #4db8ff !important; }
button[kind="primary"] { background: linear-gradient(90deg, #10b981, #059669) !important; color: white !important; font-weight: 600 !important; border: none !important; border-radius: 8px !important; box-shadow: 0 4px 6px rgba(0,0,0,0.3) !important; transition: all 0.2s ease !important; }
button[kind="primary"]:hover { background: linear-gradient(90deg, #059669, #047857) !important; transform: translateY(-2px); }
button[kind="primary"] * { color: white !important; }
button[kind="secondary"] { background-color: #16263b !important; border: 1px solid #1e3a5f !important; border-radius: 10px !important; padding: 15px !important; width: 100% !important; height: auto !important; min-height: 90px !important; display: flex !important; flex-direction: column !important; align-items: center !important; justify-content: center !important; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3) !important; transition: all 0.2s ease !important; }
button[kind="secondary"]:hover { transform: translateY(-3px) !important; box-shadow: 0 6px 12px rgba(0,0,0,0.4) !important; }
button[kind="secondary"] p { white-space: pre-wrap !important; font-size: 1.15rem !important; color: #e2e8f0 !important; margin: 0 !important; line-height: 1.5 !important; text-align: center !important; width: 100% !important; }
div[data-testid="stElementContainer"]:has(.marker-positive), div[data-testid="stElementContainer"]:has(.marker-negative), div[data-testid="stElementContainer"]:has(.marker-neutral), div[data-testid="stElementContainer"]:has(.marker-warning), div[data-testid="stElementContainer"]:has(.marker-info), div[data-testid="stElementContainer"]:has(.marker-gold), div[data-testid="stElementContainer"]:has(.marker-dark), div[data-testid="stElementContainer"]:has(.marker-player1), div[data-testid="stElementContainer"]:has(.marker-player2) { margin: 0 !important; height: 0 !important; display: none !important; }
div[data-testid="stElementContainer"]:has(.marker-positive) + div[data-testid="stElementContainer"] button { border: 1px solid #10b981 !important; background-color: rgba(16, 185, 129, 0.05) !important; }
div[data-testid="stElementContainer"]:has(.marker-positive) + div[data-testid="stElementContainer"] button p { color: #10b981 !important; font-weight: 600 !important; }
div[data-testid="stElementContainer"]:has(.marker-negative) + div[data-testid="stElementContainer"] button { border: 1px solid #ef4444 !important; background-color: rgba(239, 68, 68, 0.05) !important; }
div[data-testid="stElementContainer"]:has(.marker-negative) + div[data-testid="stElementContainer"] button p { color: #ef4444 !important; font-weight: 600 !important; }
div[data-testid="stElementContainer"]:has(.marker-warning) + div[data-testid="stElementContainer"] button { border: 1px solid #f59e0b !important; background-color: rgba(245, 158, 11, 0.05) !important; }
div[data-testid="stElementContainer"]:has(.marker-warning) + div[data-testid="stElementContainer"] button p { color: #f59e0b !important; font-weight: 600 !important; }
div[data-testid="stElementContainer"]:has(.marker-info) + div[data-testid="stElementContainer"] button { border: 1px solid #3b82f6 !important; background-color: rgba(59, 130, 246, 0.05) !important; }
div[data-testid="stElementContainer"]:has(.marker-info) + div[data-testid="stElementContainer"] button p { color: #3b82f6 !important; font-weight: 600 !important; }
div[data-testid="stElementContainer"]:has(.marker-gold) + div[data-testid="stElementContainer"] button { border: 1px solid #fbbf24 !important; background-color: rgba(251, 191, 36, 0.05) !important; }
div[data-testid="stElementContainer"]:has(.marker-gold) + div[data-testid="stElementContainer"] button p { color: #fbbf24 !important; font-weight: 600 !important; }
div[data-testid="stElementContainer"]:has(.marker-dark) + div[data-testid="stElementContainer"] button { border: 1px solid #9ca3af !important; background-color: rgba(156, 163, 175, 0.05) !important; }
div[data-testid="stElementContainer"]:has(.marker-dark) + div[data-testid="stElementContainer"] button p { color: #9ca3af !important; font-weight: 600 !important; }
div[data-testid="stElementContainer"]:has(.marker-player1) + div[data-testid="stElementContainer"] button { border: 1px solid #c084fc !important; background-color: rgba(192, 132, 252, 0.05) !important; }
div[data-testid="stElementContainer"]:has(.marker-player1) + div[data-testid="stElementContainer"] button p { color: #c084fc !important; font-weight: 600 !important; }
div[data-testid="stElementContainer"]:has(.marker-player2) + div[data-testid="stElementContainer"] button { border: 1px solid #f472b6 !important; background-color: rgba(244, 114, 182, 0.05) !important; }
div[data-testid="stElementContainer"]:has(.marker-player2) + div[data-testid="stElementContainer"] button p { color: #f472b6 !important; font-weight: 600 !important; }
div[data-testid="stElementContainer"]:has(.fab-marker) { display: none !important; }
div[data-testid="stElementContainer"]:has(.fab-marker) + div[data-testid="stElementContainer"] { position: fixed !important; bottom: 30px !important; right: 30px !important; z-index: 999999 !important; width: auto !important; }
div[data-testid="stElementContainer"]:has(.fab-marker) + div[data-testid="stElementContainer"] button { border-radius: 50px !important; padding: 15px 35px !important; background: linear-gradient(135deg, #0284c7, #10b981) !important; border: none !important; box-shadow: 0 10px 25px rgba(16, 185, 129, 0.4) !important; }
div[data-testid="stElementContainer"]:has(.fab-marker) + div[data-testid="stElementContainer"] button p { color: white !important; font-size: 16px !important; font-weight: bold !important; }
button[data-baseweb="tab"] { background-color: transparent !important; color: #a8dadc !important; font-family: 'Poppins', sans-serif !important; font-weight: 500 !important; }
button[data-baseweb="tab"][aria-selected="true"] { color: #4db8ff !important; border-bottom: 2px solid #4db8ff !important; }
hr { border-color: #1e3a5f !important; margin: 1.5em 0 !important; }
div[role="radiogroup"] > label { background-color: #16263b !important; padding: 12px 15px !important; border-radius: 8px !important; border: 1px solid #1e3a5f !important; margin-bottom: 12px !important; cursor: pointer; }
</style>
"""
st.markdown(custom_css, unsafe_allow_html=True)

# Αρχικοποίηση State
if 'form_reset_counter' not in st.session_state: st.session_state['form_reset_counter'] = 0
if 'show_toast' not in st.session_state: st.session_state['show_toast'] = False
if 'toast_message' not in st.session_state: st.session_state['toast_message'] = ""
if 'page_sel' not in st.session_state: st.session_state['page_sel'] = "📊 Dashboard & Στατιστικά"
if 'auto_odds_multi' not in st.session_state: st.session_state['auto_odds_multi'] = 1.0
if 'redirect_to' not in st.session_state: st.session_state['redirect_to'] = None

if st.session_state['redirect_to']:
    st.session_state['page_sel'] = st.session_state['redirect_to']
    st.session_state['redirect_to'] = None

if st.session_state['show_toast']:
    st.toast(st.session_state['toast_message'], icon="✅")
    st.session_state['show_toast'] = False 

# ==========================================
# ☁️ ΣΥΝΔΕΣΗ ΜΕ GOOGLE SHEETS
# ==========================================
@st.cache_resource
def init_gsheets():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    if os.path.exists('google_credentials.json'):
        creds = ServiceAccountCredentials.from_json_keyfile_name('google_credentials.json', scope)
    else:
        creds_dict = json.loads(st.secrets["google_json"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    sheet = client.open('Betting History Database').sheet1
    return sheet

@st.cache_data
def fetch_gsheets():
    sheet = init_gsheets()
    df = get_as_dataframe(sheet).dropna(how='all').dropna(axis=1, how='all')
    return df

def save_data(df_to_save):
    sheet = init_gsheets()
    sheet.clear()
    df_to_save = df_to_save[EXPECTED_COLS]
    set_with_dataframe(sheet, df_to_save)
    fetch_gsheets.clear() 

def load_data():
    df = fetch_gsheets()
    if df.empty:
        if os.path.exists('betting_history.csv') and os.stat('betting_history.csv').st_size > 0:
            df = pd.read_csv('betting_history.csv')
            save_data(df)
        else:
            df = pd.DataFrame(columns=EXPECTED_COLS)
            save_data(df)
    for col in EXPECTED_COLS:
        if col not in df.columns: df[col] = ''
            
    df['Type'] = df['Type'].replace('', 'Μονό')
    df = df[EXPECTED_COLS]
    df['Odds'] = pd.to_numeric(df['Odds'], errors='coerce').fillna(0.0)
    df['Stake'] = pd.to_numeric(df['Stake'], errors='coerce').fillna(0.0)
    df['Profit'] = pd.to_numeric(df['Profit'], errors='coerce').fillna(0.0)
    df.fillna({'Market': '', 'Event': '', 'Sport': '', 'Type': 'Μονό', 'Legs_Data': ''}, inplace=True)
    for col in ['Market', 'Event', 'Sport', 'Type', 'Legs_Data']: df[col] = df[col].astype(str)
    for k, v in SPORT_ICONS.items(): df.loc[df['Sport'] == k, 'Sport'] = v
        
    status_mapping = {"Pending": "⚪ Εκκρεμές", "Won": "🟢 Κερδισμένο", "Lost": "🔴 Χαμένο", "Void": "🔵 Ακυρωμένο", "Cash Out": "🟡 Cash Out"}
    if df['Status'].isin(status_mapping.keys()).any(): df['Status'] = df['Status'].replace(status_mapping)
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce').dt.date
    df['Time'] = pd.to_datetime(df['Time'].astype(str), errors='coerce').dt.time
    return df

df = load_data()
df = df.sort_values(by=["Date", "Time"]).reset_index(drop=True)
df.insert(0, 'Α/Α', range(1, len(df) + 1))

# ==========================================
# 🧠 DYNAMIC PLAYER/TEAM MEMORY BUILDER
# ==========================================
team_rosters = {}
all_players_global = set()
ignore_words_set = {'over', 'under', 'ov', 'un', 'o', 'u', 'ποντοι', 'ριμπαουντ', 'ασιστ', 'ασσιστ', 'τριποντα', 'γκολ', 'καρτες', 'σουτ', 'φαουλ', 'νικη', 'ισοπαλια', 'ηττα', 'να', 'σκοραρει', 'anytime', 'scorer', '1', 'x', '2', '1x', 'x2', '12', 'gg', 'ng', 'g/g', 'n/g'}

for idx, row in df.iterrows():
    def map_players(ev_str, ma_str):
        teams = []
        ev_main = str(ev_str).split("(")[0].strip()
        for delim in [' - ', ' vs ', '-']:
            if delim in ev_main and len(ev_main.split(delim)) == 2:
                p1, p2 = ev_main.split(delim)
                teams.extend([p1.strip(), p2.strip()])
                break
        if not teams and ev_main:
            teams.append(ev_main.strip())
        
        players = []
        if pd.notna(ma_str) and str(ma_str).strip() != "":
            for m_part in str(ma_str).split('|'):
                m_clean = re.sub(r'[^\w\s-]', '', m_part).strip()
                words = m_clean.split()
                p_name = []
                for w in words:
                    if re.search(r'\d', w) or (w and ''.join(c for c in unicodedata.normalize('NFD', w) if unicodedata.category(c) != 'Mn').lower().strip() in ignore_words_set): break
                    p_name.append(w)
                final_p = " ".join(p_name).strip()
                if final_p and len(final_p) > 2 and final_p.lower() not in ["home", "away", "draw", "νικη", "ισοπαλια", "yes", "no"]:
                    players.append(final_p)
        
        for t in teams:
            if t not in team_rosters: team_rosters[t] = set()
            for p in players:
                team_rosters[t].add(p)
                all_players_global.add(p)

    if row['Type'] == "Μονό":
        map_players(row['Event'], row['Market'])
    else:
        legs_str = row['Legs_Data']
        if pd.notna(legs_str) and legs_str.strip():
            try:
                for leg in json.loads(legs_str):
                    map_players(leg.get('event', row['Event']), leg.get('market', ''))
            except: pass

# Helper variables for old functions
all_events_set = set()
all_markets_set = set()
for ev in df['Event'].dropna():
    if ev.strip() != '': all_events_set.add(ev)
for ma in df['Market'].dropna():
    if '|' not in ma and ma.strip() != '': all_markets_set.add(ma)

all_events = sorted(list(all_events_set))
all_markets = sorted(list(all_markets_set))
all_teams_set = set(team_rosters.keys())
all_teams = sorted(list(all_teams_set))

global_avg_odds = df['Odds'].mean()
if pd.isna(global_avg_odds) or global_avg_odds < 1.01: global_avg_odds = 1.50
else: global_avg_odds = float(global_avg_odds)

dynamic_sports = list(SPORT_ICONS.values())
for s in df['Sport'].dropna().unique().tolist():
    if s not in dynamic_sports and s != '': dynamic_sports.append(s)

GREEK_COLUMNS = {
    "Α/Α": st.column_config.NumberColumn("Α/Α", format="%d", disabled=True),
    "Status": st.column_config.SelectboxColumn("Κατάσταση", options=STATUS_LIST, required=True),
    "Date": st.column_config.DateColumn("Ημερομηνία", format="DD/MM/YYYY"),
    "Time": st.column_config.TimeColumn("Ώρα", format="HH:mm", step=60),
    "Type": st.column_config.SelectboxColumn("Τύπος", options=BET_TYPES, required=True),
    "Sport": st.column_config.SelectboxColumn("Άθλημα", options=dynamic_sports, required=True),
    "Event": st.column_config.TextColumn("Αγώνας"),
    "Market": st.column_config.TextColumn("Αγορά", disabled=True), 
    "Odds": st.column_config.NumberColumn("Απόδοση", format="%.2f"),
    "Stake": st.column_config.NumberColumn("Ποντάρισμα", format="%.2f €"),
    "Profit": st.column_config.NumberColumn("Κέρδος / Ζημιά", format="%.2f €")
}

# ==========================================
# 📊 CALLBACK FUNCTIONS
# ==========================================
def update_auto_odds(reset_id, num_legs):
    total_odds = 1.0
    for i in range(int(num_legs)):
        leg_odds_key = f"leg_od_{i}_{reset_id}"
        leg_status_key = f"leg_st_{i}_{reset_id}"
        if leg_odds_key in st.session_state and leg_status_key in st.session_state:
            val = float(st.session_state[leg_odds_key])
            stat = st.session_state[leg_status_key]
            if stat != "🔵 Ακυρωμένο": total_odds *= val
    st.session_state['auto_odds_multi'] = total_odds

def update_auto_odds_edit(aa_val, num_legs):
    total_odds = 1.0
    for i in range(int(num_legs)):
        leg_odds_key = f"ed_leg_od_{i}_{aa_val}"
        leg_status_key = f"ed_leg_st_{i}_{aa_val}"
        if leg_odds_key in st.session_state and leg_status_key in st.session_state:
            val = float(st.session_state[leg_odds_key])
            stat = st.session_state[leg_status_key]
            if stat != "🔵 Ακυρωμένο": total_odds *= val
    st.session_state['auto_odds_multi'] = total_odds

# ==========================================
# 🧠 ΕΞΥΠΝΟΣ ΒΟΗΘΟΣ (ΟΜΑΔΕΣ & ΑΓΟΡΕΣ) 
# ==========================================
def render_event_input(sport, key_pref, mode, container=st):
    if mode == "✍️ Ελεύθερο Κείμενο" or sport not in SPORTS_HIERARCHY:
        ev_str = container.text_input("Αγώνας (Ομάδες / Παίκτες):", key=f"{key_pref}_txt")
        return ev_str
    else:
        leagues = list(SPORTS_HIERARCHY[sport].keys())
        lg = container.selectbox("🏆 Διοργάνωση", leagues, key=f"{key_pref}_lg")
        if lg == "Άλλη Διοργάνωση...":
            return container.text_input("Αγώνας (π.χ. Ολυμπιακός - ΠΑΟΚ):", key=f"{key_pref}_man_ev")
        else:
            teams = SPORTS_HIERARCHY[sport][lg]
            t1 = container.selectbox("🏠 Γηπεδούχος / P1", teams + ["✏️ Άλλη..."], key=f"{key_pref}_t1")
            if t1 == "✏️ Άλλη...": t1 = container.text_input("Γράψε Ομάδα 1:", key=f"{key_pref}_t1_man")
            t2 = container.selectbox("✈️ Φιλοξενούμενος / P2", teams + ["✏️ Άλλη..."], key=f"{key_pref}_t2")
            if t2 == "✏️ Άλλη...": t2 = container.text_input("Γράψε Ομάδα 2:", key=f"{key_pref}_t2_man")
            if t1 and t2: return f"{t1} - {t2}"
            return ""

def render_market_input(sport, key_pref, mode, event_str, container=st, prefill=""):
    if mode == "✍️ Ελεύθερο Κείμενο" or (sport not in MARKET_GENERAL and sport not in MARKET_PLAYER):
        val = container.text_input("Αγορά:", value=prefill, key=f"{key_pref}_txt")
        return val
    else:
        default_idx = 2 if prefill else 0
        market_type = container.radio("Κατηγορία Αγοράς:", ["Γενική (Match)", "👤 Ειδικό Παίκτη", "✏️ Ελεύθερο"], index=default_idx, horizontal=True, key=f"{key_pref}_type")
        
        if market_type == "✏️ Ελεύθερο":
            return container.text_input("Γράψε Αγορά:", value=prefill, key=f"{key_pref}_free")
            
        elif market_type == "Γενική (Match)":
            cats = MARKET_GENERAL.get(sport, [])
            if not cats: return container.text_input("Αγορά:", value=prefill, key=f"{key_pref}_gen_free")
            c1, c2 = container.columns(2)
            sel = c1.selectbox("Αγορά:", ["(Επιλογή)"] + cats, key=f"{key_pref}_gen_sel")
            if sel != "(Επιλογή)":
                val = c2.text_input("Σημείο / Όριο (π.χ. Over 2.5):", key=f"{key_pref}_gen_final")
                return f"{sel}: {val}" if val else sel
            return ""
            
        elif market_type == "👤 Ειδικό Παίκτη":
            cats = MARKET_PLAYER.get(sport, ["Άλλο"])
            
            # 🧠 Smart Player Lookup based on Event Memory!
            relevant_players = []
            teams = []
            ev_main = str(event_str).split("(")[0].strip()
            for delim in [' - ', ' vs ', '-']:
                if delim in ev_main and len(ev_main.split(delim)) == 2:
                    parts = ev_main.split(delim)
                    teams.extend([parts[0].strip(), parts[1].strip()])
                    break
            if not teams and ev_main: teams.append(ev_main.strip())
            
            for t in teams:
                if t in team_rosters: relevant_players.extend(list(team_rosters[t]))
            relevant_players = sorted(list(set(relevant_players)))
            all_others = sorted(list(all_players_global - set(relevant_players)))
            
            p_options = ["(Επίλεξε)"]
            if relevant_players: p_options += ["--- ΠΑΙΚΤΕΣ ΑΓΩΝΑ ---"] + relevant_players
            if all_others: p_options += ["--- ΑΛΛΟΙ ΠΑΙΚΤΕΣ ---"] + all_others
            p_options += ["➕ Νέος Παίκτης..."]
            
            c1, c2, c3 = container.columns([2, 1.5, 1.5])
            player_sel = c1.selectbox("Παίκτης:", p_options, key=f"{key_pref}_p_sel")
            
            final_player = ""
            if player_sel == "➕ Νέος Παίκτης...":
                final_player = c1.text_input("Όνομα Παίκτη:", key=f"{key_pref}_p_new")
            elif player_sel and not player_sel.startswith("---") and player_sel != "(Επίλεξε)":
                final_player = player_sel
                
            stat_sel = c2.selectbox("Στατιστικό:", ["(Επιλογή)"] + cats, key=f"{key_pref}_p_stat")
            line_val = c3.text_input("Όριο / Σημείο (π.χ. Over 15.5):", key=f"{key_pref}_p_line")
            
            if final_player and stat_sel != "(Επιλογή)":
                return f"{final_player} - {stat_sel} {line_val}".strip()
            return ""

def calc_overall_status(legs_list):
    if not legs_list: return "⚪ Εκκρεμές"
    statuses = [l.get('status', "⚪ Εκκρεμές") for l in legs_list]
    if "🔴 Χαμένο" in statuses: return "🔴 Χαμένο"
    elif "⚪ Εκκρεμές" in statuses: return "⚪ Εκκρεμές"
    elif "🟢 Κερδισμένο" in statuses: return "🟢 Κερδισμένο"
    else: return "🔵 Ακυρωμένο"

# ==========================================
# 🧾 PREMIUM DIGITAL RECEIPT
# ==========================================
def render_ticket_html(aa_val, df_source):
    row = df_source[df_source['Α/Α'] == aa_val].iloc[0]
    status_color = "#4db8ff"
    stamp_text = ""
    stamp_color = ""
    if row['Status'] == "🟢 Κερδισμένο": 
        status_color = "#10b981"; stamp_text = "WON"; stamp_color = "rgba(16, 185, 129, 0.15)"
    elif row['Status'] == "🔴 Χαμένο": 
        status_color = "#ef4444"; stamp_text = "LOST"; stamp_color = "rgba(239, 68, 68, 0.15)"
    elif row['Status'] == "🟡 Cash Out": 
        status_color = "#f59e0b"; stamp_text = "CASH OUT"; stamp_color = "rgba(245, 158, 11, 0.15)"
    elif row['Status'] == "🔵 Ακυρωμένο": 
        status_color = "#3b82f6"; stamp_text = "VOID"; stamp_color = "rgba(59, 130, 246, 0.15)"
    
    total_return = row['Stake'] + row['Profit'] if row['Status'] != "⚪ Εκκρεμές" else 0.0
    profit_str = f"+{row['Profit']:.2f} €" if row['Profit'] > 0 else f"{row['Profit']:.2f} €"
    ticket_id = f"#MB-{row['Α/Α']}{str(row['Date']).replace('-','')[2:]}"
    
    html_parts = []
    html_parts.append(f'<div style="background: linear-gradient(135deg, #16263b, #0f1c2e); padding: 30px; border-radius: 16px; border: 1px solid #1e3a5f; box-shadow: 0 15px 35px rgba(0,0,0,0.6); position: relative; overflow: hidden; font-family: \'Poppins\', sans-serif;">')
    if stamp_text: html_parts.append(f"<div style='position:absolute; top:50px; right:10px; color:{stamp_color}; font-size:65px; font-weight:900; transform:rotate(-15deg); border:4px solid {stamp_color}; padding:5px 15px; border-radius:15px; z-index:0; pointer-events:none; letter-spacing: 2px;'>{stamp_text}</div>")
    html_parts.append(f'''<div style="text-align: center; border-bottom: 2px dashed #2a4365; padding-bottom: 15px; margin-bottom: 20px; position: relative; z-index: 1;">
        <p style="margin: 0; color: #a8dadc; font-size: 13px; letter-spacing: 1px;">TICKET ID: {ticket_id}</p>
        <h2 style="margin: 5px 0 0 0; color: {status_color}; font-weight: 700; text-transform: uppercase; letter-spacing: 1.5px;">{row['Status']}</h2>
        <p style="margin: 5px 0 0 0; color: #718096; font-size: 13px;">{row['Date'].strftime('%d/%m/%Y')} • {row['Time'].strftime('%H:%M')}</p>
    </div>
    <div style="display: flex; justify-content: space-between; margin-bottom: 20px; position: relative; z-index: 1;">
        <div><p style="margin: 0; font-size: 11px; color: #4db8ff; text-transform: uppercase; letter-spacing: 1px;">ΑΘΛΗΜΑ</p><p style="margin: 0; font-size: 17px; font-weight: 600; color: #e2e8f0;">{row['Sport']}</p></div>
        <div style="text-align: right;"><p style="margin: 0; font-size: 11px; color: #4db8ff; text-transform: uppercase; letter-spacing: 1px;">ΤΥΠΟΣ</p><p style="margin: 0; font-size: 17px; font-weight: 600; color: #e2e8f0;">{row['Type']}</p></div>
    </div>
    <div style="margin-bottom: 25px; position: relative; z-index: 1;">
        <p style="margin: 0 0 15px 0; font-size: 12px; color: #4db8ff; text-transform: uppercase; letter-spacing: 1px; border-bottom: 1px solid #1e3a5f; padding-bottom: 8px;">ΕΠΙΛΟΓΕΣ ΔΕΛΤΙΟΥ</p>''')
    
    if row['Type'] == "Μονό":
        html_parts.append(f'''<div style="background-color: rgba(6, 13, 26, 0.5); padding: 15px; border-radius: 12px; margin-bottom: 10px; border-left: 4px solid {status_color};">
            <p style="margin: 0; font-weight: 600; color: #ffffff; font-size: 16px;">{row['Event']}</p>
            <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 10px;">
                <span style="color: #a8dadc; font-size: 14px;">{row['Market']}</span>
                <span style="font-weight: 700; font-size: 17px; color: #4db8ff;">{row['Odds']:.2f}</span>
            </div>
        </div>''')
    else:
        legs_str = row['Legs_Data']
        if pd.notna(legs_str) and legs_str.strip() != "":
            try:
                legs = json.loads(legs_str)
                for leg in legs:
                    l_st = leg.get('status', '⚪ Εκκρεμές')
                    l_color = "#4db8ff"
                    if "Κερδισμένο" in l_st: l_color = "#10b981"
                    elif "Χαμένο" in l_st: l_color = "#ef4444"
                    elif "Ακυρωμένο" in l_st: l_color = "#3b82f6"
                    ev_name = leg.get('event', row['Event'])
                    html_parts.append(f'''<div style="background-color: rgba(6, 13, 26, 0.5); padding: 15px; border-radius: 12px; margin-bottom: 10px; border-left: 4px solid {l_color};">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <span style="font-weight: 600; color: #ffffff; font-size: 15px;">{ev_name}</span>
                            <span style="font-size: 11px; font-weight: 600; color: {l_color}; padding: 3px 8px; background-color: rgba(0,0,0,0.3); border-radius: 12px;">{l_st}</span>
                        </div>
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 10px;">
                            <span style="color: #a8dadc; font-size: 14px; white-space: pre-wrap;">{leg.get('market', '-').replace(' | ', '<br>')}</span>
                            <span style="font-weight: 700; font-size: 16px; color: #4db8ff;">{float(leg.get('odds', 1.0)):.2f}</span>
                        </div>
                    </div>''')
            except Exception: pass
    
    html_parts.append(f'''</div>
    <div style="border-top: 2px dashed #2a4365; padding-top: 20px; position: relative; z-index: 1;">
        <div style="display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 15px;">
            <div><p style="margin: 0; font-size: 12px; color: #718096; text-transform: uppercase;">ΠΟΝΤΑΡΙΣΜΑ</p><p style="margin: 0; font-size: 18px; font-weight: 600; color: #e2e8f0;">{row['Stake']:.2f} €</p></div>
            <div style="text-align: right;"><p style="margin: 0; font-size: 12px; color: #718096; text-transform: uppercase;">ΣΥΝ. ΑΠΟΔΟΣΗ</p><p style="margin: 0; font-size: 18px; font-weight: 600; color: #e2e8f0;">{row['Odds']:.2f}</p></div>
        </div>
        <div style="background-color: rgba(0,0,0,0.2); padding: 15px; border-radius: 12px; display: flex; justify-content: space-between; align-items: center;">
            <div><p style="margin: 0; font-size: 12px; color: #a8dadc; text-transform: uppercase;">ΣΥΝ. ΕΠΙΣΤΡΟΦΗ</p><p style="margin: 0; font-size: 24px; font-weight: 700; color: #ffffff;">{total_return:.2f} €</p></div>
            <div style="text-align: right;"><p style="margin: 0; font-size: 12px; color: #a8dadc; text-transform: uppercase;">ΚΑΘΑΡΟ ΚΕΡΔΟΣ</p><p style="margin: 0; font-size: 24px; font-weight: 700; color: {status_color};">{profit_str}</p></div>
        </div>
    </div>
    </div>''')
    st.markdown("".join(html_parts), unsafe_allow_html=True)

@st.dialog("🧾 Απόδειξη Στοιχήματος", width="large")
def show_ticket_modal(aa_val, df_source):
    render_ticket_html(aa_val, df_source)

# ==========================================
# 🔍 ΑΝΑΔΥΟΜΕΝΑ ΠΑΡΑΘΥΡΑ (MODALS) - ΠΙΝΑΚΕΣ
# ==========================================
@st.dialog("📊 Λεπτομέρειες", width="large")
def show_bets_dialog(title_str, df_to_show, full_df):
    st.markdown(f"<h3 style='color: #4db8ff; font-family: Poppins;'>{title_str}</h3>", unsafe_allow_html=True)
    st.markdown("<p style='color: #a8dadc; font-size: 14px; margin-bottom: 15px; font-family: Poppins;'>💡 Κάνε κλικ σε οποιαδήποτε γραμμή για να δεις την απόδειξη (Ανακατεύθυνση στο Ιστορικό).</p>", unsafe_allow_html=True)
    if not df_to_show.empty:
        disp = df_to_show.drop(columns=['Legs_Data'], errors='ignore')[DISPLAY_ORDER].sort_values(by=["Date", "Time"], ascending=False)
        event = st.dataframe(disp, use_container_width=True, hide_index=True, column_config=GREEK_COLUMNS, on_select="rerun", selection_mode="single-row")
        if event.selection.rows:
            sel_idx = event.selection.rows[0]
            sel_aa = disp.iloc[sel_idx]['Α/Α']
            st.session_state['redirect_to'] = "🗓️ Μηνιαία Αναφορά"
            st.session_state['auto_open_ticket'] = int(sel_aa)
            st.rerun()
    else:
        st.info("Δεν βρέθηκαν δελτία.")

@st.dialog("📈 Ανάλυση Εξέλιξης", width="large")
def show_progression_dialog(metric_type, prog_dataframe, full_df):
    st.markdown("<p style='color: #a8dadc; font-size: 14px; margin-bottom: 15px; font-family: Poppins;'>💡 Κάνε κλικ σε οποιαδήποτε γραμμή για να δεις την απόδειξη (Ανακατεύθυνση στο Ιστορικό).</p>", unsafe_allow_html=True)
    if prog_dataframe.empty:
        st.info("Δεν υπάρχουν δεδομένα.")
        return
        
    if metric_type == "profit":
        st.markdown("<h3 style='color: #4db8ff; font-family: Poppins;'>💰 Εξέλιξη Συνολικού Ταμείου</h3>", unsafe_allow_html=True)
        disp_df = prog_dataframe[['Α/Α', 'Date', 'Event', 'Stake', 'Odds', 'Profit', 'Cumulative_Profit', 'Balance']].copy()
        disp_df.rename(columns={'Date': 'Ημ/νια', 'Event': 'Αγώνας', 'Stake': 'Ποντάρισμα', 'Odds': 'Απόδοση', 'Profit': 'Κέρδος/Ζημιά', 'Cumulative_Profit': 'Συνολικό Κέρδος', 'Balance': 'Τρέχον Υπόλοιπο'}, inplace=True)
        cfg = {"Συνολικό Κέρδος": st.column_config.NumberColumn("Συνολικό Κέρδος (€)", format="%.2f €"), "Τρέχον Υπόλοιπο": st.column_config.NumberColumn("Τρέχον Υπόλοιπο (€)", format="%.2f €"), "Κέρδος/Ζημιά": st.column_config.NumberColumn("Κέρδος/Ζημιά", format="%.2f €"), "Ποντάρισμα": st.column_config.NumberColumn("Ποντάρισμα", format="%.2f €"), "Ημ/νια": st.column_config.DateColumn("Ημ/νια", format="DD/MM/YYYY")}
    elif metric_type == "roi":
        st.markdown("<h3 style='color: #4db8ff; font-family: Poppins;'>📉 Εξέλιξη Yield (ROI)</h3>", unsafe_allow_html=True)
        disp_df = prog_dataframe[['Α/Α', 'Date', 'Event', 'Stake', 'Profit', 'Cumulative_ROI']].copy()
        disp_df.rename(columns={'Date': 'Ημ/νια', 'Event': 'Αγώνας', 'Stake': 'Ποντάρισμα', 'Profit': 'Κέρδος/Ζημιά', 'Cumulative_ROI': 'Τρέχον ROI'}, inplace=True)
        cfg = {"Τρέχον ROI": st.column_config.NumberColumn("Τρέχον ROI (%)", format="%.2f %%"), "Κέρδος/Ζημιά": st.column_config.NumberColumn("Κέρδος/Ζημιά", format="%.2f €"), "Ποντάρισμα": st.column_config.NumberColumn("Ποντάρισμα", format="%.2f €"), "Ημ/νια": st.column_config.DateColumn("Ημ/νια", format="DD/MM/YYYY")}
    elif metric_type == "wr":
        st.markdown("<h3 style='color: #4db8ff; font-family: Poppins;'>🎯 Εξέλιξη Win Rate</h3>", unsafe_allow_html=True)
        disp_df = prog_dataframe[prog_dataframe['Status'].isin(["🟢 Κερδισμένο", "🔴 Χαμένο"])].copy()
        disp_df = disp_df[['Α/Α', 'Date', 'Event', 'Status', 'Cumulative_WR']]
        disp_df.rename(columns={'Date': 'Ημ/νια', 'Event': 'Αγώνας', 'Status': 'Κατάσταση', 'Cumulative_WR': 'Τρέχον Win Rate'}, inplace=True)
        cfg = {"Τρέχον Win Rate": st.column_config.NumberColumn("Τρέχον Win Rate (%)", format="%.1f %%"), "Ημ/νια": st.column_config.DateColumn("Ημ/νια", format="DD/MM/YYYY")}
    elif metric_type == "avg_odds":
        st.markdown("<h3 style='color: #4db8ff; font-family: Poppins;'>⚖️ Εξέλιξη Μέσης Απόδοσης</h3>", unsafe_allow_html=True)
        disp_df = prog_dataframe[['Α/Α', 'Date', 'Event', 'Odds', 'Cumulative_AvgOdds']].copy()
        disp_df.rename(columns={'Date': 'Ημ/νια', 'Event': 'Αγώνας', 'Odds': 'Απόδοση Δελτίου', 'Cumulative_AvgOdds': 'Τρέχουσα Μέση Απόδοση'}, inplace=True)
        cfg = {"Τρέχουσα Μέση Απόδοση": st.column_config.NumberColumn("Τρέχουσα Μέση Απόδοση", format="%.2f"), "Απόδοση Δελτίου": st.column_config.NumberColumn("Απόδοση Δελτίου", format="%.2f"), "Ημ/νια": st.column_config.DateColumn("Ημ/νια", format="DD/MM/YYYY")}
    elif metric_type == "drawdown":
        st.markdown("<h3 style='color: #4db8ff; font-family: Poppins;'>📉 Εξέλιξη Βύθισης Ταμείου (Drawdown)</h3>", unsafe_allow_html=True)
        disp_df = prog_dataframe[['Α/Α', 'Date', 'Event', 'Profit', 'Cumulative_Profit', 'Peak', 'Drawdown']].copy()
        disp_df.rename(columns={'Date': 'Ημ/νια', 'Event': 'Αγώνας', 'Profit': 'Κέρδος/Ζημιά', 'Cumulative_Profit': 'Συνολικό Κέρδος', 'Peak': 'Κορυφή (Peak)', 'Drawdown': 'Βύθιση (DD)'}, inplace=True)
        cfg = {
            "Βύθιση (DD)": st.column_config.NumberColumn("Βύθιση (€)", format="%.2f €"),
            "Κορυφή (Peak)": st.column_config.NumberColumn("Κορυφή (€)", format="%.2f €"),
            "Συνολικό Κέρδος": st.column_config.NumberColumn("Συνολικό Κέρδος (€)", format="%.2f €"),
            "Κέρδος/Ζημιά": st.column_config.NumberColumn("Κέρδος/Ζημιά", format="%.2f €"),
            "Ημ/νια": st.column_config.DateColumn("Ημ/νια", format="DD/MM/YYYY")
        }
        
    event = st.dataframe(disp_df, use_container_width=True, hide_index=True, column_config=cfg, on_select="rerun", selection_mode="single-row")
    if event.selection.rows:
        sel_idx = event.selection.rows[0]
        sel_aa = disp_df.iloc[sel_idx]['Α/Α']
        st.session_state['redirect_to'] = "🗓️ Μηνιαία Αναφορά"
        st.session_state['auto_open_ticket'] = int(sel_aa)
        st.rerun()

@st.dialog("➕ Καταχώρηση Νέου Δελτίου", width="large")
def new_bet_dialog():
    reset_id = st.session_state['form_reset_counter']
    st.markdown("<br>", unsafe_allow_html=True)
    bet_type = st.radio("Τύπος Στοιχήματος", BET_TYPES, horizontal=True, key=f"bet_type_{reset_id}")
    num_legs = 2
    if bet_type != "Μονό":
        num_legs = st.number_input("Πόσα σημεία (ή αγώνες) έχει το δελτίο;", min_value=2, max_value=15, value=2, key=f"legs_num_{reset_id}")
    
    st.markdown("<h5 style='color: #a8dadc; border-bottom: 1px solid #1e3a5f; padding-bottom: 5px; margin-top: 15px; font-family: Poppins;'>1. Βασικά Στοιχεία</h5>", unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns([2, 2, 3, 3])
    d = c1.date_input("Ημερομηνία", date.today(), format="DD/MM/YYYY", key=f"date_{reset_id}")
    t = c2.time_input("Ώρα", datetime.now().time(), step=60, key=f"time_{reset_id}")
    basket_index = list(SPORT_ICONS.values()).index("🏀 Μπάσκετ")
    selected_sport_input = c3.selectbox("Άθλημα", list(SPORT_ICONS.values()), index=basket_index, key=f"sport_{reset_id}")
    entry_mode = c4.selectbox("Εισαγωγή Δεδομένων:", ["🤖 Έξυπνος Βοηθός", "✍️ Ελεύθερο Κείμενο"], key=f"entry_mode_{reset_id}")
    
    legs = []
    event_str, market_str = "", ""
    auto_odds = 1.0
    st.markdown("---")
    
    if bet_type == "Μονό":
        st.markdown("<h5 style='color: #a8dadc; border-bottom: 1px solid #1e3a5f; padding-bottom: 5px; margin-top: 15px; font-family: Poppins;'>2. Αγώνας & Αγορά</h5>", unsafe_allow_html=True)
        c_ev, c_ma = st.columns(2)
        event_str = render_event_input(selected_sport_input, f"ev_single_{reset_id}", entry_mode, c_ev)
        market_str = render_market_input(selected_sport_input, f"ma_single_{reset_id}", entry_mode, event_str, c_ma)
        
    elif bet_type == "Bet Builder":
        st.info("💡 Στο απλό Bet Builder (ίδιος αγώνας), η συνολική απόδοση δίνεται από τον bookmaker. Συμπλήρωσέ τη χειροκίνητα στο Βήμα 3!")
        st.markdown("<h5 style='color: #a8dadc; border-bottom: 1px solid #1e3a5f; padding-bottom: 5px; margin-top: 15px; font-family: Poppins;'>2. Κοινός Αγώνας & Σημεία</h5>", unsafe_allow_html=True)
        c_ev, _ = st.columns(2)
        event_str = render_event_input(selected_sport_input, f"bb_ev_{reset_id}", entry_mode, c_ev)
        st.markdown("<br>", unsafe_allow_html=True)
        for i in range(int(num_legs)):
            cc2, cc3, cc4 = st.columns([3,1,2])
            l_ma = render_market_input(selected_sport_input, f"bb_ma_{i}_{reset_id}", entry_mode, event_str, cc2)
            l_od = cc3.number_input(f"Απόδοση {i+1}", min_value=1.00, step=0.01, value=1.50, key=f"bb_od_{i}_{reset_id}")
            l_st = cc4.selectbox(f"Κατάστ. {i+1}", STATUS_LIST, key=f"bb_st_{i}_{reset_id}")
            legs.append({"event": event_str, "market": l_ma, "odds": l_od, "status": l_st})
            if l_st == "🔵 Ακυρωμένο": auto_odds *= 1.0
            else: auto_odds *= l_od

    elif bet_type == "Παρολί με Bet Builders":
        st.markdown("<h5 style='color: #a8dadc; border-bottom: 1px solid #1e3a5f; padding-bottom: 5px; margin-top: 15px; font-family: Poppins;'>2. Αγώνες & Σημεία (Bet Builders)</h5>", unsafe_allow_html=True)
        temp_odds = 1.0
        for i in range(int(num_legs)):
            st.markdown(f"<div style='background-color: rgba(22, 38, 59, 0.4); padding: 15px; border-radius: 12px; margin-bottom: 15px; border-left: 4px solid #4db8ff;'>", unsafe_allow_html=True)
            st.markdown(f"**Αγώνας {i+1}**")
            l_ev = render_event_input(selected_sport_input, f"pbb_ev_{i}_{reset_id}", entry_mode, st)
            c_ma, c_od, c_st = st.columns([4, 1, 2])
            l_ma_key = f"pbb_ma_{i}_{reset_id}"
            l_ma = c_ma.text_area(f"Επιλογές Bet Builder (Μία ανά γραμμή):", height=68, key=l_ma_key, placeholder="π.χ.\n1 & Over 2.5\nVezenkov Over Πόντων: 15.5")
            l_od = c_od.number_input(f"Απόδοση:", min_value=1.00, step=0.01, value=1.50, key=f"leg_od_{i}_{reset_id}", on_change=update_auto_odds, args=(reset_id, num_legs))
            l_st = c_st.selectbox(f"Κατάσταση:", STATUS_LIST, key=f"leg_st_{i}_{reset_id}", on_change=update_auto_odds, args=(reset_id, num_legs))
            st.markdown("</div>", unsafe_allow_html=True)
            clean_ma = l_ma.replace('\n', ' | ') if l_ma else ""
            legs.append({"event": l_ev, "market": clean_ma, "odds": l_od, "status": l_st})
            if l_st != "🔵 Ακυρωμένο": temp_odds *= l_od
        if 'auto_odds_multi' not in st.session_state or st.session_state['auto_odds_multi'] == 1.0:
            st.session_state['auto_odds_multi'] = temp_odds

    else: 
        st.markdown("<h5 style='color: #a8dadc; border-bottom: 1px solid #1e3a5f; padding-bottom: 5px; margin-top: 15px; font-family: Poppins;'>2. Ανάλυση Σημείων</h5>", unsafe_allow_html=True)
        temp_odds = 1.0
        for i in range(int(num_legs)):
            st.markdown(f"<div style='background-color: rgba(22, 38, 59, 0.4); padding: 15px; border-radius: 12px; margin-bottom: 15px; border-left: 4px solid #10b981;'>", unsafe_allow_html=True)
            st.markdown(f"**Σημείο {i+1}**")
            l_ev = render_event_input(selected_sport_input, f"ev_t_{i}_{reset_id}", entry_mode, st)
            cc2, cc3, cc4 = st.columns([3, 1, 2])
            l_ma = render_market_input(selected_sport_input, f"ma_t_{i}_{reset_id}", entry_mode, l_ev, cc2)
            l_od = cc3.number_input(f"Απόδοση:", min_value=1.00, step=0.01, value=1.50, key=f"leg_od_{i}_{reset_id}", on_change=update_auto_odds, args=(reset_id, num_legs))
            l_st = cc4.selectbox(f"Κατάστ.:", STATUS_LIST, key=f"leg_st_{i}_{reset_id}", on_change=update_auto_odds, args=(reset_id, num_legs))
            st.markdown("</div>", unsafe_allow_html=True)
            legs.append({"event": l_ev, "market": l_ma, "odds": l_od, "status": l_st})
            if l_st != "🔵 Ακυρωμένο": temp_odds *= l_od
        if 'auto_odds_multi' not in st.session_state or st.session_state['auto_odds_multi'] == 1.0:
            st.session_state['auto_odds_multi'] = temp_odds
            
    st.markdown("<h5 style='color: #a8dadc; border-bottom: 1px solid #1e3a5f; padding-bottom: 5px; margin-top: 15px; font-family: Poppins;'>3. Αποδόσεις & Ποντάρισμα</h5>", unsafe_allow_html=True)
    c5, c6, c7, c8 = st.columns(4)
    if bet_type == "Μονό":
        odds = c5.number_input("Απόδοση", min_value=1.01, step=0.01, value=round(global_avg_odds, 2), key=f"odds_single_{reset_id}")
        chosen_preset = c6.selectbox("Ποντάρισμα (€)", STAKE_PRESETS, key=f"stake_preset_{reset_id}")
        custom_stake = c7.number_input("Ή γράψε δικό σου ποσό (€)", min_value=0.0, step=0.05, format="%.2f", key=f"custom_stake_{reset_id}")
        status = c8.selectbox("Κατάσταση (Συνολική)", STATUS_LIST, key=f"status_{reset_id}")
    elif bet_type == "Bet Builder":
        odds = c5.number_input("Συνολική Απόδοση", min_value=1.00, step=0.01, value=1.50, key=f"odds_multi_{reset_id}")
        chosen_preset = c6.selectbox("Ποντάρισμα (€)", STAKE_PRESETS, key=f"stake_preset_{reset_id}")
        custom_stake = c7.number_input("Ή γράψε δικό σου ποσό (€)", min_value=0.0, step=0.05, format="%.2f", key=f"custom_stake_{reset_id}")
        status_sel = c8.selectbox("Κατάσταση (Συνολική)", ["Αυτόματος Υπολογισμός ⚙️", "🟡 Cash Out"], key=f"status_{reset_id}")
        if status_sel == "Αυτόματος Υπολογισμός ⚙️": status = calc_overall_status(legs)
        else: status = "🟡 Cash Out"
    else:
        odds = c5.number_input("Συνολική Απόδοση (Υπολογισμένη)", min_value=1.00, step=0.01, value=float(st.session_state.get('auto_odds_multi', 1.0)), key=f"odds_multi_{reset_id}")
        chosen_preset = c6.selectbox("Ποντάρισμα (€)", STAKE_PRESETS, key=f"stake_preset_{reset_id}")
        custom_stake = c7.number_input("Ή γράψε δικό σου ποσό (€)", min_value=0.0, step=0.05, format="%.2f", key=f"custom_stake_{reset_id}")
        status_sel = c8.selectbox("Κατάσταση (Συνολική)", ["Αυτόματος Υπολογισμός ⚙️", "🟡 Cash Out"], key=f"status_{reset_id}")
        if status_sel == "Αυτόματος Υπολογισμός ⚙️": status = calc_overall_status(legs)
        else: status = "🟡 Cash Out"
    
    cash_out_val = 0.0
    if status == "🟡 Cash Out":
        st.info("💸 Επέλεξες Cash Out! Δήλωσε το ποσό που εισέπραξες:")
        cash_out_val = st.number_input("Επιστροφή Cash Out (€)", min_value=0.0, step=0.01, format="%.2f", key=f"cashout_{reset_id}")
    
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("💾 ΑΠΟΘΗΚΕΥΣΗ ΔΕΛΤΙΟΥ", type="primary", key=f"save_btn_{reset_id}", use_container_width=True):
        profit = 0.0
        stake = custom_stake if chosen_preset == "Χειροκίνητα..." else float(chosen_preset)

        if status == "🟢 Κερδισμένο": profit = stake * (odds - 1)
        elif status == "🔴 Χαμένο": profit = -stake
        elif status == "🟡 Cash Out": profit = cash_out_val - stake
        elif status == "🔵 Ακυρωμένο": profit = 0.0
        
        t_string = t.strftime('%H:%M')
        legs_json = ""
        
        if bet_type != "Μονό":
            legs_json = json.dumps(legs)
            if bet_type == "Bet Builder":
                base_ev = legs[0]['event'] if legs and legs[0]['event'] else ""
                event_str = f"{base_ev} ({len(legs)} επιλογές)" if base_ev else f"{len(legs)} επιλογές"
            elif bet_type == "Παρολί με Bet Builders":
                events_list = [l['event'] for l in legs if l['event']]
                event_str = " | ".join(events_list) if events_list else ""
            else:
                events_list = [l['event'] for l in legs if l['event']]
                event_str = " | ".join(events_list) if events_list else ""
                
            market_parts = []
            for l in legs:
                emoji = "⚪"
                if l['status'] == "🟢 Κερδισμένο": emoji = "🟢"
                elif l['status'] == "🔴 Χαμένο": emoji = "🔴"
                elif l['status'] == "🔵 Ακυρωμένο": emoji = "🔵"
                market_parts.append(f"{emoji} {l['market']} ({float(l['odds']):.2f})")
            market_str = " | ".join(market_parts)
        
        try:
           new_data = pd.DataFrame([{
               'Date': d, 'Time': t_string, 'Type': bet_type, 'Sport': selected_sport_input, 'Event': event_str, 'Market': market_str, 'Odds': odds, 'Stake': stake, 'Status': status, 'Profit': profit, 'Legs_Data': legs_json
           }])
           df_to_save = pd.concat([df.drop(columns=['Α/Α'], errors='ignore'), new_data], ignore_index=True)
           save_data(df_to_save)
           st.session_state['show_toast'] = True
           st.session_state['toast_message'] = "Το δελτίο καταχωρήθηκε επιτυχώς!"
           st.session_state['form_reset_counter'] += 1 
           st.session_state['auto_odds_multi'] = 1.0
           st.rerun()
        except Exception as e:
           st.error(f"❌ Υπήρξε πρόβλημα: {e}")

# ==========================================
# 🗂️ SIDEBAR REVAMP
# ==========================================
st.sidebar.markdown("<div class='sidebar-header'>🚀 ΠΛΟΗΓΗΣΗ</div>", unsafe_allow_html=True)
page = st.sidebar.radio("", ["📊 Dashboard & Στατιστικά", "⚡ Ανοιχτά Δελτία (Εκκρεμή)", "🗓️ Μηνιαία Αναφορά", "⚙️ Διαχείριση Ιστορικού"], key="page_sel", label_visibility="collapsed")

st.sidebar.markdown("<div class='sidebar-header'>🏦 ΚΕΦΑΛΑΙΟ (BANKROLL)</div>", unsafe_allow_html=True)
starting_bankroll = st.sidebar.number_input("Αρχική Κάβα (€)", value=0.0, step=10.0, format="%.2f")

st.sidebar.markdown("<div class='sidebar-header'>🛠️ ΕΞΥΠΝΑ ΦΙΛΤΡΑ</div>", unsafe_allow_html=True)
quick_date = st.sidebar.radio("⏱️ Χρονικό Διάστημα", ["Όλα", "Σήμερα", "Τελευταίες 7 Ημέρες", "Αυτός ο Μήνας", "Χειροκίνητα..."])
if quick_date == "Όλα":
    min_d = df['Date'].min() if not df.empty else date.today()
    max_d = df['Date'].max() if not df.empty else date.today()
    date_filter = (min_d, max_d)
elif quick_date == "Σήμερα":
    date_filter = (date.today(), date.today())
elif quick_date == "Τελευταίες 7 Ημέρες":
    date_filter = (date.today() - timedelta(days=7), date.today())
elif quick_date == "Αυτός ο Μήνας":
    date_filter = (date.today().replace(day=1), date.today())
else:
    min_d = df['Date'].min() if not df.empty else date.today()
    max_d = df['Date'].max() if not df.empty else date.today()
    date_filter = st.sidebar.date_input("📅 Επιλογή Ημερομηνιών", value=(min_d, max_d), format="DD/MM/YYYY")

search_event = st.sidebar.text_input("🔍 Λέξη-Κλειδί (Ομάδα/Αγώνας/Παίκτης)")
sports_list = ["Όλα"] + sorted(df['Sport'].dropna().astype(str).unique().tolist())
selected_sport = st.sidebar.selectbox("🎯 Άθλημα", sports_list)
types_list = ["Όλοι οι Τύποι"] + sorted(df['Type'].dropna().astype(str).unique().tolist())
selected_type = st.sidebar.selectbox("🎫 Τύπος Συστήματος", types_list)

filtered_df = df.copy()

if isinstance(date_filter, tuple) and len(date_filter) == 2:
    filtered_df = filtered_df[(filtered_df['Date'] >= date_filter[0]) & (filtered_df['Date'] <= date_filter[1])]
elif isinstance(date_filter, tuple) and len(date_filter) == 1:
    filtered_df = filtered_df[filtered_df['Date'] >= date_filter[0]]
else:
    filtered_df = filtered_df[filtered_df['Date'] == date_filter]

if search_event: 
    filtered_df = filtered_df[
        filtered_df['Event'].str.contains(search_event, case=False, na=False) | 
        filtered_df['Market'].str.contains(search_event, case=False, na=False) | 
        filtered_df['Legs_Data'].astype(str).str.contains(search_event, case=False, na=False)
    ]

if selected_sport != "Όλα": filtered_df = filtered_df[filtered_df['Sport'] == selected_sport]
if selected_type != "Όλοι οι Τύποι": filtered_df = filtered_df[filtered_df['Type'] == selected_type]

# ==========================================
# MAIN APP BODY
# ==========================================
st.title("📈 Στοιχηματικό Dashboard")

st.markdown('<div class="fab-marker"></div>', unsafe_allow_html=True)
if st.button("➕ ΝΕΟ ΣΤΟΙΧΗΜΑ", type="primary", use_container_width=True):
    new_bet_dialog()

# ----------------- ΣΕΛΙΔΕΣ -----------------
if page == "📊 Dashboard & Στατιστικά":
    st.header("🏠 Στατιστικά & Αναλύσεις")
    if filtered_df.empty:
        st.warning("Δεν βρέθηκαν στοιχήματα για αυτά τα φίλτρα.")
    else:
        completed_bets = filtered_df[filtered_df['Status'].isin(["🟢 Κερδισμένο", "🔴 Χαμένο", "🟡 Cash Out", "🔵 Ακυρωμένο"])]
        total_profit = filtered_df['Profit'].sum()
        current_balance = starting_bankroll + total_profit
        total_staked = completed_bets['Stake'].sum()
        yield_pct = (total_profit / total_staked * 100) if total_staked > 0 else 0
        wl_bets = completed_bets[completed_bets['Status'].isin(["🟢 Κερδισμένο", "🔴 Χαμένο"])]
        
        count_won = len(filtered_df[filtered_df['Status'] == "🟢 Κερδισμένο"])
        count_lost = len(filtered_df[filtered_df['Status'] == "🔴 Χαμένο"])
        count_cashout = len(filtered_df[filtered_df['Status'] == "🟡 Cash Out"])
        count_void = len(filtered_df[filtered_df['Status'] == "🔵 Ακυρωμένο"])
        count_pending = len(filtered_df[filtered_df['Status'] == "⚪ Εκκρεμές"])
        
        win_rate = (len(wl_bets[wl_bets['Profit'] > 0]) / len(wl_bets) * 100) if len(wl_bets) > 0 else 0
        total_bets = len(completed_bets)
        avg_odds = filtered_df['Odds'].mean()
        
        profit_delta, roi_delta, win_rate_delta, odds_delta = None, None, None, None

        if len(filtered_df) > 1:
            temp_df = filtered_df.copy()
            temp_df['DateTime'] = pd.to_datetime(temp_df['Date'].astype(str) + ' ' + temp_df['Time'].astype(str), errors='coerce')
            temp_df = temp_df.sort_values(by="DateTime")
            prev_f = temp_df.iloc[:-1]
            odds_delta = avg_odds - prev_f['Odds'].mean()
            profit_delta = total_profit - prev_f['Profit'].sum()
            prev_c = prev_f[prev_f['Status'].isin(["🟢 Κερδισμένο", "🔴 Χαμένο", "🟡 Cash Out", "🔵 Ακυρωμένο"])]
            prev_staked = prev_c['Stake'].sum()
            prev_yield = (prev_f['Profit'].sum() / prev_staked * 100) if prev_staked > 0 else 0
            roi_delta = yield_pct - prev_yield
            prev_wl = prev_c[prev_c['Status'].isin(["🟢 Κερδισμένο", "🔴 Χαμένο"])]
            prev_wr = (len(prev_wl[prev_wl['Profit'] > 0]) / len(prev_wl) * 100) if len(prev_wl) > 0 else 0
            win_rate_delta = win_rate - prev_wr

        winning_bets = filtered_df[filtered_df['Status'] == "🟢 Κερδισμένο"]
        completed_bets['DateTime'] = pd.to_datetime(completed_bets['Date'].astype(str) + ' ' + completed_bets['Time'].astype(str))
        prog_df = completed_bets.sort_values(by="DateTime").copy()
        
        cum_profit, cum_stake, cum_roi, cum_wr, cum_avg = [], [], [], [], []
        current_p, current_s, current_wl_count, current_wins = 0.0, 0.0, 0, 0
        cum_o_sum, cum_o_count = 0.0, 0
        peaks, drawdowns, current_peak = [], [], 0.0
        
        for idx, row in prog_df.iterrows():
            current_p += row['Profit']
            if row['Status'] != "🔵 Ακυρωμένο":
                current_s += row['Stake']
                cum_o_sum += row['Odds']
                cum_o_count += 1
            status = row['Status']
            if status in ["🟢 Κερδισμένο", "🔴 Χαμένο"]:
                current_wl_count += 1
                if status == "🟢 Κερδισμένο": current_wins += 1
            
            if current_p > current_peak: current_peak = current_p
            dd = current_p - current_peak 
            
            peaks.append(current_peak)
            drawdowns.append(dd)
            cum_profit.append(current_p)
            cum_stake.append(current_s)
            cum_roi.append((current_p / current_s * 100) if current_s > 0 else 0.0)
            cum_wr.append((current_wins / current_wl_count * 100) if current_wl_count > 0 else 0.0)
            cum_avg.append((cum_o_sum / cum_o_count) if cum_o_count > 0 else 0.0)

        prog_df['Cumulative_Profit'] = cum_profit
        prog_df['Balance'] = [starting_bankroll + cp for cp in cum_profit]
        prog_df['Cumulative_Stake'] = cum_stake
        prog_df['Cumulative_ROI'] = cum_roi
        prog_df['Cumulative_WR'] = cum_wr
        prog_df['Cumulative_AvgOdds'] = cum_avg
        prog_df['Peak'] = peaks
        prog_df['Drawdown'] = drawdowns
        
        max_drawdown = min(drawdowns) if drawdowns else 0.0
        peak_bankroll = (starting_bankroll + max(peaks)) if peaks else starting_bankroll
        prog_df = prog_df.sort_values(by="DateTime", ascending=False)

        max_single_profit = winning_bets['Profit'].max() if not winning_bets.empty else 0.0
        max_profit_aa = winning_bets.loc[winning_bets['Profit'].idxmax(), 'Α/Α'] if not winning_bets.empty else None
        max_win_odds = winning_bets['Odds'].max() if not winning_bets.empty else 0.0
        max_win_odds_aa = winning_bets.loc[winning_bets['Odds'].idxmax(), 'Α/Α'] if not winning_bets.empty else None

        max_win_streak, max_lose_streak = 0, 0
        current_w, current_l = 0, 0
        win_streak_idx, lose_streak_idx = [], []
        curr_w_idx, curr_l_idx = [], []
        for idx, row in completed_bets.sort_values(by="DateTime").iterrows():
            status = row['Status']
            if status == "🟢 Κερδισμένο":
                current_w += 1; curr_w_idx.append(row['Α/Α'])
                current_l = 0; curr_l_idx = []
                if current_w > max_win_streak: max_win_streak = current_w; win_streak_idx = curr_w_idx.copy()
            elif status == "🔴 Χαμένο":
                current_l += 1; curr_l_idx.append(row['Α/Α'])
                current_w = 0; curr_w_idx = []
                if current_l > max_lose_streak: max_lose_streak = current_l; lose_streak_idx = curr_l_idx.copy()
            else: 
                current_w = 0; curr_w_idx = []; current_l = 0; curr_l_idx = []

        st.markdown("### 🏆 Στατιστικά Ταμείου & Money Management")
        
        col_a, col_b, col_c, col_d = st.columns(4)
        p_delta_str = f"\n( Κέρδος: 🟢 +{profit_delta:.2f} € )" if profit_delta and profit_delta > 0 else (f"\n( Ζημιά: 🔴 {profit_delta:.2f} € )" if profit_delta else "")
        st.markdown('<div class="marker-positive"></div>' if total_profit >= 0 else '<div class="marker-negative"></div>', unsafe_allow_html=True)
        if col_a.button(f"Καθαρό Κέρδος\n{total_profit:.2f} €{p_delta_str}", key="btn_prof", use_container_width=True):
            show_progression_dialog("profit", prog_df, df)

        st.markdown('<div class="marker-positive"></div>' if current_balance >= starting_bankroll else '<div class="marker-negative"></div>', unsafe_allow_html=True)
        if col_b.button(f"Τρέχον Υπόλοιπο\n{current_balance:.2f} €", key="btn_bal", use_container_width=True):
            show_progression_dialog("profit", prog_df, df)

        r_delta_str = f"\n( 🟢 +{roi_delta:.2f} % )" if roi_delta and roi_delta > 0 else (f"\n( 🔴 {roi_delta:.2f} % )" if roi_delta else "")
        st.markdown('<div class="marker-positive"></div>' if roi_delta and roi_delta > 0 else ('<div class="marker-negative"></div>' if roi_delta else ''), unsafe_allow_html=True)
        if col_c.button(f"Yield (ROI)\n{yield_pct:.2f} %{r_delta_str}", key="btn_roi", use_container_width=True):
            show_progression_dialog("roi", prog_df, df)

        w_delta_str = f"\n( 🟢 +{win_rate_delta:.1f} % )" if win_rate_delta and win_rate_delta > 0 else (f"\n( 🔴 {win_rate_delta:.1f} % )" if win_rate_delta else "")
        st.markdown('<div class="marker-positive"></div>' if win_rate_delta and win_rate_delta > 0 else ('<div class="marker-negative"></div>' if win_rate_delta else ''), unsafe_allow_html=True)
        if col_d.button(f"Win Rate\n{win_rate:.1f} %{w_delta_str}", key="btn_wr", use_container_width=True):
            show_progression_dialog("wr", prog_df, df)
        
        col_e, col_f, col_g, col_h = st.columns(4)
        st.markdown('<div class="marker-neutral"></div>', unsafe_allow_html=True)
        if col_e.button(f"Συνολικό Ποντάρισμα\n{total_staked:.2f} €", key="btn_staked", use_container_width=True):
            show_bets_dialog("💰 Όλα τα Πονταρισμένα Δελτία", completed_bets, df)

        st.markdown('<div class="marker-negative"></div>', unsafe_allow_html=True)
        if col_f.button(f"Max Drawdown\n{max_drawdown:.2f} € 📉", key="btn_dd", use_container_width=True):
            show_progression_dialog("drawdown", prog_df, df)

        st.markdown('<div class="marker-gold"></div>', unsafe_allow_html=True)
        if col_g.button(f"Κορυφή Ταμείου (ATH)\n{peak_bankroll:.2f} € 🏔️", key="btn_ath", use_container_width=True):
            show_progression_dialog("profit", prog_df, df)

        st.markdown('<div class="marker-neutral"></div>', unsafe_allow_html=True)
        if col_h.button(f"Σύνολο Στοιχημάτων\n{total_bets}", key="btn_all", use_container_width=True):
            show_bets_dialog("📋 Όλα τα Διευθετημένα Δελτία", completed_bets, df)

        col_i, col_j, col_k, col_l = st.columns(4)
        st.markdown('<div class="marker-positive"></div>', unsafe_allow_html=True)
        if col_i.button(f"Μέγιστο Σερί Νικών\n{max_win_streak} 🟢", key="btn_w_streak", use_container_width=True): 
            show_bets_dialog(f"🟢 Μέγιστο Σερί Νικών ({max_win_streak} δελτία)", df[df['Α/Α'].isin(win_streak_idx)], df)
        
        st.markdown('<div class="marker-negative"></div>', unsafe_allow_html=True)
        if col_j.button(f"Μέγιστο Σερί Ηττών\n{max_lose_streak} 🔴", key="btn_l_streak", use_container_width=True): 
            show_bets_dialog(f"🔴 Μέγιστο Σερί Ηττών ({max_lose_streak} δελτία)", df[df['Α/Α'].isin(lose_streak_idx)], df)
        
        o_delta_str = f"\n( 🟢 +{odds_delta:.2f} )" if odds_delta and odds_delta > 0 else (f"\n( 🔴 {odds_delta:.2f} )" if odds_delta else "")
        st.markdown('<div class="marker-positive"></div>' if odds_delta and odds_delta > 0 else ('<div class="marker-negative"></div>' if odds_delta else ''), unsafe_allow_html=True)
        if col_k.button(f"Μέση Απόδοση\n{avg_odds:.2f}{o_delta_str}", key="btn_avg_odds", use_container_width=True):
            show_progression_dialog("avg_odds", prog_df, df)
        
        st.markdown('<div class="marker-positive"></div>', unsafe_allow_html=True)
        if col_l.button(f"Μέγιστη Απόδοση Δελτίου\n{max_win_odds:.2f} 🎯", key="btn_max_odds", use_container_width=True): 
            if max_win_odds_aa:
                st.session_state['redirect_to'] = "🗓️ Μηνιαία Αναφορά"
                st.session_state['auto_open_ticket'] = int(max_win_odds_aa)
                st.rerun()
            else:
                st.toast("Δεν υπάρχει κερδισμένο δελτίο!", icon="⚠️")

        # 🧠 FUN FACTS & INSIGHTS
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("### 🧠 Fun Facts & Insights (Ειδικά Στατιστικά)")
        
        daily_profits_grouped = completed_bets.groupby('Date')['Profit'].sum().reset_index().sort_values('Date')
        max_pos_days, max_neg_days = 0, 0
        cur_pos, cur_neg = 0, 0
        cur_pos_dates, cur_neg_dates = [], []
        max_pos_dates, max_neg_dates = [], []

        for idx, row in daily_profits_grouped.iterrows():
            p = row['Profit']
            d = row['Date']
            if p > 0:
                cur_pos += 1; cur_pos_dates.append(d)
                cur_neg = 0; cur_neg_dates = []
                if cur_pos > max_pos_days: max_pos_days = cur_pos; max_pos_dates = cur_pos_dates.copy()
            elif p < 0:
                cur_neg += 1; cur_neg_dates.append(d)
                cur_pos = 0; cur_pos_dates = []
                if cur_neg > max_neg_days: max_neg_days = cur_neg; max_neg_dates = cur_neg_dates.copy()
            else:
                cur_pos, cur_neg = 0, 0; cur_pos_dates, cur_neg_dates = [], []

        team_profits = {}
        player_profits = {}
        
        def process_entities(ev_main, ma_str, profit_to_add):
            ev_main = str(ev_main).split("(")[0].strip()
            found_teams = False
            for delim in [' - ', ' vs ', '-']:
                if delim in ev_main and len(ev_main.split(delim)) == 2:
                    parts = ev_main.split(delim)
                    t1, t2 = parts[0].strip(), parts[1].strip()
                    if t1: team_profits[t1] = team_profits.get(t1, 0.0) + profit_to_add
                    if t2: team_profits[t2] = team_profits.get(t2, 0.0) + profit_to_add
                    found_teams = True
                    break
            if not found_teams and ev_main and len(ev_main) > 2:
                team_profits[ev_main] = team_profits.get(ev_main, 0.0) + profit_to_add

            if pd.notna(ma_str) and str(ma_str).strip() != "":
                for m_part in str(ma_str).split('|'):
                    m_clean = re.sub(r'[^\w\s-]', '', m_part).strip()
                    words = m_clean.split()
                    p_name = []
                    for w in words:
                        if re.search(r'\d', w) or (w and ''.join(c for c in unicodedata.normalize('NFD', w) if unicodedata.category(c) != 'Mn').lower().strip() in ignore_words_set): break
                        p_name.append(w)
                    final_p = " ".join(p_name).strip()
                    if final_p and len(final_p) > 2 and final_p.lower() not in ["home", "away", "draw", "νικη", "ισοπαλια", "yes", "no"]:
                        player_profits[final_p] = player_profits.get(final_p, 0.0) + profit_to_add

        for idx, row in completed_bets.iterrows():
            ticket_prof = float(row['Profit'])
            ticket_status = row['Status']
            stake = float(row['Stake'])
            if row['Type'] == "Μονό": process_entities(row['Event'], row['Market'], ticket_prof)
            else:
                legs_str = row['Legs_Data']
                if pd.notna(legs_str) and legs_str.strip() != "":
                    try:
                        legs = json.loads(legs_str)
                        lost_legs_count = sum(1 for l in legs if "Χαμένο" in l.get('status', ''))
                        for leg in legs:
                            leg_st = leg.get('status', '')
                            if ticket_status == "🟢 Κερδισμένο": leg_profit = ticket_prof 
                            elif ticket_status == "🔴 Χαμένο":
                                if "Χαμένο" in leg_st: leg_profit = -stake / lost_legs_count if lost_legs_count > 0 else -stake
                                else: leg_profit = 0.0 
                            elif ticket_status == "🟡 Cash Out": leg_profit = ticket_prof
                            else: leg_profit = 0.0
                            process_entities(leg.get('event', row['Event']), leg.get('market', ''), leg_profit)
                    except: pass

        best_team, best_team_prof = max(team_profits.items(), key=lambda x: x[1]) if team_profits else ("-", 0.0)
        worst_team, worst_team_prof = min(team_profits.items(), key=lambda x: x[1]) if team_profits else ("-", 0.0)
        best_player, best_player_prof = max(player_profits.items(), key=lambda x: x[1]) if player_profits else ("-", 0.0)
        worst_player, worst_player_prof = min(player_profits.items(), key=lambda x: x[1]) if player_profits else ("-", 0.0)

        best_team_disp = best_team[:18] + ".." if len(best_team) > 18 else best_team
        worst_team_disp = worst_team[:18] + ".." if len(worst_team) > 18 else worst_team
        best_player_disp = best_player[:18] + ".." if len(best_player) > 18 else best_player
        worst_player_disp = worst_player[:18] + ".." if len(worst_player) > 18 else worst_player

        c_ff1, c_ff2, c_ff3, c_ff4 = st.columns(4)
        st.markdown('<div class="marker-positive"></div>', unsafe_allow_html=True)
        if c_ff1.button(f"☀️ Σερί Θετικών Ημερών\n{max_pos_days} Μέρες", key="btn_ff_pos", use_container_width=True):
            if max_pos_days > 0: show_bets_dialog(f"☀️ Στοιχήματα ({max_pos_days} Κερδοφόρες Μέρες)", completed_bets[completed_bets['Date'].isin(max_pos_dates)], df)
            else: st.toast("Δεν υπάρχει σερί θετικών ημερών ακόμα!", icon="⚠️")
                
        st.markdown('<div class="marker-negative"></div>', unsafe_allow_html=True)
        if c_ff2.button(f"⛈️ Σερί Αρνητικών Ημερών\n{max_neg_days} Μέρες", key="btn_ff_neg", use_container_width=True):
            if max_neg_days > 0: show_bets_dialog(f"⛈️ Στοιχήματα ({max_neg_days} Ζημιογόνες Μέρες)", completed_bets[completed_bets['Date'].isin(max_neg_dates)], df)
            else: st.toast("Δεν υπάρχει σερί αρνητικών ημερών ακόμα!", icon="⚠️")

        st.markdown('<div class="marker-gold"></div>', unsafe_allow_html=True)
        if c_ff3.button(f"🏆 Χρυσή Ομάδα\n{best_team_disp} (+{best_team_prof:.2f} €)" if best_team_prof > 0 else "🏆 Χρυσή Ομάδα\n-", key="btn_ff_best", use_container_width=True):
            if best_team_prof > 0:
                team_df = completed_bets[completed_bets['Event'].str.contains(best_team, na=False) | completed_bets['Legs_Data'].str.contains(best_team, na=False)]
                show_bets_dialog(f"🏆 Ιστορικό: Αγώνες με {best_team}", team_df, df)
            else: st.toast("Δεν υπάρχει ακόμα κερδοφόρα ομάδα!", icon="⚠️")

        st.markdown('<div class="marker-dark"></div>', unsafe_allow_html=True)
        if c_ff4.button(f"🧊 Μαύρη Λίστα Ομάδων\n{worst_team_disp} ({worst_team_prof:.2f} €)" if worst_team_prof < 0 else "🧊 Μαύρη Λίστα\n-", key="btn_ff_worst", use_container_width=True):
            if worst_team_prof < 0:
                team_df = completed_bets[completed_bets['Event'].str.contains(worst_team, na=False) | completed_bets['Legs_Data'].str.contains(worst_team, na=False)]
                show_bets_dialog(f"🧊 Ιστορικό: Αγώνες με {worst_team}", team_df, df)
            else: st.toast("Δεν υπάρχει ακόμα ζημιογόνα ομάδα!", icon="⚠️")
                
        c_ff5, c_ff6, c_ff7, c_ff8 = st.columns(4)
        st.markdown('<div class="marker-player1"></div>', unsafe_allow_html=True)
        if c_ff5.button(f"🥇 MVP Παίκτης / Ειδικό\n{best_player_disp} (+{best_player_prof:.2f} €)" if best_player_prof > 0 else "🥇 MVP Παίκτης\n-", key="btn_ff_pbest", use_container_width=True):
            if best_player_prof > 0:
                p_df = completed_bets[completed_bets['Market'].str.contains(best_player, na=False) | completed_bets['Legs_Data'].str.contains(best_player, na=False)]
                show_bets_dialog(f"🥇 Ιστορικό: Στοιχήματα σε {best_player}", p_df, df)
            else: st.toast("Δεν υπάρχει κερδοφόρος παίκτης!", icon="⚠️")
                
        st.markdown('<div class="marker-player2"></div>', unsafe_allow_html=True)
        if c_ff6.button(f"📉 Χειρότερος Παίκτης\n{worst_player_disp} ({worst_player_prof:.2f} €)" if worst_player_prof < 0 else "📉 Χειρότερος Παίκτης\n-", key="btn_ff_pworst", use_container_width=True):
            if worst_player_prof < 0:
                p_df = completed_bets[completed_bets['Market'].str.contains(worst_player, na=False) | completed_bets['Legs_Data'].str.contains(worst_player, na=False)]
                show_bets_dialog(f"📉 Ιστορικό: Στοιχήματα σε {worst_player}", p_df, df)
            else: st.toast("Δεν υπάρχει ζημιογόνος παίκτης!", icon="⚠️")

        # 🧠 ΑΝΑΤΟΜΙΑ ΣΤΟΙΧΗΜΑΤΩΝ
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("---")
        st.markdown("### 🎯 Ανατομία Στοιχημάτων")
        col_s, col_o = st.columns(2)
        
        with col_s:
            st.markdown("#### 🏀 Ανάλυση ανά Άθλημα")
            sport_stats = []
            for sport in completed_bets['Sport'].unique():
                s_df = completed_bets[completed_bets['Sport'] == sport]
                s_profit = s_df['Profit'].sum()
                s_staked = s_df['Stake'].sum()
                s_roi = (s_profit / s_staked * 100) if s_staked > 0 else 0
                s_wl = s_df[s_df['Status'].isin(["🟢 Κερδισμένο", "🔴 Χαμένο"])]
                s_wr = (len(s_wl[s_wl['Profit'] > 0]) / len(s_wl) * 100) if len(s_wl) > 0 else 0
                sport_stats.append({"Άθλημα": sport, "Δελτία": len(s_df), "Win Rate (%)": s_wr, "ROI (%)": s_roi, "Κέρδος (€)": s_profit})
            if sport_stats:
                sport_df = pd.DataFrame(sport_stats).sort_values(by="Κέρδος (€)", ascending=False)
                cfg_sport = {
                    "Win Rate (%)": st.column_config.ProgressColumn("Win Rate", format="%.1f%%", min_value=0, max_value=100),
                    "ROI (%)": st.column_config.NumberColumn("ROI", format="%.1f%%"),
                    "Κέρδος (€)": st.column_config.NumberColumn("Κέρδος", format="%.2f €")
                }
                st.dataframe(sport_df, use_container_width=True, hide_index=True, column_config=cfg_sport)
            else: st.info("Δεν υπάρχουν ολοκληρωμένα δελτία για ανάλυση αθλημάτων.")

        with col_o:
            st.markdown("#### ⚖️ Ανάλυση Αποδόσεων")
            bins = [0.0, 1.49, 1.99, 2.99, 9999.0]
            labels = ["< 1.50 (Safe)", "1.50 - 1.99 (Medium)", "2.00 - 2.99 (High)", "3.00+ (Bomb)"]
            completed_bets['Odds_Bracket'] = pd.cut(completed_bets['Odds'], bins=bins, labels=labels)
            odds_stats = []
            for bracket in labels:
                o_df = completed_bets[completed_bets['Odds_Bracket'] == bracket]
                if o_df.empty: continue
                o_profit = o_df['Profit'].sum()
                o_wl = o_df[o_df['Status'].isin(["🟢 Κερδισμένο", "🔴 Χαμένο"])]
                o_wr = (len(o_wl[o_wl['Profit'] > 0]) / len(o_wl) * 100) if len(o_wl) > 0 else 0
                odds_stats.append({"Εύρος Απόδοσης": bracket, "Δελτία": len(o_df), "Win Rate (%)": o_wr, "Κέρδος (€)": o_profit})
            odds_df = pd.DataFrame(odds_stats)
            if not odds_df.empty:
                cfg_odds = {
                    "Win Rate (%)": st.column_config.ProgressColumn("Win Rate", format="%.1f%%", min_value=0, max_value=100),
                    "Κέρδος (€)": st.column_config.NumberColumn("Κέρδος", format="%.2f €")
                }
                st.dataframe(odds_df, use_container_width=True, hide_index=True, column_config=cfg_odds)
            else: st.info("Δεν υπάρχουν δεδομένα αποδόσεων.")

        st.markdown("---")
        st.markdown("### 📊 Ανάλυση Αποτελεσμάτων")
        c_w, c_l, c_c, c_v, c_p = st.columns(5)
        st.markdown('<div class="marker-positive"></div>', unsafe_allow_html=True)
        if c_w.button(f"🟢 Κερδισμένα\n{count_won}", key="btn_won", use_container_width=True): show_bets_dialog("🟢 Όλα τα Κερδισμένα", filtered_df[filtered_df['Status'] == "🟢 Κερδισμένο"], df)
        st.markdown('<div class="marker-negative"></div>', unsafe_allow_html=True)
        if c_l.button(f"🔴 Χαμένα\n{count_lost}", key="btn_lost", use_container_width=True): show_bets_dialog("🔴 Όλα τα Χαμένα", filtered_df[filtered_df['Status'] == "🔴 Χαμένο"], df)
        st.markdown('<div class="marker-warning"></div>', unsafe_allow_html=True)
        if c_c.button(f"🟡 Cash Out\n{count_cashout}", key="btn_co", use_container_width=True): show_bets_dialog("🟡 Όλα τα Cash Out", filtered_df[filtered_df['Status'] == "🟡 Cash Out"], df)
        st.markdown('<div class="marker-info"></div>', unsafe_allow_html=True)
        if c_v.button(f"🔵 Ακυρωμένα\n{count_void}", key="btn_void", use_container_width=True): show_bets_dialog("🔵 Όλα τα Ακυρωμένα", filtered_df[filtered_df['Status'] == "🔵 Ακυρωμένο"], df)
        st.markdown('<div class="marker-neutral"></div>', unsafe_allow_html=True)
        if c_p.button(f"⚪ Εκκρεμή\n{count_pending}", key="btn_pending", use_container_width=True): show_bets_dialog("⚪ Όλα τα Εκκρεμή", filtered_df[filtered_df['Status'] == "⚪ Εκκρεμές"], df)

        st.markdown("---")
        col_chart1, col_chart2 = st.columns(2)
        with col_chart1:
            st.markdown("### 📉 Εξέλιξη Ταμείου")
            chart_mode = st.radio("Επιλογή Προβολής:", ["Καθαρό Κέρδος", "Τρέχον Υπόλοιπο (Με Κάβα)"], horizontal=True, label_visibility="collapsed")
            if not completed_bets.empty:
                y_col = 'Cumulative_Profit' if chart_mode == "Καθαρό Κέρδος" else 'Balance'
                y_title = "Καθαρό Κέρδος (€)" if chart_mode == "Καθαρό Κέρδος" else "Υπόλοιπο (€)"
                zero_val = 0.0 if chart_mode == "Καθαρό Κέρδος" else starting_bankroll
                
                df_line = prog_df.sort_values(by="DateTime").copy()
                df_line['Ημ/νια'] = pd.to_datetime(df_line['Date']).dt.strftime('%d/%m/%Y')
                df_line['Bet_Count'] = range(1, len(df_line) + 1)
                zero_point = pd.DataFrame([{'Bet_Count': 0, 'Cumulative_Profit': 0.0, 'Balance': starting_bankroll, 'Ημ/νια': '-', 'Event': 'Αρχικό Κεφάλαιο', 'Profit': 0.0}])
                df_line = pd.concat([zero_point, df_line], ignore_index=True)
                
                base = alt.Chart(df_line).encode(
                    x=alt.X('Bet_Count:Q', axis=alt.Axis(labels=False, title=None, ticks=False, grid=False)),
                    y=alt.Y(f'{y_col}:Q', title=y_title, axis=alt.Axis(gridColor="#1f2937"))
                )
                area = base.mark_area(interpolate='basis', opacity=0.3).encode(
                    color=alt.condition(alt.datum[y_col] >= zero_val, alt.value('#10b981'), alt.value('#ef4444'))
                )
                line = base.mark_line(interpolate='basis', strokeWidth=4).encode(
                    color=alt.condition(alt.datum[y_col] >= zero_val, alt.value('#4ade80'), alt.value('#ff4b4b'))
                )
                hover_points = base.mark_circle(size=300, color="transparent").encode(
                    tooltip=[alt.Tooltip('Ημ/νια:N', title='Ημερομηνία'), alt.Tooltip(f'{y_col}:Q', title=y_title, format='.2f')]
                )
                chart = (area + line + hover_points).properties(height=350)
                st.altair_chart(chart, use_container_width=True, theme="streamlit")
            else: st.info("Δεν υπάρχουν ολοκληρωμένα δελτία στο επιλεγμένο εύρος ημερομηνιών για να εμφανιστεί γράφημα.")
                
        with col_chart2:
            st.markdown("### 🗓️ Ταμείο ανά Μήνα")
            monthly_df = completed_bets.copy()
            if not monthly_df.empty:
                monthly_df['MonthStr'] = pd.to_datetime(monthly_df['Date']).apply(lambda x: f"{GREEK_MONTHS[x.month]} {x.year}")
                monthly_df['Month_Sort'] = pd.to_datetime(monthly_df['Date']).dt.strftime('%Y-%m')
                monthly_group = monthly_df.groupby(['Month_Sort', 'MonthStr'])['Profit'].sum().reset_index()
                monthly_group = monthly_group.sort_values('Month_Sort')
                monthly_group['Color'] = monthly_group['Profit'].apply(lambda x: '🟢 Κέρδος' if x >= 0 else '🔴 Ζημιά')
                
                bar_base = alt.Chart(monthly_group).encode(
                    x=alt.X('MonthStr:N', sort=alt.EncodingSortField(field='Month_Sort', order='ascending'), title=None, axis=alt.Axis(labelAngle=0, labelColor="#e2e8f0", grid=False)),
                    y=alt.Y('Profit:Q', title="Καθαρό Κέρδος (€)", axis=alt.Axis(gridColor="#1f2937", labelColor="#a8dadc")),
                )
                bars = bar_base.mark_bar(cornerRadiusTopLeft=8, cornerRadiusTopRight=8, size=40, opacity=0.9).encode(
                    color=alt.Color('Color:N', scale=alt.Scale(domain=['🟢 Κέρδος', '🔴 Ζημιά'], range=['#10b981', '#ef4444']), legend=None),
                    tooltip=[alt.Tooltip('MonthStr:N', title='Μήνας'), alt.Tooltip('Profit:Q', title='Ταμείο Μήνα', format='.2f')]
                )
                text = bar_base.mark_text(
                    align='center', baseline='middle', dy=alt.expr("datum.Profit >= 0 ? -15 : 15"), fontSize=14, fontWeight=700
                ).encode(
                    text=alt.Text('Profit:Q', format='+.2f'),
                    color=alt.condition(alt.datum.Profit >= 0, alt.value('#4ade80'), alt.value('#ff4b4b'))
                )
                st.altair_chart((bars + text).properties(height=350), use_container_width=True, theme="streamlit")
            else: st.info("Δεν υπάρχουν δεδομένα.")

elif page == "⚡ Ανοιχτά Δελτία (Εκκρεμή)":
    st.header("⏳ Κέντρο Διευθέτησης (Εκκρεμή Στοιχήματα)")
    
    pending_df = filtered_df[filtered_df['Status'] == "⚪ Εκκρεμές"].copy()
    if pending_df.empty:
        st.success("🎉 Όλα τα δελτία σου είναι διευθετημένα! Δεν χρωστάς τίποτα. Πάμε για το επόμενο ταμείο!")
    else:
        pending_count = len(pending_df)
        pending_stake = pending_df['Stake'].sum()
        pending_potential_return = (pending_df['Stake'] * pending_df['Odds']).sum()
        
        st.markdown(f"""
        <div style="display: flex; justify-content: space-between; gap: 15px; margin-bottom: 25px;">
            <div style="flex: 1; background-color: #16263b; padding: 20px; border-radius: 12px; border-left: 4px solid #3b82f6; text-align: center; box-shadow: 0 4px 6px rgba(0,0,0,0.3);">
                <p style="margin: 0; font-size: 13px; color: #a8dadc; text-transform: uppercase; letter-spacing: 1px;">Ανοιχτα Δελτια</p>
                <p style="margin: 5px 0 0 0; font-size: 26px; font-weight: 700; color: #ffffff;">{pending_count}</p>
            </div>
            <div style="flex: 1; background-color: #16263b; padding: 20px; border-radius: 12px; border-left: 4px solid #f59e0b; text-align: center; box-shadow: 0 4px 6px rgba(0,0,0,0.3);">
                <p style="margin: 0; font-size: 13px; color: #a8dadc; text-transform: uppercase; letter-spacing: 1px;">Συνολικο Ρισκο</p>
                <p style="margin: 5px 0 0 0; font-size: 26px; font-weight: 700; color: #ffffff;">{pending_stake:.2f} €</p>
            </div>
            <div style="flex: 1; background-color: #16263b; padding: 20px; border-radius: 12px; border-left: 4px solid #10b981; text-align: center; box-shadow: 0 4px 6px rgba(0,0,0,0.3);">
                <p style="margin: 0; font-size: 13px; color: #a8dadc; text-transform: uppercase; letter-spacing: 1px;">Πιθανη Επιστροφη</p>
                <p style="margin: 5px 0 0 0; font-size: 26px; font-weight: 700; color: #10b981;">{pending_potential_return:.2f} €</p>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        st.info("💡 Άλλαξε την 'Κατάσταση' απευθείας στον παρακάτω πίνακα και πάτα Αποθήκευση για να τα διευθετήσεις μαζικά.")
        
        edit_pending_df = pending_df.drop(columns=['Legs_Data'])[DISPLAY_ORDER].sort_values(by="Α/Α", ascending=False)
        edit_pending_df['Πιθανή Επιστροφή'] = edit_pending_df['Stake'] * edit_pending_df['Odds']
        
        local_col_config = GREEK_COLUMNS.copy()
        local_col_config["Πιθανή Επιστροφή"] = st.column_config.NumberColumn("Πιθανή Επιστροφή", format="%.2f €", disabled=True)
        
        edited_pending = st.data_editor(edit_pending_df, use_container_width=True, hide_index=True, column_config=local_col_config)
        
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("💾 ΟΡΙΣΤΙΚΟΠΟΙΗΣΗ ΔΕΛΤΙΩΝ", type="primary", use_container_width=True):
            changes_made = False
            for idx, row in edited_pending.iterrows():
                aa_val = row['Α/Α']
                real_idx = df.index[df['Α/Α'] == aa_val].tolist()[0]
                new_status = row['Status']
                if new_status != "⚪ Εκκρεμές" and new_status != "🟡 Cash Out":
                    if new_status == '🟢 Κερδισμένο': prof = row['Stake'] * (row['Odds'] - 1)
                    elif new_status == '🔴 Χαμένο': prof = -row['Stake']
                    elif new_status in ['🔵 Ακυρωμένο']: prof = 0.0
                    else: prof = row['Profit']
                    df.at[real_idx, 'Status'] = new_status
                    df.at[real_idx, 'Profit'] = prof
                    changes_made = True
            
            if changes_made:
                save_df = df.drop(columns=['Α/Α'], errors='ignore')
                save_df['Time'] = pd.to_datetime(save_df['Time'].astype(str), errors='coerce').dt.strftime('%H:%M').fillna('00:00')
                save_data(save_df)
                st.session_state['show_toast'] = True
                st.session_state['toast_message'] = "Τα στοιχήματα διευθετήθηκαν!"
                st.rerun()
            else:
                st.toast("Δεν κάνατε καμία αλλαγή στην Κατάσταση των δελτίων.", icon="ℹ️")

elif page == "🗓️ Μηνιαία Αναφορά":
    st.header("📋 Ιστορικό ανά Μήνα")
    
    if st.session_state.get('auto_open_ticket') is not None:
        aa = st.session_state['auto_open_ticket']
        st.session_state['auto_open_ticket'] = None
        show_ticket_modal(aa, df)
    
    if filtered_df.empty:
        st.write("Το ιστορικό είναι άδειο για αυτές τις ημερομηνίες.")
    else:
        filtered_df['MonthGroup'] = pd.to_datetime(filtered_df['Date']).dt.strftime('%Y-%m')
        months = sorted(filtered_df['MonthGroup'].dropna().unique().tolist(), reverse=True)
        month_options = {}
        for m in months:
            dt_obj = datetime.strptime(m, '%Y-%m')
            m_name = f"{GREEK_MONTHS[dt_obj.month]} {dt_obj.year}"
            month_options[m_name] = m
            
        selected_month_name = st.selectbox("🗓️ Επίλεξε Μήνα προς προβολή:", list(month_options.keys()))
        selected_month = month_options[selected_month_name]
        
        month_df = filtered_df[filtered_df['MonthGroup'] == selected_month].copy()
        month_profit = month_df['Profit'].sum()
        month_df['JustDate'] = pd.to_datetime(month_df['Date']).dt.date
        daily_profits = month_df.groupby('JustDate')['Profit'].sum().reset_index()
        best_day = daily_profits.loc[daily_profits['Profit'].idxmax()] if not daily_profits.empty else None
        worst_day = daily_profits.loc[daily_profits['Profit'].idxmin()] if not daily_profits.empty else None
        
        st.markdown(f"### 📊 Στατιστικά για: {selected_month_name}")
        c1, c2, c3, c4 = st.columns(4)
        
        st.markdown('<div class="marker-neutral"></div>', unsafe_allow_html=True)
        if c1.button(f"Συνολικό Ταμείο\n{month_profit:.2f} €", key="btn_month_prof", use_container_width=True):
            show_bets_dialog(f"🗓️ Όλα τα Δελτία ({selected_month_name})", month_df, df)
        
        if best_day is not None and worst_day is not None:
            best_date_str = best_day['JustDate'].strftime('%d/%m')
            st.markdown('<div class="marker-positive"></div>', unsafe_allow_html=True)
            if c2.button(f"🟢 Πιο Κερδοφόρα Μέρα\n{best_date_str}\n({best_day['Profit']:.2f} €)", key="btn_best_day", use_container_width=True):
                best_df = month_df[month_df['JustDate'] == best_day['JustDate']]
                show_bets_dialog(f"🟢 Πιο Κερδοφόρα Μέρα ({best_date_str})", best_df, df)
                
            worst_date_str = worst_day['JustDate'].strftime('%d/%m')
            st.markdown('<div class="marker-negative"></div>', unsafe_allow_html=True)
            if c3.button(f"🔴 Χειρότερη Μέρα\n{worst_date_str}\n({worst_day['Profit']:.2f} €)", key="btn_worst_day", use_container_width=True):
                worst_df = month_df[month_df['JustDate'] == worst_day['JustDate']]
                show_bets_dialog(f"🔴 Χειρότερη Μέρα ({worst_date_str})", worst_df, df)
        else:
            c2.button("🟢 Πιο Κερδοφόρα Μέρα\n-\n(-)", key="btn_best_null", use_container_width=True, disabled=True)
            c3.button("🔴 Χειρότερη Μέρα\n-\n(-)", key="btn_worst_null", use_container_width=True, disabled=True)
            
        st.markdown('<div class="marker-neutral"></div>', unsafe_allow_html=True)
        if c4.button(f"Σύνολο Δελτίων\n{len(month_df)}", key="btn_month_bets", use_container_width=True):
            show_bets_dialog(f"🗓️ Όλα τα Δελτία ({selected_month_name})", month_df, df)
        
        st.markdown("---")
        month_df['Week'] = pd.to_datetime(month_df['Date']).dt.isocalendar().week
        weeks = sorted(month_df['Week'].dropna().unique().tolist(), reverse=True)
        
        for w in weeks:
            week_df = month_df[month_df['Week'] == w]
            week_profit = week_df['Profit'].sum()
            wp_emoji = "🟢" if week_profit > 0 else "🔴" if week_profit < 0 else "⚪"
            min_w_date = week_df['JustDate'].min().strftime('%d/%m')
            max_w_date = week_df['JustDate'].max().strftime('%d/%m')
            
            st.markdown(f"#### 📅 {w}η Εβδομάδα ({min_w_date} - {max_w_date}) | Ταμείο: {wp_emoji} {week_profit:.2f} €")
            days = sorted(week_df['JustDate'].unique().tolist(), reverse=True)
            for day in days:
                day_df = week_df[week_df['JustDate'] == day]
                day_profit = day_df['Profit'].sum()
                day_str = f"{day.day} {GREEK_MONTHS[day.month]} {day.year}"
                if day_profit > 0: d_emoji = "🟢"; d_prof_str = f"+{day_profit:.2f}"
                elif day_profit < 0: d_emoji = "🔴"; d_prof_str = f"{day_profit:.2f}"
                else: d_emoji = "⚪"; d_prof_str = f"{day_profit:.2f}"
                    
                with st.expander(f"{d_emoji} {day_str}  |  Ημερήσιο Κέρδος: {d_prof_str} €", expanded=False):
                    st.markdown("<p style='color: #a8dadc; font-size: 13px; margin-bottom: 10px;'>💡 Κάνε κλικ σε οποιοδήποτε δελτίο για να δεις την αναλυτική απόδειξη.</p>", unsafe_allow_html=True)
                    display_df = day_df.drop(columns=['MonthGroup', 'Legs_Data', 'JustDate', 'Week'])[DISPLAY_ORDER].sort_values(by="Α/Α", ascending=False)
                    event = st.dataframe(display_df, use_container_width=True, hide_index=True, column_config=GREEK_COLUMNS, on_select="rerun", selection_mode="single-row")
                    if event.selection.rows:
                        sel_idx = event.selection.rows[0]
                        sel_aa = display_df.iloc[sel_idx]['Α/Α']
                        st.session_state['redirect_to'] = "🗓️ Μηνιαία Αναφορά"
                        st.session_state['auto_open_ticket'] = int(sel_aa)
                        st.rerun()
            st.markdown("<br>", unsafe_allow_html=True)

elif page == "⚙️ Διαχείριση Ιστορικού":
    st.header("⚙️ Κέντρο Ελέγχου (Διαχείριση Ιστορικού)")
    
    hist_count = len(filtered_df)
    hist_staked = filtered_df['Stake'].sum() if not filtered_df.empty else 0.0
    hist_profit = filtered_df['Profit'].sum() if not filtered_df.empty else 0.0
    
    st.markdown(f"""
    <div style="display: flex; justify-content: space-between; gap: 15px; margin-bottom: 25px;">
        <div style="flex: 1; background-color: #16263b; padding: 20px; border-radius: 12px; border-left: 4px solid #4db8ff; text-align: center; box-shadow: 0 4px 6px rgba(0,0,0,0.3);">
            <p style="margin: 0; font-size: 13px; color: #a8dadc; text-transform: uppercase; letter-spacing: 1px;">Καταγεγραμμενα Δελτια</p>
            <p style="margin: 5px 0 0 0; font-size: 26px; font-weight: 700; color: #ffffff;">{hist_count}</p>
        </div>
        <div style="flex: 1; background-color: #16263b; padding: 20px; border-radius: 12px; border-left: 4px solid #8b5cf6; text-align: center; box-shadow: 0 4px 6px rgba(0,0,0,0.3);">
            <p style="margin: 0; font-size: 13px; color: #a8dadc; text-transform: uppercase; letter-spacing: 1px;">Συνολικος Τζιρος</p>
            <p style="margin: 5px 0 0 0; font-size: 26px; font-weight: 700; color: #ffffff;">{hist_staked:.2f} €</p>
        </div>
        <div style="flex: 1; background-color: #16263b; padding: 20px; border-radius: 12px; border-left: 4px solid {'#10b981' if hist_profit >= 0 else '#ef4444'}; text-align: center; box-shadow: 0 4px 6px rgba(0,0,0,0.3);">
            <p style="margin: 0; font-size: 13px; color: #a8dadc; text-transform: uppercase; letter-spacing: 1px;">Καθαρο Κερδος / Ζημια</p>
            <p style="margin: 5px 0 0 0; font-size: 26px; font-weight: 700; color: {'#10b981' if hist_profit >= 0 else '#ef4444'};">{hist_profit:.2f} €</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

    tab1, tab2 = st.tabs(["📝 Επεξεργασία Μεμονωμένου Δελτίου", "⚡ Μαζική Επεξεργασία (Πίνακας)"])

    with tab1:
        st.info("💡 Επίλεξε ένα δελτίο από τη λίστα. Θα ανοίξει η ίδια ακριβώς καρτέλα με την οποία το καταχώρησες, για να αλλάξεις εύκολα ό,τι θες!")
        if not filtered_df.empty:
            edit_opts = {}
            for idx, row in filtered_df.sort_values(by="Α/Α", ascending=False).iterrows():
                d_str = row['Date'].strftime('%d/%m/%Y') if pd.notnull(row['Date']) else ""
                desc = f"Α/Α {row['Α/Α']} | {d_str} | {row['Type']} | {str(row['Event'])[:35]}"
                edit_opts[desc] = row['Α/Α']
                
            selected_edit_desc = st.selectbox("Επίλεξε Δελτίο προς επεξεργασία:", list(edit_opts.keys()), key="full_edit_select")
            if selected_edit_desc:
                selected_aa = edit_opts[selected_edit_desc]
                real_idx = df.index[df['Α/Α'] == selected_aa].tolist()[0]
                row_data = df.loc[real_idx]
                
                e_type = row_data['Type']
                e_date = row_data['Date']
                e_time = row_data['Time']
                if pd.isna(e_time): e_time = datetime.now().time()
                e_sport = row_data['Sport']
                e_event = row_data['Event']
                e_market = row_data['Market']
                e_odds = float(row_data['Odds'])
                e_stake = float(row_data['Stake'])
                e_status = row_data['Status']
                e_profit = float(row_data['Profit'])
                e_legs_data = row_data['Legs_Data']
                
                e_legs = []
                if pd.notna(e_legs_data) and e_legs_data != '' and str(e_legs_data) != 'nan':
                    try: e_legs = json.loads(e_legs_data)
                    except: pass
                    
                with st.container(border=True):
                    type_idx = BET_TYPES.index(e_type) if e_type in BET_TYPES else 0
                    edit_bet_type = st.radio("Τύπος Στοιχήματος", BET_TYPES, horizontal=True, index=type_idx, key=f"ed_type_{selected_aa}")
                    edit_num_legs = len(e_legs) if len(e_legs) >= 2 else 2
                    if edit_bet_type != "Μονό":
                        edit_num_legs = st.number_input("Πόσα σημεία (ή αγώνες) έχει το δελτίο;", min_value=2, max_value=15, value=int(edit_num_legs), key=f"ed_legs_num_{selected_aa}")
                        
                    st.markdown("<h5 style='color: #a8dadc; border-bottom: 1px solid #1e3a5f; padding-bottom: 5px; margin-top: 15px;'>1. Βασικά Στοιχεία</h5>", unsafe_allow_html=True)
                    c1, c2, c3, c4 = st.columns([2, 2, 3, 3])
                    ed_d = c1.date_input("Ημερομηνία", e_date, format="DD/MM/YYYY", key=f"ed_date_{selected_aa}")
                    ed_t = c2.time_input("Ώρα", e_time, step=60, key=f"ed_time_{selected_aa}")
                    sport_idx = list(SPORT_ICONS.values()).index(e_sport) if e_sport in SPORT_ICONS.values() else list(SPORT_ICONS.values()).index("🏀 Μπάσκετ")
                    ed_sport = c3.selectbox("Άθλημα", list(SPORT_ICONS.values()), index=sport_idx, key=f"ed_sport_{selected_aa}")
                    entry_mode_ed = c4.selectbox("Εισαγωγή Δεδομένων:", ["🤖 Έξυπνος Βοηθός", "✍️ Ελεύθερο Κείμενο"], index=1, key=f"ed_entry_mode_{selected_aa}")
                    
                    new_legs = []
                    final_ev_str, final_ma_str = "" , ""
                    st.markdown("---")
                    
                    if edit_bet_type == "Μονό":
                        st.markdown("<h5 style='color: #a8dadc; border-bottom: 1px solid #1e3a5f; padding-bottom: 5px; margin-top: 15px;'>2. Αγώνας & Αγορά (Επεξεργασία)</h5>", unsafe_allow_html=True)
                        c_ev, c_ma = st.columns(2)
                        final_ev_str = render_event_input(ed_sport, f"ed_ev_{selected_aa}", entry_mode_ed, c_ev)
                        final_ma_str = render_market_input(ed_sport, f"ed_ma_{selected_aa}", entry_mode_ed, final_ev_str, c_ma, prefill=e_market)
                            
                    elif edit_bet_type == "Bet Builder":
                        st.markdown("<h5 style='color: #a8dadc; border-bottom: 1px solid #1e3a5f; padding-bottom: 5px; margin-top: 15px;'>2. Κοινός Αγώνας & Σημεία</h5>", unsafe_allow_html=True)
                        c_ev, _ = st.columns(2)
                        bb_ev = e_legs[0]['event'] if e_legs and 'event' in e_legs[0] else e_event
                        bb_ev_clean = bb_ev.split(" (")[0] if " (" in bb_ev else bb_ev
                        
                        final_ev_str = render_event_input(ed_sport, f"ed_bb_ev_{selected_aa}", entry_mode_ed, c_ev)
                        st.markdown("<br>", unsafe_allow_html=True)
                        
                        for i in range(int(edit_num_legs)):
                            cc2, cc3, cc4 = st.columns([3,1,2]) 
                            leg_ma = e_legs[i]['market'] if i < len(e_legs) else ""
                            leg_od = float(e_legs[i]['odds']) if i < len(e_legs) else 1.50
                            leg_st = e_legs[i]['status'] if i < len(e_legs) and 'status' in e_legs[i] else "⚪ Εκκρεμές"
                            
                            l_ma_final = render_market_input(ed_sport, f"ed_bb_lma_{i}_{selected_aa}", entry_mode_ed, final_ev_str, cc2, prefill=leg_ma)
                            l_od_final = cc3.number_input(f"Απόδοση {i+1}", min_value=1.00, step=0.01, value=leg_od, key=f"ed_bb_lod_{i}_{selected_aa}")
                            st_idx = STATUS_LIST.index(leg_st) if leg_st in STATUS_LIST else 0
                            l_st_final = cc4.selectbox(f"Κατάστ. {i+1}", STATUS_LIST, index=st_idx, key=f"ed_bb_lst_{i}_{selected_aa}")
                            new_legs.append({"event": final_ev_str, "market": l_ma_final, "odds": l_od_final, "status": l_st_final})

                    elif edit_bet_type == "Παρολί με Bet Builders":
                        st.markdown("<h5 style='color: #a8dadc; border-bottom: 1px solid #1e3a5f; padding-bottom: 5px; margin-top: 15px;'>2. Αγώνες & Σημεία (Bet Builders)</h5>", unsafe_allow_html=True)
                        temp_odds = 1.0
                        for i in range(int(edit_num_legs)):
                            leg_ev = e_legs[i]['event'] if i < len(e_legs) else ""
                            leg_ma = e_legs[i]['market'].replace(' | ', '\n') if i < len(e_legs) else ""
                            leg_od = float(e_legs[i]['odds']) if i < len(e_legs) else 1.50
                            leg_st = e_legs[i]['status'] if i < len(e_legs) and 'status' in e_legs[i] else "⚪ Εκκρεμές"
                            
                            st.markdown(f"<div style='background-color: rgba(22, 38, 59, 0.4); padding: 15px; border-radius: 12px; margin-bottom: 15px; border-left: 4px solid #4db8ff;'>", unsafe_allow_html=True)
                            c_ev, c_od, c_st = st.columns([4,2,2])
                            
                            l_ev_final = render_event_input(ed_sport, f"ed_pbb_ev_{i}_{selected_aa}", entry_mode_ed, c_ev)
                            
                            l_od_final = c_od.number_input(f"Απόδοση Αγώνα:", min_value=1.00, step=0.01, value=leg_od, key=f"ed_leg_od_{i}_{selected_aa}", on_change=update_auto_odds_edit, args=(selected_aa, edit_num_legs))
                            st_idx = STATUS_LIST.index(leg_st) if leg_st in STATUS_LIST else 0
                            l_st_final = c_st.selectbox(f"Κατάσταση:", STATUS_LIST, index=st_idx, key=f"ed_leg_st_{i}_{selected_aa}", on_change=update_auto_odds_edit, args=(selected_aa, edit_num_legs))
                            
                            ed_lma_key = f"ed_pbb_ma_{i}_{selected_aa}"
                            l_ma_final = st.text_area(f"Επιλογές Bet Builder (Μία ανά γραμμή):", value=leg_ma, height=80, key=ed_lma_key)
                            st.markdown("</div>", unsafe_allow_html=True)
                            
                            clean_ma = l_ma_final.replace('\n', ' | ') if l_ma_final else ""
                            new_legs.append({"event": l_ev_final, "market": clean_ma, "odds": l_od_final, "status": l_st_final})
                            if l_st_final != "🔵 Ακυρωμένο": temp_odds *= l_od_final
                            
                        if 'auto_odds_multi' not in st.session_state or st.session_state['auto_odds_multi'] == 1.0:
                            st.session_state['auto_odds_multi'] = temp_odds

                    else: 
                        st.markdown("<h5 style='color: #a8dadc; border-bottom: 1px solid #1e3a5f; padding-bottom: 5px; margin-top: 15px;'>2. Ανάλυση Σημείων</h5>", unsafe_allow_html=True)
                        temp_odds = 1.0
                        for i in range(int(edit_num_legs)):
                            cc1, cc2, cc3, cc4 = st.columns([3,3,1,2]) 
                            leg_ev = e_legs[i]['event'] if i < len(e_legs) else ""
                            leg_ma = e_legs[i]['market'] if i < len(e_legs) else ""
                            leg_od = float(e_legs[i]['odds']) if i < len(e_legs) else 1.50
                            leg_st = e_legs[i]['status'] if i < len(e_legs) and 'status' in e_legs[i] else "⚪ Εκκρεμές"
                            
                            l_ev_final = render_event_input(ed_sport, f"ed_lev_{i}_{selected_aa}", entry_mode_ed, cc1)
                            l_ma_final = render_market_input(ed_sport, f"ed_lma_{i}_{selected_aa}", entry_mode_ed, l_ev_final, cc2, prefill=leg_ma)
                            
                            l_od_final = cc3.number_input(f"Απόδοση {i+1}", min_value=1.00, step=0.01, value=leg_od, key=f"ed_leg_od_{i}_{selected_aa}", on_change=update_auto_odds_edit, args=(selected_aa, edit_num_legs))
                            st_idx = STATUS_LIST.index(leg_st) if leg_st in STATUS_LIST else 0
                            l_st_final = cc4.selectbox(f"Κατάστ. {i+1}", STATUS_LIST, index=st_idx, key=f"ed_leg_st_{i}_{selected_aa}", on_change=update_auto_odds_edit, args=(selected_aa, edit_num_legs))
                            new_legs.append({"event": l_ev_final, "market": l_ma_final, "odds": l_od_final, "status": l_st_final})
                            if l_st_final != "🔵 Ακυρωμένο": temp_odds *= l_od_final
                            
                        if 'auto_odds_multi' not in st.session_state or st.session_state['auto_odds_multi'] == 1.0:
                            st.session_state['auto_odds_multi'] = temp_odds
                            
                    st.markdown("---")
                    st.markdown("<h5 style='color: #a8dadc; border-bottom: 1px solid #1e3a5f; padding-bottom: 5px; margin-top: 15px;'>3. Αποδόσεις & Ποντάρισμα</h5>", unsafe_allow_html=True)
                    c5, c6, c7, c8 = st.columns(4)
                    if edit_bet_type == "Μονό":
                        ed_odds = c5.number_input("Απόδοση", min_value=1.01, step=0.01, value=e_odds, key=f"ed_odds_{selected_aa}")
                        preset_idx = len(STAKE_PRESETS) - 1
                        for idx_p, p_val in enumerate(STAKE_PRESETS):
                            if isinstance(p_val, float) and abs(p_val - e_stake) < 0.001: preset_idx = idx_p; break
                        ed_preset = c6.selectbox("Ποντάρισμα (€)", STAKE_PRESETS, index=preset_idx, key=f"ed_stake_p_{selected_aa}")
                        ed_custom = c7.number_input("Ή γράψε δικό σου ποσό (€)", min_value=0.0, step=0.05, value=e_stake if preset_idx == len(STAKE_PRESETS)-1 else 0.0, format="%.2f", key=f"ed_stake_c_{selected_aa}")
                        status_idx = STATUS_LIST.index(e_status) if e_status in STATUS_LIST else 0
                        ed_status = c8.selectbox("Κατάσταση (Συνολική)", STATUS_LIST, index=status_idx, key=f"ed_status_{selected_aa}")
                    elif edit_bet_type == "Bet Builder":
                        ed_odds = c5.number_input("Συνολική Απόδοση", min_value=1.00, step=0.01, value=e_odds, key=f"ed_odds_{selected_aa}")
                        preset_idx = len(STAKE_PRESETS) - 1
                        for idx_p, p_val in enumerate(STAKE_PRESETS):
                            if isinstance(p_val, float) and abs(p_val - e_stake) < 0.001: preset_idx = idx_p; break
                        ed_preset = c6.selectbox("Ποντάρισμα (€)", STAKE_PRESETS, index=preset_idx, key=f"ed_stake_p_{selected_aa}")
                        ed_custom = c7.number_input("Ή γράψε δικό σου ποσό (€)", min_value=0.0, step=0.05, value=e_stake if preset_idx == len(STAKE_PRESETS)-1 else 0.0, format="%.2f", key=f"ed_stake_c_{selected_aa}")
                        status_options = ["Αυτόματος Υπολογισμός ⚙️", "🟡 Cash Out"]
                        s_idx = 1 if e_status == "🟡 Cash Out" else 0
                        status_sel = c8.selectbox("Κατάσταση (Συνολική)", status_options, index=s_idx, key=f"ed_status_{selected_aa}")
                        if status_sel == "Αυτόματος Υπολογισμός ⚙️": ed_status = calc_overall_status(new_legs)
                        else: ed_status = "🟡 Cash Out"
                    else:
                        ed_odds = c5.number_input("Συνολική Απόδοση (Υπολογισμένη)", min_value=1.00, step=0.01, value=float(st.session_state.get('auto_odds_multi', 1.0)), key=f"ed_odds_{selected_aa}")
                        preset_idx = len(STAKE_PRESETS) - 1
                        for idx_p, p_val in enumerate(STAKE_PRESETS):
                            if isinstance(p_val, float) and abs(p_val - e_stake) < 0.001: preset_idx = idx_p; break
                        ed_preset = c6.selectbox("Ποντάρισμα (€)", STAKE_PRESETS, index=preset_idx, key=f"ed_stake_p_{selected_aa}")
                        ed_custom = c7.number_input("Ή γράψε δικό σου ποσό (€)", min_value=0.0, step=0.05, value=e_stake if preset_idx == len(STAKE_PRESETS)-1 else 0.0, format="%.2f", key=f"ed_stake_c_{selected_aa}")
                        status_options = ["Αυτόματος Υπολογισμός ⚙️", "🟡 Cash Out"]
                        s_idx = 1 if e_status == "🟡 Cash Out" else 0
                        status_sel = c8.selectbox("Κατάσταση (Συνολική)", status_options, index=s_idx, key=f"ed_status_{selected_aa}")
                        if status_sel == "Αυτόματος Υπολογισμός ⚙️": ed_status = calc_overall_status(new_legs)
                        else: ed_status = "🟡 Cash Out"
                    
                    ed_co_val = 0.0
                    if ed_status == "🟡 Cash Out":
                        existing_co = e_stake + e_profit if e_status == "🟡 Cash Out" else 0.0
                        ed_co_val = st.number_input("Επιστροφή Cash Out (€)", min_value=0.0, step=0.01, value=existing_co, format="%.2f", key=f"ed_co_{selected_aa}")
                    
                    st.markdown("<br>", unsafe_allow_html=True)
                    st.markdown("<div style='background-color: rgba(239, 68, 68, 0.1); padding: 10px; border-radius: 8px; border-left: 4px solid #ef4444; margin-bottom: 15px;'>", unsafe_allow_html=True)
                    delete_check = st.checkbox("⚠️ Οριστική διαγραφή αυτού του δελτίου", key=f"del_check_{selected_aa}")
                    st.markdown("</div>", unsafe_allow_html=True)
                    
                    if st.button("💾 ΑΠΟΘΗΚΕΥΣΗ ΑΛΛΑΓΩΝ", type="primary", key=f"ed_save_btn_{selected_aa}", use_container_width=True):
                        if delete_check:
                            df.drop(index=real_idx, inplace=True)
                            save_df = df.drop(columns=['Α/Α'], errors='ignore')
                            save_df['Time'] = pd.to_datetime(save_df['Time'].astype(str), errors='coerce').dt.strftime('%H:%M').fillna('00:00')
                            save_data(save_df)
                            st.session_state['show_toast'] = True
                            st.session_state['toast_message'] = "Το δελτίο διαγράφηκε!"
                            st.rerun()
                        else:
                            profit = 0.0
                            stake = ed_custom if ed_preset == "Χειροκίνητα..." else float(ed_preset)
                            if ed_status == "🟢 Κερδισμένο": profit = stake * (ed_odds - 1)
                            elif ed_status == "🔴 Χαμένο": profit = -stake
                            elif ed_status == "🟡 Cash Out": profit = ed_co_val - stake
                            elif ed_status == "🔵 Ακυρωμένο": profit = 0.0
                            
                            t_string = ed_t.strftime('%H:%M')
                            legs_json = ""
                            if edit_bet_type != "Μονό":
                                legs_json = json.dumps(new_legs)
                                if edit_bet_type == "Bet Builder":
                                    base_ev = new_legs[0]['event'] if new_legs and new_legs[0]['event'] else ""
                                    final_ev_str = f"{base_ev} ({len(new_legs)} επιλογές)" if base_ev else f"{len(new_legs)} επιλογές"
                                elif edit_bet_type == "Παρολί με Bet Builders":
                                    events_list = [l['event'] for l in new_legs if l['event']]
                                    final_ev_str = " | ".join(events_list) if events_list else ""
                                else:
                                    events_list = [l['event'] for l in new_legs if l['event']]
                                    final_ev_str = " | ".join(events_list) if events_list else ""
                                market_parts = []
                                for l in new_legs:
                                    emoji = "⚪"
                                    if l['status'] == "🟢 Κερδισμένο": emoji = "🟢"
                                    elif l['status'] == "🔴 Χαμένο": emoji = "🔴"
                                    elif l['status'] == "🔵 Ακυρωμένο": emoji = "🔵"
                                    market_parts.append(f"{emoji} {l['market']} ({float(l['odds']):.2f})")
                                final_ma_str = " | ".join(market_parts)
                            
                            df.at[real_idx, 'Date'] = ed_d
                            df.at[real_idx, 'Time'] = t_string
                            df.at[real_idx, 'Type'] = edit_bet_type
                            df.at[real_idx, 'Sport'] = ed_sport
                            df.at[real_idx, 'Event'] = final_ev_str
                            df.at[real_idx, 'Market'] = final_ma_str
                            df.at[real_idx, 'Odds'] = ed_odds
                            df.at[real_idx, 'Stake'] = stake
                            df.at[real_idx, 'Status'] = ed_status
                            df.at[real_idx, 'Profit'] = profit
                            df.at[real_idx, 'Legs_Data'] = legs_json
                            
                            save_df = df.drop(columns=['Α/Α'], errors='ignore')
                            save_df['Time'] = pd.to_datetime(save_df['Time'].astype(str), errors='coerce').dt.strftime('%H:%M').fillna('00:00')
                            save_data(save_df)
                            st.session_state['show_toast'] = True
                            st.session_state['toast_message'] = "Οι αλλαγές αποθηκεύτηκαν!"
                            st.session_state['auto_odds_multi'] = 1.0
                            st.rerun()

    with tab2:
        st.info("💡 Αλλάξτε κατευθείαν τις τιμές στον πίνακα και πατήστε αποθήκευση.")
        edit_df = filtered_df.copy()
        if 'Legs_Data' in edit_df.columns:
            edit_df = edit_df.drop(columns=['Legs_Data']) 
        if not edit_df.empty:
            edit_df = edit_df[DISPLAY_ORDER].sort_values(by="Α/Α", ascending=False)
            edited_df = st.data_editor(edit_df, num_rows="dynamic", use_container_width=True, hide_index=True, column_config=GREEK_COLUMNS)
            if st.button("💾 Εφαρμογή Αλλαγών (Πίνακα)", type="primary"):
                final_save_df = edited_df.copy()
                final_save_df = final_save_df.merge(df[['Α/Α', 'Legs_Data']], on='Α/Α', how='left')
                def recalc_profit(row):
                    if row['Status'] == '🟢 Κερδισμένο': return row['Stake'] * (row['Odds'] - 1)
                    elif row['Status'] == '🔴 Χαμένο': return -row['Stake']
                    elif row['Status'] in ['🔵 Ακυρωμένο', '⚪ Εκκρεμές']: return 0.0
                    else: return row['Profit'] 
                final_save_df['Profit'] = final_save_df.apply(recalc_profit, axis=1)
                final_save_df['Time'] = pd.to_datetime(final_save_df['Time'].astype(str), errors='coerce').dt.strftime('%H:%M').fillna('00:00')
                final_save_df = final_save_df.drop(columns=['Α/Α']).sort_values(by=["Date", "Time"])
                save_data(final_save_df)
                st.session_state['show_toast'] = True
                st.session_state['toast_message'] = "Ο πίνακας ενημερώθηκε!"
                st.rerun()
        else:
            st.write("Το ιστορικό είναι άδειο.")