import time
import os
import pandas as pd
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

# --- 設定儲存路徑 ---
DATA_DIR = "data"
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

# --- 設定瀏覽器 (無頭模式，讓 GitHub 能跑) ---
def get_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless") # 不開啟視窗
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    # 偽裝成一般使用者
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36")
    
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=chrome_options)

def save_to_csv(etf_code, new_df):
    """將抓到的資料存入歷史 CSV，並處理日期"""
    file_path = f"{DATA_DIR}/{etf_code}_history.csv"
    today_str = datetime.now().strftime('%Y-%m-%d')
    
    # 加上日期欄位
    new_df.insert(0, 'Date', today_str)
    
    if os.path.exists(file_path):
        # 讀取舊資料，除了日期要是字串，其他暫時讀成字串以免格式跑掉
        old_df = pd.read_csv(file_path, dtype=str)
        # 刪除今天已有的資料 (避免重複更新)
        old_df = old_df[old_df['Date'] != today_str]
        final_df = pd.concat([old_df, new_df], ignore_index=True)
    else:
        final_df = new_df
        
    final_df.to_csv(file_path, index=False, encoding='utf-8-sig')
    print(f"✅ [{etf_code}] 成功儲存 {len(new_df)} 筆資料！")

# ==========================================
# 任務 1: 抓取 00981A (統一投信 PCF)
# ==========================================
def update_00981A():
    print("🚀 [00981A] 啟動爬蟲：統一投信 PCF...")
    url = "https://www.ezmoney.com.tw/ETF/Transaction/PCF"
    driver = get_driver()
    
    try:
        driver.get(url)
        time.sleep(10) # 統一投信載入比較慢，多等一下
        
        # 嘗試抓取網頁上的表格
        html = driver.page_source
        dfs = pd.read_html(html)
        
        target_df = pd.DataFrame()
        
        # 在所有表格中尋找長得像持股清單的
        for df in dfs:
            # 統一投信的欄位名稱通常包含這些
            if '股票代號' in str(df.columns) and '權重' in str(df.columns):
                df.columns = [c.replace(' ', '') for c in df.columns] # 清除欄位空白
                
                # 重新命名欄位以符合我們的格式
                rename_map = {
                    '股票代號': '股票代號', '證券代號': '股票代號',
                    '股票名稱': '股票名稱', '證券名稱': '股票名稱',
                    '股數': '持有股數', '持有股數': '持有股數',
                    '權重': '權重', '權重(%)': '權重', '比重': '權重'
                }
                df = df.rename(columns=rename_map)
                
                # 確保必要欄位存在
                if '股票代號' in df.columns and '權重' in df.columns:
                    # 如果該表格包含多檔 ETF，通常需要篩選，這裡假設網頁已顯示目標
                    # 或是我們直接取前 50 大成分股 (通常是表格內容)
                    target_df = df.copy()
                    # 簡單清洗
                    if '持有股數' in target_df.columns:
                        target_df['持有股數'] = target_df['持有股數'].astype(str).str.replace(',', '').str.replace('--', '0')
                    else:
                        target_df['持有股數'] = 0 # 萬一沒股數欄位
                        
                    target_df['權重'] = target_df['權重'].astype(str).str.replace('%', '')
                    break
        
        if not target_df.empty:
            # 只留需要的欄位
            cols = ['股票代號', '股票名稱', '持有股數', '權重']
            final_df = target_df[cols] if set(cols).issubset(target_df.columns) else target_df
            save_to_csv("00981A", final_df)
        else:
            print("❌ [00981A] 找不到成分股表格，請檢查網頁結構。")

    except Exception as e:
        print(f"❌ [00981A] 錯誤: {e}")
    finally:
        driver.quit()

# ==========================================
# 任務 2: 抓取 00991A (復華投信 - 點擊展開)
# ==========================================
def update_00991A():
    print("🚀 [00991A] 啟動爬蟲：復華投信...")
    url = "https://www.fhtrust.com.tw/ETF/etf_detail/ETF23#stockhold" # 這是 00929 的網址範例
    driver = get_driver()
    
    try:
        driver.get(url)
        time.sleep(5)
        
        # 1. 處理「展開更多」按鈕
        print("👆 正在尋找並點擊「更多/展開」按鈕...")
        try:
            # 捲動到底部
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
            time.sleep(1)
            
            # 尋找所有按鈕，看哪個裡面有 "更多" 或 "展開"
            buttons = driver.find_elements(By.TAG_NAME, "a") + driver.find_elements(By.TAG_NAME, "button")
            clicked = False
            for btn in buttons:
                if btn.is_displayed() and ("更多" in btn.text or "展開" in btn.text):
                    driver.execute_script("arguments[0].click();", btn)
                    print("✅ 已點擊展開按鈕")
                    clicked = True
                    time.sleep(3) # 等待資料載入
                    break
            if not clicked:
                print("⚠️ 未找到展開按鈕，可能已展開或無按鈕")
                
        except Exception as e:
            print(f"⚠️ 點擊操作略過: {e}")

        # 2. 抓取表格
        html = driver.page_source
        dfs = pd.read_html(html)
        
        target_df = pd.DataFrame()
        
        for df in dfs:
            # 復華的表格特徵
            if '股票名稱' in str(df.columns) and '權重' in str(df.columns):
                df.columns = [c.replace(' ', '') for c in df.columns]
                
                rename_map = {
                    '股票名稱': '股票名稱', '證券名稱': '股票名稱', '名稱': '股票名稱',
                    '產業類別': '股票代號', # 復華有時候沒代號，暫時用其他欄位佔位
                    '股數': '持有股數', '持有股數': '持有股數', '庫存股數': '持有股數',
                    '權重': '權重', '權重%': '權重', '比例': '權重', '投資比重': '權重'
                }
                df = df.rename(columns=rename_map)
                
                if '股票名稱' in df.columns and '權重' in df.columns:
                    # 如果沒有代號，暫時用名稱代替，或需另外mapping
                    if '股票代號' not in df.columns:
                        df['股票代號'] = df['股票名稱'] 
                    
                    if '持有股數' not in df.columns:
                        df['持有股數'] = 0 
                    
                    target_df = df.copy()
                    break
        
        if not target_df.empty:
            target_df['權重'] = target_df['權重'].astype(str).str.replace('%', '')
            # 簡單過濾掉雜訊
            if '持有股數' in target_df.columns:
                 target_df['持有股數'] = target_df['持有股數'].astype(str).str.replace(',', '')
            
            cols = ['股票代號', '股票名稱', '持有股數', '權重']
            final_df = target_df[cols] if set(cols).issubset(target_df.columns) else target_df
            
            save_to_csv("00991A", final_df)
        else:
            print("❌ [00991A] 找不到成分股表格")

    except Exception as e:
        print(f"❌ [00991A] 錯誤: {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    print("=== 開始自動更新 ===")
    update_00981A()
    update_00991A()
    print("=== 更新結束 ===")
