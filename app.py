import streamlit as st
import pandas as pd
import os
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(page_title="ETF 戰情室 Pro", page_icon="📈", layout="wide")

# CSS 優化：極簡風格、去除多餘邊框
st.markdown("""
<style>
    .metric-card {
        background-color: #f8f9fa;
        padding: 15px;
        border-radius: 8px;
        border: 1px solid #e9ecef;
        color: #333;
    }
    .stDataFrame { font-size: 1.05rem; }
    /* 調整折疊選單的標題樣式 */
    .streamlit-expanderHeader {
        font-weight: 600;
        font-size: 1.1rem;
        background-color: #f1f3f5;
        border-radius: 5px;
    }
</style>
""", unsafe_allow_html=True)

st.title("📈 2026 ETF 經理人操盤追蹤 (專業折疊版)")

# --- 1. 資料讀取與清洗 ---
@st.cache_data(ttl=60)
def load_data(file_path):
    if not os.path.exists(file_path):
        return None
    try:
        return pd.read_csv(file_path, dtype=str, on_bad_lines='skip', engine='python', encoding='utf-8-sig')
    except:
        return None

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
    else:
        return pd.DataFrame()
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
    except:
        return [0.0, 0.0]

# --- 3. 產業精細分類 (去 Emoji 版) ---
STOCK_SECTOR_MAP = {
    # 散熱模組
    '3017': '散熱模組', '3324': '散熱模組', '3653': '散熱模組', '2421': '散熱模組', '3013': '散熱模組',
    # 連接器
    '3533': '連接器', '3217': '連接器', '3023': '連接器',
    # 系統組裝 (鴻海家族/電腦)
    '2317': '系統組裝', '3231': '系統組裝', '2382': '系統組裝', '2356': '系統組裝', '2376': '系統組裝', '6669': '系統組裝',
    # 半導體與IP
    '2330': '半導體製造', '2454': 'IC設計', '3661': '矽智財IP', '3443': '矽智財IP', '3035': '矽智財IP', '3529': '矽智財IP',
    # PCB與相關
    '3044': 'PCB/CCL', '3715': 'PCB/CCL', '2313': 'PCB/CCL', '2383': 'PCB/CCL', '6274': 'PCB/CCL',
    # 設備與封測
    '3583': '半導體設備', '3131': '半導體設備', '3711': '封測代工', '2449': '封測代工',
    # 網通/光通訊
    '3081': '光通訊', '4979': '光通訊', '2345': '網通', '3045': '電信', '4908': '光通訊',
    # 傳產與金融 (避免變成其他)
    '2881': '金融', '2882': '金融', '2884': '金融', '2886': '金融', '2891': '金融',
    '2603': '航運', '2609': '航運', '1513': '重電綠能', '1519': '重電綠能',
    # 特定零組件
    '3211': '電池模組', '3515': '工業電腦', '3008': '光學鏡頭', '2308': '電源供應'
}

def get_detailed_industry(row):
    code = str(row['股票代號']).strip()
    # 優先查表
    if code in STOCK_SECTOR_MAP:
        return STOCK_SECTOR_MAP[code]
    
    # 查無資料時的備用邏輯
    name = str(row['股票名稱']).strip()
    if '金' in name and '銀' in name: return '金融'
    if '電' in name: return '電子零組件'
    return '其他'

# --- 4. 狀態判斷 (文字簡潔化) ---
def determine_status(row):
    if row['持有股數_old'] == 0 and row['持有股數'] > 0: return "新進"
    elif row['持有股數_old'] > 0 and row['持有股數'] == 0: return "剔除"
    elif row['股數變化_日'] > 0: return "加碼"
    elif row['股數變化_日'] < 0: return "減碼"
    else: return "持平"

def highlight_status(val):
    if val == '新進': return 'color: #009933; font-weight: bold;'
    if val == '剔除': return 'color: #cc0000; font-weight: bold;'
    if val == '加碼': return 'color: #009933;'
    if val == '減碼': return 'color: #cc0000;'
    return 'color: #666;'

