import streamlit as st
import pandas as pd
import os
import plotly.express as px
import plotly.graph_objects as go
import requests
from bs4 import BeautifulSoup

# --- 頁面基本設定 ---
st.set_page_config(page_title="ETF 戰情室 Pro", page_icon="🦁", layout="wide")

# --- CSS 優化 (極簡 + 重點強化) ---
st.markdown("""
<style>
    .stDataFrame { font-size: 1.05rem; }
    /* KPI 數字放大 */
    div[data-testid="stMetricValue"] {
        font-size: 1.5rem !important;
        font-weight: 700;
        color: #2c3e50;
    }
    /* 產業標題樣式 */
    .industry-header {
        font-size: 1.15rem;
        font-weight: 600;
        color: #495057;
        margin-top: 20px;
        margin-bottom: 8px;
        padding-left: 12px;
        border-left: 5px solid #0d6efd; /* 藍色左邊條 */
        background-color: #f8f9fa;
        padding: 8px 12px;
        border-radius: 4px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.05);
    }
    /* 加強異動區塊的視覺 */
    .highlight-status {
        font-weight: bold;
        padding: 2px 6px;
        border-radius: 4px;
    }
</style>
""", unsafe_allow_html=True)

st.title("🦁 2026 主動式 ETF 操盤速覽 (Top 500 題材版)")

# --- 1. 資料讀取與清洗 ---
@st.cache_data(ttl=60)
def load_data(file_path):
    if not os.path.exists(file_path): return None
    try:
        return pd.read_csv(file_path, dtype=str, on_bad_lines='skip', engine='python', encoding='utf-8-sig')
    except: return None

def clean_data(df):
    if df is None or df.empty: return pd.DataFrame()
    for col in ['持有股數', '權重']:
        if col not in df.columns: df[col] = '0'
    for col in ['持有股數', '權重']:
        df[col] = df[col].astype(str).str.replace(',', '').str.replace('%', '')
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    if 'Date' in df.columns:
        df['Date'] = pd.to_datetime(df['Date'])
        df['DateStr'] = df['Date'].dt.strftime('%Y-%m-%d')
    else: return pd.DataFrame()
    df = df.drop_duplicates(subset=['DateStr', '股票代號'], keep='first')
    df = df.sort_values('Date', ascending=False)
    return df

# --- 2. 趨勢線邏輯 ---
def get_trend_data(full_df, stock_code):
    try:
        history = full_df[full_df['股票代號'] == stock_code].sort_values('Date', ascending=True)
        data = history['權重'].tail(30).tolist()
        if not data or all(x == 0 for x in data): return [0.0, 0.0]
        return data
    except: return [0.0, 0.0]

