import streamlit as st
import pandas as pd
import os
import json
import altair as alt
from datetime import date, datetime
import locale
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from gspread_dataframe import set_with_dataframe, get_as_dataframe
import re
import unicodedata
import difflib
import streamlit.components.v1 as components

# Απενεργοποίηση του ορίου γραμμών για τα γραφήματα 
alt.data_transformers.disable_max_rows()

# Ρύθμιση για Ελληνικά
try:
    locale.setlocale(locale.LC_TIME, 'el_GR.UTF-8')
except:
    pass 

# Χειροκίνητο Λεξικό για σίγουρα Ελληνικά
GREEK_MONTHS = {
    1: "Ιανουάριος", 2: "Φεβρουάριος", 3: "Μάρτιος", 4: "Απρίλιος",
    5: "Μάιος", 6: "Ιούνιος", 7: "Ιούλιος", 8: "Αύγουστος",
    9: "Σεπτέμβριος", 10: "Οκτώβριος", 11: "Νοέμβριος", 12: "Δεκέμβριος"
}

EXPECTED_COLS = ['Date', 'Time', 'Type', 'Sport', 'Event', 'Market', 'Odds', 'Stake', 'Status', 'Profit', 'Legs_Data']
DISPLAY_ORDER = ['Α/Α', 'Status', 'Date', 'Time', 'Type', 'Sport', 'Event', 'Market', 'Odds', 'Stake', 'Profit']

STATUS_LIST = ["⚪ Εκκρεμές", "🟢 Κερδισμένο", "🔴 Χαμένο", "🔵 Ακυρωμένο", "🟡 Cash Out"]
STAKE_PRESETS = [0.30, 0.15, "Χειροκίνητα..."]
BET_TYPES = ["Μονό", "Παρολί", "Bet Builder"]

SPORT_ICONS = {
    "Ποδόσφαιρο": "⚽ Ποδόσφαιρο",
    "Μπάσκετ": "🏀 Μπάσκετ",
    "Τένις": "🎾 Τένις",
    "Άλλο": "🎯 Άλλο",
    "Διάφορα": "🌎 Διάφορα"
}

st.set_page_config(page_title="My Bet Tracker", page_icon="📈", layout="wide")

# ==========================================
# 🎨 PREMIUM UI CSS & NEW TYPOGRAPHY
# ==========================================
custom_css = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&display=swap');

/* 🔹 Εφαρμογή γραμματοσειράς ΜΟΝΟ σε κείμενα, εξαιρώντας span/div για να μην σπάνε τα εικονίδια του Streamlit */
html, body, p, h1, h2, h3, h4, h5, h6, label, input, select, textarea, table, button p {
    font-family: 'Poppins', sans-serif !important;
}

