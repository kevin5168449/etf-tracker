import pandas as pd
import requests
import os
from datetime import datetime, timedelta
import io
import time
import shutil

# --- Selenium 設定 ---
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By

# --- 設定 Discord Webhook ---
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK")

def send_discord_notify(msg):
    if not DISCORD_WEBHOOK: 
        print("⚠️ 未設定 Discord Webhook，跳過通知")
        return
    data = {"content": msg, "username": "ETF 監控小幫手"}
    try: 
        requests.post(DISCORD_WEBHOOK, json=data)
        print("✅ Discord 通知已發送")
    except Exception as e: 
        print(f"❌ Discord 通知發送失敗: {e}")

def get_roc_date_string(delta_days=0):
    target_date = datetime.now() + timedelta(days=delta_days)
    roc_year = target_date.year - 1911
    return f"{roc_year}/{target_date.month:02d}/{target_date.day:02d}"

# ★★★ 新增：生成每日簡易戰報 (讓 Discord 講人話) ★★★
def generate_daily_report(df):
    try:
        # 確保日期是排序的 (最新的在上面)
        df['DateObj'] = pd.to_datetime(df['Date'])
        dates = df['DateObj'].sort_values(ascending=False).unique()
        
        if len(dates) < 2:
            return "\n(⚠️ 資料累積天數不足，暫無法分析變動)"
            
        # 取得今天和昨天的資料
        d_now = dates[0]
        d_prev = dates[1]
        
        df_now = df[df['DateObj'] == d_now].set_index('股票代號')
        df_prev = df[df['DateObj'] == d_prev].set_index('股票代號')
        
        # 合併比對
        merged = df_now[['股票名稱', '持有股數']].join(
            df_prev[['持有股數']], lsuffix='', rsuffix='_old', how='outer'
        ).fillna(0)
        
        merged['股數變化'] = merged['持有股數'] - merged['持有股數_old']
        
        # 補名稱 (若剔除，名稱可能在 old 裡)
        name_map = pd.concat([df_now['股票名稱'], df_prev['股票名稱']]).to_dict()
        merged['股票名稱'] = merged.index.map(name_map).fillna(merged.index)
        
        # 1. 找出新進榜
        new_entries = merged[(merged['持有股數_old'] == 0) & (merged['持有股數'] > 0)]
        # 2. 找出剔除榜
        exited = merged[(merged['持有股數_old'] > 0) & (merged['持有股數'] == 0)]
        # 3. 找出加碼王 (股數增加最多)
        top_buy = merged.sort_values('股數變化', ascending=False).head(1)
        # 4. 找出減碼王 (股數減少最多)
        top_sell = merged.sort_values('股數變化', ascending=True).head(1)
        
        report = ""
        
        # 撰寫報告內容
        if not new_entries.empty:
            names = ", ".join(new_entries['股票名稱'].tolist())
            report += f"\n🔥 **新進榜**: {names}"
            
        if not exited.empty:
            names = ", ".join(exited['股票名稱'].tolist())
            report += f"\n👋 **剔除榜**: {names}"
            
        if not top_buy.empty and top_buy['股數變化'].values[0] > 0:
            name = top_buy['股票名稱'].values[0]
            change = int(top_buy['股數變化'].values[0])
            report += f"\n📈 **加碼王**: {name} (+{change:,} 股)"
            
        if not top_sell.empty and top_sell['股數變化'].values[0] < 0:
            name = top_sell['股票名稱'].values[0]
            change = int(top_sell['股數變化'].values[0])
            report += f"\n📉 **減碼王**: {name} ({change:,} 股)"
            
        if report == "":
            report = "\n(💤 今日持股無顯著變化)"
            
        return report

    except Exception as e:
        return f"\n(⚠️ 戰報生成失敗: {e})"

# ★★★ 核心大腦：標準化清洗函式 ★★★
def standardize_df(df, source_name=""):
    if df.empty: return df
    
    # 強制位置對應
    if source_name == "00981A" and len(df.columns) >= 4:
        df = df.iloc[:, :4] 
        df.columns = ['股票代號', '股票名稱', '持有股數', '權重']
    elif source_name == "00991A" and len(df.columns) >= 5:
        df = df.iloc[:, [0, 1, 2, 4]]
        df.columns = ['股票代號', '股票名稱', '持有股數', '權重']
    else:
        col_map = {
            '股票代號': ['股票代號', '代號', '證券代號', 'Code'],
            '股票名稱': ['股票名稱', '名稱', '證券名稱', 'Name'],
            '持有股數': ['持有股數', '股數', '庫存股數', 'Shares'],
            '權重': ['權重', '權重(%)', '比例', '持股(%)', '持股比率', 'Weight']
        }
        for target, cands in col_map.items():
            for cand in cands:
                matches = [c for c in df.columns if str(c).strip() in cands]
                if matches:
                    df.rename(columns={matches[0]: target}, inplace=True)
                    break

    for col in ['持有股數', '權重']:
        if col in df.columns:
            df[col] = df[col].astype(str).str.replace('%', '').str.replace(',', '').str.replace('-', '0')
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    required = ['股票代號', '股票名稱', '持有股數', '權重']
    for req in required:
        if req not in df.columns:
            if req == '權重': df[req] = 0 
            elif req == '股票代號': df[req] = 'N/A'
    
    df = df[df['股票代號'] != '股票代號']
    df = df[df['股票代號'] != '證券代號']

    return df[['股票代號', '股票名稱', '持有股數', '權重']]

