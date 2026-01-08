import time
import os
import pandas as pd
import requests
import json
from datetime import datetime, timedelta
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

# 設定台灣時間 (解決 GitHub Actions 是 UTC 的問題)
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
    
    # 插入日期欄位
    if 'Date' not in new_df.columns:
        new_df.insert(0, 'Date', today_str)
    
    if os.path.exists(file_path):
        old_df = pd.read_csv(file_path, dtype=str)
        # 移除當天舊資料 (避免重複)
        old_df = old_df[old_df['Date'] != today_str]
        final_df = pd.concat([old_df, new_df], ignore_index=True)
    else:
        final_df = new_df
        
    final_df.to_csv(file_path, index=False, encoding='utf-8-sig')
    print(f"✅ [{etf_code}] 成功儲存 {len(new_df)} 筆資料！")
    return len(new_df)

def clean_column_name(col):
    """清理欄位名稱"""
    if isinstance(col, tuple): col = "".join(str(c) for c in col)
    return str(col).strip().replace(" ", "").replace("\n", "")

def fix_double_text(val):
    """
    修復網頁文字重複問題 (例如: '23302330' -> '2330')
    """
    s = str(val).strip()
    # 如果長度是偶數且不為空
    if len(s) > 0 and len(s) % 2 == 0:
        mid = len(s) // 2
        # 如果前半段等於後半段，就只取一半
        if s[:mid] == s[mid:]:
            return s[:mid]
    return s

# ==========================================
# 00981A: 統一投信 (包含修正疊字功能)
# ==========================================
def update_00981A():
    print("\n🚀 [00981A] 啟動爬蟲：統一投信...")
    url = "https://www.ezmoney.com.tw/ETF/Transaction/PCF"
    driver = get_driver()
    count = 0
    
    try:
        driver.get(url)
        time.sleep(8) # 等待載入
        
        html = driver.page_source
        dfs = pd.read_html(html)
        print(f"🔍 00981A 發現 {len(dfs)} 個表格")
        
        target_df = pd.DataFrame()
        
        for i, df in enumerate(dfs):
            df.columns = [clean_column_name(c) for c in df.columns]
            cols = "".join(df.columns)
            
            # 寬鬆條件
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
            
            # ★★★ 關鍵修復：清洗重複文字 ★★★
            target_df['股票代號'] = target_df['股票代號'].apply(fix_double_text)
            target_df['股票名稱'] = target_df['股票名稱'].apply(fix_double_text)
            # -----------------------------------

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
# 00991A: 復華投信 (強力點擊 + 驗收等待)
# ==========================================
def update_00991A():
    print("\n🚀 [00991A] 啟動爬蟲：復華投信...")
    url = "https://www.fhtrust.com.tw/ETF/etf_detail/ETF23#stockhold"
    driver = get_driver()
    count = 0
    
    try:
        driver.get(url)
        time.sleep(5)
        
        print("👆 嘗試定位 #stockhold 區塊...")
        try:
            target_div = driver.find_element(By.ID, "stockhold")
            driver.execute_script("arguments[0].scrollIntoView(true);", target_div)
            time.sleep(2)
        except:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight/1.5);")
            time.sleep(2)

        print("👆 尋找「更多/展開」按鈕...")
        clicked = False
        try:
            xpath = "//*[contains(text(),'更多') or contains(text(),'展開') or contains(text(),'查閱全部') or contains(text(),'More')]"
            buttons = driver.find_elements(By.XPATH, xpath)
            for btn in buttons:
                if btn.is_displayed():
                    driver.execute_script("arguments[0].click();", btn)
                    time.sleep(1)
                    try: ActionChains(driver).move_to_element(btn).click().perform()
                    except: pass
                    clicked = True
                    break
        except Exception as e:
            print(f"⚠️ 點擊嘗試失敗: {e}")

        # 驗收式等待：直到行數 > 15
        print("⏳ 正在驗收資料是否展開...")
        best_df = pd.DataFrame()
        
        for attempt in range(10):
            try:
                html = driver.page_source
                dfs = pd.read_html(html)
                current_best_df = pd.DataFrame()
                max_rows = 0
                
                for df in dfs:
                    df.columns = [clean_column_name(c) for c in df.columns]
                    cols = "".join(df.columns)
                    if ("名稱" in cols or "代號" in cols) and ("權重" in cols or "比例" in cols):
                        if len(df) > max_rows:
                            max_rows = len(df)
                            current_best_df = df.copy()
                
                print(f"   第 {attempt+1} 次檢查: {max_rows} 筆資料")
                
                if max_rows > 15:
                    best_df = current_best_df
                    print(f"🌟 展開成功！抓到 {max_rows} 筆")
                    break
                
                if max_rows > 0: best_df = current_best_df
                time.sleep(2)
            except: pass

        if not best_df.empty:
            rename_map = {}
            for c in best_df.columns:
                if "代號" in c: rename_map[c] = "股票代號"
                elif "名稱" in c: rename_map[c] = "股票名稱"
                elif "股數" in c or "庫存" in c: rename_map[c] = "持有股數"
                elif "權重" in c or "比例" in c: rename_map[c] = "權重"
            
            best_df = best_df.rename(columns=rename_map)
            
            if "股票名稱" in best_df.columns:
                if "股票代號" not in best_df.columns: best_df["股票代號"] = best_df["股票名稱"]
                if "持有股數" not in best_df.columns: best_df["持有股數"] = 0
                
                best_df = best_df[['股票代號', '股票名稱', '持有股數', '權重']]
                best_df['權重'] = best_df['權重'].astype(str).str.replace('%', '')
                count = save_to_csv("00991A", best_df)
            else:
                print("❌ [00991A] 表格欄位不符")
        else:
            print("❌ [00991A] 找不到任何表格")

    except Exception as e:
        print(f"❌ [00991A] 錯誤: {e}")
    finally:
        driver.quit()
    return count

# ==========================================
# Discord 推播功能
# ==========================================
def send_discord_notify(message):
    webhook_url = os.environ.get("DISCORD_WEBHOOK")
    if not webhook_url:
        print("⚠️ 未設定 DISCORD_WEBHOOK")
        return

    data = {
        "username": "🦁 ETF 戰情室",
        "avatar_url": "https://cdn-icons-png.flaticon.com/512/2504/2504936.png",
        "content": message
    }
    try:
        requests.post(webhook_url, json=data)
        print("✅ Discord 通知已發送")
    except Exception as e:
        print(f"❌ Discord 發送失敗: {e}")

if __name__ == "__main__":
    print("=== 開始自動更新 ===")
    
    c1 = update_00981A()
    c2 = update_00991A()
    
    # 準備 Discord 訊息
    today = get_taiwan_date()
    msg = f"📢 **{today} ETF 持股更新報告**\n"
    
    if c1 > 0: msg += f"✅ **00981A**: 成功更新 {c1} 筆 (已修正疊字)\n"
    else: msg += f"⚠️ **00981A**: 更新失敗或無資料\n"
        
    if c2 > 0: msg += f"✅ **00991A**: 成功更新 {c2} 筆\n"
    else: msg += f"⚠️ **00991A**: 更新失敗或無資料\n"
    
    msg += "\n📊 請前往戰情室查看詳細數據"
    
    send_discord_notify(msg)
    print("=== 更新結束 ===")