def color_change_text(val):
    if isinstance(val, (int, float)):
        return 'color: #009933' if val > 0 else 'color: #cc0000' if val < 0 else 'color: #ccc'
    return ''

# --- 5. 主程式邏輯 ---
def show_etf_dashboard(etf_code, etf_name):
    st.markdown("---")
    st.subheader(f"📊 {etf_code} {etf_name}")
    
    # 讀取資料
    csv_path = f'data/{etf_code}_history.csv'
    raw_df = load_data(csv_path)
    if raw_df is None or raw_df.empty:
        st.warning(f"⚠️ {etf_code} 尚無資料")
        return

    df = clean_data(raw_df)
    all_dates = df['DateStr'].unique()
    if len(all_dates) == 0: return

    # 日期選擇
    c1, c2 = st.columns([1, 3])
    with c1:
        date_now_str = st.selectbox(f"基準日期", all_dates, index=0, key=f"d1_{etf_code}")
    
    # 計算比較基準 (前一日 & 上週)
    idx_now = list(all_dates).index(date_now_str)
    idx_prev = idx_now + 1 if idx_now + 1 < len(all_dates) else idx_now
    idx_week = idx_now + 5 if idx_now + 5 < len(all_dates) else len(all_dates) - 1
    
    # 準備資料
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
        
        # 補回名稱
        all_names = pd.concat([df_now['股票名稱'], df_prev['股票名稱']])
        name_map = all_names[~all_names.index.duplicated()].to_dict()
        merged['股票名稱'] = merged.index.map(lambda x: name_map.get(x, x))
        
        merged = merged.reset_index()
        merged['產業'] = merged.apply(get_detailed_industry, axis=1)

    except Exception as e:
        st.error(f"資料處理錯誤: {e}")
        return

    # --- 戰略持股列表 (折疊式) ---
    st.write("##### 📋 持股配置詳情")
    
    table_df = merged[(merged['持有股數'] > 0) | (merged['持有股數_old'] > 0)].copy()
    table_df['狀態'] = table_df.apply(determine_status, axis=1)

    # 取得趨勢線
    trend_col = []
    for code in table_df['股票代號']:
        trend_col.append(get_trend_data(df, code))
    table_df['歷史走勢'] = trend_col

    # 1. 依照產業分組並計算權重
    industry_stats = table_df.groupby('產業')['權重'].sum().sort_values(ascending=False)

    # 2. 迴圈產生折疊區塊
    for industry_name, total_weight in industry_stats.items():
        # 篩選該產業股票
        sub_df = table_df[table_df['產業'] == industry_name].copy()
        sub_df = sub_df.sort_values('權重', ascending=False)
        
        # 樣式設定
        styled_sub_df = sub_df.style\
            .map(highlight_status, subset=['狀態'])\
            .map(color_change_text, subset=['股數變化_日', '股數變化_週'])
        
        # 標題：顯示產業名稱與總權重
        expander_label = f"▼ {industry_name} (佔比: {total_weight:.2f}%)"
        
        # 預設不展開，保持乾淨
        with st.expander(expander_label, expanded=False):
            st.dataframe(
                styled_sub_df,
                column_order=['股票代號', '股票名稱', '權重', '狀態', '股數變化_日', '股數變化_週', '持有股數', '歷史走勢'],
                hide_index=True,
                use_container_width=True,
                column_config={
                    "股票代號": st.column_config.TextColumn("代號", width="small"),
                    "股票名稱": st.column_config.TextColumn("名稱"),
                    "權重": st.column_config.ProgressColumn("權重", format="%.2f%%", min_value=0, max_value=10),
                    "狀態": st.column_config.TextColumn("動態", width="small"),
                    "股數變化_日": st.column_config.NumberColumn("日增減", format="%+d"),
                    "股數變化_週": st.column_config.NumberColumn("週增減", format="%+d"),
                    "持有股數": st.column_config.NumberColumn("庫存", format="%d"),
                    "歷史走勢": st.column_config.LineChartColumn("30日趨勢", width="medium")
                }
            )

# 執行顯示
show_etf_dashboard("00981A", "主動統一台股增長")
show_etf_dashboard("00991A", "主動復華未來50")
