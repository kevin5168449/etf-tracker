import pandas as pd
import requests
import os
from datetime import datetime, timedelta
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

def get_roc_date_string(delta_days=0):
    """產生民國日期字串，支援往前推算日期 (例如 delta_days=-1 為昨天)"""
    target_date = datetime.now() + timedelta(days=delta_days)
    roc_year = target_date.year - 1911
    return f"{roc_year}/{target_date.month:02d}/{target_date.day:02d}"

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

# 2. 復華專用：暴力抓取每一行 (Force Row Iteration)
def get_fuhhwa_all_holdings_force(url):
    print(f"🤖 啟動 Chrome 前往復華官網: {url}")
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("user-agent=Mozilla/5.0")

    driver = None
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.get(url)
        
        # 等待表格載入
        print("⏳ 等待表格出現...")
        wait = WebDriverWait(driver, 20)
        # 嘗試定位表格的主體
        table_body = wait.until(EC.presence_of_element_located((By.TAG_NAME, "tbody")))
        time.sleep(3) # 再多等一下讓資料渲染
        
        # ★★★ 關鍵修改：直接抓取所有的 tr (列) ★★★
        rows = table_body.find_elements(By.TAG_NAME, "tr")
        print(f"🔍 偵測到網頁表格共有 {len(rows)} 列資料")
        
        data = []
        for row in rows:
            # 抓取每一列的所有格子 (td)
            cols = row.find_elements(By.TAG_NAME, "td")
            # 復華的表格通常是: [代號, 名稱, 股數, 金額, 權重]
            if len(cols) >= 3:
                row_data = [col.text.strip() for col in cols]
                data.append(row_data)
        
        if data:
            # 手動轉成 DataFrame (這裡假設常見的順序，後續會再根據內容清洗)
            # 先抓第一列判斷欄位數
            num_cols = len(data[0])
            if num_cols == 5:
                columns = ['股票代號', '股票名稱', '持有股數', '金額', '權重']
            else:
                columns = [f'Col_{i}' for i in range(num_cols)]
                
            df = pd.DataFrame(data, columns=columns)
            print(f"✅ 成功暴力提取 {len(df)} 筆資料！")
            return df
            
        return pd.DataFrame()

    except Exception as e:
        print(f"❌ 復華爬蟲失敗: {e}")
        return pd.DataFrame()
    finally:
        if driver: driver.quit()

def get_etf_data(etf_code):
    df = pd.DataFrame()
    
    # === 統一 00981A ===
    if etf_code == "00981A":
        # 嘗試抓取今天
        roc_date = get_roc_date_string(0)
        url = f"https://www.ezmoney.com.tw/ETF/Transaction/PCFExcelNPOI?fundCode=49YTW&date={roc_date}&specificDate=false"
        print(f"📥 下載統一: {url}")
        try:
            res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
            df = smart_read_excel(res.content)
            
            # 如果今天是空的(例如假日)，嘗試抓昨天 (統一通常有留存舊檔)
            if df.empty:
                print("⚠️ 今日無資料，嘗試抓取昨日...")
                roc_date_yest = get_roc_date_string(-1)
                url_yest = f"https://www.ezmoney.com.tw/ETF/Transaction/PCFExcelNPOI?fundCode=49YTW&date={roc_date_yest}&specificDate=false"
                res = requests.get(url_yest, headers={"User-Agent": "Mozilla/5.0"})
                df = smart_read_excel(res.content)
        except Exception as e:
            print(f"❌ 統一失敗: {e}")

    # === 復華 00991A ===
    elif etf_code == "00991A":
        url = "https://www.fhtrust.com.tw/ETF/etf_detail/ETF23#stockhold"
        # 使用新的暴力抓取法
        df = get_fuhhwa_all_holdings_force(url)

    # === 資料清洗 ===
    if df.empty: return pd.DataFrame()

    # 1. 欄位對應
    col_map = {
        '股票代號': ['股票代號', '代號', '證券代號', 'Col_0'], # Col_0 是防呆
        '股票名稱': ['股票名稱', '名稱', '證券名稱', 'Col_1'],
        '持有股數': ['持有股數', '股數', 'Col_2'],
        '權重': ['權重', '權重(%)', '比例', 'Col_4']
    }
    
    for target, cands in col_map.items():
        for cand in cands:
            matches = [c for c in df.columns if str(c).strip() == cand]
            if matches:
                df.rename(columns={matches[0]: target}, inplace=True)
                break
    
    # 2. 數值清洗 (移除逗號、百分比)
    for col in ['持有股數', '權重']:
        if col in df.columns:
            df[col] = df[col].astype(str).str.replace('%', '').str.replace(',', '')
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    # 3. 檢查必要欄位
    # 如果抓下來的是 Col_0, Col_1... 我們需要聰明判斷哪一欄是哪一欄
    # 復華格式通常是: 代號(0), 名稱(1), 股數(2), 金額(3), 權重(4)
    
    required = ['股票代號', '股票名稱', '持有股數']
    
    # 確保欄位都存在，如果缺權重就補0
    if '股票名稱' in df.columns and '持有股數' in df.columns:
        if '股票代號' not in df.columns: df['股票代號'] = "N/A"
        if '權重' not in df.columns: df['權重'] = 0
        
        # 過濾掉可能是標題的行 (例如 "證券代號" 出現在內容裡)
        df = df[df['股票代號'] != '證券代號']
        
        return df[['股票代號', '股票名稱', '持有股數', '權重']]
    
    return pd.DataFrame()

def process_etf(etf_code, etf_name):
    print(f"\n--- 處理 {etf_name} ({etf_code}) ---")
    df_new = get_etf_data(etf_code)
    
    if df_new.empty: 
        print(f"⚠️ 無法獲取數據，跳過。")
        return ""
    
    today_str = datetime.now().strftime('%Y-%m-%d')
    file_path = f'data/{etf_code}_history.csv'
    
    if '股票代號' in df_new.columns:
        df_new['股票代號'] = df_new['股票代號'].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    df_new['Date'] = today_str
    
    mode = 'a' if os.path.exists(file_path) else 'w'
    header = not os.path.exists(file_path)
    df_new.to_csv(file_path, mode=mode, header=header, index=False)
    
    return f"✅ {etf_name} 更新成功 (共 {len(df_new)} 筆)"

def main():
    if not os.path.exists('data'): os.makedirs('data')
    
    msg = process_etf("00981A", "主動統一")
    msg += "\n" + process_etf("00991A", "主動復華未來")
    
    print(msg)

if __name__ == "__main__":
    main()
