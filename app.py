import streamlit as st
import pandas as pd
import os

# 1. 網頁基本設定
st.set_page_config(page_title="ETF 雙戰情室", page_icon="📊", layout="wide")
st.title("🚀 2026 主動式 ETF 每日追蹤")
st.caption("數據來源：GitHub Actions 自動爬蟲 | 自動化更新")

# 2. 讀取數據的函式 (強制轉字串，防止 Bug)
def load_data(file_path):
    if os.path.exists(file_path):
        return pd.read_csv(file_path, dtype={'股票代號': str})
    return None

# 3. 顯示 ETF 的通用函式
def show_etf_status(etf_code, etf_name):
    st.divider()
    st.header(f"📈 {etf_code} {etf_name}")
    
    csv_path = f'data/{etf_code}_history.csv'
    df = load_data(csv_path)

    if df is not None and not df.empty:
        # 找出最新日期
        dates = sorted(df['Date'].unique(), reverse=True)
        latest_date = dates[0]
        st.info(f"📅 數據更新日期：**{latest_date}**")

        # 篩選最新資料
        latest_df = df[df['Date'] == latest_date].copy()
        
        # 左右分欄
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.subheader("📋 前十大持股 (最新)")
            # 取前 10 大
            top10 = latest_df.sort_values('持有股數', ascending=False).head(10)
            st.dataframe(top10[['股票代號', '股票名稱', '持有股數']], hide_index=True, use_container_width=True)

        with col2:
            st.subheader("🥧 持股權重分佈")
            st.bar_chart(top10.set_index('股票名稱')['持有股數'])

        # --- 比較昨日變化 ---
        if len(dates) >= 2:
            prev_date = dates[1]
            st.subheader(f"⚡ 持股異動偵測 ({prev_date} ➡ {latest_date})")
            
            prev_df = df[df['Date'] == prev_date]
            
            # 合併比對
            merged = pd.merge(latest_df, prev_df, on=['股票代號', '股票名稱'], how='left', suffixes=('', '_old'))
            merged['變化'] = merged['持有股數'] - merged['持有股數_old'].fillna(0)
            
            # 找出有變化的
            changes = merged[merged['變化'] != 0].dropna()
            
            if not changes.empty:
                for _, row in changes.iterrows():
                    change = int(row['變化'])
                    # 只顯示變化大於 100 股的 (過濾雜訊)
                    if abs(change) > 100:
                        color = "green" if change > 0 else "red"
                        icon = "🟢 加碼" if change > 0 else "🔴 減碼"
                        sheets = change / 1000
                        st.markdown(f":{color}[{icon} **{row['股票名稱']}** ({row['股票代號']}): {change:+,} 股 ({sheets:+.1f}張)]")
            else:
                st.write("💤 與前一日相比，主要持股無顯著變化。")
    else:
        st.warning(f"⚠️ 尚未找到 {etf_code} 的數據，請等待 GitHub Action 執行成功。")

# 4. 呼叫函式顯示兩檔 ETF
show_etf_status("00981A", "主動統一台股增長")
show_etf_status("00980A", "主動野村臺灣優選") # 如果您還沒跑野村的資料，這一塊會顯示警告，是正常的
