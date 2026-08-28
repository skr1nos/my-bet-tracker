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

def format_month(yyyymm):
    """Μετατρέπει το YYYY-MM σε ανθρώπινη μορφή: Μήνας YYYY (MM/YYYY)"""
    try:
        y, m = yyyymm.split('-')
        return f"{GREEK_MONTHS[int(m)]} {y} ({m}/{y})"
    except:
        return yyyymm

EXPECTED_COLS = ['Date', 'Time', 'Type', 'Sport', 'Event', 'Market', 'Odds', 'Stake', 'Status', 'Profit', 'Legs_Data']
DISPLAY_ORDER = ['Α/Α', 'Status', 'Date', 'Time', 'Type', 'Sport', 'Event', 'Market', 'Odds', 'Stake', 'Profit']

STATUS_LIST = ["⚪ Εκκρεμές", "🟢 Κερδισμένο", "🔴 Χαμένο", "🔵 Ακυρωμένο", "🟡 Cash Out"]
BET_TYPES = ["Μονό", "Παρολί", "Bet Builder", "Παρολί με Bet Builders"]

SPORT_ICONS = {
    "Ποδόσφαιρο": "⚽ Ποδόσφαιρο",
    "Μπάσκετ": "🏀 Μπάσκετ",
    "Τένις": "🎾 Τένις",
    "Άλλο": "🎯 Άλλο",
    "Διάφορα": "🌎 Διάφορα"
}

# ==========================================
# 🧠 ΒΟΗΘΗΤΙΚΕΣ ΣΥΝΑΡΤΗΣΕΙΣ (ΑΣΦΑΛΕΙΑ ΔΕΔΟΜΕΝΩΝ & NORMALIZATION)
# ==========================================
def normalize_greek(text):
    if not text or pd.isna(text): return ""
    text = str(text).lower()
    text = ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')
    text = text.replace('ς', 'σ')
    return text.strip()

def clean_selection(val):
    if not val: return val
    if " · " in val: return val.split(" · ")[0]
    return val

def safe_float(val, min_val=1.00):
    try:
        f = float(val)
        if pd.isna(f) or f < min_val: 
            return min_val
        return f
    except:
        return min_val

# ==========================================
# 🧠 ΔΙΑΧΕΙΡΙΣΗ CUSTOM ΒΑΣΗΣ
# ==========================================
def load_custom_db():
    default_db = {"hierarchy": {}, "players": [], "bankrolls": {}}
    if os.path.exists("custom_database.json"):
        try:
            with open("custom_database.json", "r", encoding="utf-8") as f:
                db = json.load(f)
                if "bankrolls" not in db: db["bankrolls"] = {}
                return db
        except:
            pass
    return default_db

