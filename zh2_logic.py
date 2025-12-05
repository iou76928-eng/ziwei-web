# zh2_logic.py
# -*- coding: utf-8 -*-
import re

# ==========================================
# 1. 定義宮位轉換邏輯 (從 zh2.py 移植)
# ==========================================
map_wealth_decade = {
    "大命": "大財帛的官祿宮", "大兄": "大財帛的田宅宮", "大夫": "大財帛的福德宮",
    "大子": "大財帛的父母宮", "大財": "大財帛的命宮",   "大疾": "大財帛的兄弟宮",
    "大遷": "大財帛的夫妻宮", "大友": "大財帛的子女宮", "大僕": "大財帛的子女宮",
    "大官": "大財帛的財帛宮", "大田": "大財帛的疾厄宮", "大福": "大財帛的遷移宮",
    "大父": "大財帛的朋友宮"
}
map_wealth_annual = {
    "流命": "流財帛的官祿宮", "流兄": "流財帛的田宅宮", "流夫": "流財帛的福德宮",
    "流子": "流財帛的父母宮", "流財": "流財帛的命宮",   "流疾": "流財帛的兄弟宮",
    "流遷": "流財帛的夫妻宮", "流友": "流財帛的子女宮", "流僕": "流財帛的子女宮",
    "流官": "流財帛的財帛宮", "流田": "流財帛的疾厄宮", "流福": "流財帛的遷移宮",
    "流父": "流財帛的朋友宮"
}
map_career_decade = {
    "大命": "大事業的財帛宮", "大兄": "大事業的疾厄宮", "大夫": "大事業的遷移宮",
    "大子": "大事業的朋友宮", "大財": "大事業的官祿宮", "大疾": "大事業的田宅宮",
    "大遷": "大事業的福德宮", "大友": "大事業的父母宮", "大僕": "大事業的父母宮",
    "大官": "大事業的命宮",   "大田": "大事業的兄弟宮", "大福": "大事業的夫妻宮",
    "大父": "大事業的子女宮"
}
map_career_annual = {
    "流命": "流事業的財帛宮", "流兄": "流事業的疾厄宮", "流夫": "流事業的遷移宮",
    "流子": "流事業的朋友宮", "流財": "流事業的官祿宮", "流疾": "流事業的田宅宮",
    "流遷": "流事業的福德宮", "流友": "流事業的父母宮", "流僕": "流事業的父母宮",
    "流官": "流事業的命宮",   "流田": "流事業的兄弟宮", "流福": "流事業的夫妻宮",
    "流父": "流事業的子女宮"
}

title_map = {
    "大財": "大限財帛命宮", "流財": "流年財帛命宮",
    "大官": "大限官祿命宮", "流官": "流年官祿命宮"
}

BLOCK_TITLES = {
    1: "第一區塊 : 大限課題",
    2: "第二區塊 : 大限財帛",
    3: "第三區塊 : 大限事業",
    4: "第四區塊 : 流年課題",
    5: "第五區塊 : 流年財帛",
    6: "第六區塊 : 流年事業",
    7: "第七區塊 : 客戶類型",
    8: "第八區塊 : 流月命/遷 運勢",
    9: "第九區塊 : 流日命/遷 運勢"
}

def is_header_line(line):
    keywords = ["目前年紀", "大限區間", "目前流年", "流年干", "地支干"]
    return any(k in line for k in keywords)

def get_block_trigger(line):
    # 優先順序：財/官 -> 友 -> 命
    if any(line.startswith(k) for k in ["大限財帛", "大財", "化大財", "化大限財帛"]): return 2
    if any(line.startswith(k) for k in ["大限官祿", "大官", "化大官", "化大限官祿"]): return 3
    if any(line.startswith(k) for k in ["流年財帛", "流財", "化流財", "化流年財帛"]): return 5
    if any(line.startswith(k) for k in ["流年官祿", "流官", "化流官", "化流年官祿"]): return 6
    
    if any(line.startswith(k) for k in ["大友", "大僕"]): return 1
    if any(line.startswith(k) for k in ["流友", "流僕"]): return 4
    
    if any(line.startswith(k) for k in ["大命", "化大命"]): return 1
    if any(line.startswith(k) for k in ["流命", "化流命"]): return 4
    return None 

def colorize_html(text):
    """將文字中的關鍵字轉為 HTML span 標籤"""
    # 四化顏色
    text = text.replace("祿", '<span class="lu">祿</span>')
    text = text.replace("權", '<span class="quan">權</span>')
    text = text.replace("科", '<span class="ke">科</span>')
    text = text.replace("忌", '<span class="ji">忌</span>')
    
    # 運勢好壞
    text = text.replace("運勢 好", '<span class="luck-good">運勢 好</span>')
    text = text.replace("運勢 差", '<span class="luck-bad">運勢 差</span>')
    
    # 星系標籤變色
    if "星系 :" in text:
        parts = text.split("星系 :", 1)
        text = f'<span class="star-label">{parts[0]}星系 :</span>{parts[1]}'
        
    # 化XX 開頭變粗體
    clean_text = re.sub(r'<[^>]+>', '', text) # 簡易移除標籤檢查純文字
    if clean_text.strip().startswith("化"):
        text = f'<span class="bold-text">{text}</span>'
        
    return text