def smart_read_excel(content):
    try:
        temp_df = pd.read_excel(io.BytesIO(content), header=None, nrows=20)
        header_row = -1
        for i, row in temp_df.iterrows():
            row_str = row.astype(str).str.cat()
            if "股票代號" in row_str or "Code" in row_str:
                header_row = i
                break
        return pd.read_excel(io.BytesIO(content), header=header_row) if header_row != -1 else pd.DataFrame()
    except: return pd.DataFrame()

def get_fuhhwa_aggressive(url):
    print(f"🤖 啟動 Chrome 前往復華官網: {url}")
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    driver = None
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.get(url)
        time.sleep(8)
        
        max_clicks = 10
        click_count = 0
        while click_count < max_clicks:
            try:
                buttons = driver.find_elements(By.XPATH, "//*[contains(text(),'更多') or contains(text(),'全部') or contains(text(),'查閱')]")
                clicked = False
                for btn in buttons:
                    if btn.is_displayed():
                        driver.execute_script("arguments[0].scrollIntoView(true);", btn)
                        time.sleep(1)
                        driver.execute_script("arguments[0].click();", btn)
                        time.sleep(3)
                        clicked = True
                        click_count += 1
                        break
                if not clicked: break
            except: break

        dfs = pd.read_html(driver.page_source)
        best_df = pd.DataFrame()
        max_rows = 0
        for temp in dfs:
            if len(temp) > max_rows and len(temp.columns) >= 3:
                max_rows = len(temp)
                best_df = temp
        return best_df
    except Exception as e:
        print(f"❌ 復華爬蟲失敗: {e}")
        return pd.DataFrame()
    finally:
        if driver: driver.quit()

def get_etf_data(etf_code):
    df = pd.DataFrame()
    if etf_code == "00981A":
        roc_date = get_roc_date_string(0)
        url = f"https://www.ezmoney.com.tw/ETF/Transaction/PCFExcelNPOI?fundCode=49YTW&date={roc_date}&specificDate=false"
        print(f"📥 下載統一 (00981A): {url}")
        try:
            res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
            df = smart_read_excel(res.content)
            if df.empty:
                roc_date_yest = get_roc_date_string(-1)
                url_yest = f"https://www.ezmoney.com.tw/ETF/Transaction/PCFExcelNPOI?fundCode=49YTW&date={roc_date_yest}&specificDate=false"
                res = requests.get(url_yest, headers={"User-Agent": "Mozilla/5.0"})
                df = smart_read_excel(res.content)
        except Exception as e: print(f"❌ 統一失敗: {e}")

    elif etf_code == "00991A":
        url = "https://www.fhtrust.com.tw/ETF/etf_detail/ETF23#stockhold"
        df = get_fuhhwa_aggressive(url)

    return standardize_df(df, source_name=etf_code)

def process_etf(etf_code, etf_name):
    print(f"\n--- 處理 {etf_name} ({etf_code}) ---")
    
    file_path = f'data/{etf_code}_history.csv'
    
    # 自動修復
    if os.path.exists(file_path):
        try:
            check_df = pd.read_csv(file_path)
            if '權重' not in check_df.columns:
                os.remove(file_path)
            elif not check_df.empty and '權重' in check_df.columns and check_df['權重'].sum() == 0:
                os.remove(file_path)
        except: pass

    # 1. 抓取今日
    df_new = get_etf_data(etf_code)
    
    if df_new.empty: 
        print(f"⚠️ 無法獲取數據，跳過。")
        return f"⚠️ {etf_name} 無法獲取數據"
    
    today_str = datetime.now().strftime('%Y-%m-%d')
    if '股票代號' in df_new.columns:
        df_new['股票代號'] = df_new['股票代號'].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    df_new['Date'] = today_str

    # 2. 合併與去重
    if os.path.exists(file_path):
        try:
            old_df = pd.read_csv(file_path, dtype=str)
            final_df = pd.concat([df_new, old_df], ignore_index=True)
            final_df = final_df.drop_duplicates(subset=['Date', '股票代號'], keep='first')
        except:
            final_df = df_new
    else:
        final_df = df_new

    # 3. 存檔
    final_df.to_csv(file_path, index=False, encoding='utf-8-sig')
    
    # ★★★ 4. 生成戰報 (Analysis) ★★★
    report = generate_daily_report(final_df)
    
    return f"✅ **{etf_name}** 更新成功{report}\n"

def main():
    if not os.path.exists('data'): os.makedirs('data')
    
    msg = ""
    msg += process_etf("00981A", "主動統一")
    msg += "\n--------------------\n"
    msg += process_etf("00991A", "主動復華未來")
    
    print(msg)
    
    # 發送 Discord 通知
    send_discord_notify(msg)

if __name__ == "__main__":
    main()
