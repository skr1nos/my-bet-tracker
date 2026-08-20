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

if st.session_state['show_toast']:
    st.toast(st.session_state['toast_message'], icon="✅")
    st.session_state['show_toast'] = False 

# ==========================================
# Έξυπνη Αναζήτηση Παρόμοιων Ονομάτων
# ==========================================
def get_similar_items(user_text, history_list):
    if not user_text or len(user_text.strip()) < 3:
        return []
    
    user_lower = user_text.lower()
    matches = [x for x in history_list if user_lower in x.lower() and x.lower() != user_lower]
    
    if not matches:
        user_words = set(re.findall(r'\w{3,}', user_lower))
        if user_words:
            for item in history_list:
                item_words = set(re.findall(r'\w{3,}', item.lower()))
                if user_words.intersection(item_words) and item.lower() != user_lower:
                    matches.append(item)
                    
    return list(set(matches))[:3]

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
    for col in ['Market', 'Event', 'Sport', 'Type', 'Legs_Data']:
        df[col] = df[col].astype(str)
    
    for k, v in SPORT_ICONS.items():
        df.loc[df['Sport'] == k, 'Sport'] = v
        
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

global_avg_odds = df['Odds'].mean()
if pd.isna(global_avg_odds) or global_avg_odds < 1.01:
    global_avg_odds = 1.50
else:
    global_avg_odds = float(global_avg_odds)

dynamic_sports = list(SPORT_ICONS.values())
for s in df['Sport'].dropna().unique().tolist():
    if s not in dynamic_sports and s != '':
        dynamic_sports.append(s)

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

page = st.sidebar.radio(
    "Επίλεξε Σελίδα:",
    ["🏠 Αρχική & Στατιστικά", "⏳ Εκκρεμή", "📋 Ιστορικό ανά Μήνα", "✏️ Επεξεργασία & Διαγραφή"]
)

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
    start_date, end_date = date_filter
    filtered_df = filtered_df[(filtered_df['Date'] >= start_date) & (filtered_df['Date'] <= end_date)]
elif len(date_filter) == 1:
    start_date = date_filter[0]
    filtered_df = filtered_df[filtered_df['Date'] >= start_date]

if search_event: filtered_df = filtered_df[filtered_df['Event'].str.contains(search_event, case=False, na=False)]
if selected_sport != "Όλα": filtered_df = filtered_df[filtered_df['Sport'] == selected_sport]
if selected_type != "Όλοι οι Τύποι": filtered_df = filtered_df[filtered_df['Type'] == selected_type]

st.title("📈 Στοιχηματικό Dashboard")

