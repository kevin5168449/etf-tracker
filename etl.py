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
    """產生民國日期字串，例如: 115/01/06"""
    now = datetime.now()
    roc_year = now.year - 1911
    return f"{roc_year}/{now.month:02d}/{now.day:02d}"

# 1. 統一專用：聰明讀取 Excel
def smart_read_excel(content):
    try:
        # 先偷看前 20 行，找標題在哪
        temp_df = pd.read_excel(io.BytesIO(content), header=None, nrows=20)
        header_row = -1
        for i, row in temp_df.iterrows():
            row_str = row.astype(str).str.cat()
            if "股票代號" in row_str or "Code" in row_str:
                header_row = i
                break
        return pd.read_excel(io.BytesIO(content), header=header_row) if header_row != -1 else pd.DataFrame()
    except: return pd.DataFrame()

# 2. 復華專用：全自動下載/爬取
def get_fuhhwa_all_holdings(url):
    print(f"🤖 啟動 Chrome 前往復華官網: {url}")
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    driver = None
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.get(url)
        
        # 等待網頁載入
        time.sleep(5)
        
        # ★★★ 策略 A：尋找「下載/匯出」連結 (通常包含 .xls, .csv 或 '下載') ★★★
        print("🔍 正在尋找是否有 Excel/CSV 下載連結...")
        try:
            # 尋找頁面上所有可能包含下載連結的元素
            links = driver.find_elements(By.TAG_NAME, "a")
            download_url = None
            
            for link in links:
                href = link.get_attribute("href")
                text = link.text
                # 判斷關鍵字：匯出、下載、PCF、Excel、CSV
                if href and ('.xls' in href or '.csv' in href or 'download' in href.lower() or 'PCF' in text or '匯出' in text or '下載' in text):
                    print(f"🎯 找到潛在下載連結: [{text}] -> {href}")
                    download_url = href
                    # 如果找到明確的 Excel/CSV 檔案，優先使用
                    if '.xls' in href or '.csv' in href:
                        break
            
            if download_url:
                print(f"📥 嘗試直接下載檔案: {download_url}")
                # 使用 requests 下載該檔案
                file_res = requests.get(download_url, headers={"User-Agent": "Mozilla/5.0"})
                if file_res.status_code == 200:
                    try:
                        # 嘗試當作 Excel 讀取
                        print("試著以 Excel 格式解析...")
                        return smart_read_excel(file_res.content)
                    except:
                        # 嘗試當作 CSV 讀取
                        print("試著以 CSV 格式解析...")
                        return pd.read_csv(io.BytesIO(file_res.content))
        except Exception as e:
            print(f"⚠️ 下載策略失敗，轉為抓取頁面表格: {e}")

        # ★★★ 策略 B：如果沒檔案，就暴力爬取網頁上「最大」的表格 ★★★
        # (通常如果沒下載按鈕，網頁上的表格可能是全部顯示，或者需要翻頁，我們先抓當前頁面最大的表格)
        print("🕸️ 沒找到檔案，轉為爬取網頁表格...")
        page_source = driver.page_source
        dfs = pd.read_html(page_source)
        
        best_df = pd.DataFrame()
        max_rows = 0
        
        for temp in dfs:
            # 我們要找包含 "股票名稱" 且 "行數最多" 的那個表格
            cols = str(temp.columns)
            if '股票名稱' in cols or '證券名稱' in cols or '名稱' in cols:
                # 排除只有一兩行的雜訊表格
                if len(temp) > max_rows:
                    max_rows = len(temp)
                    best_df = temp
        
        if not best_df.empty:
            print(f"✅ 成功抓到最大的表格，共 {len(best_df)} 筆資料")
            return best_df
            
        return pd.DataFrame()

    except Exception as e:
        print(f"❌ 復華爬蟲失敗: {e}")
        return pd.DataFrame()
    finally:
        if driver: driver.quit()

def get_etf_data(etf_code):
    df = pd.DataFrame()
    
    # === 統一 00981A (修正代碼為 49YTW) ===
    if etf_code == "00981A":
        roc_date = get_roc_date_string() # 自動產生如 115/01/06
        # 使用您提供的正確網址格式 (注意 fundCode=49YTW)
        url = f"https://www.ezmoney.com.tw/ETF/Transaction/PCFExcelNPOI?fundCode=49YTW&date={roc_date}&specificDate=false"
        print(f"📥 下載統一 (00981A): {url}")
        try:
            res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
            df = smart_read_excel(res.content)
        except Exception as e:
            print(f"❌ 統一失敗: {e}")

    # === 復華 00991A (嘗試抓取全部持股) ===
    elif etf_code == "00991A":
        # 這是復華 ETF23 (00991A) 的詳細頁面
        url = "https://www.fhtrust.com.tw/ETF/etf_detail/ETF23#stockhold"
        print(f"🕷️ 爬取復華 (00991A)...")
        
        df = get_fuhhwa_all_holdings(url)

    # === 資料清洗與標準化 ===
    if df.empty: return pd.DataFrame()

    # 1. 統一欄位名稱
    col_map = {
        '股票代號': ['股票代號', '代號', '股號', 'Symbol', '證券代號'],
        '股票名稱': ['股票名稱', '名稱', '股名', 'Name', '證券名稱', '證券'],
        '持有股數': ['持有股數', '股數', '庫存股數', '權重', '比例', '持股(%)', '持有股數(股)', '股數/單位數']
    }
    for target, cands in col_map.items():
        for cand in cands:
            matches = [c for c in df.columns if str(c).strip() in cands]
            if matches:
                df.rename(columns={matches[0]: target}, inplace=True)
                break
    
    # 2. 數值處理
    if '持有股數' in df.columns:
        df['持有股數'] = df['持有股數'].astype(str).str.replace('%', '').str.replace(',', '')
        df['持有股數'] = pd.to_numeric(df['持有股數'], errors='coerce').fillna(0)

    required = ['股票代號', '股票名稱', '持有股數']
    
    # 如果只有名稱和股數，缺代號，暫時補 N/A (有些官網只有名稱)
    if '股票名稱' in df.columns and '持有股數' in df.columns:
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
