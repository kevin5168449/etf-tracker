import time
import os
import pandas as pd
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# --- 設定 ---
DATA_DIR = "data"
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

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
    today_str = datetime.now().strftime('%Y-%m-%d')
    
    if isinstance(new_df, list): new_df = pd.DataFrame(new_df)
    new_df.insert(0, 'Date', today_str)
    
    if os.path.exists(file_path):
        old_df = pd.read_csv(file_path, dtype=str)
        old_df = old_df[old_df['Date'] != today_str]
        final_df = pd.concat([old_df, new_df], ignore_index=True)
    else:
        final_df = new_df
        
    final_df.to_csv(file_path, index=False, encoding='utf-8-sig')
    print(f"✅ [{etf_code}] 成功儲存 {len(new_df)} 筆資料！")

def clean_column_name(col):
    if isinstance(col, tuple): col = "".join(str(c) for c in col)
    return str(col).strip().replace(" ", "").replace("\n", "")

# ==========================================
# 00981A: 統一投信 (已成功，保持原樣)
# ==========================================
def update_00981A():
    print("\n🚀 [00981A] 啟動爬蟲：統一投信...")
    url = "https://www.ezmoney.com.tw/ETF/Transaction/PCF"
    driver = get_driver()
    
    try:
        driver.get(url)
        time.sleep(8)
        
        html = driver.page_source
        dfs = pd.read_html(html)
        print(f"🔍 00981A 發現 {len(dfs)} 個表格")
        
        target_df = pd.DataFrame()
        
        for i, df in enumerate(dfs):
            df.columns = [clean_column_name(c) for c in df.columns]
            cols = "".join(df.columns)
            
            has_id_name = any(x in cols for x in ["代號", "名稱", "證券"])
            has_weight = any(x in cols for x in ["權重", "比重", "%", "比例", "股數"])
            
            if has_id_name and has_weight:
                rename_map = {}
                for c in df.columns:
                    if "代號" in c: rename_map[c] = "股票代號"
                    elif "名稱" in c: rename_map[c] = "股票名稱"
                    elif "股數" in c or "單位" in c: rename_map[c] = "持有股數"
                    elif "權重" in c or "比重" in c or "%" in c: rename_map[c] = "權重"
                
                df = df.rename(columns=rename_map)
                
                if "股票名稱" in df.columns:
                    if "股票代號" not in df.columns: df["股票代號"] = df["股票名稱"]
                    if "持有股數" not in df.columns: df["持有股數"] = 0
                    if "權重" not in df.columns: continue 
                    
                    target_df = df.copy()
                    break 
        
        if not target_df.empty:
            target_df = target_df[['股票代號', '股票名稱', '持有股數', '權重']]
            target_df['持有股數'] = target_df['持有股數'].astype(str).str.replace(',', '').str.replace('--', '0')
            target_df['權重'] = target_df['權重'].astype(str).str.replace('%', '')
            save_to_csv("00981A", target_df)
        else:
            print("❌ [00981A] 找不到表格")

    except Exception as e:
        print(f"❌ [00981A] 錯誤: {e}")
    finally:
        driver.quit()

# ==========================================
# 00991A: 復華投信 (強力點擊 + 驗收式等待)
# ==========================================
def update_00991A():
    print("\n🚀 [00991A] 啟動爬蟲：復華投信...")
    url = "https://www.fhtrust.com.tw/ETF/etf_detail/ETF23#stockhold"
    driver = get_driver()
    
    try:
        driver.get(url)
        time.sleep(5)
        
        print("👆 嘗試定位 #stockhold 區塊...")
        try:
            # 1. 嘗試捲動到持股區塊，確保按鈕在畫面中
            target_div = driver.find_element(By.ID, "stockhold")
            driver.execute_script("arguments[0].scrollIntoView(true);", target_div)
            time.sleep(2)
        except:
            print("⚠️ 找不到 #stockhold ID，使用一般捲動")
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight/1.5);")
            time.sleep(2)

        # 2. 尋找並點擊按鈕
        print("👆 尋找「更多/展開」按鈕...")
        clicked = False
        try:
            # 策略 A: 找含有特定文字的元素 (最通用)
            xpath = "//*[contains(text(),'更多') or contains(text(),'展開') or contains(text(),'查閱全部') or contains(text(),'More')]"
            buttons = driver.find_elements(By.XPATH, xpath)
            
            for btn in buttons:
                # 只點擊可見的按鈕
                if btn.is_displayed():
                    print(f"   👉 嘗試點擊按鈕: {btn.text}")
                    # 雙重保險：先用 JS 點，再用 ActionChains 點
                    driver.execute_script("arguments[0].click();", btn)
                    time.sleep(1)
                    try:
                        ActionChains(driver).move_to_element(btn).click().perform()
                    except: pass
                    clicked = True
                    break
        except Exception as e:
            print(f"⚠️ 點擊嘗試失敗: {e}")

        if not clicked:
            print("⚠️ 未發現明顯的展開按鈕，將嘗試直接抓取...")

        # 3. 驗收式等待：不斷重讀表格，直到資料變多
        print("⏳ 正在驗收資料是否展開 (最多等 20 秒)...")
        best_df = pd.DataFrame()
        
        for attempt in range(10): # 嘗試 10 次，每次間隔 2 秒
            try:
                html = driver.page_source
                dfs = pd.read_html(html)
                
                # 在所有表格中找最長的那一個
                current_best_df = pd.DataFrame()
                max_rows = 0
                
                for df in dfs:
                    df.columns = [clean_column_name(c) for c in df.columns]
                    cols = "".join(df.columns)
                    if ("名稱" in cols or "代號" in cols) and ("權重" in cols or "比例" in cols):
                        if len(df) > max_rows:
                            max_rows = len(df)
                            current_best_df = df.copy()
                
                print(f"   第 {attempt+1} 次檢查: 最大表格有 {max_rows} 筆資料")
                
                # 如果找到超過 15 筆的，代表展開成功！
                if max_rows > 15:
                    best_df = current_best_df
                    print(f"🌟 成功！抓取代號為 00991A 的完整清單 ({max_rows} 筆)")
                    break
                
                # 否則暫存這個 10 筆的，繼續等
                if max_rows > 0:
                    best_df = current_best_df
                
                time.sleep(2)
                
            except: pass

        # 4. 處理抓到的資料
        if not best_df.empty:
            # 欄位對應
            rename_map = {}
            for c in best_df.columns:
                if "代號" in c: rename_map[c] = "股票代號"
                elif "名稱" in c: rename_map[c] = "股票名稱"
                elif "股數" in c or "庫存" in c: rename_map[c] = "持有股數"
                elif "權重" in c or "比例" in c: rename_map[c] = "權重"
            
            best_df = best_df.rename(columns=rename_map)
            
            if "股票名稱" in best_df.columns and "權重" in best_df.columns:
                if "股票代號" not in best_df.columns: best_df["股票代號"] = best_df["股票名稱"]
                if "持有股數" not in best_df.columns: best_df["持有股數"] = 0
                
                best_df = best_df[['股票代號', '股票名稱', '持有股數', '權重']]
                best_df['權重'] = best_df['權重'].astype(str).str.replace('%', '')
                save_to_csv("00991A", best_df)
            else:
                print("❌ [00991A] 表格欄位不符")
        else:
            print("❌ [00991A] 找不到任何表格")

    except Exception as e:
        print(f"❌ [00991A] 錯誤: {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    update_00981A()
    update_00991A()
