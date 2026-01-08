import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os

# --- 設定網頁標題 ---
st.set_page_config(page_title="ETF 主動式戰情室", layout="wide")
st.title("🦁 主動式 ETF 經理人操盤戰情室")
st.markdown("### 追蹤經理人的每一步棋：新進、剔除、加減碼")

# --- 讀取資料函式 ---
def load_data(etf_code):
    file_path = f"data/{etf_code}_history.csv"
    if os.path.exists(file_path):
        df = pd.read_csv(file_path)
        df['Date'] = pd.to_datetime(df['Date'])
        # 清洗數據：轉為數值
        df['權重'] = df['權重'].astype(str).str.replace('%', '')
        df['權重'] = pd.to_numeric(df['權重'], errors='coerce').fillna(0)
        df['持有股數'] = df['持有股數'].astype(str).str.replace(',', '').str.replace('--', '0')
        df['持有股數'] = pd.to_numeric(df['持有股數'], errors='coerce').fillna(0)
        return df
    return None

# --- 核心邏輯：計算異動 ---
def calculate_changes(df):
    dates = df['Date'].sort_values(ascending=False).unique()
    if len(dates) < 2:
        return df[df['Date'] == dates[0]].copy(), None, dates[0]
    
    today = dates[0]
    yesterday = dates[1]
    
    df_today = df[df['Date'] == today].copy()
    df_yesterday = df[df['Date'] == yesterday].copy()
    
    # 合併比較
    merged = pd.merge(
        df_today[['股票代號', '股票名稱', '持有股數', '權重']],
        df_yesterday[['股票代號', '持有股數', '權重']],
        on='股票代號',
        how='outer',
        suffixes=('_今', '_昨')
    )
    merged = merged.fillna(0)
    
    # 計算差異
    merged['股數增減'] = merged['持有股數_今'] - merged['持有股數_昨']
    merged['權重增減'] = merged['權重_今'] - merged['權重_昨']
    
    # 定義動作標籤
    def classify_action(row):
        if row['持有股數_昨'] == 0 and row['持有股數_今'] > 0: return '✨ 新進榜'
        if row['持有股數_昨'] > 0 and row['持有股數_今'] == 0: return '❌ 已剔除'
        if row['股數增減'] > 0: return '🔴 加碼'
        if row['股數增減'] < 0: return '🟢 減碼'
        return '⚪ 持平'

    merged['動作'] = merged.apply(classify_action, axis=1)
    
    # 補回名稱 (針對剔除的股票，名稱可能會是 0，需要從昨天資料補)
    for idx, row in merged.iterrows():
        if row['股票名稱'] == 0:
            old_name = df_yesterday[df_yesterday['股票代號'] == row['股票代號']]['股票名稱'].values
            if len(old_name) > 0:
                merged.at[idx, '股票名稱'] = old_name[0]
                
    return df_today, merged, today

