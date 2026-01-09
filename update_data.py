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
# 00981A: 統一台股增長 (選單選取版)
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
        # 切換選單
        print(f"👆 尋找基金：{TARGET_NAME}...")
        found = False
        try:
            selects = driver.find_elements(By.TAG_NAME, "select")
            for el in selects:
                try:
                    select = Select(el)
                    for opt in select.options:
                        if "台股增長" in opt.text and "主動" in opt.text:
                            print(f"🎯 找到目標：{opt.text}")
                            select.select_by_visible_text(opt.text)
                            found = True
                            time.sleep(5)
                            break
                except: pass
                if found: break
            if not found: print("⚠️ 警告：選單中找不到該基金，將抓取預設值。")
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
# 00980A: 野村臺灣智慧優選 (V12 查看更多修正版)
# ==========================================
def update_00980A():
    print(f"\n🚀 [00980A] 啟動爬蟲：野村投信 (00980A)...")
    url = "https://www.nomurafunds.com.tw/ETFWEB/product-description?fundNo=00980A"
    driver = get_driver()
    count = 0
    
    try:
        driver.get(url)
        time.sleep(8)
        
        # 1. 暴力捲動喚醒
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
        time.sleep(1)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        
        # 2. 切換分頁 (持股權重)
        try:
            tabs = driver.find_elements(By.XPATH, "//*[contains(text(),'持股') or contains(text(),'成分')]")
            for tab in tabs:
                if tab.is_displayed():
                    driver.execute_script("arguments[0].click();", tab)
                    time.sleep(2)
                    break
        except: pass

        # 3. ★★★ 關鍵修正：針對「查看更多」文字點擊 ★★★
        print("👆 尋找「查看更多」按鈕...")
        try:
            # 野村的按鈕常常就是表格的最後一列，裡面寫著「查看更多」
            # 我們直接找包含這四個字的元素
            xpath = "//*[contains(text(),'查看更多') or contains(text(),'顯示全部')]"
            elements = driver.find_elements(By.XPATH, xpath)
            for el in elements:
                if el.is_displayed():
                    print(f"   🎯 點擊：{el.text}")
                    driver.execute_script("arguments[0].click();", el)
                    time.sleep(3) # 點完要等一下
                    break
        except Exception as e:
            print(f"⚠️ 點擊失敗: {e}")

        # 4. 抓取表格
        print("⏳ 讀取表格中...")
        best_df = pd.DataFrame()
        # 嘗試多次，等待資料展開
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
                        # ★★★ 過濾掉「查看更多」這種垃圾行 ★★★
                        # 如果某一行的「股票名稱」包含「查看更多」，就不要算它
                        if '股票名稱' in df.columns:
                            df = df[~df['股票名稱'].astype(str).str.contains('查看更多|更多')]
                        
                        if len(df) > max_rows:
                            max_rows = len(df)
                            current_best = df.copy()
                
                print(f"   目前最大行數: {max_rows}")
                if max_rows > 15: # 只要大於 15 筆就當作成功
                    best_df = current_best
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
                
                # 最後再清洗一次，確保沒有「查看更多」殘留
                best_df = best_df[~best_df['股票名稱'].astype(str).str.contains('查看更多')]
                best_df = best_df[~best_df['股票代號'].astype(str).str.contains('查看更多')]

                # 清洗數據
                for col in best_df.columns: best_df[col] = best_df[col].apply(clean_cell_data)
                best_df['權重'] = best_df['權重'].astype(str).str.replace('%', '')
                
                count = save_to_csv("00980A", best_df)
            else: print("❌ [00980A] 欄位錯誤")
        else:
            print("❌ [00980A] 找不到表格")

    except Exception as e:
        print(f"❌ [00980A] 錯誤: {e}")
    finally:
        driver.quit()
    return count

