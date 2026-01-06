import streamlit as st
import pandas as pd
import os
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(page_title="ETF 戰情室 2.0", page_icon="🚀", layout="wide")

# CSS 優化視覺 (讓指標卡更好看)
st.markdown("""
<style>
    .metric-card {
        background-color: #262730;
        padding: 15px;
        border-radius: 10px;
        border: 1px solid #41424C;
    }
    .stDataFrame { font-size: 1.1rem; }
</style>
""", unsafe_allow_html=True)

st.title("🚀 2026 主動式 ETF 經理人操盤追蹤")

# --- 資料讀取與修復 ---
@st.cache_data(ttl=60)
def load_data(file_path):
    if not os.path.exists(file_path):
        return None
    try:
        # ★★★ 關鍵設定：加入 encoding='utf-8-sig' 以便正確讀取我們剛修復的中文檔 ★★★
        return pd.read_csv(file_path, dtype=str, on_bad_lines='skip', engine='python', encoding='utf-8-sig')
    except:
        # 如果失敗，嘗試預設編碼
        try:
            return pd.read_csv(file_path, dtype=str, on_bad_lines='skip', engine='python')
        except:
            return None

def clean_data(df):
    if df is None or df.empty: return pd.DataFrame()
    
    # 補齊欄位
    for col in ['持有股數', '權重']:
        if col not in df.columns: df[col] = '0'
            
    # 清洗數值
    for col in ['持有股數', '權重']:
        df[col] = df[col].astype(str).str.replace(',', '').str.replace('%', '')
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    
    # 日期排序
    if 'Date' in df.columns:
        df['Date'] = pd.to_datetime(df['Date'])
        df = df.sort_values('Date', ascending=False)
        # 轉回字串以便顯示
        df['DateStr'] = df['Date'].dt.strftime('%Y-%m-%d')
    else:
        return pd.DataFrame() # 如果沒日期欄位，視為無效
    
    return df

# --- 核心邏輯：計算趨勢線數據 (Sparklines) ---
def get_trend_data(full_df, stock_code):
    # 抓取該股票過去所有的權重數據 (按日期舊->新排序)
    history = full_df[full_df['股票代號'] == stock_code].sort_values('Date', ascending=True)
    # 為了讓迷你圖好看，只取最近 30 筆
    return history['權重'].tail(30).tolist()

