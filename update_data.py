import time
import os
import re
import pandas as pd
import requests
import json
import math
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# --- 設定 ---
DATA_DIR = "data"
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

def get_taiwan_date():
    return (datetime.utcnow() + timedelta(hours=8)).strftime('%Y-%m-%d')

def get_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36")
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=chrome_options)

def clean_column_name(col):
    if isinstance(col, tuple): col = "".join(str(c) for c in col)
    return str(col).strip().replace(" ", "").replace("\n", "")

def clean_cell_data(val):
    s = str(val).strip()
    parts = s.split()
    if len(parts) == 2 and parts[0] == parts[1]:
        return parts[0]
    if len(s) > 1 and len(s) % 2 == 0:
        mid = len(s) // 2
        if s[:mid] == s[mid:]:
            return s[:mid]
    return s

# --- 核心存檔與防呆邏輯 ---
def save_to_csv(etf_code, new_df):
    file_path = f"{DATA_DIR}/{etf_code}_history.csv"
    today_str = get_taiwan_date()
    
    if isinstance(new_df, list): new_df = pd.DataFrame(new_df)
    
    # 統一欄位型態
    new_df['權重'] = pd.to_numeric(new_df['權重'], errors='coerce').fillna(0)
    new_df['持有股數'] = pd.to_numeric(new_df['持有股數'], errors='coerce').fillna(0)
    
    # 檢查是否已存在
    if os.path.exists(file_path):
        old_df = pd.read_csv(file_path)
        
        # 1. 檢查今天是否已經存過了
        if today_str in old_df['Date'].values:
            print(f"⚠️ [{etf_code}] 今天 ({today_str}) 已經有資料了，覆蓋更新...")
            old_df = old_df[old_df['Date'] != today_str]
        
        # 2. ★★★ 核心防呆：檢查是否跟「上一筆資料」完全一樣 ★★★
        # 取出最近的一天
        if not old_df.empty:
            last_date = old_df['Date'].max()
            last_record = old_df[old_df['Date'] == last_date].copy()
            
            # 進行比對 (只比對股票代號和權重，因為權重隨股價波動，不可能完全一樣)
            # 先排序確保順序一致
            new_check = new_df.sort_values('股票代號')[['股票代號', '權重']].reset_index(drop=True)
            old_check = last_record.sort_values('股票代號')[['股票代號', '權重']].reset_index(drop=True)
            
            # 如果筆數一樣 且 內容完全一樣
            if len(new_check) == len(old_check):
                try:
                    # 比較 DataFrame 是否相等
                    if new_check.equals(old_check):
                        print(f"⛔ [{etf_code}] 警告：抓到的資料與 {last_date} 完全一致！")
                        print("⛔ 判定網站尚未更新數據，本次 **不予存檔**。")
                        return 0
                except: pass

        # 加入日期並存檔
        new_df.insert(0, 'Date', today_str)
        final_df = pd.concat([old_df, new_df], ignore_index=True)
    else:
        new_df.insert(0, 'Date', today_str)
        final_df = new_df
        
    final_df.to_csv(file_path, index=False, encoding='utf-8-sig')
    print(f"✅ [{etf_code}] 成功儲存 {len(new_df)} 筆資料！")
    return len(new_df)

