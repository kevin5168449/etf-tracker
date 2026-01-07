import streamlit as st
import pandas as pd
import os
import plotly.express as px
import plotly.graph_objects as go
import requests
from bs4 import BeautifulSoup

# --- 頁面設定 ---
st.set_page_config(page_title="ETF 戰情室 Pro (完整版)", page_icon="🦁", layout="wide")

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
    /* 讓現金水位的卡片特別一點 */
    .cash-card {
        background-color: #e3f2fd;
        padding: 10px;
        border-radius: 8px;
        border: 1px solid #90caf9;
        text-align: center;
    }
</style>
""", unsafe_allow_html=True)

st.title("🦁 2026 主動式 ETF 戰情室 (現金水位 + 產業流向版)")

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

# --- 2. 簡約分類系統 ---
CORE_SECTOR_MAP = {
    '2330': '半導體業', '2303': '半導體業', '2454': '半導體業', '3711': '半導體業',
    '3443': '半導體業', '3661': '半導體業', '3034': '半導體業', '2379': '半導體業',
    '2317': '電腦週邊', '2382': '電腦週邊', '3231': '電腦週邊', '2356': '電腦週邊',
    '3017': '電腦週邊', '3324': '電腦週邊', '2376': '電腦週邊', '6669': '電腦週邊',
    '2301': '電腦週邊', '3217': '電腦週邊', '3533': '電子零組件', '2308': '電子零組件',
    '2345': '通信網路', '3045': '通信網路', '2412': '通信網路', '4904': '通信網路',
    '2881': '金融保險', '2882': '金融保險', '2891': '金融保險', '2886': '金融保險',
    '2884': '金融保險', '2892': '金融保險', '5880': '金融保險',
    '2603': '航運業', '2609': '航運業', '2615': '航運業', '2618': '航運業',
    '1513': '電機機械', '1519': '電機機械', '1605': '電器電纜', '2002': '鋼鐵工業'
}

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

def get_industry(row):
    code = str(row['股票代號']).strip()
    if code in CORE_SECTOR_MAP: return CORE_SECTOR_MAP[code]
    online_sector = fetch_yahoo_sector(code)
    if online_sector: return f"{online_sector}"
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

    # --- KPI 計算 (含現金水位) ---
    top_buy_day = merged.sort_values('股數變化_日', ascending=False).iloc[0]
    buy_val_day = top_buy_day['股數變化_日']
    
    top_buy_week = merged.sort_values('股數變化_週', ascending=False).iloc[0]
    buy_val_week = top_buy_week['股數變化_週']
    
    day_act_count = len(merged[merged['股數變化_日'] != 0])
    
    # 計算持股總權重 (剩餘的假設為現金/期貨)
    total_stock_weight = merged['權重'].sum()
    cash_position = 100.0 - total_stock_weight
    
    # 顯示 KPI (5 欄)
    k1, k2, k3, k4, k5 = st.columns(5)
    
    # 1. 現金水位 (如果 <0 代表資料有誤或槓桿，這裡設底限為0)
    cash_display = max(0.0, cash_position)
    k1.metric("💰 現金/避險水位", f"{cash_display:.2f}%", delta=None) # 不顯示漲跌，只顯示水位
    
    # 2. 本日加碼
    if buy_val_day > 0:
        k2.metric("👑 本日加碼", f"{top_buy_day['股票名稱']}", f"+{int(buy_val_day):,}")
    else:
        k2.metric("👑 本日加碼", "無", "0")
    
    # 3. 本週加碼
    if buy_val_week > 0:
        k3.metric("🏆 本週加碼", f"{top_buy_week['股票名稱']}", f"+{int(buy_val_week):,}")
    else:
        k3.metric("🏆 本週加碼", "無", "0")

    # 4. 異動數
    k4.metric("⚡ 今日異動", f"{day_act_count}")
    
    # 5. 持股數
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
                "權重": st.column_config.NumberColumn("權重", format="%.2f%%")
            }
        )
    else:
        st.info("😴 今日經理人按兵不動 (無買賣紀錄)")

    # --- Section 2: 戰情圖表區 (熱力圖 + 產業流向) ---
    col1, col2 = st.columns([2, 1]) # 左邊寬一點給熱力圖
    
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
        # 計算各產業的本週股數變化總和 (簡單估算)
        # 注意：嚴格來說應該算金額，但這裡用股數變化做近似趨勢
        sector_flow = merged.groupby('產業')['股數變化_週'].sum().sort_values(ascending=False)
        # 只取變動最大的前 5 名和後 5 名
        top_sectors = pd.concat([sector_flow.head(3), sector_flow.tail(3)])
        
        if not top_sectors.empty:
            # 顏色：大於0紅，小於0綠
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
                xaxis_title="股數增減 (約略)",
                yaxis=dict(autorange="reversed") # 讓漲的排上面
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
