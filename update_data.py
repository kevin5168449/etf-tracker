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
    # 偽裝成真人
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36")
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=chrome_options)

def save_to_csv(etf_code, new_df):
    file_path = f"{DATA_DIR}/{etf_code}_history.csv"
    today_str = datetime.now().strftime('%Y-%m-%d')
    
    # 確保是 DataFrame
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
    """清理欄位名稱"""
    if isinstance(col, tuple): col = "".join(str(c) for c in col)
    return str(col).strip().replace(" ", "").replace("\n", "")

# ==========================================
# 00981A: 統一投信 (寬鬆模式 + 詳細 Log)
# ==========================================
def update_00981A():
    print("\n🚀 [00981A] 啟動爬蟲：統一投信...")
    url = "https://www.ezmoney.com.tw/ETF/Transaction/PCF"
    driver = get_driver()
    
    try:
        driver.get(url)
        # 等待網頁載入
        time.sleep(8)
        
        html = driver.page_source
        dfs = pd.read_html(html)
        print(f"🔍 網頁中發現 {len(dfs)} 個表格")
        
        target_df = pd.DataFrame()
        
        for i, df in enumerate(dfs):
            # 清理欄位
            df.columns = [clean_column_name(c) for c in df.columns]
            cols = "".join(df.columns)
            
            # 除錯用：印出每個表格的欄位，讓我們知道它長怎樣
            print(f"   📋 表格 {i} 欄位: {df.columns.tolist()[:5]}")

            # 寬鬆條件：只要有 (代號 OR 名稱) AND (權重 OR 比重 OR %)
            has_id_name = any(x in cols for x in ["代號", "名稱", "證券"])
            has_weight = any(x in cols for x in ["權重", "比重", "%", "比例"])
            
            if has_id_name and has_weight:
                print(f"🎯 鎖定表格 {i}")
                
                # 智慧對應欄位
                rename_map = {}
                for c in df.columns:
                    if "代號" in c: rename_map[c] = "股票代號"
                    elif "名稱" in c: rename_map[c] = "股票名稱"
                    elif "股數" in c or "單位" in c: rename_map[c] = "持有股數"
                    elif "權重" in c or "比重" in c or "%" in c: rename_map[c] = "權重"
                
                df = df.rename(columns=rename_map)
                
                # 補齊缺失欄位
                if "股票名稱" in df.columns:
                    if "股票代號" not in df.columns: df["股票代號"] = df["股票名稱"]
                    if "持有股數" not in df.columns: df["持有股數"] = 0
                    if "權重" not in df.columns: continue # 權重是必須的
                    
                    target_df = df.copy()
                    break # 找到就跳出
        
        if not target_df.empty:
            target_df = target_df[['股票代號', '股票名稱', '持有股數', '權重']]
            # 數據清洗
            target_df['持有股數'] = target_df['持有股數'].astype(str).str.replace(',', '').str.replace('--', '0')
            target_df['權重'] = target_df['權重'].astype(str).str.replace('%', '')
            save_to_csv("00981A", target_df)
        else:
            print("❌ [00981A] 找不到符合的表格，請檢查上方 Log 的欄位名稱。")

    except Exception as e:
        print(f"❌ [00981A] 系統錯誤: {e}")
    finally:
        driver.quit()

# ==========================================
# 00991A: 復華投信 (智慧等待行數增加)
# ==========================================
def update_00991A():
    print("\n🚀 [00991A] 啟動爬蟲：復華投信...")
    url = "https://www.fhtrust.com.tw/ETF/etf_detail/ETF23#stockhold"
    driver = get_driver()
    
    try:
        driver.get(url)
        time.sleep(5)
        
        # 1. 先計算原本有幾行 (通常是 10 行)
        initial_rows = len(driver.find_elements(By.TAG_NAME, "tr"))
        print(f"📊 點擊前行數: {initial_rows}")

        # 2. 點擊展開
        print("👆 尋找並點擊「更多/展開」按鈕...")
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
            driver.execute_script(js_script)
            
            # 3. 智慧等待：每 1 秒檢查一次，最多等 15 秒，直到行數變多
            print("⏳ 等待資料展開中...")
            for _ in range(15):
                current_rows = len(driver.find_elements(By.TAG_NAME, "tr"))
                if current_rows > initial_rows + 5: # 如果行數明顯增加
                    print(f"✅ 偵測到資料載入！當前行數: {current_rows}")
                    break
                time.sleep(1)
            else:
                print("⚠️ 等待超時，資料可能未完全展開，嘗試直接抓取...")
                
        except Exception as e:
            print(f"⚠️ 點擊操作異常: {e}")

        # 4. 抓取表格 (此時 HTML 應該已經包含新資料)
        html = driver.page_source
        dfs = pd.read_html(html)
        print(f"🔍 復華網頁發現 {len(dfs)} 個表格")

        best_df = pd.DataFrame()
        max_rows = 0
        
        # 貪婪模式：找最大的那個表
        for i, df in enumerate(dfs):
            df.columns = [clean_column_name(c) for c in df.columns]
            cols = "".join(df.columns)

            if ("名稱" in cols or "代號" in cols) and ("權重" in cols or "比例" in cols):
                rename_map = {}
                for c in df.columns:
                    if "代號" in c: rename_map[c] = "股票代號"
                    elif "名稱" in c: rename_map[c] = "股票名稱"
                    elif "股數" in c or "庫存" in c: rename_map[c] = "持有股數"
                    elif "權重" in c or "比例" in c: rename_map[c] = "權重"
                
                df = df.rename(columns=rename_map)
                
                # 我們要找行數最多的那個 (避免抓到 header 或 summary)
                if len(df) > max_rows:
                    if "股票名稱" in df.columns and "權重" in df.columns:
                        max_rows = len(df)
                        best_df = df.copy()
                        print(f"🌟 發現潛在目標: 表格 {i} (共 {max_rows} 筆)")

        if not best_df.empty:
            if "股票代號" not in best_df.columns: best_df["股票代號"] = best_df["股票名稱"]
            if "持有股數" not in best_df.columns: best_df["持有股數"] = 0
            
            best_df = best_df[['股票代號', '股票名稱', '持有股數', '權重']]
            best_df['權重'] = best_df['權重'].astype(str).str.replace('%', '')
            
            # 如果還是只抓到 10 筆，可能是 click 真的失敗，但我們盡力了
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
