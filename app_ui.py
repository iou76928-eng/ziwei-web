# -*- coding: utf-8 -*-
import sys
import os  # <---【修正1】補上這裡，不然讀不到環境變數會報錯
import webbrowser
from threading import Timer
from flask import Flask, request, render_template_string
from bs4 import BeautifulSoup
import re
import time

# === 匯入核心與邏輯轉接器 ===
try:
    import ziwei_core as engine
    import zh2_logic as logic_adapter
except ImportError as e:
    print(f"【嚴重錯誤】找不到模組！{e}。請確保 ziwei_core.py 與 zh2_logic.py 在同一目錄下。")
    sys.exit(1)

# === Selenium 相關套件 ===
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import Select
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options
except ImportError:
    print("【嚴重錯誤】缺少 Selenium 套件！請執行 pip install selenium")
    sys.exit(1)

app = Flask(__name__)

# ================= 爬蟲層 (Data Layer) =================
def scrape_and_format_raw_text(year, month, day, hour, gender_val):
    driver = None
    try:
        print(f"【爬蟲啟動】目標：{year}/{month}/{day} {hour}時 (性別:{gender_val})")
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        
        # === 極限省記憶體設定 ===
        options.add_argument("--window-size=1024,768")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-infobars")
        
        # 設定 Chrome 不載入圖片 (Image Block)
        prefs = {
            "profile.managed_default_content_settings.images": 2, 
            "profile.default_content_setting_values.notifications": 2
        }
        options.add_experimental_option("prefs", prefs)

        # Chrome binary 位置 (Render 環境專用)
        chrome_bin = os.environ.get("CHROME_BIN")
        if chrome_bin:
            options.binary_location = chrome_bin

        # 【修正2】這裡原本有兩行 driver = ...，我刪掉了一行，只留一行
        driver = webdriver.Chrome(options=options)
        
        driver.get("https://fate.windada.com/cgi-bin/fate")
        
        WebDriverWait(driver, 15).until(lambda d: "紫微" in d.title)
        
        try:
            el = driver.find_element(By.ID, "bYear")
            el.clear()
            el.send_keys(str(year))
            Select(driver.find_element(By.ID, "bMonth")).select_by_value(str(month))
            Select(driver.find_element(By.ID, "bDay")).select_by_value(str(day))
            Select(driver.find_element(By.ID, "bHour")).select_by_value(str(hour))
            target_id = "bMale" if str(gender_val) == "1" else "bFemale"
            driver.execute_script("arguments[0].click();", driver.find_element(By.ID, target_id))
        except Exception as e:
            return f"填表過程錯誤: {e}"

        try:
            driver.find_element(By.CSS_SELECTOR, "input[type='submit']").click()
        except:
            driver.execute_script("document.forms[0].submit();")

        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.XPATH, "//table[contains(@style, 'border:2px solid black')]"))
            )
        except:
            print("等待逾時，嘗試直接抓取...")
        
        page_html = driver.page_source

    except Exception as e:
        return f"瀏覽器執行錯誤: {str(e)}"
    finally:
        if driver: driver.quit() 

    soup = BeautifulSoup(page_html, 'html.parser')
    
    header_lines = []
    center_cell = soup.find("td", {"colspan": "2"})
    if center_cell:
        full_text = center_cell.get_text(separator="\n")
        for line in full_text.split('\n'):
            line = line.strip()
            if any(k in line for k in ["干支", "命主", "身主", "陽曆", "農曆", "五行", "局", "生年"]):
                header_lines.append(line)
    
    cells = []
    palace_keywords = ["命宮", "兄弟", "夫妻", "子女", "財帛", "疾厄", 
                       "遷移", "交友", "事業", "田宅", "福德", "父母"]
    all_tds = soup.find_all('td')
    
    for td in all_tds:
        if td.get("colspan") == "2": continue
        b_tag = td.find("b")
        if not b_tag: continue
        palace_raw = b_tag.get_text(strip=True)
        palace_clean = palace_raw.replace("【", "").replace("】", "").replace("[", "").replace("]", "")
        
        is_valid_palace = False
        for pk in palace_keywords:
            if pk in palace_clean:
                is_valid_palace = True
                break
        if not is_valid_palace: continue
            
        full_text = td.get_text(separator=" ", strip=True)
        stem_match = re.search(r'([甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥])', full_text)
        stem_str = stem_match.group(1) if stem_match else "??"
        
        daxian_match = re.search(r'大限[:：\s]?(\d+-\d+)', full_text)
        if not daxian_match: daxian_match = re.search(r'(\d{1,3}-\d{1,3})', full_text)
        daxian_str = f"大限:{daxian_match.group(1)}" if daxian_match else "大限:0-0"
        
        xiaoxian_match = re.search(r'小限\s*[:：]?\s*([\d\s]+)', full_text)
        if xiaoxian_match:
            nums = xiaoxian_match.group(1).strip().split()
            xiaoxian_str = "小限:" + " ".join(nums)
        else:
            xiaoxian_str = "小限: (自動補全)"

        star_text_raw = full_text
        star_text_raw = star_text_raw.replace(stem_str, "", 1)
        star_text_raw = star_text_raw.replace(palace_raw, "")
        star_text_raw = star_text_raw.replace(f"【{palace_clean}】", "")
        if daxian_match: star_text_raw = star_text_raw.replace(daxian_match.group(0), "")
        if xiaoxian_match: star_text_raw = star_text_raw.replace(xiaoxian_match.group(0), "")
        star_text_raw = re.sub(r'大限\s*[:：]?', '', star_text_raw)
        star_text_raw = re.sub(r'小限\s*[:：]?', '', star_text_raw)
        star_text_clean = re.sub(r'\s+', ',', star_text_raw.strip())
        star_text_clean = star_text_clean.strip(',')

        formatted_cell = (
            f"{stem_str}【{palace_clean}】\n"
            f"{daxian_str}\n"
            f"{xiaoxian_str}\n" 
            f"{star_text_clean}"
        )
        cells.append(formatted_cell)

    if len(cells) < 12:
        return f"錯誤：無法解析宮位 (只抓到 {len(cells)} 個)，可能網頁改版。\n解析Log: {cells}"

    final_raw_text = "\n".join(header_lines) + "\n\n" + "\n\n".join(cells)
    return final_raw_text

