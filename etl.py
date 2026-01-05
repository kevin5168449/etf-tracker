import pandas as pd
import requests
import os
from datetime import datetime

# 1. 設定 LINE Token (從 GitHub Secrets 讀取)
LINE_TOKEN = os.environ.get("LINE_TOKEN")

def send_line_notify(msg):
    if not LINE_TOKEN:
        print("⚠️ 未設定 LINE_TOKEN，跳過發送通知")
        return
    url = "https://notify-api.line.me/api/notify"
    headers = {"Authorization": "Bearer " + LINE_TOKEN}
    payload = {"message": msg}
    requests.post(url, headers=headers, data=payload)

def get_etf_data():
    # --- 這裡是用於演示的模擬數據 ---
    # 實戰中，請將 data 替換成 pd.read_csv('真實的PCF下載網址')
    # 這裡我們模擬 00981A 今天買進了 "奇鋐"
    import random
    today_holdings = [
        {'股票代號': '3017', '股票名稱': '奇鋐', '持有股數': 500000 + random.randint(-1000, 5000)},
        {'股票代號': '2330', '股票名稱': '台積電', '持有股數': 1000000},
        {'股票代號': '6669', '股票名稱': '緯穎', '持有股數': 200000 + random.randint(0, 2000)}
    ]
    df = pd.DataFrame(today_holdings)
    return df

def main():
    print("🚀 開始執行 ETF 數據抓取...")
    
    # 確保 data 資料夾存在
    if not os.path.exists('data'):
        os.makedirs('data')

    today_str = datetime.now().strftime('%Y-%m-%d')
    history_file = 'data/00981A_history.csv'
    
    # 1. 獲取今日數據
    df_new = get_etf_data()
    df_new['Date'] = today_str
    
    # 2. 比較昨日數據
    msg = ""
    if os.path.exists(history_file):
        df_history = pd.read_csv(history_file)
        last_date = df_history['Date'].max()
        
        # 只取最近一天的資料來比較
        df_old = df_history[df_history['Date'] == last_date]
        
        # 合併比較
        merged = pd.merge(df_new, df_old, on=['股票代號', '股票名稱'], how='left', suffixes=('', '_old'))
        merged['股數變化'] = merged['持有股數'] - merged['持有股數_old'].fillna(0)
        
        # 篩選變動
        changes = merged[merged['股數變化'] != 0]
        
        if not changes.empty:
            msg = f"\n📊 [00981A] {today_str} 持股異動:\n"
            for _, row in changes.iterrows():
                icon = "🔴減" if row['股數變化'] < 0 else "🟢加"
                msg += f"{icon} {row['股票名稱']}: {int(row['股數變化']):,} 股\n"
    else:
        msg = f"\n🚀 系統初次啟動！已建立 {today_str} 基礎資料庫。"

    # 3. 發送通知
    if msg:
        print(msg)
        send_line_notify(msg)
    
    # 4. 存檔 (累加數據)
    # 如果檔案存在，用 append 模式；不存在則寫入 header
    mode = 'a' if os.path.exists(history_file) else 'w'
    header = not os.path.exists(history_file)
    df_new.to_csv(history_file, mode=mode, header=header, index=False)
    print("✅ 數據已更新至 data/00981A_history.csv")

if __name__ == "__main__":
    main()
