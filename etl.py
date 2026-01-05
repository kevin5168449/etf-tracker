import pandas as pd
import requests
import os
from datetime import datetime
import io

# --- 設定 Discord Webhook ---
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK")

def send_discord_notify(msg):
    if not DISCORD_WEBHOOK: return
    data = {"content": msg, "username": "ETF 監控小幫手"}
    try: requests.post(DISCORD_WEBHOOK, json=data)
    except: pass

def get_roc_date_string():
    now = datetime.now()
    return f"{now.year - 1911}/{now.month:02d}/{now.day:02d}"

# 聰明讀取 Excel (統一專用)
def smart_read_excel(content):
    try:
        temp_df = pd.read_excel(io.BytesIO(content), header=None, nrows=20)
        header_row = -1
        for i, row in temp_df.iterrows():
            if "股票代號" in row.astype(str).str.cat() or "Code" in row.astype(str).str.cat():
                header_row = i
                break
        return pd.read_excel(io.BytesIO(content), header=header_row) if header_row != -1 else pd.DataFrame()
    except: return pd.DataFrame()

def get_etf_data(etf_code):
    df = pd.DataFrame()
    
    # === 統一 00981A (維持原樣) ===
    if etf_code == "00981A":
        roc_date = get_roc_date_string()
        url = f"https://www.ezmoney.com.tw/ETF/Transaction/PCFExcelNPOI?fundCode=61YTW&date={roc_date}&specificDate=false"
        print(f"📥 下載統一: {url}")
        try:
            res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
            df = smart_read_excel(res.content)
        except Exception as e:
            print(f"❌ 統一失敗: {e}")

    # === 野村 00980A (改抓 MoneyDJ) ===
    elif etf_code == "00980A":
        # MoneyDJ 的野村持股頁面
        url = "https://www.moneydj.com/ETF/X/Basic/Basic0004X.xdjhtm?etfid=00980A"
        print(f"🕷️ 爬取 MoneyDJ (野村): {url}")
        try:
            # 這裡需要 lxml
            dfs = pd.read_html(url, encoding='utf-8')
            # MoneyDJ 通常有好幾個表格，持股通常在很後面，或者包含 "股票名稱"
            for temp in dfs:
                if '股票名稱' in temp.columns and '股票代號' in temp.columns:
                    df = temp
                    print(f"✅ 成功在 MoneyDJ 找到表格！")
                    break
        except Exception as e:
            print(f"❌ 野村(MoneyDJ)失敗: {e}")

    # === 欄位清洗 ===
    col_map = {
        '股票代號': ['股票代號', '代號'],
        '股票名稱': ['股票名稱', '名稱'],
        '持有股數': ['持有股數', '股數', '庫存股數', '張數', '權重'] # MoneyDJ 有時候給張數
    }
    for target, cands in col_map.items():
        for cand in cands:
            matches = [c for c in df.columns if str(c).strip() == cand]
            if matches:
                df.rename(columns={matches[0]: target}, inplace=True)
                break
    
    # 處理 MoneyDJ 可能給的是 "張數" 而不是 "股數" 的情況
    # 如果數值很小 (例如 < 50000)，通常是張數，要乘 1000
    if not df.empty and '持有股數' in df.columns:
        # 清洗非數字字元
        df['持有股數'] = pd.to_numeric(df['持有股數'].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
        
        # 簡單判斷：如果是 MoneyDJ 抓來的，通常第一名只有幾千(張)，要換算成股
        if etf_code == "00980A" and df['持有股數'].max() < 100000: 
            print("⚠️ 偵測到單位可能是「張」，自動轉換為「股」")
            df['持有股數'] = df['持有股數'] * 1000

    required = ['股票代號', '股票名稱', '持有股數']
    if all(c in df.columns for c in required):
        return df[required]
    return pd.DataFrame()

def process_etf(etf_code, etf_name):
    df_new = get_etf_data(etf_code)
    if df_new.empty: return ""
    
    today_str = datetime.now().strftime('%Y-%m-%d')
    file_path = f'data/{etf_code}_history.csv'
    
    # 強制代號轉字串
    if '股票代號' in df_new.columns:
        df_new['股票代號'] = df_new['股票代號'].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    df_new['Date'] = today_str
    
    # 存檔
    mode = 'a' if os.path.exists(file_path) else 'w'
    header = not os.path.exists(file_path)
    df_new.to_csv(file_path, mode=mode, header=header, index=False)
    
    # 比對 (略過 Discord 訊息邏輯簡化，因為重點是存檔給網頁看)
    return f"✅ {etf_name} 更新成功"

def main():
    if not os.path.exists('data'): os.makedirs('data')
    msg = process_etf("00981A", "主動統一")
    msg += "\n" + process_etf("00980A", "主動野村")
    print(msg)
    # 如果您想要 Discord 通知，可以取消下面註解
    # send_discord_notify(msg)

if __name__ == "__main__":
    main()
