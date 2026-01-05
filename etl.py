import pandas as pd
import requests
import os
from datetime import datetime
import io

# --- 設定 Discord Webhook ---
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK")

def send_discord_notify(msg):
    if not DISCORD_WEBHOOK:
        print("⚠️ 未設定 DISCORD_WEBHOOK，跳過通知")
        return
    
    data = {"content": msg, "username": "ETF 監控小幫手"}
    
    try:
        result = requests.post(DISCORD_WEBHOOK, json=data)
        if 200 <= result.status_code < 300:
            print("✅ Discord 通知發送成功")
        else:
            print(f"❌ 發送失敗: {result.text}")
    except Exception as e:
        print(f"❌ 發送錯誤: {e}")

# 小工具：自動產生「民國年」日期字串
def get_roc_date_string():
    now = datetime.now()
    roc_year = now.year - 1911
    return f"{roc_year}/{now.month:02d}/{now.day:02d}"

# ★★★ 新增功能：聰明讀取 Excel (自動跳過標題行) ★★★
def smart_read_excel(content):
    try:
        # 先讀取前 20 行，不設標題
        temp_df = pd.read_excel(io.BytesIO(content), header=None, nrows=20)
        
        # 尋找含有「股票代號」或「Code」的那一行
        header_row_index = -1
        for i, row in temp_df.iterrows():
            row_str = row.astype(str).str.cat() # 把整行黏成字串
            if "股票代號" in row_str or "證券代號" in row_str or "Code" in row_str:
                header_row_index = i
                print(f"🔍 在第 {i} 行找到表格標題！")
                break
        
        if header_row_index != -1:
            # 從找到的那一行開始重新讀取
            df = pd.read_excel(io.BytesIO(content), header=header_row_index)
            return df
        else:
            print("⚠️ 找不到標題列，嘗試直接讀取...")
            return pd.read_excel(io.BytesIO(content))
            
    except Exception as e:
        print(f"Excel 解析錯誤: {e}")
        return pd.DataFrame()

def get_etf_data(etf_code):
    df = pd.DataFrame()
    
    # ==========================================
    # 統一投信 (00981A)
    # ==========================================
    if etf_code == "00981A":
        roc_date = get_roc_date_string()
        url = f"https://www.ezmoney.com.tw/ETF/Transaction/PCFExcelNPOI?fundCode=61YTW&date={roc_date}&specificDate=false"
        print(f"📥 正在下載統一 (00981A): {url} ...")
        
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            response = requests.get(url, headers=headers)
            
            # 使用新的聰明讀取功能
            df = smart_read_excel(response.content)

        except Exception as e:
            print(f"❌ 統一 (00981A) 下載失敗: {e}")
            return pd.DataFrame()

    # ==========================================
    # 野村投信 (00980A)
    # ==========================================
    elif etf_code == "00980A":
        # 嘗試用假資料或是暫時跳過，因為野村網頁版太難爬
        print(f"⚠️ 野村 (00980A) 暫時無法爬取，跳過。")
        return pd.DataFrame()
    
    # --- 統一欄位名稱 ---
    column_mapping = {
        '股票代號': ['股票代號', 'Code', '證券代號', '標的代號', 'Stock Code'],
        '股票名稱': ['股票名稱', 'Name', '證券名稱', '標的名稱', 'Stock Name'],
        '持有股數': ['持有股數', 'Shares', '庫存股數', '股數', '持有股數/單位數']
    }
    
    # 自動改名
    if not df.empty:
        for target, candidates in column_mapping.items():
            for candidate in candidates:
                matches = [col for col in df.columns if str(col).strip() in candidates]
                if matches:
                    df.rename(columns={matches[0]: target}, inplace=True)
                    break
                
    # 只留我們需要的欄位
    required = ['股票代號', '股票名稱', '持有股數']
    available = [c for c in required if c in df.columns]
    
    if len(available) == 3:
        # 去除代號為 NaN 的行 (可能是 Excel 下方的備註)
        df = df.dropna(subset=['股票代號'])
        return df[required]
    else:
        if not df.empty:
            print(f"⚠️ {etf_code} 欄位對應不完整，目前欄位: {df.columns.tolist()}")
        return pd.DataFrame()

def process_etf(etf_code, etf_name):
    print(f"\n🔄 處理中: {etf_name} ({etf_code})...")
    
    # 1. 抓資料
    df_new = get_etf_data(etf_code)
    
    if df_new.empty:
        print(f"⚠️ {etf_name} 無法獲取數據，跳過比對。")
        return ""

    today_str = datetime.now().strftime('%Y-%m-%d')
    history_file = f'data/{etf_code}_history.csv'
    
    # 強制轉字串
    if '股票代號' in df_new.columns:
        df_new['股票代號'] = df_new['股票代號'].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    df_new['Date'] = today_str

    # 2. 比較邏輯
    msg = ""
    if os.path.exists(history_file):
        try:
            df_history = pd.read_csv(history_file, dtype={'股票代號': str})
            if not df_history.empty:
                last_date = df_history['Date'].max()
                df_old = df_history[df_history['Date'] == last_date].copy()
                df_old['股票代號'] = df_old['股票代號'].astype(str).str.strip()
                
                # 合併
                merged = pd.merge(df_new, df_old, on=['股票代號', '股票名稱'], how='left', suffixes=('', '_old'))
                merged['股數變化'] = merged['持有股數'] - merged['持有股數_old'].fillna(0)
                changes = merged[merged['股數變化'] != 0]
                
                if not changes.empty:
                    msg = f"\n📊 **[{etf_code} {etf_name}] 持股異動:**\n"
                    for _, row in changes.iterrows():
                        change = int(row['股數變化'])
                        icon = "🔴減" if change < 0 else "🟢加"
                        sheets = change / 1000
                        if abs(sheets) >= 0.1: # 只顯示 0.1 張以上的變化
                            msg += f"{icon} **{row['股票名稱']}** ({row['股票代號']}): {sheets:+.1f}張\n"
        except Exception as e:
            print(f"比對歷史資料時發生錯誤: {e}")

    # 3. 存檔
    mode = 'a' if os.path.exists(history_file) else 'w'
    header = not os.path.exists(history_file)
    df_new.to_csv(history_file, mode=mode, header=header, index=False)
    print(f"✅ {etf_name} 數據存檔完成")
    
    return msg

def main():
    print("🚀 啟動 ETF 監控系統...")
    if not os.path.exists('data'):
        os.makedirs('data')
        
    final_msg = ""
    
    # 執行統一 (00981A)
    final_msg += process_etf("00981A", "主動統一") or ""
    
    # 執行野村 (00980A) - 先暫停，確保統一能跑
    # final_msg += process_etf("00980A", "主動野村") or ""

    if final_msg:
        print("準備發送 Discord 通知...")
        send_discord_notify(final_msg)
    else:
        # 👇 這裡我加了一個測試訊息，確認 Discord 是通的
        print("今日無異動，發送存活確認...")
        send_discord_notify("🔔 ETF 機器人測試：系統執行成功！(目前顯示此訊息代表程式沒壞，但今日持股無顯著變化，或初次建立資料庫)")

if __name__ == "__main__":
    main()
