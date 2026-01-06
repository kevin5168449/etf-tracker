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

# ★★★ 2. 復華專用：暴力位置抓取 & 瘋狂點擊 ★★★
def get_fuhhwa_aggressive(url):
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
        print("⏳ 等待網頁載入...")
        time.sleep(8)
        
        # --- 策略：瘋狂點擊「更多」直到不能點為止 ---
        print("🔍 開始尋找並點擊「更多」按鈕...")
        max_clicks = 10 # 最多點 10 次防止無窮迴圈
        click_count = 0
        
        while click_count < max_clicks:
            try:
                # 尋找所有可能的按鈕
                buttons = driver.find_elements(By.XPATH, "//*[contains(text(),'更多') or contains(text(),'全部') or contains(text(),'查閱')]")
                clicked_in_this_round = False
                
                for btn in buttons:
                    if btn.is_displayed():
                        # 滾動到按鈕位置 (防止被擋住)
                        driver.execute_script("arguments[0].scrollIntoView(true);", btn)
                        time.sleep(1)
                        # 強制點擊
                        driver.execute_script("arguments[0].click();", btn)
                        print(f"👉 第 {click_count+1} 次點擊展開...")
                        time.sleep(3) # 等待資料載入
                        clicked_in_this_round = True
                        click_count += 1
                        break # 一次迴圈只點一個，重新抓取元素避免 stale element
                
                if not clicked_in_this_round:
                    print("✅ 沒有更多按鈕可點了，停止展開。")
                    break
            except Exception as e:
                print(f"⚠️ 點擊過程小插曲: {e}")
                break

        # --- 抓取表格 ---
        print("🕸️ 開始解析網頁表格...")
        page_source = driver.page_source
        dfs = pd.read_html(page_source)
        
        best_df = pd.DataFrame()
        max_rows = 0
        
        for temp in dfs:
            # 優先找列數最多的表格
            if len(temp) > max_rows:
                # 簡單檢查欄位數，通常是 5 欄 (代號/名稱/股數/金額/權重)
                if len(temp.columns) >= 3: 
                    max_rows = len(temp)
                    best_df = temp
        
        if not best_df.empty:
            print(f"✅ 成功抓到表格！共 {len(best_df)} 筆資料 (欄位: {best_df.columns.tolist()})")
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
        df = get_fuhhwa_aggressive(url)

    # === 資料清洗與強制對應 ===
    if df.empty: return pd.DataFrame()

    # ★★★ 關鍵修改：優先使用位置 (Index) 對應 ★★★
    # 如果表格有 5 欄，不管標題叫什麼，我們強制認定：
    # Col 0: 代號, Col 1: 名稱, Col 2: 股數, Col 4: 權重
    if len(df.columns) == 5:
        print("🔧 偵測到 5 欄表格，啟用強制位置對應...")
        df.columns = ['股票代號', '股票名稱', '持有股數', '金額', '權重']
    else:
        # 如果不是 5 欄，嘗試用關鍵字找
        col_map = {
            '股票代號': ['股票代號', '代號', '證券代號'],
            '股票名稱': ['股票名稱', '名稱', '證券名稱'],
            '持有股數': ['持有股數', '股數'],
            '權重': ['權重', '權重(%)', '比例', '持股(%)', '持股比率']
        }
        for target, cands in col_map.items():
            for cand in cands:
                matches = [c for c in df.columns if str(c).strip() in cands]
                if matches:
                    df.rename(columns={matches[0]: target}, inplace=True)
                    break

    # 數值清洗
    for col in ['持有股數', '權重']:
        if col in df.columns:
            # 先轉字串，處理特殊符號，再轉數字
            df[col] = df[col].astype(str).str.replace('%', '').str.replace(',', '').str.replace('-', '0')
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    # 確保輸出
    if '股票名稱' in df.columns and '持有股數' in df.columns:
        if '股票代號' not in df.columns: df['股票代號'] = "N/A"
        if '權重' not in df.columns: df['權重'] = 0 # 如果真的沒抓到，至少補0
        
        # 排除可能是標題的行
        df = df[df['股票代號'] != '證券代號']
        
        return df[['股票代號', '股票名稱', '持有股數', '權重']]
    
    return pd.DataFrame()

def process_etf(etf_code, etf_name):
    print(f"\n--- 處理 {etf_name} ({etf_code}) ---")
    
    # 強制刪除舊檔以防格式衝突
    file_path = f'data/{etf_code}_history.csv'
    if etf_code == "00991A" and os.path.exists(file_path):
        try:
            # 讀取檢查，如果權重是0，就刪掉重跑
            check_df = pd.read_csv(file_path)
            if '權重' in check_df.columns and check_df['權重'].sum() == 0:
                print(f"🔥 偵測到權重資料異常 (全為0)，刪除重抓: {file_path}")
                os.remove(file_path)
        except: pass

    df_new = get_etf_data(etf_code)
    
    if df_new.empty: 
        print(f"⚠️ 無法獲取數據，跳過。")
        return ""
    
    today_str = datetime.now().strftime('%Y-%m-%d')
    
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