# ================= 網頁介面 HTML (UI Layer) =================

HTML_TEMPLATE = """
<!doctype html>
<html lang="zh-Hant">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>紫微斗數智慧分析 (九區塊版)</title>
    <style>
        body { font-family: "Microsoft JhengHei", sans-serif; background: #121212; color: #e0e0e0; margin: 0; padding: 20px; }
        .container { max-width: 1400px; margin: 0 auto; background: #1e1e1e; padding: 25px; border-radius: 12px; border: 1px solid #333; box-shadow: 0 4px 20px rgba(0,0,0,0.5); }
        h1 { color: #bb86fc; text-align: center; margin-bottom: 5px; }
        .subtitle { text-align: center; color: #888; font-size: 0.9em; margin-bottom: 25px; }
        
        .control-panel { display: flex; flex-wrap: wrap; gap: 15px; background: #2c2c2c; padding: 20px; border-radius: 8px; border-left: 5px solid #bb86fc; }
        .form-group { flex: 1; min-width: 80px; }
        label { display: block; margin-bottom: 5px; font-weight: bold; color: #cfcfcf; font-size: 0.9rem; }
        select, input { width: 100%; padding: 10px; background: #383838; border: 1px solid #555; color: #fff; border-radius: 4px; font-size: 1rem; }
        select:focus, input:focus { border-color: #bb86fc; outline: none; }
        
        .btn-submit { width: 100%; padding: 12px; background: #bb86fc; color: #000; font-weight: bold; border: none; border-radius: 6px; cursor: pointer; transition: 0.2s; font-size: 1.1rem; margin-top: 10px; }
        .btn-submit:hover { background: #a370f7; }
        .btn-submit:disabled { background: #555; cursor: not-allowed; }

        .loading-overlay { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); z-index: 999; text-align: center; padding-top: 20vh; }
        .loading-text { color: #bb86fc; font-size: 2rem; font-weight: bold; }
        .error-msg { background: #cf6679; color: #000; padding: 15px; border-radius: 6px; margin-top: 20px; font-weight: bold; }

        /* 九區塊佈局 */
        .grid-container {
            display: grid;
            grid-template-columns: repeat(3, 1fr); /* 3欄 */
            gap: 15px;
            margin-top: 30px;
        }
        @media (max-width: 900px) {
            .grid-container { grid-template-columns: repeat(2, 1fr); }
        }
        @media (max-width: 600px) {
            .grid-container { grid-template-columns: 1fr; }
        }

        .block-card {
            background: #252526;
            border: 1px solid #444;
            border-radius: 8px;
            overflow: hidden;
            display: flex;
            flex-direction: column;
        }
        /* 讓流日運勢 (區塊9) 跨兩欄顯示 (如果寬度夠) */
        .block-9 {
            grid-column: span 1; /* 預設不跨 */
        }
        @media (min-width: 900px) {
            .block-9 { grid-column: span 1; } /* 可自行調整為 span 3 讓它在最下面全寬 */
        }

        .block-header {
            background: #003366;
            color: #fff;
            padding: 10px 15px;
            font-weight: bold;
            font-size: 1.1rem;
            border-bottom: 1px solid #444;
        }
        .block-content {
            padding: 15px;
            font-family: "Microsoft JhengHei", sans-serif;
            font-size: 0.95rem;
            line-height: 1.6;
            color: #ddd;
            overflow-y: auto;
            max-height: 400px;
        }

        /* 顏色標籤 CSS (對應 zh2.py 的 logic) */
        .lu { color: #27ae60; font-weight: bold; }
        .quan { color: #9b59b6; font-weight: bold; }
        .ke { color: #2980b9; font-weight: bold; }
        .ji { color: #e74c3c; font-weight: bold; }
        .star-label { color: #888; font-weight: bold; }
        .bold-text { font-weight: bold; color: #fff; }
        .luck-good { color: #d35400; font-weight: bold; }
        .luck-bad { color: #7f8c8d; font-weight: bold; }
        
        .raw-data-area {
            margin-top: 30px;
            border-top: 1px solid #444;
            padding-top: 20px;
        }
        .raw-data-area textarea {
            width: 100%; height: 150px;
            background: #111; color: #0f0; border: 1px solid #444;
            font-family: monospace;
        }
    </style>
    <script>
        function showLoading() {
            document.getElementById('loading').style.display = 'block';
            document.getElementById('submitBtn').disabled = true;
            document.getElementById('submitBtn').innerText = '分析運算中...';
        }
    </script>
</head>
<body>
    <div id="loading" class="loading-overlay">
        <div class="loading-text">🔮 命盤解析中...</div>
        <p style="color:#fff;">爬蟲取盤 -> 核心運算 -> 九宮格重組</p>
    </div>

    <div class="container">
        <h1>🌌 紫微斗數智慧分析 (Web整合版)</h1>
        <div class="subtitle">爬蟲 + 核心運算 + 自動九區塊分類</div>
        
        <form method="post" onsubmit="showLoading()">
            <div class="control-panel">
                <div class="form-group">
                    <label>性別</label>
                    <select name="sex">
                        <option value="1" {% if sex=='1' %}selected{% endif %}>男</option>
                        <option value="0" {% if sex=='0' %}selected{% endif %}>女</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>出生年 (西元)</label>
                    <input type="number" name="year" value="{{ year }}" required>
                </div>
                <div class="form-group">
                    <label>月</label>
                    <select name="month">
                        {% for i in range(1, 13) %}
                        <option value="{{ i }}" {% if month==i|string %}selected{% endif %}>{{ i }}</option>
                        {% endfor %}
                    </select>
                </div>
                <div class="form-group">
                    <label>日</label>
                    <select name="day">
                        {% for i in range(1, 32) %}
                        <option value="{{ i }}" {% if day==i|string %}selected{% endif %}>{{ i }}</option>
                        {% endfor %}
                    </select>
                </div>
                <div class="form-group">
                    <label>時辰 (0-23)</label>
                    <select name="hour">
                        {% for i in range(0, 24) %}
                        <option value="{{ i }}" {% if hour==i|string %}selected{% endif %}>{{ i }}點</option>
                        {% endfor %}
                    </select>
                </div>
                <div class="form-group" style="min-width: 120px;">
                    <label>分析流年</label>
                    <input type="number" name="target_year" value="{{ target_year }}">
                </div>
                <div style="flex-basis: 100%;">
                    <button type="submit" class="btn-submit" id="submitBtn">開始分析</button>
                </div>
            </div>
        </form>

        {% if error %}
            <div class="error-msg">⚠️ 執行錯誤：<br>{{ error }}</div>
        {% endif %}

        {% if blocks %}
        <div class="grid-container">
            {% for bid in range(1, 10) %}
            <div class="block-card block-{{ bid }}">
                <div class="block-header">{{ blocks[bid].title }}</div>
                <div class="block-content">
                    {{ blocks[bid].content | safe }}
                </div>
            </div>
            {% endfor %}
        </div>
        
        <div class="raw-data-area">
            <details>
                <summary style="cursor:pointer; color:#888;">查看原始命盤數據 (Raw Data)</summary>
                <textarea readonly>{{ raw_data }}</textarea>
            </details>
        </div>
        {% endif %}
    </div>
</body>
</html>
"""

