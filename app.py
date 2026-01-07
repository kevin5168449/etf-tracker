import streamlit as st
import pandas as pd
import os
import plotly.express as px
import plotly.graph_objects as go
import requests
from bs4 import BeautifulSoup

# --- 頁面設定 ---
st.set_page_config(page_title="ETF 戰情室 Lite", page_icon="📉", layout="wide")

# --- CSS 極簡優化 ---
st.markdown("""
<style>
    .stDataFrame { font-size: 1.05rem; }
    div[data-testid="stMetricValue"] {
        font-size: 1.5rem !important;
        font-weight: 700;
        color: #2c3e50;
    }
    /* 簡約的分類標題 */
    .industry-header {
        font-size: 1.1rem;
        font-weight: 600;
        color: #555;
        background-color: #f8f9fa;
        padding: 8px 12px;
        border-left: 4px solid #6c757d; /* 灰色系，低調專業 */
        border-radius: 4px;
        margin-top: 15px;
        margin-bottom: 5px;
    }
</style>
""", unsafe_allow_html=True)

st.title("📉 2026 主動式 ETF 戰情室 (簡約版)")

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

# --- 2. 簡約分類系統 (本地核心名單 + 網路查詢) ---

# 只列出最核心、最常見的題材，剩下的交給網路查，保持程式碼乾淨
CORE_SECTOR_MAP = {
    # 半導體
    '2330': '半導體業', '2303': '半導體業', '2454': '半導體業', '3711': '半導體業',
    '3443': '半導體業', '3661': '半導體業', '3034': '半導體業', '2379': '半導體業',
    # 電腦週邊 (AI 伺服器/散熱)
    '2317': '電腦週邊', '2382': '電腦週邊', '3231': '電腦週邊', '2356': '電腦週邊',
    '3017': '電腦週邊', '3324': '電腦週邊', '2376': '電腦週邊', '6669': '電腦週邊',
    '2301': '電腦週邊', '3217': '電腦週邊', '3533': '電子零組件', '2308': '電子零組件',
    # 網通
    '2345': '通信網路', '3045': '通信網路', '2412': '通信網路', '4904': '通信網路',
    # 金融
    '2881': '金融保險', '2882': '金融保險', '2891': '金融保險', '2886': '金融保險',
    '2884': '金融保險', '2892': '金融保險', '5880': '金融保險',
    # 傳產
    '2603': '航運業', '2609': '航運業', '2615': '航運業', '2618': '航運業',
    '1513': '電機機械', '1519': '電機機械', '1605': '電器電纜', '2002': '鋼鐵工業'
}

@st.cache_data(ttl=86400)
def fetch_yahoo_sector(stock_code):
    """
    簡單的爬蟲：去 Yahoo 奇摩股市抓分類
    """
    try:
        url = f"https://tw.stock.yahoo.com/quote/{stock_code}" 
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers, timeout=2)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            # 抓取 Yahoo 頁面特徵 (連結包含 /category/)
            links = soup.find_all('a')
            for link in links:
                href = link.get('href', '')
                if '/h/category/' in href:
                    return link.text.strip() # 直接回傳中文分類，如 "半導體業"
        return None
    except:
        return None

def get_industry(row):
    code = str(row['股票代號']).strip()
    
    # 1. 先查本地核心名單 (速度快)
    if code in CORE_SECTOR_MAP:
        return CORE_SECTOR_MAP[code]
    
    # 2. 查不到就去網路上問 Yahoo (確保準確)
    online_sector = fetch_yahoo_sector(code)
    if online_sector:
        return f"{online_sector}" # 加個星號標記是網路上抓的
        
    return '其他'

# --- 3. 狀態判斷 ---
def determine_status(row):
    if row['持有股數_old'] == 0 and row['持有股數'] > 0: return "✨ 新進"
    elif row['持有股數_old'] > 0 and row['持有股數'] == 0: return "❌ 剔除"
    elif row['股數變化_日'] > 0: return "📈 加碼"
    elif row['股數變化_日'] < 0: return "📉 減碼"
    else: return "持平"

def highlight_status(val):
    if '新進' in val: return 'color: #d63384; font-weight: bold;'
    if '剔除' in val: return 'color: #dc3545; font-weight: bold;'
    if '加碼' in val: return 'color: #198754; font-weight: bold;'
    if '減碼' in val: return 'color: #0d6efd;'
    return 'color: #999;'