.stApp { background-color: #0b172a; }
[data-testid="stSidebar"] { background-color: #060d1a; border-right: 1px solid #1e3a5f; }

.sidebar-header {
    font-size: 0.8rem;
    color: #4db8ff;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    font-weight: 700;
    margin-top: 25px;
    margin-bottom: 10px;
    border-bottom: 1px solid #1e3a5f;
    padding-bottom: 8px;
    font-family: 'Poppins', sans-serif !important;
}

[data-testid="stStatusWidget"] { display: none !important; }

[data-testid="stVerticalBlockBorderWrapper"], div[role="dialog"] {
    background-color: #0f1c2e !important;
    border: 1px solid #1e3a5f !important;
    border-radius: 16px !important;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5) !important;
}

[data-testid="stDialog"] > div {
    background-color: #0b172a !important;
    border-radius: 20px !important;
    border: 1px solid #2a4365 !important;
}
[data-testid="stDialog"] header { background-color: #0b172a !important; }

.stTextInput input, .stNumberInput input, 
[data-baseweb="select"] > div, 
.stDateInput input, .stTimeInput input {
    background-color: #16263b !important;
    color: #e2e8f0 !important;
    border: 1px solid #2a4365 !important;
    border-radius: 8px !important;
    font-size: 15px !important;
    letter-spacing: 0.3px !important;
}

div[data-baseweb="input"]:focus-within, div[data-baseweb="select"]:focus-within {
    border-color: #4db8ff !important;
    box-shadow: inset 0 0 0 1px #4db8ff !important;
}

button[kind="primary"] {
    background: linear-gradient(90deg, #10b981, #059669) !important;
    color: white !important;
    font-weight: 600 !important;
    border: none !important;
    border-radius: 8px !important;
    box-shadow: 0 4px 6px rgba(0,0,0,0.3) !important;
    transition: all 0.2s ease !important;
}
button[kind="primary"]:hover {
    background: linear-gradient(90deg, #059669, #047857) !important;
    transform: translateY(-2px);
}
button[kind="primary"] * { color: white !important; }

/* 🔹 Δευτερεύοντα Κουμπιά / Στατιστικά */
button[kind="secondary"] {
    background-color: #16263b !important;
    border: 1px solid #1e3a5f !important;
    border-radius: 10px !important;
    padding: 15px !important;
    width: 100% !important;
    height: auto !important;
    min-height: 90px !important;
    display: flex !important;
    flex-direction: column !important;
    align-items: center !important;  
    justify-content: center !important; 
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3) !important;
    transition: all 0.2s ease !important;
}
button[kind="secondary"]:hover {
    transform: translateY(-3px) !important;
    box-shadow: 0 6px 12px rgba(0,0,0,0.4) !important;
}
button[kind="secondary"] p {
    white-space: pre-wrap !important;
    font-size: 1.15rem !important;
    color: #e2e8f0 !important;
    margin: 0 !important;
    line-height: 1.5 !important;
    text-align: center !important;  
    width: 100% !important;
}

/* 🎨 DYNAMIC COLORS ΓΙΑ ΤΑ ΣΤΑΤΙΣΤΙΚΑ */
div[data-testid="stElementContainer"]:has(.marker-positive),
div[data-testid="stElementContainer"]:has(.marker-negative),
div[data-testid="stElementContainer"]:has(.marker-neutral),
div[data-testid="stElementContainer"]:has(.marker-warning),
div[data-testid="stElementContainer"]:has(.marker-info) {
    margin: 0 !important; height: 0 !important; display: none !important;
}

/* Πράσινο */
div[data-testid="stElementContainer"]:has(.marker-positive) + div[data-testid="stElementContainer"] button {
    border: 1px solid #10b981 !important;
    background-color: rgba(16, 185, 129, 0.05) !important;
}
div[data-testid="stElementContainer"]:has(.marker-positive) + div[data-testid="stElementContainer"] button p {
    color: #10b981 !important; font-weight: 600 !important;
}

/* Κόκκινο */
div[data-testid="stElementContainer"]:has(.marker-negative) + div[data-testid="stElementContainer"] button {
    border: 1px solid #ef4444 !important;
    background-color: rgba(239, 68, 68, 0.05) !important;
}
div[data-testid="stElementContainer"]:has(.marker-negative) + div[data-testid="stElementContainer"] button p {
    color: #ef4444 !important; font-weight: 600 !important;
}

/* Πορτοκαλί */
div[data-testid="stElementContainer"]:has(.marker-warning) + div[data-testid="stElementContainer"] button {
    border: 1px solid #f59e0b !important;
    background-color: rgba(245, 158, 11, 0.05) !important;
}
div[data-testid="stElementContainer"]:has(.marker-warning) + div[data-testid="stElementContainer"] button p {
    color: #f59e0b !important; font-weight: 600 !important;
}

/* Μπλε */
div[data-testid="stElementContainer"]:has(.marker-info) + div[data-testid="stElementContainer"] button {
    border: 1px solid #3b82f6 !important;
    background-color: rgba(59, 130, 246, 0.05) !important;
}
div[data-testid="stElementContainer"]:has(.marker-info) + div[data-testid="stElementContainer"] button p {
    color: #3b82f6 !important; font-weight: 600 !important;
}

hr { border-color: #1e3a5f !important; margin: 1.5em 0 !important; }

/* 🔹 ΜΕΝΟΥ ΠΛΟΗΓΗΣΗΣ */
div[role="radiogroup"] > label {
    background-color: #16263b !important;
    padding: 12px 15px !important; 
    border-radius: 8px !important;
    border: 1px solid #1e3a5f !important;
    margin-bottom: 12px !important; 
    cursor: pointer;
}
</style>
"""
st.markdown(custom_css, unsafe_allow_html=True)

if 'form_reset_counter' not in st.session_state: st.session_state['form_reset_counter'] = 0
if 'show_toast' not in st.session_state: st.session_state['show_toast'] = False
if 'toast_message' not in st.session_state: st.session_state['toast_message'] = ""
if 'page_sel' not in st.session_state: st.session_state['page_sel'] = "📊 Dashboard & Στατιστικά"

if st.session_state['show_toast']:
    st.toast(st.session_state['toast_message'], icon="✅")
    st.session_state['show_toast'] = False 

# ==========================================
# 🧠 AI-Like Έξυπνη Αναζήτηση & Διόρθωση 
# ==========================================
def normalize_greek(text):
    if not text: return ""
    text = ''.join(c for c in unicodedata.normalize('NFD', str(text)) if unicodedata.category(c) != 'Mn')
    return text.lower().strip()

def find_team_match(t, norm_teams_dict):
    m = difflib.get_close_matches(t, norm_teams_dict.keys(), n=1, cutoff=0.65)
    if m: return norm_teams_dict[m[0]]
    for kt in norm_teams_dict.keys():
        if t in kt and len(t) >= 4:
            return norm_teams_dict[kt]
    return t

def get_event_suggestions(user_text, all_events, all_teams):
    if len(user_text) < 3: return []
    norm_user = normalize_greek(user_text)
    if norm_user in [normalize_greek(e) for e in all_events]: return []
        
    suggestions = []
    delim_found = False
    for delim in [' - ', ' vs ', '-']:
        if delim in user_text:
            delim_found = True
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
        full_matches = difflib.get_close_matches(norm_user, [normalize_greek(e) for e in all_events], n=2, cutoff=0.75)
        for fm in full_matches:
            for ev in all_events:
                if normalize_greek(ev) == fm:
                    suggestions.append(ev); break
                    
    return list(dict.fromkeys(suggestions))[:3]

def get_market_suggestions(user_text, all_markets):
    if len(user_text) < 3: return []
    norm_user = normalize_greek(user_text)
    if norm_user in [normalize_greek(m) for m in all_markets]: return []
        
    ignore_break_words = {'over', 'under', 'ov', 'un', 'o', 'u', 'ποντοι', 'ριμπαουντ', 'ασιστ', 'ασσιστ', 'τριποντα', 'γκολ', 'καρτες', 'σουτ', 'φαουλ', 'νικη', 'ισοπαλια', 'ηττα'}
    
    def get_entity_prefix(text):
        words = []
        for w in text.split():
            if re.search(r'\d', w) or w in ignore_break_words:
                break
            words.append(w)
        return " ".join(words)

    user_prefix = get_entity_prefix(norm_user)
    
    scored_markets = []
    for m in all_markets:
        norm_m = normalize_greek(m)
        if norm_user in norm_m:
            scored_markets.append((m, 2.0))
            continue
            
        m_prefix = get_entity_prefix(norm_m)
        if user_prefix and m_prefix:
            prefix_ratio = difflib.SequenceMatcher(None, user_prefix, m_prefix).ratio()
            if prefix_ratio < 0.65: continue 
            overall_ratio = difflib.SequenceMatcher(None, norm_user, norm_m).ratio()
            scored_markets.append((m, overall_ratio + prefix_ratio))
        else:
            overall_ratio = difflib.SequenceMatcher(None, norm_user, norm_m).ratio()
            if overall_ratio > 0.75:
                scored_markets.append((m, overall_ratio))
                
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

# ==========================================
# 🧾 PREMIUM DIGITAL RECEIPT (TICKET)
# ==========================================
def render_ticket_html(aa_val, df_source):
    row = df_source[df_source['Α/Α'] == aa_val].iloc[0]
    
    status_color = "#4db8ff"
    stamp_text = ""
    stamp_color = ""
    
    if row['Status'] == "🟢 Κερδισμένο": 
        status_color = "#10b981"
        stamp_text = "WON"
        stamp_color = "rgba(16, 185, 129, 0.15)"
    elif row['Status'] == "🔴 Χαμένο": 
        status_color = "#ef4444"
        stamp_text = "LOST"
        stamp_color = "rgba(239, 68, 68, 0.15)"
    elif row['Status'] == "🟡 Cash Out": 
        status_color = "#f59e0b"
        stamp_text = "CASH OUT"
        stamp_color = "rgba(245, 158, 11, 0.15)"
    elif row['Status'] == "🔵 Ακυρωμένο": 
        status_color = "#3b82f6"
        stamp_text = "VOID"
        stamp_color = "rgba(59, 130, 246, 0.15)"
    
    total_return = row['Stake'] + row['Profit'] if row['Status'] != "⚪ Εκκρεμές" else 0.0
    profit_str = f"+{row['Profit']:.2f} €" if row['Profit'] > 0 else f"{row['Profit']:.2f} €"
    ticket_id = f"#MB-{row['Α/Α']}{str(row['Date']).replace('-','')[2:]}"
    
    stamp_html = f"""<div style='position:absolute; top:50px; right:10px; color:{stamp_color}; font-size:65px; font-weight:900; transform:rotate(-15deg); border:4px solid {stamp_color}; padding:5px 15px; border-radius:15px; z-index:0; pointer-events:none; letter-spacing: 2px;'>{stamp_text}</div>""" if stamp_text else ""
    
    html = f"""
    <div style="background: linear-gradient(135deg, #16263b, #0f1c2e); padding: 30px; border-radius: 16px; border: 1px solid #1e3a5f; box-shadow: 0 15px 35px rgba(0,0,0,0.6); position: relative; overflow: hidden; font-family: 'Poppins', sans-serif;">
        {stamp_html}
        <div style="text-align: center; border-bottom: 2px dashed #2a4365; padding-bottom: 15px; margin-bottom: 20px; position: relative; z-index: 1;">
            <p style="margin: 0; color: #a8dadc; font-size: 13px; letter-spacing: 1px;">TICKET ID: {ticket_id}</p>
            <h2 style="margin: 5px 0 0 0; color: {status_color}; font-weight: 700; text-transform: uppercase; letter-spacing: 1.5px;">{row['Status']}</h2>
            <p style="margin: 5px 0 0 0; color: #718096; font-size: 13px;">{row['Date'].strftime('%d/%m/%Y')} • {row['Time'].strftime('%H:%M')}</p>
        </div>
        
        <div style="display: flex; justify-content: space-between; margin-bottom: 20px; position: relative; z-index: 1;">
            <div>
                <p style="margin: 0; font-size: 11px; color: #4db8ff; text-transform: uppercase; letter-spacing: 1px;">Άθλημα</p>
                <p style="margin: 0; font-size: 17px; font-weight: 600; color: #e2e8f0;">{row['Sport']}</p>
            </div>
            <div style="text-align: right;">
                <p style="margin: 0; font-size: 11px; color: #4db8ff; text-transform: uppercase; letter-spacing: 1px;">Τύπος</p>
                <p style="margin: 0; font-size: 17px; font-weight: 600; color: #e2e8f0;">{row['Type']}</p>
            </div>
        </div>
        
        <div style="margin-bottom: 25px; position: relative; z-index: 1;">
            <p style="margin: 0 0 15px 0; font-size: 12px; color: #4db8ff; text-transform: uppercase; letter-spacing: 1px; border-bottom: 1px solid #1e3a5f; padding-bottom: 8px;">Επιλογές Δελτίου</p>
    """
    
    if row['Type'] == "Μονό":
        html += f"""
        <div style="background-color: rgba(6, 13, 26, 0.5); padding: 15px; border-radius: 12px; margin-bottom: 10px; border-left: 4px solid {status_color};">
            <p style="margin: 0; font-weight: 600; color: #ffffff; font-size: 16px;">{row['Event']}</p>
            <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 10px;">
                <span style="color: #a8dadc; font-size: 14px;">{row['Market']}</span>
                <span style="font-weight: 700; font-size: 17px; color: #4db8ff;">{row['Odds']:.2f}</span>
            </div>
        </div>
        """
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
                    html += f"""
                    <div style="background-color: rgba(6, 13, 26, 0.5); padding: 15px; border-radius: 12px; margin-bottom: 10px; border-left: 4px solid {l_color};">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <span style="font-weight: 600; color: #ffffff; font-size: 15px;">{ev_name}</span>
                            <span style="font-size: 11px; font-weight: 600; color: {l_color}; padding: 3px 8px; background-color: rgba(0,0,0,0.3); border-radius: 12px;">{l_st}</span>
                        </div>
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 10px;">
                            <span style="color: #a8dadc; font-size: 14px;">{leg.get('market', '-')}</span>
                            <span style="font-weight: 700; font-size: 16px; color: #4db8ff;">{float(leg.get('odds', 1.0)):.2f}</span>
                        </div>
                    </div>
                    """
            except Exception as e:
                pass
    
    html += f"""
        </div>
        <div style="border-top: 2px dashed #2a4365; padding-top: 20px; position: relative; z-index: 1;">
            <div style="display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 15px;">
                <div>
                    <p style="margin: 0; font-size: 12px; color: #718096; text-transform: uppercase;">Ποντάρισμα</p>
                    <p style="margin: 0; font-size: 18px; font-weight: 600; color: #e2e8f0;">{row['Stake']:.2f} €</p>
                </div>
                <div style="text-align: right;">
                    <p style="margin: 0; font-size: 12px; color: #718096; text-transform: uppercase;">Συν. Απόδοση</p>
                    <p style="margin: 0; font-size: 18px; font-weight: 600; color: #e2e8f0;">{row['Odds']:.2f}</p>
                </div>
            </div>
            
            <div style="background-color: rgba(0,0,0,0.2); padding: 15px; border-radius: 12px; display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <p style="margin: 0; font-size: 12px; color: #a8dadc; text-transform: uppercase;">Συνολική Επιστροφή</p>
                    <p style="margin: 0; font-size: 24px; font-weight: 700; color: #ffffff;">{total_return:.2f} €</p>
                </div>
                <div style="text-align: right;">
                    <p style="margin: 0; font-size: 12px; color: #a8dadc; text-transform: uppercase;">Καθαρό Κέρδος</p>
                    <p style="margin: 0; font-size: 24px; font-weight: 700; color: {status_color};">{profit_str}</p>
                </div>
            </div>
        </div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

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
            st.session_state['auto_open_ticket'] = int(sel_aa)
            st.session_state['page_sel'] = "🗓️ Μηνιαία Αναφορά"
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
        disp_df = prog_dataframe[['Α/Α', 'Date', 'Event', 'Stake', 'Odds', 'Profit', 'Cumulative_Profit']].copy()
        disp_df.rename(columns={'Date': 'Ημ/νια', 'Event': 'Αγώνας', 'Stake': 'Ποντάρισμα', 'Odds': 'Απόδοση', 'Profit': 'Κέρδος/Ζημιά', 'Cumulative_Profit': 'Τρέχον Ταμείο'}, inplace=True)
        cfg = {
            "Τρέχον Ταμείο": st.column_config.NumberColumn("Τρέχον Ταμείο (€)", format="%.2f €"),
            "Κέρδος/Ζημιά": st.column_config.NumberColumn("Κέρδος/Ζημιά", format="%.2f €"),
            "Ποντάρισμα": st.column_config.NumberColumn("Ποντάρισμα", format="%.2f €"),
            "Ημ/νια": st.column_config.DateColumn("Ημ/νια", format="DD/MM/YYYY")
        }
    elif metric_type == "roi":
        st.markdown("<h3 style='color: #4db8ff; font-family: Poppins;'>📉 Εξέλιξη Yield (ROI)</h3>", unsafe_allow_html=True)
        disp_df = prog_dataframe[['Α/Α', 'Date', 'Event', 'Stake', 'Profit', 'Cumulative_ROI']].copy()
        disp_df.rename(columns={'Date': 'Ημ/νια', 'Event': 'Αγώνας', 'Stake': 'Ποντάρισμα', 'Profit': 'Κέρδος/Ζημιά', 'Cumulative_ROI': 'Τρέχον ROI'}, inplace=True)
        cfg = {
            "Τρέχον ROI": st.column_config.NumberColumn("Τρέχον ROI (%)", format="%.2f %%"),
            "Κέρδος/Ζημιά": st.column_config.NumberColumn("Κέρδος/Ζημιά", format="%.2f €"),
            "Ποντάρισμα": st.column_config.NumberColumn("Ποντάρισμα", format="%.2f €"),
            "Ημ/νια": st.column_config.DateColumn("Ημ/νια", format="DD/MM/YYYY")
        }
    elif metric_type == "wr":
        st.markdown("<h3 style='color: #4db8ff; font-family: Poppins;'>🎯 Εξέλιξη Win Rate</h3>", unsafe_allow_html=True)
        disp_df = prog_dataframe[prog_dataframe['Status'].isin(["🟢 Κερδισμένο", "🔴 Χαμένο"])].copy()
        disp_df = disp_df[['Α/Α', 'Date', 'Event', 'Status', 'Cumulative_WR']]
        disp_df.rename(columns={'Date': 'Ημ/νια', 'Event': 'Αγώνας', 'Status': 'Κατάσταση', 'Cumulative_WR': 'Τρέχον Win Rate'}, inplace=True)
        cfg = {
            "Τρέχον Win Rate": st.column_config.NumberColumn("Τρέχον Win Rate (%)", format="%.1f %%"),
            "Ημ/νια": st.column_config.DateColumn("Ημ/νια", format="DD/MM/YYYY")
        }
    elif metric_type == "avg_odds":
        st.markdown("<h3 style='color: #4db8ff; font-family: Poppins;'>⚖️ Εξέλιξη Μέσης Απόδοσης</h3>", unsafe_allow_html=True)
        disp_df = prog_dataframe[['Α/Α', 'Date', 'Event', 'Odds', 'Cumulative_AvgOdds']].copy()
        disp_df.rename(columns={'Date': 'Ημ/νια', 'Event': 'Αγώνας', 'Odds': 'Απόδοση Δελτίου', 'Cumulative_AvgOdds': 'Τρέχουσα Μέση Απόδοση'}, inplace=True)
        cfg = {
            "Τρέχουσα Μέση Απόδοση": st.column_config.NumberColumn("Τρέχουσα Μέση Απόδοση", format="%.2f"),
            "Απόδοση Δελτίου": st.column_config.NumberColumn("Απόδοση Δελτίου", format="%.2f"),
            "Ημ/νια": st.column_config.DateColumn("Ημ/νια", format="DD/MM/YYYY")
        }
        
    event = st.dataframe(disp_df, use_container_width=True, hide_index=True, column_config=cfg, on_select="rerun", selection_mode="single-row")
    
    if event.selection.rows:
        sel_idx = event.selection.rows[0]
        sel_aa = disp_df.iloc[sel_idx]['Α/Α']
        st.session_state['auto_open_ticket'] = int(sel_aa)
        st.session_state['page_sel'] = "🗓️ Μηνιαία Αναφορά"
        st.rerun()

@st.dialog("➕ Καταχώρηση Νέου Δελτίου", width="large")
def new_bet_dialog():
    reset_id = st.session_state['form_reset_counter']
    
    st.markdown("<br>", unsafe_allow_html=True)
    bet_type = st.radio("Τύπος Στοιχήματος", BET_TYPES, horizontal=True, key=f"bet_type_{reset_id}")
    num_legs = 2
    if bet_type != "Μονό":
        num_legs = st.number_input("Πόσα σημεία έχει το δελτίο;", min_value=2, max_value=15, value=2, key=f"legs_num_{reset_id}")
    
    st.markdown("<h5 style='color: #a8dadc; border-bottom: 1px solid #1e3a5f; padding-bottom: 5px; margin-top: 15px; font-family: Poppins;'>1. Βασικά Στοιχεία</h5>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    d = c1.date_input("Ημερομηνία", date.today(), format="DD/MM/YYYY", key=f"date_{reset_id}")
    t = c2.time_input("Ώρα", datetime.now().time(), step=60, key=f"time_{reset_id}")
    basket_index = list(SPORT_ICONS.values()).index("🏀 Μπάσκετ")
    selected_sport_input = c3.selectbox("Άθλημα", list(SPORT_ICONS.values()), index=basket_index, key=f"sport_{reset_id}")
    
    legs = []
    event_str, market_str = "", ""
    auto_odds = 1.0
    st.markdown("---")
    
    if bet_type == "Μονό":
        st.markdown("<h5 style='color: #a8dadc; border-bottom: 1px solid #1e3a5f; padding-bottom: 5px; margin-top: 15px; font-family: Poppins;'>2. Αγώνας & Αγορά</h5>", unsafe_allow_html=True)
        c_ev, c_ma = st.columns(2)
        event_key = f"ev_single_txt_{reset_id}"
        event_str = c_ev.text_input("Αγώνας:", key=event_key)
        render_suggestions(c_ev, event_key, event_str, get_event_suggestions, (all_events, all_teams))
        
        market_key = f"ma_single_txt_{reset_id}"
        market_str = c_ma.text_input("Αγορά:", key=market_key)
        render_suggestions(c_ma, market_key, market_str, get_market_suggestions, (all_markets,))
        
    elif bet_type == "Bet Builder":
        st.markdown("<h5 style='color: #a8dadc; border-bottom: 1px solid #1e3a5f; padding-bottom: 5px; margin-top: 15px; font-family: Poppins;'>2. Κοινός Αγώνας & Σημεία</h5>", unsafe_allow_html=True)
        c_ev, _ = st.columns(2)
        event_key = f"bb_ev_txt_{reset_id}"
        event_str = c_ev.text_input("Αγώνας (Για όλα τα σημεία):", key=event_key)
        render_suggestions(c_ev, event_key, event_str, get_event_suggestions, (all_events, all_teams))

        st.markdown("<br>", unsafe_allow_html=True)
        for i in range(int(num_legs)):
            cc2, cc3, cc4 = st.columns([3,1,2])
            l_ma_key = f"bb_ma_t_{i}_{reset_id}"
            l_ma = cc2.text_input(f"Σημείο {i+1}", key=l_ma_key)
            render_suggestions(cc2, l_ma_key, l_ma, get_market_suggestions, (all_markets,))
            l_od = cc3.number_input(f"Απόδοση {i+1}", min_value=1.00, step=0.01, value=1.50, key=f"bb_od_{i}_{reset_id}")
            l_st = cc4.selectbox(f"Κατάστ. {i+1}", STATUS_LIST, key=f"bb_st_{i}_{reset_id}")
            legs.append({"event": event_str, "market": l_ma, "odds": l_od, "status": l_st})
            if l_st == "🔵 Ακυρωμένο": auto_odds *= 1.0
            else: auto_odds *= l_od

    else: 
        st.markdown("<h5 style='color: #a8dadc; border-bottom: 1px solid #1e3a5f; padding-bottom: 5px; margin-top: 15px; font-family: Poppins;'>2. Ανάλυση Σημείων</h5>", unsafe_allow_html=True)
        for i in range(int(num_legs)):
            cc1, cc2, cc3, cc4 = st.columns([3,3,1,2])
            l_ev_key = f"ev_t_{i}_{reset_id}"
            l_ev = cc1.text_input(f"Αγώνας {i+1}", key=l_ev_key)
            render_suggestions(cc1, l_ev_key, l_ev, get_event_suggestions, (all_events, all_teams))
            l_ma_key = f"ma_t_{i}_{reset_id}"
            l_ma = cc2.text_input(f"Σημείο {i+1}", key=l_ma_key)
            render_suggestions(cc2, l_ma_key, l_ma, get_market_suggestions, (all_markets,))
            l_od = cc3.number_input(f"Απόδοση {i+1}", min_value=1.00, step=0.01, value=1.50, key=f"od_{i}_{reset_id}")
            l_st = cc4.selectbox(f"Κατάστ. {i+1}", STATUS_LIST, key=f"lst_{i}_{reset_id}")
            legs.append({"event": l_ev, "market": l_ma, "odds": l_od, "status": l_st})
            if l_st == "🔵 Ακυρωμένο": auto_odds *= 1.0
            else: auto_odds *= l_od
            
    st.markdown("<h5 style='color: #a8dadc; border-bottom: 1px solid #1e3a5f; padding-bottom: 5px; margin-top: 15px; font-family: Poppins;'>3. Αποδόσεις & Ποντάρισμα</h5>", unsafe_allow_html=True)
    c5, c6, c7, c8 = st.columns(4)
    
    if bet_type == "Μονό":
        odds = c5.number_input("Απόδοση", min_value=1.01, step=0.01, value=round(global_avg_odds, 2), key=f"odds_single_{reset_id}")
        chosen_preset = c6.selectbox("Ποντάρισμα (€)", STAKE_PRESETS, key=f"stake_preset_{reset_id}")
        custom_stake = c7.number_input("Ή γράψε δικό σου ποσό (€)", min_value=0.0, step=0.05, format="%.2f", key=f"custom_stake_{reset_id}")
        status = c8.selectbox("Κατάσταση (Συνολική)", STATUS_LIST, key=f"status_{reset_id}")
    else:
        odds = c5.number_input("Συνολική Απόδοση (Υπολογισμένη)", min_value=1.00, step=0.01, value=float(auto_odds), key=f"odds_multi_{reset_id}")
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
               'Date': d, 'Time': t_string, 'Type': bet_type, 'Sport': selected_sport_input, 
               'Event': event_str, 'Market': market_str, 'Odds': odds, 'Stake': stake, 
               'Status': status, 'Profit': profit, 'Legs_Data': legs_json
           }])
           df_to_save = pd.concat([df.drop(columns=['Α/Α'], errors='ignore'), new_data], ignore_index=True)
           save_data(df_to_save)
           st.session_state['show_toast'] = True
           st.session_state['toast_message'] = "Το δελτίο καταχωρήθηκε επιτυχώς!"
           st.session_state['form_reset_counter'] += 1 
           st.rerun()
        except Exception as e:
           st.error(f"❌ Υπήρξε πρόβλημα: {e}")

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
        
    status_mapping = {
        "Pending": "⚪ Εκκρεμές", "Won": "🟢 Κερδισμένο",
        "Lost": "🔴 Χαμένο", "Void": "🔵 Ακυρωμένο", "Cash Out": "🟡 Cash Out"
    }
    if df['Status'].isin(status_mapping.keys()).any():
        df['Status'] = df['Status'].replace(status_mapping)
        
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce').dt.date
    df['Time'] = pd.to_datetime(df['Time'].astype(str), errors='coerce').dt.time
    return df

df = load_data()
df = df.sort_values(by=["Date", "Time"]).reset_index(drop=True)
df.insert(0, 'Α/Α', range(1, len(df) + 1))

all_events_set = set()
all_markets_set = set()
for ev in df['Event'].dropna():
    if ev.strip() != '': all_events_set.add(ev)
for ma in df['Market'].dropna():
    if '|' not in ma and ma.strip() != '': all_markets_set.add(ma)

all_events = sorted(list(all_events_set))
all_markets = sorted(list(all_markets_set))

all_teams_set = set()
for ev in all_events:
    for delim in [' - ', ' vs ', '-']:
        if delim in ev:
            parts = ev.split(delim)
            if len(parts) == 2:
                all_teams_set.add(parts[0].strip())
                all_teams_set.add(parts[1].strip())
            break
    else:
        all_teams_set.add(ev)
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
# 🗂️ SIDEBAR REVAMP
# ==========================================
st.sidebar.markdown("<div class='sidebar-header'>🚀 ΠΛΟΗΓΗΣΗ</div>", unsafe_allow_html=True)

page = st.sidebar.radio(
    "",
    ["📊 Dashboard & Στατιστικά", "⚡ Ανοιχτά Δελτία (Εκκρεμή)", "🗓️ Μηνιαία Αναφορά", "⚙️ Διαχείριση Ιστορικού"],
    key="page_sel",
    label_visibility="collapsed"
)

st.sidebar.markdown("<div class='sidebar-header'>🛠️ ΕΞΥΠΝΑ ΦΙΛΤΡΑ</div>", unsafe_allow_html=True)

min_d = df['Date'].min() if not df.empty else date.today()
max_d = df['Date'].max() if not df.empty else date.today()
date_filter = st.sidebar.date_input("📅 Χρονικό Διάστημα", value=(min_d, max_d), format="DD/MM/YYYY")

search_event = st.sidebar.text_input("🔍 Λέξη-Κλειδί (Ομάδα/Αγώνας)")
sports_list = ["Όλα"] + sorted(df['Sport'].dropna().astype(str).unique().tolist())
selected_sport = st.sidebar.selectbox("🎯 Άθλημα", sports_list)
types_list = ["Όλοι οι Τύποι"] + sorted(df['Type'].dropna().astype(str).unique().tolist())
selected_type = st.sidebar.selectbox("🎫 Τύπος Συστήματος", types_list)

filtered_df = df.copy()
if len(date_filter) == 2:
    filtered_df = filtered_df[(filtered_df['Date'] >= date_filter[0]) & (filtered_df['Date'] <= date_filter[1])]
elif len(date_filter) == 1:
    filtered_df = filtered_df[filtered_df['Date'] >= date_filter[0]]
if search_event: filtered_df = filtered_df[filtered_df['Event'].str.contains(search_event, case=False, na=False)]
if selected_sport != "Όλα": filtered_df = filtered_df[filtered_df['Sport'] == selected_sport]
if selected_type != "Όλοι οι Τύποι": filtered_df = filtered_df[filtered_df['Type'] == selected_type]

# ==========================================
# MAIN APP BODY
# ==========================================
st.title("📈 Στοιχηματικό Dashboard")

# --- ΤΟ ΚΕΝΤΡΙΚΟ ΚΟΥΜΠΙ ΝΕΟΥ ΣΤΟΙΧΗΜΑΤΟΣ ---
st.markdown("<div id='bet-button-anchor' style='height: 1px;'></div>", unsafe_allow_html=True)
if st.button("➕ ΝΕΟ ΣΤΟΙΧΗΜΑ", type="primary", use_container_width=True):
    new_bet_dialog()

# 🧠 THE ULTIMATE FLOATING PILL HACK (DOM INJECTION WITH POLLING)
components.html(
    """
    <script>
    const pWin = window.parent;
    const pDoc = pWin.document;

    function initFAB() {
        if (!pDoc.getElementById('my-custom-fab')) {
            const fab = pDoc.createElement('button');
            fab.id = 'my-custom-fab';
            fab.innerHTML = '➕ ΝΕΟ ΣΤΟΙΧΗΜΑ';
            fab.style.cssText = `
                position: fixed; bottom: 30px; right: 30px; z-index: 999999;
                background: linear-gradient(135deg, #0284c7, #10b981);
                color: white; border: none; border-radius: 50px;
                padding: 15px 30px; font-size: 16px; font-weight: 700;
                font-family: 'Poppins', sans-serif;
                box-shadow: 0 10px 25px rgba(16, 185, 129, 0.4);
                cursor: pointer; opacity: 0; pointer-events: none;
                transform: translateY(20px); transition: all 0.3s ease;
            `;
            
            fab.onmouseover = () => { fab.style.transform = 'translateY(-5px) scale(1.05)'; };
            fab.onmouseout = () => { fab.style.transform = 'translateY(0) scale(1)'; };
            
            fab.onclick = () => {
                const buttons = Array.from(pDoc.querySelectorAll('button'));
                const topBtn = buttons.find(b => b.innerText.includes('ΝΕΟ ΣΤΟΙΧΗΜΑ') && b.id !== 'my-custom-fab');
                if(topBtn) {
                    topBtn.click();
                    pWin.scrollTo({top: 0, behavior: 'smooth'});
                }
            };
            
            pDoc.body.appendChild(fab);
        }

        const anchor = pDoc.getElementById('bet-button-anchor');
        const fab = pDoc.getElementById('my-custom-fab');
        
        if (anchor && fab) {
            const rect = anchor.getBoundingClientRect();
            // Αν το κουμπί βγει πάνω από την οθόνη, φέρε το FAB!
            if (rect.bottom < 50) {
                fab.style.opacity = '1';
                fab.style.pointerEvents = 'auto';
                fab.style.transform = 'translateY(0) scale(1)';
            } else {
                fab.style.opacity = '0';
                fab.style.pointerEvents = 'none';
                fab.style.transform = 'translateY(20px) scale(1)';
            }
        }
    }
    
    // Το τρέχουμε διαρκώς για να είναι αλεξίσφαιρο
    setInterval(initFAB, 500);
    </script>
    """,
    height=0
)

# ----------------- ΣΕΛΙΔΕΣ -----------------
if page == "📊 Dashboard & Στατιστικά":
    st.header("🏠 Στατιστικά & Αναλύσεις")
    if filtered_df.empty:
        st.warning("Δεν βρέθηκαν στοιχήματα για αυτά τα φίλτρα.")
    else:
        completed_bets = filtered_df[filtered_df['Status'].isin(["🟢 Κερδισμένο", "🔴 Χαμένο", "🟡 Cash Out", "🔵 Ακυρωμένο"])]
        
        total_profit = filtered_df['Profit'].sum()
        total_staked = completed_bets['Stake'].sum()
        yield_pct = (total_profit / total_staked * 100) if total_staked > 0 else 0
        
        wl_bets = completed_bets[completed_bets['Status'].isin(["🟢 Κερδισμένο", "🔴 Χαμένο"])]
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
        
        # --- ΥΠΟΛΟΓΙΣΜΟΣ ΕΞΕΛΙΞΗΣ (PROGRESSION DATA) ---
        completed_bets['DateTime'] = pd.to_datetime(completed_bets['Date'].astype(str) + ' ' + completed_bets['Time'].astype(str))
        prog_df = completed_bets.sort_values(by="DateTime")
        
        cum_profit = []
        cum_stake = []
        cum_roi = []
        cum_wr = []
        cum_avg = []
        
        current_p = 0.0
        current_s = 0.0
        current_wl_count = 0
        current_wins = 0
        cum_o_sum = 0.0
        cum_o_count = 0
        
        max_win_streak, max_lose_streak = 0, 0
        current_w, current_l = 0, 0
        win_streak_idx, lose_streak_idx = [], []
        curr_w_idx, curr_l_idx = [], []
        
        for idx, row in prog_df.iterrows():
            current_p += row['Profit']
            if row['Status'] != "🔵 Ακυρωμένο":
                current_s += row['Stake']
                cum_o_sum += row['Odds']
                cum_o_count += 1
            
            status = row['Status']
            if status in ["🟢 Κερδισμένο", "🔴 Χαμένο"]:
                current_wl_count += 1
                if status == "🟢 Κερδισμένο":
                    current_wins += 1
            
            c_roi = (current_p / current_s * 100) if current_s > 0 else 0.0
            c_wr = (current_wins / current_wl_count * 100) if current_wl_count > 0 else 0.0
            c_avg_odds = (cum_o_sum / cum_o_count) if cum_o_count > 0 else 0.0
            
            cum_profit.append(current_p)
            cum_stake.append(current_s)
            cum_roi.append(c_roi)
            cum_wr.append(c_wr)
            cum_avg.append(c_avg_odds)

            if status == "🟢 Κερδισμένο":
                current_w += 1
                curr_w_idx.append(row['Α/Α'])
                current_l = 0
                curr_l_idx = []
                if current_w > max_win_streak: 
                    max_win_streak = current_w
                    win_streak_idx = curr_w_idx.copy()
            elif status == "🔴 Χαμένο":
                current_l += 1
                curr_l_idx.append(row['Α/Α'])
                current_w = 0
                curr_w_idx = []
                if current_l > max_lose_streak: 
                    max_lose_streak = current_l
                    lose_streak_idx = curr_l_idx.copy()
            else: 
                current_w = 0; curr_w_idx = []
                current_l = 0; curr_l_idx = []

        prog_df['Cumulative_Profit'] = cum_profit
        prog_df['Cumulative_Stake'] = cum_stake
        prog_df['Cumulative_ROI'] = cum_roi
        prog_df['Cumulative_WR'] = cum_wr
        prog_df['Cumulative_AvgOdds'] = cum_avg
        prog_df = prog_df.sort_values(by="DateTime", ascending=False)

        max_win_odds = winning_bets['Odds'].max() if not winning_bets.empty else 0.0
        max_win_odds_aa = winning_bets.loc[winning_bets['Odds'].idxmax(), 'Α/Α'] if not winning_bets.empty else None

        count_won = len(filtered_df[filtered_df['Status'] == "🟢 Κερδισμένο"])
        count_lost = len(filtered_df[filtered_df['Status'] == "🔴 Χαμένο"])
        count_cashout = len(filtered_df[filtered_df['Status'] == "🟡 Cash Out"])
        count_void = len(filtered_df[filtered_df['Status'] == "🔵 Ακυρωμένο"])
        count_pending = len(filtered_df[filtered_df['Status'] == "⚪ Εκκρεμές"])

        # --- ΕΜΦΑΝΙΣΗ CLICKABLE ΣΤΑΤΙΣΤΙΚΩΝ ΚΑΡΤΩΝ ---
        st.markdown("### 🏆 Στατιστικά Ταμείου")
        col_a, col_b, col_c, col_d = st.columns(4)
        
        p_delta_str = ""
        if profit_delta is not None and not pd.isna(profit_delta) and profit_delta != 0:
            p_delta_str = f"\n( 🟢 +{profit_delta:.2f} € )" if profit_delta > 0 else f"\n( 🔴 {profit_delta:.2f} € )"
            st.markdown('<div class="marker-positive"></div>' if profit_delta > 0 else '<div class="marker-negative"></div>', unsafe_allow_html=True)
        if col_a.button(f"Συνολικό Κέρδος\n{total_profit:.2f} €{p_delta_str}", key="btn_prof", use_container_width=True):
            show_progression_dialog("profit", prog_df, df)

        r_delta_str = ""
        if roi_delta is not None and not pd.isna(roi_delta) and roi_delta != 0:
            r_delta_str = f"\n( 🟢 +{roi_delta:.2f} % )" if roi_delta > 0 else f"\n( 🔴 {roi_delta:.2f} % )"
            st.markdown('<div class="marker-positive"></div>' if roi_delta > 0 else '<div class="marker-negative"></div>', unsafe_allow_html=True)
        if col_b.button(f"Yield (ROI)\n{yield_pct:.2f} %{r_delta_str}", key="btn_roi", use_container_width=True):
            show_progression_dialog("roi", prog_df, df)

        w_delta_str = ""
        if win_rate_delta is not None and not pd.isna(win_rate_delta) and win_rate_delta != 0:
            w_delta_str = f"\n( 🟢 +{win_rate_delta:.1f} % )" if win_rate_delta > 0 else f"\n( 🔴 {win_rate_delta:.1f} % )"
            st.markdown('<div class="marker-positive"></div>' if win_rate_delta > 0 else '<div class="marker-negative"></div>', unsafe_allow_html=True)
        if col_c.button(f"Win Rate\n{win_rate:.1f} %{w_delta_str}", key="btn_wr", use_container_width=True):
            show_progression_dialog("wr", prog_df, df)
        
        st.markdown('<div class="marker-neutral"></div>', unsafe_allow_html=True)
        if col_d.button(f"Σύνολο Στοιχημάτων\n{total_bets}", key="btn_all", use_container_width=True):
            show_bets_dialog("📋 Όλα τα Διευθετημένα Δελτία", completed_bets, df)

        col_e, col_f, col_g, col_h = st.columns(4)
        
        st.markdown('<div class="marker-positive"></div>', unsafe_allow_html=True)
        if col_e.button(f"Μέγιστο Σερί Νικών\n{max_win_streak} 🟢", key="btn_w_streak", use_container_width=True): 
            show_bets_dialog(f"🟢 Μέγιστο Σερί Νικών ({max_win_streak} δελτία)", df[df['Α/Α'].isin(win_streak_idx)], df)
        
        st.markdown('<div class="marker-negative"></div>', unsafe_allow_html=True)
        if col_f.button(f"Μέγιστο Σερί Ηττών\n{max_lose_streak} 🔴", key="btn_l_streak", use_container_width=True): 
            show_bets_dialog(f"🔴 Μέγιστο Σερί Ηττών ({max_lose_streak} δελτία)", df[df['Α/Α'].isin(lose_streak_idx)], df)
        
        o_delta_str = ""
        if odds_delta is not None and not pd.isna(odds_delta) and odds_delta != 0:
            o_delta_str = f"\n( 🟢 +{odds_delta:.2f} )" if odds_delta > 0 else f"\n( 🔴 {odds_delta:.2f} )"
            st.markdown('<div class="marker-positive"></div>' if odds_delta > 0 else '<div class="marker-negative"></div>', unsafe_allow_html=True)
        if col_g.button(f"Μέση Απόδοση\n{avg_odds:.2f}{o_delta_str}", key="btn_avg_odds", use_container_width=True):
            show_progression_dialog("avg_odds", prog_df, df)
        
        st.markdown('<div class="marker-positive"></div>', unsafe_allow_html=True)
        if col_h.button(f"Μέγιστη Απόδοση\n{max_win_odds:.2f} 🏆", key="btn_max_odds", use_container_width=True): 
            show_bets_dialog(f"🏆 Δελτίο με Μέγιστη Κερδισμένη Απόδοση ({max_win_odds})", df[df['Α/Α'] == max_win_odds_aa], df)
        
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("### 📊 Ανάλυση Αποτελεσμάτων")
        c_w, c_l, c_c, c_v, c_p = st.columns(5)
        
        st.markdown('<div class="marker-positive"></div>', unsafe_allow_html=True)
        if c_w.button(f"🟢 Κερδισμένα\n{count_won}", key="btn_won", use_container_width=True): 
            show_bets_dialog("🟢 Όλα τα Κερδισμένα", filtered_df[filtered_df['Status'] == "🟢 Κερδισμένο"], df)
        
        st.markdown('<div class="marker-negative"></div>', unsafe_allow_html=True)
        if c_l.button(f"🔴 Χαμένα\n{count_lost}", key="btn_lost", use_container_width=True): 
            show_bets_dialog("🔴 Όλα τα Χαμένα", filtered_df[filtered_df['Status'] == "🔴 Χαμένο"], df)
        
        st.markdown('<div class="marker-warning"></div>', unsafe_allow_html=True)
        if c_c.button(f"🟡 Cash Out\n{count_cashout}", key="btn_co", use_container_width=True): 
            show_bets_dialog("🟡 Όλα τα Cash Out", filtered_df[filtered_df['Status'] == "🟡 Cash Out"], df)
        
        st.markdown('<div class="marker-info"></div>', unsafe_allow_html=True)
        if c_v.button(f"🔵 Ακυρωμένα\n{count_void}", key="btn_void", use_container_width=True): 
            show_bets_dialog("🔵 Όλα τα Ακυρωμένα", filtered_df[filtered_df['Status'] == "🔵 Ακυρωμένο"], df)
        
        st.markdown('<div class="marker-neutral"></div>', unsafe_allow_html=True)
        if c_p.button(f"⚪ Εκκρεμή\n{count_pending}", key="btn_pending", use_container_width=True): 
            show_bets_dialog("⚪ Όλα τα Εκκρεμή", filtered_df[filtered_df['Status'] == "⚪ Εκκρεμές"], df)

        st.markdown("---")
        col_chart1, col_chart2 = st.columns(2)
        
        with col_chart1:
            st.markdown("### 📉 Εξέλιξη Κέρδους")
            if not completed_bets.empty:
                df_line = prog_df.sort_values(by="DateTime").copy()
                df_line['Ημ/νια'] = pd.to_datetime(df_line['Date']).dt.strftime('%d/%m/%Y')
                df_line['Bet_Count'] = range(1, len(df_line) + 1)
                
                zero_point = pd.DataFrame([{'Bet_Count': 0, 'Cumulative_Profit': 0.0, 'Ημ/νια': '-', 'Event': 'Αρχικό Κεφάλαιο (Μηδέν)', 'Profit': 0.0}])
                df_line = pd.concat([zero_point, df_line], ignore_index=True)
                
                base = alt.Chart(df_line).encode(
                    x=alt.X('Bet_Count:Q', axis=alt.Axis(labels=False, title=None, ticks=False, grid=False)),
                    y=alt.Y('Cumulative_Profit:Q', title="Ταμείο (€)", axis=alt.Axis(gridColor="#1f2937"))
                )
                
                line = base.mark_trail(interpolate='monotone').encode(
                    color=alt.condition(alt.datum.Cumulative_Profit >= 0, alt.value('#4ade80'), alt.value('#ff4b4b')),
                    size=alt.value(3)
                )
                
                points = base.mark_circle(size=60).encode(
                    color=alt.condition(alt.datum.Cumulative_Profit >= 0, alt.value('#4ade80'), alt.value('#ff4b4b'))
                )
                
                hover_points = base.mark_circle(size=500, color="transparent").encode(
                    tooltip=[alt.Tooltip('Ημ/νια:N', title='Ημερομηνία'), alt.Tooltip('Cumulative_Profit:Q', title='Κέρδος (€)', format='.2f')]
                )
                
                chart = (line + points + hover_points).properties(height=350)
                st.altair_chart(chart, use_container_width=True, theme="streamlit")
            else:
                st.info("Δεν υπάρχουν ολοκληρωμένα δελτία στο επιλεγμένο εύρος ημερομηνιών για να εμφανιστεί γράφημα.")
                
        with col_chart2:
            st.markdown("### 🗓️ Ταμείο ανά Μήνα")
            monthly_df = completed_bets.copy()
            if not monthly_df.empty:
                monthly_df['MonthStr'] = pd.to_datetime(monthly_df['Date']).apply(lambda x: f"{GREEK_MONTHS[x.month]} {x.year}")
                monthly_df['Month_Sort'] = pd.to_datetime(monthly_df['Date']).dt.strftime('%Y-%m')
                
                monthly_group = monthly_df.groupby(['Month_Sort', 'MonthStr'])['Profit'].sum().reset_index()
                monthly_group = monthly_group.sort_values('Month_Sort')
                monthly_group['Color'] = monthly_group['Profit'].apply(lambda x: '🟢 Κέρδος' if x >= 0 else '🔴 Ζημιά')
                
                bar_chart = alt.Chart(monthly_group).mark_bar(cornerRadiusTopLeft=5, cornerRadiusTopRight=5).encode(
                    x=alt.X('MonthStr:N', sort=alt.EncodingSortField(field='Month_Sort', order='ascending'), title=None, axis=alt.Axis(labelAngle=0, labelColor="#e2e8f0")),
                    y=alt.Y('Profit:Q', title="Καθαρό Κέρδος (€)", axis=alt.Axis(gridColor="#1f2937")),
                    color=alt.Color('Color:N', scale=alt.Scale(domain=['🟢 Κέρδος', '🔴 Ζημιά'], range=['#4ade80', '#ff4b4b']), legend=None),
                    tooltip=[alt.Tooltip('MonthStr:N', title='Μήνας'), alt.Tooltip('Profit:Q', title='Ταμείο Μήνα', format='.2f')]
                ).properties(height=350)
                st.altair_chart(bar_chart, use_container_width=True, theme="streamlit")
            else:
                st.info("Δεν υπάρχουν δεδομένα.")

elif page == "⚡ Ανοιχτά Δελτία (Εκκρεμή)":
    st.header("⏳ Εκκρεμή Στοιχήματα")
    st.info("💡 Άλλαξε την 'Κατάσταση' και πάτα Αποθήκευση για να τα διευθετήσεις.")
    
    pending_df = filtered_df[filtered_df['Status'] == "⚪ Εκκρεμές"].copy()
    
    if pending_df.empty:
        st.success("Όλα τα δελτία σου είναι διευθετημένα! Δεν χρωστάς τίποτα.")
    else:
        edit_pending_df = pending_df.drop(columns=['Legs_Data'])[DISPLAY_ORDER].sort_values(by="Α/Α", ascending=False)
        edited_pending = st.data_editor(edit_pending_df, use_container_width=True, hide_index=True, column_config=GREEK_COLUMNS)
        
        if st.button("💾 Αποθήκευση Εκκρεμών", type="primary"):
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
            
            save_df = df.drop(columns=['Α/Α'], errors='ignore')
            save_df['Time'] = pd.to_datetime(save_df['Time'].astype(str), errors='coerce').dt.strftime('%H:%M').fillna('00:00')
            save_data(save_df)
            st.session_state['show_toast'] = True
            st.session_state['toast_message'] = "Τα στοιχήματα διευθετήθηκαν!"
            st.rerun()

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
                        show_ticket_modal(sel_aa, df)
            
            st.markdown("<br>", unsafe_allow_html=True)

elif page == "⚙️ Διαχείριση Ιστορικού":
    st.header("✏️ Επεξεργασία & Διαγραφή")
    
    st.markdown("### 📝 Πλήρης Επεξεργασία (Μορφή Φόρμας)")
    st.info("💡 Επίλεξε ένα δελτίο. Θα ανοίξει η ίδια ακριβώς καρτέλα με την οποία το καταχώρησες, για να αλλάξεις εύκολα ό,τι θες!")
    
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
                    edit_num_legs = st.number_input("Πόσα σημεία έχει το δελτίο;", min_value=2, max_value=15, value=int(edit_num_legs), key=f"ed_legs_num_{selected_aa}")
                    
                st.markdown("<h5 style='color: #a8dadc; border-bottom: 1px solid #1e3a5f; padding-bottom: 5px; margin-top: 15px;'>1. Βασικά Στοιχεία</h5>", unsafe_allow_html=True)
                c1, c2, c3 = st.columns(3)
                ed_d = c1.date_input("Ημερομηνία", e_date, format="DD/MM/YYYY", key=f"ed_date_{selected_aa}")
                ed_t = c2.time_input("Ώρα", e_time, step=60, key=f"ed_time_{selected_aa}")
                
                sport_idx = list(SPORT_ICONS.values()).index(e_sport) if e_sport in SPORT_ICONS.values() else list(SPORT_ICONS.values()).index("🏀 Μπάσκετ")
                ed_sport = c3.selectbox("Άθλημα", list(SPORT_ICONS.values()), index=sport_idx, key=f"ed_sport_{selected_aa}")
                
                new_legs = []
                final_ev_str, final_ma_str = "", ""
                auto_odds = 1.0
                st.markdown("---")
                
                if edit_bet_type == "Μονό":
                    st.markdown("<h5 style='color: #a8dadc; border-bottom: 1px solid #1e3a5f; padding-bottom: 5px; margin-top: 15px;'>2. Αγώνας & Αγορά (Επεξεργασία)</h5>", unsafe_allow_html=True)
                    c_ev, c_ma = st.columns(2)
                    
                    ed_ev_key = f"ed_ev_txt_{selected_aa}"
                    final_ev_str = c_ev.text_input("Αγώνας:", value=e_event, key=ed_ev_key)
                    render_suggestions(c_ev, ed_ev_key, final_ev_str, get_event_suggestions, (all_events, all_teams))
                        
                    ed_ma_key = f"ed_ma_txt_{selected_aa}"
                    final_ma_str = c_ma.text_input("Αγορά:", value=e_market, key=ed_ma_key)
                    render_suggestions(c_ma, ed_ma_key, final_ma_str, get_market_suggestions, (all_markets,))
                        
                elif edit_bet_type == "Bet Builder":
                    st.markdown("<h5 style='color: #a8dadc; border-bottom: 1px solid #1e3a5f; padding-bottom: 5px; margin-top: 15px;'>2. Κοινός Αγώνας & Σημεία</h5>", unsafe_allow_html=True)
                    c_ev, _ = st.columns(2)
                    bb_ev = e_legs[0]['event'] if e_legs and 'event' in e_legs[0] else e_event
                    bb_ev_clean = bb_ev.split(" (")[0] if " (" in bb_ev else bb_ev
                    
                    ed_ev_key = f"ed_bb_ev_t_{selected_aa}"
                    final_ev_str = c_ev.text_input("Αγώνας:", value=bb_ev_clean, key=ed_ev_key)
                    render_suggestions(c_ev, ed_ev_key, final_ev_str, get_event_suggestions, (all_events, all_teams))

                    st.markdown("<br>", unsafe_allow_html=True)
                    for i in range(int(edit_num_legs)):
                        cc2, cc3, cc4 = st.columns([3,1,2]) 
                        leg_ma = e_legs[i]['market'] if i < len(e_legs) else ""
                        leg_od = float(e_legs[i]['odds']) if i < len(e_legs) else 1.50
                        leg_st = e_legs[i]['status'] if i < len(e_legs) and 'status' in e_legs[i] else "⚪ Εκκρεμές"
                        
                        ed_lma_key = f"ed_bb_lma_t_{i}_{selected_aa}"
                        l_ma_final = cc2.text_input(f"Σημείο {i+1}", value=leg_ma, key=ed_lma_key)
                        render_suggestions(cc2, ed_lma_key, l_ma_final, get_market_suggestions, (all_markets,))
                            
                        l_od_final = cc3.number_input(f"Απόδοση {i+1}", min_value=1.00, step=0.01, value=leg_od, key=f"ed_bb_lod_{i}_{selected_aa}")
                        st_idx = STATUS_LIST.index(leg_st) if leg_st in STATUS_LIST else 0
                        l_st_final = cc4.selectbox(f"Κατάστ. {i+1}", STATUS_LIST, index=st_idx, key=f"ed_bb_lst_{i}_{selected_aa}")

                        new_legs.append({"event": final_ev_str, "market": l_ma_final, "odds": l_od_final, "status": l_st_final})
                        if l_st_final == "🔵 Ακυρωμένο": auto_odds *= 1.0
                        else: auto_odds *= l_od_final
                        
                else: # Παρολί
                    st.markdown("<h5 style='color: #a8dadc; border-bottom: 1px solid #1e3a5f; padding-bottom: 5px; margin-top: 15px;'>2. Ανάλυση Σημείων</h5>", unsafe_allow_html=True)
                    for i in range(int(edit_num_legs)):
                        cc1, cc2, cc3, cc4 = st.columns([3,3,1,2]) 
                        leg_ev = e_legs[i]['event'] if i < len(e_legs) else ""
                        leg_ma = e_legs[i]['market'] if i < len(e_legs) else ""
                        leg_od = float(e_legs[i]['odds']) if i < len(e_legs) else 1.50
                        leg_st = e_legs[i]['status'] if i < len(e_legs) and 'status' in e_legs[i] else "⚪ Εκκρεμές"
                        
                        ed_lev_key = f"ed_lev_t_{i}_{selected_aa}"
                        l_ev_final = cc1.text_input(f"Αγώνας {i+1}", value=leg_ev, key=ed_lev_key)
                        render_suggestions(cc1, ed_lev_key, l_ev_final, get_event_suggestions, (all_events, all_teams))
                            
                        ed_lma_key = f"ed_lma_t_{i}_{selected_aa}"
                        l_ma_final = cc2.text_input(f"Σημείο {i+1}", value=leg_ma, key=ed_lma_key)
                        render_suggestions(cc2, ed_lma_key, l_ma_final, get_market_suggestions, (all_markets,))
                            
                        l_od_final = cc3.number_input(f"Απόδοση {i+1}", min_value=1.00, step=0.01, value=leg_od, key=f"ed_lod_{i}_{selected_aa}")
                        st_idx = STATUS_LIST.index(leg_st) if leg_st in STATUS_LIST else 0
                        l_st_final = cc4.selectbox(f"Κατάστ. {i+1}", STATUS_LIST, index=st_idx, key=f"ed_lst_{i}_{selected_aa}")

                        new_legs.append({"event": l_ev_final, "market": l_ma_final, "odds": l_od_final, "status": l_st_final})
                        if l_st_final == "🔵 Ακυρωμένο": auto_odds *= 1.0
                        else: auto_odds *= l_od_final
                        
                st.markdown("---")
                st.markdown("<h5 style='color: #a8dadc; border-bottom: 1px solid #1e3a5f; padding-bottom: 5px; margin-top: 15px;'>3. Αποδόσεις & Ποντάρισμα</h5>", unsafe_allow_html=True)
                c5, c6, c7, c8 = st.columns(4)
                
                if edit_bet_type == "Μονό":
                    ed_odds = c5.number_input("Απόδοση", min_value=1.01, step=0.01, value=e_odds, key=f"ed_odds_{selected_aa}")
                    
                    preset_idx = len(STAKE_PRESETS) - 1
                    for idx_p, p_val in enumerate(STAKE_PRESETS):
                        if isinstance(p_val, float) and abs(p_val - e_stake) < 0.001:
                            preset_idx = idx_p; break
                    
                    ed_preset = c6.selectbox("Ποντάρισμα (€)", STAKE_PRESETS, index=preset_idx, key=f"ed_stake_p_{selected_aa}")
                    ed_custom = c7.number_input("Ή γράψε δικό σου ποσό (€)", min_value=0.0, step=0.05, value=e_stake if preset_idx == len(STAKE_PRESETS)-1 else 0.0, format="%.2f", key=f"ed_stake_c_{selected_aa}")
                    
                    status_idx = STATUS_LIST.index(e_status) if e_status in STATUS_LIST else 0
                    ed_status = c8.selectbox("Κατάσταση (Συνολική)", STATUS_LIST, index=status_idx, key=f"ed_status_{selected_aa}")
                else:
                    ed_odds = c5.number_input("Συνολική Απόδοση (Υπολογισμένη)", min_value=1.00, step=0.01, value=float(auto_odds), key=f"ed_odds_{selected_aa}")
                    
                    preset_idx = len(STAKE_PRESETS) - 1
                    for idx_p, p_val in enumerate(STAKE_PRESETS):
                        if isinstance(p_val, float) and abs(p_val - e_stake) < 0.001:
                            preset_idx = idx_p; break
                    
                    ed_preset = c6.selectbox("Ποντάρισμα (€)", STAKE_PRESETS, index=preset_idx, key=f"ed_stake_p_{selected_aa}")
                    ed_custom = c7.number_input("Ή γράψε δικό σου ποσό (€)", min_value=0.0, step=0.05, value=e_stake if preset_idx == len(STAKE_PRESETS)-1 else 0.0, format="%.2f", key=f"ed_stake_c_{selected_aa}")
                    
                    # Δυναμική Κατάσταση
                    status_options = ["Αυτόματος Υπολογισμός ⚙️", "🟡 Cash Out"]
                    s_idx = 1 if e_status == "🟡 Cash Out" else 0
                    status_sel = c8.selectbox("Κατάσταση (Συνολική)", status_options, index=s_idx, key=f"ed_status_{selected_aa}")
                    if status_sel == "Αυτόματος Υπολογισμός ⚙️":
                        ed_status = calc_overall_status(new_legs)
                    else:
                        ed_status = "🟡 Cash Out"
                
                ed_co_val = 0.0
                if ed_status == "🟡 Cash Out":
                    existing_co = e_stake + e_profit if e_status == "🟡 Cash Out" else 0.0
                    ed_co_val = st.number_input("Επιστροφή Cash Out (€)", min_value=0.0, step=0.01, value=existing_co, format="%.2f", key=f"ed_co_{selected_aa}")
                
                st.markdown("<br>", unsafe_allow_html=True)
                delete_check = st.checkbox("🗑️ Οριστική διαγραφή αυτού του δελτίου", key=f"del_check_{selected_aa}")
                
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
                        st.rerun()

    st.markdown("---")
    with st.expander("⚡ Γρήγορη Επεξεργασία Πίνακα (Μαζικές αλλαγές)"):
        edit_df = filtered_df.copy()
        if 'Legs_Data' in edit_df.columns:
            edit_df = edit_df.drop(columns=['Legs_Data']) 
            
        if not edit_df.empty:
            edit_df = edit_df[DISPLAY_ORDER].sort_values(by="Α/Α", ascending=False)
            
            edited_df = st.data_editor(
                edit_df, 
                num_rows="dynamic", 
                use_container_width=True,
                hide_index=True,
                column_config=GREEK_COLUMNS
            )
            
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