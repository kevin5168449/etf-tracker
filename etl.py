import pandas as pd
import requests
import os
from datetime import datetime
import io
import time

# --- Selenium 設定 ---
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

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

# 1. 統一專用：聰明讀取 Excel
def smart_read_excel(content):
    try:
        temp_df = pd.read_excel(io.BytesIO(content), header=None, nrows=20)
        header_row = -1
        for i, row in temp_df.iterrows():
            row_str = row.astype(str).str.cat()
            if "股票代號" in row_str or "Code" in row_str:
                header_row = i
                break
        return pd.read_excel(io.BytesIO(content), header=header_row) if header_row != -1 else pd.DataFrame()
    except: return pd.DataFrame()

# 2. 復華專用：使用 Selenium 爬官網表格
def get_fuhhwa_holdings(url):
    print(f"🤖 啟動 Chrome 前往復華官網: {url}")
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    # 偽裝成真人，避免被復華官網擋
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    driver = None
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.get(url)
        
        # 等待網頁載入，復華官網比較慢，多給一點時間
        try:
            # 等待表格出現 (尋找常見的表格標籤)
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.TAG_NAME, "table"))
            )
            # 強制等待 5 秒讓 JavaScript 渲染數據
            time.sleep(5)
            print("✅ 復華頁面載入完成")
        except:
            print("⚠️ 等待超時，嘗試直接抓取...")
            
        return driver.page_source
    except Exception as e:
        print(f"❌ 爬蟲失敗: {e}")
        return None
    finally:
        if driver: driver.quit()

def get_etf_data(etf_code):
    df = pd.DataFrame()
    
    # === 統一 00981A (官方 Excel 下載) ===
    if etf_code == "00981A":
        roc_date = get_roc_date_string()
        url = f"https://www.ezmoney.com.tw/ETF/Transaction/PCFExcelNPOI?fundCode=61YTW&date={roc_date}&specificDate=false"
        print(f"📥 下載統一 (00981A): {url}")
        try:
            res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
            df = smart_read_excel(res.content)
        except Exception as e:
            print(f"❌ 統一失敗: {e}")

    # === 復華 00991A (官網爬蟲) ===
    elif etf_code == "00991A":
        # 您提供的網址
        url = "https://www.fhtrust.com.tw/ETF/etf_detail/ETF23#stockhold"
        print(f"🕷️ 爬取復華官網 (00991A)...")
        
        html = get_fuhhwa_holdings(url)
        if html:
            try:
                # 復華官網可能有多個表格，我們要找包含 "股票名稱" 或 "股數" 的那個
                dfs = pd.read_html(html)
                for temp in dfs:
                    # 檢查關鍵欄位
                    cols = str(temp.columns)
                    if '股票名稱' in cols or '證券名稱' in cols:
                        df = temp
                        print(f"✅ 成功抓到復華持股表格！(共 {len(df)} 筆)")
                        # 如果表格有 "股數" 欄位，這就是我們要的真愛
                        if '股數' in cols or '持有股數' in cols:
                            break
            except Exception as e:
                print(f"❌ 解析失敗: {e}")

    # === 資料清洗與標準化 ===
    if df.empty: return pd.DataFrame()

    # 1. 統一欄位名稱
    col_map = {
        '股票代號': ['股票代號', '代號', '股號', 'Symbol', '證券代號'],
        '股票名稱': ['股票名稱', '名稱', '股名', 'Name', '證券名稱'],
        '持有股數': ['持有股數', '股數', '庫存股數', '權重', '比例', '持股(%)', '持有股數(股)']
    }
    for target, cands in col_map.items():
        for cand in cands:
            # 部分比對 (防止欄位有空白鍵)
            matches = [c for c in df.columns if str(c).strip() in cands]
            if matches:
                df.rename(columns={matches[0]: target}, inplace=True)
                break
    
    # 2. 數值處理
    if '持有股數' in df.columns:
        # 移除 % 和 逗號
        df['持有股數'] = df['持有股數'].astype(str).str.replace('%', '').str.replace(',', '')
        df['持有股數'] = pd.to_numeric(df['持有股數'], errors='coerce').fillna(0)
        
        # 復華官網通常是給 "股數" (數值很大)，如果是 Yahoo 才是 %
        if etf_code == "00991A":
             # 如果最大值大於 1000，代表抓到的是真實股數，這很棒！
             if df['持有股數'].max() > 1000:
                 print("ℹ️ 成功抓取到真實股數！")
             else:
                 print("ℹ️ 抓取到的是權重(%)")

    required = ['股票代號', '股票名稱', '持有股數']
    # 確保欄位存在
    available = [c for c in required if c in df.columns]
    if len(available) >= 2 and '股票名稱' in df.columns and '持有股數' in df.columns:
        # 如果缺代號，暫時補上 N/A
        if '股票代號' not in df.columns: df['股票代號'] = "N/A"
        return df[['股票代號', '股票名稱', '持有股數']]
    
    return pd.DataFrame()

def process_etf(etf_code, etf_name):
    print(f"\n--- 處理 {etf_name} ({etf_code}) ---")
    df_new = get_etf_data(etf_code)
    
    if df_new.empty: 
        print(f"⚠️ 無法獲取數據，跳過。")
        return ""
    
    today_str = datetime.now().strftime('%Y-%m-%d')
    file_path = f'data/{etf_code}_history.csv'
    
    # 強制轉字串
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
    msg += "\n" + process_etf("00991A", "主動復華未來")
    
    print(msg)

if __name__ == "__main__":
    main()
