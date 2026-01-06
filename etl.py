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

# --- 設定 Discord Webhook (選填) ---
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK")

def send_discord_notify(msg):
    if not DISCORD_WEBHOOK: return
    data = {"content": msg, "username": "ETF 監控小幫手"}
    try: requests.post(DISCORD_WEBHOOK, json=data)
    except: pass

def get_roc_date_string(delta_days=0):
    """產生民國日期字串，例如 115/01/06"""
    target_date = datetime.now() + timedelta(days=delta_days)
    roc_year = target_date.year - 1911
    return f"{roc_year}/{target_date.month:02d}/{target_date.day:02d}"

# ★★★ 核心大腦：標準化清洗函式 ★★★
def standardize_df(df, source_name=""):
    if df.empty: return df
    
    print(f"🔧 [{source_name}] 原始欄位: {df.columns.tolist()}")
    
    # --- 策略 A: 強制位置對應 (最穩) ---
    # 統一 Excel (00981A) 通常是 4 欄: [代號, 名稱, 股數, 權重]
    if source_name == "00981A" and len(df.columns) >= 4:
        print("🔧 [00981A] 啟用強制位置對應 (4欄模式)...")
        df = df.iloc[:, :4] 
        df.columns = ['股票代號', '股票名稱', '持有股數', '權重']

    # 復華網頁 (00991A) 通常是 5 欄: [代號, 名稱, 股數, 金額, 權重]
    elif source_name == "00991A" and len(df.columns) >= 5:
        print("🔧 [00991A] 啟用強制位置對應 (5欄模式)...")
        # 取第 0, 1, 2, 4 欄
        df = df.iloc[:, [0, 1, 2, 4]]
        df.columns = ['股票代號', '股票名稱', '持有股數', '權重']
        
    # --- 策略 B: 關鍵字搜尋 (備用) ---
    else:
        print("⚠️ 欄位數量不符合預期，轉為關鍵字搜尋...")
        col_map = {
            '股票代號': ['股票代號', '代號', '證券代號', 'Code'],
            '股票名稱': ['股票名稱', '名稱', '證券名稱', 'Name'],
            '持有股數': ['持有股數', '股數', '庫存股數', 'Shares'],
            '權重': ['權重', '權重(%)', '比例', '持股(%)', '持股比率', 'Weight']
        }
        for target, cands in col_map.items():
            for cand in cands:
                matches = [c for c in df.columns if str(c).strip() in cands]
                if matches:
                    df.rename(columns={matches[0]: target}, inplace=True)
                    break

    # --- 策略 C: 數值強力清洗 ---
    for col in ['持有股數', '權重']:
        if col in df.columns:
            # 轉字串 -> 移除 %, ,, - -> 轉數字 -> 補 0
            df[col] = df[col].astype(str).str.replace('%', '').str.replace(',', '').str.replace('-', '0')
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    # --- 策略 D: 最終安檢 ---
    required = ['股票代號', '股票名稱', '持有股數', '權重']
    for req in required:
        if req not in df.columns:
            if req == '權重': df[req] = 0 
            elif req == '股票代號': df[req] = 'N/A'
    
    # 排除標題行 (有些 Excel 第一行是重複標題)
    df = df[df['股票代號'] != '股票代號']
    df = df[df['股票代號'] != '證券代號']

    return df[['股票代號', '股票名稱', '持有股數', '權重']]

# 1. 統一專用：讀取 Excel Response
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

# 2. 復華專用：Selenium 暴力爬蟲 + 瘋狂點擊
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
        print("⏳ 等待網頁載入...")
        time.sleep(8)
        
        # 瘋狂點擊展開
        print("🔍 尋找並點擊「更多」按鈕...")
        max_clicks = 10
        click_count = 0
        while click_count < max_clicks:
            try:
                # 尋找各種可能的「更多」按鈕
                buttons = driver.find_elements(By.XPATH, "//*[contains(text(),'更多') or contains(text(),'全部') or contains(text(),'查閱')]")
                clicked = False
                for btn in buttons:
                    if btn.is_displayed():
                        # 捲動到元素位置
                        driver.execute_script("arguments[0].scrollIntoView(true);", btn)
                        time.sleep(1)
                        # 強制點擊
                        driver.execute_script("arguments[0].click();", btn)
                        print(f"👉 點擊展開 ({click_count+1})...")
                        time.sleep(3) # 等待載入
                        clicked = True
                        click_count += 1
                        break
                if not clicked: break
            except: break

        # 抓取表格
        print("🕸️ 解析網頁表格...")
        dfs = pd.read_html(driver.page_source)
        best_df = pd.DataFrame()
        max_rows = 0
        for temp in dfs:
            # 找列數最多且欄位足夠的表格
            if len(temp) > max_rows and len(temp.columns) >= 3:
                max_rows = len(temp)
                best_df = temp
        
        return best_df
    except Exception as e:
        print(f"❌ 復華爬蟲失敗: {e}")
        return pd.DataFrame()
    finally:
        if driver: driver.quit()

