import streamlit as st
import pandas as pd
import plotly.express as px
import os

# --- 設定網頁 ---
st.set_page_config(page_title="ETF 經理人操盤戰情室", layout="wide", page_icon="🦁")

# CSS 美化：讓 Metric 卡片更好看
st.markdown("""
<style>
    div[data-testid="stMetricValue"] { font-size: 24px; }
    .big-font { font-size:20px !important; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

st.title("🦁 主動式 ETF 經理人操盤戰情室")

# --- 讀取資料 ---
def load_data(etf_code):
    file_path = f"data/{etf_code}_history.csv"
    if os.path.exists(file_path):
        df = pd.read_csv(file_path)
        df['Date'] = pd.to_datetime(df['Date'])
        # 數據清洗
        df['權重'] = df['權重'].astype(str).str.replace('%', '')
        df['權重'] = pd.to_numeric(df['權重'], errors='coerce').fillna(0)
        df['持有股數'] = df['持有股數'].astype(str).str.replace(',', '').str.replace('--', '0')
        df['持有股數'] = pd.to_numeric(df['持有股數'], errors='coerce').fillna(0)
        # 過濾掉垃圾資料 (例如"查看更多")
        df = df[~df['股票名稱'].str.contains('查看更多|更多', na=False)]
        return df.sort_values(by='Date', ascending=False)
    return None

# --- 計算異動邏輯 ---
def get_comparison(df, current_date, base_date):
    df_curr = df[df['Date'] == current_date].copy()
    df_base = df[df['Date'] == base_date].copy()
    
    # 合併
    merged = pd.merge(
        df_curr[['股票代號', '股票名稱', '持有股數', '權重']],
        df_base[['股票代號', '持有股數', '權重']],
        on='股票代號', how='outer', suffixes=('_今', '_昨')
    )
    merged = merged.fillna(0)
    
    # 計算差異
    merged['股數增減'] = merged['持有股數_今'] - merged['持有股數_昨']
    merged['權重增減'] = merged['權重_今'] - merged['權重_昨']
    
    # 補回名稱 (若剔除，今日名稱會是 0)
    for idx, row in merged.iterrows():
        if row['股票名稱'] == 0:
            old_name = df_base[df_base['股票代號'] == row['股票代號']]['股票名稱'].values
            if len(old_name) > 0: merged.at[idx, '股票名稱'] = old_name[0]
            
    return merged

# --- 顯示單一 ETF 儀表板 ---
def show_dashboard(etf_code, etf_name):
    df = load_data(etf_code)
    if df is None:
        st.error(f"⚠️ {etf_code} 尚未有資料。")
        return

    # --- 1. 側邊欄：日期選擇 (全域控制) ---
    all_dates = df['Date'].dt.date.unique()
    if len(all_dates) < 1:
        st.warning("資料不足。")
        return

    st.sidebar.header(f"📅 {etf_name} 日期設定")
    date_curr = st.sidebar.selectbox(f"{etf_code} 觀察日期", all_dates, index=0)
    # 預設基準日期為觀察日期的前一天 (如果有的話)
    default_base_idx = 1 if len(all_dates) > 1 else 0
    date_base = st.sidebar.selectbox(f"{etf_code} 比較基準", all_dates, index=default_base_idx)
    
    st.sidebar.markdown("---")

    # --- 計算數據 ---
    merged = get_comparison(df, pd.Timestamp(date_curr), pd.Timestamp(date_base))
    
    # 找出焦點股
    top_buy = merged.sort_values('股數增減', ascending=False).iloc[0]
    top_sell = merged.sort_values('股數增減', ascending=True).iloc[0]
    new_entries = merged[(merged['持有股數_昨'] == 0) & (merged['持有股數_今'] > 0)]
    exits = merged[(merged['持有股數_昨'] > 0) & (merged['持有股數_今'] == 0)]

    # --- 2. 戰情摘要 (Highlights) ---
    st.markdown(f"### 🗓️ {date_curr} vs {date_base} 操盤摘要")
    
    col1, col2, col3, col4 = st.columns(4)
    
    # 卡片 1: 最大加碼
    with col1:
        st.metric(
            label="🔥 本日最大加碼",
            value=top_buy['股票名稱'],
            delta=f"+{int(top_buy['股數增減']):,}" if top_buy['股數增減'] > 0 else "無動作"
        )
        
    # 卡片 2: 最大減碼
    with col2:
        st.metric(
            label="🧊 本日最大減碼",
            value=top_sell['股票名稱'],
            delta=f"{int(top_sell['股數增減']):,}" if top_sell['股數增減'] < 0 else "無動作",
            delta_color="inverse"
        )
        
    # 卡片 3: 新進榜
    with col3:
        st.metric(
            label="✨ 新進檔數",
            value=f"{len(new_entries)} 檔",
            delta="點擊下方查看" if not new_entries.empty else "無"
        )

    # 卡片 4: 剔除榜
    with col4:
        st.metric(
            label="❌ 剔除檔數",
            value=f"{len(exits)} 檔",
            delta="點擊下方查看" if not exits.empty else "無",
            delta_color="inverse"
        )

    st.divider()

    # --- 3. 資金熱力圖 (最直觀的視覺) ---
    st.subheader("🗺️ 資金流向熱力圖")
    st.caption("方塊越大=權重越重 | 顏色越紅=加碼越多 | 顏色越綠=減碼越多")
    
    # 過濾掉權重為 0 的 (已剔除無法畫圖)
    map_data = merged[merged['權重_今'] > 0].copy()
    
    if not map_data.empty:
        fig = px.treemap(
            map_data,
            path=['股票名稱'],
            values='權重_今',
            color='股數增減',
            color_continuous_scale=['#00aa00', '#ffffff', '#ff0000'], # 綠-白-紅
            color_continuous_midpoint=0,
            hover_data=['股票代號', '股數增減', '權重_今']
        )
        fig.update_traces(textinfo="label+value+percent entry")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("尚無足夠持股資料繪製熱力圖")

    # --- 4. 分類詳細清單 ---
    c1, c2 = st.columns(2)
    
    with c1:
        st.subheader("✨ 新進榜 (New)")
        if not new_entries.empty:
            st.dataframe(new_entries[['股票名稱', '權重_今', '持有股數_今']], use_container_width=True)
        else:
            st.info("無")
            
    with c2:
        st.subheader("❌ 剔除榜 (Removed)")
        if not exits.empty:
            st.dataframe(exits[['股票名稱', '權重_昨', '持有股數_昨']], use_container_width=True)
        else:
            st.info("無")

    # --- 5. 完整持股異動表 ---
    st.subheader("📋 完整持股異動明細")
    
    # 格式化顯示 (隱藏 Date, 加入顏色)
    def highlight_change(val):
        color = '#ffcccc' if val > 0 else '#ccffcc' if val < 0 else ''
        return f'background-color: {color}'

    # 選擇顯示欄位
    show_df = merged[['股票代號', '股票名稱', '持有股數_今', '股數增減', '權重_今', '權重增減']].copy()
    show_df = show_df.sort_values(by='權重_今', ascending=False) # 預設依權重排序

    st.dataframe(
        show_df.style.map(highlight_change, subset=['股數增減', '權重增減'])
                     .format({'持有股數_今': '{:,.0f}', '股數增減': '{:+,.0f}', '權重_今': '{:.2f}', '權重增減': '{:+.2f}'}),
        use_container_width=True,
        height=600
    )

# --- 主程式：分頁 ---
tab1, tab2, tab3 = st.tabs(["00981A 統一", "00991A 復華", "00980A 野村"])

with tab1:
    show_dashboard("00981A", "統一台股增長主動式ETF")
with tab2:
    show_dashboard("00991A", "復華未來50")
with tab3:
    show_dashboard("00980A", "野村臺灣智慧優選")
