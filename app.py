import streamlit as st
import pandas as pd
import plotly.express as px
import os

# --- 設定網頁 ---
st.set_page_config(page_title="ETF 經理人操盤戰情室", layout="wide", page_icon="🦁")

# --- CSS 美化：緊湊表格與靠右對齊 ---
st.markdown("""
<style>
    /* Metric 數字大小 */
    div[data-testid="stMetricValue"] { font-size: 24px; }
    
    /* 表格緊湊化 */
    div[data-testid="stDataFrame"] td {
        padding-top: 4px !important;
        padding-bottom: 4px !important;
        font-size: 14px;
    }
    div[data-testid="stDataFrame"] th {
        padding-top: 4px !important;
        padding-bottom: 4px !important;
    }

    /* 強制表格文字靠右 */
    .dataframe { text-align: right !important; }
</style>
""", unsafe_allow_html=True)

st.title("🦁 主動式 ETF 經理人操盤戰情室")

# --- 讀取資料 ---
def load_data(etf_code):
    file_path = f"data/{etf_code}_history.csv"
    if os.path.exists(file_path):
        df = pd.read_csv(file_path)
        df['Date'] = pd.to_datetime(df['Date'])
        # 數據清洗
        df['權重'] = df['權重'].astype(str).str.replace('%', '')
        df['權重'] = pd.to_numeric(df['權重'], errors='coerce').fillna(0)
        df['持有股數'] = df['持有股數'].astype(str).str.replace(',', '').str.replace('--', '0')
        df['持有股數'] = pd.to_numeric(df['持有股數'], errors='coerce').fillna(0)
        # 過濾垃圾資料
        df = df[~df['股票名稱'].str.contains('查看更多|更多', na=False)]
        return df.sort_values(by='Date', ascending=False)
    return None

# --- 計算異動邏輯 ---
def get_comparison(df, current_date, base_date):
    df_curr = df[df['Date'] == current_date].copy()
    df_base = df[df['Date'] == base_date].copy()
    
    # 合併
    merged = pd.merge(
        df_curr[['股票代號', '股票名稱', '持有股數', '權重']],
        df_base[['股票代號', '持有股數', '權重']],
        on='股票代號', how='outer', suffixes=('_今', '_昨')
    )
    merged = merged.fillna(0)
    
    # 計算差異
    merged['股數增減'] = merged['持有股數_今'] - merged['持有股數_昨']
    merged['權重增減'] = merged['權重_今'] - merged['權重_昨']
    
    # 補回名稱
    for idx, row in merged.iterrows():
        if row['股票名稱'] == 0:
            old_name = df_base[df_base['股票代號'] == row['股票代號']]['股票名稱'].values
            if len(old_name) > 0: merged.at[idx, '股票名稱'] = old_name[0]
            
    return merged

