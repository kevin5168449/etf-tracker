import streamlit as st
import pandas as pd
import os
import plotly.express as px
import plotly.graph_objects as go

# --- 頁面基本設定 ---
st.set_page_config(page_title="ETF 戰情室 Pro", page_icon="📈", layout="wide")

# --- CSS 優化：極簡風格、去除多餘邊框、優化折疊標題 ---
st.markdown("""
<style>
    /* 全局字體大小微調 */
    .stDataFrame { font-size: 1.05rem; }
    
    /* 指標卡片樣式 */
    div[data-testid="stMetricValue"] {
        font-size: 1.5rem !important;
        font-weight: 700;
        color: #333;
    }
    
    /* 折疊選單標題優化 */
    .streamlit-expanderHeader {
        font-weight: 600;
        font-size: 1.1rem;
        background-color: #f8f9fa;
        border-radius: 5px;
        border-left: 5px solid #ced4da; /* 預設灰色左邊條 */
    }
    
    /* 讓有異動的折疊標題更明顯 (這部分需配合邏輯動態調整，這裡先做基礎優化) */
    .streamlit-expanderHeader:hover {
        background-color: #e9ecef;
        color: #000;
    }
</style>
""", unsafe_allow_html=True)

st.title("📈 2026 主動式 ETF 經理人操盤追蹤")

# --- 1. 資料讀取與清洗 ---
@st.cache_data(ttl=60)
def load_data(file_path):
    if not os.path.exists(file_path):
        return None
    try:
        # 讀取 CSV，確保所有欄位先視為字串以免格式跑掉
        return pd.read_csv(file_path, dtype=str, on_bad_lines='skip', engine='python', encoding='utf-8-sig')
    except:
        return None

def clean_data(df):
    if df is None or df.empty: return pd.DataFrame()
    
    # 補全缺失欄位
    for col in ['持有股數', '權重']:
        if col not in df.columns: df[col] = '0'
            
    # 數值清洗：移除逗號與百分比符號，轉為浮點數
    for col in ['持有股數', '權重']:
        df[col] = df[col].astype(str).str.replace(',', '').str.replace('%', '')
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
    # 日期處理
    if 'Date' in df.columns:
        df['Date'] = pd.to_datetime(df['Date'])
        df['DateStr'] = df['Date'].dt.strftime('%Y-%m-%d')
    else:
        return pd.DataFrame()
        
    # 去除重複並排序
    df = df.drop_duplicates(subset=['DateStr', '股票代號'], keep='first')
    df = df.sort_values('Date', ascending=False)
    return df

# --- 2. 趨勢線邏輯 (Sparkline) ---
def get_trend_data(full_df, stock_code):
    try:
        history = full_df[full_df['股票代號'] == stock_code].sort_values('Date', ascending=True)
        # 取最近 30 筆權重數據
        data = history['權重'].tail(30).tolist()
        if not data or all(x == 0 for x in data): return [0.0, 0.0]
        return data
    except:
        return [0.0, 0.0]

# --- 3. 產業精細分類對照表 (無 Emoji 版) ---
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
    # 傳產與金融
    '2881': '金融', '2882': '金融', '2884': '金融', '2886': '金融', '2891': '金融',
    '2603': '航運', '2609': '航運', '1513': '重電綠能', '1519': '重電綠能',
    # 特定零組件 (解決"其他"問題)
    '3211': '電池模組', '3515': '工業電腦', '3008': '光學鏡頭', '2308': '電源供應'
}

def get_detailed_industry(row):
    code = str(row['股票代號']).strip()
    # 優先查表
    if code in STOCK_SECTOR_MAP:
        return STOCK_SECTOR_MAP[code]
    
    # 查無資料時的備用關鍵字邏輯
    name = str(row['股票名稱']).strip()
    if '金' in name and '銀' in name: return '金融'
    if '電' in name: return '電子零組件'
    return '其他'

# --- 4. 狀態判斷與樣式 (文字化) ---
def determine_status(row):
    if row['持有股數_old'] == 0 and row['持有股數'] > 0: return "新進"
    elif row['持有股數_old'] > 0 and row['持有股數'] == 0: return "剔除"
    elif row['股數變化_日'] > 0: return "加碼"
    elif row['股數變化_日'] < 0: return "減碼"
    else: return "持平"

def highlight_status(val):
    # 透過 CSS 顏色讓狀態更直觀
    if val == '新進': return 'color: #d63384; font-weight: bold;' # 桃紅色
    if val == '剔除': return 'color: #dc3545; font-weight: bold;' # 紅色
    if val == '加碼': return 'color: #198754; font-weight: bold;' # 綠色
    if val == '減碼': return 'color: #0dcaf0;' # 淺藍色
    return 'color: #6c757d;' # 灰色

def color_change_text(val):
    if isinstance(val, (int, float)):
        return 'color: #198754' if val > 0 else 'color: #dc3545' if val < 0 else 'color: #adb5bd'
    return ''