# --- 3. 究極分類系統 (Top 500 + 新聞題材) ---
# 這裡我花時間整理了新聞最常提到的板塊，而非死板的產業分類
STOCK_SECTOR_MAP = {
    # === 👑 護國神山與大聯盟 (半導體製造) ===
    '2330': '👑 台積電/晶圓代工', '2303': '👑 晶圓代工', '5347': '👑 晶圓代工', '6770': '👑 晶圓代工',
    
    # === 🧠 AI 大腦 (IC設計/IP/ASIC) ===
    '2454': '🧠 發哥/IC設計', '2379': '🧠 瑞昱/IC設計', '3034': '🧠 聯詠/IC設計', 
    '3661': '🧠 矽智財 (IP/ASIC)', '3443': '🧠 矽智財 (IP/ASIC)', '3529': '🧠 矽智財 (IP/ASIC)', 
    '3035': '🧠 矽智財 (IP/ASIC)', '6643': '🧠 矽智財 (IP/ASIC)', '6531': '🧠 矽智財 (IP/ASIC)',
    '4961': '🧠 IC設計', '8299': '🧠 群聯/記憶體控制', '5269': '🧠 祥碩/高速傳輸',
    '4966': '🧠 譜瑞/高速傳輸', '6415': '🧠 矽力/電源IC', '6138': '🧠 茂達/電源IC',

    # === 🤖 AI 伺服器軍火庫 (組裝/ODM) ===
    '2317': '🤖 鴻海/組裝', '2382': '🤖 廣達/AI伺服器', '3231': '🤖 緯創/AI伺服器', 
    '2356': '🤖 英業達', '2376': '🤖 技嘉', '6669': '🤖 緯穎/AI伺服器', 
    '2324': '🤖 仁寶', '2301': '🤖 光寶科', '2421': '🤖 建準', '3013': '🤖 晟銘電/機殼',
    '8210': '🤖 勤誠/機殼', '2059': '🤖 川湖/導軌',

    # === ❄️ 散熱 (液冷/氣冷) ===
    '3017': '❄️ 奇鋐/散熱', '3324': '❄️ 雙鴻/散熱', '3653': '❄️ 健策/散熱', 
    '2421': '❄️ 建準/散熱', '6230': '❄️ 超眾', '8996': '❄️ 高力/液冷',

    # === 📦 CoWoS 先進封裝設備 ===
    '3131': '📦 弘塑/CoWoS設備', '3583': '📦 辛耘/CoWoS設備', '6187': '📦 萬潤/CoWoS設備', 
    '6640': '📦 均華', '2449': '📦 京元電/封測', '3711': '📦 日月光/封測', 
    '6239': '📦 力成', '8150': '📦 南茂', '5483': '📦 中美晶', '6488': '📦 環球晶',

    # === 🛹 PCB 與 銅箔基板 (CCL) ===
    '2383': '🛹 台光電/CCL', '6274': '🛹 台燿/CCL', '6213': '🛹 聯茂/CCL',
    '3037': '🛹 欣興/載板', '3189': '🛹 景碩', '8046': '🛹 南電',
    '3044': '🛹 健鼎/PCB', '2313': '🛹 華通/低軌衛星', '3715': '🛹 定穎/車用PCB', 
    '2368': '🛹 金像電/伺服器PCB', '6191': '🛹 精成科',

    # === ✨ CPO 矽光子/光通訊/網通 ===
    '3081': '✨ 聯亞/CPO', '4979': '✨ 華星光/CPO', '3450': '✨ 聯鈞/CPO', 
    '4908': '✨ 前鼎/CPO', '3234': '✨ 光環', '2345': '📡 智邦/交換器', 
    '5388': '📡 中磊', '3704': '📡 啟碁', '6285': '📡 啟碁', '3045': '📡 台灣大', '2412': '📡 中華電',

    # === 🔌 電源/重電/綠能 ===
    '2308': '🔌 台達電', '1513': '⚡ 中興電/重電', '1519': '⚡ 華城/重電', 
    '1503': '⚡ 士電', '1504': '⚡ 東元', '1605': '⚡ 華新/電纜', 
    '1609': '⚡ 大亞', '9958': '⚡ 世紀鋼/風電',

    # === 🔋 BBU/電池/被動元件 ===
    '3211': '🔋 順達/BBU', '6121': '🔋 新普/電池', '6558': '🔋 興能高',
    '2327': '🧱 國巨/被動元件', '2492': '🧱 華新科', 

    # === 🔗 連接器 ===
    '3533': '🔗 嘉澤/CPU插槽', '3217': '🔗 優群', '3023': '🔗 信邦', '3605': '🔗 宏致',

    # === 💰 金融海嘯 (金控/銀行) ===
    '2881': '💰 富邦金', '2882': '💰 國泰金', '2891': '💰 中信金', '2886': '💰 兆豐金',
    '2884': '💰 玉山金', '2885': '💰 元大金', '2883': '💰 開發金', '2892': '💰 第一金',
    '2880': '💰 華南金', '2890': '💰 永豐金', '5880': '💰 合庫金', '2887': '💰 台新金',

    # === 🚢 航運/傳產/集團 ===
    '2603': '🚢 長榮/貨櫃', '2609': '🚢 陽明', '2615': '🚢 萬海', 
    '2618': '✈️ 長榮航', '2610': '✈️ 華航', '2637': '🚢 慧洋/散裝',
    '1101': '🏗️ 台泥', '1102': '🏗️ 亞泥', '2002': '🏗️ 中鋼', 
    '1301': '🛢️ 台塑', '1303': '🛢️ 南亞', '1326': '🛢️ 台化', '6505': '🛢️ 台塑化',
    '2207': '🚗 和泰車', '2201': '🚗 裕隆', '9904': '👟 寶成', '9910': '👟 豐泰',
    
    # === 🍎 光學/手機/消費電 ===
    '3008': '🍎 大立光/鏡頭', '3406': '🍎 玉晶光', '2474': '🍎 可成',
    '2409': '📺 友達', '3481': '📺 群創', '4938': '💻 和碩'
}