# ==========================================
# 00991A: 復華未來50 (V21 死纏爛打重試版)
# ==========================================
def update_00991A():
    TARGET_NAME = "復華未來50"
    print(f"\n🚀 [00991A] 啟動爬蟲：復華投信 ({TARGET_NAME})...")
    url = "https://www.fhtrust.com.tw/ETF/etf_detail/ETF23"
    
    # 內部函式：執行一次完整的抓取流程
    def run_scrape_attempt(driver):
        try:
            driver.get(url)
            time.sleep(10) # 基礎等待
            
            # 1. 喚醒頁面
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
            time.sleep(2)
            
            # 2. 定位區塊
            try:
                xpath = "//*[contains(text(),'持股權重') or contains(text(),'基金持股') or @id='stockhold']"
                target = driver.find_element(By.XPATH, xpath)
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", target)
                time.sleep(2)
            except: pass

            # 3. 尋找並點擊按鈕 (嘗試多種選擇器)
            print("   👆 尋找展開按鈕...")
            try:
                # 找出所有可能的按鈕
                buttons = driver.find_elements(By.XPATH, "//*[contains(text(),'更多') or contains(text(),'展開') or contains(@class, 'more')]")
                
                clicked = False
                for btn in buttons:
                    if btn.is_displayed():
                        # 使用 JS 強制點擊 (穿透遮擋)
                        driver.execute_script("arguments[0].click();", btn)
                        clicked = True
                        print(f"   🎯 點擊了: {btn.text}")
                        time.sleep(1) # 點一下等一下
                
                if clicked:
                    print("   ⏳ 點擊完成，等待資料載入 (10秒)...")
                    time.sleep(10)
                else:
                    print("   ⚠️ 沒找到按鈕，可能已展開或被遮擋")
            except Exception as e:
                print(f"   ⚠️ 點擊錯誤: {e}")

            # 4. 抓取資料
            best_df = pd.DataFrame()
            html = driver.page_source
            dfs = pd.read_html(html)
            
            for df in dfs:
                df.columns = [clean_column_name(c) for c in df.columns]
                cols = "".join(df.columns)
                if ("名稱" in cols or "代號" in cols) and ("權重" in cols or "比例" in cols):
                    if len(df) > len(best_df):
                        best_df = df.copy()
            
            return best_df

        except Exception as e:
            print(f"   ❌ 發生錯誤: {e}")
            return pd.DataFrame()

    # --- 主流程：最多嘗試 3 次 ---
    driver = get_driver()
    final_df = pd.DataFrame()
    
    for attempt in range(1, 4): # 嘗試第 1, 2, 3 次
        print(f"🔄 第 {attempt} 次嘗試抓取...")
        current_df = run_scrape_attempt(driver)
        
        if not current_df.empty and len(current_df) > 20:
            print(f"🌟 成功！抓到 {len(current_df)} 筆資料！")
            final_df = current_df
            break # 成功就跳出迴圈
        else:
            print(f"⚠️ 第 {attempt} 次失敗 (只抓到 {len(current_df)} 筆)，準備重試...")
            driver.delete_all_cookies() # 清除 Cookie 避免被舊狀態卡住
            time.sleep(5) # 休息一下再試

    driver.quit()

    # --- 結算與存檔 ---
    if not final_df.empty and len(final_df) > 20:
        rename_map = {}
        for c in final_df.columns:
            if "代號" in c: rename_map[c] = "股票代號"
            elif "名稱" in c: rename_map[c] = "股票名稱"
            elif "股數" in c: rename_map[c] = "持有股數"
            elif "權重" in c: rename_map[c] = "權重"
        
        final_df = final_df.rename(columns=rename_map)
        if "股票名稱" in final_df.columns:
            if "股票代號" not in final_df.columns: final_df["股票代號"] = final_df["股票名稱"]
            if "持有股數" not in final_df.columns: final_df["持有股數"] = 0
            
            final_df = final_df[['股票代號', '股票名稱', '持有股數', '權重']]
            # 清洗
            for col in final_df.columns: final_df[col] = final_df[col].apply(clean_cell_data)
            final_df['權重'] = final_df['權重'].astype(str).str.replace('%', '')
            
            return save_to_csv("00991A", final_df)
    
    print("❌ [00991A] 三次嘗試皆失敗，放棄更新 (保留舊資料以策安全)")
    return 0
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
    msg += f"✅ **00981A (統一)**: 更新 {c1} 筆\n" if c1 > 0 else f"⚠️ **00981A**: 失敗\n"
    msg += f"✅ **00991A (復華)**: 更新 {c2} 筆\n" if c2 > 0 else f"⚠️ **00991A**: 失敗\n"
    msg += f"✅ **00980A (野村)**: 更新 {c3} 筆\n" if c3 > 0 else f"⚠️ **00980A**: 失敗\n"
    
    send_discord_notify(msg)
    print("=== 更新結束 ===")