# ==========================================
# 00981A: 統一台股增長
# ==========================================
def update_00981A():
    TARGET_NAME = "統一台股增長主動式ETF基金" 
    print(f"\n🚀 [00981A] 啟動爬蟲：統一投信...")
    url = "https://www.ezmoney.com.tw/ETF/Transaction/PCF"
    driver = get_driver()
    count = 0
    try:
        driver.get(url)
        time.sleep(5)
        found = False
        try:
            selects = driver.find_elements(By.TAG_NAME, "select")
            for el in selects:
                try:
                    select = Select(el)
                    for opt in select.options:
                        if "台股增長" in opt.text and "主動" in opt.text:
                            select.select_by_visible_text(opt.text)
                            found = True
                            time.sleep(5)
                            break
                except: pass
                if found: break
        except: pass

        html = driver.page_source
        dfs = pd.read_html(html)
        target_df = pd.DataFrame()
        for df in dfs:
            df.columns = [clean_column_name(c) for c in df.columns]
            cols = "".join(df.columns)
            if ("代號" in cols or "名稱" in cols) and ("權重" in cols or "比重" in cols):
                rename_map = {}
                for c in df.columns:
                    if "代號" in c: rename_map[c] = "股票代號"
                    elif "名稱" in c: rename_map[c] = "股票名稱"
                    elif "股數" in c: rename_map[c] = "持有股數"
                    elif "權重" in c or "比重" in c: rename_map[c] = "權重"
                df = df.rename(columns=rename_map)
                if "股票名稱" in df.columns and "權重" in df.columns:
                    target_df = df.copy()
                    if "股票代號" not in target_df.columns: target_df["股票代號"] = target_df["股票名稱"]
                    if "持有股數" not in target_df.columns: target_df["持有股數"] = 0
                    break
        if not target_df.empty:
            target_df = target_df[['股票代號', '股票名稱', '持有股數', '權重']]
            for col in target_df.columns: target_df[col] = target_df[col].apply(clean_cell_data)
            target_df['持有股數'] = target_df['持有股數'].astype(str).str.replace(',', '').str.replace('--', '0')
            target_df['權重'] = target_df['權重'].astype(str).str.replace('%', '')
            count = save_to_csv("00981A", target_df)
        else: print("❌ [00981A] 找不到表格")
    except Exception as e: print(f"❌ [00981A] 錯誤: {e}")
    finally: driver.quit()
    return count

# ==========================================
# 00980A: 野村 (V23 修正版)
# ==========================================
def update_00980A():
    print(f"\n🚀 [00980A] 啟動爬蟲：野村投信...")
    url = "https://www.nomurafunds.com.tw/ETFWEB/product-description?fundNo=00980A"
    driver = get_driver()
    count = 0
    try:
        driver.get(url)
        time.sleep(8)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
        time.sleep(2)
        try:
            tabs = driver.find_elements(By.XPATH, "//*[contains(text(),'持股') or contains(text(),'成分')]")
            for tab in tabs:
                if tab.is_displayed():
                    driver.execute_script("arguments[0].click();", tab)
                    time.sleep(2)
                    break
        except: pass
        try:
            xpath = "//*[contains(text(),'查看更多') or contains(text(),'顯示全部')]"
            elements = driver.find_elements(By.XPATH, xpath)
            for el in elements:
                if el.is_displayed():
                    driver.execute_script("arguments[0].click();", el)
                    time.sleep(3)
        except: pass

        best_df = pd.DataFrame()
        for _ in range(5):
            try:
                html = driver.page_source
                dfs = pd.read_html(html)
                for df in dfs:
                    df.columns = [clean_column_name(c) for c in df.columns]
                    cols = "".join(df.columns)
                    if ("名稱" in cols or "代號" in cols) and ("權重" in cols):
                        if '股票名稱' in df.columns:
                            df = df[~df['股票名稱'].astype(str).str.contains('查看更多|更多')]
                        if len(df) > len(best_df): best_df = df.copy()
            except: pass
            time.sleep(1)

        if not best_df.empty:
            rename_map = {}
            for c in best_df.columns:
                if "代號" in c: rename_map[c] = "股票代號"
                elif "名稱" in c: rename_map[c] = "股票名稱"
                elif "股數" in c: rename_map[c] = "持有股數"
                elif "權重" in c: rename_map[c] = "權重"
            best_df = best_df.rename(columns=rename_map)
            
            if "股票名稱" in best_df.columns:
                if "股票代號" not in best_df.columns: best_df["股票代號"] = best_df["股票名稱"]
                if "持有股數" not in best_df.columns: best_df["持有股數"] = 0
                best_df = best_df[['股票代號', '股票名稱', '持有股數', '權重']]
                best_df = best_df[~best_df['股票名稱'].str.contains('查看更多|更多')]
                for col in best_df.columns: best_df[col] = best_df[col].apply(clean_cell_data)
                best_df['權重'] = best_df['權重'].astype(str).str.replace('%', '')
                count = save_to_csv("00980A", best_df)
        else: print("❌ [00980A] 找不到表格")
    except Exception as e: print(f"❌ 錯誤: {e}")
    finally: driver.quit()
    return count

