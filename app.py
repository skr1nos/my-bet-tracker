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

custom_css = """
<style>
.stApp { background-color: #0b172a; }
[data-testid="stSidebar"] { background-color: #060d1a; }
h1, h2, h3, p, label, .stMarkdown { color: #e2e8f0 !important; }
[data-testid="stMetric"] { background-color: #16263b; border-radius: 10px; padding: 15px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3); }
[data-testid="stMetricLabel"] { color: #a8dadc !important; }
[data-testid="stMetricValue"] { color: #ffffff !important; }
/* Κρύβει το ανθρωπάκι φόρτωσης του Streamlit */
[data-testid="stStatusWidget"] { display: none !important; }
</style>
"""
st.markdown(custom_css, unsafe_allow_html=True)

if 'form_reset_counter' not in st.session_state: st.session_state['form_reset_counter'] = 0
if 'show_toast' not in st.session_state: st.session_state['show_toast'] = False
if 'toast_message' not in st.session_state: st.session_state['toast_message'] = ""
if 'show_new_bet_modal' not in st.session_state: st.session_state['show_new_bet_modal'] = False
if 'active_view' not in st.session_state: st.session_state['active_view'] = None

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
            if prefix_ratio < 0.65:
                continue 
            
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

st.sidebar.title("🗂️ Μενού Εφαρμογής")
if st.sidebar.button("➕ Νέο Στοίχημα", type="primary", use_container_width=True):
    st.session_state['show_new_bet_modal'] = not st.session_state['show_new_bet_modal']

page = st.sidebar.radio("Επίλεξε Σελίδα:", ["🏠 Αρχική & Στατιστικά", "⏳ Εκκρεμή", "📋 Ιστορικό ανά Μήνα", "✏️ Επεξεργασία & Διαγραφή"])
st.sidebar.markdown("---")
st.sidebar.markdown("### 🔍 Γενικά Φίλτρα")

min_d = df['Date'].min() if not df.empty else date.today()
max_d = df['Date'].max() if not df.empty else date.today()
date_filter = st.sidebar.date_input("📅 Εύρος Ημερομηνιών", value=(min_d, max_d), format="DD/MM/YYYY")

search_event = st.sidebar.text_input("🔍 Αναζήτηση Αγώνα / Ομάδας")
sports_list = ["Όλα"] + sorted(df['Sport'].dropna().astype(str).unique().tolist())
selected_sport = st.sidebar.selectbox("Επιλογή Αθλήματος", sports_list)
types_list = ["Όλοι οι Τύποι"] + sorted(df['Type'].dropna().astype(str).unique().tolist())
selected_type = st.sidebar.selectbox("Επιλογή Τύπου Δελτίου", types_list)

filtered_df = df.copy()
if len(date_filter) == 2:
    filtered_df = filtered_df[(filtered_df['Date'] >= date_filter[0]) & (filtered_df['Date'] <= date_filter[1])]
elif len(date_filter) == 1:
    filtered_df = filtered_df[filtered_df['Date'] >= date_filter[0]]
if search_event: filtered_df = filtered_df[filtered_df['Event'].str.contains(search_event, case=False, na=False)]
if selected_sport != "Όλα": filtered_df = filtered_df[filtered_df['Sport'] == selected_sport]
if selected_type != "Όλοι οι Τύποι": filtered_df = filtered_df[filtered_df['Type'] == selected_type]

st.title("📈 Στοιχηματικό Dashboard")