# Αν είναι ανοιχτή η φόρμα, δείξε ΜΟΝΟ τη φόρμα
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
        
        st.markdown("**1. Βασικά Στοιχεία**")
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
            st.markdown("**2. Αγώνας & Αγορά (Με μνήμη Ιστορικού)**")
            c_ev, c_ma = st.columns(2)
            
            ev_choice = c_ev.selectbox("Αγώνας", ["✍️ Νέα Καταχώρηση..."] + all_events, key=f"ev_choice_single_{reset_id}")
            if ev_choice == "✍️ Νέα Καταχώρηση...": 
                event_str = c_ev.text_input("Γράψε νέο Αγώνα:", value="", key=f"ev_single_{reset_id}")
                if event_str:
                    sims = get_similar_items(event_str, all_events)
                    if sims:
                        c_ev.info("💡 **Μήπως εννοείς:**\n" + "\n".join([f"- {s}" for s in sims]))
            else: 
                event_str = ev_choice
                
            ma_choice = c_ma.selectbox("Αγορά", ["✍️ Νέα Καταχώρηση..."] + all_markets, key=f"ma_choice_single_{reset_id}")
            if ma_choice == "✍️ Νέα Καταχώρηση...": 
                market_str = c_ma.text_input("Γράψε νέα Αγορά:", value="", key=f"ma_single_{reset_id}")
                if market_str:
                    sims = get_similar_items(market_str, all_markets)
                    if sims:
                        c_ma.info("💡 **Μήπως εννοείς:**\n" + "\n".join([f"- {s}" for s in sims]))
            else: 
                market_str = ma_choice
            
        else:
            st.markdown(f"**2. Ανάλυση Σημείων ({bet_type})**")
            
            for i in range(int(num_legs)):
                cc1, cc2, cc3 = st.columns([2,2,1])
                l_ev_choice = cc1.selectbox(f"Αγώνας {i+1}", ["✍️ Νέα Καταχώρηση..."] + all_events, key=f"lev_choice_{i}_{reset_id}")
                if l_ev_choice == "✍️ Νέα Καταχώρηση...": 
                    l_ev = cc1.text_input(f"Νέος Αγώνας {i+1}", value="", key=f"ev_{i}_{reset_id}", label_visibility="collapsed")
                    if l_ev:
                        sims = get_similar_items(l_ev, all_events)
                        if sims:
                            cc1.info("💡 **Μήπως εννοείς:**\n" + "\n".join([f"- {s}" for s in sims]))
                else: 
                    l_ev = l_ev_choice
                    
                l_ma_choice = cc2.selectbox(f"Σημείο {i+1}", ["✍️ Νέα Καταχώρηση..."] + all_markets, key=f"lma_choice_{i}_{reset_id}")
                if l_ma_choice == "✍️ Νέα Καταχώρηση...": 
                    l_ma = cc2.text_input(f"Νέο Σημείο {i+1}", value="", key=f"ma_{i}_{reset_id}", label_visibility="collapsed")
                    if l_ma:
                        sims = get_similar_items(l_ma, all_markets)
                        if sims:
                            cc2.info("💡 **Μήπως εννοείς:**\n" + "\n".join([f"- {s}" for s in sims]))
                else: 
                    l_ma = l_ma_choice
                    
                l_od = cc3.number_input(f"Απόδοση {i+1}", min_value=1.00, step=0.01, value=1.50, key=f"od_{i}_{reset_id}")
                
                legs.append({"event": l_ev, "market": l_ma, "odds": l_od, "status": "⚪ Εκκρεμές"})
                auto_odds *= l_od
                
        st.markdown("---")
        st.markdown("**3. Αποδόσεις & Ποντάρισμα**")
        c5, c6, c7, c8 = st.columns(4)
        
        if bet_type == "Μονό":
            odds = c5.number_input("Απόδοση", min_value=1.01, step=0.01, value=round(global_avg_odds, 2), key=f"odds_single_{reset_id}")
        else:
            odds = c5.number_input("Συνολική Απόδοση Δελτίου", min_value=1.01, step=0.01, value=float(auto_odds), key=f"odds_multi_{reset_id}")
            
        chosen_preset = c6.selectbox("Ποντάρισμα (€)", STAKE_PRESETS, key=f"stake_preset_{reset_id}")
        custom_stake = c7.number_input("Ή γράψε δικό σου ποσό (€)", min_value=0.0, step=0.05, format="%.2f", key=f"custom_stake_{reset_id}")
        status = c8.selectbox("Κατάσταση (Συνολική)", STATUS_LIST, key=f"status_{reset_id}")
        
        cash_out_val = 0.0
        if status == "🟡 Cash Out":
            st.info("💸 Επέλεξες Cash Out! Δήλωσε το ποσό που εισέπραξες:")
            cash_out_val = st.number_input("Επιστροφή Cash Out (€)", min_value=0.0, step=0.01, format="%.2f", key=f"cashout_{reset_id}")
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        if st.button("💾 Αποθήκευση Δελτίου", type="primary"):
            profit = 0.0
            stake = custom_stake if chosen_preset == "Χειροκίνητα..." else float(chosen_preset)

            if status == "🟢 Κερδισμένο": profit = stake * (odds - 1)
            elif status == "🔴 Χαμένο": profit = -stake
            elif status == "🟡 Cash Out": profit = cash_out_val - stake
            
            t_string = t.strftime('%H:%M')
            legs_json = ""
            
            if bet_type != "Μονό":
                legs_json = json.dumps(legs)
                if bet_type == "Bet Builder":
                    event_str = legs[0]['event'] if legs[0]['event'] else "" 
                else:
                    events_list = [l['event'] for l in legs if l['event']]
                    event_str = " | ".join(events_list) if events_list else ""
                    
                market_str = " | ".join([f"⚪ {l['market']} ({l['odds']:.2f})" for l in legs])
            
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

