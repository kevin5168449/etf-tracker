import pandas as pd
import requests
import os
from datetime import datetime
import io
import time

# --- Selenium 相關設定 ---
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

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

# ★★★ 核彈級武器：使用 Selenium 模擬真實瀏覽器 ★★★
def get_html_with_selenium(url):
    print(f"🤖 啟動 Chrome 瀏覽器前往: {url}")
    
    chrome_options = Options()
    chrome_options.add_argument("--headless") # 不顯示視窗
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    # 偽裝成一般使用者
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    driver = None
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        driver.get(url)
        # 等待 5 秒讓網頁 JavaScript 跑完 (這是關鍵！)
        time.sleep(5) 
        
        page_source = driver.page_source
        return page_source
    except Exception as e:
        print(f"❌ Selenium 執行失敗: {e}")
        return None
    finally:
        if driver:
            driver.quit()

def get_etf_data(etf_code):
    df = pd.DataFrame()
    
    # === 統一 00981A (Excel 下載) ===
    if etf_code == "00981A":
        roc_date = get_roc_date_string()
        url = f"https://www.ezmoney.com.tw/ETF/Transaction/PCFExcelNPOI?fundCode=61YTW&date={roc_date}&specificDate=false"
        print(f"📥 下載統一 (00981A): {url}")
        try:
            res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
            df = smart_read_excel(res.content)
        except Exception as e:
            print(f"❌ 統一失敗: {e}")

    # === 野村 00980A (改用 Selenium 抓 MoneyDJ) ===
    elif etf_code == "00980A":
        url = "https://www.moneydj.com/ETF/X/Basic/Basic0006X.xdjhtm?etfid=00980A"
        print(f"🕷️ 嘗試抓取 MoneyDJ (野村)...")
        
        try:
            # 使用 Selenium 抓取完整的 HTML
            html_content = get_html_with_selenium(url)
            
            if html_content:
                dfs = pd.read_html(html_content)
                for temp in dfs:
                    if '股票名稱' in temp.columns or '名稱' in temp.columns:
                        df = temp
                        print(f"✅ 成功抓到表格！共 {len(df)} 筆資料")
                        break
            else:
                print("❌ 無法取得網頁內容")

        except Exception as e:
            print(f"❌ 野村解析失敗: {e}")

    # === 欄位清洗 ===
    if df.empty: return pd.DataFrame()

    col_map = {
        '股票代號': ['股票代號', '代號'],
        '股票名稱': ['股票名稱', '名稱'],
        '持有股數': ['持有股數', '股數', '庫存股數', '張數', '權重', '股數/單位數']
    }
    for target, cands in col_map.items():
        for cand in cands:
            matches = [c for c in df.columns if str(c).strip() == cand]
            if matches:
                df.rename(columns={matches[0]: target}, inplace=True)
                break
    
    # 處理張數轉股數
    if '持有股數' in df.columns:
        df['持有股數'] = pd.to_numeric(df['持有股數'].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
        # 如果最大值小於 10 萬，極大機率是「張」，乘 1000
        if etf_code == "00980A" and df['持有股數'].max() < 100000:
            print("⚠️ 單位自動修正：張 -> 股")
            df['持有股數'] = df['持有股數'] * 1000

    required = ['股票代號', '股票名稱', '持有股數']
    if all(c in df.columns for c in required):
        return df[required]
    
    return pd.DataFrame()

def process_etf(etf_code, etf_name):
    print(f"--- 開始處理 {etf_name} ---")
    df_new = get_etf_data(etf_code)
    
    if df_new.empty: 
        print(f"⚠️ {etf_name} 無數據，跳過。")
        return ""
    
    today_str = datetime.now().strftime('%Y-%m-%d')
    file_path = f'data/{etf_code}_history.csv'
    
    if '股票代號' in df_new.columns:
        df_new['股票代號'] = df_new['股票代號'].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    df_new['Date'] = today_str
    
    mode = 'a' if os.path.exists(file_path) else 'w'
    header = not os.path.exists(file_path)
    df_new.to_csv(file_path, mode=mode, header=header, index=False)
    
    return f"✅ {etf_name} 更新成功"

def main():
    if not os.path.exists('data'): os.makedirs('data')
    msg = process_etf("00981A", "主動統一")
    msg += "\n" + process_etf("00980A", "主動野村")
    print(msg)

if __name__ == "__main__":
    main()
