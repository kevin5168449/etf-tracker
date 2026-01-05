import pandas as pd
import requests
import os
from datetime import datetime
import io

# --- 設定 Discord Webhook ---
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK")

def send_discord_notify(msg):
    if not DISCORD_WEBHOOK:
        print("⚠️ 未設定 DISCORD_WEBHOOK，跳過通知")
        return
    
    data = {"content": msg, "username": "ETF 監控小幫手"}
    
    try:
        result = requests.post(DISCORD_WEBHOOK, json=data)
        if 200 <= result.status_code < 300:
            print("✅ Discord 通知發送成功")
        else:
            print(f"❌ 發送失敗: {result.text}")
    except Exception as e:
        print(f"❌ 發送錯誤: {e}")

# 小工具：自動產生「民國年」日期字串 (格式：115/01/06)
def get_roc_date_string():
    now = datetime.now()
    roc_year = now.year - 1911
    return f"{roc_year}/{now.month:02d}/{now.day:02d}"

def get_etf_data(etf_code):
    df = pd.DataFrame()
    
    # ==========================================
    # 統一投信 (00981A) - 自動帶入今天日期
    # ==========================================
    if etf_code == "00981A":
        # 這裡會自動產生像 "115/01/07" 的日期
        roc_date = get_roc_date_string()
        url = f"https://www.ezmoney.com.tw/ETF/Transaction/PCFExcelNPOI?fundCode=61YTW&date={roc_date}&specificDate=false"
        print(f"📥 正在下載統一 (00981A): {url} ...")
        
        try:
            # 偽裝成瀏覽器
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            response = requests.get(url, headers=headers)
            # 統一通常是 Excel 格式
            try:
                df = pd.read_excel(io.BytesIO(response.content))
            except:
                # 萬一它是 HTML 格式
                dfs = pd.read_html(io.BytesIO(response.content))
                if dfs: df = dfs[0]

        except Exception as e:
            print(f"❌ 統一 (00981A) 下載失敗: {e}")
            return pd.DataFrame()

    # ==========================================
    # 野村投信 (00980A) - 爬取網頁表格
    # ==========================================
    elif etf_code == "00980A":
        # 您剛剛提供的網址
        url = "https://www.nomurafunds.com.tw/ETFWEB/product-description?fundNo=00980A&tab=Shareholding"
        print(f"🕷️ 正在爬取野村 (00980A): {url} ...")
        
        try:
            # 使用 pd.read_html 直接抓網頁上的表格
            # 注意：如果網頁跑太慢或用 JavaScript 渲染，可能會抓不到，這時候需要進階技巧
            # 但我們先試試看最簡單的 read_html
            headers = {"User-Agent": "Mozilla/5.0"}
            response = requests.get(url, headers=headers)
            
            # 指定 encoding='utf-8' 防止亂碼
            tables = pd.read_html(response.text)
            
            if len(tables) > 0:
                # 通常第一個表格就是持股名單
                df = tables[0]
                print(f"✅ 野村抓取成功！原始欄位: {df.columns.tolist()}")
            else:
                print("⚠️ 野村網頁上找不到表格 (可能是動態網頁)")
                return pd.DataFrame()
                
        except Exception as e:
            print(f"❌ 野村爬取失敗: {e}")
            return pd.DataFrame()
    
    # --- 統一欄位名稱 (標準化) ---
    # 為了讓後面好比較，我們要幫欄位改名
    column_mapping = {
        '股票代號': ['股票代號', 'Code', '證券代號', '標的代號', 'Stock Code'],
        '股票名稱': ['股票名稱', 'Name', '證券名稱', '標的名稱', 'Stock Name'],
        '持有股數': ['持有股數', 'Shares', '庫存股數', '股數', '持有股數/單位數', 'Shares/Units']
    }
    
    # 自動改名
    for target, candidates in column_mapping.items():
        for candidate in candidates:
            # 部分比對 (防止欄位有空白鍵)
            matches = [col for col in df.columns if str(col).strip() in candidates]
            if matches:
                df.rename(columns={matches[0]: target}, inplace=True)
                break
                
    # 只留我們需要的欄位
    required = ['股票代號', '股票名稱', '持有股數']
    # 確保欄位存在
    available = [c for c in required if c in df.columns]
    
    if len(available) == 3:
        return df[required]
    else:
        print(f"⚠️ {etf_code} 欄位對應不完整，目前欄位: {df.columns.tolist()}")
        # 嘗試印出前幾行來除錯
        print(df.head())
        return pd.DataFrame()

def process_etf(etf_code, etf_name):
    print(f"\n🔄 處理中: {etf_name} ({etf_code})...")
    
    # 1. 抓資料
    df_new = get_etf_data(etf_code)
    
    if df_new.empty:
        print(f"⚠️ {etf_name} 無法獲取數據，跳過比對。")
        return ""

    today_str = datetime.now().strftime('%Y-%m-%d')
    history_file = f'data/{etf_code}_history.csv'
    
    # 強制轉字串 (修復 Bug)
    if '股票代號' in df_new.columns:
        df_new['股票代號'] = df_new['股票代號'].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    df_new['Date'] = today_str

    # 2. 比較邏輯
    msg = ""
    if os.path.exists(history_file):
        try:
            df_history = pd.read_csv(history_file, dtype={'股票代號': str})
            if not df_history.empty:
                last_date = df_history['Date'].max()
                df_old = df_history[df_history['Date'] == last_date].copy()
                df_old['股票代號'] = df_old['股票代號'].astype(str).str.strip()
                
                # 合併
                merged = pd.merge(df_new, df_old, on=['股票代號', '股票名稱'], how='left', suffixes=('', '_old'))
                merged['股數變化'] = merged['持有股數'] - merged['持有股數_old'].fillna(0)
                changes = merged[merged['股數變化'] != 0]
                
                if not changes.empty:
                    msg = f"\n📊 **[{etf_code} {etf_name}] 持股異動:**\n"
                    for _, row in changes.iterrows():
                        change = int(row['股數變化'])
                        icon = "🔴減" if change < 0 else "🟢加"
                        sheets = change / 1000
                        # 只顯示變化超過 0.1 張的
                        if abs(sheets) >= 0.1:
                            msg += f"{icon} **{row['股票名稱']}** ({row['股票代號']}): {change:,} 股 ({sheets:+.1f}張)\n"
        except Exception as e:
            print(f"比對歷史資料時發生錯誤: {e}")

    # 3. 存檔
    mode = 'a' if os.path.exists(history_file) else 'w'
    header = not os.path.exists(history_file)
    df_new.to_csv(history_file, mode=mode, header=header, index=False)
    print(f"✅ {etf_name} 數據存檔完成")
    
    return msg

def main():
    print("🚀 啟動 ETF 雙監控系統 (Unified + Nomura)...")
    if not os.path.exists('data'):
        os.makedirs('data')
        
    final_msg = ""
    
    # 執行統一 (00981A)
    final_msg += process_etf("00981A", "主動統一") or ""
    
    # 執行野村 (00980A)
    final_msg += process_etf("00980A", "主動野村") or ""

    if final_msg:
        print("準備發送 Discord 通知...")
        send_discord_notify(final_msg)
    else:
        print("💤 今日兩檔 ETF 皆無顯著異動 (或下載失敗)。")

if __name__ == "__main__":
    main()
