import time
import os
import re
import pandas as pd
import requests
import json
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

def save_to_csv(etf_code, new_df):
    file_path = f"{DATA_DIR}/{etf_code}_history.csv"
    today_str = get_taiwan_date()
    
    if isinstance(new_df, list): new_df = pd.DataFrame(new_df)
    if 'Date' not in new_df.columns: new_df.insert(0, 'Date', today_str)
    
    # 強制轉型權重為數字
    new_df['權重'] = pd.to_numeric(new_df['權重'], errors='coerce').fillna(0)
    
    if os.path.exists(file_path):
        old_df = pd.read_csv(file_path, dtype=str)
        old_df = old_df[old_df['Date'] != today_str]
        final_df = pd.concat([old_df, new_df], ignore_index=True)
    else:
        final_df = new_df
        
    final_df.to_csv(file_path, index=False, encoding='utf-8-sig')
    print(f"✅ [{etf_code}] 成功儲存 {len(new_df)} 筆資料！")
    return len(new_df)

def clean_column_name(col):
    if isinstance(col, tuple): col = "".join(str(c) for c in col)
    return str(col).strip().replace(" ", "").replace("\n", "")

def clean_cell_data(val):
    """強力清洗：解決疊字、空白、換行"""
    s = str(val).strip()
    # 處理中間有空白的疊字 ("2330 2330")
    parts = s.split()
    if len(parts) == 2 and parts[0] == parts[1]:
        return parts[0]
    # 處理無空白疊字 ("23302330")
    if len(s) > 1 and len(s) % 2 == 0:
        mid = len(s) // 2
        if s[:mid] == s[mid:]:
            return s[:mid]
    return s

# ==========================================
# 00981A: 統一台股增長主動式ETF基金
# ==========================================
def update_00981A():
    # ★★★ 設定正確的中文名稱 ★★★
    TARGET_NAME = "統一台股增長主動式ETF基金"  # <-- 請確認這跟官網選單上的字完全一樣，如果不確定，可用關鍵字如 "台股增長"
    
    print(f"\n🚀 [00981A] 啟動爬蟲：統一投信...")
    url = "https://www.ezmoney.com.tw/ETF/Transaction/PCF"
    driver = get_driver()
    count = 0
    
    try:
        driver.get(url)
        time.sleep(5)
        
        # --- 步驟 1: 切換選單 ---
        print(f"👆 正在尋找基金：{TARGET_NAME}...")
        found = False
        try:
            # 找到頁面上所有下拉選單
            selects = driver.find_elements(By.TAG_NAME, "select")
            for el in selects:
                try:
                    select = Select(el)
                    # 遍歷選項找目標
                    for opt in select.options:
                        # 使用模糊比對，只要包含關鍵字就選
                        if "台股增長" in opt.text and "主動" in opt.text:
                            print(f"🎯 找到目標：{opt.text}")
                            select.select_by_visible_text(opt.text)
                            found = True
                            time.sleep(5) # 等待重新載入
                            break
                except: pass
                if found: break
            
            if not found:
                print("⚠️ 警告：選單中找不到該基金，將抓取預設值。")
                # 印出所有選項供除錯
                if selects:
                    print("可選基金列表:", [o.text for o in Select(selects[0]).options][:5], "...")
        except Exception as e:
            print(f"⚠️ 選單切換失敗: {e}")

        # --- 步驟 2: 抓取表格 ---
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
            # 全面清洗
            for col in target_df.columns:
                target_df[col] = target_df[col].apply(clean_cell_data)
                
            target_df['持有股數'] = target_df['持有股數'].astype(str).str.replace(',', '').str.replace('--', '0')
            target_df['權重'] = target_df['權重'].astype(str).str.replace('%', '')
            count = save_to_csv("00981A", target_df)
        else:
            print("❌ [00981A] 找不到表格")

    except Exception as e:
        print(f"❌ [00981A] 錯誤: {e}")
    finally:
        driver.quit()
    return count