# --- 5. 核心顯示邏輯 (Show Dashboard) ---
def show_etf_dashboard(etf_code, etf_name):
    st.markdown("---")
    st.subheader(f"📊 {etf_code} {etf_name}")
    
    # 讀取 CSV
    csv_path = f'data/{etf_code}_history.csv'
    raw_df = load_data(csv_path)
    if raw_df is None or raw_df.empty:
        st.warning(f"⚠️ {etf_code} 尚無資料，請確認 data 資料夾內是否有 csv 檔案")
        return

    df = clean_data(raw_df)
    all_dates = df['DateStr'].unique()
    if len(all_dates) == 0: return

    # 日期控制列
    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        date_now_str = st.selectbox(f"基準日期", all_dates, index=0, key=f"d1_{etf_code}")
    
    # 自動計算前一日與上週索引
    idx_now = list(all_dates).index(date_now_str)
    idx_prev = idx_now + 1 if idx_now + 1 < len(all_dates) else idx_now
    idx_week = idx_now + 5 if idx_now + 5 < len(all_dates) else len(all_dates) - 1
    
    with c3:
        st.caption(f"📅 比較區間： vs 前日 ({all_dates[idx_prev]}) | vs 上週 ({all_dates[idx_week]})")
    
    # 資料合併與計算
    try:
        df_now = df[df['DateStr'] == date_now_str].copy().set_index('股票代號')
        df_prev = df[df['DateStr'] == all_dates[idx_prev]].copy().set_index('股票代號')
        df_week = df[df['DateStr'] == all_dates[idx_week]].copy().set_index('股票代號')
        
        # 合併今日與昨日
        merged = df_now[['股票名稱', '持有股數', '權重']].join(
            df_prev[['持有股數']], lsuffix='', rsuffix='_old', how='outer'
        ).fillna(0)
        
        # 合併上週
        merged = merged.join(df_week[['持有股數']], rsuffix='_week', how='outer').fillna(0)
        
        # 計算變化量
        merged['股數變化_日'] = merged['持有股數'] - merged['持有股數_old']
        merged['股數變化_週'] = merged['持有股數'] - merged['持有股數_week']
        
        # 補回名稱 (若今日無庫存，名稱會變成 NaN，需從歷史資料找回)
        all_names = pd.concat([df_now['股票名稱'], df_prev['股票名稱']])
        name_map = all_names[~all_names.index.duplicated()].to_dict()
        merged['股票名稱'] = merged.index.map(lambda x: name_map.get(x, x))
        
        merged = merged.reset_index()
        # 套用產業分類
        merged['產業'] = merged.apply(get_detailed_industry, axis=1)

    except Exception as e:
        st.error(f"資料處理發生錯誤: {e}")
        return

    # --- KPI 顯示 ---
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("📊 總持股數", f"{len(df_now)} 檔")
    
    # 本週買超最多
    top_buy = merged.sort_values('股數變化_週', ascending=False).iloc[0]
    buy_val = top_buy['股數變化_週']
    if buy_val > 0:
        k2.metric("🏆 本週加碼王", f"{top_buy['股票名稱']}", f"+{int(buy_val):,} 股")
    else:
        k2.metric("🏆 本週加碼王", "無", "0")

    # 今日異動檔數
    day_act_count = len(merged[merged['股數變化_日'] != 0])
    k4.metric("⚡ 今日異動", f"{day_act_count} 檔")

    # --- 戰略持股列表 (智慧折疊版) ---
    st.write("##### 📋 持股配置詳情 (異動優先)")
    
    # 1. 準備基礎資料表
    # 過濾掉早已全數賣出且無動作的雜訊
    table_df = merged[(merged['持有股數'] > 0) | (merged['持有股數_old'] > 0)].copy()
    table_df['狀態'] = table_df.apply(determine_status, axis=1)

    # 取得 30日趨勢數據
    trend_col = []
    for code in table_df['股票代號']:
        trend_col.append(get_trend_data(df, code))
    table_df['歷史走勢'] = trend_col

    # 2. 計算各產業總權重，並排序 (大權重產業排上面)
    industry_stats = table_df.groupby('產業')['權重'].sum().sort_values(ascending=False)
    
    # 3. 找出前三大重倉產業 (用於預設展開)
    top_3_industries = industry_stats.head(3).index.tolist()

    # 4. 迴圈生成折疊區塊
    for industry_name, total_weight in industry_stats.items():
        sub_df = table_df[table_df['產業'] == industry_name].copy()
        
        # --- ⚡ 關鍵排序邏輯：讓有動作的股票置頂 ---
        # 建立輔助排序欄位：取變化的絕對值
        sub_df['abs_change'] = sub_df['股數變化_日'].abs()
        # 先排異動大小(大->小)，再排權重(大->小)
        sub_df = sub_df.sort_values(['abs_change', '權重'], ascending=[False, False])
        
        # --- 🔍 偵測該分類內是否有關鍵動作 ---
        has_new = '新進' in sub_df['狀態'].values
        has_removed = '剔除' in sub_df['狀態'].values
        has_increase = '加碼' in sub_df['狀態'].values
        has_decrease = '減碼' in sub_df['狀態'].values
        
        # --- 📂 標題動態生成 (Smart Header) ---
        status_badges = []
        if has_new: status_badges.append("✨新進")
        if has_removed: status_badges.append("❌剔除")
        if has_increase: status_badges.append("📈加碼")
        
        # 如果有徽章，顯示在標題旁
        status_str = f" | {' '.join(status_badges)}" if status_badges else ""
        expander_label = f"▼ {industry_name} (佔比: {total_weight:.2f}%){status_str}"
        
        # --- 🔓 智慧展開邏輯 (Smart Expand) ---
        # 展開條件：是前三大產業 OR 有新進 OR 有剔除 OR 有加減碼
        should_expand = (industry_name in top_3_industries) or has_new or has_removed or has_increase or has_decrease

        with st.expander(expander_label, expanded=should_expand):
            # 樣式映射
            styled_sub_df = sub_df.style\
                .map(highlight_status, subset=['狀態'])\
                .map(color_change_text, subset=['股數變化_日', '股數變化_週'])
            
            # 顯示表格
            st.dataframe(
                styled_sub_df,
                # 定義欄位順序：狀態最左，代號第二
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

# --- 執行儀表板 ---
show_etf_dashboard("00981A", "主動統一台股增長")
show_etf_dashboard("00991A", "主動復華未來50")
