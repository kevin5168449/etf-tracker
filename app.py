import streamlit as st
import pandas as pd
import os
import plotly.express as px

# 1. 網頁基本設定
st.set_page_config(page_title="ETF 戰情室", page_icon="📊", layout="wide")
st.title("🚀 2026 主動式 ETF 每日追蹤")

# 2. 讀取數據函式 (加入快取加速)
@st.cache_data(ttl=60) # 每60秒清除一次快取，確保資料最新
def load_data(file_path):
    if os.path.exists(file_path):
        # 讀取時，先把所有欄位當成文字讀進來，避免格式跑掉
        return pd.read_csv(file_path, dtype=str)
    return None

# 3. 資料清洗與去重專用函式
def clean_and_deduplicate(df):
    if df is None or df.empty: return df
    
    # 清洗數字格式 (移除逗號)
    if '持有股數' in df.columns:
        df['持有股數'] = df['持有股數'].astype(str).str.replace(',', '')
        df['持有股數'] = pd.to_numeric(df['持有股數'], errors='coerce').fillna(0)
    
    # ★★★ 關鍵修復：去除重複資料 ★★★
    # 針對 "Date", "股票代號" 這兩欄做去重，只保留第一筆
    df = df.drop_duplicates(subset=['Date', '股票代號'], keep='first')
    
    return df

# 4. 計算連續買超天數 (進階功能)
def calculate_streak(df, stock_code, current_date):
    # 篩選出該股票的所有歷史紀錄，並按日期排序
    history = df[df['股票代號'] == stock_code].sort_values('Date', ascending=False)
    
    streak = 0
    dates = history['Date'].tolist()
    shares = history['持有股數'].tolist()
    
    # 從今天開始往前比
    for i in range(len(shares) - 1):
        if shares[i] > shares[i+1]: # 今天比昨天多 (買超)
            if streak >= 0: streak += 1
            else: break # 趨勢中斷
        elif shares[i] < shares[i+1]: # 今天比昨天少 (賣超)
            if streak <= 0: streak -= 1
            else: break # 趨勢中斷
        else:
            break # 持平則中斷
            
    return streak

# 5. 通用顯示函式
def show_etf_dashboard(etf_code, etf_name):
    st.divider()
    st.header(f"📈 {etf_code} {etf_name}")
    
    csv_path = f'data/{etf_code}_history.csv'
    raw_df = load_data(csv_path)

    if raw_df is not None and not raw_df.empty:
        # 先進行資料清洗與去重
        df = clean_and_deduplicate(raw_df)
        
        # 取得所有可用日期
        all_dates = sorted(df['Date'].unique(), reverse=True)
        
        # --- 側邊欄控制區 ---
        col_ctrl1, col_ctrl2 = st.columns(2)
        with col_ctrl1:
            date1 = st.selectbox(f"選擇基準日期 ({etf_code})", all_dates, index=0, key=f"d1_{etf_code}")
        with col_ctrl2:
            default_idx = 1 if len(all_dates) > 1 else 0
            date2 = st.selectbox(f"選擇比較日期 ({etf_code})", all_dates, index=default_idx, key=f"d2_{etf_code}")

        # 準備比對資料
        df_current = df[df['Date'] == date1].copy()
        df_prev = df[df['Date'] == date2].copy()
        
        # 合併比對 (Outer join 確保新增或剔除的股票都在)
        merged = pd.merge(df_current, df_prev, on=['股票代號', '股票名稱'], how='outer', suffixes=('', '_old'))
        
        # 填充 NaN (避免新進榜股票變成 NaN)
        merged['持有股數'] = merged['持有股數'].fillna(0)
        merged['持有股數_old'] = merged['持有股數_old'].fillna(0)
        
        # 計算變化
        merged['股數變化'] = merged['持有股數'] - merged['持有股數_old']
        
        # 計算權重 (佔比) - 簡單估算
        total_shares = merged['持有股數'].sum()
        merged['權重(%)'] = (merged['持有股數'] / total_shares * 100).round(2)
        
        # --- 計算連續買賣超 (這會比較花時間，只算前50大以節省效能) ---
        # 先排好序
        merged = merged.sort_values('持有股數', ascending=False)
        
        # 準備一個欄位放連買天數
        merged['連買天數'] = 0
        
        # 只對目前持有的股票算連買
        for idx, row in merged.iterrows():
            if row['持有股數'] > 0:
                s_code = row['股票代號']
                streak = calculate_streak(df, s_code, date1)
                merged.at[idx, '連買天數'] = streak

        # --- 顯示畫面 Layout ---
        col_chart, col_list = st.columns([1, 1.5]) # 左圖右表
        
        with col_chart:
            st.subheader(f"📊 前十大持股佔比 ({date1})")
            
            # 準備畫圖資料 (取前10大)
            top10 = merged.head(10).sort_values('持有股數', ascending=True)
            
            # 使用 Plotly 畫漂亮的橫向長條圖
            fig = px.bar(
                top10, 
                x='持有股數', 
                y='股票名稱', 
                orientation='h',
                text='權重(%)', # 顯示權重在棒子上
                color='持有股數', # 顏色深淺代表股數多寡
                color_continuous_scale='Blues',
                hover_data={
                    '股票代號': True,
                    '持有股數': ':,.0f',
                    '股數變化': ':+,.0f'
                }
            )
            fig.update_traces(texttemplate='%{text}%', textposition='outside')
            fig.update_layout(height=500, yaxis={'categoryorder':'total ascending'}, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

        with col_list:
            st.subheader(f"📋 完整持股清單 (共 {len(merged)} 檔)")
            
            # 格式化顯示函式
            def highlight_change(val):
                if val > 0: return 'color: #28a745; font-weight: bold' # 綠色
                elif val < 0: return 'color: #dc3545; font-weight: bold' # 紅色
                else: return 'color: #6c757d' # 灰色
            
            def highlight_streak(val):
                if val >= 3: return 'background-color: #d4edda; color: #155724' # 連買3天以上亮綠燈
                elif val <= -3: return 'background-color: #f8d7da; color: #721c24' # 連賣3天以上亮紅燈
                return ''

            # 整理要顯示的表格
            display_df = merged[['股票名稱', '股票代號', '持有股數', '股數變化', '連買天數']]
            
            # 顯示 Dataframe (開啟搜尋功能)
            st.dataframe(
                display_df.style
                .map(highlight_change, subset=['股數變化'])
                .map(highlight_streak, subset=['連買天數'])
                .format({
                    "持有股數": "{:,.0f}", 
                    "股數變化": "{:+,.0f}",
                    "連買天數": "{:+d} 天"
                }),
                use_container_width=True,
                height=600, # 拉高表格高度
                hide_index=True
            )
            
    else:
        st.warning(f"⚠️ {etf_code} 尚無資料，請等待爬蟲執行。")

# 6. 執行
show_etf_dashboard("00981A", "主動統一台股增長")
show_etf_dashboard("00980A", "主動野村臺灣優選")
