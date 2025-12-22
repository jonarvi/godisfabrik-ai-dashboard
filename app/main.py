import streamlit as st
import pandas as pd
import sqlalchemy
import requests
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

# --- SETUP & KONFIGURATION ---
st.set_page_config(page_title="Godisfabrik 4.1", layout="wide", page_icon="🍬")

# CSS
st.markdown("""
<style>
    .stButton>button { text-align: left; border-radius: 8px; }
    .action-btn>button { background-color: #2e7d32; color: white; }
    .report-btn>button { background-color: #1565c0; color: white; }
    div[data-testid="stMetricValue"] { font-size: 1.5rem; }
</style>
""", unsafe_allow_html=True)

# Databaskoppling
DB_SERVER = "127.0.0.1"
@st.cache_resource
def get_engine():
    return sqlalchemy.create_engine(f"mssql+pyodbc://sa:CandyFactory2025!@{DB_SERVER}/CandyDB?driver=ODBC+Driver+17+for+SQL+Server&TrustServerCertificate=yes")

def get_data(query, params=None):
    try:
        engine = get_engine()
        return pd.read_sql(query, engine, params=params)
    except Exception:
        return pd.DataFrame()

# --- AI LOGIK (FÖRBÄTTRAD) ---
def ask_ai_logic(prompt, start_d, end_d):
    prompt_lower = prompt.lower()
    
    # 1. FÖRSÖK HITTA GRAF-TRÄFFAR (Hårdare regler)
    sql_query = ""
    title = ""
    
    # Topplista larm
    if "larm" in prompt_lower and any(x in prompt_lower for x in ["topp", "mest", "vanligast", "antal"]):
        sql_query = "SELECT TOP 10 Description, COUNT(*) as Antal FROM Alarms WHERE StartTime BETWEEN ? AND ? GROUP BY Description ORDER BY Antal DESC"
        title = "Topp Larmorsaker"
        
    # Värsta maskinerna (Måste innehålla ord om fel/larm)
    elif "maskin" in prompt_lower and any(x in prompt_lower for x in ["mest larm", "värsta", "flest fel", "problem"]):
        sql_query = "SELECT TOP 10 m.Name, COUNT(*) as Antal FROM Alarms a JOIN Machines m ON a.MachineID=m.MachineID WHERE a.StartTime BETWEEN ? AND ? GROUP BY m.Name ORDER BY Antal DESC"
        title = "Maskiner med flest fel"
        
    # Produktionstoppen
    elif any(x in prompt_lower for x in ["producerat", "produktion", "gjort"]) and any(x in prompt_lower for x in ["mest", "topp", "bäst"]):
        sql_query = "SELECT TOP 10 p.Name, SUM(pl.ProducedKg) as Mängd FROM ProductionLog pl JOIN Products p ON pl.ProductID=p.ProductID WHERE pl.StartTime BETWEEN ? AND ? GROUP BY p.Name ORDER BY Mängd DESC"
        title = "Produktionsvolym"

    # Om vi hittade en graf-match, returnera data
    if sql_query:
        df = get_data(sql_query, (start_d, end_d))
        return {"type": "data", "df": df, "title": title}

    # 2. ANNARS: TEXTSVAR (Med bättre kontext)
    
    # Hämta relevant data beroende på frågan för att ge AI:n bättre "hjärna"
    context_data = ""
    
    # Om frågan handlar om maskiner/avdelningar
    if any(x in prompt_lower for x in ["vilka", "finns", "avdelning", "intag", "blanderi", "press", "pack"]):
        df_m = get_data("SELECT m.Name, d.Name as Dept FROM Machines m JOIN Departments d ON m.DeptID=d.DeptID")
        context_data += f"\nMASKINLISTA:\n{df_m.to_string(index=False)}"

    # Om frågan handlar om produktion/kapacitet/sämst/bäst
    if any(x in prompt_lower for x in ["producerat", "kapacitet", "sämst", "bäst", "effektivitet", "kasserat"]):
        df_p = get_data("""
            SELECT TOP 10 m.Name, SUM(pl.ProducedKg) as ProdKg, SUM(pl.ScrappedKg) as ScrapKg 
            FROM ProductionLog pl JOIN Machines m ON pl.MachineID=m.MachineID 
            WHERE pl.StartTime BETWEEN ? AND ? GROUP BY m.Name ORDER BY ProdKg DESC
        """, (start_d, end_d))
        context_data += f"\nPRODUKTIONSDATA (Kg):\n{df_p.to_string(index=False)}"

    # Standard: Lite larmdata är alltid bra
    df_a = get_data("SELECT TOP 5 Description, COUNT(*) as Antal FROM Alarms WHERE StartTime BETWEEN ? AND ? GROUP BY Description ORDER BY Antal DESC", (start_d, end_d))
    context_data += f"\nTOPP LARM:\n{df_a.to_string(index=False)}"
    
    full_prompt = f"""
    Du är en hjälpsam driftschef på en godisfabrik. Svara på svenska.
    
    FABRIKSDATA:
    {context_data}
    
    ANVÄNDARENS FRÅGA: 
    {prompt}
    
    Instruktion: Använd datan ovan för att svara. Gissa inte om maskinnamn. Om datan visar "ProdKg", använd det.
    """
    
    try:
        r = requests.post("http://127.0.0.1:11434/api/generate", json={"model": "llama3", "prompt": full_prompt, "stream": False})
        return {"type": "text", "content": r.json()['response']}
    except:
        return {"type": "text", "content": "Kunde inte nå AI-motorn."}