def save_custom_db(db):
    with open("custom_database.json", "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=4)

def save_new_entities_to_db(sport):
    custom_db = load_custom_db()
    changed = False
    if "hierarchy" not in custom_db: custom_db["hierarchy"] = {}
    if "players" not in custom_db: custom_db["players"] = []
    
    for key, val in st.session_state.items():
        if not isinstance(val, str) or not val.strip(): continue
        val = val.strip()
        
        if key.endswith("_new_lg"):
            if sport not in custom_db["hierarchy"]: custom_db["hierarchy"][sport] = {}
            if val not in custom_db["hierarchy"][sport]:
                custom_db["hierarchy"][sport][val] = []
                changed = True
        
        if key.endswith("_t1_man") or key.endswith("_t2_man"):
            base_key = key.rsplit("_", 2)[0]
            lg_key = f"{base_key}_lg"
            new_lg_key = f"{base_key}_new_lg"
            
            lg_name = None
            if lg_key in st.session_state:
                lg_val = clean_selection(st.session_state[lg_key])
                if lg_val == "➕ Νέα Διοργάνωση..." and new_lg_key in st.session_state: lg_name = st.session_state[new_lg_key].strip()
                elif lg_val and lg_val != "➕ Νέα Διοργάνωση...": lg_name = lg_val
                    
            if lg_name:
                if sport not in custom_db["hierarchy"]: custom_db["hierarchy"][sport] = {}
                if lg_name not in custom_db["hierarchy"][sport]: custom_db["hierarchy"][sport][lg_name] = []
                
                existing_teams = SPORTS_HIERARCHY.get(sport, {}).get(lg_name, [])
                if val not in custom_db["hierarchy"][sport][lg_name] and val not in existing_teams:
                    custom_db["hierarchy"][sport][lg_name].append(val)
                    changed = True

        if key.endswith("_p_new"):
            if val not in custom_db["players"] and val not in all_players_global:
                custom_db["players"].append(val)
                changed = True

    if changed:
        save_custom_db(custom_db)

# ==========================================
# 🧠 ΒΑΣΙΚΗ ΒΑΣΗ ΔΕΔΟΜΕΝΩΝ 
# ==========================================
SPORTS_HIERARCHY = {
    "⚽ Ποδόσφαιρο": {
        "🇬🇷 Super League": ["Ολυμπιακός", "Παναθηναϊκός", "ΑΕΚ", "ΠΑΟΚ", "Άρης", "ΟΦΗ", "Παναιτωλικός", "Αστέρας Τρίπολης", "Βόλος", "Ατρόμητος", "Λαμία", "Πανσερραϊκός", "Καλλιθέα", "Λεβαδειακός"],
        "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League": ["Άρσεναλ", "Μάντσεστερ Σίτι", "Λίβερπουλ", "Τσέλσι", "Μάντσεστερ Γιουνάιτεντ", "Τότεναμ", "Νιούκαστλ", "Άστον Βίλα", "Έβερτον", "Μπράιτον", "Μπρέντφορντ", "Γουέστ Χαμ", "Φούλαμ", "Μπόρνμουθ", "Κρίσταλ Πάλας"],
        "🇪🇸 La Liga": ["Ρεάλ Μαδρίτης", "Μπαρτσελόνα", "Ατλέτικο Μαδρίτης", "Τζιρόνα", "Μπιλμπάο", "Σοσιεδάδ", "Βιγιαρεάλ", "Βαλένθια", "Μπέτις", "Σεβίλλη", "Θέλτα", "Μαγιόρκα", "Οσασούνα"],
        "🇮🇹 Serie A": ["Ίντερ", "Γιουβέντους", "Μίλαν", "Νάπολι", "Αταλάντα", "Ρόμα", "Λάτσιο", "Φιορεντίνα", "Τορίνο", "Μπολόνια"],
        "🇩🇪 Bundesliga": ["Μπάγερν Μονάχου", "Ντόρτμουντ", "Λεβερκούζεν", "Λειψία", "Στουτγκάρδη", "Άιντραχτ Φρανκφούρτης", "Βόλφσμπουργκ"],
        "🇫🇷 Ligue 1": ["Παρί Σεν Ζερμέν", "Μονακό", "Μαρσέιγ", "Λιλ", "Λυών", "Λανς"],
        "🇪🇺 Champions League": ["Ρεάλ Μαδρίτης", "Μπαρτσελόνα", "Μπάγερν Μονάχου", "Λίβερπουλ", "Μάντσεστερ Σίτι", "Άρσεναλ", "Γιουβέντους", "Λεβερκούζεν", "Παρί Σεν Ζερμέν", "Ίντερ", "Μίλαν", "Ντόρτμουντ", "Σπόρτινγκ", "Μονακό", "Άστον Βίλα"],
        "🇪🇺 Europa League": ["Ολυμπιακός", "ΠΑΟΚ", "Μάντσεστερ Γιουνάιτεντ", "Τότεναμ", "Άγιαξ", "Λάτσιο", "Ρόμα", "Μπιλμπάο", "Λυών", "Σοσιεδάδ", "Άιντραχτ", "Γαλατασαράι", "Φενέρμπαχτσε"],
        "🇪🇺 Conference League": ["Παναθηναϊκός", "Τσέλσι", "Φιορεντίνα", "Μπέτις", "Κοπεγχάγη", "Χάιντενχαϊμ", "Γάνδη", "ΑΠΟΕΛ", "Ομόνοια", "Πάφος"],
        "🌍 Διεθνή (Εθνικές)": ["Ελλάδα", "Αγγλία", "Ισπανία", "Γαλλία", "Γερμανία", "Πορτογαλία", "Ολλανδία", "Ιταλία", "Αργεντινή", "Βραζιλία", "Βέλγιο"]
    },
    "🏀 Μπάσκετ": {
        "🇪🇺 Euroleague": ["Ολυμπιακός", "Παναθηναϊκός", "Ρεάλ Μαδρίτης", "Μπαρτσελόνα", "Μονακό", "Φενέρμπαχτσε", "Αναντολού Εφές", "Μπάγερν Μονάχου", "Ζαλγκίρις", "Ερυθρός Αστέρας", "Παρτιζάν", "Αρμάνι Μιλάνο", "Βίρτους Μπολόνια", "Μακάμπι Τελ Αβίβ", "Βιλερμπάν", "Μπασκόνια", "Άλμπα Βερολίνου", "Παρί"],
        "🇬🇷 Basket League": ["Ολυμπιακός", "Παναθηναϊκός", "Περιστέρι", "Προμηθέας", "ΑΕΚ", "Άρης", "ΠΑΟΚ", "Κολοσσός Ρόδου", "Μαρούσι", "Καρδίτσα", "Λαύριο", "Πανιώνιος"],
        "🇺🇸 NBA": ["Ατλάντα Χοκς", "Μπόστον Σέλτικς", "Μπρούκλιν Νετς", "Σάρλοτ Χόρνετς", "Σικάγο Μπουλς", "Κλίβελαντ Καβαλίερς", "Ντάλας Μάβερικς", "Ντένβερ Νάγκετς", "Ντιτρόιτ Πίστονς", "Γκόλντεν Στέιτ Γουόριορς", "Χιούστον Ρόκετς", "Ιντιάνα Πέισερς", "Λος Άντζελες Κλίπερς", "Λος Άντζελες Λέικερς", "Μέμφις Γκρίζλις", "Μαϊάμι Χιτ", "Μιλγουόκι Μπακς", "Μινεσότα Τίμπεργουλβς", "Νέα Ορλεάνη Πέλικανς", "Νιου Γιορκ Νικς", "Οκλαχόμα Σίτι Θάντερ", "Ορλάντο Μάτζικ", "Φιλαδέλφεια Σίξερς", "Φοίνιξ Σανς", "Πόρτλαντ Τρέιλ Μπλέιζερς", "Σακραμέντο Κινγκς", "Σαν Αντόνιο Σπερς", "Τορόντο Ράπτορς", "Γιούτα Τζαζ", "Ουάσινγκτον Γουίζαρντς"],
        "🇺🇸 WNBA": ["Λας Βέγκας Έισις (Aces)", "Νιου Γιορκ Λίμπερτι (Liberty)", "Κονέκτικατ Σαν (Sun)", "Μινεσότα Λινξ (Lynx)", "Σιάτλ Στορμ (Storm)", "Ιντιάνα Φίβερ (Fever)", "Φοίνιξ Μέρκιουρι (Mercury)", "Ατλάντα Ντριμ (Dream)", "Σικάγο Σκάι (Sky)", "Λος Άντζελες Σπαρκς (Sparks)", "Ντάλας Γουίνγκς (Wings)", "Ουάσινγκτον Μίστικς (Mystics)", "Γκόλντεν Στέιτ Βαλκίρις (Valkyries)"],
        "🌍 Εθνικές (FIBA / Προκριματικά)": ["Ελλάδα", "ΗΠΑ", "Σερβία", "Γερμανία", "Γαλλία", "Καναδάς", "Ισπανία", "Αυστραλία", "Λιθουανία", "Ιταλία", "Λετονία", "Σλοβενία", "Πουέρτο Ρίκο", "Βραζιλία", "Τουρκία", "Μαυροβούνιο", "Μπαχάμες", "Γεωργία", "Φινλανδία", "Νέα Ζηλανδία"],
        "🇪🇺 Eurocup": ["Χάποελ Τελ Αβίβ", "Μπανταλόνα", "Γκραν Κανάρια", "Βαλένθια", "Μπεσίκτας", "Τουρκ Τέλεκομ", "Μπουργκ", "Τσεντεβίτα", "Άρης", "Τρέντο", "Ουλμ", "Κλουζ", "Γουλβς"],
        "🇪🇺 BCL (Champions League)": ["Τενερίφη", "Ουνικάχα Μάλαγα", "Μούρθια", "Γαλατασαράι", "Καρσίγιακα", "Χάποελ Ιερουσαλήμ", "ΑΕΚ", "Περιστέρι", "Προμηθέας", "Ρίτας Βίλνιους", "Ιγκοκέα", "Ντερτόνα", "Βόννη", "Κέμνιτς"]
    },
    "🎾 Τένις": {
        "🎾 Άνδρες (ATP)": ["Sinner", "Alcaraz", "Djokovic", "Zverev", "Medvedev", "Tsitsipas", "Rublev", "Ruud", "Dimitrov", "De Minaur", "Fritz", "Tiafoe", "Rune", "Shelton", "Hurkacz", "Paul", "Khachanov"],
        "🎾 Γυναίκες (WTA)": ["Swiatek", "Sabalenka", "Gauff", "Rybakina", "Pegula", "Zheng", "Sakkari", "Jabeur", "Ostapenko", "Collins", "Navarro", "Paolini", "Krejcikova", "Haddad Maia", "Kasatkina"]
    }
}

# ΕΝΣΩΜΑΤΩΣΗ ΤΩΝ CUSTOM ΔΕΔΟΜΕΝΩΝ ΑΠΟ ΤΟ JSON
custom_db = load_custom_db()
for c_sport, c_leagues in custom_db.get("hierarchy", {}).items():
    if c_sport not in SPORTS_HIERARCHY: SPORTS_HIERARCHY[c_sport] = {}
    for c_league, c_teams in c_leagues.items():
        if c_league not in SPORTS_HIERARCHY[c_sport]:
            SPORTS_HIERARCHY[c_sport][c_league] = []
        for team in c_teams:
            if team not in SPORTS_HIERARCHY[c_sport][c_league]:
                SPORTS_HIERARCHY[c_sport][c_league].append(team)

MARKET_GENERAL = {
    "⚽ Ποδόσφαιρο": ["Τελικό Αποτέλεσμα (1X2)", "Over/Under Γκολ", "Goal/Goal ή No Goal", "Διπλή Ευκαιρία", "Ημίχρονο/Τελικό", "Κόρνερ Match", "Κάρτες Match"],
    "🏀 Μπάσκετ": ["Νικητής (Με Παράταση)", "Χάντικαπ (Spread)", "Over/Under Πόντων", "Ημίχρονο/Τελικό"],
    "🎾 Τένις": ["Νικητής Αγώνα", "Over/Under Games", "Χάντικαπ Games", "Ακριβές Σκορ Σετ", "Over/Under Άσσοι", "Over/Under Διπλά Λάθη"]
}

MARKET_PLAYER = {
    "⚽ Ποδόσφαιρο": ["Να Σκοράρει", "Πρώτος Σκόρερ", "Σουτ στην Εστία", "Κάρτα", "Ασίστ", "Τάκλιν", "Πάσες"],
    "🏀 Μπάσκετ": ["Πόντοι", "Ριμπάουντ", "Ασίστ", "Εύστοχα Τρίποντα", "Κλεψίματα", "Κοψίματα", "Λάθη", "Πόντοι + Ασίστ", "Πόντοι + Ριμπάουντ", "Ριμπάουντ + Ασίστ", "Π.Ρ.Α."],
    "🎾 Τένις": ["Άσσοι", "Διπλά Λάθη", "Breaks"]
}

st.set_page_config(page_title="My Bet Tracker", page_icon="📈", layout="wide")

# ==========================================
# 🎨 PREMIUM UI CSS
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

/* 🔹 THE HUB CARDS STYLING 🔹 */
.hub-card {
    background: linear-gradient(145deg, #16263b, #0f1c2e);
    border: 1px solid #1e3a5f;
    border-radius: 16px;
    padding: 20px;
    text-align: center;
    box-shadow: 0 10px 20px rgba(0,0,0,0.4);
    transition: all 0.3s ease;
}
.hub-card:hover { transform: translateY(-5px); box-shadow: 0 15px 30px rgba(0,0,0,0.6); border-color: #4db8ff; }
.hub-title { font-size: 22px; font-weight: 700; color: #4db8ff; margin-bottom: 15px; border-bottom: 2px solid #1e3a5f; padding-bottom: 10px;}
.hub-stat { font-size: 14px; color: #a8dadc; text-transform: uppercase; margin-bottom: 5px; font-weight: 500;}
.hub-val { font-size: 20px; color: #ffffff; font-weight: 700; margin-bottom: 15px;}
.hub-val.green { color: #10b981; }
.hub-val.red { color: #ef4444; }

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
div[role="radiogroup"] { gap: 15px; }
div[role="radiogroup"] > label { background-color: #16263b !important; padding: 12px 20px !important; border-radius: 8px !important; border: 1px solid #1e3a5f !important; margin-bottom: 5px !important; cursor: pointer; flex: 1; text-align: center; justify-content: center; }
</style>
"""
st.markdown(custom_css, unsafe_allow_html=True)

# Αρχικοποίηση State
if 'form_reset_counter' not in st.session_state: st.session_state['form_reset_counter'] = 0
if 'show_toast' not in st.session_state: st.session_state['show_toast'] = False
if 'toast_message' not in st.session_state: st.session_state['toast_message'] = ""
if 'page_sel' not in st.session_state: st.session_state['page_sel'] = "🏠 Hub (Μήνες)"
if 'auto_odds_multi' not in st.session_state: st.session_state['auto_odds_multi'] = 1.0
if 'selected_month' not in st.session_state: st.session_state['selected_month'] = None
if 'last_opened_dialog_bet' not in st.session_state: st.session_state['last_opened_dialog_bet'] = None
if 'last_opened_prog_bet' not in st.session_state: st.session_state['last_opened_prog_bet'] = None

if st.session_state['show_toast']:
    st.toast(st.session_state['toast_message'], icon="✅")
    st.session_state['show_toast'] = False 

# ==========================================
# 📊 CALLBACK FUNCTIONS
# ==========================================
def update_auto_odds(reset_id, num_legs):
    total_odds = 1.0
    for i in range(int(num_legs)):
        leg_odds_key = f"leg_od_{i}_{reset_id}"
        leg_status_key = f"leg_st_{i}_{reset_id}"
        if leg_odds_key in st.session_state and leg_status_key in st.session_state:
            val = safe_float(st.session_state[leg_odds_key], 1.00)
            stat = st.session_state[leg_status_key]
            if stat != "🔵 Ακυρωμένο": total_odds *= val
    st.session_state['auto_odds_multi'] = total_odds

def update_auto_odds_edit(aa_val, num_legs):
    total_odds = 1.0
    for i in range(int(num_legs)):
        leg_odds_key = f"ed_leg_od_{i}_{aa_val}"
        leg_status_key = f"ed_leg_st_{i}_{aa_val}"
        if leg_odds_key in st.session_state and leg_status_key in st.session_state:
            val = safe_float(st.session_state[leg_odds_key], 1.00)
            stat = st.session_state[leg_status_key]
            if stat != "🔵 Ακυρωμένο": total_odds *= val
    st.session_state['auto_odds_multi'] = total_odds

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
df['MonthGroup'] = pd.to_datetime(df['Date']).dt.strftime('%Y-%m')

# ==========================================
# 🧠 DYNAMIC PLAYER/TEAM MEMORY BUILDER
# ==========================================
team_rosters = {}
all_players_global = set()
ignore_words_set = {normalize_greek(w) for w in ['over', 'under', 'ov', 'un', 'o', 'u', 'ποντοι', 'ριμπαουντ', 'ασιστ', 'ασσιστ', 'τριποντα', 'γκολ', 'καρτες', 'σουτ', 'φαουλ', 'νικη', 'ισοπαλια', 'ηττα', 'να', 'σκοραρει', 'anytime', 'scorer', '1', 'x', '2', '1x', 'x2', '12', 'gg', 'ng', 'g/g', 'n/g']}

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
                    if re.search(r'\d', w) or (w and normalize_greek(w) in ignore_words_set): break
                    p_name.append(w)
                final_p = " ".join(p_name).strip()
                if final_p and len(final_p) > 2 and normalize_greek(final_p) not in ["home", "away", "draw", "νικη", "ισοπαλια", "yes", "no"]:
                    players.append(final_p)
        
        for t in teams:
            if t not in team_rosters: team_rosters[t] = set()
            for p in players:
                team_rosters[t].add(p)
                all_players_global.add(p)

    if row['Type'] == "Μονό": map_players(row['Event'], row['Market'])
    else:
        legs_str = row['Legs_Data']
        if pd.notna(legs_str) and legs_str.strip():
            try:
                for leg in json.loads(legs_str): map_players(leg.get('event', row['Event']), leg.get('market', ''))
            except: pass

for p in custom_db.get("players", []): all_players_global.add(p)

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

def find_team_match(t, norm_teams_dict):
    m = difflib.get_close_matches(t, norm_teams_dict.keys(), n=1, cutoff=0.65)
    if m: return norm_teams_dict[m[0]]
    for kt in norm_teams_dict.keys():
        if t in kt and len(t) >= 4: return norm_teams_dict[kt]
    return t

def get_event_suggestions(user_text, all_events, all_teams):
    if len(user_text) < 3: return []
    norm_user = normalize_greek(user_text)
    norm_events_dict = {normalize_greek(e): e for e in all_events}
    if norm_user in norm_events_dict: return []
    suggestions = []
    for delim in [' - ', ' vs ', '-']:
        if delim in user_text:
            parts = user_text.split(delim)
            if len(parts) == 2:
                t1, t2 = parts[0].strip(), parts[1].strip()
                nt1, nt2 = normalize_greek(t1), normalize_greek(t2)
                norm_teams_dict = {normalize_greek(t): t for t in all_teams}
                final_t1 = find_team_match(nt1, norm_teams_dict) if nt1 else t1
                final_t2 = find_team_match(nt2, norm_teams_dict) if nt2 else t2
                if final_t1 != t1 or final_t2 != t2:
                    suggestions.append(f"{final_t1} {delim.strip()} {final_t2}")
            break
    if not suggestions:
        full_matches = difflib.get_close_matches(norm_user, list(norm_events_dict.keys()), n=2, cutoff=0.75)
        for fm in full_matches: suggestions.append(norm_events_dict[fm])
    return list(dict.fromkeys(suggestions))[:3]

def get_market_suggestions(user_text, all_markets):
    if len(user_text) < 3: return []
    norm_user = normalize_greek(user_text)
    norm_markets_dict = {normalize_greek(m): m for m in all_markets}
    if norm_user in norm_markets_dict: return []
    def get_entity_prefix(text):
        words = []
        for w in text.split():
            if re.search(r'\d', w) or normalize_greek(w) in ignore_words_set: break
            words.append(w)
        return " ".join(words)
    user_prefix = get_entity_prefix(norm_user)
    scored_markets = []
    for norm_m, orig_m in norm_markets_dict.items():
        if norm_user in norm_m:
            scored_markets.append((orig_m, 2.0))
            continue
        m_prefix = get_entity_prefix(norm_m)
        if user_prefix and m_prefix:
            prefix_ratio = difflib.SequenceMatcher(None, user_prefix, m_prefix).ratio()
            if prefix_ratio < 0.65: continue 
            overall_ratio = difflib.SequenceMatcher(None, norm_user, norm_m).ratio()
            scored_markets.append((orig_m, overall_ratio + prefix_ratio))
        else:
            overall_ratio = difflib.SequenceMatcher(None, norm_user, norm_m).ratio()
            if overall_ratio > 0.75:
                scored_markets.append((orig_m, overall_ratio))
    scored_markets.sort(key=lambda x: x[1], reverse=True)
    return list(dict.fromkeys([x[0] for x in scored_markets]))[:3]

def render_suggestions(container, input_key, current_value, sugg_func, args):
    if not current_value: return
    sims = sugg_func(current_value, *args)
    if sims and current_value not in sims:
        container.markdown("<div style='color:#a8dadc; font-size:13px; margin-bottom:5px;'>💡 Μήπως εννοείς; (Κλικ για επιλογή)</div>", unsafe_allow_html=True)
        for sim in sims:
            def update_val(k=input_key, v=sim): st.session_state[k] = v
            container.button(sim, key=f"btn_sugg_{input_key}_{sim}", on_click=update_val, use_container_width=True)

def calc_overall_status(legs_list):
    if not legs_list: return "⚪ Εκκρεμές"
    statuses = [l.get('status', "⚪ Εκκρεμές") for l in legs_list]
    if "🔴 Χαμένο" in statuses: return "🔴 Χαμένο"
    elif "⚪ Εκκρεμές" in statuses: return "⚪ Εκκρεμές"
    elif "🟢 Κερδισμένο" in statuses: return "🟢 Κερδισμένο"
    else: return "🔵 Ακυρωμένο"

def render_event_input(sport, key_pref, mode, container=st):
    if mode == "✍️ Ελεύθερο Κείμενο" or sport not in SPORTS_HIERARCHY:
        ev_str = container.text_input("Αγώνας (Ομάδες / Παίκτες):", key=f"{key_pref}_txt")
        return ev_str
    else:
        leagues = list(SPORTS_HIERARCHY[sport].keys())
        lg_opts = ["(Επίλεξε Διοργάνωση)", "➕ Νέα Διοργάνωση..."] + [f"{l} · {normalize_greek(l)}" for l in leagues]
        
        lg_raw = container.selectbox("🏆 Διοργάνωση", lg_opts, index=0, key=f"{key_pref}_lg")
        lg = clean_selection(lg_raw)
        
        if lg in ["(Επίλεξε Διοργάνωση)", ""]: return ""
        elif lg == "➕ Νέα Διοργάνωση...":
            new_lg = container.text_input("Όνομα Νέας Διοργάνωσης:", key=f"{key_pref}_new_lg")
            teams = []
        elif lg == "Άλλη Διοργάνωση...":
            return container.text_input("Αγώνας (π.χ. Ολυμπιακός - ΠΑΟΚ):", key=f"{key_pref}_man_ev")
        else:
            teams = SPORTS_HIERARCHY[sport][lg]
            
        t_opts = ["(Επίλεξε Ομάδα)", "➕ Νέα Ομάδα..."] + [f"{t} · {normalize_greek(t)}" for t in teams]
        
        c_home, c_vs, c_away = container.columns([5, 1, 5])
        
        t1_raw = c_home.selectbox("🏠 Γηπεδούχος / P1", t_opts, index=0, key=f"{key_pref}_t1")
        final_t1 = clean_selection(t1_raw)
        if final_t1 == "➕ Νέα Ομάδα...": final_t1 = c_home.text_input("Γράψε Ομάδα 1:", key=f"{key_pref}_t1_man")
        elif final_t1 in ["(Επίλεξε Ομάδα)", ""]: final_t1 = ""
            
        with c_vs:
            st.markdown("<div style='text-align: center; margin-top: 36px; font-weight: bold; color: #718096;'>VS</div>", unsafe_allow_html=True)
            
        t2_raw = c_away.selectbox("✈️ Φιλοξενούμενος / P2", t_opts, index=0, key=f"{key_pref}_t2")
        final_t2 = clean_selection(t2_raw)
        if final_t2 == "➕ Νέα Ομάδα...": final_t2 = c_away.text_input("Γράψε Ομάδα 2:", key=f"{key_pref}_t2_man")
        elif final_t2 in ["(Επίλεξε Ομάδα)", ""]: final_t2 = ""
            
        if final_t1 and final_t2: return f"{final_t1} - {final_t2}"
        return ""

def render_market_input(sport, key_pref, mode, event_str, container=st, prefill=""):
    if mode == "✍️ Ελεύθερο Κείμενο" or (sport not in MARKET_GENERAL and sport not in MARKET_PLAYER):
        val = container.text_input("Αγορά:", value=prefill, key=f"{key_pref}_txt")
        return val
    else:
        default_idx = 2 if prefill else 0
        market_type = container.radio("Κατηγορία Αγοράς:", ["🎯 Γενική (Match)", "👤 Ειδικό Παίκτη", "✏️ Ελεύθερο"], index=default_idx, horizontal=True, key=f"{key_pref}_type")
        
        if market_type == "✏️ Ελεύθερο":
            val = container.text_input("Γράψε Αγορά:", value=prefill, key=f"{key_pref}_free")
            return val
            
        elif market_type == "🎯 Γενική (Match)":
            cats = MARKET_GENERAL.get(sport, [])
            if not cats: return container.text_input("Αγορά:", value=prefill, key=f"{key_pref}_gen_free")
            c1, c2 = container.columns([3, 2])
            sel = c1.selectbox("Επιλογή Αγοράς:", ["(Επιλογή)"] + cats, key=f"{key_pref}_gen_sel")
            if sel != "(Επιλογή)":
                val = c2.text_input("Σημείο / Όριο (π.χ. Over 2.5, 1):", key=f"{key_pref}_gen_final")
                return f"{sel}: {val}" if val else sel
            return ""
            
        elif market_type == "👤 Ειδικό Παίκτη":
            cats = MARKET_PLAYER.get(sport, ["Άλλο"])
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
                norm_t = normalize_greek(t)
                for db_t in team_rosters:
                    if normalize_greek(db_t) == norm_t:
                        relevant_players.extend(list(team_rosters[db_t]))
            relevant_players = sorted(list(set(relevant_players)))
            all_others = sorted(list(all_players_global - set(relevant_players)))
            
            p_options = ["(Επίλεξε Παίκτη)", "➕ Νέος Παίκτης..."]
            if relevant_players: p_options += ["--- ΠΑΙΚΤΕΣ ΑΓΩΝΑ ---"] + [f"{p} · {normalize_greek(p)}" for p in relevant_players]
            if all_others: p_options += ["--- ΑΛΛΟΙ ΠΑΙΚΤΕΣ ---"] + [f"{p} · {normalize_greek(p)}" for p in all_others]
            
            c_p = container.columns(1)[0]
            player_sel_raw = c_p.selectbox("Παίκτης:", p_options, index=0, key=f"{key_pref}_p_sel")
            player_sel = clean_selection(player_sel_raw)
            
            final_player = ""
            if player_sel == "➕ Νέος Παίκτης...":
                final_player = c_p.text_input("Όνομα Παίκτη:", key=f"{key_pref}_p_new")
            elif player_sel and not player_sel.startswith("---") and player_sel != "(Επίλεξε Παίκτη)":
                final_player = player_sel
                
            c1, c2 = container.columns(2)
            stat_sel = c1.selectbox("Στατιστικό:", ["(Επιλογή)"] + cats, key=f"{key_pref}_p_stat")
            line_val = c2.text_input("Όριο / Σημείο (π.χ. Over 15.5):", key=f"{key_pref}_p_line")
            
            if final_player and stat_sel != "(Επιλογή)":
                return f"{final_player} - {stat_sel} {line_val}".strip()
            return ""

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
                <span style="font-weight: 700; font-size: 17px; color: #4db8ff;">{safe_float(row['Odds'], 1.00):.2f}</span>
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
                            <span style="font-weight: 700; font-size: 16px; color: #4db8ff;">{safe_float(leg.get('odds', 1.0), 1.0):.2f}</span>
                        </div>
                    </div>''')
            except Exception: pass
    
    html_parts.append(f'''</div>
    <div style="border-top: 2px dashed #2a4365; padding-top: 20px; position: relative; z-index: 1;">
        <div style="display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 15px;">
            <div><p style="margin: 0; font-size: 12px; color: #718096; text-transform: uppercase;">ΠΟΝΤΑΡΙΣΜΑ</p><p style="margin: 0; font-size: 18px; font-weight: 600; color: #e2e8f0;">{safe_float(row['Stake'], 0.0):.2f} €</p></div>
            <div style="text-align: right;"><p style="margin: 0; font-size: 12px; color: #718096; text-transform: uppercase;">ΣΥΝ. ΑΠΟΔΟΣΗ</p><p style="margin: 0; font-size: 18px; font-weight: 600; color: #e2e8f0;">{safe_float(row['Odds'], 1.00):.2f}</p></div>
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
# 🔍 ΔΙΑΛΟΓΟΙ ΣΤΑΤΙΣΤΙΚΩΝ
# ==========================================
@st.dialog("📊 Λεπτομέρειες", width="large")
def show_bets_dialog(title_str, df_to_show, full_df):
    st.markdown(f"<h3 style='color: #4db8ff; font-family: Poppins;'>{title_str}</h3>", unsafe_allow_html=True)
    st.markdown("<p style='color: #a8dadc; font-size: 14px; margin-bottom: 15px; font-family: Poppins;'>💡 Κάνε κλικ σε οποιαδήποτε γραμμή για να δεις την απόδειξη.</p>", unsafe_allow_html=True)
    if not df_to_show.empty:
        disp = df_to_show.drop(columns=['Legs_Data', 'MonthGroup'], errors='ignore')[DISPLAY_ORDER].sort_values(by=["Date", "Time"], ascending=False)
        event = st.dataframe(disp, use_container_width=True, hide_index=True, column_config=GREEK_COLUMNS, on_select="rerun", selection_mode="single-row", key=f"dialog_bets_df_{title_str}")
        if event.selection.rows:
            sel_idx = event.selection.rows[0]
            sel_aa = disp.iloc[sel_idx]['Α/Α']
            if st.session_state.get('last_opened_dialog_bet') != sel_aa:
                st.session_state['last_opened_dialog_bet'] = sel_aa
                st.session_state['auto_open_ticket'] = int(sel_aa)
                st.rerun()
        else:
            st.session_state['last_opened_dialog_bet'] = None
    else:
        st.info("Δεν βρέθηκαν δελτία.")

@st.dialog("📈 Ανάλυση Εξέλιξης", width="large")
def show_progression_dialog(metric_type, prog_dataframe, full_df):
    st.markdown("<p style='color: #a8dadc; font-size: 14px; margin-bottom: 15px; font-family: Poppins;'>💡 Κάνε κλικ σε οποιαδήποτε γραμμή για να δεις την απόδειξη.</p>", unsafe_allow_html=True)
    if prog_dataframe.empty:
        st.info("Δεν υπάρχουν δεδομένα.")
        return
        
    if metric_type == "profit":
        st.markdown("<h3 style='color: #4db8ff; font-family: Poppins;'>💰 Εξέλιξη Ταμείου</h3>", unsafe_allow_html=True)
        disp_df = prog_dataframe[['Α/Α', 'Date', 'Event', 'Stake', 'Odds', 'Profit', 'Cumulative_Profit', 'Balance']].copy()
        disp_df.rename(columns={'Date': 'Ημ/νια', 'Event': 'Αγώνας', 'Stake': 'Ποντάρισμα', 'Odds': 'Απόδοση', 'Profit': 'Κέρδος/Ζημιά', 'Cumulative_Profit': 'Συνολικό Κέρδος', 'Balance': 'Τρέχον Υπόλοιπο'}, inplace=True)
        cfg = {"Συνολικό Κέρδος": st.column_config.NumberColumn("Συνολικό Κέρδος (€)", format="%.2f €"), "Τρέχον Υπόλοιπο": st.column_config.NumberColumn("Τρέχον Υπόλοιπο (€)", format="%.2f €"), "Κέρδος/Ζημιά": st.column_config.NumberColumn("Κέρδος/Ζημιά", format="%.2f €"), "Ποντάρισμα": st.column_config.NumberColumn("Ποντάρισμα", format="%.2f €"), "Ημ/νια": st.column_config.DateColumn("Ημ/νια", format="DD/MM/YYYY")}
    elif metric_type == "roi":
        st.markdown("<h3 style='color: #4db8ff; font-family: Poppins;'>📉 Εξέλιξη Μονάδων (Units)</h3>", unsafe_allow_html=True)
        disp_df = prog_dataframe[['Α/Α', 'Date', 'Event', 'Stake', 'Profit', 'Cumulative_Units']].copy()
        disp_df.rename(columns={'Date': 'Ημ/νια', 'Event': 'Αγώνας', 'Stake': 'Ποντάρισμα', 'Profit': 'Κέρδος/Ζημιά', 'Cumulative_Units': 'Τρέχουσες Μονάδες'}, inplace=True)
        cfg = {"Τρέχουσες Μονάδες": st.column_config.NumberColumn("Τρέχουσες Μονάδες", format="%+.2f U"), "Κέρδος/Ζημιά": st.column_config.NumberColumn("Κέρδος/Ζημιά", format="%.2f €"), "Ποντάρισμα": st.column_config.NumberColumn("Ποντάρισμα", format="%.2f €"), "Ημ/νια": st.column_config.DateColumn("Ημ/νια", format="DD/MM/YYYY")}
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
        
    event = st.dataframe(disp_df, use_container_width=True, hide_index=True, column_config=cfg, on_select="rerun", selection_mode="single-row", key="dialog_prog_df")
    if event.selection.rows:
        sel_idx = event.selection.rows[0]
        sel_aa = disp_df.iloc[sel_idx]['Α/Α']
        if st.session_state.get('last_opened_prog_bet') != sel_aa:
            st.session_state['last_opened_prog_bet'] = sel_aa
            st.session_state['auto_open_ticket'] = int(sel_aa)
            st.rerun()
    else:
        st.session_state['last_opened_prog_bet'] = None

# ==========================================
# 🔄 ΔΙΑΛΟΓΟΣ ΕΝΑΡΞΗΣ ΝΕΟΥ ΜΗΝΑ
# ==========================================
@st.dialog("➕ Έναρξη Νέου Μήνα", width="small")
def start_new_month_dialog(suggested_month, default_bankroll):
    st.markdown("### Ξεκίνα έναν νέο κύκλο στοιχηματισμού!")
    st.write("Η εφαρμογή θα υπολογίζει αυτόματα τις **Μονάδες (Units)** σου διαιρώντας την κάβα σου διά 20.")
    
    today = date.today()
    opts = []
    for y in [today.year - 1, today.year, today.year + 1]:
        for m in range(1, 13):
            opts.append(f"{y}-{m:02d}")
    
    s_idx = opts.index(suggested_month) if suggested_month in opts else len(opts)//2
    new_m = st.selectbox("Επίλεξε Μήνα:", opts, index=s_idx, format_func=format_month)
    new_br = st.number_input("Αρχική Κάβα Μήνα (€):", value=float(default_bankroll), step=1.0, min_value=0.0)
    
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("💾 Δημιουργία Μήνα", type="primary", use_container_width=True):
        db = load_custom_db()
        if "bankrolls" not in db: db["bankrolls"] = {}
        db["bankrolls"][new_m] = new_br
        save_custom_db(db)
        st.session_state['show_toast'] = True
        st.session_state['toast_message'] = f"Ο {format_month(new_m)} προστέθηκε επιτυχώς!"
        st.rerun()

# ==========================================
# ➕ ΦΟΡΜΑ ΚΑΤΑΧΩΡΗΣΗΣ ΝΕΟΥ ΔΕΛΤΙΟΥ
# ==========================================
@st.dialog("➕ Καταχώρηση Νέου Δελτίου", width="large")
def new_bet_dialog():
    reset_id = st.session_state['form_reset_counter']
    st.markdown("<br>", unsafe_allow_html=True)
    
    st.markdown("<style>div[role='radiogroup'] { display: flex; justify-content: center; gap: 10px; }</style>", unsafe_allow_html=True)
    bet_type = st.radio("Τύπος Στοιχήματος", BET_TYPES, horizontal=True, key=f"bet_type_{reset_id}", label_visibility="collapsed")
    
    num_legs = 2
    if bet_type != "Μονό":
        num_legs = st.number_input("Πόσα σημεία (ή αγώνες) έχει το δελτίο;", min_value=2, max_value=15, value=2, key=f"legs_num_{reset_id}")
    
    st.markdown("<h5 style='color:#a8dadc; border-bottom:1px solid #1e3a5f; padding-bottom:5px; margin-top:20px;'>1. Βασικά Στοιχεία</h5>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 1, 2])
    d = c1.date_input("Ημερομηνία", date.today(), format="DD/MM/YYYY", key=f"date_{reset_id}")
    t = c2.time_input("Ώρα", datetime.now().time(), step=60, key=f"time_{reset_id}")
    basket_index = list(SPORT_ICONS.values()).index("🏀 Μπάσκετ")
    selected_sport_input = c3.selectbox("Άθλημα", list(SPORT_ICONS.values()), index=basket_index, key=f"sport_{reset_id}")
    
    st.markdown("<br>", unsafe_allow_html=True)
    entry_mode = st.radio("Λειτουργία Συμπλήρωσης:", ["🤖 Έξυπνος Βοηθός", "✍️ Ελεύθερο Κείμενο"], horizontal=True, key=f"entry_mode_{reset_id}")
    
    legs = []
    event_str, market_str = "", ""
    auto_odds = 1.0
    
    st.markdown("<h5 style='color:#a8dadc; border-bottom:1px solid #1e3a5f; padding-bottom:5px; margin-top:20px;'>2. Επιλογές Δελτίου</h5>", unsafe_allow_html=True)
    
    if bet_type == "Μονό":
        with st.container(border=True):
            event_str = render_event_input(selected_sport_input, f"ev_single_{reset_id}", entry_mode, st)
            st.markdown("---")
            market_str = render_market_input(selected_sport_input, f"ma_single_{reset_id}", entry_mode, event_str, st)
        
    elif bet_type == "Bet Builder":
        st.info("💡 Στο απλό Bet Builder (ίδιος αγώνας), η συνολική απόδοση δίνεται από τον bookmaker. Συμπλήρωσέ τη χειροκίνητα στο Βήμα 3!")
        with st.container(border=True):
            st.markdown("**🏟️ Κοινός Αγώνας**")
            event_str = render_event_input(selected_sport_input, f"bb_ev_{reset_id}", entry_mode, st)
            
        for i in range(int(num_legs)):
            with st.container(border=True):
                st.markdown(f"**📌 Σημείο {i+1}**")
                l_ma = render_market_input(selected_sport_input, f"bb_ma_{i}_{reset_id}", entry_mode, event_str, st)
                st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
                c_od, c_st = st.columns(2)
                l_od = c_od.number_input(f"Απόδοση {i+1}", min_value=1.00, step=0.01, value=1.50, key=f"bb_od_{i}_{reset_id}")
                l_st = c_st.selectbox(f"Κατάστ. {i+1}", STATUS_LIST, key=f"bb_st_{i}_{reset_id}")
                legs.append({"event": event_str, "market": l_ma, "odds": l_od, "status": l_st})
                if l_st == "🔵 Ακυρωμένο": auto_odds *= 1.0
                else: auto_odds *= l_od

    elif bet_type == "Παρολί με Bet Builders":
        temp_odds = 1.0
        for i in range(int(num_legs)):
            with st.container(border=True):
                st.markdown(f"**🏟️ Αγώνας {i+1} (Bet Builder)**")
                l_ev = render_event_input(selected_sport_input, f"pbb_ev_{i}_{reset_id}", entry_mode, st)
                st.markdown("---")
                c_ma, c_od, c_st = st.columns([4, 1, 2])
                l_ma_key = f"pbb_ma_{i}_{reset_id}"
                l_ma = c_ma.text_area(f"Επιλογές Bet Builder (Μία ανά γραμμή):", height=68, key=l_ma_key, placeholder="π.χ.\n1 & Over 2.5\nVezenkov - Πόντοι Over 15.5")
                l_od = c_od.number_input(f"Απόδοση:", min_value=1.00, step=0.01, value=1.50, key=f"leg_od_{i}_{reset_id}", on_change=update_auto_odds, args=(reset_id, num_legs))
                l_st = c_st.selectbox(f"Κατάσταση:", STATUS_LIST, key=f"leg_st_{i}_{reset_id}", on_change=update_auto_odds, args=(reset_id, num_legs))
                clean_ma = l_ma.replace('\n', ' | ') if l_ma else ""
                legs.append({"event": l_ev, "market": clean_ma, "odds": l_od, "status": l_st})
                if l_st != "🔵 Ακυρωμένο": temp_odds *= l_od
        if 'auto_odds_multi' not in st.session_state or st.session_state['auto_odds_multi'] == 1.0:
            st.session_state['auto_odds_multi'] = temp_odds

    else: 
        temp_odds = 1.0
        for i in range(int(num_legs)):
            with st.container(border=True):
                st.markdown(f"**📌 Επιλογή {i+1}**")
                l_ev = render_event_input(selected_sport_input, f"ev_t_{i}_{reset_id}", entry_mode, st)
                st.markdown("<div style='height: 5px;'></div>", unsafe_allow_html=True)
                l_ma = render_market_input(selected_sport_input, f"ma_t_{i}_{reset_id}", entry_mode, l_ev, st)
                st.markdown("<div style='height: 5px;'></div>", unsafe_allow_html=True)
                c_od, c_st = st.columns(2)
                l_od = c_od.number_input(f"Απόδοση:", min_value=1.00, step=0.01, value=1.50, key=f"leg_od_{i}_{reset_id}", on_change=update_auto_odds, args=(reset_id, num_legs))
                l_st = c_st.selectbox(f"Κατάστ.:", STATUS_LIST, key=f"leg_st_{i}_{reset_id}", on_change=update_auto_odds, args=(reset_id, num_legs))
                legs.append({"event": l_ev, "market": l_ma, "odds": l_od, "status": l_st})
                if l_st != "🔵 Ακυρωμένο": temp_odds *= l_od
        if 'auto_odds_multi' not in st.session_state or st.session_state['auto_odds_multi'] == 1.0:
            st.session_state['auto_odds_multi'] = temp_odds
            
    st.markdown("<h5 style='color:#a8dadc; border-bottom:1px solid #1e3a5f; padding-bottom:5px; margin-top:20px;'>3. Ταμείο & Ποντάρισμα</h5>", unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown("<div style='background-color: rgba(6, 13, 26, 0.5); padding: 15px; border-radius: 8px;'>", unsafe_allow_html=True)
        c5, c6, c7, c8 = st.columns(4)
        
        # 🧮 UNIT CALCULATOR LOGIC
        m_str = d.strftime('%Y-%m')
        month_br = custom_db.get("bankrolls", {}).get(m_str, 0.0)
        unit_val = month_br / 20.0 if month_br > 0 else 0.0
        
        if unit_val > 0:
            STAKE_PRESETS_DYNAMIC = [f"🎯 1 Μονάδα ({unit_val:.2f} €)", f"🛡️ 0.5 Μονάδα ({unit_val / 2:.2f} €)", "✏️ Χειροκίνητο Ποσό..."]
        else:
            STAKE_PRESETS_DYNAMIC = ["✏️ Χειροκίνητο Ποσό..."]
            st.warning("⚠️ Δεν έχει οριστεί κάβα για αυτόν τον μήνα. Ο υπολογισμός Μονάδας (Unit) είναι ανενεργός.")

        if bet_type == "Μονό":
            odds = c5.number_input("Απόδοση", min_value=1.01, step=0.01, value=safe_float(global_avg_odds, 1.01), key=f"odds_single_{reset_id}")
            chosen_preset = c6.selectbox("Ποντάρισμα (Στρατηγική)", STAKE_PRESETS_DYNAMIC, key=f"stake_preset_{reset_id}")
            custom_stake = c7.number_input("Ποσό (€)", min_value=0.0, step=0.05, format="%.2f", key=f"custom_stake_{reset_id}")
            status = c8.selectbox("Κατάσταση (Συνολική)", STATUS_LIST, key=f"status_{reset_id}")
        elif bet_type == "Bet Builder":
            odds = c5.number_input("Συνολική Απόδοση", min_value=1.00, step=0.01, value=1.50, key=f"odds_multi_{reset_id}")
            chosen_preset = c6.selectbox("Ποντάρισμα (Στρατηγική)", STAKE_PRESETS_DYNAMIC, key=f"stake_preset_{reset_id}")
            custom_stake = c7.number_input("Ποσό (€)", min_value=0.0, step=0.05, format="%.2f", key=f"custom_stake_{reset_id}")
            status_sel = c8.selectbox("Κατάσταση (Συνολική)", ["Αυτόματος Υπολογισμός ⚙️", "🟡 Cash Out"], key=f"status_{reset_id}")
            if status_sel == "Αυτόματος Υπολογισμός ⚙️": status = calc_overall_status(legs)
            else: status = "🟡 Cash Out"
        else:
            odds = c5.number_input("Συνολική Απόδοση (Υπολογισμένη)", min_value=1.00, step=0.01, value=float(st.session_state.get('auto_odds_multi', 1.0)), key=f"odds_multi_{reset_id}")
            chosen_preset = c6.selectbox("Ποντάρισμα (Στρατηγική)", STAKE_PRESETS_DYNAMIC, key=f"stake_preset_{reset_id}")
            custom_stake = c7.number_input("Ποσό (€)", min_value=0.0, step=0.05, format="%.2f", key=f"custom_stake_{reset_id}")
            status_sel = c8.selectbox("Κατάσταση (Συνολική)", ["Αυτόματος Υπολογισμός ⚙️", "🟡 Cash Out"], key=f"status_{reset_id}")
            if status_sel == "Αυτόματος Υπολογισμός ⚙️": status = calc_overall_status(legs)
            else: status = "🟡 Cash Out"
        st.markdown("</div>", unsafe_allow_html=True)
    
    cash_out_val = 0.0
    if status == "🟡 Cash Out":
        st.info("💸 Επέλεξες Cash Out! Δήλωσε το ποσό που εισέπραξες:")
        cash_out_val = st.number_input("Επιστροφή Cash Out (€)", min_value=0.0, step=0.01, format="%.2f", key=f"cashout_{reset_id}")
    
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("💾 ΑΠΟΘΗΚΕΥΣΗ ΔΕΛΤΙΟΥ", type="primary", key=f"save_btn_{reset_id}", use_container_width=True):
        profit = 0.0
        
        # 🧮 EXTRACT STAKE FROM PRESET
        if chosen_preset.startswith("🎯"): stake = unit_val
        elif chosen_preset.startswith("🛡️"): stake = unit_val / 2.0
        else: stake = custom_stake

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
                market_parts.append(f"{emoji} {l['market']} ({safe_float(l.get('odds', 1.0), 1.0):.2f})")
            market_str = " | ".join(market_parts)
        
        try:
           save_new_entities_to_db(selected_sport_input)
           new_data = pd.DataFrame([{
               'Date': d, 'Time': t_string, 'Type': bet_type, 'Sport': selected_sport_input, 'Event': event_str, 'Market': market_str, 'Odds': odds, 'Stake': stake, 'Status': status, 'Profit': profit, 'Legs_Data': legs_json
           }])
           df_to_save = pd.concat([df.drop(columns=['Α/Α', 'MonthGroup'], errors='ignore'), new_data], ignore_index=True)
           save_data(df_to_save)
           st.session_state['show_toast'] = True
           st.session_state['toast_message'] = "Το δελτίο καταχωρήθηκε επιτυχώς!"
           st.session_state['form_reset_counter'] += 1 
           st.session_state['auto_odds_multi'] = 1.0
           st.rerun()
        except Exception as e:
           st.error(f"❌ Υπήρξε πρόβλημα: {e}")

# ==========================================
# 🗂️ ΠΛΟΗΓΗΣΗ (SIDEBAR)
# ==========================================
st.sidebar.markdown("<div class='sidebar-header'>🚀 ΠΛΟΗΓΗΣΗ</div>", unsafe_allow_html=True)
page = st.sidebar.radio("", ["🏠 Hub (Μήνες)", "🌍 All-Time Στατιστικά", "⚡ Ανοιχτά Δελτία", "⚙️ Διαχείριση Ιστορικού"], key="page_sel", label_visibility="collapsed")

# ==========================================
# MAIN APP BODY
# ==========================================
st.markdown('<div class="fab-marker"></div>', unsafe_allow_html=True)
if st.button("➕ ΝΕΟ ΣΤΟΙΧΗΜΑ", type="primary", use_container_width=True):
    new_bet_dialog()

# ----------------- ΣΕΛΙΔΕΣ -----------------
if page == "🏠 Hub (Μήνες)":
    if st.session_state.get('selected_month') is None:
        st.title("🏠 My Betting Hub")
        st.markdown("Επίλεξε τον μήνα που θέλεις να αναλύσεις ή ξεκίνα έναν νέο κύκλο.")
        
        valid_dates = df['Date'].dropna()
        all_months_data = set(valid_dates.apply(lambda x: x.strftime('%Y-%m')))
        all_months_db = set(custom_db.get("bankrolls", {}).keys())
        all_months = sorted(list(all_months_data | all_months_db), reverse=True)
        
        last_known_balance = 0.0
        suggested_new_month = date.today().strftime('%Y-%m')
        if all_months:
            latest_m = all_months[0]
            m_df = df[df['MonthGroup'] == latest_m]
            m_br = custom_db.get("bankrolls", {}).get(latest_m, 0.0)
            m_prof = m_df['Profit'].sum()
            last_known_balance = m_br + m_prof
            
            try:
                dt_obj = datetime.strptime(latest_m, '%Y-%m')
                next_dt = dt_obj + timedelta(days=32)
                suggested_new_month = next_dt.strftime('%Y-%m')
            except: pass

        if st.button("➕ Έναρξη Νέου Μήνα", use_container_width=True):
            start_new_month_dialog(suggested_new_month, last_known_balance)
            
        st.markdown("<hr>", unsafe_allow_html=True)
        
        if not all_months:
            st.info("Δεν υπάρχει ακόμα ιστορικό.")
        else:
            cols = st.columns(3)
            for i, m in enumerate(all_months):
                with cols[i % 3].container(border=True):
                    m_df = df[df['MonthGroup'] == m]
                    m_prof = m_df['Profit'].sum()
                    m_br = custom_db.get("bankrolls", {}).get(m, 0.0)
                    m_bal = m_br + m_prof
                    
                    m_unit = m_br / 20.0 if m_br > 0 else 0.0
                    m_units_won = m_prof / m_unit if m_unit > 0 else 0.0
                    
                    st.markdown(f"<div class='hub-title'>📅 {format_month(m)}</div>", unsafe_allow_html=True)
                    st.markdown(f"<p class='hub-stat'>Αρχικη Καβα:</p><p class='hub-val'>{m_br:.2f} €</p>", unsafe_allow_html=True)
                    st.markdown(f"<p class='hub-stat'>Τρεχον Υπολοιπο:</p><p class='hub-val'>{m_bal:.2f} €</p>", unsafe_allow_html=True)
                    
                    c_class = "green" if m_prof >= 0 else "red"
                    sgn = "+" if m_prof >= 0 else ""
                    unit_str = f" ({sgn}{m_units_won:.1f} Units)" if m_unit > 0 else ""
                    st.markdown(f"<p class='hub-stat'>Καθαρο Κερδος:</p><p class='hub-val {c_class}'>{sgn}{m_prof:.2f} €{unit_str}</p>", unsafe_allow_html=True)
                    
                    if st.button(f"Άνοιγμα Μήνα", key=f"open_m_{m}", use_container_width=True):
                        st.session_state['selected_month'] = m
                        st.rerun()

    else:
        sel_m = st.session_state['selected_month']
        
        if st.session_state.get('auto_open_ticket') is not None:
            aa = st.session_state['auto_open_ticket']
            st.session_state['auto_open_ticket'] = None
            show_ticket_modal(aa, df)

        m_df = df[df['MonthGroup'] == sel_m].copy()
        m_br = custom_db.get("bankrolls", {}).get(sel_m, 0.0)
        m_unit = m_br / 20.0 if m_br > 0 else 0.0
        
        col_back, col_space, col_edit = st.columns([2, 5, 3])
        if col_back.button("🔙 Επιστροφή στο Hub"):
            st.session_state['selected_month'] = None
            st.rerun()
            
        with col_edit.expander("🏦 Επεξεργασία Κάβας"):
            new_br = st.number_input("Κάβα Μήνα (€)", value=float(m_br), step=1.0)
            if st.button("💾 Αποθήκευση", key=f"save_br_{sel_m}"):
                db = load_custom_db()
                if "bankrolls" not in db: db["bankrolls"] = {}
                db["bankrolls"][sel_m] = new_br
                save_custom_db(db)
                st.rerun()
                
        st.title(f"📊 Dashboard: {format_month(sel_m)}")
        
        if m_df.empty:
            st.warning("Αυτός ο μήνας δεν έχει ακόμα δελτία.")
        else:
            completed_bets = m_df[m_df['Status'].isin(["🟢 Κερδισμένο", "🔴 Χαμένο", "🟡 Cash Out", "🔵 Ακυρωμένο"])]
            total_profit = completed_bets['Profit'].sum()
            current_balance = m_br + total_profit
            total_staked = completed_bets['Stake'].sum()
            total_units_won = total_profit / m_unit if m_unit > 0 else 0.0
            
            wl_bets = completed_bets[completed_bets['Status'].isin(["🟢 Κερδισμένο", "🔴 Χαμένο"])]
            win_rate = (len(wl_bets[wl_bets['Profit'] > 0]) / len(wl_bets) * 100) if len(wl_bets) > 0 else 0
            total_bets = len(completed_bets)
            avg_odds = m_df['Odds'].mean()
            
            winning_bets = completed_bets[completed_bets['Status'] == "🟢 Κερδισμένο"]
            
            completed_bets['DateTime'] = pd.to_datetime(completed_bets['Date'].astype(str) + ' ' + completed_bets['Time'].astype(str))
            prog_df = completed_bets.sort_values(by="DateTime").copy()
            
            cum_profit, cum_stake, cum_roi, cum_wr, cum_avg, cum_u = [], [], [], [], [], []
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
                cum_u.append(current_p / m_unit if m_unit > 0 else 0.0)

            prog_df['Cumulative_Profit'] = cum_profit
            prog_df['Balance'] = [m_br + cp for cp in cum_profit]
            prog_df['Cumulative_Units'] = cum_u
            prog_df['Cumulative_Stake'] = cum_stake
            prog_df['Cumulative_ROI'] = cum_roi
            prog_df['Cumulative_WR'] = cum_wr
            prog_df['Cumulative_AvgOdds'] = cum_avg
            prog_df['Peak'] = peaks
            prog_df['Drawdown'] = drawdowns
            
            max_drawdown = min(drawdowns) if drawdowns else 0.0
            peak_bankroll = (m_br + max(peaks)) if peaks else m_br
            prog_df = prog_df.sort_values(by="DateTime", ascending=False)

            st.markdown("### 🏆 Στατιστικά Μήνα")
            col_a, col_b, col_c, col_d = st.columns(4)
            st.markdown('<div class="marker-positive"></div>' if total_profit >= 0 else '<div class="marker-negative"></div>', unsafe_allow_html=True)
            if col_a.button(f"Καθαρό Κέρδος\n{total_profit:.2f} €", key="btn_prof", use_container_width=True): show_progression_dialog("profit", prog_df, df)

            st.markdown('<div class="marker-positive"></div>' if current_balance >= m_br else '<div class="marker-negative"></div>', unsafe_allow_html=True)
            if col_b.button(f"Τρέχον Υπόλοιπο\n{current_balance:.2f} €", key="btn_bal", use_container_width=True): show_progression_dialog("profit", prog_df, df)

            u_sgn = "+" if total_units_won >= 0 else ""
            st.markdown('<div class="marker-positive"></div>' if total_units_won > 0 else ('<div class="marker-negative"></div>' if total_units_won < 0 else ''), unsafe_allow_html=True)
            if col_c.button(f"Μονάδες (+/-)\n{u_sgn}{total_units_won:.1f} U", key="btn_u", use_container_width=True): show_progression_dialog("roi", prog_df, df)

            st.markdown('<div class="marker-neutral"></div>', unsafe_allow_html=True)
            if col_d.button(f"Win Rate\n{win_rate:.1f} %", key="btn_wr", use_container_width=True): show_progression_dialog("wr", prog_df, df)
            
            col_e, col_f, col_g, col_h = st.columns(4)
            st.markdown('<div class="marker-neutral"></div>', unsafe_allow_html=True)
            if col_e.button(f"Συνολικό Ποντάρισμα\n{total_staked:.2f} €", key="btn_staked", use_container_width=True): show_bets_dialog("💰 Όλα τα Πονταρισμένα Δελτία", completed_bets, df)

            st.markdown('<div class="marker-negative"></div>', unsafe_allow_html=True)
            if col_f.button(f"Max Drawdown\n{max_drawdown:.2f} € 📉", key="btn_dd", use_container_width=True): show_progression_dialog("drawdown", prog_df, df)

            st.markdown('<div class="marker-gold"></div>', unsafe_allow_html=True)
            if col_g.button(f"Κορυφή Ταμείου (ATH)\n{peak_bankroll:.2f} € 🏔️", key="btn_ath", use_container_width=True): show_progression_dialog("profit", prog_df, df)

            st.markdown('<div class="marker-neutral"></div>', unsafe_allow_html=True)
            if col_h.button(f"Σύνολο Στοιχημάτων\n{total_bets}", key="btn_all", use_container_width=True): show_bets_dialog("📋 Όλα τα Διευθετημένα Δελτία", completed_bets, df)

            st.markdown("---")
            st.markdown("### 📉 Ημερήσια Εξέλιξη Ταμείου")
            df_line = prog_df.sort_values(by="DateTime").copy()
            df_line['Ημ/νια'] = pd.to_datetime(df_line['Date']).dt.strftime('%d/%m/%Y')
            df_line['Bet_Count'] = range(1, len(df_line) + 1)
            zero_point = pd.DataFrame([{'Bet_Count': 0, 'Cumulative_Profit': 0.0, 'Balance': m_br, 'Ημ/νια': '-', 'Event': 'Αρχικό Κεφάλαιο', 'Profit': 0.0}])
            df_line = pd.concat([zero_point, df_line], ignore_index=True)
            
            base = alt.Chart(df_line).encode(
                x=alt.X('Bet_Count:Q', axis=alt.Axis(labels=False, title=None, ticks=False, grid=False)),
                y=alt.Y('Balance:Q', title="Υπόλοιπο (€)", axis=alt.Axis(gridColor="#1f2937"))
            )
            area = base.mark_area(interpolate='basis', opacity=0.3).encode(color=alt.condition(alt.datum['Balance'] >= m_br, alt.value('#10b981'), alt.value('#ef4444')))
            line = base.mark_line(interpolate='basis', strokeWidth=4).encode(color=alt.condition(alt.datum['Balance'] >= m_br, alt.value('#4ade80'), alt.value('#ff4b4b')))
            hover_points = base.mark_circle(size=300, color="transparent").encode(tooltip=[alt.Tooltip('Ημ/νια:N', title='Ημερομηνία'), alt.Tooltip('Balance:Q', title="Υπόλοιπο (€)", format='.2f')])
            chart = (area + line + hover_points).properties(height=350)
            st.altair_chart(chart, use_container_width=True, theme="streamlit")

            st.markdown("---")
            st.markdown("### 📋 Αναλυτικό Ιστορικό (Ανά Εβδομάδα)")
            m_df['JustDate'] = pd.to_datetime(m_df['Date']).dt.date
            m_df['Week'] = pd.to_datetime(m_df['Date']).dt.isocalendar().week
            weeks = sorted(m_df['Week'].dropna().unique().tolist(), reverse=True)
            
            for w in weeks:
                week_df = m_df[m_df['Week'] == w]
                week_profit = week_df['Profit'].sum()
                wp_emoji = "🟢" if week_profit > 0 else "🔴" if week_profit < 0 else "⚪"
                min_w_date = week_df['JustDate'].min().strftime('%d/%m/%Y')
                max_w_date = week_df['JustDate'].max().strftime('%d/%m/%Y')
                
                st.markdown(f"#### 📅 {w}η Εβδομάδα ({min_w_date} - {max_w_date}) | Ταμείο: {wp_emoji} {week_profit:.2f} €")
                days = sorted(week_df['JustDate'].dropna().unique().tolist(), reverse=True)
                for day in days:
                    day_df = week_df[week_df['JustDate'] == day]
                    day_profit = day_df['Profit'].sum()
                    day_str = f"{day.strftime('%d/%m/%Y')} ({GREEK_MONTHS[day.month]})"
                    if day_profit > 0: d_emoji = "🟢"; d_prof_str = f"+{day_profit:.2f}"
                    elif day_profit < 0: d_emoji = "🔴"; d_prof_str = f"{day_profit:.2f}"
                    else: d_emoji = "⚪"; d_prof_str = f"{day_profit:.2f}"
                        
                    with st.expander(f"{d_emoji} {day_str}  |  Ημερήσιο Κέρδος: {d_prof_str} €", expanded=False):
                        st.markdown("<p style='color: #a8dadc; font-size: 13px; margin-bottom: 10px;'>💡 Κάνε κλικ σε οποιοδήποτε δελτίο για να δεις την αναλυτική απόδειξη.</p>", unsafe_allow_html=True)
                        display_df = day_df.drop(columns=['MonthGroup', 'Legs_Data', 'JustDate', 'Week'], errors='ignore')[DISPLAY_ORDER].sort_values(by="Α/Α", ascending=False)
                        
                        df_key = f"df_{day.strftime('%Y%m%d')}"
                        event = st.dataframe(display_df, use_container_width=True, hide_index=True, column_config=GREEK_COLUMNS, on_select="rerun", selection_mode="single-row", key=df_key)
                        
                        last_op_key = f"last_op_{df_key}"
                        if event.selection.rows:
                            sel_idx = event.selection.rows[0]
                            sel_aa = display_df.iloc[sel_idx]['Α/Α']
                            
                            if st.session_state.get(last_op_key) != sel_aa:
                                st.session_state[last_op_key] = sel_aa
                                st.session_state['auto_open_ticket'] = int(sel_aa)
                                st.rerun()
                        else:
                            st.session_state[last_op_key] = None
                st.markdown("<br>", unsafe_allow_html=True)

elif page == "🌍 All-Time Στατιστικά":
    st.header("🌍 All-Time Στατιστικά (Lifetime)")
    
    if df.empty:
        st.warning("Δεν βρέθηκαν στοιχήματα στο Ιστορικό.")
    else:
        completed_bets = df[df['Status'].isin(["🟢 Κερδισμένο", "🔴 Χαμένο", "🟡 Cash Out", "🔵 Ακυρωμένο"])]
        total_profit = completed_bets['Profit'].sum()
        total_staked = completed_bets['Stake'].sum()
        yield_pct = (total_profit / total_staked * 100) if total_staked > 0 else 0
        wl_bets = completed_bets[completed_bets['Status'].isin(["🟢 Κερδισμένο", "🔴 Χαμένο"])]
        win_rate = (len(wl_bets[wl_bets['Profit'] > 0]) / len(wl_bets) * 100) if len(wl_bets) > 0 else 0
        
        c1, c2, c3 = st.columns(3)
        c1.metric("🌍 Συνολικό Κέρδος (Lifetime)", f"{total_profit:.2f} €")
        c2.metric("🎯 Lifetime Win Rate", f"{win_rate:.1f} %")
        c3.metric("📈 Lifetime Yield", f"{yield_pct:.2f} %")
        
        st.markdown("---")
        st.markdown("### 🧠 Lifetime Fun Facts & Insights (Ειδικά Στατιστικά)")
        team_profits = {}
        player_profits = {}
        display_names = {}
        
        def add_to_dict(e_dict, orig_name, profit_val):
            if not orig_name: return
            norm = normalize_greek(orig_name)
            if len(norm) < 2: return
            if norm not in e_dict:
                e_dict[norm] = 0.0
                display_names[norm] = orig_name
            e_dict[norm] += profit_val

        def process_entities(ev_main, ma_str, profit_to_add):
            ev_main = str(ev_main).split("(")[0].strip()
            found_teams = False
            for delim in [' - ', ' vs ', '-']:
                if delim in ev_main and len(ev_main.split(delim)) == 2:
                    parts = ev_main.split(delim)
                    t1, t2 = parts[0].strip(), parts[1].strip()
                    add_to_dict(team_profits, t1, profit_to_add)
                    add_to_dict(team_profits, t2, profit_to_add)
                    found_teams = True
                    break
            if not found_teams and ev_main and len(ev_main) > 2:
                add_to_dict(team_profits, ev_main, profit_to_add)

            if pd.notna(ma_str) and str(ma_str).strip() != "":
                for m_part in str(ma_str).split('|'):
                    m_clean = re.sub(r'[^\w\s-]', '', m_part).strip()
                    words = m_clean.split()
                    p_name = []
                    for w in words:
                        if re.search(r'\d', w) or (w and normalize_greek(w) in ignore_words_set): break
                        p_name.append(w)
                    final_p = " ".join(p_name).strip()
                    if final_p and len(final_p) > 2 and normalize_greek(final_p) not in ["home", "away", "draw", "νικη", "ισοπαλια", "yes", "no"]:
                        add_to_dict(player_profits, final_p, profit_to_add)

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

        best_team_norm, best_team_prof = max(team_profits.items(), key=lambda x: x[1]) if team_profits else ("-", 0.0)
        worst_team_norm, worst_team_prof = min(team_profits.items(), key=lambda x: x[1]) if team_profits else ("-", 0.0)
        best_player_norm, best_player_prof = max(player_profits.items(), key=lambda x: x[1]) if player_profits else ("-", 0.0)
        worst_player_norm, worst_player_prof = min(player_profits.items(), key=lambda x: x[1]) if player_profits else ("-", 0.0)

        best_team_disp = display_names.get(best_team_norm, "-")
        worst_team_disp = display_names.get(worst_team_norm, "-")
        best_player_disp = display_names.get(best_player_norm, "-")
        worst_player_disp = display_names.get(worst_player_norm, "-")

        best_team_disp_s = best_team_disp[:18] + ".." if len(best_team_disp) > 18 else best_team_disp
        worst_team_disp_s = worst_team_disp[:18] + ".." if len(worst_team_disp) > 18 else worst_team_disp
        best_player_disp_s = best_player_disp[:18] + ".." if len(best_player_disp) > 18 else best_player_disp
        worst_player_disp_s = worst_player_disp[:18] + ".." if len(worst_player_disp) > 18 else worst_player_disp

        c_ff3, c_ff4, c_ff5, c_ff6 = st.columns(4)
        
        st.markdown('<div class="marker-gold"></div>', unsafe_allow_html=True)
        if c_ff3.button(f"🏆 Χρυσή Ομάδα\n{best_team_disp_s} (+{best_team_prof:.2f} €)" if best_team_prof > 0 else "🏆 Χρυσή Ομάδα\n-", key="btn_ff_best", use_container_width=True):
            if best_team_prof > 0:
                team_df = completed_bets[completed_bets['Event'].astype(str).apply(normalize_greek).str.contains(best_team_norm, na=False) | completed_bets['Legs_Data'].astype(str).apply(normalize_greek).str.contains(best_team_norm, na=False)]
                show_bets_dialog(f"🏆 Ιστορικό: Αγώνες με {best_team_disp}", team_df, df)
            else: st.toast("Δεν υπάρχει ακόμα κερδοφόρα ομάδα!", icon="⚠️")

        st.markdown('<div class="marker-dark"></div>', unsafe_allow_html=True)
        if c_ff4.button(f"🧊 Μαύρη Λίστα Ομάδων\n{worst_team_disp_s} ({worst_team_prof:.2f} €)" if worst_team_prof < 0 else "🧊 Μαύρη Λίστα\n-", key="btn_ff_worst", use_container_width=True):
            if worst_team_prof < 0:
                team_df = completed_bets[completed_bets['Event'].astype(str).apply(normalize_greek).str.contains(worst_team_norm, na=False) | completed_bets['Legs_Data'].astype(str).apply(normalize_greek).str.contains(worst_team_norm, na=False)]
                show_bets_dialog(f"🧊 Ιστορικό: Αγώνες με {worst_team_disp}", team_df, df)
            else: st.toast("Δεν υπάρχει ακόμα ζημιογόνα ομάδα!", icon="⚠️")
                
        st.markdown('<div class="marker-player1"></div>', unsafe_allow_html=True)
        if c_ff5.button(f"🥇 MVP Παίκτης / Ειδικό\n{best_player_disp_s} (+{best_player_prof:.2f} €)" if best_player_prof > 0 else "🥇 MVP Παίκτης\n-", key="btn_ff_pbest", use_container_width=True):
            if best_player_prof > 0:
                p_df = completed_bets[completed_bets['Market'].astype(str).apply(normalize_greek).str.contains(best_player_norm, na=False) | completed_bets['Legs_Data'].astype(str).apply(normalize_greek).str.contains(best_player_norm, na=False)]
                show_bets_dialog(f"🥇 Ιστορικό: Στοιχήματα σε {best_player_disp}", p_df, df)
            else: st.toast("Δεν υπάρχει κερδοφόρος παίκτης!", icon="⚠️")
                
        st.markdown('<div class="marker-player2"></div>', unsafe_allow_html=True)
        if c_ff6.button(f"📉 Χειρότερος Παίκτης\n{worst_player_disp_s} ({worst_player_prof:.2f} €)" if worst_player_prof < 0 else "📉 Χειρότερος Παίκτης\n-", key="btn_ff_pworst", use_container_width=True):
            if worst_player_prof < 0:
                p_df = completed_bets[completed_bets['Market'].astype(str).apply(normalize_greek).str.contains(worst_player_norm, na=False) | completed_bets['Legs_Data'].astype(str).apply(normalize_greek).str.contains(worst_player_norm, na=False)]
                show_bets_dialog(f"📉 Ιστορικό: Στοιχήματα σε {worst_player_disp}", p_df, df)
            else: st.toast("Δεν υπάρχει ζημιογόνος παίκτης!", icon="⚠️")

        st.markdown("---")
        st.markdown("### 🏀 Lifetime Ανάλυση ανά Άθλημα")
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


elif page == "⚡ Ανοιχτά Δελτία":
    st.header("⏳ Κέντρο Διευθέτησης (Εκκρεμή Στοιχήματα)")
    
    pending_df = df[df['Status'] == "⚪ Εκκρεμές"].copy()
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
        
        edit_pending_df = pending_df.drop(columns=['Legs_Data', 'MonthGroup'], errors='ignore')[DISPLAY_ORDER].sort_values(by="Α/Α", ascending=False)
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
                save_df = df.drop(columns=['Α/Α', 'MonthGroup'], errors='ignore')
                save_df['Time'] = pd.to_datetime(save_df['Time'].astype(str), errors='coerce').dt.strftime('%H:%M').fillna('00:00')
                save_data(save_df)
                st.session_state['show_toast'] = True
                st.session_state['toast_message'] = "Τα στοιχήματα διευθετήθηκαν!"
                st.rerun()
            else:
                st.toast("Δεν κάνατε καμία αλλαγή στην Κατάσταση των δελτίων.", icon="ℹ️")

elif page == "⚙️ Διαχείριση Ιστορικού":
    st.header("⚙️ Κέντρο Ελέγχου (Διαχείριση Ιστορικού)")
    
    hist_count = len(df)
    hist_staked = df['Stake'].sum() if not df.empty else 0.0
    hist_profit = df['Profit'].sum() if not df.empty else 0.0
    
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
        if not df.empty:
            edit_opts = {}
            for idx, row in df.sort_values(by="Α/Α", ascending=False).iterrows():
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
                
                e_odds = safe_float(row_data['Odds'], 1.00)
                e_stake = safe_float(row_data['Stake'], 0.0)
                e_profit = safe_float(row_data['Profit'], 0.0)
                
                e_status = row_data['Status']
                e_legs_data = row_data['Legs_Data']
                
                e_legs = []
                if pd.notna(e_legs_data) and e_legs_data != '' and str(e_legs_data) != 'nan':
                    try: e_legs = json.loads(e_legs_data)
                    except: pass
                    
                with st.container(border=True):
                    type_idx = BET_TYPES.index(e_type) if e_type in BET_TYPES else 0
                    
                    st.markdown("<style>div[role='radiogroup'] { display: flex; justify-content: center; gap: 10px; }</style>", unsafe_allow_html=True)
                    edit_bet_type = st.radio("Τύπος Στοιχήματος", BET_TYPES, horizontal=True, index=type_idx, key=f"ed_type_{selected_aa}", label_visibility="collapsed")
                    edit_num_legs = len(e_legs) if len(e_legs) >= 2 else 2
                    if edit_bet_type != "Μονό":
                        edit_num_legs = st.number_input("Πόσα σημεία (ή αγώνες) έχει το δελτίο;", min_value=2, max_value=15, value=int(edit_num_legs), key=f"ed_legs_num_{selected_aa}")
                        
                    st.markdown("<h5 style='color: #a8dadc; border-bottom: 1px solid #1e3a5f; padding-bottom: 5px; margin-top: 15px;'>1. Βασικά Στοιχεία</h5>", unsafe_allow_html=True)
                    c1, c2, c3 = st.columns([1, 1, 2])
                    ed_d = c1.date_input("Ημερομηνία", e_date, format="DD/MM/YYYY", key=f"ed_date_{selected_aa}")
                    ed_t = c2.time_input("Ώρα", e_time, step=60, key=f"ed_time_{selected_aa}")
                    sport_idx = list(SPORT_ICONS.values()).index(e_sport) if e_sport in SPORT_ICONS.values() else list(SPORT_ICONS.values()).index("🏀 Μπάσκετ")
                    ed_sport = c3.selectbox("Άθλημα", list(SPORT_ICONS.values()), index=sport_idx, key=f"ed_sport_{selected_aa}")
                    
                    st.markdown("<br>", unsafe_allow_html=True)
                    entry_mode_ed = st.radio("Λειτουργία Συμπλήρωσης:", ["🤖 Έξυπνος Βοηθός", "✍️ Ελεύθερο Κείμενο"], horizontal=True, index=1, key=f"ed_entry_mode_{selected_aa}")
                    
                    new_legs = []
                    final_ev_str, final_ma_str = "" , ""
                    st.markdown("<h5 style='color:#a8dadc; border-bottom:1px solid #1e3a5f; padding-bottom:5px; margin-top:20px;'>2. Επιλογές Δελτίου</h5>", unsafe_allow_html=True)
                    
                    if edit_bet_type == "Μονό":
                        with st.container(border=True):
                            final_ev_str = render_event_input(ed_sport, f"ed_ev_{selected_aa}", entry_mode_ed, st)
                            st.markdown("---")
                            final_ma_str = render_market_input(ed_sport, f"ed_ma_{selected_aa}", entry_mode_ed, final_ev_str, st, prefill=e_market)
                            
                    elif edit_bet_type == "Bet Builder":
                        with st.container(border=True):
                            st.markdown("**🏟️ Κοινός Αγώνας**")
                            bb_ev = e_legs[0]['event'] if e_legs and 'event' in e_legs[0] else e_event
                            bb_ev_clean = bb_ev.split(" (")[0] if " (" in bb_ev else bb_ev
                            final_ev_str = render_event_input(ed_sport, f"ed_bb_ev_{selected_aa}", entry_mode_ed, st)
                        
                        for i in range(int(edit_num_legs)):
                            with st.container(border=True):
                                st.markdown(f"**📌 Σημείο {i+1}**")
                                leg_ma = e_legs[i]['market'] if i < len(e_legs) else ""
                                leg_od = safe_float(e_legs[i].get('odds', 1.50), 1.00) if i < len(e_legs) else 1.50
                                leg_st = e_legs[i]['status'] if i < len(e_legs) and 'status' in e_legs[i] else "⚪ Εκκρεμές"
                                
                                l_ma_final = render_market_input(ed_sport, f"ed_bb_lma_{i}_{selected_aa}", entry_mode_ed, final_ev_str, st, prefill=leg_ma)
                                st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
                                c_od, c_st = st.columns(2)
                                l_od_final = c_od.number_input(f"Απόδοση {i+1}", min_value=1.00, step=0.01, value=leg_od, key=f"ed_bb_lod_{i}_{selected_aa}")
                                st_idx = STATUS_LIST.index(leg_st) if leg_st in STATUS_LIST else 0
                                l_st_final = c_st.selectbox(f"Κατάστ. {i+1}", STATUS_LIST, index=st_idx, key=f"ed_bb_lst_{i}_{selected_aa}")
                                new_legs.append({"event": final_ev_str, "market": l_ma_final, "odds": l_od_final, "status": l_st_final})

                    elif edit_bet_type == "Παρολί με Bet Builders":
                        temp_odds = 1.0
                        for i in range(int(edit_num_legs)):
                            with st.container(border=True):
                                st.markdown(f"**🏟️ Αγώνας {i+1} (Bet Builder)**")
                                leg_ev = e_legs[i]['event'] if i < len(e_legs) else ""
                                leg_ma = e_legs[i]['market'].replace(' | ', '\n') if i < len(e_legs) else ""
                                leg_od = safe_float(e_legs[i].get('odds', 1.50), 1.00) if i < len(e_legs) else 1.50
                                leg_st = e_legs[i]['status'] if i < len(e_legs) and 'status' in e_legs[i] else "⚪ Εκκρεμές"
                                
                                l_ev_final = render_event_input(ed_sport, f"ed_pbb_ev_{i}_{selected_aa}", entry_mode_ed, st)
                                st.markdown("---")
                                
                                c_ma, c_od, c_st = st.columns([4, 1, 2])
                                ed_lma_key = f"ed_pbb_ma_{i}_{selected_aa}"
                                l_ma_final = c_ma.text_area(f"Επιλογές Bet Builder (Μία ανά γραμμή):", value=leg_ma, height=68, key=ed_lma_key)
                                
                                l_od_final = c_od.number_input(f"Απόδοση:", min_value=1.00, step=0.01, value=leg_od, key=f"ed_leg_od_{i}_{selected_aa}", on_change=update_auto_odds_edit, args=(selected_aa, edit_num_legs))
                                st_idx = STATUS_LIST.index(leg_st) if leg_st in STATUS_LIST else 0
                                l_st_final = c_st.selectbox(f"Κατάσταση:", STATUS_LIST, index=st_idx, key=f"ed_leg_st_{i}_{selected_aa}", on_change=update_auto_odds_edit, args=(selected_aa, edit_num_legs))
                                
                                clean_ma = l_ma_final.replace('\n', ' | ') if l_ma_final else ""
                                new_legs.append({"event": l_ev_final, "market": clean_ma, "odds": l_od_final, "status": l_st_final})
                                if l_st_final != "🔵 Ακυρωμένο": temp_odds *= l_od_final
                            
                        if 'auto_odds_multi' not in st.session_state or st.session_state['auto_odds_multi'] == 1.0:
                            st.session_state['auto_odds_multi'] = temp_odds

                    else: 
                        temp_odds = 1.0
                        for i in range(int(edit_num_legs)):
                            with st.container(border=True):
                                st.markdown(f"**📌 Επιλογή {i+1}**")
                                leg_ev = e_legs[i]['event'] if i < len(e_legs) else ""
                                leg_ma = e_legs[i]['market'] if i < len(e_legs) else ""
                                leg_od = safe_float(e_legs[i].get('odds', 1.50), 1.00) if i < len(e_legs) else 1.50
                                leg_st = e_legs[i]['status'] if i < len(e_legs) and 'status' in e_legs[i] else "⚪ Εκκρεμές"
                                
                                l_ev_final = render_event_input(ed_sport, f"ed_lev_{i}_{selected_aa}", entry_mode_ed, st)
                                st.markdown("<div style='height: 5px;'></div>", unsafe_allow_html=True)
                                l_ma_final = render_market_input(ed_sport, f"ed_lma_{i}_{selected_aa}", entry_mode_ed, l_ev_final, st, prefill=leg_ma)
                                st.markdown("<div style='height: 5px;'></div>", unsafe_allow_html=True)
                                
                                c_od, c_st = st.columns(2)
                                l_od_final = c_od.number_input(f"Απόδοση {i+1}", min_value=1.00, step=0.01, value=leg_od, key=f"ed_leg_od_{i}_{selected_aa}", on_change=update_auto_odds_edit, args=(selected_aa, edit_num_legs))
                                st_idx = STATUS_LIST.index(leg_st) if leg_st in STATUS_LIST else 0
                                l_st_final = c_st.selectbox(f"Κατάστ. {i+1}", STATUS_LIST, index=st_idx, key=f"ed_leg_st_{i}_{selected_aa}", on_change=update_auto_odds_edit, args=(selected_aa, edit_num_legs))
                                new_legs.append({"event": l_ev_final, "market": l_ma_final, "odds": l_od_final, "status": l_st_final})
                                if l_st_final != "🔵 Ακυρωμένο": temp_odds *= l_od_final
                            
                        if 'auto_odds_multi' not in st.session_state or st.session_state['auto_odds_multi'] == 1.0:
                            st.session_state['auto_odds_multi'] = temp_odds
                            
                    st.markdown("---")
                    st.markdown("<h5 style='color:#a8dadc; border-bottom:1px solid #1e3a5f; padding-bottom:5px; margin-top:20px;'>3. Ταμείο & Ποντάρισμα</h5>", unsafe_allow_html=True)
                    with st.container(border=True):
                        st.markdown("<div style='background-color: rgba(6, 13, 26, 0.5); padding: 15px; border-radius: 8px;'>", unsafe_allow_html=True)
                        c5, c6, c7, c8 = st.columns(4)
                        
                        m_str_ed = ed_d.strftime('%Y-%m')
                        month_br_ed = custom_db.get("bankrolls", {}).get(m_str_ed, 0.0)
                        unit_val_ed = month_br_ed / 20.0 if month_br_ed > 0 else 0.0
                        
                        if unit_val_ed > 0:
                            STAKE_PRESETS_DYNAMIC_ED = [f"🎯 1 Μονάδα ({unit_val_ed:.2f} €)", f"🛡️ 0.5 Μονάδα ({unit_val_ed / 2:.2f} €)", "✏️ Χειροκίνητο Ποσό..."]
                        else:
                            STAKE_PRESETS_DYNAMIC_ED = ["✏️ Χειροκίνητο Ποσό..."]
                            st.warning("⚠️ Δεν έχει οριστεί κάβα για αυτόν τον μήνα. Υπολογισμός ανενεργός.")
                            
                        if edit_bet_type == "Μονό":
                            ed_odds = c5.number_input("Απόδοση", min_value=1.01, step=0.01, value=safe_float(e_odds, 1.01), key=f"ed_odds_{selected_aa}")
                            ed_preset = c6.selectbox("Ποντάρισμα", STAKE_PRESETS_DYNAMIC_ED, index=len(STAKE_PRESETS_DYNAMIC_ED)-1, key=f"ed_stake_p_{selected_aa}")
                            ed_custom = c7.number_input("Ποσό (€)", min_value=0.0, step=0.05, value=e_stake, format="%.2f", key=f"ed_stake_c_{selected_aa}")
                            status_idx = STATUS_LIST.index(e_status) if e_status in STATUS_LIST else 0
                            ed_status = c8.selectbox("Κατάσταση", STATUS_LIST, index=status_idx, key=f"ed_status_{selected_aa}")
                        elif edit_bet_type == "Bet Builder":
                            ed_odds = c5.number_input("Απόδοση", min_value=1.00, step=0.01, value=safe_float(e_odds, 1.00), key=f"ed_odds_{selected_aa}")
                            ed_preset = c6.selectbox("Ποντάρισμα", STAKE_PRESETS_DYNAMIC_ED, index=len(STAKE_PRESETS_DYNAMIC_ED)-1, key=f"ed_stake_p_{selected_aa}")
                            ed_custom = c7.number_input("Ποσό (€)", min_value=0.0, step=0.05, value=e_stake, format="%.2f", key=f"ed_stake_c_{selected_aa}")
                            status_options = ["Αυτόματος Υπολογισμός ⚙️", "🟡 Cash Out"]
                            s_idx = 1 if e_status == "🟡 Cash Out" else 0
                            status_sel = c8.selectbox("Κατάσταση", status_options, index=s_idx, key=f"ed_status_{selected_aa}")
                            if status_sel == "Αυτόματος Υπολογισμός ⚙️": ed_status = calc_overall_status(new_legs)
                            else: ed_status = "🟡 Cash Out"
                        else:
                            ed_odds = c5.number_input("Απόδοση", min_value=1.00, step=0.01, value=safe_float(st.session_state.get('auto_odds_multi', e_odds), 1.00), key=f"ed_odds_{selected_aa}")
                            ed_preset = c6.selectbox("Ποντάρισμα", STAKE_PRESETS_DYNAMIC_ED, index=len(STAKE_PRESETS_DYNAMIC_ED)-1, key=f"ed_stake_p_{selected_aa}")
                            ed_custom = c7.number_input("Ποσό (€)", min_value=0.0, step=0.05, value=e_stake, format="%.2f", key=f"ed_stake_c_{selected_aa}")
                            status_options = ["Αυτόματος Υπολογισμός ⚙️", "🟡 Cash Out"]
                            s_idx = 1 if e_status == "🟡 Cash Out" else 0
                            status_sel = c8.selectbox("Κατάσταση", status_options, index=s_idx, key=f"ed_status_{selected_aa}")
                            if status_sel == "Αυτόματος Υπολογισμός ⚙️": ed_status = calc_overall_status(new_legs)
                            else: ed_status = "🟡 Cash Out"
                        st.markdown("</div>", unsafe_allow_html=True)
                    
                    ed_co_val = 0.0
                    if ed_status == "🟡 Cash Out":
                        existing_co = e_stake + e_profit if e_status == "🟡 Cash Out" else 0.0
                        ed_co_val = st.number_input("Επιστροφή Cash Out (€)", min_value=0.0, step=0.01, value=safe_float(existing_co, 0.0), format="%.2f", key=f"ed_co_{selected_aa}")
                    
                    st.markdown("<br>", unsafe_allow_html=True)
                    st.markdown("<div style='background-color: rgba(239, 68, 68, 0.1); padding: 10px; border-radius: 8px; border-left: 4px solid #ef4444; margin-bottom: 15px;'>", unsafe_allow_html=True)
                    delete_check = st.checkbox("⚠️ Οριστική διαγραφή αυτού του δελτίου", key=f"del_check_{selected_aa}")
                    st.markdown("</div>", unsafe_allow_html=True)
                    
                    if st.button("💾 ΑΠΟΘΗΚΕΥΣΗ ΑΛΛΑΓΩΝ", type="primary", key=f"ed_save_btn_{selected_aa}", use_container_width=True):
                        if delete_check:
                            df.drop(index=real_idx, inplace=True)
                            save_df = df.drop(columns=['Α/Α', 'MonthGroup'], errors='ignore')
                            save_df['Time'] = pd.to_datetime(save_df['Time'].astype(str), errors='coerce').dt.strftime('%H:%M').fillna('00:00')
                            save_data(save_df)
                            st.session_state['show_toast'] = True
                            st.session_state['toast_message'] = "Το δελτίο διαγράφηκε!"
                            st.rerun()
                        else:
                            profit = 0.0
                            if ed_preset.startswith("🎯"): stake = unit_val_ed
                            elif ed_preset.startswith("🛡️"): stake = unit_val_ed / 2.0
                            else: stake = ed_custom
                            
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
                                    market_parts.append(f"{emoji} {l['market']} ({safe_float(l.get('odds', 1.0), 1.0):.2f})")
                                final_ma_str = " | ".join(market_parts)
                            
                            try:
                                save_new_entities_to_db(ed_sport)
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
                                
                                save_df = df.drop(columns=['Α/Α', 'MonthGroup'], errors='ignore')
                                save_df['Time'] = pd.to_datetime(save_df['Time'].astype(str), errors='coerce').dt.strftime('%H:%M').fillna('00:00')
                                save_data(save_df)
                                st.session_state['show_toast'] = True
                                st.session_state['toast_message'] = "Οι αλλαγές αποθηκεύτηκαν!"
                                st.session_state['auto_odds_multi'] = 1.0
                                st.rerun()
                            except Exception as e:
                                st.error(f"❌ Υπήρξε πρόβλημα: {e}")

    with tab2:
        st.info("💡 Αλλάξτε κατευθείαν τις τιμές στον πίνακα και πατήστε αποθήκευση.")
        edit_df = df.copy()
        if 'Legs_Data' in edit_df.columns:
            edit_df = edit_df.drop(columns=['Legs_Data']) 
        if not edit_df.empty:
            edit_df = edit_df.drop(columns=['MonthGroup'], errors='ignore')[DISPLAY_ORDER].sort_values(by="Α/Α", ascending=False)
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