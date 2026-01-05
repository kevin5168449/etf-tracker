import streamlit as st
import pandas as pd
import os
import plotly.express as px

st.set_page_config(page_title="ETF 戰情室", page_icon="📊", layout="wide")
st.title("🚀 2026 主動式 ETF 每日追蹤")

@st.cache_data(ttl=60)
def load_data(file_path):
    if os.path.exists(file_path):
        return pd.read_csv(file_path, dtype=str)
    return None

def clean_and_deduplicate(df):
    if df is None or df.empty: return df
    if '持有股數' in df.columns:
        df['持有股數'] = df['持有股數'].astype(str).str.replace(',', '')
        df['持有股數'] = pd.to_numeric(df['持有股數'], errors='coerce').fillna(0)
    # 去重
    df = df.drop_duplicates(subset=['Date', '股票代號'], keep='first')
    return df

def calculate_streak(df, stock_code, current_date):
    history = df[df['股票代號'] == stock_code].sort_values('Date', ascending=False)
    streak = 0
    shares = history['持有股數'].tolist()
    for i in range(len(shares) - 1):
        if shares[i] > shares[i+1]:
            if streak >= 0: streak += 1
            else: break
        elif shares[i] < shares[i+1]:
            if streak <= 0: streak -= 1
            else: break
        else: break
    return streak

def show_etf_dashboard(etf_code, etf_name):
    st.divider()
    st.header(f"📈 {etf_code} {etf_name}")
    
    csv_path = f'data/{etf_code}_history.csv'
    raw_df = load_data(csv_path)

    if raw_df is not None and not raw_df.empty:
        df = clean_and_deduplicate(raw_df)
        all_dates = sorted(df['Date'].unique(), reverse=True)
        
        col_ctrl1, col_ctrl2 = st.columns(2)
        with col_ctrl1:
            date1 = st.selectbox(f"選擇基準日期 ({etf_code})", all_dates, index=0, key=f"d1_{etf_code}")
        with col_ctrl2:
            default_idx = 1 if len(all_dates) > 1 else 0
            date2 = st.selectbox(f"選擇比較日期 ({etf_code})", all_dates, index=default_idx, key=f"d2_{etf_code}")

        df_current = df[df['Date'] == date1].copy()
        df_prev = df[df['Date'] == date2].copy()
        
        merged = pd.merge(df_current, df_prev, on=['股票代號', '股票名稱'], how='outer', suffixes=('', '_old'))
        merged['持有股數'] = merged['持有股數'].fillna(0)
        merged['持有股數_old'] = merged['持有股數_old'].fillna(0)
        merged['股數變化'] = merged['持有股數'] - merged['持有股數_old']
        
        # 計算佔比
        total_shares = merged['持有股數'].sum()
        if total_shares > 0:
            merged['權重(%)'] = (merged['持有股數'] / total_shares * 100).round(2)
        else:
            merged['權重(%)'] = 0
        
        # 計算連買
        merged = merged.sort_values('持有股數', ascending=False)
        merged['連買天數'] = 0
        for idx, row in merged.iterrows():
            if row['持有股數'] > 0:
                merged.at[idx, '連買天數'] = calculate_streak(df, row['股票代號'], date1)

        col_chart, col_list = st.columns([1, 1.5])
        
        with col_chart:
            st.subheader(f"📊 前十大持股 ({date1})")
            top10 = merged.head(10).sort_values('持有股數', ascending=True)
            
            fig = px.bar(
                top10, 
                x='持有股數', 
                y='股票名稱', 
                orientation='h',
                text='權重(%)',
                color='持有股數',
                color_continuous_scale='Blues'
            )
            fig.update_traces(texttemplate='%{text}%', textposition='outside')
            # ★★★ 這裡拉高了圖表，並加大了字體 ★★★
            fig.update_layout(
                height=600, 
                yaxis={'categoryorder':'total ascending', 'tickfont': {'size': 14}},
                showlegend=False
            )
            st.plotly_chart(fig, use_container_width=True)

        with col_list:
            st.subheader(f"📋 完整持股清單 ({len(merged)} 檔)")
            
            def highlight_change(val):
                if val > 0: return 'color: #28a745; font-weight: bold'
                elif val < 0: return 'color: #dc3545; font-weight: bold'
                else: return 'color: #6c757d'
            
            def highlight_streak(val):
                if val >= 3: return 'background-color: #d4edda; color: #155724'
                elif val <= -3: return 'background-color: #f8d7da; color: #721c24'
                return ''

            st.dataframe(
                merged[['股票名稱', '股票代號', '持有股數', '股數變化', '連買天數']].style
                .map(highlight_change, subset=['股數變化'])
                .map(highlight_streak, subset=['連買天數'])
                .format({"持有股數": "{:,.0f}", "股數變化": "{:+,.0f}", "連買天數": "{:+d} 天"}),
                use_container_width=True,
                height=600,
                hide_index=True
            )
    else:
        st.warning(f"⚠️ {etf_code} 尚無資料，請等待爬蟲執行。")

show_etf_dashboard("00981A", "主動統一台股增長")
show_etf_dashboard("00980A", "主動野村臺灣優選")