if st.session_state['show_new_bet_modal']:
    with st.container(border=True):
        col_t, col_btn = st.columns([0.9, 0.1])
        col_t.markdown("### ➕ Καταχώρηση Νέου Δελτίου")
        if col_btn.button("❌", help="Κλείσιμο"):
            st.session_state['show_new_bet_modal'] = False
            st.rerun()
            
        reset_id = st.session_state['form_reset_counter']
        
        bet_type = st.radio("Τύπος Στοιχήματος", BET_TYPES, horizontal=True, key=f"bet_type_{reset_id}")
        num_legs = 2
        if bet_type != "Μονό":
            num_legs = st.number_input("Πόσα σημεία έχει το δελτίο;", min_value=2, max_value=15, value=2, key=f"legs_num_{reset_id}")
        
        st.markdown("🔹 **Βασικά Στοιχεία**")
        c1, c2, c3 = st.columns(3)
        d = c1.date_input("Ημερομηνία (ΗΗ/ΜΜ/ΕΕΕΕ)", date.today(), format="DD/MM/YYYY", key=f"date_{reset_id}")
        t = c2.time_input("Ώρα", datetime.now().time(), step=60, key=f"time_{reset_id}")
        basket_index = list(SPORT_ICONS.values()).index("🏀 Μπάσκετ")
        selected_sport_input = c3.selectbox("Άθλημα", list(SPORT_ICONS.values()), index=basket_index, key=f"sport_{reset_id}")
        
        legs = []
        event_str, market_str = "", ""
        auto_odds = 1.0
        st.markdown("---")
        
        if bet_type == "Μονό":
            st.markdown("🔹 **Αγώνας & Αγορά**")
            c_ev, c_ma = st.columns(2)
            
            event_key = f"ev_single_txt_{reset_id}"
            event_str = c_ev.text_input("Αγώνας:", key=event_key)
            render_suggestions(c_ev, event_key, event_str, get_event_suggestions, (all_events, all_teams))
            
            market_key = f"ma_single_txt_{reset_id}"
            market_str = c_ma.text_input("Αγορά:", key=market_key)
            render_suggestions(c_ma, market_key, market_str, get_market_suggestions, (all_markets,))
            
        elif bet_type == "Bet Builder":
            st.markdown("🔹 **Κοινός Αγώνας (Bet Builder)**")
            c_ev, _ = st.columns(2)
            
            event_key = f"bb_ev_txt_{reset_id}"
            event_str = c_ev.text_input("Αγώνας:", key=event_key)
            render_suggestions(c_ev, event_key, event_str, get_event_suggestions, (all_events, all_teams))

            st.markdown("🔹 **Σημεία Bet Builder**")
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

        else: # Παρολί
            st.markdown(f"🔹 **Ανάλυση Σημείων ({bet_type})**")
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
                
        st.markdown("---")
        st.markdown("🔹 **Αποδόσεις & Ποντάρισμα**")
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
        
        if st.button("💾 Αποθήκευση Δελτίου", type="primary", key=f"save_btn_{reset_id}"):
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
               st.session_state['show_new_bet_modal'] = False 
            except Exception as e:
               st.error(f"❌ Υπήρξε πρόβλημα: {e}")
            st.rerun()

