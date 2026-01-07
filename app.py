import streamlit as st
import pandas as pd
import os
import plotly.express as px
import plotly.graph_objects as go
import requests
import twstock # 引入 twstock 套件
from bs4 import BeautifulSoup

# --- 頁面設定 ---
st.set_page_config(page_title="ETF 戰情室 Pro (twstock版)", page_icon="🦁", layout="wide")

# --- CSS 優化 ---
st.markdown("""
<style>
    .stDataFrame { font-size: 1.05rem; }
    div[data-testid="stMetricValue"] {
        font-size: 1.5rem !important;
        font-weight: 700;
        color: #2c3e50;
    }
    div[data-testid="stSelectbox"] {
        font-size: 1.1rem;
    }
    /* 產業標籤樣式 */
    .sector-tag {
        font-weight: bold;
        padding: 2px 8px;
        border-radius: 4px;
        background-color: #f1f3f5;
        color: #495057;
        border: 1px solid #ced4da;
    }
</style>
""", unsafe_allow_html=True)

st.title("🦁 2026 主動式 ETF 戰情室 (精準分類版)")

# --- 1. 資料處理核心 ---
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

def get_trend_data(full_df, stock_code):
    try:
        history = full_df[full_df['股票代號'] == stock_code].sort_values('Date', ascending=True)
        data = history['權重'].tail(30).tolist()
        if not data or all(x == 0 for x in data): return [0.0, 0.0]
        return data
    except: return [0.0, 0.0]

# --- 2. 混合分類系統 (熱門題材 + twstock 資料庫) ---

# A. 第一層：手動鎖定的「熱門細分題材」 (針對電子股做細分)
HOT_SECTOR_MAP = {
    # 護國神山
    '2330': '晶圓代工', '2303': '晶圓代工', '5347': '晶圓代工', '6770': '晶圓代工',
    # AI 伺服器 / 組裝
    '2317': 'AI伺服器', '2382': 'AI伺服器', '3231': 'AI伺服器', '2356': 'AI伺服器',
    '6669': 'AI伺服器', '2376': 'AI伺服器', '2301': 'AI伺服器', '2421': 'AI伺服器',
    # 散熱
    '3017': '散熱模組', '3324': '散熱模組', '3653': '散熱模組', '3013': '散熱模組', '8996': '散熱模組',
    # IC設計 / IP
    '2454': 'IC設計', '3034': 'IC設計', '2379': 'IC設計', '3035': 'IP矽智財', 
    '3661': 'IP矽智財', '3443': 'IP矽智財', '3529': 'IP矽智財', '6643': 'IP矽智財',
    # CoWoS / 設備
    '3131': 'CoWoS設備', '3583': 'CoWoS設備', '6187': 'CoWoS設備', '6640': 'CoWoS設備',
    '3711': '封測代工', '2449': '封測代工',
    # 高速傳輸 / CPO
    '3081': '光通訊CPO', '4979': '光通訊CPO', '3450': '光通訊CPO', '4966': '高速傳輸', '5269': '高速傳輸',
    # 網通
    '2345': '網通設備', '3704': '網通設備', '6285': '網通設備', '3045': '電信運營', '2412': '電信運營',
    # 電源 / 重電
    '2308': '電源供應', '1513': '重電綠能', '1519': '重電綠能', '1503': '重電綠能', '1504': '重電綠能',
    # 貨櫃
    '2603': '貨櫃航運', '2609': '貨櫃航運', '2615': '貨櫃航運'
}

# B. 第二層：twstock 官方分類 (處理傳產、金融、標準電子股)
def get_twstock_sector(code):
    try:
        # twstock.codes 是一個巨大的字典，包含所有台股資訊
        if code in twstock.codes:
            # 抓取官方分類，例如 "半導體業", "金融保險業", "水泥工業"
            sector = twstock.codes[code].group
            # 簡化名稱 (去掉"業"或"工業"讓版面好看)
            return sector.replace("工業", "").replace("業", "")
    except:
        pass
    return None

# C. 第三層：Yahoo 網路備援 (處理 twstock 沒更新的新股)
@st.cache_data(ttl=86400)
def fetch_yahoo_sector(stock_code):
    try:
        url = f"https://tw.stock.yahoo.com/quote/{stock_code}" 
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers, timeout=2)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            links = soup.find_all('a')
            for link in links:
                href = link.get('href', '')
                if '/h/category/' in href:
                    return link.text.strip()
        return None
    except: return None