def process_ziwei_data(raw_data):
    """主要處理函式：接收 ziwei_core 的輸出，回傳 9 個區塊的 HTML 字串字典"""
    if not raw_data:
        return {}

    lines = raw_data.split('\n')
    buffers = {i: [] for i in range(1, 10)}
    pending_headers = []
    
    current_block = 1  
    current_mode = None 
    
    # 摘要資料收集
    summary_data = {
        "d_wealth_stars": "", "d_wealth_lu": "",
        "d_career_stars": "", "d_career_lu": "",
        "d_friend": "",
        "a_wealth_stars": "", "a_wealth_lu": "",
        "a_career_stars": "", "a_career_lu": "",
        "a_friend": ""
    }

    for line in lines:
        line_stripped = line.strip()
        if not line_stripped: continue
        
        # 1. 處理分隔線 (Reset logic)
        if line_stripped.startswith("===="):
            pending_headers = [] 
            if "大限" in line_stripped:
                current_block = 1
                current_mode = None
            elif "流年" in line_stripped:
                current_block = 4
                current_mode = None
            elif "流月" in line_stripped: 
                current_block = 8
                current_mode = None
            elif "流日" in line_stripped: 
                current_block = 9
                current_mode = None
            continue 

        # 2. 標頭緩衝
        if current_block <= 6 and is_header_line(line_stripped):
            pending_headers.append(line_stripped)
            continue

        # 3. 判斷 Trigger
        new_block = get_block_trigger(line_stripped)
        
        if current_block <= 6 and new_block is not None:
            current_block = new_block
            
            if current_block in [2, 5]: current_mode = 'wealth'
            elif current_block in [3, 6]: current_mode = 'career'
            else: current_mode = None
            
            if pending_headers:
                buffers[current_block].extend(pending_headers)
                pending_headers = [] 

        elif pending_headers:
             buffers[current_block].extend(pending_headers)
             pending_headers = []

        # === 內容轉換 ===
        display_line = line_stripped
        
        # 標題替換
        for key, val in title_map.items():
            if display_line.startswith(key):
                display_line = display_line.replace(key, val, 1)
                break
            elif display_line.startswith("化" + key):
                display_line = display_line.replace(key, val, 1)
                break

        # 宮位轉換
        if current_mode:
            if current_mode == 'wealth':
                map_decade = map_wealth_decade
                map_annual = map_wealth_annual
            else: 
                map_decade = map_career_decade
                map_annual = map_career_annual
            
            pattern = r'((?:大|流)[命兄夫子財疾遷友僕官田福父])(?:宮)?'
            def replace_palace(match):
                code = match.group(1)
                if code.startswith("大") and code in map_decade:
                    return f"/{map_decade[code]}"
                if code.startswith("流") and code in map_annual:
                    return f"/{map_annual[code]}"
                return match.group(0)

            display_line = re.sub(pattern, replace_palace, display_line)
            display_line = display_line.replace("//", "/")
            display_line = display_line.replace(": /", ": ")

        # === 摘要資料擷取 (Block 7) ===
        check_text = display_line.strip()
        if check_text.startswith("大財星系") or check_text.startswith("大限財帛命宮星系"): 
            summary_data["d_wealth_stars"] = display_line
        elif check_text.startswith("大財祿入") or check_text.startswith("大限財帛命宮祿入"): 
            summary_data["d_wealth_lu"] = display_line
        elif check_text.startswith("大官星系") or check_text.startswith("大限官祿命宮星系"): 
            summary_data["d_career_stars"] = display_line
        elif check_text.startswith("大官祿入") or check_text.startswith("大限官祿命宮祿入"): 
            summary_data["d_career_lu"] = display_line
        elif check_text.startswith("大友星系"): 
            summary_data["d_friend"] = display_line
        elif check_text.startswith("流財星系") or check_text.startswith("流年財帛命宮星系"): 
            summary_data["a_wealth_stars"] = display_line
        elif check_text.startswith("流財祿入") or check_text.startswith("流年財帛命宮祿入"): 
            summary_data["a_wealth_lu"] = display_line
        elif check_text.startswith("流官星系") or check_text.startswith("流年官祿命宮星系"): 
            summary_data["a_career_stars"] = display_line
        elif check_text.startswith("流官祿入") or check_text.startswith("流年官祿命宮祿入"): 
            summary_data["a_career_lu"] = display_line
        elif check_text.startswith("流友星系"): 
            summary_data["a_friend"] = display_line

        # === 存入緩衝區 ===
        is_friend_stars = check_text.startswith("大友星系") or check_text.startswith("流友星系")

        if current_block in [8, 9]:
            buffers[current_block].append(display_line)
        elif not is_friend_stars:
            target = current_block if current_block != 7 else 1
            buffers[target].append(display_line)

    # === 構建 Block 7 內容 ===
    buffers[7] = [
        "===客戶類型===",
        summary_data["d_wealth_stars"], summary_data["d_wealth_lu"],
        summary_data["d_career_stars"], summary_data["d_career_lu"],
        summary_data["d_friend"],
        "", 
        summary_data["a_wealth_stars"], summary_data["a_wealth_lu"],
        summary_data["a_career_stars"], summary_data["a_career_lu"],
        summary_data["a_friend"]
    ]
    buffers[7] = [line for line in buffers[7] if line is not None] # 清理 None

    # === 轉為 HTML 格式 ===
    final_blocks = {}
    for b_id in range(1, 10):
        title = BLOCK_TITLES.get(b_id, f"區塊 {b_id}")
        content_lines = buffers[b_id]
        
        # 著色並組合成 HTML
        html_content = ""
        for line in content_lines:
            if not line:
                html_content += "<br>"
            else:
                html_content += colorize_html(line) + "<br>"
        
        final_blocks[b_id] = {
            "title": title,
            "content": html_content
        }
        
    return final_blocks