# ==========================================
# 00991A: 復華 (V28 狙擊手版)
# ==========================================
def update_00991A():
    TARGET_NAME = "復華未來50"
    print(f"\n🚀 [00991A] 啟動爬蟲：復華投信 ({TARGET_NAME})...")
    url = "https://www.fhtrust.com.tw/ETF/etf_detail/ETF23"
    driver = get_driver()
    count = 0
    try:
        driver.get(url)
        print("💤 等待網頁載入...")
        try:
            WebDriverWait(driver, 25).until(
                EC.presence_of_element_located((By.XPATH, "//*[contains(text(),'證券代號') or contains(text(),'證券名稱')]"))
            )
        except:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(3)
        
        driver.execute_script("window.scrollTo(0, 800);")
        time.sleep(2)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)

        try:
            expand_btn = driver.find_elements(By.XPATH, "//*[contains(text(),'展開更多')]")
            if expand_btn:
                driver.execute_script("arguments[0].click();", expand_btn[0])
                time.sleep(5)
        except: pass

        print("⏳ 啟動資料抓取...")
        best_df = pd.DataFrame()
        try:
            rows = driver.find_elements(By.XPATH, "//table//tr")
            if len(rows) < 5:
                time.sleep(5)
                rows = driver.find_elements(By.XPATH, "//table//tr")

            data = []
            for row in rows:
                row_text = driver.execute_script("return arguments[0].innerText;", row).strip()
                if row_text and any(char.isdigit() for char in row_text):
                    parts = row_text.replace('\t', '\n').split('\n')
                    parts = [p.strip() for p in parts if p.strip() != ""]
                    if len(parts) >= 3:
                        data.append(parts)

            if len(data) > 0:
                processed_data = []
                for parts in data:
                    code = next((p for p in parts if p.isdigit() and len(p) == 4), None)
                    weight = next((p for p in parts if '%' in p), "0")
                    name = "未知"
                    if code:
                        try:
                            idx = parts.index(code)
                            if idx + 1 < len(parts): name = parts[idx+1]
                        except: pass
                    shares = "0"
                    for p in parts:
                        if ',' in p and '%' not in p:
                            shares = p
                            break
                    if code and name:
                        processed_data.append([code, name, shares, weight])

                if len(processed_data) > 0:
                    best_df = pd.DataFrame(processed_data, columns=['股票代號', '股票名稱', '持有股數', '權重'])
        except Exception as e: print(f"❌ 失敗: {e}")

        if not best_df.empty:
            if len(best_df) < 15:
                print(f"⛔ [失敗] 只抓到 {len(best_df)} 筆。拒絕存檔！")
                return 0
            best_df = best_df.drop_duplicates(subset=['股票代號'])
            best_df['持有股數'] = best_df['持有股數'].astype(str).str.replace(',', '').str.replace('--', '0')
            best_df['權重'] = best_df['權重'].astype(str).str.replace('%', '')
            count = save_to_csv("00991A", best_df)
        else: print("❌ 找不到資料")
    except Exception as e: print(f"❌ 錯誤: {e}")
    finally: driver.quit()
    return count

# ==========================================
# Discord 推播
# ==========================================
def send_discord_notify(message):
    webhook_url = os.environ.get("DISCORD_WEBHOOK")
    if not webhook_url: return
    data = {"username": "🦁 ETF 戰情室", "content": message}
    try: requests.post(webhook_url, json=data)
    except: pass

if __name__ == "__main__":
    print("=== 開始自動更新 ===")
    c1 = update_00981A()
    c2 = update_00991A()
    c3 = update_00980A()
    
    today = get_taiwan_date()
    msg = f"📢 **{today} ETF 持股更新報告**\n"
    msg += f"✅ **00981A (統一)**: 更新 {c1} 筆\n" if c1 > 0 else f"⚠️ **00981A**: 未更新/失敗\n"
    msg += f"✅ **00991A (復華)**: 更新 {c2} 筆\n" if c2 > 0 else f"⚠️ **00991A**: 未更新/失敗\n"
    msg += f"✅ **00980A (野村)**: 更新 {c3} 筆\n" if c3 > 0 else f"⚠️ **00980A**: 未更新/失敗\n"
    
    send_discord_notify(msg)
    print("=== 更新結束 ===")