# --- 顯示儀表板函式 ---
def show_etf_dashboard(etf_code, etf_name):
    st.header(f"📊 {etf_name} ({etf_code})")
    
    df = load_data(etf_code)
    if df is None:
        st.error("⚠️ 尚未有資料，請檢查爬蟲是否執行。")
        return

    latest_df, merged_df, latest_date = calculate_changes(df)
    st.caption(f"📅 資料更新日期: {latest_date.strftime('%Y-%m-%d')}")

    # === 1. 重點摘要 (Metrics) ===
    if merged_df is not None:
        new_entry = merged_df[merged_df['動作'] == '✨ 新進榜']
        exit_entry = merged_df[merged_df['動作'] == '❌ 已剔除']
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("持股檔數", f"{len(latest_df)}", delta=f"{len(latest_df) - len(df[df['Date']!=latest_date]['Date'].unique()) if len(df['Date'].unique())>1 else 0}")
        c2.metric("✨ 新進檔數", f"{len(new_entry)}", delta_color="normal")
        c3.metric("❌ 剔除檔數", f"{len(exit_entry)}", delta_color="inverse")
        
        # 顯示最大加碼股
        top_buy = merged_df.sort_values('股數增減', ascending=False).iloc[0] if not merged_df.empty else None
        if top_buy is not None and top_buy['股數增減'] > 0:
            c4.metric("🔥 最大加碼", f"{top_buy['股票名稱']}", f"+{int(top_buy['股數增減']):,}")

    st.divider()

    # === 2. 🚨 置頂專區：新進與剔除 (最重要！) ===
    if merged_df is not None:
        col_new, col_exit = st.columns(2)
        
        with col_new:
            st.subheader("✨ 今日新進榜 (New)")
            if not new_entry.empty:
                st.dataframe(new_entry[['股票代號', '股票名稱', '持有股數_今', '權重_今']].style.applymap(lambda x: 'background-color: #ffcccc', subset=['股票名稱']), use_container_width=True)
            else:
                st.info("今日無新進個股")
                
        with col_exit:
            st.subheader("❌ 今日剔除榜 (Removed)")
            if not exit_entry.empty:
                st.dataframe(exit_entry[['股票代號', '股票名稱', '持有股數_昨']].style.applymap(lambda x: 'background-color: #ccffcc', subset=['股票名稱']), use_container_width=True)
            else:
                st.info("今日無剔除個股")

    # === 3. 🔥 資金熱力圖 (Heatmap) ===
    st.subheader("🗺️ 資金流向熱力圖 (板塊大小=權重, 顏色=加減碼)")
    
    if merged_df is not None:
        # 為了畫圖，我們過濾掉已剔除的 (權重為0無法顯示在板塊圖)，只看現在持有的
        heatmap_data = merged_df[merged_df['權重_今'] > 0].copy()
        
        # 設定顏色：台灣股市習慣 (紅漲/買，綠跌/賣)
        # 我們用 '股數增減' 來決定顏色深淺
        # 為了讓顏色對比更明顯，我們建立一個 color column
        
        fig = px.treemap(
            heatmap_data, 
            path=['股票名稱'], 
            values='權重_今',
            color='股數增減',
            color_continuous_scale=['#00aa00', '#ffffff', '#ff0000'], # 綠 -> 白 -> 紅
            color_continuous_midpoint=0,
            hover_data=['股票代號', '股數增減', '動作'],
            title=f"{etf_name} 持股權重與資金流向"
        )
        fig.update_traces(textinfo="label+value+percent entry") # 顯示名稱+權重
        fig.update_layout(margin=dict(t=50, l=25, r=25, b=25))
        st.plotly_chart(fig, use_container_width=True)
    
    else:
        st.info("累積兩天資料後，將顯示資金熱力圖。")

    # === 4. 📋 詳細異動表 (美化版) ===
    st.subheader("📋 詳細持股異動表")
    if merged_df is not None:
        # 排序：加碼最多 -> 減碼最多
        display_df = merged_df.sort_values(by='股數增減', ascending=False)
        
        # 選擇要顯示的欄位
        display_df = display_df[['動作', '股票代號', '股票名稱', '持有股數_今', '股數增減', '權重_今', '權重增減']]
        
        # 針對「股數增減」欄位做顏色標記
        def color_change(val):
            color = '#ff4b4b' if val > 0 else '#00cc96' if val < 0 else 'transparent'
            return f'color: {color}; font-weight: bold'

        st.dataframe(
            display_df.style.map(color_change, subset=['股數增減', '權重增減'])
                            .format({'持有股數_今': '{:,.0f}', '股數增減': '{:+,.0f}', '權重_今': '{:.2f}%', '權重增減': '{:+.2f}%'}),
            use_container_width=True,
            height=500
        )
    else:
        st.dataframe(latest_df)

# --- 主程式區塊 ---
tab1, tab2, tab3 = st.tabs(["00981A 統一", "00991A 復華", "00980A 野村"])

with tab1:
    show_etf_dashboard("00981A", "統一台股增長主動式ETF")

with tab2:
    show_etf_dashboard("00991A", "復華未來50")

with tab3:
    show_etf_dashboard("00980A", "野村臺灣智慧優選")
