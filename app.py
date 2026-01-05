import streamlit as st
import pandas as pd
import os
import plotly.express as px # 引入更強的畫圖工具

# 1. 網頁基本設定
st.set_page_config(page_title="ETF 戰情室", page_icon="📊", layout="wide")
st.title("🚀 2026 主動式 ETF 每日追蹤")

# 2. 讀取數據函式
def load_data(file_path):
    if os.path.exists(file_path):
        return pd.read_csv(file_path, dtype={'股票代號': str})
    return None

# 3. 通用顯示函式
def show_etf_dashboard(etf_code, etf_name):
    st.divider()
    st.header(f"📈 {etf_code} {etf_name}")
    
    csv_path = f'data/{etf_code}_history.csv'
    df = load_data(csv_path)

    if df is not None and not df.empty:
        # 取得所有可用日期
        all_dates = sorted(df['Date'].unique(), reverse=True)
        
        # --- 側邊欄控制區 (針對每個 ETF 獨立控制) ---
        col_ctrl1, col_ctrl2 = st.columns(2)
        with col_ctrl1:
            # 讓使用者選擇 "主要日期" (通常是今天)
            date1 = st.selectbox(f"選擇基準日期 ({etf_code})", all_dates, index=0, key=f"d1_{etf_code}")
        with col_ctrl2:
            # 讓使用者選擇 "比較日期" (通常是昨天)
            # 如果有第二天，預設選第二天，否則選跟第一天一樣
            default_idx = 1 if len(all_dates) > 1 else 0
            date2 = st.selectbox(f"選擇比較日期 ({etf_code})", all_dates, index=default_idx, key=f"d2_{etf_code}")

        # 準備資料
        df_current = df[df['Date'] == date1].copy()
        df_prev = df[df['Date'] == date2].copy()
        
        # 合併比對
        merged = pd.merge(df_current, df_prev, on=['股票代號', '股票名稱'], how='left', suffixes=('', '_old'))
        merged['股數變化'] = merged['持有股數'] - merged['持有股數_old'].fillna(0)
        merged['變化率(%)'] = (merged['股數變化'] / merged['持有股數_old']).fillna(0) * 100
        
        # 排序：依照持有股數多寡
        merged = merged.sort_values('持有股數', ascending=False)
        
        # --- 顯示畫面 ---
        col_main, col_chart = st.columns([1, 1.5])
        
        with col_main:
            st.subheader(f"📋 持股清單 ({date1})")
            
            # 格式化顯示 (加入顏色與箭頭)
            def highlight_change(val):
                if val > 0: return 'color: green'
                elif val < 0: return 'color: red'
                else: return 'color: grey'

            # 準備要顯示的表格
            display_df = merged[['股票名稱', '股票代號', '持有股數', '股數變化']].head(15) # 只看前15大
            
            st.dataframe(
                display_df.style.map(highlight_change, subset=['股數變化'])
                                .format({"持有股數": "{:,}", "股數變化": "{:+,.0f}"}),
                use_container_width=True,
                hide_index=True
            )
            
        with col_chart:
            st.subheader("📊 前十大持股權重 (橫向)")
            # 使用 Plotly 畫橫向圖
            top10 = merged.head(10).sort_values('持有股數', ascending=True) # 反向排序是為了讓最大的在上面
            
            fig = px.bar(
                top10, 
                x='持有股數', 
                y='股票名稱', 
                orientation='h', # h = 水平橫向
                text='持有股數',
                title=f"{date1} 前十大持股",
                hover_data=['股票代號', '股數變化']
            )
            fig.update_traces(texttemplate='%{text:.2s}', textposition='outside')
            fig.update_layout(yaxis={'categoryorder':'total ascending'}) # 確保順序正確
            st.plotly_chart(fig, use_container_width=True)

        # --- 特別顯示：劇烈變動區 ---
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
        st.warning(f"⚠️ {etf_code} 尚無資料，請確認爬蟲是否執行成功。")

# 4. 執行
show_etf_dashboard("00981A", "主動統一台股增長")
show_etf_dashboard("00980A", "主動野村臺灣優選")