def color_change_text(val):
    if isinstance(val, (int, float)):
        return 'color: #198754' if val > 0 else 'color: #dc3545' if val < 0 else 'color: #ccc'
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

    # 日期選擇
    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        date_now_str = st.selectbox(f"基準日期", all_dates, index=0, key=f"d1_{etf_code}")
    
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
        # ★ 執行分類 (簡單版)
        merged['產業'] = merged.apply(get_industry, axis=1)

    except Exception as e:
        st.error(f"Error: {e}")
        return

    # --- KPI ---
    top_buy_day = merged.sort_values('股數變化_日', ascending=False).iloc[0]
    buy_val_day = top_buy_day['股數變化_日']
    
    top_buy_week = merged.sort_values('股數變化_週', ascending=False).iloc[0]
    buy_val_week = top_buy_week['股數變化_週']
    
    day_act_count = len(merged[merged['股數變化_日'] != 0])
    
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("持股數", f"{len(df_now)}")
    
    if buy_val_day > 0:
        k2.metric("👑 本日加碼", f"{top_buy_day['股票名稱']}", f"+{int(buy_val_day):,}")
    else:
        k2.metric("👑 本日加碼", "無", "0")
        
    if buy_val_week > 0:
        k3.metric("🏆 本週加碼", f"{top_buy_week['股票名稱']}", f"+{int(buy_val_week):,}")
    else:
        k3.metric("🏆 本週加碼", "無", "0")

    k4.metric("⚡ 今日異動", f"{day_act_count}")
    k5.metric("💰 最大持倉", f"{merged.sort_values('權重', ascending=False).iloc[0]['股票名稱']}")

    # --- Section 1: 今日異動 (置頂，一眼看) ---
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
                "權重": st.column_config.NumberColumn("權重", format="%.2f%%")
            }
        )
    else:
        st.info("😴 今日無動作")

    # --- Section 2: 圖表 ---
    col1, col2 = st.columns(2)
    with col1:
        st.caption("持股產業分佈")
        ind_counts = merged[merged['持有股數']>0]['產業'].value_counts()
        if not ind_counts.empty:
            fig = px.pie(
                values=ind_counts.values, names=ind_counts.index, hole=0.5,
                color_discrete_sequence=px.colors.qualitative.Pastel
            )
            fig.update_traces(textinfo='percent+label', textposition='inside')
            fig.update_layout(showlegend=False, margin=dict(t=10, b=10, l=10, r=10), height=250)
            st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.caption("近週動作排行 (Top 10)")
        week_top = merged[merged['股數變化_週'].abs() > 0].sort_values('股數變化_週', ascending=False).head(10)
        if not week_top.empty:
            fig = go.Figure()
            fig.add_trace(go.Bar(
                y=week_top['股票名稱'], x=week_top['股數變化_週'], orientation='h',
                marker=dict(color=week_top['股數變化_週'], colorscale='Tealrose', cmid=0)
            ))
            fig.update_layout(height=250, margin=dict(t=10, b=10, l=0, r=0), xaxis_title=None)
            st.plotly_chart(fig, use_container_width=True)

    # --- Section 3: 完整清單 (折疊) ---
    with st.expander("📂 完整持股列表 (依產業分類)", expanded=False):
        table_df = merged[(merged['持有股數'] > 0) | (merged['持有股數_old'] > 0)].copy()
        table_df['狀態'] = table_df.apply(determine_status, axis=1)

        trend_col = []
        for code in table_df['股票代號']:
            trend_col.append(get_trend_data(df, code))
        table_df['歷史走勢'] = trend_col

        ind_stats = table_df.groupby('產業')['權重'].sum().sort_values(ascending=False)
        
        for ind_name, total_w in ind_stats.items():
            sub = table_df[table_df['產業'] == ind_name].copy()
            sub = sub.sort_values('權重', ascending=False)
            
            st.markdown(f"<div class='industry-header'>{ind_name} ({total_w:.2f}%)</div>", unsafe_allow_html=True)
            
            styled_sub = sub.style\
                .map(highlight_status, subset=['狀態'])\
                .map(color_change_text, subset=['股數變化_日', '股數變化_週'])
            
            st.dataframe(
                styled_sub,
                column_order=['狀態', '股票代號', '股票名稱', '權重', '股數變化_日', '股數變化_週', '持有股數', '歷史走勢'],
                hide_index=True,
                use_container_width=True,
                column_config={
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
