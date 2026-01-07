import streamlit as st
import pandas as pd
import os
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(page_title="ETF 戰情室 5.2", page_icon="🚀", layout="wide")

# CSS 優化視覺
st.markdown("""
<style>
    .metric-card {
        background-color: #262730;
        padding: 15px;
        border-radius: 10px;
        border: 1px solid #41424C;
    }
    .stDataFrame { font-size: 1.1rem; }
    div[data-testid="stMetricValue"] { font-size: 1.4rem !important; }
</style>
""", unsafe_allow_html=True)

st.title("🚀 2026 主動式 ETF 經理人操盤追蹤 (題材細分版)")

# --- 資料讀取與修復 ---
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

# --- 核心邏輯：計算趨勢線數據 ---
def get_trend_data(full_df, stock_code):
    try:
        history = full_df[full_df['股票代號'] == stock_code].sort_values('Date', ascending=True)
        data = history['權重'].tail(30).tolist()
        if not data: return [0.0, 0.0]
        if all(x == 0 for x in data): return [0.0, 0.0]
        return data
    except:
        return [0.0, 0.0]

# --- ★★★ 究極細分：台股熱門題材字典 ★★★ ---
STOCK_SECTOR_MAP = {
    # === 🌬️ 散熱族群 ===
    '3017': '🌬️ 散熱', '3324': '🌬️ 散熱', '3338': '🌬️ 散熱', '2421': '🌬️ 散熱', 
    '3013': '🌬️ 散熱', '8996': '🌬️ 散熱', '6275': '🌬️ 散熱', '6230': '🌬️ 散熱',
    
    # === 📦 CoWoS / 先進封裝 / 設備 ===
    '3131': '📦 CoWoS設備', '3583': '📦 CoWoS設備', '6187': '📦 CoWoS設備', '6640': '📦 CoWoS設備',
    '3711': '📦 封測代工', '2449': '📦 封測代工', '6239': '📦 封測代工', '8150': '📦 封測代工',
    '6515': '📦 封測材料', '5443': '📦 封測材料',
    
    # === 🔦 CPO / 矽光子 / 網通 ===
    '2345': '🔦 CPO/網通', '4979': '🔦 CPO/網通', '3450': '🔦 CPO/矽光子', '3363': '🔦 CPO/矽光子',
    '4908': '🔦 CPO/矽光子', '3081': '🔦 CPO/矽光子', '3234': '🔦 CPO/網通', '6442': '🔦 CPO/網通',
    '5388': '🔦 CPO/網通', '3704': '🔦 CPO/網通',
    
    # === 🧠 矽智財 (IP) / ASIC ===
    '3661': '🧠 矽智財IP', '3443': '🧠 矽智財IP', '3035': '🧠 矽智財IP', '6531': '🧠 矽智財IP',
    '3529': '🧠 矽智財IP', '6643': '🧠 矽智財IP', '5269': '🧠 高速傳輸', '4966': '🧠 高速傳輸',
    
    # === 🤖 AI 伺服器 / 組裝 (ODM) ===
    '2382': '🤖 AI伺服器', '3231': '🤖 AI伺服器', '2356': '🤖 AI伺服器', '6669': '🤖 AI伺服器',
    '2376': '🤖 AI伺服器', '2317': '🤖 鴻海家族', '2354': '🤖 鴻海家族', '2301': '🤖 AI伺服器',
    
    # === 💾 記憶體 ===
    '8299': '💾 記憶體', '2408': '💾 記憶體', '2344': '💾 記憶體', '3260': '💾 記憶體', 
    '2337': '💾 記憶體', '2451': '💾 記憶體', '4967': '💾 記憶體',
    
    # === 💎 晶圓代工 ===
    '2330': '💎 晶圓代工', '2303': '💎 晶圓代工', '5347': '💎 晶圓代工', '3707': '💎 晶圓代工',
    
    # === 🧱 PCB / CCL (銅箔基板) ===
    '2383': '🧱 PCB/CCL', '6213': '🧱 PCB/CCL', '6274': '🧱 PCB/CCL', '2368': '🧱 PCB/CCL',
    '3037': '🧱 PCB/CCL', '2313': '🧱 PCB/CCL', '3044': '🧱 PCB/CCL',
    
    # === ⚡ 重電 / 綠能 / 電線電纜 ===
    '1513': '⚡ 重電綠能', '1519': '⚡ 重電綠能', '1503': '⚡ 重電綠能', '1504': '⚡ 重電綠能',
    '1609': '⚡ 電線電纜', '1605': '⚡ 電線電纜', '9958': '⚡ 綠能風電',
    
    # === 🚢 航運 ===
    '2603': '🚢 貨櫃航運', '2609': '🚢 貨櫃航運', '2615': '🚢 貨櫃航運', 
    '2618': '✈️ 航空', '2610': '✈️ 航空', '2637': '🚢 散裝航運',
    
    # === 💰 金融 ===
    '2881': '💰 金融壽險', '2882': '💰 金融壽險', '2886': '💰 金融', '2891': '💰 金融',
    '2884': '💰 金融', '2885': '💰 金融', '2883': '💰 金融', '2892': '💰 金融',
    
    # === 🧱 傳產 (水泥/鋼鐵/塑膠) ===
    '2002': '🏗️ 鋼鐵', '1101': '🏗️ 水泥', '1301': '🛢️ 塑膠', '1303': '🛢️ 塑膠', '2105': '🚗 輪胎'
}