def show_etf_dashboard(etf_code, etf_name):
    st.markdown(f"---")
    st.header(f"📈 {etf_code} {etf_name}")
    
    csv_path = f'data/{etf_code}_history.csv'
    raw_df = load_data(csv_path)

    if raw_df is None or raw_df.empty:
        st.warning(f"⚠️ {etf_code} 尚無資料，請等待爬蟲累積數據。")
        return

    df = clean_data(raw_df)
    if df.empty:
        st.warning(f"⚠️ {etf_code} 資料格式有誤，無法解析。")
        return
    
    # 取得日期選單
    all_dates = df['DateStr'].unique()
    if len(all_dates) == 0: return

    # --- 控制列 ---
    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        date1 = st.selectbox(f"基準日期", all_dates, index=0, key=f"d1_{etf_code}")
    with c2:
        default_idx = 1 if len(all_dates) > 1 else 0
        date2 = st.selectbox(f"比較日期", all_dates, index=default_idx, key=f"d2_{etf_code}")
    
    # --- 資料準備 ---
    df_now = df[df['DateStr'] == date1].copy().set_index('股票代號')
    df_old = df[df['DateStr'] == date2].copy().set_index('股票代號')
    
    # 合併比較 (Outer Join 以便抓出新進/剔除)
    merged = df_now[['股票名稱', '持有股數', '權重']].join(
        df_old[['持有股數', '權重']], lsuffix='', rsuffix='_old', how='outer'
    ).fillna(0)
    
    merged['權重變化'] = merged['權重'] - merged['權重_old']
    merged['股數變化'] = merged['持有股數'] - merged['持有股數_old']
    merged = merged.reset_index() # 股票代號變回欄位
    
    # 補回缺失的股票名稱 (若是剔除股，df_now 沒名稱)
    name_map = pd.concat([df_now['股票名稱'], df_old['股票名稱']]).to_dict()
    merged['股票名稱'] = merged['股票代號'].map(name_map).fillna(merged['股票代號'])

    # --- KPI 指標卡 (戰情室亮點) ---
    # 新進榜: 舊權重為0, 新權重>0
    new_entries = merged[(merged['權重_old'] == 0) & (merged['權重'] > 0)]
    # 剔除: 舊權重>0, 新權重=0
    exited = merged[(merged['權重_old'] > 0) & (merged['權重'] == 0)]
    
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("📊 總持股數", f"{len(df_now)} 檔")
    k2.metric("🔥 本日新進", f"{len(new_entries)} 檔", delta_color="normal")
    k3.metric("👋 本日剔除", f"{len(exited)} 檔", delta_color="inverse")
    
    # 找出最大加碼股
    top_buy = merged.sort_values('權重變化', ascending=False).iloc[0] if not merged.empty else None
    if top_buy is not None and top_buy['權重變化'] > 0:
        k4.metric("👑 加碼王", f"{top_buy['股票名稱']}", f"+{top_buy['權重變化']:.2f}%")
    else:
        k4.metric("👑 加碼王", "無", "0%")

    # --- 圖表區 ---
    col_chart1, col_chart2 = st.columns(2)
    
    # 1. 持股權重排行 (Bar Chart)
    with col_chart1:
        st.subheader("📊 持股權重排行")
        # 只顯示目前持有的
        curr_holdings = merged[merged['權重'] > 0].sort_values('權重', ascending=False).head(15)
        
        fig1 = px.bar(
            curr_holdings, y='股票名稱', x='權重', 
            orientation='h', text='權重',
            color='權重', color_continuous_scale='Blues'
        )
        fig1.update_traces(texttemplate='%{text:.2f}%', textposition='outside')
        fig1.update_layout(yaxis={'categoryorder':'total ascending'}, height=400, margin=dict(l=0, r=0, t=30, b=0))
        st.plotly_chart(fig1, use_container_width=True)

    # 2. 經理人動作雷達 (加減碼排行) - 這是新功能！
    with col_chart2:
        st.subheader("⚡ 經理人動作 (權重變化)")
        # 取變動最大的前 15 名 (包含加碼和減碼)
        changes = merged[merged['權重變化'].abs() > 0].sort_values('權重變化', ascending=True)
        if len(changes) > 15:
            # 取頭尾各 7 檔
            changes = pd.concat([changes.head(7), changes.tail(8)])
        
        if not changes.empty:
            fig2 = go.Figure()
            fig2.add_trace(go.Bar(
                y=changes['股票名稱'], x=changes['權重變化'],
                orientation='h',
                marker=dict(
                    color=changes['權重變化'],
                    colorscale='RdBu', # 紅跌藍漲
                    midpoint=0
                ),
                text=changes['權重變化'].apply(lambda x: f"{x:+.2f}%"),
                textposition='outside'
            ))
            fig2.update_layout(
                height=400, 
                margin=dict(l=0, r=0, t=30, b=0),
                xaxis_title="權重增減 (%)"
            )
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("⚠️ 兩日之間持股無權重變化")

    # --- 智慧表格 (含迷你圖) ---
    st.subheader("📋 詳細持股監控")
    
    # 準備表格資料
    table_df = merged.copy()
    
    # 加入歷史趨勢 (Sparkline)
    trend_col = []
    for code in table_df['股票代號']:
        trend_col.append(get_trend_data(df, code))
    table_df['歷史走勢'] = trend_col

    # 排序：優先顯示新進榜，接著按權重排序
    table_df['is_new'] = table_df['權重_old'] == 0
    table_df = table_df.sort_values(['is_new', '權重'], ascending=[False, False])

    # 顯示設定
    st.dataframe(
        table_df,
        column_order=['股票名稱', '股票代號', '權重', '權重變化', '持有股數', '股數變化', '歷史走勢'],
        hide_index=True,
        use_container_width=True,
        height=600,
        column_config={
            "股票名稱": st.column_config.TextColumn("股票名稱", help="股票名稱"),
            "權重": st.column_config.ProgressColumn(
                "權重 (%)", 
                format="%.2f%%", 
                min_value=0, 
                max_value=15, 
            ),
            "權重變化": st.column_config.NumberColumn(
                "權重增減", 
                format="%.2f%%",
            ),
            "持有股數": st.column_config.NumberColumn(
                "持有股數", 
                format="%d",
            ),
            # ★★★ 迷你折線圖 (Sparkline) ★★★
            "歷史走勢": st.column_config.LineChartColumn(
                "近30日趨勢",
                width="medium",
                help="過去30筆權重變化走勢",
                y_min=0,
                y_max=None 
            )
        }
    )

# 執行顯示
show_etf_dashboard("00981A", "主動統一台股增長")
show_etf_dashboard("00991A", "主動復華未來50")
