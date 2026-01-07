import streamlit as st
import pandas as pd
import os
import plotly.express as px
import plotly.graph_objects as go

# --- 頁面基本設定 ---
st.set_page_config(page_title="ETF 戰情室 Pro", page_icon="⚡", layout="wide")

# --- CSS 優化 ---
st.markdown("""
<style>
    .stDataFrame { font-size: 1.05rem; }
    div[data-testid="stMetricValue"] {
        font-size: 1.5rem !important;
        font-weight: 700;
        color: #333;
    }
    /* 讓分類標題更明顯 */
    .industry-header {
        font-size: 1.1rem;
        font-weight: 600;
        color: #495057;
        margin-top: 15px;
        margin-bottom: 5px;
        padding-left: 10px;
        border-left: 4px solid #0d6efd;
        background-color: #f1f3f5;
        padding: 5px 10px;
        border-radius: 4px;
    }
    /* 異動區塊的特別樣式 */
    .highlight-box {
        border: 2px solid #ffc107;
        padding: 10px;
        border-radius: 10px;
        background-color: #fff3cd;
        margin-bottom: 20px;
    }
</style>
""", unsafe_allow_html=True)

st.title("⚡ 2026 主動式 ETF 操盤速覽 (異動置頂版)")

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

# --- 3. 究極產業分類表 ---
STOCK_SECTOR_MAP = {
    '2330': '半導體製造', '2303': '半導體製造', '5347': '半導體製造', '6770': '半導體製造',
    '2454': 'IC設計', '3034': 'IC設計', '2379': 'IC設計', '4961': 'IC設計', '3035': 'IC設計',
    '3661': '矽智財IP', '3443': '矽智財IP', '3529': '矽智財IP', '6643': '矽智財IP', '6531': '矽智財IP',
    '2317': '系統組裝', '2382': '系統組裝', '3231': '系統組裝', '2356': '系統組裝', '2376': '系統組裝', '6669': '系統組裝',
    '3017': '散熱模組', '3324': '散熱模組', '3653': '散熱模組', '2421': '散熱模組', '3013': '散熱模組',
    '3131': 'CoWoS設備', '3583': 'CoWoS設備', '6187': 'CoWoS設備', '3711': '封測代工', '2449': '封測代工',
    '3533': '連接器', '3217': '連接器', '2327': '被動元件', '2308': '電源供應', '3211': '電池模組',
    '3037': 'PCB載板', '2383': 'CCL銅箔', '3044': 'PCB硬板', '3715': 'PCB硬板',
    '2345': '網通設備', '3081': '光通訊CPO', '4979': '光通訊CPO', '3045': '電信運營',
    '2603': '貨櫃航運', '2609': '貨櫃航運', '1513': '重電綠能', '1519': '重電綠能',
    '2881': '金控壽險', '2882': '金控壽險', '2884': '金控銀行', '2886': '金控銀行', '2891': '金控銀行',
    '2002': '鋼鐵工業', '1101': '水泥建材', '1301': '塑膠化工', '2395': '工業電腦', '3008': '光學鏡頭'
}

def get_detailed_industry(row):
    code = str(row['股票代號']).strip()
    if code in STOCK_SECTOR_MAP: return STOCK_SECTOR_MAP[code]
    name = str(row['股票名稱']).strip()
    if any(x in name for x in ['金', '銀', '壽', '保']): return '金融保險'
    if any(x in name for x in ['電', '技', '光', '科']): return '其他電子'
    if any(x in name for x in ['運', '航', '海']): return '航運'
    return '其他傳產'

# --- 4. 狀態判斷與樣式 ---
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
    return 'color: #adb5bd;' # 持平用淡灰色，讓重點凸顯

def color_change_text(val):
    if isinstance(val, (int, float)):
        return 'color: #198754' if val > 0 else 'color: #dc3545' if val < 0 else 'color: #adb5bd'
    return ''

# --- 5. 主程式 ---
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
        merged['產業'] = merged.apply(get_detailed_industry, axis=1)

    except Exception as e:
        st.error(f"資料處理錯誤: {e}")
        return

    # KPI 區塊
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("📊 總持股數", f"{len(df_now)} 檔")
    
    top_buy = merged.sort_values('股數變化_週', ascending=False).iloc[0]
    buy_val = top_buy['股數變化_週']
    if buy_val > 0:
        k2.metric("🏆 本週加碼王", f"{top_buy['股票名稱']}", f"+{int(buy_val):,} 股")
    else:
        k2.metric("🏆 本週加碼王", "無", "0")

    day_act_count = len(merged[merged['股數變化_日'] != 0])
    k4.metric("⚡ 今日異動", f"{day_act_count} 檔")

    # =========================================================================
    # 🔥 1. 今日異動速覽區 (Action Dashboard) - 這就是你要的「一眼看出」
    # =========================================================================
    st.markdown("### 🔥 今日焦點操作 (Daily Highlights)")
    
    # 篩選今日有變化的股票
    action_df = merged[merged['股數變化_日'] != 0].copy()
    
    if not action_df.empty:
        # 計算狀態
        action_df['狀態'] = action_df.apply(determine_status, axis=1)
        # 排序：新進/剔除優先，接著是大額加減碼
        action_df['abs_change'] = action_df['股數變化_日'].abs()
        action_df = action_df.sort_values(['狀態', 'abs_change'], ascending=[False, False])
        
        # 樣式設定
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
                "產業": st.column_config.TextColumn("題材"),
                "股數變化_日": st.column_config.NumberColumn("今日增減", format="%+d"),
                "持有股數": st.column_config.NumberColumn("目前庫存", format="%d"),
                "權重": st.column_config.NumberColumn("權重", format="%.2f%%")
            }
        )
    else:
        st.info("😴 今日經理人無任何操作 (本日持股無變動)")

    # =========================================================================
    # 📊 2. 圖表區 (維持)
    # =========================================================================
    col_chart1, col_chart2 = st.columns(2)
    with col_chart1:
        st.caption("🏭 持股題材分佈")
        industry_counts = merged[merged['持有股數']>0]['產業'].value_counts()
        if not industry_counts.empty:
            fig1 = px.pie(
                values=industry_counts.values, names=industry_counts.index, hole=0.5,
                color_discrete_sequence=px.colors.qualitative.Set3 # 柔和配色
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
    # 📋 3. 完整持股清單 (預設折疊，需要才打開)
    # =========================================================================
    with st.expander("📂 查看完整持股清單 (按產業分類)", expanded=False):
        
        table_df = merged[(merged['持有股數'] > 0) | (merged['持有股數_old'] > 0)].copy()
        table_df['狀態'] = table_df.apply(determine_status, axis=1)

        trend_col = []
        for code in table_df['股票代號']:
            trend_col.append(get_trend_data(df, code))
        table_df['歷史走勢'] = trend_col

        industry_stats = table_df.groupby('產業')['權重'].sum().sort_values(ascending=False)
        
        for industry_name, total_weight in industry_stats.items():
            sub_df = table_df[table_df['產業'] == industry_name].copy()
            sub_df = sub_df.sort_values('權重', ascending=False)
            
            st.markdown(f"""
            <div class='industry-header'>
                {industry_name} <span style='font-size:0.9rem; color:#666;'>(佔比: {total_weight:.2f}%)</span>
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