# ================= 路由控制 (Controller) =================

@app.route("/", methods=["GET", "POST"])
def index():
    default_target_year = engine.current_year() + 1
    
    context = {
        "year": "1992", "month": "9", "day": "25", "hour": "7", 
        "sex": "0", 
        "target_year": default_target_year, 
        "blocks": None, "error": "", "raw_data": ""
    }

    if request.method == "POST":
        try:
            year = request.form.get("year")
            month = request.form.get("month")
            day = request.form.get("day")
            hour = request.form.get("hour")
            sex = request.form.get("sex")
            target_year_str = request.form.get("target_year")
            
            context.update({
                "year": year, "month": month, "day": day, "hour": hour, 
                "sex": sex, "target_year": target_year_str
            })
            
            target_year = int(target_year_str) if target_year_str else default_target_year

            # 1. 執行爬蟲
            raw_data = scrape_and_format_raw_text(year, month, day, hour, sex)
            
            if "錯誤" in raw_data and "【" not in raw_data:
                context["error"] = raw_data
            else:
                context["raw_data"] = raw_data
                try:
                    # 2. 核心分析
                    final_res_text = engine.run_chart_from_text(raw_data, target_year=target_year)
                    
                    # 3. 呼叫 zh2_logic 進行九區塊重組
                    # 這裡就是你要的整合點：將 core 的文字輸出轉給 logic 處理
                    blocks_data = logic_adapter.process_ziwei_data(final_res_text)
                    context["blocks"] = blocks_data
                    
                except Exception as logic_error:
                    import traceback
                    traceback.print_exc()
                    context["error"] = f"分析失敗：{str(logic_error)}"
                    
        except Exception as e:
            context["error"] = f"系統執行例外：{str(e)}"

    return render_template_string(HTML_TEMPLATE, **context)

def open_browser():
    webbrowser.open_new("http://127.0.0.1:5000")

if __name__ == "__main__":
    print(f"=== 紫微斗數 Web UI 啟動 (連結核心版本: {getattr(engine, 'CYEAR', 'Unknown')}) ===")
    Timer(1, open_browser).start()

    app.run(host="0.0.0.0", port=5000, debug=False)