else:
    if page == "🏠 Αρχική & Στατιστικά":
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
            winning_bets = filtered_df[filtered_df['Status'] == "🟢 Κερδισμένο"]
            
            # --- ΥΠΟΛΟΓΙΣΜΟΙ ΓΙΑ ΤΑ ΣΕΡΙ (Κρατάμε τα Α/Α) ---
            completed_bets['DateTime'] = pd.to_datetime(completed_bets['Date'].astype(str) + ' ' + completed_bets['Time'].astype(str))
            sorted_for_streaks = completed_bets.sort_values(by="DateTime")
            
            max_win_streak, max_lose_streak = 0, 0
            current_w, current_l = 0, 0
            win_streak_idx, lose_streak_idx = [], []
            curr_w_idx, curr_l_idx = [], []
            
            for idx, row in sorted_for_streaks.iterrows():
                status = row['Status']
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

            max_win_odds = winning_bets['Odds'].max() if not winning_bets.empty else 0.0
            max_win_odds_aa = winning_bets.loc[winning_bets['Odds'].idxmax(), 'Α/Α'] if not winning_bets.empty else None

            count_won = len(filtered_df[filtered_df['Status'] == "🟢 Κερδισμένο"])
            count_lost = len(filtered_df[filtered_df['Status'] == "🔴 Χαμένο"])
            count_cashout = len(filtered_df[filtered_df['Status'] == "🟡 Cash Out"])
            count_void = len(filtered_df[filtered_df['Status'] == "🔵 Ακυρωμένο"])
            count_pending = len(filtered_df[filtered_df['Status'] == "⚪ Εκκρεμές"])

            # --- ΕΜΦΑΝΙΣΗ ΣΤΑΤΙΣΤΙΚΩΝ ΚΑΙ ΚΟΥΜΠΙΩΝ (INTERACTIVE VIEW) ---
            st.markdown("### 🏆 Στατιστικά Ταμείου")
            col_a, col_b, col_c, col_d = st.columns(4)
            prof_color = "#4ade80" if total_profit > 0 else "#ff4b4b" if total_profit < 0 else "#ffffff"

            col_a.markdown(f"""
            <div style="background-color: #16263b; border-radius: 10px; padding: 15px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);">
                <div style="color: #a8dadc; font-size: 14px; margin-bottom: 0.3rem;">Συνολικό Κέρδος</div>
                <div style="color: {prof_color}; font-size: 1.8rem; font-weight: normal;">{total_profit:.2f} €</div>
            </div>""", unsafe_allow_html=True)

            col_b.markdown(f"""
            <div style="background-color: #16263b; border-radius: 10px; padding: 15px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);">
                <div style="color: #a8dadc; font-size: 14px; margin-bottom: 0.3rem;">Yield (ROI)</div>
                <div style="color: {prof_color}; font-size: 1.8rem; font-weight: normal;">{yield_pct:.2f} %</div>
            </div>""", unsafe_allow_html=True)

            col_c.metric("Win Rate", f"{win_rate:.1f} %")
            col_d.metric("Σύνολο Στοιχημάτων", f"{total_bets}")
            if col_d.button("🔍 Προβολή Όλων", use_container_width=True, key="btn_all"): st.session_state['active_view'] = 'all'

            col_e, col_f, col_g, col_h = st.columns(4)
            col_e.metric("Μέγιστο Σερί Νικών", f"{max_win_streak} 🟢")
            if col_e.button("🔍 Προβολή Σερί", use_container_width=True, key="btn_w_streak"): st.session_state['active_view'] = 'w_streak'
            
            col_f.metric("Μέγιστο Σερί Ηττών", f"{max_lose_streak} 🔴")
            if col_f.button("🔍 Προβολή Σερί", use_container_width=True, key="btn_l_streak"): st.session_state['active_view'] = 'l_streak'
            
            col_g.metric("Μέση Απόδοση", f"{avg_odds:.2f}")
            
            col_h.metric("Μέγιστη Κερδισμένη Απόδοση", f"{max_win_odds:.2f}")
            if col_h.button("🔍 Προβολή Δελτίου", use_container_width=True, key="btn_max_odds"): st.session_state['active_view'] = 'max_odds'
            
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown("### 📊 Ανάλυση Αποτελεσμάτων")
            c_w, c_l, c_c, c_v, c_p = st.columns(5)
            c_w.metric("🟢 Κερδισμένα", f"{count_won}")
            if c_w.button("🔍 Προβολή", use_container_width=True, key="btn_won"): st.session_state['active_view'] = 'won'
            
            c_l.metric("🔴 Χαμένα", f"{count_lost}")
            if c_l.button("🔍 Προβολή", use_container_width=True, key="btn_lost"): st.session_state['active_view'] = 'lost'
            
            c_c.metric("🟡 Cash Out", f"{count_cashout}")
            if c_c.button("🔍 Προβολή", use_container_width=True, key="btn_co"): st.session_state['active_view'] = 'cashout'
            
            c_v.metric("🔵 Ακυρωμένα", f"{count_void}")
            if c_v.button("🔍 Προβολή", use_container_width=True, key="btn_void"): st.session_state['active_view'] = 'void'
            
            c_p.metric("⚪ Εκκρεμή", f"{count_pending}")
            if c_p.button("🔍 Προβολή", use_container_width=True, key="btn_pending"): st.session_state['active_view'] = 'pending'

            # --- ΠΡΟΒΟΛΗ ΖΩΝΤΑΝΟΥ ΠΙΝΑΚΑ ΟΤΑΝ ΠΑΤΑΕΙ ΤΑ ΚΟΥΜΠΙΑ ---
            view = st.session_state.get('active_view', None)
            if view:
                st.markdown("---")
                col_title, col_close = st.columns([0.85, 0.15])
                view_df = pd.DataFrame()
                title_str = ""
                
                if view == 'all':
                    view_df = completed_bets
                    title_str = "📋 Όλα τα Διευθετημένα Δελτία"
                elif view == 'w_streak':
                    view_df = df[df['Α/Α'].isin(win_streak_idx)]
                    title_str = f"🟢 Μέγιστο Σερί Νικών ({max_win_streak} δελτία)"
                elif view == 'l_streak':
                    view_df = df[df['Α/Α'].isin(lose_streak_idx)]
                    title_str = f"🔴 Μέγιστο Σερί Ηττών ({max_lose_streak} δελτία)"
                elif view == 'max_odds':
                    view_df = df[df['Α/Α'] == max_win_odds_aa]
                    title_str = f"🏆 Δελτίο με Μέγιστη Κερδισμένη Απόδοση ({max_win_odds})"
                elif view == 'won':
                    view_df = filtered_df[filtered_df['Status'] == "🟢 Κερδισμένο"]
                    title_str = "🟢 Όλα τα Κερδισμένα"
                elif view == 'lost':
                    view_df = filtered_df[filtered_df['Status'] == "🔴 Χαμένο"]
                    title_str = "🔴 Όλα τα Χαμένα"
                elif view == 'cashout':
                    view_df = filtered_df[filtered_df['Status'] == "🟡 Cash Out"]
                    title_str = "🟡 Όλα τα Cash Out"
                elif view == 'void':
                    view_df = filtered_df[filtered_df['Status'] == "🔵 Ακυρωμένα"]
                    title_str = "🔵 Όλα τα Ακυρωμένα"
                elif view == 'pending':
                    view_df = filtered_df[filtered_df['Status'] == "⚪ Εκκρεμές"]
                    title_str = "⚪ Όλα τα Εκκρεμή"

                col_title.markdown(f"#### {title_str}")
                if col_close.button("❌ Κλείσιμο Προβολής", key="close_view"):
                    st.session_state['active_view'] = None
                    st.rerun()
                    
                if not view_df.empty:
                    disp = view_df.drop(columns=['Legs_Data'], errors='ignore')[DISPLAY_ORDER].sort_values(by=["Date", "Time"], ascending=False)
                    st.dataframe(disp, use_container_width=True, hide_index=True, column_config=GREEK_COLUMNS)
                else:
                    st.info("Δεν βρέθηκαν δελτία για αυτή την κατηγορία.")
            
            st.markdown("---")
            col_chart1, col_chart2 = st.columns(2)
            
            with col_chart1:
                st.markdown("### 📉 Εξέλιξη Κέρδους")
                if not completed_bets.empty:
                    df_line = sorted_for_streaks.copy()
                    df_line['Bankroll'] = df_line['Profit'].cumsum()
                    df_line['Ημ/νια'] = pd.to_datetime(df_line['Date']).dt.strftime('%d/%m/%Y')
                    df_line['Bet_Count'] = range(1, len(df_line) + 1)
                    
                    zero_point = pd.DataFrame([{'Bet_Count': 0, 'Bankroll': 0.0, 'Ημ/νια': '-', 'Event': 'Αρχικό Κεφάλαιο (Μηδέν)', 'Profit': 0.0}])
                    df_line = pd.concat([zero_point, df_line], ignore_index=True)
                    
                    base = alt.Chart(df_line).encode(
                        x=alt.X('Bet_Count:Q', axis=alt.Axis(labels=False, title=None, ticks=False, grid=False)),
                        y=alt.Y('Bankroll:Q', title="Ταμείο (€)", axis=alt.Axis(gridColor="#1f2937"))
                    )
                    
                    line = base.mark_trail(interpolate='monotone').encode(
                        color=alt.condition(alt.datum.Bankroll >= 0, alt.value('#4ade80'), alt.value('#ff4b4b')),
                        size=alt.value(3)
                    )
                    
                    points = base.mark_circle(size=60).encode(
                        color=alt.condition(alt.datum.Bankroll >= 0, alt.value('#4ade80'), alt.value('#ff4b4b'))
                    )
                    
                    hover_points = base.mark_circle(size=500, color="transparent").encode(
                        tooltip=[alt.Tooltip('Ημ/νια:N', title='Ημερομηνία'), alt.Tooltip('Bankroll:Q', title='Κέρδος (€)', format='.2f')]
                    )
                    
                    chart = (line + points + hover_points).properties(height=350)
                    st.altair_chart(chart, use_container_width=True, theme="streamlit")
                else:
                    st.info("Δεν υπάρχουν ολοκληρωμένα δελτία στο επιλεγμένο εύρος ημερομηνιών για να εμφανιστεί γράφημα.")
                    
            with col_chart2:
                st.markdown("### 🗓️ Ταμείο ανά Μήνα")
                monthly_df = completed_bets.copy()
                if not monthly_df.empty:
                    monthly_df['MonthStr'] = pd.to_datetime(monthly_df['Date']).dt.strftime('%m/%Y')
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

    elif page == "⏳ Εκκρεμή":
        st.header("⏳ Εκκρεμή Στοιχήματα")
        st.info("💡 Άλλαξε την 'Κατάσταση' και πάτα Αποθήκευση για να τα διευθετήσεις.")
        
        pending_df = filtered_df[filtered_df['Status'] == "⚪ Εκκρεμές"].copy()
        
        if pending_df.empty:
            st.success("Όλα τα δελτία σου είναι διευθετημένα! Δεν χρωστάς τίποτα.")
        else:
            edit_pending_df = pending_df.drop(columns=['Legs_Data'])[DISPLAY_ORDER].sort_values(by="Α/Α", ascending=False)
            edited_pending = st.data_editor(edit_pending_df, use_container_width=True, hide_index=True, column_config=GREEK_COLUMNS)
            
            if st.button("💾 Αποθήκευση Εκκρεμών"):
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

    elif page == "📋 Ιστορικό ανά Μήνα":
        st.header("📋 Ιστορικό ανά Μήνα")
        if filtered_df.empty:
            st.write("Το ιστορικό είναι άδειο για αυτές τις ημερομηνίες.")
        else:
            filtered_df['MonthGroup'] = pd.to_datetime(filtered_df['Date']).dt.strftime('%Y-%m')
            months = sorted(filtered_df['MonthGroup'].dropna().unique().tolist(), reverse=True)
            
            month_options = {}
            for m in months:
                dt_obj = datetime.strptime(m, '%Y-%m')
                m_name = dt_obj.strftime('%B %Y').capitalize()
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
            c1.metric("Συνολικό Ταμείο", f"{month_profit:.2f} €")
            
            if best_day is not None and worst_day is not None:
                c2.metric("🟢 Πιο Κερδοφόρα", f"{best_day['JustDate'].strftime('%d/%m')} ({best_day['Profit']:.2f} €)")
                c3.metric("🔴 Χειρότερη Μέρα", f"{worst_day['JustDate'].strftime('%d/%m')} ({worst_day['Profit']:.2f} €)")
            else:
                c2.metric("🟢 Πιο Κερδοφόρα", "-")
                c3.metric("🔴 Χειρότερη Μέρα", "-")
                
            c4.metric("Σύνολο Δελτίων", f"{len(month_df)}")
            
            st.markdown("---")
            
            month_df['Week'] = pd.to_datetime(month_df['Date']).dt.isocalendar().week
            weeks = sorted(month_df['Week'].dropna().unique().tolist(), reverse=True)
            
            for w in weeks:
                week_df = month_df[month_df['Week'] == w]
                week_profit = week_df['Profit'].sum()
                wp_emoji = "🟢" if week_profit > 0 else "🔴" if week_profit < 0 else "⚪"
                
                min_w_date = week_df['JustDate'].min().strftime('%d/%m')
                max_w_date = week_df['JustDate'].max().strftime('%d/%m')
                
                st.markdown(f"#### 📅 Εβδομάδα ({min_w_date} - {max_w_date}) | Ταμείο: {wp_emoji} {week_profit:.2f} €")
                
                days = sorted(week_df['JustDate'].unique().tolist(), reverse=True)
                for day in days:
                    day_df = week_df[week_df['JustDate'] == day]
                    day_profit = day_df['Profit'].sum()
                    day_str = day.strftime('%d %B %Y') 
                    
                    if day_profit > 0: d_emoji = "🟢"; d_prof_str = f"+{day_profit:.2f}"
                    elif day_profit < 0: d_emoji = "🔴"; d_prof_str = f"{day_profit:.2f}"
                    else: d_emoji = "⚪"; d_prof_str = f"{day_profit:.2f}"
                        
                    with st.expander(f"{d_emoji} {day_str}  |  Ημερήσιο Κέρδος: {d_prof_str} €", expanded=False):
                        display_df = day_df.drop(columns=['MonthGroup', 'Legs_Data', 'JustDate', 'Week'])[DISPLAY_ORDER].sort_values(by="Α/Α", ascending=False)
                        st.dataframe(display_df, use_container_width=True, hide_index=True, column_config=GREEK_COLUMNS)
                
                st.markdown("<br>", unsafe_allow_html=True)

    elif page == "✏️ Επεξεργασία & Διαγραφή":
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
                        
                    st.markdown("🔹 **Βασικά Στοιχεία**")
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
                        st.markdown("🔹 **Αγώνας & Αγορά (Επεξεργασία)**")
                        c_ev, c_ma = st.columns(2)
                        
                        ed_ev_key = f"ed_ev_txt_{selected_aa}"
                        final_ev_str = c_ev.text_input("Αγώνας:", value=e_event, key=ed_ev_key)
                        render_suggestions(c_ev, ed_ev_key, final_ev_str, get_event_suggestions, (all_events, all_teams))
                            
                        ed_ma_key = f"ed_ma_txt_{selected_aa}"
                        final_ma_str = c_ma.text_input("Αγορά:", value=e_market, key=ed_ma_key)
                        render_suggestions(c_ma, ed_ma_key, final_ma_str, get_market_suggestions, (all_markets,))
                            
                    elif edit_bet_type == "Bet Builder":
                        st.markdown("🔹 **Κοινός Αγώνας (Bet Builder)**")
                        c_ev, _ = st.columns(2)
                        bb_ev = e_legs[0]['event'] if e_legs and 'event' in e_legs[0] else e_event
                        bb_ev_clean = bb_ev.split(" (")[0] if " (" in bb_ev else bb_ev
                        
                        ed_ev_key = f"ed_bb_ev_t_{selected_aa}"
                        final_ev_str = c_ev.text_input("Αγώνας:", value=bb_ev_clean, key=ed_ev_key)
                        render_suggestions(c_ev, ed_ev_key, final_ev_str, get_event_suggestions, (all_events, all_teams))

                        st.markdown("🔹 **Σημεία Bet Builder**")
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
                        st.markdown(f"🔹 **Ανάλυση Σημείων ({edit_bet_type})**")
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
                    st.markdown("🔹 **Αποδόσεις & Ποντάρισμα**")
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
                    
                    if st.button("💾 Αποθήκευση Αλλαγών", type="primary", key=f"ed_save_btn_{selected_aa}"):
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
                
                if st.button("💾 Εφαρμογή Αλλαγών (Πίνακα)"):
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