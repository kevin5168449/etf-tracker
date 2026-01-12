import streamlit as st
import pandas as pd
import plotly.express as px
import os
import subprocess
import time

st.set_page_config(page_title="ETF 經理人戰情室", layout="wide", page_icon="🦁")

# CSS
st.markdown("""
<style>
    div[data-testid="stMetricValue"] { font-size: 26px; font-weight: bold; }
    div[data-testid="stDataFrame"] td { padding-top: 8px !important; padding-bottom: 8px !important; }
</style>
""", unsafe_allow_html=True)

st.title("🦁 主動式 ETF 經理人操盤戰情室")

# --- 側邊欄：手動更新功能 ---
with st.sidebar:
    st.header("⚙️ 系統功能")
    if st.button("🔄 立即手動更新資料"):
        status_text = st.empty()
        status_text.info("⏳ 正在連線爬蟲，請稍候 (約需 1-2 分鐘)...")
        try:
            # 執行 python update_data.py
            result = subprocess.run(["python", "update_data.py"], capture_output=True, text=True)
            if result.returncode == 0:
                status_text.success("✅ 更新成功！請重新整理網頁。")
                st.code(result.stdout) # 顯示爬蟲 Log 讓你知道發生什麼事
                time.sleep(3)
                st.rerun() # 自動重整
            else:
                status_text.error("❌ 更新失敗")
                st.error(result.stderr)
        except Exception as e:
            status_text.error(f"❌ 執行錯誤: {e}")
    st.markdown("---")

# --- 讀取資料 ---
def load_data(etf_code):
    file_path = f"data/{etf_code}_history.csv"
    if os.path.exists(file_path):
        df = pd.read_csv(file_path)
        df['Date'] = pd.to_datetime(df['Date'])
        # 清洗
        df['權重'] = df['權重'].astype(str).str.replace('%', '')
        df['權重'] = pd.to_numeric(df['權重'], errors='coerce').fillna(0)
        df['持有股數'] = df['持有股數'].astype(str).str.replace(',', '').str.replace('--', '0')
        df['持有股數'] = pd.to_numeric(df['持有股數'], errors='coerce').fillna(0)
        
        df = df[~df['股票名稱'].str.contains('查看更多|更多|Total', na=False)]
        
        return df.sort_values(by='Date', ascending=False)
    return None

# --- 計算異動 ---
def get_comparison(df, current_date, base_date):
    df_curr = df[df['Date'] == current_date].copy()
    df_base = df[df['Date'] == base_date].copy()
    
    merged = pd.merge(
        df_curr[['股票代號', '股票名稱', '持有股數', '權重']],
        df_base[['股票代號', '持有股數', '權重']],
        on='股票代號', how='outer', suffixes=('_今', '_昨')
    )
    merged = merged.fillna(0)
    
    merged['股數增減'] = merged['持有股數_今'] - merged['持有股數_昨']
    merged['權重增減'] = merged['權重_今'] - merged['權重_昨']
    
    def determine_status(row):
        if row['持有股數_昨'] == 0 and row['持有股數_今'] > 0: return '✨ 新進'
        if row['持有股數_昨'] > 0 and row['持有股數_今'] == 0: return '❌ 剔除'
        if row['股數增減'] > 0: return '🔴 加碼'
        if row['股數增減'] < 0: return '🟢 減碼'
        return '⚪ 持平'

    merged['狀態'] = merged.apply(determine_status, axis=1)
    
    for idx, row in merged.iterrows():
        if row['股票名稱'] == 0:
            old_name = df_base[df_base['股票代號'] == row['股票代號']]['股票名稱'].values
            if len(old_name) > 0: merged.at[idx, '股票名稱'] = old_name[0]
            
    return merged