# --- 4. 備用方案：Yahoo 奇摩股市爬蟲 ---
# 當股票不在上面的 Top 500 名單時，程式會自動去爬 Yahoo 奇摩股市的分類
@st.cache_data(ttl=86400)
def fetch_tw_sector(stock_code):
    try:
        url = f"https://tw.stock.yahoo.com/quote/{stock_code}" 
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers, timeout=3)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            # 抓取 Yahoo 產業連結特徵
            links = soup.find_all('a')
            for link in links:
                href = link.get('href', '')
                if '/h/category/' in href:
                    sector_name = link.text.strip()
                    return f"🌍 {sector_name}" # 加個地球符號代表是網路上抓的
        return None
    except:
        return None

def get_detailed_industry(row):
    code = str(row['股票代號']).strip()
    name = str(row['股票名稱']).strip()
    
    # 1. 優先查 Top 500 字典 (最精準的新聞題材)
    if code in STOCK_SECTOR_MAP:
        return STOCK_SECTOR_MAP[code]
    
    # 2. 關鍵字補漏 (處理明顯的類股)
    if '金' in name and any(x in name for x in ['銀', '控', '保', '壽']): return '💰 金融保險'
    if '電' in name and '台' in name: return '⚡ 公用/電信'
    if any(x in name for x in ['ETF', '債', '富邦', '元大', '國泰']): return '📊 ETF/基金'

    # 3. 最後一招：連網去問 Yahoo
    online_sector = fetch_tw_sector(code)
    if online_sector:
        return online_sector
        
    return '📦 其他'

# --- 5. 狀態判斷與樣式 ---
def determine_status(row):
    if row['持有股數_old'] == 0 and row['持有股數'] > 0: return "✨ 新進"
    elif row['持有股數_old'] > 0 and row['持有股數'] == 0: return "❌ 剔除"
    elif row['股數變化_日'] > 0: return "📈 加碼"
    elif row['股數變化_日'] < 0: return "📉 減碼"
    else: return "持平"

def highlight_status(val):
    if '新進' in val: return 'color: #d63384; font-weight: bold; background-color: #fce4ec;'
    if '剔除' in val: return 'color: #dc3545; font-weight: bold; background-color: #f8d7da;'
    if '加碼' in val: return 'color: #198754; font-weight: bold;'
    if '減碼' in val: return 'color: #0d6efd;'
    return 'color: #6c757d;'

def color_change_text(val):
    if isinstance(val, (int, float)):
        return 'color: #198754' if val > 0 else 'color: #dc3545' if val < 0 else 'color: #adb5bd'
    return ''

