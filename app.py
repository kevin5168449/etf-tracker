import streamlit as st
import pandas as pd
import os
import plotly.express as px

# 1. 網頁基本設定
st.set_page_config(page_title="ETF 戰情室", page_icon="📊", layout="wide")
st.title("🚀 2026 主動式 ETF 每日追蹤")

# 2. 讀取數據函式
def load_data(file_path):
    if os.path.exists(file_path):
        # 讀取時，先把所有欄位當成文字讀進來，避免格式跑掉
        return pd.read_csv(file_path, dtype=str)
    return None

# 3. 通用顯示函式
def show_etf_dashboard(etf_code, etf_name):
    st.divider()
    st.header(f"📈 {etf_code} {etf_name}")
    
    csv_path = f'data/{etf_code}_history.csv'
    df = load_data(csv_path)

    if df is not None and not df.empty:
        # ★★★ 關鍵修復：清洗數據 (Data Cleaning) ★★★
        # 1. 把逗號拿掉 (例如 "1,000" -> "1000")
        if '持有股數' in df.columns:
            df['持有股數'] = df['持有股數'].astype(str).str.replace(',', '')
            # 2. 強制轉成數字 (不能轉的變成 0)
            df['持有股數'] = pd.to_numeric(df['持有股數'], errors='coerce').fillna(0)
            
        # 取得所有可用日期
        all_dates = sorted(df['Date'].unique(), reverse=True)
        
        # --- 側邊欄控制區 ---
        col_ctrl1, col_ctrl2 = st.columns(2)
        with col_ctrl1:
            date1 = st.selectbox(f"選擇基準日期 ({etf_code})", all_dates, index=0, key=f"d1_{etf_code}")
        with col_ctrl2:
            default_idx = 1 if len(all_dates) > 1 else 0
            date2 = st.selectbox(f"選擇比較日期 ({etf_code})", all_dates, index=default_idx, key=f"d2_{etf_code}")

        # 準備資料
        df_current = df[df['Date'] == date1].copy()
        df_prev = df[df['Date'] == date2].copy()
        
        # 合併比對
        merged = pd.merge(df_current, df_prev, on=['股票代號', '股票名稱'], how='left', suffixes=('', '_old'))
        
        # 現在大家都是數字了，可以安心相減！
        merged['持有股數_old'] = merged['持有股數_old'].fillna(0) # 確保舊資料是 0 而不是 NaN
        merged['股數變化'] = merged['持有股數'] - merged['持有股數_old']
        
        # 排序
        merged = merged.sort_values('持有股數', ascending=False)
        
        # --- 顯示畫面 ---
        col_main, col_chart = st.columns([1, 1.5])
        
        with col_main:
            st.subheader(f"📋 持股清單 ({date1})")
            
            def highlight_change(val):
                if val > 0: return 'color: green'
                elif val < 0: return 'color: red'
                else: return 'color: grey'

            display_df = merged[['股票名稱', '股票代號', '持有股數', '股數變化']].head(15)
            
            st.dataframe(
                display_df.style.map(highlight_change, subset=['股數變化'])
                                .format({"持有股數": "{:,.0f}", "股數變化": "{:+,.0f}"}),
                use_container_width=True,
                hide_index=True
            )
            
        with col_chart:
            st.subheader("📊 前十大持股權重")
            # 準備畫圖資料 (取前10大，並反轉順序讓最大的在上面)
            top10 = merged.head(10).sort_values('持有股數', ascending=True)
            
            fig = px.bar(
                top10, 
                x='持有股數', 
                y='股票名稱', 
                orientation='h', # 橫向
                text='持有股數',
                title=f"{date1} 前十大持股",
                # 自訂滑鼠移過去顯示的資訊
                hover_data={
                    '股票名稱': True,
                    '持有股數': ':,.0f', # 加千分位
                    '股數變化': ':+,.0f'  # 加正負號和千分位
                }
            )
            # 設定文字格式
            fig.update_traces(texttemplate='%{text:.2s}', textposition='outside')
            # 讓圖表高度自適應
            fig.update_layout(height=500, yaxis={'categoryorder':'total ascending'})
            
            st.plotly_chart(fig, use_container_width=True)

        # --- 劇烈變動區 ---
        st.subheader("⚡ 焦點個股 (變動 > 10 張)")
        changes = merged[abs(merged['股數變化']) >= 10000].sort_values('股數變化', ascending=False)
        if not changes.empty:
            for _, row in changes.iterrows():
                change = row['股數變化']
                sheets = change / 1000
                color = "green" if change > 0 else "red"
                icon = "🟢 加碼" if change > 0 else "🔴 減碼"
                st.markdown(f"#### :{color}[{icon} {row['股票名稱']} ({row['股票代號']}): {sheets:+.1f} 張]")
        else:
            st.caption("無顯著變動。")

    else:
        st.warning(f"⚠️ {etf_code} 尚無資料，請等待 GitHub Action 執行成功。")

# 4. 執行
show_etf_dashboard("00981A", "主動統一台股增長")
show_etf_dashboard("00980A", "主動野村臺灣優選")
