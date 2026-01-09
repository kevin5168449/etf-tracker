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
# 00991A: 復華未來50 (V25 漸進捲動+精準文字版)
# ==========================================
def update_00991A():
    TARGET_NAME = "復華未來50"
    print(f"\n🚀 [00991A] 啟動爬蟲：復華投信 ({TARGET_NAME})...")
    url = "https://www.fhtrust.com.tw/ETF/etf_detail/ETF23"
    driver = get_driver()
    count = 0
    
    try:
        driver.get(url)
        print("💤 等待網頁載入 (10秒)...")
        time.sleep(10) 
        
        # 1. ★★★ 漸進式捲動 (讓網頁慢慢吐出資料) ★★★
        print("🔄 正在喚醒頁面 (30% -> 60% -> 100%)...")
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.3);")
        time.sleep(2)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.6);")
        time.sleep(2)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        
        # 2. 回到持股區塊附近
        print("👆 嘗試定位持股區塊...")
        try:
            # 嘗試找表頭 "證券代號"
            headers = driver.find_elements(By.XPATH, "//*[contains(text(),'證券代號')]")
            if headers:
                target = headers[0]
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", target)
                time.sleep(2)
            else:
                # 找不到表頭就找 ID
                target = driver.find_element(By.ID, "stockhold")
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", target)
        except: 
            print("⚠️ 定位失敗，保持在底部")

        # 3. ★★★ 尋找並點擊「展開」類型的按鈕 ★★★
        print("👆 尋找「展開更多」按鈕...")
        clicked = False
        try:
            # 策略：找出所有包含 "展開" 兩個字的元素
            # 這是針對截圖中 "展開更多" 的精準打擊
            xpath = "//*[contains(text(),'展開')]" 
            candidates = driver.find_elements(By.XPATH, xpath)
            
            for btn in candidates:
                if btn.is_displayed():
                    txt = btn.text.strip()
                    # 再次確認文字內容
                    if "展開" in txt or "更多" in txt:
                        print(f"   🎯 鎖定按鈕文字: [{txt}]")
                        
                        # 畫紅框 (Debug)
                        driver.execute_script("arguments[0].style.border='5px solid red'", btn)
                        time.sleep(1)
                        
                        # JS 強制點擊
                        driver.execute_script("arguments[0].click();", btn)
                        print("   ✅ 點擊成功！")
                        clicked = True
                        break # 點到一個就收工
            
            if clicked:
                print("⏳ 等待資料展開 (15秒)...") # 給它多一點時間長資料
                time.sleep(15)
            else:
                print("⚠️ 掃描全頁未發現「展開」按鈕，嘗試尋找箭頭圖示...")
                # 備用方案：有時候是 CSS class 
                css_btns = driver.find_elements(By.CSS_SELECTOR, ".more, .btn-more, .r-btn")
                for btn in css_btns:
                    if btn.is_displayed():
                        driver.execute_script("arguments[0].click();", btn)
                        print("   ✅ (備用方案) 點擊了 CSS 按鈕")
                        time.sleep(10)
                        break

        except Exception as e:
            print(f"⚠️ 點擊錯誤: {e}")

        # 4. 讀取資料 (雙重模式)
        print("⏳ 讀取表格資料...")
        best_df = pd.DataFrame()

        # 方法 A: Pandas
        try:
            html = driver.page_source
            dfs = pd.read_html(html)
            for df in dfs:
                df.columns = [clean_column_name(c) for c in df.columns]
                cols = "".join(df.columns)
                if ("代號" in cols) and ("權重" in cols):
                    if len(df) > len(best_df): best_df = df.copy()
        except: pass

        # 方法 B: Selenium 硬抓 (如果 Pandas 抓太少)
        if len(best_df) < 20:
            print(f"⚠️ Pandas 只抓到 {len(best_df)} 筆，啟動「Selenium 硬抓模式」...")
            try:
                # 抓取表格每一列
                rows = driver.find_elements(By.XPATH, "//table//tr")
                data = []
                for row in rows:
                    cols = row.find_elements(By.TAG_NAME, "td")
                    # 根據截圖，應該要有 4~5 個欄位
                    if len(cols) >= 4: 
                        row_text = [c.text.strip() for c in cols]
                        data.append(row_text)
                
                print(f"   📊 硬抓模式找到 {len(data)} 列")
                if len(data) > 20:
                    # 假設順序：代號, 名稱, 股數, 金額, 權重
                    # 依截圖 2330 | 台灣積體 | 2,000,000 | ... | 18.553%
                    # 取第 0, 1, 2, 4 欄
                    temp_df = pd.DataFrame(data)
                    # 自動對應欄位 (簡單版)
                    if len(temp_df.columns) >= 5:
                        temp_df = temp_df.iloc[:, [0, 1, 2, 4]]
                        temp_df.columns = ['股票代號', '股票名稱', '持有股數', '權重']
                        best_df = temp_df
            except Exception as e:
                print(f"   ❌ 硬抓失敗: {e}")

        # 5. 最終存檔與安全閥
        if not best_df.empty:
            print(f"📊 最終確認資料筆數: {len(best_df)}")
            
            # ★★★ 安全閥：一定要大於 20 筆才存 ★★★
            if len(best_df) < 20:
                print(f"⛔ [失敗] 只有 {len(best_df)} 筆 (目標是 50 筆)。")
                print("⛔ **拒絕存檔** 以免造成假剔除！請檢查 Log。")
                return 0
            
            # 欄位正規化
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
                # 清洗
                for col in best_df.columns: best_df[col] = best_df[col].apply(clean_cell_data)
                best_df['權重'] = best_df['權重'].astype(str).str.replace('%', '')
                count = save_to_csv("00991A", best_df)
            else: print("❌ 欄位不符")
        else: print("❌ 找不到表格")

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
    msg += f"✅ **00981A (統一)**: 更新 {c1} 筆\n" if c1 > 0 else f"⚠️ **00981A**: 失敗\n"
    msg += f"✅ **00991A (復華)**: 更新 {c2} 筆\n" if c2 > 0 else f"⚠️ **00991A**: 失敗\n"
    msg += f"✅ **00980A (野村)**: 更新 {c3} 筆\n" if c3 > 0 else f"⚠️ **00980A**: 失敗\n"
    
    send_discord_notify(msg)
    print("=== 更新結束 ===")