# --- 顯示介面 ---
def show_dashboard(etf_code, etf_name):
    df = load_data(etf_code)
    if df is None:
        st.error(f"⚠️ {etf_code} 尚未有資料。")
        return

    all_dates = df['Date'].dt.date.unique()
    if len(all_dates) < 1:
        st.warning("資料不足。")
        return

    st.sidebar.header(f"📅 {etf_name} 設定")
    date_curr = st.sidebar.selectbox(f"{etf_code} 觀察日期", all_dates, index=0)
    default_base_idx = 1 if len(all_dates) > 1 else 0
    date_base = st.sidebar.selectbox(f"{etf_code} 比較基準", all_dates, index=default_base_idx)
    st.sidebar.markdown("---")

    merged = get_comparison(df, pd.Timestamp(date_curr), pd.Timestamp(date_base))
    
    new_entries = merged[merged['狀態'] == '✨ 新進']
    exits = merged[merged['狀態'] == '❌ 剔除']
    increases = merged[merged['狀態'] == '🔴 加碼'].sort_values('股數增減', ascending=False)
    decreases = merged[merged['狀態'] == '🟢 減碼'].sort_values('股數增減', ascending=True)

    st.markdown(f"### 🗓️ {date_curr} vs {date_base} 操盤重點")
    
    c1, c2 = st.columns(2)
    with c1:
        st.info("🔴 **多方操作 (Buy)**")
        sc1, sc2 = st.columns(2)
        sc1.metric("✨ 新進", f"{len(new_entries)}")
        sc2.metric("🔺 加碼", f"{len(increases)}")
        if not new_entries.empty: st.dataframe(new_entries[['股票名稱', '權重_今', '持有股數_今']], hide_index=True, use_container_width=True)
        if not increases.empty: st.dataframe(increases.head(5)[['股票名稱', '股數增減', '權重_今']].style.format({'股數增減': '+{:,.0f}'}), hide_index=True, use_container_width=True)

    with c2:
        st.success("🟢 **空方操作 (Sell)**")
        sc3, sc4 = st.columns(2)
        sc3.metric("❌ 剔除", f"{len(exits)}")
        sc4.metric("🔻 減碼", f"{len(decreases)}")
        if not exits.empty: st.dataframe(exits[['股票名稱', '權重_昨', '持有股數_昨']], hide_index=True, use_container_width=True)
        if not decreases.empty: st.dataframe(decreases.head(5)[['股票名稱', '股數增減', '權重_今']].style.format({'股數增減': '{:,.0f}'}), hide_index=True, use_container_width=True)

    st.divider()
    
    # 熱力圖
    st.subheader("🗺️ 資金流向熱力圖")
    map_data = merged[merged['權重_今'] > 0].copy()
    if not map_data.empty:
        fig = px.treemap(map_data, path=['股票名稱'], values='權重_今', color='股數增減', color_continuous_scale=['#00aa00', '#ffffff', '#ff0000'], color_continuous_midpoint=0)
        st.plotly_chart(fig, use_container_width=True)

    # 完整列表
    st.subheader("📋 完整持股異動明細 (依權重排序)")
    show_df = merged[['狀態', '股票代號', '股票名稱', '權重_今', '權重增減', '持有股數_今', '股數增減']].sort_values(by='權重_今', ascending=False)
    
    st.dataframe(
        show_df, use_container_width=True, hide_index=True, height=800,
        column_config={
            "狀態": st.column_config.TextColumn("動作", width="small"),
            "權重_今": st.column_config.ProgressColumn("權重 (%)", format="%.2f%%", min_value=0, max_value=max(show_df['權重_今'].max(), 10)),
            "股數增減": st.column_config.NumberColumn("持股增減", format="%+d")
        }
    )

tab1, tab2, tab3 = st.tabs(["00981A 統一", "00991A 復華", "00980A 野村"])
with tab1: show_dashboard("00981A", "統一台股增長主動式ETF")
with tab2: show_dashboard("00991A", "復華未來50")
with tab3: show_dashboard("00980A", "野村臺灣智慧優選")