def get_etf_data(etf_code):
    df = pd.DataFrame()
    
    # === 統一 00981A (Excel 下載) ===
    if etf_code == "00981A":
        roc_date = get_roc_date_string(0)
        url = f"https://www.ezmoney.com.tw/ETF/Transaction/PCFExcelNPOI?fundCode=49YTW&date={roc_date}&specificDate=false"
        print(f"📥 下載統一 (00981A): {url}")
        try:
            res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
            df = smart_read_excel(res.content)
            
            # 如果今天沒資料(例如早上或假日)，試試抓昨天
            if df.empty:
                print("⚠️ 今日無資料，嘗試抓取昨日...")
                roc_date_yest = get_roc_date_string(-1)
                url_yest = f"https://www.ezmoney.com.tw/ETF/Transaction/PCFExcelNPOI?fundCode=49YTW&date={roc_date_yest}&specificDate=false"
                res = requests.get(url_yest, headers={"User-Agent": "Mozilla/5.0"})
                df = smart_read_excel(res.content)
        except Exception as e:
            print(f"❌ 統一失敗: {e}")

    # === 復華 00991A (網頁爬蟲) ===
    elif etf_code == "00991A":
        url = "https://www.fhtrust.com.tw/ETF/etf_detail/ETF23#stockhold"
        df = get_fuhhwa_aggressive(url)

    # === 標準化清洗 ===
    return standardize_df(df, source_name=etf_code)

def process_etf(etf_code, etf_name):
    print(f"\n--- 處理 {etf_name} ({etf_code}) ---")
    
    file_path = f'data/{etf_code}_history.csv'
    
    # ★ 自動修復：檢查舊檔是否正常 ★
    if os.path.exists(file_path):
        try:
            # 讀取檢查
            check_df = pd.read_csv(file_path)
            # 檢查 1: 是否缺欄位
            if '權重' not in check_df.columns:
                print(f"🔥 [修復] 舊檔缺欄位，刪除重抓: {file_path}")
                os.remove(file_path)
            # 檢查 2: 權重是否全為 0 (只有當檔案裡有資料時才檢查)
            elif not check_df.empty and '權重' in check_df.columns and check_df['權重'].sum() == 0:
                print(f"🔥 [修復] 舊檔權重異常 (0%)，刪除重抓: {file_path}")
                os.remove(file_path)
        except: pass

    # 獲取新資料
    df_new = get_etf_data(etf_code)
    
    if df_new.empty: 
        print(f"⚠️ 無法獲取數據，跳過。")
        return ""
    
    today_str = datetime.now().strftime('%Y-%m-%d')
    
    # 確保代號是乾淨的字串
    if '股票代號' in df_new.columns:
        df_new['股票代號'] = df_new['股票代號'].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    df_new['Date'] = today_str

    # 存檔 (包含亂碼修復 encoding='utf-8-sig')
    mode = 'a' if os.path.exists(file_path) else 'w'
    header = not os.path.exists(file_path)
    # ★★★ 關鍵設定：encoding='utf-8-sig' 讓 Excel 讀懂中文 ★★★
    df_new.to_csv(file_path, mode=mode, header=header, index=False, encoding='utf-8-sig')
    
    return f"✅ {etf_name} 更新成功 (共 {len(df_new)} 筆)"

def main():
    if not os.path.exists('data'): os.makedirs('data')
    
    msg = process_etf("00981A", "主動統一")
    msg += "\n" + process_etf("00991A", "主動復華未來")
    
    print(msg)

if __name__ == "__main__":
    main()
