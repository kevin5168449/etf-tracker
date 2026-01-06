import pandas as pd
import requests
import os
from datetime import datetime, timedelta
import io
import time
import glob

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

# ★★★ 2. 復華專用：強力點擊下載法 ★★★
def get_fuhhwa_download(url):
    print(f"🤖 啟動 Chrome 前往復華官網: {url}")
    
    # 設定下載路徑為當前目錄
    download_dir = os.getcwd()
    
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    # 關鍵設定：允許 headless 模式下載檔案
    prefs = {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
    }
    chrome_options.add_experimental_option("prefs", prefs)

    driver = None
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.get(url)
        
        # 等待網頁載入
        time.sleep(5)
        
        print("🔍 正在尋找「匯出/下載」按鈕...")
        download_clicked = False
        
        # 嘗試尋找各種可能的下載按鈕 (根據復華官網特性)
        # 策略 1: 找包含 "匯出" 或 "Excel" 的連結或按鈕
        try:
            # 使用 XPath 尋找包含特定文字的元素
            buttons = driver.find_elements(By.XPATH, "//*[contains(text(),'匯出') or contains(text(),'Excel') or contains(text(),'下載')]")
            
            for btn in buttons:
                if btn.is_displayed() and btn.is_enabled():
                    print(f"🎯 找到下載按鈕: {btn.text}")
                    # 使用 JavaScript 強制點擊 (比普通點擊更有效)
                    driver.execute_script("arguments[0].click();", btn)
                    download_clicked = True
                    break
        except Exception as e:
            print(f"⚠️ 策略 1 失敗: {e}")

        # 如果策略 1 沒找到，嘗試策略 2: 找特定的 class (例如 icon-excel)
        if not download_clicked:
            try:
                btns = driver.find_elements(By.CSS_SELECTOR, ".icon-xls, .fa-file-excel")
                if btns:
                    print("🎯 找到 Excel 圖示按鈕，嘗試點擊...")
                    driver.execute_script("arguments[0].click();", btns[0])
                    download_clicked = True
            except: pass

        if not download_clicked:
            print("❌ 找不到下載按鈕，無法取得完整清單。")
            return pd.DataFrame()

        # 等待檔案下載完成
        print("⏳ 等待檔案下載中...")
        time.sleep(10) # 給它一點時間下載
        
        # 搜尋目錄下最新的 .xls 或 .xlsx 檔案
        files = glob.glob(os.path.join(download_dir, "*.xls*")) + glob.glob(os.path.join(download_dir, "*.csv"))
        if not files:
            print("❌ 下載資料夾中沒看到檔案")
            return pd.DataFrame()
            
        # 找到最新的檔案
        latest_file = max(files, key=os.path.getctime)
        print(f"✅ 成功下載檔案: {latest_file}")
        
        # 讀取檔案
        if latest_file.endswith('.csv'):
            return pd.read_csv(latest_file)
        else:
            return pd.read_excel(latest_file)

    except Exception as e:
        print(f"❌ 復華下載失敗: {e}")
        return pd.DataFrame()
    finally:
        if driver: driver.quit()

def get_etf_data(etf_code):
    df = pd.DataFrame()
    
    # === 統一 00981A ===
    if etf_code == "00981A":
        roc_date = get_roc_date_string(0)
        url = f"https://www.ezmoney.com.tw/ETF/Transaction/PCFExcelNPOI?fundCode=49YTW&date={roc_date}&specificDate=false"
        print(f"📥 下載統一: {url}")
        try:
            res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
            df = smart_read_excel(res.content)
            
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
        # 使用新的下載法
        df = get_fuhhwa_download(url)

    # === 資料清洗 ===
    if df.empty: return pd.DataFrame()

    # 1. 欄位對應
    col_map = {
        '股票代號': ['股票代號', '代號', '證券代號', 'Col_0'],
        '股票名稱': ['股票名稱', '名稱', '證券名稱', 'Col_1'],
        '持有股數': ['持有股數', '股數', 'Col_2'],
        '權重': ['權重', '權重(%)', '比例', 'Col_4']
    }
    
    for target, cands in col_map.items():
        for cand in cands:
            matches = [c for c in df.columns if str(c).strip() in cands]
            if matches:
                df.rename(columns={matches[0]: target}, inplace=True)
                break
    
    # 2. 數值清洗
    for col in ['持有股數', '權重']:
        if col in df.columns:
            df[col] = df[col].astype(str).str.replace('%', '').str.replace(',', '')
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    # 3. 確保輸出欄位
    if '股票名稱' in df.columns and '持有股數' in df.columns:
        if '股票代號' not in df.columns: df['股票代號'] = "N/A"
        if '權重' not in df.columns: df['權重'] = 0
        
        # 排除標題行
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
    
    # 強制轉字串
    if '股票代號' in df_new.columns:
        df_new['股票代號'] = df_new['股票代號'].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    df_new['Date'] = today_str

    # 自動修復舊檔
    if os.path.exists(file_path):
        try:
            old_df = pd.read_csv(file_path, nrows=1)
            # 如果資料量變多了 (例如原本10筆，現在50筆)，建議重建以確保資料一致性
            # 或者如果欄位不對，也重建
            if '權重' not in old_df.columns and '權重' in df_new.columns:
                print(f"🧹 偵測到舊檔案格式過時，自動刪除重建: {file_path}")
                os.remove(file_path)
        except: pass

    # 存檔
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
