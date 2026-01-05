import pandas as pd
import requests
import os
from datetime import datetime
import io
import time
import re

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

# ★★★ Yahoo 股市專用爬蟲 ★★★
def get_yahoo_holdings(url):
    print(f"🤖 啟動 Chrome 前往 Yahoo 股市: {url}")
    
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
        # 等待表格出現 (Yahoo 的表格 class 通常包含 'table-body')
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "table-body"))
            )
            print("✅ Yahoo 頁面載入完成")
        except:
            print("⚠️ 等待超時，嘗試直接讀取...")

        page_source = driver.page_source
        return page_source
    except Exception as e:
        print(f"❌ Yahoo 爬取失敗: {e}")
        return None
    finally:
        if driver: driver.quit()

def get_etf_data(etf_code):
    df = pd.DataFrame()
    
    # === 統一 00981A (維持原樣) ===
    if etf_code == "00981A":
        roc_date = get_roc_date_string()
        url = f"https://www.ezmoney.com.tw/ETF/Transaction/PCFExcelNPOI?fundCode=61YTW&date={roc_date}&specificDate=false"
        print(f"📥 下載統一 (00981A): {url}")
        try:
            res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
            df = smart_read_excel(res.content)
        except Exception as e:
            print(f"❌ 統一失敗: {e}")

    # === 野村 00980A (改抓 Yahoo 股市) ===
    elif etf_code == "00980A":
        # Yahoo 股市持股頁面
        url = "https://tw.stock.yahoo.com/quote/00980A/holdings"
        print(f"🕷️ 嘗試抓取 Yahoo 股市 (野村)...")
        
        html_content = get_yahoo_holdings(url)
        
        if html_content:
            try:
                # Yahoo 的表格通常比較亂，我們需要篩選一下
                dfs = pd.read_html(html_content)
                for temp in dfs:
                    # Yahoo 的欄位通常是 "股號", "股名", "比例"
                    if '比例' in temp.columns or '持股(%)' in temp.columns:
                        df = temp
                        print(f"✅ 成功抓到 Yahoo 表格！(共 {len(df)} 筆)")
                        break
            except Exception as e:
                print(f"❌ Yahoo 解析表格失敗: {e}")

    # === 欄位清洗 ===
    if df.empty: return pd.DataFrame()

    # 1. 統一欄位名稱
    col_map = {
        '股票代號': ['股票代號', '代號', '股號', 'Symbol'],
        '股票名稱': ['股票名稱', '名稱', '股名', 'Name'],
        '持有股數': ['持有股數', '股數', '張數', '權重', '比例', '持股(%)'] # Yahoo 用 "比例"
    }
    for target, cands in col_map.items():
        for cand in cands:
            matches = [c for c in df.columns if str(c).strip() == cand]
            if matches:
                df.rename(columns={matches[0]: target}, inplace=True)
                break
    
    # 2. 特殊處理：如果是 Yahoo 抓到的，持有股數欄位其實是 "%"
    if etf_code == "00980A":
        # Yahoo 的 "比例" 欄位可能是字串 "15.00%"，要轉成數字
        if '持有股數' in df.columns:
            df['持有股數'] = df['持有股數'].astype(str).str.replace('%', '').str.replace(',', '')
            df['持有股數'] = pd.to_numeric(df['持有股數'], errors='coerce').fillna(0)
            print("ℹ️ 已將 Yahoo 權重% 轉換為數值，作為比較基準")
            
            # 為了讓 00980A 的圖表不要太小 (跟 00981A 的股數相比)，我們可以把它放大
            # 這裡我們保留原樣，但在 app.py 顯示時要注意它是 %
            # 或者，為了讓圖表好看，我們假設它有 10,000 單位，這樣 bar chart 才會有長度
            # df['持有股數'] = df['持有股數'] * 10000 

    # 3. 處理統一的張數/股數
    elif etf_code == "00981A" and '持有股數' in df.columns:
        df['持有股數'] = pd.to_numeric(df['持有股數'].astype(str).str.replace(',', ''), errors='coerce').fillna(0)

    # 4. 處理股票名稱和代號 (Yahoo 有時候會把 "2330 台積電" 寫在同一格)
    if '股票名稱' in df.columns and '股票代號' not in df.columns:
        # 嘗試從名稱分拆代號
        # 這邊簡單處理，Yahoo 通常是有分開的，如果不分開我們之後再修
        pass

    required = ['股票代號', '股票名稱', '持有股數']
    # 如果 Yahoo 缺代號 (有時候只有名稱)，我們勉強接受
    if '股票名稱' in df.columns and '持有股數' in df.columns:
        if '股票代號' not in df.columns:
             df['股票代號'] = "N/A" # 暫時填入
        return df[['股票代號', '股票名稱', '持有股數']]
    
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
