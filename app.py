import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os

# --- 設定網頁標題 ---
st.set_page_config(page_title="ETF 主動式戰情室", layout="wide")
st.title("🦁 主動式 ETF 經理人操盤戰情室")

# --- 讀取資料函式 ---
def load_data(etf_code):
    file_path = f"data/{etf_code}_history.csv"
    if os.path.exists(file_path):
        # 讀取時將權重轉為數字，日期轉為時間格式
        df = pd.read_csv(file_path)
        df['Date'] = pd.to_datetime(df['Date'])
        # 確保權重是數字 (處理爬蟲可能留下的 %)
        df['權重'] = df['權重'].astype(str).str.replace('%', '')
        df['權重'] = pd.to_numeric(df['權重'], errors='coerce').fillna(0)
        # 確保股數是數字
        df['持有股數'] = df['持有股數'].astype(str).str.replace(',', '').str.replace('--', '0')
        df['持有股數'] = pd.to_numeric(df['持有股數'], errors='coerce').fillna(0)
        return df
    return None

# --- 顯示儀表板函式 ---
def show_etf_dashboard(etf_code, etf_name):
    st.header(f"📊 {etf_name} ({etf_code})")
    
    df = load_data(etf_code)
    
    if df is None:
        st.warning("⚠️ 尚未有資料，請確認爬蟲是否已執行。")
        return

    # 取得最近兩個交易日
    dates = df['Date'].sort_values(ascending=False).unique()
    
    if len(dates) < 1:
        st.warning("資料不足。")
        return
        
    latest_date = dates[0]
    st.write(f"📅 資料更新日期: {latest_date.strftime('%Y-%m-%d')}")
    
    # 取出最新資料
    latest_df = df[df['Date'] == latest_date].copy()
    latest_df = latest_df.sort_values(by='權重', ascending=False).reset_index(drop=True)
    
    # --- 關鍵數據 ---
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("持股總數", f"{len(latest_df)} 檔")
    with col2:
        top1 = latest_df.iloc[0]
        st.metric("最大持股", f"{top1['股票名稱']} ({top1['權重']}%)")
    with col3:
        # 計算前十大權重總和
        top10_weight = latest_df.iloc[:10]['權重'].sum()
        st.metric("前十大持股占比", f"{top10_weight:.2f}%")

    # --- 如果有兩天以上的資料，計算異動 ---
    if len(dates) >= 2:
        prev_date = dates[1]
        prev_df = df[df['Date'] == prev_date].copy()
        
        # 合併比較 (以股票代號為準)
        merged = pd.merge(
            latest_df[['股票代號', '股票名稱', '持有股數', '權重']], 
            prev_df[['股票代號', '持有股數', '權重']], 
            on='股票代號', 
            how='outer', 
            suffixes=('_今', '_昨')
        )
        
        # 填充 NaN 為 0 (處理新進或剔除)
        merged = merged.fillna(0)
        
        # 計算差異
        merged['股數增減'] = merged['持有股數_今'] - merged['持有股數_昨']
        merged['權重增減'] = merged['權重_今'] - merged['權重_昨']
        
        # 找出大動作 (股數變動超過 1 張的)
        changes = merged[abs(merged['股數增減']) > 1000].copy() # 門檻設為 1000 股
        
        if not changes.empty:
            st.subheader("🔥 經理人最新操盤動作 (股數變動)")
            # 為了美觀，只顯示重要欄位
            show_changes = changes[['股票名稱', '持有股數_今', '股數增減', '權重_今', '權重增減']]
            
            # 格式化顯示
            st.dataframe(
                show_changes.style.background_gradient(subset=['股數增減'], cmap='RdYlGn'),
                use_container_width=True
            )
        else:
            st.info("🧘 這兩天經理人沒有顯著換股動作 (或是資料尚未累積兩天)")

    # --- 持股清單與圖表 ---
    col_left, col_right = st.columns([1, 1])
    
    with col_left:
        st.subheader("📋 最新完整持股清單")
        st.dataframe(latest_df, use_container_width=True)
        
    with col_right:
        st.subheader("🥧 權重分佈圖")
        fig = px.pie(latest_df.head(15), values='權重', names='股票名稱', title='前 15 大持股佔比')
        st.plotly_chart(fig, use_container_width=True)

# --- 主程式區塊：設定分頁 ---
# ★★★ 重點在這裡：新增第三個分頁 ★★★
tab1, tab2, tab3 = st.tabs(["00981A 統一", "00991A 復華", "00980A 野村"])

with tab1:
    show_etf_dashboard("00981A", "統一台股增長主動式ETF")

with tab2:
    show_etf_dashboard("00991A", "復華未來50")

with tab3:
    show_etf_dashboard("00980A", "野村臺灣智慧優選")