# --- STATE ---
if 'view' not in st.session_state: st.session_state.view = 'chat'
if 'target_id' not in st.session_state: st.session_state.target_id = None
if 'chat_log' not in st.session_state: st.session_state.chat_log = []

# --- SIDEBAR ---
with st.sidebar:
    st.header("🏭 Styrpanel")
    st.subheader("Datum")
    d1 = st.date_input("Från", datetime(2024, 1, 1))
    d2 = st.date_input("Till", datetime.now())
    st.divider()
    
    st.markdown('<div class="report-btn">', unsafe_allow_html=True)
    if st.button("📄 Skapa Larmrapport"): st.session_state.view = 'report'
    if st.button("🚀 Beräkna OEE"): st.session_state.view = 'oee'
    st.markdown('</div>', unsafe_allow_html=True)
    if st.button("💬 Chat"): st.session_state.view = 'chat'
    st.divider()

    st.subheader("Avdelningar")
    depts = get_data("SELECT * FROM Departments")
    machines = get_data("SELECT * FROM Machines")
    if not depts.empty:
        for _, d in depts.iterrows():
            with st.expander(f"📁 {d['Name']}"):
                my_machines = machines[machines['DeptID'] == d['DeptID']]
                for _, m in my_machines.iterrows():
                    if st.button(f"⚙️ {m['Name']}", key=f"side_m_{m['MachineID']}"):
                        st.session_state.view = 'machine'
                        st.session_state.target_id = (m['MachineID'], m['Name'])

# --- VYER ---

# 1. CHAT
if st.session_state.view == 'chat':
    st.title("💬 Fråga Fabriken")
    
    # Här är fixen för DuplicateElementId: Vi använder enumerate(i) för att ge varje graf ett unikt ID
    for i, msg in enumerate(st.session_state.chat_log):
        with st.chat_message(msg['role']):
            if msg['type'] == 'text': 
                st.write(msg['content'])
            elif msg['type'] == 'data':
                st.write(f"**{msg['title']}**")
                if not msg['df'].empty:
                    cols = msg['df'].columns
                    fig = px.bar(msg['df'], x=cols[0], y=cols[1])
                    fig.update_layout(xaxis_tickangle=-45)
                    # VIKTIGT: Unik key här!
                    st.plotly_chart(fig, use_container_width=True, key=f"chat_chart_{i}")
                    with st.expander("Visa data"):
                        st.dataframe(msg['df'])

    prompt = st.chat_input("Fråga...")
    if prompt:
        st.session_state.chat_log.append({"role": "user", "type": "text", "content": prompt})
        with st.spinner("AI söker..."):
            response = ask_ai_logic(prompt, d1, d2)
        st.session_state.chat_log.append({"role": "assistant", "type": response['type'], "content": response.get('content'), "df": response.get('df'), "title": response.get('title')})
        st.rerun()