# --- 顯示儀表板 ---
def show_dashboard(etf_code, etf_name):
    df = load_data(etf_code)
    if df is None:
        st.error(f"⚠️ {etf_code} 尚未有資料。")
        return

    # --- 1. 側邊欄：日期選擇 ---
    all_dates = df['Date'].dt.date.unique()
    if len(all_dates) < 1:
        st.warning("資料不足。")
        return

    st.sidebar.header(f"📅 {etf_name} 日期設定")
    date_curr = st.sidebar.selectbox(f"{etf_code} 觀察日期", all_dates, index=0)
    default_base_idx = 1 if len(all_dates) > 1 else 0
    date_base = st.sidebar.selectbox(f"{etf_code} 比較基準", all_dates, index=default_base_idx)
    st.sidebar.markdown("---")

    merged = get_comparison(df, pd.Timestamp(date_curr), pd.Timestamp(date_base))
    
    # 分類
    new_entries = merged[(merged['持有股數_昨'] == 0) & (merged['持有股數_今'] > 0)]
    exits = merged[(merged['持有股數_昨'] > 0) & (merged['持有股數_今'] == 0)]
    
    holding_changes = merged[(merged['持有股數_昨'] > 0) & (merged['持有股數_今'] > 0)].copy()
    increases = holding_changes[holding_changes['股數增減'] > 0].sort_values('股數增減', ascending=False)
    decreases = holding_changes[holding_changes['股數增減'] < 0].sort_values('股數增減', ascending=True)

    # --- 2. 戰情儀表板 (榜單式) ---
    st.markdown(f"### 🗓️ {date_curr} vs {date_base} 操盤重點")
    
    c1, c2 = st.columns(2)
    
    # === 左側：買方榜單 ===
    with c1:
        st.info("🔴 **多方操作 (新進 + 加碼)**")
        sub_c1, sub_c2 = st.columns(2)
        with sub_c1: st.metric("✨ 新進檔數", f"{len(new_entries)}", delta_color="normal")
        with sub_c2: st.metric("🔺 加碼檔數", f"{len(increases)}", delta_color="normal")
        
        # 1. 新進榜
        if not new_entries.empty:
            st.markdown("##### ✨ 新進榜 (New)")
            st.dataframe(
                new_entries[['股票名稱', '權重_今', '持有股數_今']].style.format({'權重_今': '{:.2f}%', '持有股數_今': '{:,.0f}'}).set_properties(**{'text-align': 'right'}),
                hide_index=True, use_container_width=True
            )
        else:
            st.caption("今日無新進個股")
        
        # 2. 加碼榜
        if not increases.empty:
            st.markdown("##### 🔺 重點加碼榜 (Top 5)")
            top_inc = increases.head(5)[['股票名稱', '股數增減', '權重_今']]
            st.dataframe(
                top_inc.style.format({'股數增減': '+{:,.0f}', '權重_今': '{:.2f}%'}).set_properties(**{'text-align': 'right'}),
                hide_index=True, use_container_width=True
            )
        else:
            st.caption("今日無加碼個股")

    # === 右側：賣方榜單 ===
    with c2:
        st.success("🟢 **空方操作 (剔除 + 減碼)**") # Streamlit 的 success 是綠色，剛好符合台股跌/賣
        sub_c3, sub_c4 = st.columns(2)
        with sub_c3: st.metric("❌ 剔除檔數", f"{len(exits)}", delta_color="inverse")
        with sub_c4: st.metric("🔻 減碼檔數", f"{len(decreases)}", delta_color="inverse")
            
        # 3. 剔除榜
        if not exits.empty:
            st.markdown("##### ❌ 剔除榜 (Removed)")
            st.dataframe(
                exits[['股票名稱', '權重_昨', '持有股數_昨']].style.format({'權重_昨': '{:.2f}%', '持有股數_昨': '{:,.0f}'}).set_properties(**{'text-align': 'right'}),
                hide_index=True, use_container_width=True
            )
        else:
            st.caption("今日無剔除個股")
            
        # 4. 減碼榜
        if not decreases.empty:
            st.markdown("##### 🔻 重點減碼榜 (Top 5)")
            top_dec = decreases.head(5)[['股票名稱', '股數增減', '權重_今']]
            st.dataframe(
                top_dec.style.format({'股數增減': '{:,.0f}', '權重_今': '{:.2f}%'}).set_properties(**{'text-align': 'right'}),
                hide_index=True, use_container_width=True
            )
        else:
            st.caption("今日無減碼個股")

    st.divider()

    # --- 3. 資金熱力圖 ---
    st.subheader("🗺️ 資金流向熱力圖")
    map_data = merged[merged['權重_今'] > 0].copy()
    if not map_data.empty:
        fig = px.treemap(
            map_data,
            path=['股票名稱'],
            values='權重_今',
            color='股數增減',
            color_continuous_scale=['#00aa00', '#ffffff', '#ff0000'],
            color_continuous_midpoint=0,
            hover_data=['股票代號', '股數增減', '權重_今']
        )
        fig.update_traces(textinfo="label+value+percent entry")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("尚無資料")

    # --- 4. 完整持股異動表 ---
    st.subheader("📋 完整持股異動明細 (依權重排序)")
    
    show_df = merged[['股票代號', '股票名稱', '持有股數_今', '股數增減', '權重_今', '權重增減']].copy()
    show_df.columns = ['代號', '名稱', '目前持股 (股)', '持股增減 (股)', '權重 (%)', '權重變化 (%)']
    
    # 依權重由大到小排序
    show_df = show_df.sort_values(by='權重 (%)', ascending=False)

    # 樣式設定
    def highlight_change(val):
        color = '#ffcccc' if val > 0 else '#ccffcc' if val < 0 else ''
        return f'background-color: {color}'

    st.dataframe(
        show_df.style.map(highlight_change, subset=['持股增減 (股)', '權重變化 (%)'])
                     .format({
                         '目前持股 (股)': '{:,.0f}', 
                         '持股增減 (股)': '{:+,.0f}', 
                         '權重 (%)': '{:.2f}', 
                         '權重變化 (%)': '{:+.2f}'
                     })
                     .set_properties(**{'text-align': 'right'}),
        use_container_width=True,
        hide_index=True, 
        height=800
    )

# --- 主程式：分頁 ---
tab1, tab2, tab3 = st.tabs(["00981A 統一", "00991A 復華", "00980A 野村"])

with tab1:
    show_dashboard("00981A", "統一台股增長主動式ETF")
with tab2:
    show_dashboard("00991A", "復華未來50")
with tab3:
    show_dashboard("00980A", "野村臺灣智慧優選")
