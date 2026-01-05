import streamlit as st
import pandas as pd
import os

st.set_page_config(page_title="ETF 戰情室", layout="wide", page_icon="📈")

st.title("⚡ 2025 主動式 ETF 追蹤儀表板")

data_file = 'data/00981A_history.csv'

if os.path.exists(data_file):
    df = pd.read_csv(data_file)
    dates = sorted(df['Date'].unique(), reverse=True)
    latest_date = dates[0]
    
    st.info(f"📅 最新數據日期: {latest_date}")
    
    # 篩選最新資料
    current_df = df[df['Date'] == latest_date]
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("📋 最新持股清單")
        st.dataframe(current_df, use_container_width=True)
        
    with col2:
        st.subheader("🥧 權重概覽")
        st.bar_chart(current_df.set_index('股票名稱')['持有股數'])
        
    st.divider()
    st.subheader("📈 歷史持股數據")
    st.dataframe(df)
else:
    st.warning("⚠️ 尚未有數據，請等待 GitHub Action 執行第一次抓取 (約需 1-2 分鐘)。")
