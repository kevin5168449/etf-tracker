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
# 00991A: 復華未來50 (V28 狙擊手待命版)
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
        
        # 1. ★★★ 狙擊手待命：直到看到「證券代號」才動作 ★★★
        try:
            # 這是最關鍵的一步：不再是用時間等，而是用「條件」等
            # 我們等待表格的表頭出現
            WebDriverWait(driver, 25).until(
                EC.presence_of_element_located((By.XPATH, "//*[contains(text(),'證券代號') or contains(text(),'證券名稱')]"))
            )
            print("   ✅ 偵測到表格表頭！")
        except:
            print("   ⚠️ 等待超時，嘗試暴力捲動喚醒...")
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(3)
        
        # 2. 觸發 Lazy Load (確保下面的資料長出來)
        # 復華的資料需要捲動才會 render，我們模擬人類慢慢往下滑
        print("🔄 捲動頁面觸發資料載入...")
        driver.execute_script("window.scrollTo(0, 300);")
        time.sleep(1)
        driver.execute_script("window.scrollTo(0, 800);") # 大概是表格的位置
        time.sleep(2)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);") # 到底
        time.sleep(2)

        # 3. 點擊展開 (雖然可能不需要，但點一下保險)
        try:
            # 針對 V26 截圖中的 "展開更多"
            expand_btn = driver.find_elements(By.XPATH, "//*[contains(text(),'展開更多')]")
            if expand_btn:
                driver.execute_script("arguments[0].click();", expand_btn[0])
                print("   ✅ 點擊了「展開更多」")
                time.sleep(5)
        except: pass

        # 4. ★★★ 鎖定表格並強力提取 ★★★
        print("⏳ 啟動資料抓取...")
        best_df = pd.DataFrame()
        
        try:
            # 策略：直接找所有的 tr (表格列)
            # 為了避免抓到別的表格，我們先定位到含有 "2330" 或 "台灣積體" 的區塊
            # 如果找不到台積電，就抓全頁所有的 tr
            
            rows = driver.find_elements(By.XPATH, "//table//tr")
            if len(rows) < 5:
                # 如果 table 標籤抓不到，試試看 div 結構 (有些 RWD 網頁用 div 排版)
                print("   ⚠️ Table 標籤抓取過少，切換 Div 模式...")
                # 這裡假設它是用 div 模擬的表格，抓取所有包含 text 的 div
                # 但復華應該是 table，我們先堅持用 table，只是可能要等久一點
                time.sleep(5)
                rows = driver.find_elements(By.XPATH, "//table//tr")

            print(f"   📊 掃描到 {len(rows)} 列 HTML 元件...")
            
            data = []
            for row in rows:
                # 使用 JavaScript 提取整列的 innerText (包含隱藏內容)
                # 這比逐個 cell 抓更穩，因為它會把整行的字串連在一起
                row_text = driver.execute_script("return arguments[0].innerText;", row).strip()
                
                # 如果這一行有內容，且包含數字 (股票代號或股數)
                if row_text and any(char.isdigit() for char in row_text):
                    # 復華的格式通常是以換行符號 \n 或 tab \t 分隔
                    # 我們嘗試切割它
                    parts = row_text.replace('\t', '\n').split('\n')
                    parts = [p.strip() for p in parts if p.strip() != ""]
                    
                    # 簡單判斷：有效的資料行至少要有 3~4 個欄位 (代號, 名稱, 股數, 權重)
                    if len(parts) >= 3:
                        data.append(parts)

            print(f"   ✅ 成功提取 {len(data)} 筆資料 (含隱藏)！")
            
            # 處理抓到的資料
            if len(data) > 0:
                # 我們需要標準化資料
                # 假設抓到的 parts 是 ['2330', '台灣積體', '2,000,000', '18.553%']
                processed_data = []
                for parts in data:
                    # 尋找代號 (通常是 4 碼數字)
                    code = next((p for p in parts if p.isdigit() and len(p) == 4), None)
                    # 尋找權重 (有 % 的)
                    weight = next((p for p in parts if '%' in p), "0")
                    # 尋找名稱 (通常在代號後面)
                    name = "未知"
                    if code:
                        try:
                            idx = parts.index(code)
                            if idx + 1 < len(parts):
                                name = parts[idx+1]
                        except: pass
                    
                    # 尋找股數 (含有 , 的大數字，且不是權重)
                    shares = "0"
                    for p in parts:
                        if ',' in p and '%' not in p:
                            shares = p
                            break
                    
                    if code and name:
                        processed_data.append([code, name, shares, weight])

                if len(processed_data) > 0:
                    best_df = pd.DataFrame(processed_data, columns=['股票代號', '股票名稱', '持有股數', '權重'])

        except Exception as e:
            print(f"   ❌ 資料解析失敗: {e}")

        # 5. 存檔與安全閥
        if not best_df.empty:
            print(f"📊 最終確認筆數: {len(best_df)}")
            
            # 安全閥
            if len(best_df) < 15:
                print(f"⛔ [失敗] 只抓到 {len(best_df)} 筆。拒絕存檔！")
                return 0
            
            # 清洗與存檔
            # 去除重複 (有時候表頭會被當成資料抓兩次)
            best_df = best_df.drop_duplicates(subset=['股票代號'])
            
            # 強制清洗
            best_df['持有股數'] = best_df['持有股數'].astype(str).str.replace(',', '').str.replace('--', '0')
            best_df['權重'] = best_df['權重'].astype(str).str.replace('%', '')
            
            count = save_to_csv("00991A", best_df)
        else:
            print("❌ 找不到任何資料列")

    except Exception as e:
        print(f"❌ 錯誤: {e}")
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
    c3 = update_00980A()
    
    today = get_taiwan_date()
    msg = f"📢 **{today} ETF 持股更新報告**\n"
    msg += f"✅ **00981A (統一)**: 更新 {c1} 筆\n" if c1 > 0 else f"⚠️ **00981A**: 失敗\n"
    msg += f"✅ **00991A (復華)**: 更新 {c2} 筆\n" if c2 > 0 else f"⚠️ **00991A**: 失敗\n"
    msg += f"✅ **00980A (野村)**: 更新 {c3} 筆\n" if c3 > 0 else f"⚠️ **00980A**: 失敗\n"
    
    send_discord_notify(msg)
    print("=== 更新結束 ===")