# 2. RAPPORT
elif st.session_state.view == 'report':
    st.title("📄 Larmrapport")
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Larmtrend")
        df = get_data("SELECT CAST(StartTime as DATE) as D, COUNT(*) as C FROM Alarms WHERE StartTime BETWEEN ? AND ? GROUP BY CAST(StartTime as DATE) ORDER BY D DESC", (d1, d2))
        if not df.empty:
            fig = px.bar(df, x='D', y='C')
            fig.update_layout(xaxis_tickangle=-45)
            st.plotly_chart(fig, use_container_width=True, key="rep_chart_1")
    with c2:
        st.subheader("Topporsaker")
        df = get_data("SELECT TOP 10 Description, SUM(DurationMinutes) as T FROM Alarms WHERE StartTime BETWEEN ? AND ? GROUP BY Description ORDER BY T DESC", (d1, d2))
        if not df.empty:
            fig = px.bar(df, x='Description', y='T')
            fig.update_layout(xaxis_tickangle=-45)
            st.plotly_chart(fig, use_container_width=True, key="rep_chart_2")

# 3. OEE
elif st.session_state.view == 'oee':
    st.title("🚀 OEE Dashboard")
    machs = get_data("SELECT MachineID, Name FROM Machines")
    for i, m in machs.iterrows():
        mid = m['MachineID']
        stats = get_data("SELECT SUM(pl.ProducedKg) as P, SUM(pl.ScrappedKg) as S, SUM(pl.DurationHours) as H, (SELECT SUM(DurationMinutes) FROM Alarms WHERE MachineID=? AND StartTime BETWEEN ? AND ?) as D FROM ProductionLog pl WHERE pl.MachineID=? AND pl.StartTime BETWEEN ? AND ?", (mid, d1, d2, mid, d1, d2))
        
        if not stats.empty and stats.iloc[0]['P'] is not None:
            row = stats.iloc[0]
            prod, scrap = row['P'] or 0, row['S'] or 0
            avail = ((row['H']*60 + (row['D'] or 0)) - (row['D'] or 0)) / ((row['H']*60 + (row['D'] or 0)) or 1)
            qual = prod / (prod + scrap) if (prod+scrap) > 0 else 1
            oee = avail * qual * 0.9 * 100
            
            with st.container():
                st.markdown(f"### {m['Name']}")
                c1, c2, c3 = st.columns([1, 2, 1])
                c1.metric("Tillgänglighet", f"{avail*100:.1f}%")
                c1.metric("Kvalitet", f"{qual*100:.1f}%")
                fig = go.Figure(go.Indicator(mode="gauge+number", value=oee, title={'text': "OEE"}, gauge={'axis': {'range': [None, 100]}, 'bar': {'color': "darkblue"}, 'steps': [{'range': [0, 50], 'color': "lightgray"}, {'range': [50, 85], 'color': "gray"}], 'threshold': {'line': {'color': "red", 'width': 4}, 'thickness': 0.75, 'value': 85}}))
                fig.update_layout(height=250, margin=dict(l=10, r=10, t=30, b=10))
                c2.plotly_chart(fig, use_container_width=True, key=f"oee_chart_{mid}")
                c3.metric("Prod", f"{prod:.0f} kg")
                c3.metric("Kass", f"{scrap:.0f} kg")
                st.divider()

# 4. MASKIN
elif st.session_state.view == 'machine':
    mid, mname = st.session_state.target_id
    st.title(f"⚙️ {mname}")
    t1, t2 = st.tabs(["Data", "AI"])
    with t1:
        df = get_data("SELECT TOP 50 a.StartTime, a.Description, s.SensorType, s.Value FROM Alarms a JOIN Sensors s ON a.AlarmID=s.AlarmID WHERE a.MachineID=? AND a.StartTime BETWEEN ? AND ? ORDER BY a.StartTime DESC", (mid, d1, d2))
        if not df.empty:
            st.dataframe(df, use_container_width=True)
            fig = px.scatter(df, x='StartTime', y='Value', color='SensorType')
            fig.update_layout(xaxis_tickangle=-45)
            st.plotly_chart(fig, use_container_width=True, key="sens_chart")
    with t2:
        q = st.text_input("Analysera maskin:")
        if q:
            # Smartare kontext här också
            larm_ctx = df.head(5).to_string() if not df.empty else "Inga larm."
            try:
                res = requests.post("http://127.0.0.1:11434/api/generate", json={"model": "llama3", "prompt": f"Analysera {mname}. Larmdata:\n{larm_ctx}\nFråga: {q}", "stream": False}).json()['response']
                st.write(res)
            except: st.error("AI error")
