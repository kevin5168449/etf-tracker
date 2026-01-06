import streamlit as st
import pandas as pd
import os
import plotly.express as px

st.set_page_config(page_title="ETF 戰情室", page_icon="📊", layout="wide")
st.title("🚀 2026 主動式 ETF 每日追蹤")

# ★★★ 升級版讀取函式：自動修復壞掉的 CSV ★★★
@st.cache_data(ttl=60)
def load_data(file_path):
    if not os.path.exists(file_path):
        return None
        
    try:
        # 嘗試正常讀取
        return pd.read_csv(file_path, dtype=str)
    except pd.errors.ParserError:
        st.warning(f"⚠️ 偵測到 {file_path} 格式混亂 (新舊資料衝突)，正在自動修復...")
        try:
            # 救援模式：使用 Python 引擎，並忽略壞掉的行
            # 這樣通常能讀到最新的資料 (因為新資料欄位比較多)
            df = pd.read_csv(file_path, dtype=str, on_bad_lines='skip', engine='python')
            return df
        except:
            return None

def clean_and_deduplicate(df):
    if df is None or df.empty: return df
    
    # 確保欄位存在 (防止舊資料缺欄位報錯)
    for col in ['持有股數', '權重']:
        if col not in df.columns:
            df[col] = '0' # 補上預設值
            
    # 清洗數值
    for col in ['持有股數', '權重']:
        df[col] = df[col].astype(str).str.replace(',', '').str.replace('%', '')
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
    df = df.drop_duplicates(subset=['Date', '股票代號'], keep='first')
    return df

def calculate_streak(df, stock_code, current_date):
    history = df[df['股票代號'] == stock_code].sort_values('Date', ascending=False)
    streak = 0
    shares = history['持有股數'].tolist()
    for i in range(len(shares) - 1):
        if shares[i] > shares[i+1]:
            streak = streak + 1 if streak >= 0 else 1
        elif shares[i] < shares[i+1]:
            streak = streak - 1 if streak <= 0 else -1
        else: break
    return streak

def show_etf_dashboard(etf_code, etf_name):
    st.divider()
    st.header(f"📈 {etf_code} {etf_name}")
    
    csv_path = f'data/{etf_code}_history.csv'
    raw_df = load_data(csv_path)

    if raw_df is not None and not raw_df.empty:
        df = clean_and_deduplicate(raw_df)
        
        if df.empty:
            st.warning("資料清洗後為空，請確認爬蟲是否成功。")
            return

        all_dates = sorted(df['Date'].unique(), reverse=True)
        
        col_ctrl1, col_ctrl2 = st.columns(2)
        with col_ctrl1:
            date1 = st.selectbox(f"基準 ({etf_code})", all_dates, 0, key=f"d1_{etf_code}")
        with col_ctrl2:
            default_idx = 1 if len(all_dates) > 1 else 0
            date2 = st.selectbox(f"比較 ({etf_code})", all_dates, default_idx, key=f"d2_{etf_code}")

        df_now = df[df['Date'] == date1].copy()
        df_old = df[df['Date'] == date2].copy()
        
        merged = pd.merge(df_now, df_old, on=['股票代號', '股票名稱'], how='outer', suffixes=('', '_old'))
        merged = merged.fillna(0)
        merged['股數變化'] = merged['持有股數'] - merged['持有股數_old']
        
        # 排序邏輯：有權重用權重，沒權重用股數
        has_weight = merged['權重'].sum() > 0
        sort_col = '權重' if has_weight else '持有股數'
        
        merged = merged.sort_values(sort_col, ascending=False)
        merged['連買天數'] = 0
        for idx, row in merged.iterrows():
            if row['持有股數'] > 0:
                merged.at[idx, '連買天數'] = calculate_streak(df, row['股票代號'], date1)

        col_chart, col_list = st.columns([1, 1.5])
        
        with col_chart:
            st.subheader(f"📊 前十大持股 (依{sort_col}排序)")
            top10 = merged.head(10).sort_values(sort_col, ascending=True)
            
            x_val = '權重' if has_weight else '持有股數'
            
            fig = px.bar(
                top10, 
                x=x_val, 
                y='股票名稱', 
                orientation='h',
                text='權重' if has_weight else '持有股數',
                color=x_val,
                color_continuous_scale='Blues',
                hover_data=['持有股數', '權重']
            )
            
            text_fmt = '%{text:.2f}%' if has_weight else '%{text:,.0f}'
            fig.update_traces(texttemplate=text_fmt, textposition='outside')
            fig.update_layout(height=600, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

        with col_list:
            st.subheader(f"📋 完整持股清單")
            
            def style_change(v):
                return f'color: {"red" if v < 0 else "green" if v > 0 else "gray"}'
            
            st.dataframe(
                merged[['股票名稱', '股票代號', '持有股數', '權重', '股數變化', '連買天數']].style
                .map(lambda x: style_change(x), subset=['股數變化'])
                .format({"持有股數": "{:,.0f}", "權重": "{:.2f}%", "股數變化": "{:+,.0f}", "連買天數": "{:+d} 天"}),
                use_container_width=True, height=600, hide_index=True
            )
    else:
        st.warning(f"⚠️ {etf_code} 等待數據中... (如果剛刪除檔案，請等待 Actions 執行完畢)")

show_etf_dashboard("00981A", "主動統一")
show_etf_dashboard("00991A", "主動復華未來")