def get_detailed_industry(row):
    code = str(row['股票代號']).strip()
    name = str(row['股票名稱']).strip()
    
    if code in STOCK_SECTOR_MAP:
        return STOCK_SECTOR_MAP[code]
    
    if '金' in name and '銀' in name: return '💰 金融'
    if '電' in name: return '🔌 其他電子'
    
    return '📦 其他'

# --- 判斷狀態標籤 ---
def determine_status(row):
    if row['持有股數_old'] == 0 and row['持有股數'] > 0:
        return "🔥 新進"
    elif row['持有股數_old'] > 0 and row['持有股數'] == 0:
        return "👋 剔除"
    elif row['股數變化_日'] > 0:
        return "📈 加碼"
    elif row['股數變化_日'] < 0:
        return "📉 減碼"
    else:
        return "➖ 持平"

# --- 色彩樣式 ---
def highlight_status(val):
    if '新進' in val: return 'background-color: #d4edda; color: #155724; font-weight: bold;'
    elif '剔除' in val: return 'background-color: #f8d7da; color: #721c24; font-weight: bold;'
    elif '加碼' in val: return 'color: #28a745; font-weight: bold;'
    elif '減碼' in val: return 'color: #dc3545; font-weight: bold;'
    return ''

def color_change_text(val):
    if isinstance(val, (int, float)):
        color = '#28a745' if val > 0 else '#dc3545' if val < 0 else 'inherit'
        return f'color: {color}'
    return ''

