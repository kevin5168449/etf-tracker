import pandas as pd
import requests
import os
from datetime import datetime

# --- 改用 Discord 設定 ---
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK")

def send_discord_notify(msg):
    if not DISCORD_WEBHOOK:
        print("⚠️ 未設定 DISCORD_WEBHOOK，跳過通知")
        return
    
    # Discord 的格式很簡單，只要傳送 'content' 即可
    data = {
        "content": msg,
        "username": "ETF 監控小幫手" # 您可以自訂機器人名字
    }
    
    try:
        result = requests.post(DISCORD_WEBHOOK, json=data)
        if 200 <= result.status_code < 300:
            print("✅ Discord 通知發送成功")
        else:
            print(f"❌ 發送失敗: {result.text}")
    except Exception as e:
        print(f"❌ 發送錯誤: {e}")

def get_etf_data():
    # --- 模擬數據 (實戰請換成真實爬蟲) ---
    import random
    today_holdings = [
        {'股票代號': '3017', '股票名稱': '奇鋐', '持有股數': 500000 + random.randint(-5000, 5000)},
        {'股票代號': '2330', '股票名稱': '台積電', '持有股數': 1000000},
        {'股票代號': '6669', '股票名稱': '緯穎', '持有股數': 200000 + random.randint(100, 1000)}
    ]
    df = pd.DataFrame(today_holdings)
    return df

def main():
    print("🚀 開始執行 ETF 數據抓取 (Discord 版)...")
    
    if not os.path.exists('data'):
        os.makedirs('data')

    today_str = datetime.now().strftime('%Y-%m-%d')
    history_file = 'data/00981A_history.csv'
    
    # 1. 獲取數據
    df_new = get_etf_data()
    df_new['Date'] = today_str
    
    # 2. 比較邏輯
    msg = ""
    if os.path.exists(history_file):
        df_history = pd.read_csv(history_file)
        last_date = df_history['Date'].max()
        df_old = df_history[df_history['Date'] == last_date]
        
        merged = pd.merge(df_new, df_old, on=['股票代號', '股票名稱'], how='left', suffixes=('', '_old'))
        merged['股數變化'] = merged['持有股數'] - merged['持有股數_old'].fillna(0)
        
        changes = merged[merged['股數變化'] != 0]
        
        if not changes.empty:
            # Discord 支援 Markdown 格式 (粗體用 **)
            msg = f"📊 **[00981A] {today_str} 持股異動:**\n"
            for _, row in changes.iterrows():
                icon = "🔴減" if row['股數變化'] < 0 else "🟢加"
                msg += f"{icon} {row['股票名稱']}: **{int(row['股數變化']):,}** 股\n"
    else:
        msg = f"🚀 系統初次啟動！已建立 {today_str} 基礎資料庫。"

    # 3. 發送 Discord 通知
    if msg:
        print(msg)
        send_discord_notify(msg)
    
    # 4. 存檔
    mode = 'a' if os.path.exists(history_file) else 'w'
    header = not os.path.exists(history_file)
    df_new.to_csv(history_file, mode=mode, header=header, index=False)
    print("✅ 數據存檔完成")

if __name__ == "__main__":
    main()
