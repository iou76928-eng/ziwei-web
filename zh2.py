import tkinter as tk
from tkinter import scrolledtext, messagebox
import re

# ==========================================
# 1. 定義宮位轉換邏輯
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

# ==========================================
# 2. 核心應用程式
# ==========================================

class ZiweiApp:
    def __init__(self, root):
        self.root = root
        self.root.title("紫微斗數轉換器 (九區塊-順序調整版)")
        self.root.geometry("880x950") 

        # 上方輸入區
        frame_top = tk.Frame(root)
        frame_top.pack(fill=tk.BOTH, expand=False, padx=10, pady=5)
        tk.Label(frame_top, text="【原始資料輸入】", font=("微軟正黑體", 10, "bold")).pack(anchor="w")
        self.input_text = scrolledtext.ScrolledText(frame_top, height=8, font=("Consolas", 10))
        self.input_text.pack(fill=tk.BOTH, expand=True)
        
        # 按鈕
        btn_convert = tk.Button(root, text="⬇️ 執行轉換 (調整順序) ⬇️", 
                                font=("微軟正黑體", 12, "bold"), 
                                bg="#4CAF50", fg="white", 
                                command=self.run_conversion)
        btn_convert.pack(fill=tk.X, padx=10, pady=5, ipady=5)

        # 結果區
        self.canvas_frame = tk.Frame(root)
        self.canvas_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.canvas = tk.Canvas(self.canvas_frame)
        self.scrollbar = tk.Scrollbar(self.canvas_frame, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = tk.Frame(self.canvas)
        self.scrollable_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        # 建立 9 個區塊，調整順序與標題
        self.result_widgets = {} 
        self.block_configs = [
            (1, "第一區塊 : 大限課題"),
            (2, "第二區塊 : 大限財帛"),
            (3, "第三區塊 : 大限事業"),
            (4, "第四區塊 : 流年課題"),
            (5, "第五區塊 : 流年財帛"),
            (6, "第六區塊 : 流年事業"),
            (7, "第七區塊 : 客戶類型"),          # 原本在最後，移至此
            (8, "第八區塊 : 流月命/遷 運勢"),    # 原本是7
            (9, "第九區塊 : 流日命/遷 運勢")     # 原本是8
        ]

        for b_id, title in self.block_configs:
            lf = tk.LabelFrame(self.scrollable_frame, text=title, font=("微軟正黑體", 11, "bold"), fg="#003366", bg="#f0f0f0")
            lf.pack(fill=tk.X, expand=True, padx=5, pady=5)
            # 流日運勢(9)內容可能較多，給高一點
            h = 10 if b_id == 9 else 7
            txt = scrolledtext.ScrolledText(lf, height=h, font=("微軟正黑體", 10))
            txt.pack(fill=tk.BOTH, expand=True)
            self.setup_tags(txt)
            self.result_widgets[b_id] = txt

        self.root.bind_all("<MouseWheel>", self._on_mousewheel)

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")

    def setup_tags(self, text_widget):
        text_widget.tag_config("lu", foreground="#27ae60", font=("微軟正黑體", 10, "bold")) 
        text_widget.tag_config("quan", foreground="#9b59b6", font=("微軟正黑體", 10, "bold")) 
        text_widget.tag_config("ke", foreground="#2980b9", font=("微軟正黑體", 10, "bold")) 
        text_widget.tag_config("ji", foreground="#c0392b", font=("微軟正黑體", 10, "bold")) 
        text_widget.tag_config("bold_text", font=("微軟正黑體", 10, "bold")) 
        text_widget.tag_config("star_label", foreground="#555555", font=("微軟正黑體", 10, "bold"))
        # 增加流日運勢的好壞標籤
        text_widget.tag_config("luck_good", foreground="#d35400", font=("微軟正黑體", 10, "bold")) # 運勢 好
        text_widget.tag_config("luck_bad", foreground="#7f8c8d", font=("微軟正黑體", 10, "bold"))  # 運勢 差/平

    # === 判斷是否為標頭行 ===
    def is_header_line(self, line):
        keywords = ["目前年紀", "大限區間", "目前流年", "流年干", "地支干"]
        return any(k in line for k in keywords)

    # === 判斷該行觸發哪個區塊 (Trigger) ===
    def get_block_trigger(self, line):
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

    def run_conversion(self):
        # 清空
        for b_id in self.result_widgets:
            self.result_widgets[b_id].delete("1.0", tk.END)

        raw_data = self.input_text.get("1.0", tk.END).strip()
        if not raw_data: return

        lines = raw_data.split('\n')
        
        # 擴充 Buffer，這裡的 Key 1~9 對應上面 result_widgets 的 ID
        # 注意：Block 7 (客戶類型) 是程式產生的，所以 parser 只要負責 1-6, 8, 9
        buffers = {i: [] for i in range(1, 10)}
        pending_headers = [] 
        
        current_block = 1  
        current_mode = None 
        
        # 摘要資料
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
            
            # 1. 處理分隔線 (Reset & Mapping)
            # 在這裡我們把輸入資料的 "流月" 對應到 Block 8，"流日" 對應到 Block 9
            if line_stripped.startswith("===="):
                pending_headers = [] 
                if "大限" in line_stripped:
                    current_block = 1
                    current_mode = None
                elif "流年" in line_stripped:
                    current_block = 4
                    current_mode = None
                elif "流月" in line_stripped: 
                    current_block = 8 # 流月 改去 Block 8
                    current_mode = None
                elif "流日" in line_stripped: 
                    current_block = 9 # 流日 改去 Block 9
                    current_mode = None
                continue 

            # 2. 標頭緩衝 (僅針對 1~6 區塊的宮位資訊標頭)
            # Block 7 是摘要，8, 9 是運勢，不需要此邏輯
            if current_block <= 6 and self.is_header_line(line_stripped):
                pending_headers.append(line_stripped)
                continue

            # 3. 判斷 Trigger (僅針對 1~6 區塊)
            new_block = self.get_block_trigger(line_stripped)
            
            # 只有當我們還在 1~6 區塊範圍內，才允許被關鍵字觸發跳轉
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
            
            # 標題替換 (只對 1~6 有效)
            for key, val in title_map.items():
                if display_line.startswith(key):
                    display_line = display_line.replace(key, val, 1)
                    break
                elif display_line.startswith("化" + key):
                    display_line = display_line.replace(key, val, 1)
                    break

            # 宮位轉換 (僅在 wealth/career 模式下執行)
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

            # === 摘要資料擷取 (用於 Block 7) ===
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

            # === 存入緩衝區 (1~6, 8, 9) ===
            # Block 7 是摘要，所以我們只要確保不是要顯示在 Block 7 的東西跑進 1~6 即可
            is_friend_stars = check_text.startswith("大友星系") or check_text.startswith("流友星系")

            # 存入邏輯：
            # 1~6: 正常存入 (過濾掉友星系，因為要放在 Summary)
            # 8, 9: 流月流日，直接存入
            if current_block in [8, 9]:
                buffers[current_block].append(display_line)
            elif not is_friend_stars:
                # 若 current_block 意外跑到 7，強制歸為 1 (防呆)
                target = current_block if current_block != 7 else 1
                buffers[target].append(display_line)

        # === 輸出結果 ===
        # 1. 輸出 Block 1~6
        for b_id in range(1, 7):
            lines_in_block = buffers[b_id]
            txt_widget = self.result_widgets[b_id]
            for l in lines_in_block:
                txt_widget.insert(tk.END, l + "\n")
            self.highlight_keywords(txt_widget)

        # 2. 輸出 Block 7 (客戶類型摘要)
        txt_summary = self.result_widgets[7]
        txt_summary.insert(tk.END, "===客戶類型===\n")
        summary_lines = [
            summary_data["d_wealth_stars"],
            summary_data["d_wealth_lu"],
            summary_data["d_career_stars"],
            summary_data["d_career_lu"],
            summary_data["d_friend"],
            "", 
            summary_data["a_wealth_stars"],
            summary_data["a_wealth_lu"],
            summary_data["a_career_stars"],
            summary_data["a_career_lu"],
            summary_data["a_friend"]
        ]
        for line in summary_lines:
            if line == "":
                txt_summary.insert(tk.END, "\n")
            elif line:
                txt_summary.insert(tk.END, line + "\n")
        self.highlight_keywords(txt_summary)

        # 3. 輸出 Block 8, 9 (流月, 流日)
        for b_id in [8, 9]:
            lines_in_block = buffers[b_id]
            txt_widget = self.result_widgets[b_id]
            for l in lines_in_block:
                txt_widget.insert(tk.END, l + "\n")
            self.highlight_keywords(txt_widget)

    def highlight_keywords(self, text_widget):
        # 原有四化
        keywords = [("祿", "lu"), ("權", "quan"), ("科", "ke"), ("忌", "ji")]
        for key, tag in keywords:
            start_idx = "1.0"
            while True:
                pos = text_widget.search(key, start_idx, stopindex=tk.END)
                if not pos: break
                end_pos = f"{pos}+1c"
                text_widget.tag_add(tag, pos, end_pos)
                start_idx = end_pos

        # 星系與標頭
        line_count = int(text_widget.index('end-1c').split('.')[0])
        for i in range(1, line_count + 1):
            line_text = text_widget.get(f"{i}.0", f"{i}.end")
            if "星系 :" in line_text:
                split_idx = line_text.find(":")
                if split_idx != -1:
                    text_widget.tag_add("star_label", f"{i}.0", f"{i}.{split_idx+1}")
            if line_text.strip().startswith("化"):
                text_widget.tag_add("bold_text", f"{i}.0", f"{i}.end")
            
            # 流日運勢標記
            if "運勢 好" in line_text:
                start = line_text.find("運勢 好")
                if start != -1:
                    text_widget.tag_add("luck_good", f"{i}.{start}", f"{i}.{start+4}")
            if "運勢 差" in line_text:
                start = line_text.find("運勢 差")
                if start != -1:
                    text_widget.tag_add("luck_bad", f"{i}.{start}", f"{i}.{start+4}")

if __name__ == "__main__":
    root = tk.Tk()
    app = ZiweiApp(root)
    root.mainloop()