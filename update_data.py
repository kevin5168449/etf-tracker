import time
import os
import pandas as pd
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
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
    new_df.insert(0, 'Date', today_str)
    
    if os.path.exists(file_path):
        old_df = pd.read_csv(file_path, dtype=str)
        old_df = old_df[old_df['Date'] != today_str]
        final_df = pd.concat([old_df, new_df], ignore_index=True)
    else:
        final_df = new_df
        
    final_df.to_csv(file_path, index=False, encoding='utf-8-sig')
    print(f"✅ [{etf_code}] 成功儲存 {len(new_df)} 筆資料！")

def clean_columns(df):
    """清理欄位名稱，避免 tuple 錯誤"""
    new_columns = []
    for col in df.columns:
        if isinstance(col, tuple):
            col_str = "".join(str(c) for c in col)
        else:
            col_str = str(col)
        new_columns.append(col_str.strip().replace(" ", "").replace("\n", ""))
    df.columns = new_columns
    return df

# ==========================================
# 00981A: 統一投信 (放寬標準)
# ==========================================
def update_00981A():
    print("\n🚀 [00981A] 啟動爬蟲：統一投信...")
    url = "https://www.ezmoney.com.tw/ETF/Transaction/PCF"
    driver = get_driver()
    
    try:
        driver.get(url)
        try:
            WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, "table")))
        except:
            print("⚠️ 等待超時")

        html = driver.page_source
        dfs = pd.read_html(html)
        print(f"🔍 網頁中發現 {len(dfs)} 個表格")
        
        target_df = pd.DataFrame()
        
        # 尋找最像持股清單的表格
        for i, df in enumerate(dfs):
            df = clean_columns(df)
            cols = "".join(df.columns)
            
            # 放寬條件：只要有 "名稱" 或 "代號"，加上 "權重" 即可
            if ("名稱" in cols or "代號" in cols) and ("權重" in cols or "比重" in cols):
                print(f"🎯 鎖定表格 {i} (欄位符合)")
                
                rename_map = {}
                for c in df.columns:
                    if "代號" in c: rename_map[c] = "股票代號"
                    elif "名稱" in c: rename_map[c] = "股票名稱"
                    elif "股數" in c: rename_map[c] = "持有股數"
                    elif "權重" in c or "比重" in c: rename_map[c] = "權重"
                
                df = df.rename(columns=rename_map)
                
                # 簡單檢查，如果有超過 5 筆資料才算
                if len(df) > 5 and "股票名稱" in df.columns and "權重" in df.columns:
                    target_df = df.copy()
                    if "股票代號" not in target_df.columns: target_df["股票代號"] = target_df["股票名稱"]
                    if "持有股數" not in target_df.columns: target_df["持有股數"] = 0
                    break
        
        if not target_df.empty:
            target_df = target_df[['股票代號', '股票名稱', '持有股數', '權重']]
            target_df['持有股數'] = target_df['持有股數'].astype(str).str.replace(',', '').str.replace('--', '0')
            target_df['權重'] = target_df['權重'].astype(str).str.replace('%', '')
            save_to_csv("00981A", target_df)
        else:
            print("❌ [00981A] 找不到成分股表格")

    except Exception as e:
        print(f"❌ [00981A] 系統錯誤: {e}")
    finally:
        driver.quit()

# ==========================================
# 00991A: 復華投信 (貪婪模式：抓最大的表格)
# ==========================================
def update_00991A():
    print("\n🚀 [00991A] 啟動爬蟲：復華投信...")
    url = "https://www.fhtrust.com.tw/ETF/etf_detail/ETF23#stockhold"
    driver = get_driver()
    
    try:
        driver.get(url)
        time.sleep(5)
        
        print("👆 尋找展開按鈕...")
        try:
            js_script = """
            var btns = document.querySelectorAll('a, button, div');
            for (var i = 0; i < btns.length; i++) {
                if (btns[i].innerText.includes('更多') || btns[i].innerText.includes('展開')) {
                    btns[i].click();
                    return true;
                }
            }
            return false;
            """
            result = driver.execute_script(js_script)
            if result:
                print("✅ JS 點擊成功")
            else:
                # 備用方案：暴力點擊所有看起來像按鈕的東西
                print("⚠️ JS 沒找到，嘗試暴力點擊...")
                buttons = driver.find_elements(By.CSS_SELECTOR, ".more, .btn, .expand")
                for btn in buttons:
                    try: driver.execute_script("arguments[0].click();", btn)
                    except: pass
            
            # ★★★ 點擊後等待久一點，讓資料長出來 ★★★
            time.sleep(8) 
        except:
            print("⚠️ 點擊操作略過")

        html = driver.page_source
        dfs = pd.read_html(html)
        print(f"🔍 復華網頁發現 {len(dfs)} 個表格")

        best_df = pd.DataFrame()
        max_rows = 0
        
        # ★★★ 貪婪模式：遍歷所有表格，找出符合欄位且「行數最多」的那一個 ★★★
        # 這樣就能避開只有 10 筆的預覽表，抓到有 30-50 筆的完整表
        for i, df in enumerate(dfs):
            df = clean_columns(df)
            cols = "".join(df.columns)

            if ("名稱" in cols or "代號" in cols) and ("權重" in cols or "比例" in cols):
                # 重新命名以便檢查
                rename_map = {}
                for c in df.columns:
                    if "代號" in c: rename_map[c] = "股票代號"
                    elif "名稱" in c: rename_map[c] = "股票名稱"
                    elif "股數" in c or "庫存" in c: rename_map[c] = "持有股數"
                    elif "權重" in c or "比例" in c or "比重" in c: rename_map[c] = "權重"
                
                temp_df = df.rename(columns=rename_map)
                
                # 如果這個表格的資料筆數 > 目前找到最多的，就暫定它是目標
                if len(temp_df) > max_rows:
                    if "股票名稱" in temp_df.columns and "權重" in temp_df.columns:
                        max_rows = len(temp_df)
                        best_df = temp_df.copy()
                        print(f"🌟 發現潛在目標：表格 {i} (共 {max_rows} 筆資料)")

        if not best_df.empty:
            if "股票代號" not in best_df.columns: best_df["股票代號"] = best_df["股票名稱"]
            if "持有股數" not in best_df.columns: best_df["持有股數"] = 0
            
            best_df = best_df[['股票代號', '股票名稱', '持有股數', '權重']]
            best_df['權重'] = best_df['權重'].astype(str).str.replace('%', '')
            save_to_csv("00991A", best_df)
        else:
            print("❌ [00991A] 找不到任何有效表格")

    except Exception as e:
        print(f"❌ [00991A] 錯誤: {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    update_00981A()
    update_00991A()