# --- 6. 主程式 ---
def show_etf_dashboard(etf_code, etf_name):
    st.markdown("---")
    st.subheader(f"📊 {etf_code} {etf_name}")
    
    csv_path = f'data/{etf_code}_history.csv'
    raw_df = load_data(csv_path)
    if raw_df is None or raw_df.empty:
        st.warning(f"⚠️ {etf_code} 尚無資料")
        return

    df = clean_data(raw_df)
    all_dates = df['DateStr'].unique()
    if len(all_dates) == 0: return

    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        date_now_str = st.selectbox(f"基準日期", all_dates, index=0, key=f"d1_{etf_code}")
    
    idx_now = list(all_dates).index(date_now_str)
    idx_prev = idx_now + 1 if idx_now + 1 < len(all_dates) else idx_now
    idx_week = idx_now + 5 if idx_now + 5 < len(all_dates) else len(all_dates) - 1
    
    with c3:
        st.caption(f"📅 比較區間： vs 前日 ({all_dates[idx_prev]}) | vs 上週 ({all_dates[idx_week]})")
    
    try:
        df_now = df[df['DateStr'] == date_now_str].copy().set_index('股票代號')
        df_prev = df[df['DateStr'] == all_dates[idx_prev]].copy().set_index('股票代號')
        df_week = df[df['DateStr'] == all_dates[idx_week]].copy().set_index('股票代號')
        
        merged = df_now[['股票名稱', '持有股數', '權重']].join(
            df_prev[['持有股數']], lsuffix='', rsuffix='_old', how='outer'
        ).fillna(0)
        
        merged = merged.join(df_week[['持有股數']], rsuffix='_week', how='outer').fillna(0)
        merged['股數變化_日'] = merged['持有股數'] - merged['持有股數_old']
        merged['股數變化_週'] = merged['持有股數'] - merged['持有股數_week']
        
        all_names = pd.concat([df_now['股票名稱'], df_prev['股票名稱']])
        name_map = all_names[~all_names.index.duplicated()].to_dict()
        merged['股票名稱'] = merged.index.map(lambda x: name_map.get(x, x))
        
        merged = merged.reset_index()
        # 執行究極分類
        merged['產業'] = merged.apply(get_detailed_industry, axis=1)

    except Exception as e:
        st.error(f"資料處理錯誤: {e}")
        return

    # =========================================================================
    # KPI 儀表板 (新增本日加碼王)
    # =========================================================================
    
    top_buy_day = merged.sort_values('股數變化_日', ascending=False).iloc[0]
    buy_val_day = top_buy_day['股數變化_日']
    
    top_buy_week = merged.sort_values('股數變化_週', ascending=False).iloc[0]
    buy_val_week = top_buy_week['股數變化_週']

    day_act_count = len(merged[merged['股數變化_日'] != 0])
    
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("📊 總持股數", f"{len(df_now)} 檔")
    
    if buy_val_day > 0:
        k2.metric("👑 本日加碼王", f"{top_buy_day['股票名稱']}", f"+{int(buy_val_day):,} 股")
    else:
        k2.metric("👑 本日加碼王", "無", "0")
        
    if buy_val_week > 0:
        k3.metric("🏆 本週加碼王", f"{top_buy_week['股票名稱']}", f"+{int(buy_val_week):,} 股")
    else:
        k3.metric("🏆 本週加碼王", "無", "0")

    k4.metric("⚡ 今日異動", f"{day_act_count} 檔")
    k5.metric("💰 最大持倉", f"{merged.sort_values('權重', ascending=False).iloc[0]['股票名稱']}")

    # =========================================================================
    # 🔥 1. 今日異動速覽區 (置頂顯示，一眼看穿)
    # =========================================================================
    st.markdown("### 🔥 今日焦點操作 (Daily Highlights)")
    
    action_df = merged[merged['股數變化_日'] != 0].copy()
    
    if not action_df.empty:
        action_df['狀態'] = action_df.apply(determine_status, axis=1)
        action_df['abs_change'] = action_df['股數變化_日'].abs()
        # 排序：狀態優先 (新進/剔除) -> 變動量大小
        action_df = action_df.sort_values(['狀態', 'abs_change'], ascending=[False, False])
        
        styled_action = action_df.style\
            .map(highlight_status, subset=['狀態'])\
            .map(color_change_text, subset=['股數變化_日', '股數變化_週'])
            
        st.dataframe(
            styled_action,
            column_order=['狀態', '股票代號', '股票名稱', '產業', '股數變化_日', '持有股數', '權重'],
            hide_index=True,
            use_container_width=True,
            column_config={
                "狀態": st.column_config.TextColumn("動態", width="small"),
                "股票代號": st.column_config.TextColumn("代號", width="small"),
                "股票名稱": st.column_config.TextColumn("名稱"),
                "產業": st.column_config.TextColumn("題材 (地球=聯網查詢)"),
                "股數變化_日": st.column_config.NumberColumn("今日增減", format="%+d"),
                "持有股數": st.column_config.NumberColumn("目前庫存", format="%d"),
                "權重": st.column_config.NumberColumn("權重", format="%.2f%%")
            }
        )
    else:
        st.info("😴 今日經理人躺平，無任何買賣操作")

    # =========================================================================
    # 📊 2. 圖表分析區
    # =========================================================================
    col_chart1, col_chart2 = st.columns(2)
    with col_chart1:
        st.caption("🏭 持股題材分佈 (Top 500 分類)")
        industry_counts = merged[merged['持有股數']>0]['產業'].value_counts()
        if not industry_counts.empty:
            fig1 = px.pie(
                values=industry_counts.values, names=industry_counts.index, hole=0.5,
                color_discrete_sequence=px.colors.qualitative.Prism # 使用鮮明配色
            )
            fig1.update_traces(textinfo='percent+label', textposition='inside')
            fig1.update_layout(showlegend=False, margin=dict(l=10, r=10, t=10, b=10), height=300)
            st.plotly_chart(fig1, use_container_width=True)

    with col_chart2:
        st.caption("📅 近一週動作 (Top 10)")
        week_movers = merged[merged['股數變化_週'].abs() > 0].sort_values('股數變化_週', ascending=False).head(10)
        if not week_movers.empty:
            fig2 = go.Figure()
            fig2.add_trace(go.Bar(
                y=week_movers['股票名稱'], x=week_movers['股數變化_週'], orientation='h',
                marker=dict(color=week_movers['股數變化_週'], colorscale='Tealrose', cmid=0)
            ))
            fig2.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=10), xaxis_title=None)
            st.plotly_chart(fig2, use_container_width=True)

    # =========================================================================
    # 📋 3. 完整持股清單 (折疊隱藏，按新聞題材分類)
    # =========================================================================
    with st.expander("📂 查看完整持股清單 (按新聞題材分類)", expanded=False):
        
        table_df = merged[(merged['持有股數'] > 0) | (merged['持有股數_old'] > 0)].copy()
        table_df['狀態'] = table_df.apply(determine_status, axis=1)

        trend_col = []
        for code in table_df['股票代號']:
            trend_col.append(get_trend_data(df, code))
        table_df['歷史走勢'] = trend_col

        # 計算權重排序
        industry_stats = table_df.groupby('產業')['權重'].sum().sort_values(ascending=False)
        
        for industry_name, total_weight in industry_stats.items():
            sub_df = table_df[table_df['產業'] == industry_name].copy()
            sub_df = sub_df.sort_values('權重', ascending=False)
            
            # 使用 Markdown 製作漂亮的分類標題
            st.markdown(f"""
            <div class='industry-header'>
                {industry_name} <span style='font-size:0.9rem; color:#666; font-weight:normal;'>(佔比: {total_weight:.2f}%)</span>
            </div>
            """, unsafe_allow_html=True)
            
            styled_sub_df = sub_df.style\
                .map(highlight_status, subset=['狀態'])\
                .map(color_change_text, subset=['股數變化_日', '股數變化_週'])
            
            st.dataframe(
                styled_sub_df,
                column_order=['狀態', '股票代號', '股票名稱', '權重', '股數變化_日', '股數變化_週', '持有股數', '歷史走勢'],
                hide_index=True,
                use_container_width=True,
                column_config={
                    "狀態": st.column_config.TextColumn("動態", width="small"),
                    "股票代號": st.column_config.TextColumn("代號", width="small"),
                    "股票名稱": st.column_config.TextColumn("名稱"),
                    "權重": st.column_config.ProgressColumn("權重", format="%.2f%%", min_value=0, max_value=10),
                    "股數變化_日": st.column_config.NumberColumn("日增減", format="%+d"),
                    "股數變化_週": st.column_config.NumberColumn("週增減", format="%+d"),
                    "持有股數": st.column_config.NumberColumn("庫存", format="%d"),
                    "歷史走勢": st.column_config.LineChartColumn("30日趨勢", width="medium")
                }
            )

# 執行
show_etf_dashboard("00981A", "主動統一台股增長")
show_etf_dashboard("00991A", "主動復華未來50")