# Αλλιώς, αν Η ΦΟΡΜΑ ΕΙΝΑΙ ΚΛΕΙΣΤΗ, δείξε το περιεχόμενο της επιλεγμένης σελίδας
else:
    if page == "🏠 Αρχική & Στατιστικά":
        st.header("🏠 Στατιστικά & Αναλύσεις")
        if filtered_df.empty:
            st.warning("Δεν βρέθηκαν στοιχήματα για αυτά τα φίλτρα.")
        else:
            completed_bets = filtered_df[filtered_df['Status'].isin(["🟢 Κερδισμένο", "🔴 Χαμένο", "🟡 Cash Out"])]
            
            total_profit = filtered_df['Profit'].sum()
            total_staked = completed_bets['Stake'].sum()
            yield_pct = (total_profit / total_staked * 100) if total_staked > 0 else 0
            win_rate = (len(completed_bets[completed_bets['Profit'] > 0]) / len(completed_bets) * 100) if len(completed_bets) > 0 else 0
            total_bets = len(completed_bets)

            avg_odds = filtered_df['Odds'].mean()
            winning_bets = filtered_df[filtered_df['Status'] == "🟢 Κερδισμένο"]
            max_win_odds = winning_bets['Odds'].max() if not winning_bets.empty else 0.0

            completed_bets['DateTime'] = pd.to_datetime(completed_bets['Date'].astype(str) + ' ' + completed_bets['Time'].astype(str))
            sorted_for_streaks = completed_bets.sort_values(by="DateTime")
            
            max_win_streak, max_lose_streak = 0, 0
            current_w, current_l = 0, 0
            
            for status in sorted_for_streaks['Status']:
                if status == "🟢 Κερδισμένο":
                    current_w += 1; current_l = 0
                    if current_w > max_win_streak: max_win_streak = current_w
                elif status == "🔴 Χαμένο":
                    current_l += 1; current_w = 0
                    if current_l > max_lose_streak: max_lose_streak = current_l
                else: 
                    current_w = 0; current_l = 0

            count_won = len(filtered_df[filtered_df['Status'] == "🟢 Κερδισμένο"])
            count_lost = len(filtered_df[filtered_df['Status'] == "🔴 Χαμένο"])
            count_cashout = len(filtered_df[filtered_df['Status'] == "🟡 Cash Out"])
            count_void = len(filtered_df[filtered_df['Status'] == "🔵 Ακυρωμένο"])
            count_pending = len(filtered_df[filtered_df['Status'] == "⚪ Εκκρεμές"])

            st.markdown("### 🏆 Στατιστικά Ταμείου")
            col_a, col_b, col_c, col_d = st.columns(4)
            
            prof_color = "#4ade80" if total_profit > 0 else "#ff4b4b" if total_profit < 0 else "#ffffff"

            col_a.markdown(f"""
            <div style="background-color: #16263b; border-radius: 10px; padding: 15px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);">
                <div style="color: #a8dadc; font-size: 14px; margin-bottom: 0.3rem;">Συνολικό Κέρδος</div>
                <div style="color: {prof_color}; font-size: 1.8rem; font-weight: normal;">{total_profit:.2f} €</div>
            </div>
            """, unsafe_allow_html=True)

            col_b.markdown(f"""
            <div style="background-color: #16263b; border-radius: 10px; padding: 15px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);">
                <div style="color: #a8dadc; font-size: 14px; margin-bottom: 0.3rem;">Yield (ROI)</div>
                <div style="color: {prof_color}; font-size: 1.8rem; font-weight: normal;">{yield_pct:.2f} %</div>
            </div>
            """, unsafe_allow_html=True)

            col_c.metric("Win Rate", f"{win_rate:.1f} %")
            col_d.metric("Σύνολο Στοιχημάτων (Διευθετημένα)", f"{total_bets}")

            col_e, col_f, col_g, col_h = st.columns(4)
            col_e.metric("Μέγιστο Σερί Νικών", f"{max_win_streak} 🟢")
            col_f.metric("Μέγιστο Σερί Ηττών", f"{max_lose_streak} 🔴")
            col_g.metric("Μέση Απόδοση", f"{avg_odds:.2f}")
            col_h.metric("Μέγιστη Κερδισμένη Απόδοση", f"{max_win_odds:.2f}")
            
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown("### 📊 Ανάλυση Αποτελεσμάτων")
            c_w, c_l, c_c, c_v, c_p = st.columns(5)
            c_w.metric("🟢 Κερδισμένα", f"{count_won}")
            c_l.metric("🔴 Χαμένα", f"{count_lost}")
            c_c.metric("🟡 Cash Out", f"{count_cashout}")
            c_v.metric("🔵 Ακυρωμένα", f"{count_void}")
            c_p.metric("⚪ Εκκρεμή", f"{count_pending}")

            st.markdown("---")
            
            col_chart1, col_chart2 = st.columns(2)
            
            with col_chart1:
                st.markdown("### 📉 Εξέλιξη Κέρδους")
                if not completed_bets.empty:
                    df_line = sorted_for_streaks.copy()
                    df_line['Bankroll'] = df_line['Profit'].cumsum()
                    df_line['Ημ/νια'] = df_line['Date'].astype(str) + " " + df_line['Time'].astype(str)
                    df_line['Bet_Count'] = range(1, len(df_line) + 1)
                    
                    zero_point = pd.DataFrame([{
                        'Bet_Count': 0, 'Bankroll': 0.0, 'Ημ/νια': '-', 
                        'Event': 'Αρχικό Κεφάλαιο (Μηδέν)', 'Profit': 0.0
                    }])
                    df_line = pd.concat([zero_point, df_line], ignore_index=True)
                    
                    base = alt.Chart(df_line).encode(
                        x=alt.X('Bet_Count:Q', axis=alt.Axis(labels=False, title=None, ticks=False, grid=False)),
                        y=alt.Y('Bankroll:Q', title="Ταμείο (€)", axis=alt.Axis(gridColor="#1f2937"))
                    )
                    
                    line = base.mark_line(color="#4db8ff", strokeWidth=3, point=True)
                    
                    hover_points = base.mark_circle(size=500, color="transparent").encode(
                        tooltip=[
                            alt.Tooltip('Ημ/νια:N', title='Ημερομηνία'), 
                            alt.Tooltip('Bankroll:Q', title='Κέρδος (€)', format='.2f')
                        ]
                    )
                    
                    chart = (line + hover_points).properties(height=350)
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
                        tooltip=[
                            alt.Tooltip('MonthStr:N', title='Μήνας'), 
                            alt.Tooltip('Profit:Q', title='Ταμείο Μήνα', format='.2f')
                        ]
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
                
        st.markdown("---")
        
        st.markdown("### 💸 Ειδική Διευθέτηση Cash Out")
        st.info("💡 Έκανες Cash Out σε κάποιο εκκρεμές δελτίο; Επίλεξέ το εδώ και δήλωσε το ποσό που πήρες πίσω.")
        
        if not pending_df.empty:
            co_options = {}
            pending_co_df = pending_df.sort_values(by="Α/Α", ascending=False)
            for idx, row in pending_co_df.iterrows():
                d_str = pd.to_datetime(row['Date']).strftime('%d/%m/%Y') if pd.notnull(row['Date']) else ""
                desc = f"Α/Α {row['Α/Α']} | {d_str} | {row['Type']} | {row['Market']} (Ποντάρισμα: {row['Stake']}€)"
                co_options[desc] = row['Α/Α'] 
                
            selected_co_desc = st.selectbox("Επίλεξε Εκκρεμές Δελτίο για Cash Out:", list(co_options.keys()), key="co_select_tab2")
            selected_co_aa = co_options[selected_co_desc]
            co_return = st.number_input("Ποσό που εισέπραξες (€):", min_value=0.0, step=0.05, format="%.2f", key="co_val_tab2")
            
            if st.button("💸 Εφαρμογή Cash Out", key="co_btn_tab2"):
                real_idx = df.index[df['Α/Α'] == selected_co_aa].tolist()[0]
                stake = float(df.at[real_idx, 'Stake'])
                profit = co_return - stake
                
                df.at[real_idx, 'Status'] = "🟡 Cash Out"
                df.at[real_idx, 'Profit'] = profit
                
                save_df = df.drop(columns=['Α/Α'], errors='ignore')
                save_df['Time'] = pd.to_datetime(save_df['Time'].astype(str), errors='coerce').dt.strftime('%H:%M').fillna('00:00')
                save_data(save_df)
                
                st.session_state['show_toast'] = True
                st.session_state['toast_message'] = "Το Cash Out καταχωρήθηκε επιτυχώς!"
                st.rerun()

    elif page == "📋 Ιστορικό ανά Μήνα":
        st.header("📋 Ιστορικό ανά Μήνα")
        if filtered_df.empty:
            st.write("Το ιστορικό είναι άδειο για αυτές τις ημερομηνίες.")
        else:
            filtered_df['MonthGroup'] = pd.to_datetime(filtered_df['Date']).dt.strftime('%Y-%m')
            months = sorted(filtered_df['MonthGroup'].dropna().unique().tolist(), reverse=True)
            
            for month in months:
                month_df = filtered_df[filtered_df['MonthGroup'] == month].copy()
                month_profit = month_df['Profit'].sum()
                
                dt_obj = datetime.strptime(month, '%Y-%m')
                month_name = dt_obj.strftime('%B %Y').capitalize()
                
                if month_profit > 0: title_emoji = "🟢"
                elif month_profit < 0: title_emoji = "🔴"
                else: title_emoji = "⚪"
                    
                with st.expander(f"🗓️ {month_name}  |  Ταμείο Μήνα: {title_emoji} {month_profit:.2f} €"):
                    month_df['JustDate'] = pd.to_datetime(month_df['Date']).dt.date
                    days = sorted(month_df['JustDate'].unique().tolist(), reverse=True)
                    
                    for day in days:
                        day_df = month_df[month_df['JustDate'] == day]
                        day_profit = day_df['Profit'].sum()
                        day_str = day.strftime('%d/%m/%Y')
                        
                        if day_profit > 0: d_emoji = "🟢"; d_prof_str = f"+{day_profit:.2f}"
                        elif day_profit < 0: d_emoji = "🔴"; d_prof_str = f"{day_profit:.2f}"
                        else: d_emoji = "⚪"; d_prof_str = f"{day_profit:.2f}"
                            
                        st.markdown(f"#### 📅 {day_str} &nbsp;|&nbsp; Ημερήσιο Κέρδος: {d_emoji} {d_prof_str} €")
                        
                        display_df = day_df.drop(columns=['MonthGroup', 'Legs_Data', 'JustDate'])[DISPLAY_ORDER].sort_values(by="Α/Α", ascending=False)
                        st.dataframe(display_df, use_container_width=True, hide_index=True, column_config=GREEK_COLUMNS)
                    
                    st.markdown("<br>", unsafe_allow_html=True)

    elif page == "✏️ Επεξεργασία & Διαγραφή":
        st.header("✏️ Επεξεργασία & Διαγραφή")
        
        st.markdown("### Κεντρικός Πίνακας")
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
            
            if st.button("💾 Εφαρμογή Αλλαγών (Κεντρικού Πίνακα)"):
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

        st.markdown("---")
        
        st.markdown("### 💸 Ειδική Διευθέτηση Cash Out")
        st.info("💡 Έκανες Cash Out σε κάποιο δελτίο στο παρελθόν ή θες να διορθώσεις το ποσό; Επίλεξέ το εδώ και δήλωσε την επιστροφή σου.")
        
        cashout_bets = filtered_df[filtered_df['Status'] == '🟡 Cash Out']
        
        if not cashout_bets.empty:
            co_options = {}
            all_co_df = cashout_bets.sort_values(by="Α/Α", ascending=False)
            for idx, row in all_co_df.iterrows():
                d_str = pd.to_datetime(row['Date']).strftime('%d/%m/%Y') if pd.notnull(row['Date']) else ""
                desc = f"Α/Α {row['Α/Α']} | {d_str} | {row['Type']} | {row['Market']} (Ποντάρισμα: {row['Stake']}€)"
                co_options[desc] = row['Α/Α'] 
                
            selected_co_desc = st.selectbox("Επίλεξε Δελτίο για διόρθωση Cash Out:", list(co_options.keys()), key="co_select_tab4")
            selected_co_aa = co_options[selected_co_desc]
            co_return = st.number_input("Ποσό που εισέπραξες (€):", min_value=0.0, step=0.05, format="%.2f", key="co_val_tab4")
            
            if st.button("💸 Εφαρμογή Cash Out", key="co_btn_tab4"):
                real_idx = df.index[df['Α/Α'] == selected_co_aa].tolist()[0]
                stake = float(df.at[real_idx, 'Stake'])
                profit = co_return - stake
                
                df.at[real_idx, 'Status'] = "🟡 Cash Out"
                df.at[real_idx, 'Profit'] = profit
                
                save_df = df.drop(columns=['Α/Α'], errors='ignore')
                save_df['Time'] = pd.to_datetime(save_df['Time'].astype(str), errors='coerce').dt.strftime('%H:%M').fillna('00:00')
                save_data(save_df)
                
                st.session_state['show_toast'] = True
                st.session_state['toast_message'] = "Το Cash Out καταχωρήθηκε επιτυχώς!"
                st.rerun()
        else:
            st.success("Δεν βρέθηκαν στοιχήματα σε κατάσταση Cash Out στα επιλεγμένα φίλτρα.")

        st.markdown("---")
        st.markdown("### 🛠️ Ενημέρωση Σημείων (Ανοιχτά Παρολί / Bet Builders)")
        st.info("💡 Εδώ εμφανίζονται **μόνο** τα δελτία που είναι ακόμα σε Εκκρεμότητα. Αν χαθεί ή κερδηθεί όλο το δελτίο, θα υπολογιστεί το κέρδος αυτόματα!")
        
        open_multi_bets = filtered_df[
            (filtered_df['Type'].isin(['Παρολί', 'Bet Builder'])) & 
            (filtered_df['Status'] == '⚪ Εκκρεμές')
        ]
        
        if not open_multi_bets.empty:
            bet_options = {}
            open_multi_bets = open_multi_bets.sort_values(by="Α/Α", ascending=False)
            for idx, row in open_multi_bets.iterrows():
                d_str = pd.to_datetime(row['Date']).strftime('%d/%m/%Y') if pd.notnull(row['Date']) else ""
                desc = f"Α/Α {row['Α/Α']} | {d_str} | {row['Type']} | {row['Event']}"
                bet_options[desc] = row['Α/Α'] 
                
            selected_desc = st.selectbox("Επίλεξε Ανοιχτό Δελτίο:", list(bet_options.keys()))
            selected_aa = bet_options[selected_desc]
            
            real_idx = df.index[df['Α/Α'] == selected_aa].tolist()[0]
            
            row_data = df.loc[real_idx]
            legs_data = row_data['Legs_Data']
            
            if pd.notna(legs_data) and legs_data != '' and legs_data != 'nan':
                try:
                    legs_list = json.loads(legs_data)
                    updated_legs = []
                    
                    st.markdown(f"**Σημεία για: {selected_desc}**")
                    
                    for i, leg in enumerate(legs_list):
                        col1, col2, col3, col4 = st.columns([3, 3, 2, 3])
                        col1.write(f"**Αγώνας:** {leg.get('event', '')}")
                        col2.write(f"**Αγορά:** {leg.get('market', '')}")
                        col3.write(f"**Απόδοση:** {leg.get('odds', '')}")
                        
                        current_status = leg.get('status', '⚪ Εκκρεμές')
                        new_stat = col4.selectbox(f"Κατάσταση {i+1}", STATUS_LIST, index=STATUS_LIST.index(current_status), key=f"leg_stat_{i}")
                        
                        updated_legs.append({
                            "event": leg.get('event', ''),
                            "market": leg.get('market', ''),
                            "odds": leg.get('odds', ''),
                            "status": new_stat
                        })
                        
                    if st.button("💾 Αποθήκευση Σημείων"):
                        new_json = json.dumps(updated_legs)
                        
                        market_parts = []
                        for l in updated_legs:
                            emoji = "⚪"
                            if l['status'] == "🟢 Κερδισμένο": emoji = "🟢"
                            elif l['status'] == "🔴 Χαμένο": emoji = "🔴"
                            elif l['status'] == "🔵 Ακυρωμένο": emoji = "🔵"
                            market_parts.append(f"{emoji} {l['market']} ({float(l['odds']):.2f})")
                        
                        new_market_str = " | ".join(market_parts)
                        
                        df.at[real_idx, 'Legs_Data'] = new_json
                        df.at[real_idx, 'Market'] = new_market_str
                        
                        statuses = [l['status'] for l in updated_legs]
                        
                        if "🔴 Χαμένο" in statuses:
                            new_overall = "🔴 Χαμένο"
                        elif "⚪ Εκκρεμές" in statuses:
                            new_overall = "⚪ Εκκρεμές"
                        else:
                            if "🟢 Κερδισμένο" in statuses:
                                new_overall = "🟢 Κερδισμένο"
                            else:
                                new_overall = "🔵 Ακυρωμένο"
                                
                        df.at[real_idx, 'Status'] = new_overall
                        
                        stake = float(df.at[real_idx, 'Stake'])
                        odds = float(df.at[real_idx, 'Odds'])
                        
                        if new_overall == "🟢 Κερδισμένο":
                            df.at[real_idx, 'Profit'] = stake * (odds - 1.0)
                        elif new_overall == "🔴 Χαμένο":
                            df.at[real_idx, 'Profit'] = -stake
                        elif new_overall == "🔵 Ακυρωμένο":
                            df.at[real_idx, 'Profit'] = 0.0
                            
                        save_df = df.drop(columns=['Α/Α'], errors='ignore')
                        save_df['Time'] = pd.to_datetime(save_df['Time'].astype(str), errors='coerce').dt.strftime('%H:%M').fillna('00:00')
                        save_data(save_df)
                        
                        st.session_state['show_toast'] = True
                        if new_overall == "🟢 Κερδισμένο":
                            st.session_state['toast_message'] = "✅ Όλα τα σημεία έπιασαν! Το δελτίο ΚΕΡΔΙΣΕ!"
                        elif new_overall == "🔴 Χαμένο":
                            st.session_state['toast_message'] = "❌ Δυστυχώς το δελτίο χάθηκε..."
                        else:
                            st.session_state['toast_message'] = "✅ Τα σημεία ενημερώθηκαν επιτυχώς!"
                            
                        st.rerun()
                except Exception as e:
                    st.error("Υπήρξε πρόβλημα με την ανάγνωση των σημείων.")
        else:
            st.success("Δεν έχεις κανένα ανοιχτό Παρολί ή Bet Builder!")