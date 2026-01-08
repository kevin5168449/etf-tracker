import streamlit as st
import pandas as pd
import plotly.express as px
import os

# --- 設定網頁 ---
st.set_page_config(page_title="ETF 經理人操盤戰情室", layout="wide", page_icon="🦁")

# CSS 美化：調整字體與 Metric 樣式
st.markdown("""
<style>
    div[data-testid="stMetricValue"] { font-size: 24px; }
    .big-font { font-size:18px !important; font-weight: bold; }
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
        # 過濾掉垃圾資料
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
    
    # 補回名稱
    for idx, row in merged.iterrows():
        if row['股票名稱'] == 0:
            old_name = df_base[df_base['股票代號'] == row['股票代號']]['股票名稱'].values
            if len(old_name) > 0: merged.at[idx, '股票名稱'] = old_name[0]
            
    return merged

# --- 顯示儀表板 ---
def show_dashboard(etf_code, etf_name):
    df = load_data(etf_code)
    if df is None:
        st.error(f"⚠️ {etf_code} 尚未有資料。")
        return

    # --- 1. 側邊欄：日期選擇 ---
    all_dates = df['Date'].dt.date.unique()
    if len(all_dates) < 1:
        st.warning("資料不足。")
        return

    st.sidebar.header(f"📅 {etf_name} 日期設定")
    date_curr = st.sidebar.selectbox(f"{etf_code} 觀察日期", all_dates, index=0)
    default_base_idx = 1 if len(all_dates) > 1 else 0
    date_base = st.sidebar.selectbox(f"{etf_code} 比較基準", all_dates, index=default_base_idx)
    st.sidebar.markdown("---")

    # --- 計算數據 ---
    merged = get_comparison(df, pd.Timestamp(date_curr), pd.Timestamp(date_base))
    
    # 分類
    new_entries = merged[(merged['持有股數_昨'] == 0) & (merged['持有股數_今'] > 0)]
    exits = merged[(merged['持有股數_昨'] > 0) & (merged['持有股數_今'] == 0)]
    
    # 排除新進/剔除，只看既有持股的加減碼
    holding_changes = merged[(merged['持有股數_昨'] > 0) & (merged['持有股數_今'] > 0)].copy()
    increases = holding_changes[holding_changes['股數增減'] > 0].sort_values('股數增減', ascending=False)
    decreases = holding_changes[holding_changes['股數增減'] < 0].sort_values('股數增減', ascending=True)

    # --- 2. 戰情儀表板 (四大天王) ---
    st.markdown(f"### 🗓️ {date_curr} vs {date_base} 操盤重點")
    
    # 使用 2x2 排版，左邊是「買進訊號」，右邊是「賣出訊號」
    c1, c2 = st.columns(2)
    
    with c1:
        st.info("📈 **買進訊號 (Bullish)**")
        sub_c1, sub_c2 = st.columns(2)
        with sub_c1:
            st.metric("✨ 新進檔數", f"{len(new_entries)}", delta_color="normal")
        with sub_c2:
            st.metric("🔴 加碼檔數", f"{len(increases)}", delta_color="normal")
            
        # 新進榜表格
        if not new_entries.empty:
            st.markdown("**✨ 新進榜**")
            st.dataframe(new_entries[['股票名稱', '權重_今', '持有股數_今']], hide_index=True, use_container_width=True)
        
        # 加碼榜表格 (Top 5)
        if not increases.empty:
            st.markdown("**🔴 重點加碼 (Top 5)**")
            top_inc = increases.head(5)[['股票名稱', '股數增減', '權重_今']]
            st.dataframe(top_inc.style.format({'股數增減': '+{:,.0f}'}), hide_index=True, use_container_width=True)

    with c2:
        st.error("📉 **賣出訊號 (Bearish)**")
        sub_c3, sub_c4 = st.columns(2)
        with sub_c3:
            st.metric("❌ 剔除檔數", f"{len(exits)}", delta_color="inverse")
        with sub_c4:
            st.metric("🟢 減碼檔數", f"{len(decreases)}", delta_color="inverse")
            
        # 剔除榜表格
        if not exits.empty:
            st.markdown("**❌ 剔除榜**")
            st.dataframe(exits[['股票名稱', '權重_昨', '持有股數_昨']], hide_index=True, use_container_width=True)
            
        # 減碼榜表格 (Top 5)
        if not decreases.empty:
            st.markdown("**🟢 重點減碼 (Top 5)**")
            top_dec = decreases.head(5)[['股票名稱', '股數增減', '權重_今']]
            st.dataframe(top_dec.style.format({'股數增減': '{:,.0f}'}), hide_index=True, use_container_width=True)

    st.divider()

    # --- 3. 資金熱力圖 ---
    st.subheader("🗺️ 資金流向熱力圖")
    map_data = merged[merged['權重_今'] > 0].copy()
    if not map_data.empty:
        fig = px.treemap(
            map_data,
            path=['股票名稱'],
            values='權重_今',
            color='股數增減',
            color_continuous_scale=['#00aa00', '#ffffff', '#ff0000'],
            color_continuous_midpoint=0,
            hover_data=['股票代號', '股數增減', '權重_今']
        )
        fig.update_traces(textinfo="label+value+percent entry")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("尚無資料")

    # --- 4. 完整持股異動表 ---
    st.subheader("📋 完整持股異動明細")
    
    # 整理顯示欄位與名稱
    show_df = merged[['股票代號', '股票名稱', '持有股數_今', '股數增減', '權重_今', '權重增減']].copy()
    show_df.columns = ['代號', '名稱', '目前持股 (股)', '持股增減 (股)', '權重 (%)', '權重變化 (%)']
    
    # 排序：優先顯示「動作大」的 (絕對值排序)
    show_df = show_df.iloc[show_df['持股增減 (股)'].abs().argsort()[::-1]]

    # 樣式設定
    def highlight_change(val):
        color = '#ffcccc' if val > 0 else '#ccffcc' if val < 0 else ''
        return f'background-color: {color}'

    st.dataframe(
        show_df.style.map(highlight_change, subset=['持股增減 (股)', '權重變化 (%)'])
                     .format({
                         '目前持股 (股)': '{:,.0f}', 
                         '持股增減 (股)': '{:+,.0f}', 
                         '權重 (%)': '{:.2f}', 
                         '權重變化 (%)': '{:+.2f}'
                     }),
        use_container_width=True,
        hide_index=True, # ★★★ 這裡隱藏了最前面的怪數字
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