def show_etf_dashboard(etf_code, etf_name):
    st.markdown(f"---")
    st.header(f"📈 {etf_code} {etf_name}")
    
    csv_path = f'data/{etf_code}_history.csv'
    raw_df = load_data(csv_path)
    if raw_df is None or raw_df.empty:
        st.warning(f"⚠️ {etf_code} 尚無資料")
        return

    df = clean_data(raw_df)
    all_dates = df['DateStr'].unique()
    if len(all_dates) == 0: return

    # --- 控制列 ---
    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        date_now_str = st.selectbox(f"基準日期", all_dates, index=0, key=f"d1_{etf_code}")
    
    idx_now = list(all_dates).index(date_now_str)
    idx_prev = idx_now + 1 if idx_now + 1 < len(all_dates) else idx_now
    date_prev_str = all_dates[idx_prev]
    idx_week = idx_now + 5 if idx_now + 5 < len(all_dates) else len(all_dates) - 1
    date_week_str = all_dates[idx_week]

    with c3:
        st.caption(f"📅 比較區間： 日變化 ({date_prev_str}) | 週變化 ({date_week_str})")
    
    # --- 資料準備 ---
    try:
        df_now = df[df['DateStr'] == date_now_str].copy().set_index('股票代號')
        df_prev = df[df['DateStr'] == date_prev_str].copy().set_index('股票代號')
        df_week = df[df['DateStr'] == date_week_str].copy().set_index('股票代號')
        
        merged = df_now[['股票名稱', '持有股數', '權重']].join(
            df_prev[['持有股數']], lsuffix='', rsuffix='_old', how='outer'
        ).fillna(0)
        
        merged = merged.join(df_week[['持有股數']], rsuffix='_week', how='outer').fillna(0)
        
        merged['股數變化_日'] = merged['持有股數'] - merged['持有股數_old']
        merged['股數變化_週'] = merged['持有股數'] - merged['持有股數_week']
        
        # ★★★ 絕對修復：改用字典查表法 (完全棄用 fillna) ★★★
        # 1. 建立字典 (Index: 股票代號 -> Value: 股票名稱)
        all_names = pd.concat([df_now['股票名稱'], df_prev['股票名稱']])
        name_map = all_names[~all_names.index.duplicated()].to_dict()
        
        # 2. 使用 lambda 函式一對一轉換 (如果字典沒查到，就顯示股票代號)
        # 這行保證回傳純文字，絕不會有 Index 錯誤
        merged['股票名稱'] = merged.index.map(lambda x: name_map.get(x, x))
        # ★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★

        merged = merged.reset_index()
        merged['產業'] = merged.apply(get_detailed_industry, axis=1)

    except Exception as e:
        st.error(f"資料處理錯誤: {e}")
        return

    # --- KPI 區塊 ---
    industry_counts = merged[merged['持有股數']>0]['產業'].value_counts()
    top_industry = industry_counts.index[0] if not industry_counts.empty else "無"
    
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("📊 總持股數", f"{len(df_now)} 檔")
    
    top_buy_week = merged.sort_values('股數變化_週', ascending=False).iloc[0]
    if top_buy_week['股數變化_週'] > 0:
        k2.metric("🏆 本週加碼王", f"{top_buy_week['股票名稱']}", f"+{int(top_buy_week['股數變化_週']):,} 股")
    else:
        k2.metric("🏆 本週加碼王", "無", "0")
        
    k3.metric("🏭 最大持倉題材", top_industry, f"{industry_counts.get(top_industry, 0)} 檔")
    
    day_act = merged[merged['股數變化_日'] != 0]
    k4.metric("⚡ 今日異動檔數", f"{len(day_act)} 檔")

    # --- 圖表區 (產業圓餅圖 + 週變化) ---
    col_chart1, col_chart2 = st.columns(2)
    
    with col_chart1:
        st.subheader("🏭 持股題材分佈")
        if not industry_counts.empty:
            fig1 = px.pie(
                values=industry_counts.values, 
                names=industry_counts.index,
                hole=0.4,
                color_discrete_sequence=px.colors.sequential.Turbo
            )
            fig1.update_layout(height=350, margin=dict(l=0, r=0, t=0, b=0))
            st.plotly_chart(fig1, use_container_width=True)
        else:
            st.info("無資料")

    with col_chart2:
        st.subheader("📅 近一週大戶動作 (前10名)")
        week_movers = merged[merged['股數變化_週'].abs() > 0].sort_values('股數變化_週', ascending=False).head(10)
        
        if not week_movers.empty:
            fig2 = go.Figure()
            fig2.add_trace(go.Bar(
                y=week_movers['股票名稱'], x=week_movers['股數變化_週'],
                orientation='h',
                marker=dict(color=week_movers['股數變化_週'], colorscale='RdBu', cmid=0),
                text=week_movers['股數變化_週'].apply(lambda x: f"{x:+,.0f}"),
                textposition='outside'
            ))
            fig2.update_layout(height=350, margin=dict(l=0, r=0, t=0, b=0), xaxis_title="近5日股數增減")
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("累積數據不足，暫無週變化資料")

    # --- 戰略表格 ---
    st.subheader("📋 戰略持股監控 (題材細分版)")
    
    table_df = merged[(merged['持有股數'] > 0) | (merged['持有股數_old'] > 0)].copy()
    table_df['狀態'] = table_df.apply(determine_status, axis=1)

    trend_col = []
    for code in table_df['股票代號']:
        trend_col.append(get_trend_data(df, code))
    table_df['歷史走勢'] = trend_col

    table_df['sort_score'] = table_df['股數變化_週'].abs()
    table_df = table_df.sort_values(['sort_score'], ascending=[False])

    styled_df = table_df.style\
        .map(highlight_status, subset=['狀態'])\
        .map(color_change_text, subset=['股數變化_日', '股數變化_週'])

    st.dataframe(
        styled_df,
        column_order=['狀態', '產業', '股票名稱', '權重', '股數變化_日', '股數變化_週', '持有股數', '歷史走勢'],
        hide_index=True,
        use_container_width=True,
        height=1000, 
        column_config={
            "狀態": st.column_config.TextColumn("動態", width="small"),
            "產業": st.column_config.TextColumn("題材", width="small"),
            "股票名稱": st.column_config.TextColumn("股票名稱"),
            "權重": st.column_config.ProgressColumn("權重", format="%.2f%%", min_value=0, max_value=10),
            "股數變化_日": st.column_config.NumberColumn("日增減", format="%+d"),
            "股數變化_週": st.column_config.NumberColumn("週增減", format="%+d"),
            "持有股數": st.column_config.NumberColumn("庫存", format="%d"),
            "歷史走勢": st.column_config.LineChartColumn("30日趨勢", width="medium")
        }
    )

# 執行顯示
show_etf_dashboard("00981A", "主動統一台股增長")
show_etf_dashboard("00991A", "主動復華未來50")