# D. 綜合分類邏輯
def get_industry(row):
    code = str(row['股票代號']).strip()
    
    # 1. 最優先：如果是我們手動定義的熱門股 (AI, CoWoS...)
    if code in HOT_SECTOR_MAP:
        return HOT_SECTOR_MAP[code]
    
    # 2. 次優先：問 twstock 資料庫 (標準分類)
    # 這一步會消滅 99% 的「其他」
    ts_sector = get_twstock_sector(code)
    if ts_sector:
        return ts_sector
    
    # 3. 最後手段：問 Yahoo (針對剛上市的新股)
    online_sector = fetch_yahoo_sector(code)
    if online_sector:
        return f"{online_sector}"
        
    return '其他'

# --- 3. 狀態判斷與顏色邏輯 (台股配色) ---
def determine_status(row):
    if row['持有股數_old'] == 0 and row['持有股數'] > 0: return "✨ 新進"
    elif row['持有股數_old'] > 0 and row['持有股數'] == 0: return "❌ 剔除"
    elif row['股數變化_日'] > 0: return "📈 加碼"
    elif row['股數變化_日'] < 0: return "📉 減碼"
    else: return "持平"

def highlight_status(val):
    if '新進' in val: return 'color: #d32f2f; font-weight: bold;'
    if '剔除' in val: return 'color: #2e7d32; font-weight: bold;'
    if '加碼' in val: return 'color: #d32f2f; font-weight: bold;'
    if '減碼' in val: return 'color: #2e7d32; font-weight: bold;'
    return 'color: #999;'

def color_change_text(val):
    if isinstance(val, (int, float)):
        return 'color: #d32f2f' if val > 0 else 'color: #2e7d32' if val < 0 else 'color: #ccc'
    return ''

