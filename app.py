import streamlit as st
import pandas as pd
import os
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(page_title="ETF 戰情室 2.0", page_icon="🚀", layout="wide")

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
</style>
""", unsafe_allow_html=True)

st.title("🚀 2026 主動式 ETF 經理人操盤追蹤")

# --- 資料讀取與修復 ---
@st.cache_data(ttl=60)
def load_data(file_path):
    if not os.path.exists(file_path):
        return None
    try:
        # 嘗試讀取，加入 utf-8-sig 防止亂碼
        return pd.read_csv(file_path, dtype=str, on_bad_lines='skip', engine='python', encoding='utf-8-sig')
    except:
        return None

def clean_data(df):
    if df is None or df.empty: return pd.DataFrame()
    
    # 1. 補齊欄位
    for col in ['持有股數', '權重']:
        if col not in df.columns: df[col] = '0'
            
    # 2. 清洗數值
    for col in ['持有股數', '權重']:
        df[col] = df[col].astype(str).str.replace(',', '').str.replace('%', '')
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    
    # 3. 日期處理
    if 'Date' in df.columns:
        df['Date'] = pd.to_datetime(df['Date'])
        # 轉回字串以便顯示
        df['DateStr'] = df['Date'].dt.strftime('%Y-%m-%d')
    else:
        return pd.DataFrame()

    # ★★★ 關鍵修復：網頁端強制去重 (防止 CSV 裡有重複資料導致報錯) ★★★
    # 針對同一天、同一檔股票，只留一筆
    df = df.drop_duplicates(subset=['DateStr', '股票代號'], keep='first')
    
    # 按日期排序
    df = df.sort_values('Date', ascending=False)
    
    return df

# --- 核心邏輯：計算趨勢線數據 ---
def get_trend_data(full_df, stock_code):
    try:
        history = full_df[full_df['股票代號'] == stock_code].sort_values('Date', ascending=True)
        return history['權重'].tail(30).tolist()
    except:
        return []

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
        st.warning(f"⚠️ {etf_code} 資料格式有誤或為空。")
        return
    
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
    try:
        df_now = df[df['DateStr'] == date1].copy().set_index('股票代號')
        df_old = df[df['DateStr'] == date2].copy().set_index('股票代號')
        
        # 合併比較
        merged = df_now[['股票名稱', '持有股數', '權重']].join(
            df_old[['持有股數', '權重']], lsuffix='', rsuffix='_old', how='outer'
        ).fillna(0)
        
        merged['權重變化'] = merged['權重'] - merged['權重_old']
        merged['股數變化'] = merged['持有股數'] - merged['持有股數_old']
        merged = merged.reset_index()
        
        # 補名稱
        name_map = pd.concat([df_now['股票名稱'], df_old['股票名稱']]).to_dict()
        merged['股票名稱'] = merged['股票代號'].map(name_map).fillna(merged['股票代號'])
    except Exception as e:
        st.error(f"資料處理時發生錯誤: {e}")
        return

    # --- KPI 指標卡 ---
    new_entries = merged[(merged['權重_old'] == 0) & (merged['權重'] > 0)]
    exited = merged[(merged['權重_old'] > 0) & (merged['權重'] == 0)]
    
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("📊 總持股數", f"{len(df_now)} 檔")
    k2.metric("🔥 本日新進", f"{len(new_entries)} 檔", delta_color="normal")
    k3.metric("👋 本日剔除", f"{len(exited)} 檔", delta_color="inverse")
    
    top_buy = merged.sort_values('權重變化', ascending=False).iloc[0] if not merged.empty else None
    if top_buy is not None and top_buy['權重變化'] > 0:
        k4.metric("👑 加碼王", f"{top_buy['股票名稱']}", f"+{top_buy['權重變化']:.2f}%")
    else:
        k4.metric("👑 加碼王", "無", "0%")

    # --- 圖表區 ---
    col_chart1, col_chart2 = st.columns(2)
    
    # 1. 持股權重排行
    with col_chart1:
        st.subheader("📊 持股權重排行")
        curr_holdings = merged[merged['權重'] > 0].sort_values('權重', ascending=False).head(15)
        if not curr_holdings.empty:
            fig1 = px.bar(
                curr_holdings, y='股票名稱', x='權重', 
                orientation='h', text='權重',
                color='權重', color_continuous_scale='Blues'
            )
            fig1.update_traces(texttemplate='%{text:.2f}%', textposition='outside')
            fig1.update_layout(yaxis={'categoryorder':'total ascending'}, height=400, margin=dict(l=0, r=0, t=30, b=0))
            st.plotly_chart(fig1, use_container_width=True)
        else:
            st.info("暫無持股資料")

    # 2. 經理人動作雷達 (安全版)
    with col_chart2:
        st.subheader("⚡ 經理人動作 (權重變化)")
        # 過濾出有變動的
        changes = merged[merged['權重變化'].abs() > 0].sort_values('權重變化', ascending=True)
        
        if not changes.empty:
            if len(changes) > 15:
                changes = pd.concat([changes.head(7), changes.tail(8)])
            
            try:
                fig2 = go.Figure()
                fig2.add_trace(go.Bar(
                    y=changes['股票名稱'], x=changes['權重變化'],
                    orientation='h',
                    marker=dict(
                        color=changes['權重變化'],
                        colorscale='RdBu', 
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
            except Exception as e:
                st.warning(f"圖表繪製失敗 (可能是數據異常): {e}")
        else:
            st.info("⚠️ 兩日之間持股無權重變化")

    # --- 智慧表格 ---
    st.subheader("📋 詳細持股監控")
    
    table_df = merged.copy()
    
    # Sparklines (加入防呆)
    trend_col = []
    for code in table_df['股票代號']:
        trend_col.append(get_trend_data(df, code))
    table_df['歷史走勢'] = trend_col

    table_df['is_new'] = table_df['權重_old'] == 0
    table_df = table_df.sort_values(['is_new', '權重'], ascending=[False, False])

    st.dataframe(
        table_df,
        column_order=['股票名稱', '股票代號', '權重', '權重變化', '持有股數', '股數變化', '歷史走勢'],
        hide_index=True,
        use_container_width=True,
        height=600,
        column_config={
            "股票名稱": st.column_config.TextColumn("股票名稱"),
            "權重": st.column_config.ProgressColumn("權重 (%)", format="%.2f%%", min_value=0, max_value=15),
            "權重變化": st.column_config.NumberColumn("權重增減", format="%.2f%%"),
            "持有股數": st.column_config.NumberColumn("持有股數", format="%d"),
            "歷史走勢": st.column_config.LineChartColumn("近30日趨勢", width="medium", y_min=0, y_max=None)
        }
    )

# 執行顯示
show_etf_dashboard("00981A", "主動統一台股增長")
show_etf_dashboard("00991A", "主動復華未來50")
