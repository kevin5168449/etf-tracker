import pandas as pd
import requests
import os
from datetime import datetime, timedelta
import io
import time
import shutil

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

# ★★★ 2. 復華專用：自動點擊「查閱更多」 ★★★
def get_fuhhwa_expand_and_scrape(url):
    print(f"🤖 啟動 Chrome 前往復華官網: {url}")
    
    chrome_options = Options()
    chrome_options.add_argument("--headless") # 無頭模式
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
        
        # --- 關鍵動作：尋找並點擊「更多」按鈕 ---
        print("🔍 尋找「查閱更多 / 顯示全部」按鈕...")
        try:
            # 使用 XPath 尋找包含關鍵字的按鈕或連結
            # 關鍵字：查閱更多, 顯示更多, 載入更多, More, All
            buttons = driver.find_elements(By.XPATH, "//*[contains(text(),'查閱更多') or contains(text(),'顯示更多') or contains(text(),'更多資料') or contains(text(),'顯示全部')]")
            
            clicked = False
            for btn in buttons:
                if btn.is_displayed():
                    print(f"👉 嘗試點擊按鈕: [{btn.text}]")
                    # 使用 JavaScript 強制點擊 (最穩)
                    driver.execute_script("arguments[0].click();", btn)
                    clicked = True
                    time.sleep(3) # 等它展開
            
            if not clicked:
                print("⚠️ 未發現明顯的展開按鈕，將直接抓取當前表格 (可能只有前10筆)")
            else:
                print("✅ 已點擊展開按鈕！")
                
        except Exception as e:
            print(f"⚠️ 點擊展開時發生小錯誤 (不影響後續嘗試): {e}")

        # --- 開始抓取表格 ---
        print("🕸️ 開始解析網頁表格...")
        # 重新取得網頁原始碼 (包含展開後的內容)
        page_source = driver.page_source
        dfs = pd.read_html(page_source)
        
        best_df = pd.DataFrame()
        max_rows = 0
        
        for temp in dfs:
            # 尋找包含 "股票名稱" 且 "行數最多" 的表格
            cols = str(temp.columns)
            if '股票名稱' in cols or '證券名稱' in cols or '名稱' in cols:
                # 排除過小的表格
                if len(temp) > max_rows:
                    max_rows = len(temp)
                    best_df = temp
        
        if not best_df.empty:
            print(f"✅ 成功抓到表格，共 {len(best_df)} 筆資料 (若 >10 筆代表展開成功)")
            return best_df
            
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
        # 使用「點擊展開」法
        df = get_fuhhwa_expand_and_scrape(url)

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

    # 3. 確保輸出
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

    # ★★★ 自動修復邏輯 (關鍵) ★★★
    # 如果舊檔案存在，檢查它是否有「權重」欄位
    # 如果沒有，代表是舊格式，必須刪除重建，否則 app.py 會報錯或顯示 0%
    if os.path.exists(file_path):
        try:
            old_df = pd.read_csv(file_path, nrows=1)
            if '權重' not in old_df.columns and '權重' in df_new.columns:
                print(f"🧹 偵測到舊檔案缺少「權重」欄位，自動刪除重建: {file_path}")
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