# --- 4. 主程式 ---
def show_etf_dashboard(etf_code, etf_name):
    st.markdown("---")
    st.subheader(f"📊 {etf_code} {etf_name}")
    
    csv_path = f'data/{etf_code}_history.csv'
    raw_df = load_data(csv_path)
    if raw_df is None or raw_df.empty:
        st.warning(f"⚠️ {etf_code} 無資料")
        return

    df = clean_data(raw_df)
    all_dates = df['DateStr'].unique()
    if len(all_dates) == 0: return

    # --- 日期選單 ---
    date_options = {}
    for i, date_str in enumerate(all_dates):
        idx_prev = i + 1 if i + 1 < len(all_dates) else i
        idx_week = i + 5 if i + 5 < len(all_dates) else len(all_dates) - 1
        prev_date = all_dates[idx_prev]
        week_date = all_dates[idx_week]
        
        if i == len(all_dates) - 1:
             label = f"{date_str} (初始資料)"
        else:
             label = f"{date_str} (vs 前日 {prev_date[5:]} | vs 上週 {week_date[5:]})"
        date_options[date_str] = label

    date_now_str = st.selectbox(
        "📅 選擇基準日期", 
        options=all_dates, 
        index=0, 
        format_func=lambda x: date_options[x],
        key=f"d1_{etf_code}"
    )
    
    idx_now = list(all_dates).index(date_now_str)
    idx_prev = idx_now + 1 if idx_now + 1 < len(all_dates) else idx_now
    idx_week = idx_now + 5 if idx_now + 5 < len(all_dates) else len(all_dates) - 1
    
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
        merged['產業'] = merged.apply(get_industry, axis=1)

    except Exception as e:
        st.error(f"Error: {e}")
        return

    # --- KPI 計算 ---
    top_buy_day = merged.sort_values('股數變化_日', ascending=False).iloc[0]
    buy_val_day = top_buy_day['股數變化_日']
    
    top_buy_week = merged.sort_values('股數變化_週', ascending=False).iloc[0]
    buy_val_week = top_buy_week['股數變化_週']
    
    day_act_count = len(merged[merged['股數變化_日'] != 0])
    
    total_stock_weight = merged['權重'].sum()
    cash_position = 100.0 - total_stock_weight
    
    k1, k2, k3, k4, k5 = st.columns(5)
    cash_display = max(0.0, cash_position)
    k1.metric("💰 現金/避險水位", f"{cash_display:.2f}%")
    
    if buy_val_day > 0:
        k2.metric("👑 本日加碼", f"{top_buy_day['股票名稱']}", f"+{int(buy_val_day):,}")
    else:
        k2.metric("👑 本日加碼", "無", "0")
        
    if buy_val_week > 0:
        k3.metric("🏆 本週加碼", f"{top_buy_week['股票名稱']}", f"+{int(buy_val_week):,}")
    else:
        k3.metric("🏆 本週加碼", "無", "0")

    k4.metric("⚡ 今日異動", f"{day_act_count}")
    k5.metric("📊 持股檔數", f"{len(df_now)}")

    # --- Section 1: 今日異動 (置頂) ---
    st.markdown("### 🔥 今日焦點異動")
    action_df = merged[merged['股數變化_日'] != 0].copy()
    
    if not action_df.empty:
        action_df['狀態'] = action_df.apply(determine_status, axis=1)
        action_df['abs_change'] = action_df['股數變化_日'].abs()
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
                "股數變化_日": st.column_config.NumberColumn("今日增減", format="%+d"),
                "權重": st.column_config.NumberColumn("權重", format="%.2f%%"),
                "產業": st.column_config.TextColumn("分類")
            }
        )
    else:
        st.info("😴 今日經理人按兵不動")

    # --- Section 2: 戰情圖表區 (熱力圖 + 產業流向) ---
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown("### 🗺️ 資金熱力圖 (面積=權重)")
        treemap_df = merged[merged['權重'] > 0.1].copy() 
        if not treemap_df.empty:
            custom_colors = [[0.0, '#2e7d32'], [0.5, '#ffffff'], [1.0, '#d32f2f']]
            fig_map = px.treemap(
                treemap_df,
                path=['產業', '股票名稱'],
                values='權重',
                color='股數變化_週',
                color_continuous_scale=custom_colors,
                color_continuous_midpoint=0,
                custom_data=['持有股數', '股數變化_週']
            )
            fig_map.update_traces(hovertemplate='<b>%{label}</b><br>權重: %{value:.2f}%<br>週增減: %{customdata[1]:+d}')
            fig_map.update_layout(margin=dict(t=0, l=0, r=0, b=0), height=400)
            st.plotly_chart(fig_map, use_container_width=True)

    with col2:
        st.markdown("### 🌊 本週產業流向")
        sector_flow = merged.groupby('產業')['股數變化_週'].sum().sort_values(ascending=False)
        top_sectors = pd.concat([sector_flow.head(3), sector_flow.tail(3)])
        
        if not top_sectors.empty:
            colors = ['#d32f2f' if v > 0 else '#2e7d32' for v in top_sectors.values]
            fig_bar = go.Figure(go.Bar(
                x=top_sectors.values,
                y=top_sectors.index,
                orientation='h',
                marker_color=colors
            ))
            fig_bar.update_layout(
                margin=dict(t=0, l=0, r=0, b=0), 
                height=400,
                xaxis_title="股數增減 (趨勢)",
                yaxis=dict(autorange="reversed")
            )
            st.plotly_chart(fig_bar, use_container_width=True)

    # --- Section 3: 完整持股列表 (單一大表格) ---
    with st.expander("📂 完整持股清單 (點擊表頭可排序)", expanded=False):
        table_df = merged[(merged['持有股數'] > 0) | (merged['持有股數_old'] > 0)].copy()
        table_df['狀態'] = table_df.apply(determine_status, axis=1)
        
        trend_col = []
        for code in table_df['股票代號']:
            trend_col.append(get_trend_data(df, code))
        table_df['歷史走勢'] = trend_col

        table_df = table_df.sort_values(['產業', '權重'], ascending=[True, False])

        styled_df = table_df.style\
            .map(highlight_status, subset=['狀態'])\
            .map(color_change_text, subset=['股數變化_日', '股數變化_週'])
        
        st.dataframe(
            styled_df,
            column_order=['狀態', '股票代號', '產業', '股票名稱', '權重', '股數變化_日', '股數變化_週', '持有股數', '歷史走勢'],
            hide_index=True,
            use_container_width=True,
            column_config={
                "狀態": st.column_config.TextColumn("動態", width="small"),
                "股票代號": st.column_config.TextColumn("代號", width="small"),
                "產業": st.column_config.TextColumn("類別", width="medium"),
                "股票名稱": st.column_config.TextColumn("名稱"),
                "權重": st.column_config.ProgressColumn("權重", format="%.2f%%", min_value=0, max_value=10),
                "股數變化_日": st.column_config.NumberColumn("日增減", format="%+d"),
                "股數變化_週": st.column_config.NumberColumn("週增減", format="%+d"),
                "持有股數": st.column_config.NumberColumn("庫存", format="%d"),
                "歷史走勢": st.column_config.LineChartColumn("30日趨勢", width="small")
            }
        )

# 執行
show_etf_dashboard("00981A", "主動統一台股增長")
show_etf_dashboard("00991A", "主動復華未來50")