# ==========================================
# 00991A: 復華未來50 (主動復華未來50)
# ==========================================
def update_00991A():
    # ★★★ 設定正確的中文名稱 ★★★
    # 復華網址通常是直接帶入參數，或者要選單
    # 這裡我們使用通用的復華 PCF 頁面，然後嘗試選單
    TARGET_NAME = "復華未來50" # 請確認關鍵字
    
    print(f"\n🚀 [00991A] 啟動爬蟲：復華投信 ({TARGET_NAME})...")
    # 復華主動式 ETF 列表頁面
    url = "https://www.fhtrust.com.tw/ETF/etf_detail/ETF23#stockhold" 
    # 註：復華的網址通常是固定的 (ETFxx)，如果不確定 00991A 對應哪個 ID
    # 建議先用上面這個通用頁面，然後看能不能選
    
    driver = get_driver()
    count = 0
    
    try:
        driver.get(url)
        time.sleep(5)
        
        # --- 步驟 1: 嘗試切換基金 (如果網頁有提供切換) ---
        # 復華的頁面結構比較複雜，有些是上方有 Tab 或 Dropdown
        # 如果是單一頁面網址，則不需要切換。
        # 假設 00991A 有獨立網址，請在此替換 url
        
        # --- 步驟 2: 點擊展開 (維持之前成功的邏輯) ---
        try:
            target_div = driver.find_element(By.ID, "stockhold")
            driver.execute_script("arguments[0].scrollIntoView(true);", target_div)
            time.sleep(2)
        except: pass

        print("👆 尋找「更多」按鈕...")
        clicked = False
        try:
            xpath = "//*[contains(text(),'更多') or contains(text(),'展開') or contains(text(),'查閱全部')]"
            buttons = driver.find_elements(By.XPATH, xpath)
            for btn in buttons:
                if btn.is_displayed():
                    driver.execute_script("arguments[0].click();", btn)
                    time.sleep(1)
                    try: ActionChains(driver).move_to_element(btn).click().perform()
                    except: pass
                    clicked = True
                    break
        except: pass

        # --- 步驟 3: 驗收等待 ---
        print("⏳ 等待資料載入...")
        best_df = pd.DataFrame()
        for _ in range(10):
            try:
                html = driver.page_source
                dfs = pd.read_html(html)
                current_best = pd.DataFrame()
                max_rows = 0
                for df in dfs:
                    df.columns = [clean_column_name(c) for c in df.columns]
                    cols = "".join(df.columns)
                    if ("名稱" in cols or "代號" in cols) and ("權重" in cols or "比例" in cols):
                        if len(df) > max_rows:
                            max_rows = len(df)
                            current_best = df.copy()
                
                if max_rows > 15:
                    best_df = current_best
                    print(f"🌟 抓到完整清單：{max_rows} 筆")
                    break
                if max_rows > 0: best_df = current_best
                time.sleep(2)
            except: pass

        if not best_df.empty:
            rename_map = {}
            for c in best_df.columns:
                if "代號" in c: rename_map[c] = "股票代號"
                elif "名稱" in c: rename_map[c] = "股票名稱"
                elif "股數" in c: rename_map[c] = "持有股數"
                elif "權重" in c or "比例" in c: rename_map[c] = "權重"
            
            best_df = best_df.rename(columns=rename_map)
            if "股票名稱" in best_df.columns:
                if "股票代號" not in best_df.columns: best_df["股票代號"] = best_df["股票名稱"]
                if "持有股數" not in best_df.columns: best_df["持有股數"] = 0
                
                best_df = best_df[['股票代號', '股票名稱', '持有股數', '權重']]
                # 全面清洗
                for col in best_df.columns:
                    best_df[col] = best_df[col].apply(clean_cell_data)
                
                best_df['權重'] = best_df['權重'].astype(str).str.replace('%', '')
                count = save_to_csv("00991A", best_df)
        else:
            print("❌ [00991A] 找不到表格")

    except Exception as e:
        print(f"❌ [00991A] 錯誤: {e}")
    finally:
        driver.quit()
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
    
    today = get_taiwan_date()
    msg = f"📢 **{today} ETF 持股更新報告**\n"
    msg += f"✅ **00981A (統一)**: 更新 {c1} 筆\n" if c1 > 0 else f"⚠️ **00981A**: 失敗\n"
    msg += f"✅ **00991A (復華)**: 更新 {c2} 筆\n" if c2 > 0 else f"⚠️ **00991A**: 失敗\n"
    
    send_discord_notify(msg)
    print("=== 更新結束 ===")
