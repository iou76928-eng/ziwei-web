# -*- coding: utf-8 -*-
import re
import io
import copy
import contextlib
from datetime import datetime, timedelta
from flask import Flask, request, render_template_string

# ======================= 全域設定 =======================
DEBUG = False          # 預設關閉除錯
CYEAR = None           # ← 統一年份來源（由 run_chart_from_text 設定）

# ===== 白名單（原版保留） =====
MAIN_STARS = ["紫微","天府","天相","天梁","武曲","七殺","破軍","廉貞","天機","太陽","太陰","巨門","天同","貪狼"]
AUX_STARS  = ["文曲","文昌","左輔","右弼","天魁","天鉞"]
MINI_STARS = ["火星","鈴星","祿存","擎羊","陀螺","地劫","地空"]  # 會把「陀羅」正規為「陀螺」

ALIASES = {"陀羅": "陀螺"}  # 同義正規

PALACE_ABBR = {
    "命宮":"命","兄弟宮":"兄","夫妻宮":"夫","子女宮":"子","財帛宮":"財","疾厄宮":"疾",
    "遷移宮":"遷","交友宮":"僕","事業宮":"官","田宅宮":"田","福德宮":"福","父母宮":"父",
}

# ===== 生年四化對照（原版保留） =====
YEAR_HUA = {
    "甲": {"祿":"廉貞","權":"破軍","科":"武曲","忌":"太陽"},
    "乙": {"祿":"天機","權":"天梁","科":"紫微","忌":"太陰"},
    "丙": {"祿":"天同","權":"天機","科":"文昌","忌":"廉貞"},
    "丁": {"祿":"太陰","權":"天同","科":"天機","忌":"巨門"},
    "戊": {"祿":"貪狼","權":"太陰","科":"右弼","忌":"天機"},
    "己": {"祿":"武曲","權":"貪狼","科":"天梁","忌":"文曲"},
    "庚": {"祿":"太陽","權":"武曲","科":"太陰","忌":"天同"},
    "辛": {"祿":"巨門","權":"太陽","科":"文曲","忌":"文昌"},
    "壬": {"祿":"天梁","權":"紫微","科":"左輔","忌":"武曲"},
    "癸": {"祿":"破軍","權":"巨門","科":"太陰","忌":"貪狼"},
}

# ===== 化忌化解對應表 =====
HUA_JI_RESOLVE = {
    "甲": ("子", "紫微科"),
    "乙": ("丙", "文昌科"),
    "丙": ("丁", "天機科"),
    "丁": ("戊", "右弼科"),
    "戊": ("己", "天梁科"),
    "己": ("庚", "太陰科"),
    "庚": ("辛", "文曲科"),
    "辛": ("壬", "左輔科"),
    "壬": (("庚", "癸"), "太陰科"),  # 特例：兩宮
    "癸": ("甲", "武曲科"),
}

# ==================== 基本工具 ====================

def normalize_token(t: str) -> str:
    """同義正規 + 去掉尾綴（旺/陷/廟/地/平/祿/權/科/忌/利）"""
    t = ALIASES.get(t.strip(), t.strip())
    return re.sub(r"(旺|陷|廟|地|平|權|科|祿|忌|利)+$", "", t)

def pick_whitelist(star_line: str):
    """只抽取白名單主/輔/小星，去重保序。"""
    raw = [x for x in re.split(r"[,\，\s、]+", star_line.strip()) if x]
    found_main, found_aux, found_mini = [], [], []
    for tok in raw:
        norm = normalize_token(tok)
        if norm in MAIN_STARS and norm not in found_main:
            found_main.append(norm)
        elif norm in AUX_STARS and norm not in found_aux:
            found_aux.append(norm)
        elif norm in MINI_STARS and norm not in found_mini:
            found_mini.append(norm)
    return found_main, found_aux, found_mini

def palace_to_abbr(palace_name: str) -> str:
    """宮名→縮寫；含『命宮-身宮』一律視為命。"""
    if "命宮" in palace_name:
        return "命"
    for full, ab in PALACE_ABBR.items():
        if full in palace_name:
            return ab
    return ""

def parse_year_stem(raw_text: str) -> str:
    """從『干支』行擷取生年天干。"""
    m = re.search(r"干支[:：︰]\s*([甲乙丙丁戊己庚辛壬癸])[子丑寅卯辰巳午未申酉戌亥]年", raw_text)
    return m.group(1) if m else ""

# ==================== 解析命盤 ====================

def parse_chart(raw_text: str):
    """
    回傳 data, col_order, year_stem
    data = { col: {'palace','main','aux','mini','daxian','abbr'} }
    """
    block_pat = re.compile(
        r"([甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥])【([^】]+)】\s*"
        r"大限:([0-9]+)-([0-9]+)\s*"
        r"小限:[^\n]*\n"
        r"([^\n]+)"
    )
    data, col_order = {}, []
    for m in re.finditer(block_pat, raw_text):
        col, palace = m.group(1), m.group(2)
        dx_a, dx_b = m.group(3), m.group(4)
        star_line = m.group(5)
        main, aux, mini = pick_whitelist(star_line)
        abbr = palace_to_abbr(palace)
        data[col] = {
            "palace": palace,
            "main": main,
            "aux": aux,
            "mini": [ALIASES.get(x, x) for x in mini],
            "daxian": f"{dx_a}~{dx_b}",
            "abbr": abbr,
        }
        if col not in col_order:
            col_order.append(col)

    year_stem = parse_year_stem(raw_text)
    return data, col_order, year_stem

# ==================== 舊版簡單表格（保留） ====================

def render_markdown_table(data: dict, col_order: list, year_stem: str = "") -> str:
    header = ["原始資料", "宮干支"] + col_order
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(["----","---"] + ["----"]*len(col_order)) + " |",
    ]

    def add_row(label, key):
        row = ["", label]
        for c in col_order:
            val = data[c][key]
            row.append("/".join(val) if isinstance(val, list) else val)
        lines.append("| " + " | ".join(row) + " |")

    # 主/輔/小/大限/本命
    add_row("主星", "main")
    add_row("輔星", "aux")
    add_row("小星", "mini")
    add_row("大限", "daxian")
    row = ["本命","宮位"] + [data[c]["abbr"] for c in col_order]
    lines.append("| " + " | ".join(row) + " |")

    # 生年四化
    if year_stem and year_stem in YEAR_HUA:
        hua_map = YEAR_HUA[year_stem]
        cell = {col: [] for col in col_order}
        for typ in ["祿","權","科","忌"]:
            star = hua_map.get(typ, "")
            if not star:
                continue
            for c in col_order:
                bucket = data.get(c, {})
                if (star in bucket.get("main", [])) or (star in bucket.get("aux", [])) or (star in bucket.get("mini", [])):
                    cell[c].append(f"{star}{typ}")
        row = ["", f"生年四化（{year_stem}）"] + ["/".join(cell[c]) if cell[c] else "" for c in col_order]
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)

# ==================== 舊版檢核（保留） ====================

def quick_validate(data: dict, col_order: list, year_stem: str = ""):
    # 主星出現計數
    count = {s: 0 for s in MAIN_STARS}
    for col in col_order:
        for s in data[col]["main"]:
            count[s] += 1
    missing = [s for s,c in count.items() if c == 0]
    if missing:
        print("⚠️ 以下主星未在輸入文本中出現：", "、".join(missing))

    dx_missing = [col for col in col_order if not data[col]["daxian"]]
    if dx_missing:
        print("⚠️ 以下欄位缺大限：", "、".join(dx_missing))

    abbr_missing = [col for col in col_order if not data[col]["abbr"]]
    if abbr_missing:
        print("⚠️ 以下欄位無法辨識本命宮位縮寫：", "、".join(abbr_missing))

    # 生年四化存在但星未定位
    if year_stem and year_stem in YEAR_HUA:
        hua_map, not_found = YEAR_HUA[year_stem], []
        for typ, star in hua_map.items():
            found = any(
                (star in data[c]["main"]) or
                (star in data[c]["aux"])  or
                (star in data[c]["mini"])
                for c in col_order
            )
            if not found:
                not_found.append(f"{star}{typ}")
        if not_found:
            print("⚠️ 生年四化中以下星未定位到（含主/輔/小）：", "、".join(not_found))

# ----------------------------------------------------------------------
# ============================ 新功能共用 ===============================
# ----------------------------------------------------------------------

PALACE_ORDER_CANONICAL = ["命","兄","夫","子","財","疾","遷","僕","官","田","福","父"]

# 新增：對宮對照表（本命 12 宮）
OPPOSITE_PALACE = {
    "命": "遷", "遷": "命",
    "兄": "僕", "僕": "兄",
    "夫": "官", "官": "夫",
    "子": "福", "福": "子",
    "財": "田", "田": "財",
    "疾": "父", "父": "疾",
}

# 大限／流年用的宮位名稱（只是輸出文字）
DA_PALACE_NAME = {
    "命": "大命", "兄": "大兄", "夫": "大夫", "子": "大子",
    "財": "大財", "疾": "大疾", "遷": "大遷", "僕": "大友",
    "官": "大官", "田": "大田", "福": "大福", "父": "大父",
}

LIU_PALACE_NAME = {
    "命": "流命", "兄": "流兄", "夫": "流夫", "子": "流子",
    "財": "流財", "疾": "流疾", "遷": "流遷", "僕": "流友",
    "官": "流官", "田": "流田", "福": "流福", "父": "流父",
}

def has_main_star(stars_str: str) -> bool:
    """判斷這個星系字串裡，有沒有主星（MAIN_STARS）"""
    if not stars_str:
        return False
    tokens = [t for t in re.split(r"[、，,\s/]+", stars_str) if t]
    return any(t in MAIN_STARS for t in tokens)

def format_da_star_line(label: str, palace_star: dict) -> str:
    """
    大限星系輸出：
      若該宮沒有主星 → 追加『(空宮，抓對宮主星) 大XX星系 : 星曜』
      只會在你呼叫的宮位上生效（例如：財、官）
    """
    base_name = DA_PALACE_NAME.get(label, f"大{label}")
    base_stars = palace_star.get(label, "")
    line = f"{base_name}星系 : {base_stars}"

    # 沒有主星才啟動「對宮補星」邏輯
    if not has_main_star(base_stars):
        opp = OPPOSITE_PALACE.get(label)
        if opp:
            opp_name = DA_PALACE_NAME.get(opp, f"大{opp}")
            opp_stars = palace_star.get(opp, "")
            if opp_stars:
                line += f" ｜(空宮，抓對宮主星) {opp_name}星系 : {opp_stars}"
    return line

def format_liu_star_line(label: str, palace_star: dict) -> str:
    """
    流年星系輸出版本：
      若該宮沒有主星 → 追加『(空宮，抓對宮主星) 流XX星系 : 星曜』
    """
    base_name = LIU_PALACE_NAME.get(label, f"流{label}")
    base_stars = palace_star.get(label, "")
    line = f"{base_name}星系 : {base_stars}"

    if not has_main_star(base_stars):
        opp = OPPOSITE_PALACE.get(label)
        if opp:
            opp_name = LIU_PALACE_NAME.get(opp, f"流{opp}")
            opp_stars = palace_star.get(opp, "")
            if opp_stars:
                line += f" ｜(空宮，抓對宮主星) {opp_name}星系 : {opp_stars}"
    return line

def parse_birth_year(raw_text: str) -> int:
    m = re.search(r"陽曆[:：︰]?\s*(\d{4})年", raw_text)
    return int(m.group(1)) if m else 0

def current_year() -> int:
    return datetime.now().year

def reorder_cols_by_palace(data: dict, col_order: list) -> list:
    """依『本命宮位』順序重排欄位。"""
    buckets = {abbr: None for abbr in PALACE_ORDER_CANONICAL}
    used = set()
    for col in col_order:
        abbr = (data.get(col, {}).get("abbr") or "").strip()
        if abbr in PALACE_ORDER_CANONICAL and buckets[abbr] is None:
            buckets[abbr] = col
            used.add(col)
    ordered = [buckets[a] for a in PALACE_ORDER_CANONICAL if buckets[a]]
    tail = [c for c in col_order if c not in used]
    return ordered + tail

def find_daxian_anchor_col(data: dict, cols: list, age: int) -> str:
    """找『歲數所在的大限欄位』（含頭尾）。"""
    for c in cols:
        rng = data.get(c, {}).get("daxian", "")
        m = re.match(r"^\s*(\d+)\s*~\s*(\d+)\s*$", rng)
        if not m:
            continue
        a, b = int(m.group(1)), int(m.group(2))
        if a <= age <= b:
            return c
    return ""

def safe_find_anchor_by_age(data: dict, cols: list, age: int) -> str:
    found = find_daxian_anchor_col(data, cols, age)
    if found:
        if DEBUG:
            print(f"DEBUG[DAXIAN] 歲數 {age} 命中：{found}（區間 {data[found]['daxian']}）")
        return found
    best_col, best_gap = "", 10**9
    for c in cols:
        m = re.match(r"^\s*(\d+)\s*~\s*(\d+)\s*$", data.get(c,{}).get("daxian",""))
        if not m:
            continue
        a,b = int(m.group(1)), int(m.group(2))
        gap = min(abs(age-a), abs(age-b)) if (age < a or age > b) else 0
        if gap < best_gap:
            best_gap, best_col = gap, c
    if DEBUG and best_col:
        print(f"DEBUG[DAXIAN] 歲數 {age} 未命中任何區間，改用最近：{best_col}（{data[best_col]['daxian']}，距離={best_gap}）")
    return best_col

def build_daxian_ming_row(cols: list, data: dict, anchor_col: str) -> list:
    """anchor_col 標命，右側依 PALACE_ORDER_CANONICAL 循環。"""
    if not anchor_col or anchor_col not in cols:
        return [""] * len(cols)
    labels = PALACE_ORDER_CANONICAL
    out = [""] * len(cols)
    start_idx = cols.index(anchor_col)
    for offset in range(len(cols)):
        pos = (start_idx + offset) % len(cols)
        out[pos] = labels[offset % len(labels)]
    return out

def get_stem_from_col(col: str) -> str:
    return col[0] if col and col[0] in YEAR_HUA else ""

def build_hua_cells_for_stem(stem: str, cols: list, data: dict) -> list:
    cells = {c: [] for c in cols}
    if not stem or stem not in YEAR_HUA:
        return ["" for _ in cols]
    hua_map = YEAR_HUA[stem]
    for typ in ["祿","權","科","忌"]:
        star = hua_map.get(typ, "")
        if not star:
            continue
        located = [
            c for c in cols
            if (star in data[c]["main"]) or (star in data[c]["aux"]) or (star in data[c]["mini"])
        ]
        for c in located:
            cells[c].append(f"{star}{typ}")
    return ["/".join(cells[c]) if cells[c] else "" for c in cols]

def find_col_for_label(cols: list, ming_line: list, target_label: str) -> str:
    for i, lab in enumerate(ming_line):
        if lab == target_label:
            return cols[i]
    return ""

def debug_report_order(col_order: list, cols_reordered: list, data: dict):
    if not DEBUG:
        return
    pairs  = [f"{i+1}.{c}({data.get(c,{}).get('abbr','?')})" for i,c in enumerate(col_order)]
    pairs2 = [f"{i+1}.{c}({data.get(c,{}).get('abbr','?')})" for i,c in enumerate(cols_reordered)]
    print("DEBUG[ORDER] 原始欄序：", " | ".join(pairs))
    print("DEBUG[ORDER] 重排欄序：", " | ".join(pairs2))
    tail = [c for c in cols_reordered if not data.get(c,{}).get('abbr')]
    if tail:
        print("DEBUG[ORDER] 無縮寫（置於隊尾）：", "、".join(tail))

def debug_four_hua_locate(tag: str, stem: str, cols: list, data: dict) -> dict:
    """取得某天干四化落點，同時列印 debug。"""
    cells = {c: [] for c in cols}
    if not stem or stem not in YEAR_HUA:
        if DEBUG:
            print(f"DEBUG[HUA] {tag}：無有效天干（{stem}）")
        return cells
    det = []
    for typ in ["祿","權","科","忌"]:
        star = YEAR_HUA[stem].get(typ,"")
        located = [
            c for c in cols
            if (star in data[c]["main"]) or (star in data[c]["aux"]) or (star in data[c]["mini"])
        ]
        if not located:
            det.append(f"{typ}:{star}->未定位")
        else:
            det.append(f"{typ}:{star}->" + ",".join(located))
            for c in located:
                cells[c].append(f"{star}{typ}")
    if DEBUG:
        print(f"DEBUG[HUA] {tag}（{stem}）｜" + "； ".join(det))
    return cells

# === 四化 token 工具 ===

def extract_hua_type(token: str) -> str:
    m = re.search(r"(祿|權|科|忌)", token)
    return m.group(1) if m else ""

def extract_star_name(token: str) -> str:
    return re.sub(r"(祿|權|科|忌)", "", token)

# ---------------- 流年／流月 工具 ----------------

ZODIAC = ["子","丑","寅","卯","辰","巳","午","未","申","酉","戌","亥"]
STEMS  = ["甲","乙","丙","丁","戊","己","庚","辛","壬","癸"]

HOUR_RANGE_TEXT = {
    "子": "23:00~01:00","丑": "01:00~03:00","寅": "03:00~05:00","卯": "05:00~07:00",
    "辰": "07:00~09:00","巳": "09:00~11:00","午": "11:00~13:00","未": "13:00~15:00",
    "申": "15:00~17:00","酉": "17:00~19:00","戌": "19:00~21:00","亥": "21:00~23:00",
}

def zodiac_of_year(year: int) -> str:
    base = 1984  # 甲子年
    return ZODIAC[(year - base) % 12]

def year_stem_of_year(year: int) -> str:
    base = 1984  # 甲子年
    return STEMS[(year - base) % 10]

def get_col_with_branch(cols: list, branch: str) -> str:
    for c in cols:
        if branch in c:
            return c
    return ""

def branch_of_col(col: str) -> str:
    for ch in col:
        if ch in ZODIAC:
            return ch
    return ""

def build_liunian_row(cols: list, year: int) -> list:
    """今年地支所在欄為命，右側依 PALACE_ORDER_CANONICAL。"""
    dz = zodiac_of_year(year)
    anchor_col = get_col_with_branch(cols, dz)
    if not anchor_col:
        return [""] * len(cols)
    out = [""] * len(cols)
    labels = PALACE_ORDER_CANONICAL[:]
    start_idx = cols.index(anchor_col)
    for offset in range(len(cols)):
        pos = (start_idx + offset) % len(cols)
        out[pos] = labels[offset % len(labels)]
    return out

# 指定年份每月天干
LIUYUE_MONTH_STEMS = {
    2025: ["戊","己","庚","辛","壬","癸","甲","乙","丙","丁","戊","己"],
    2026: ["庚","辛","壬","癸","甲","乙","丙","丁","戊","己","庚","辛"],
    2027: ["壬","癸","甲","乙","丙","丁","戊","己","庚","辛","庚","辛"],
}

def liuyue_base_index(cols: list, data: dict, liunian_row: list) -> int:
    """找出流月 1 月命 的基準位置。"""
    col_yin = get_col_with_branch(cols, "寅")
    base_pal = data.get(col_yin, {}).get("abbr", "")
    if DEBUG:
        print(f"DEBUG[LIUYUE] 本命『寅』在欄 {col_yin}，本命宮位＝{base_pal}")
    try:
        idx = liunian_row.index(base_pal)
        if DEBUG:
            print(f"DEBUG[LIUYUE] 流年行中對應宮位索引 = {idx}")
        return idx
    except ValueError:
        if DEBUG:
            print("DEBUG[LIUYUE] 在流年行找不到對應宮位，流月將輸出空白。")
        return -1

def build_liuyue_row_by_month(cols: list, base_idx: int, month_no: int) -> list:
    """以 base_idx 為 1 月命，向右遞增。"""
    if base_idx < 0:
        return [""] * len(cols)
    labels = PALACE_ORDER_CANONICAL[:]
    out = [""] * len(cols)
    start_idx = (base_idx - (month_no - 1)) % len(cols)
    for offset in range(len(cols)):
        pos = (start_idx + offset) % len(cols)
        out[pos] = labels[offset % len(labels)]
    return out

# ---------------- 流日設定 ＆ 工具 ----------------

LIURI_CONFIG = {
    2025: {m: {"days": 0, "first_day_stem": ""} for m in range(1,13)},
    2026: {
        1: {"days": 30, "first_day_stem": "壬"},
        2: {"days": 29, "first_day_stem": "壬"},
        3: {"days": 30, "first_day_stem": "辛"},
        4: {"days": 29, "first_day_stem": "辛"},
        5: {"days": 29, "first_day_stem": "庚"},
        6: {"days": 30, "first_day_stem": "己"},
        7: {"days": 29, "first_day_stem": "己"},
        8: {"days": 29, "first_day_stem": "戊"},
        9: {"days": 30, "first_day_stem": "丁"},
        10: {"days": 30, "first_day_stem": "丁"},
        11: {"days": 30, "first_day_stem": "丁"},
        12: {"days": 29, "first_day_stem": "丁"},
    },
}

# 農曆 1 月 1 日 對應國曆日期
LIURI_LUNAR_YEAR_START_SOLAR = {
    2026: datetime(2026, 2, 17),
}

def day_stem_for(year: int, month_no: int, day_no: int) -> str:
    """給定農曆年月日，回傳該日天干。"""
    year_cfg = LIURI_CONFIG.get(year, {})
    cfg = year_cfg.get(month_no)
    if not cfg:
        return ""
    first = cfg.get("first_day_stem", "")
    if first not in STEMS:
        return ""
    idx0 = STEMS.index(first)
    return STEMS[(idx0 + (day_no - 1)) % 10]

def build_liuri_palace_row_for_day(cols: list, liuyue_palace_row: list, day_no: int) -> list:
    """
    流日宮位：
      1. 找此月「流月命」所在欄位
      2. 以該欄位地支為 1 號，依子丑寅卯...排
      3. 第 day_no 天找到地支 → 標為命，右側依 PALACE_ORDER_CANONICAL 排滿
    """
    if not liuyue_palace_row or len(liuyue_palace_row) != len(cols):
        return [""] * len(cols)

    target_col = ""
    for i, lab in enumerate(liuyue_palace_row):
        if lab == "命":
            target_col = cols[i]
            break
    if not target_col:
        return [""] * len(cols)

    start_branch = branch_of_col(target_col)
    if start_branch not in ZODIAC:
        return [""] * len(cols)

    base_idx = ZODIAC.index(start_branch)
    day_branch = ZODIAC[(base_idx + (day_no - 1)) % 12]
    anchor_col = get_col_with_branch(cols, day_branch)
    if not anchor_col:
        return [""] * len(cols)

    labels = PALACE_ORDER_CANONICAL[:]
    out = [""] * len(cols)
    start_idx = cols.index(anchor_col)
    for offset in range(len(cols)):
        pos = (start_idx + offset) % len(cols)
        out[pos] = labels[offset % len(labels)]
    return out

# ==================== 流日命/遷 運勢（舊版函式，供摘要用） ====================

def find_day_ji_branch(day_stem: str, cols: list, data: dict) -> str:
    """找當日化忌落在哪一支。"""
    if not day_stem or day_stem not in YEAR_HUA:
        return ""
    ji_star = YEAR_HUA[day_stem].get("忌")
    if not ji_star:
        return ""
    for c in cols:
        bucket = data.get(c, {})
        if (ji_star in bucket.get("main", [])) or \
           (ji_star in bucket.get("aux", []))  or \
           (ji_star in bucket.get("mini", [])):
            return branch_of_col(c)
    return ""

def compute_ri_fortune_for_day(
    year: int, month_no: int, day_no: int,
    cols: list, liuri_row: list,
    day_stem: str, day_cells_map: dict,
    data: dict
) -> str:
    """
    只看「日命／日遷」：
      - 有忌 → 差（整日不適合決策）
      - 無忌但有祿/權/科 → 好
      - 其餘 → 平
      - 若非差，再算忌時（以化忌落點 + 日命地支推算）
    """
    col_ming = col_qian = None
    for idx, lab in enumerate(liuri_row):
        if lab == "命":
            col_ming = cols[idx]
        elif lab == "遷":
            col_qian = cols[idx]

    tokens_ming = day_cells_map.get(col_ming, []) if col_ming else []
    tokens_qian = day_cells_map.get(col_qian, []) if col_qian else []

    def types_of(tokens):
        return [extract_hua_type(t) for t in tokens if extract_hua_type(t)]

    types_ming = types_of(tokens_ming)
    types_qian = types_of(tokens_qian)

    # 有忌 → 差
    if "忌" in types_ming or "忌" in types_qian:
        return f"{year}年{month_no}月{day_no}日 : 運勢 差，整日不適合決策"

    POS_TYPES = {"祿","權","科"}
    all_pos = POS_TYPES.intersection(set(types_ming + types_qian))
    fortune = "好" if all_pos else "平"

    # 算忌時
    if not col_ming:
        return f"{year}年{month_no}月{day_no}日 : 運勢 {fortune}"

    ming_branch = branch_of_col(col_ming)
    if ming_branch not in ZODIAC:
        return f"{year}年{month_no}月{day_no}日 : 運勢 {fortune}"

    ji_branch = find_day_ji_branch(day_stem, cols, data)
    if ji_branch not in ZODIAC:
        return f"{year}年{month_no}月{day_no}日 : 運勢 {fortune}"

    start_idx = ZODIAC.index(ming_branch)
    ji_idx = ZODIAC.index(ji_branch)
    pos = (ji_idx - start_idx) % 12 + 1
    hour_branch = ZODIAC[pos - 1]
    hour_range = HOUR_RANGE_TEXT.get(hour_branch, "")

    if hour_range:
        return f"{year}年{month_no}月{day_no}日 : 運勢 {fortune}，忌時 : {hour_branch}時({hour_range})"
    return f"{year}年{month_no}月{day_no}日 : 運勢 {fortune}"

# ====================== 流月命／流月遷 運勢計算 ======================

def detect_month_hua_ji_hit(m_stem: str, cols: list, liuyue_row: list):
    """
    保留備用：檢查 HUA_JI_RESOLVE 是否命中月命/月遷。
    回傳 (hit: bool, 描述字串)
    """
    if not m_stem or m_stem not in HUA_JI_RESOLVE:
        return False, ""

    mapping = HUA_JI_RESOLVE[m_stem]
    targets = []
    if m_stem == "壬":
        pals, star_k = mapping
        for p in pals:
            targets.append((p, star_k))
    else:
        p, star_k = mapping
        targets.append((p, star_k))

    hit, labels = False, []
    for symbol, star_k in targets:
        target_col = ""
        for c in cols:
            if symbol in c:
                target_col = c
                break
        if not target_col:
            continue
        idx = cols.index(target_col)
        pal_label = liuyue_row[idx] if idx < len(liuyue_row) else ""
        if not pal_label:
            continue
        labels.append(f"月{pal_label}宮/{star_k}")
        if pal_label in ("命", "遷"):
            hit = True

    return hit, "；".join(labels)

def format_yue_palace_tokens(tokens: list, palace_label: str) -> str:
    """將某一宮的四化列表格式化成『星星祿、星星忌/月命』形式。"""
    if not tokens:
        return ""
    filtered = [t for t in tokens if extract_hua_type(t) in ("祿","權","科","忌")]
    if not filtered:
        return ""
    txt = "、".join(filtered)
    return f"{txt}/月{palace_label}"

def compute_yue_fortune_for_month(
    year: int, month_no: int,
    cols: list, liuyue_row: list,
    m_stem: str, month_cells_map: dict
) -> str:
    """只看月命／月遷，依你定義的分數規則輸出一句話月運勢。"""
    col_ming = col_qian = None
    for idx, lab in enumerate(liuyue_row):
        if lab == "命":
            col_ming = cols[idx]
        elif lab == "遷":
            col_qian = cols[idx]

    tokens_ming = month_cells_map.get(col_ming, []) if col_ming else []
    tokens_qian = month_cells_map.get(col_qian, []) if col_qian else []

    def types_of(tokens):
        return [extract_hua_type(t) for t in tokens if extract_hua_type(t)]

    types_ming = types_of(tokens_ming)
    types_qian = types_of(tokens_qian)

    # A. 同宮含忌的分類
    def classify_with_ji(types):
        s = set(types)
        if "忌" not in s:
            return None
        if "祿" in s:
            return ("祿+忌", -50, "波動起伏，穩扎穩打", "combo")
        if "權" in s:
            return ("權+忌", -40, "謹防突變，放慢節奏", "combo")
        if "科" in s:
            return ("科+忌", -30, "好事多磨，糾纏不斷", "combo")
        return ("忌", -20, "重新檢視，冷靜思考", "pure")

    ji_ming = classify_with_ji(types_ming)
    ji_qian = classify_with_ji(types_qian)

    # 有忌 → 忌主導
    if ji_ming or ji_qian:
        if ji_ming and ji_qian:
            pattern_m, score_m, msg_m, _ = ji_ming
            pattern_q, score_q, msg_q, _ = ji_qian
            if score_m <= score_q:
                chosen = ("命", tokens_ming, pattern_m, score_m, msg_m)
            else:
                chosen = ("遷", tokens_qian, pattern_q, score_q, msg_q)
        elif ji_ming:
            pattern, score, msg, _ = ji_ming
            chosen = ("命", tokens_ming, pattern, score, msg)
        else:
            pattern, score, msg, _ = ji_qian
            chosen = ("遷", tokens_qian, pattern, score, msg)

        palace_label, palace_tokens, pattern, score, msg = chosen
        token_desc = format_yue_palace_tokens(palace_tokens, palace_label)
        return f"{year}年{month_no}月 : {token_desc}｜{msg}，好運指數{score}分"

    # B. 沒有忌 → 看祿/權/科
    POS_SCORE = {"祿": 80, "權": 100, "科": 60}
    POS_MSG = {
        "祿": "把握機會，順勢而為",
        "權": "主動出擊，努力可得",
        "科": "認知清晰，認真學習",
    }

    all_types = [t for t in (types_ming + types_qian) if t in POS_SCORE]
    if not all_types:
        return f"{year}年{month_no}月 : 本月運勢平穩"

    best_type = max(set(all_types), key=lambda t: POS_SCORE[t])
    score, msg = POS_SCORE[best_type], POS_MSG[best_type]

    parts = []
    if tokens_ming:
        parts.append(format_yue_palace_tokens(tokens_ming, "命"))
    if tokens_qian:
        parts.append(format_yue_palace_tokens(tokens_qian, "遷"))
    token_desc = "，".join(parts) if parts else "本月有好星啟動"

    return f"{year}年{month_no}月 : {token_desc}｜{msg}，好運指數{score}分"

# ======================== 流日運勢（新版：好／平／差 + 忌時） ========================

def calc_ji_time(cols:list, liuri_row:list, day_cells_map:dict, day_stem:str):
    """找化忌落點 → 從日命算距離 → 對應時辰。"""
    target_col = None
    for c in cols:
        for t in day_cells_map.get(c, []):
            if extract_hua_type(t) == "忌":
                target_col = c
                break
        if target_col:
            break
    if not target_col:
        return "無"

    col_ming = None
    for idx, lab in enumerate(liuri_row):
        if lab == "命":
            col_ming = cols[idx]
            break
    if not col_ming:
        return "無"

    start_branch = branch_of_col(col_ming)
    target_branch = branch_of_col(target_col)
    if not start_branch or not target_branch:
        return "無"

    start_idx = ZODIAC.index(start_branch)
    target_idx = ZODIAC.index(target_branch)
    steps = (target_idx - start_idx + 12) % 12 + 1

    time_map = {
        1:"子時(23:00~01:00)", 2:"丑時(01:00~03:00)", 3:"寅時(03:00~05:00)",
        4:"卯時(05:00~07:00)", 5:"辰時(07:00~09:00)", 6:"巳時(09:00~11:00)",
        7:"午時(11:00~13:00)", 8:"未時(13:00~15:00)", 9:"申時(15:00~17:00)",
        10:"酉時(17:00~19:00)",11:"戌時(19:00~21:00)",12:"亥時(21:00~23:00)",
    }
    steps = ((steps - 1) % 12) + 1
    return time_map.get(steps, "無")

def compute_yue_ri_fortune(
    year:int, month_no:int, day_no:int,
    cols:list, liuri_row:list,
    day_stem:str, day_cells_map:dict
):
    """
    依規則：
      - 日命/日遷 若有忌 => 差
      - 無忌但有祿/權/科 => 好
      - 其餘 => 平
      並計算「忌時」。
    """
    col_ming = col_qian = None
    for idx, lab in enumerate(liuri_row):
        if lab == "命":
            col_ming = cols[idx]
        elif lab == "遷":
            col_qian = cols[idx]

    tokens_ming = day_cells_map.get(col_ming, []) if col_ming else []
    tokens_qian = day_cells_map.get(col_qian, []) if col_qian else []

    def types(tokens):
        return [extract_hua_type(t) for t in tokens if extract_hua_type(t)]

    types_ming = types(tokens_ming)
    types_qian = types(tokens_qian)

    if "忌" in types_ming or "忌" in types_qian:
        return f"{year}年{month_no}月{day_no}日 : 運勢 差，整日不適合決策"

    good_types = {"祿","權","科"}
    has_good = (set(types_ming) & good_types) or (set(types_qian) & good_types)
    fortune = "好" if has_good else "平"

    ji_time = calc_ji_time(cols, liuri_row, day_cells_map, day_stem)
    return f"{year}年{month_no}月{day_no}日 : 運勢 {fortune}，忌時 : {ji_time}"

# ====================== 共用：摘要計算工具 ======================

def compute_in_out_for_palace(four_map: dict, palace_star: dict, target_pal: str, label_prefix: str):
    """
    針對某宮計算：
      - 祿/權/科/忌 入：來源宮的星系 / label_prefix+宮位
      - 祿/權/科/忌 出：優先用「目的宮」星系，找不到才退回本宮星系或 token
    """
    res = {
        "祿入": [], "祿出": [],
        "權入": [], "權出": [],
        "科入": [], "科出": [],
        "忌入": [], "忌出": [],
    }

    # 該宮飛出
    info = four_map.get(target_pal)
    if info:
        by_big = info.get("by_big", {})
        stars_str_self = palace_star.get(target_pal, "")
        for dest_pal, tokens in by_big.items():
            for tok in tokens:
                hua = extract_hua_type(tok)
                if hua not in ("祿","權","科","忌"):
                    continue
                key = f"{hua}出"
                stars_dest = palace_star.get(dest_pal, "")
                star_repr = stars_dest or stars_str_self or tok
                res[key].append((star_repr, f"{label_prefix}{dest_pal}"))

    # 該宮飛入
    for src_pal, info2 in four_map.items():
        by_big2 = info2.get("by_big", {})
        tokens2 = by_big2.get(target_pal, [])
        if not tokens2:
            continue
        stars_str_src = palace_star.get(src_pal, "")
        for tok2 in tokens2:
            hua = extract_hua_type(tok2)
            if hua not in ("祿","權","科","忌"):
                continue
            key = f"{hua}入"
            star_repr = stars_str_src or tok2
            res[key].append((star_repr, f"{label_prefix}{src_pal}"))

    return res


def compute_sub_ji_for_palace(
    four_map: dict,
    palace_star: dict,
    target_pal: str,
    label_prefix: str,
):
    """
    子忌：
      1. 先找 target_pal（例如：命）的忌出，找到『第一個被飛到的宮位』 first_dest_pal
      2. 再看 first_dest_pal 本身四化裡，對其它宮的忌出
      3. 輸出時，star_repr 使用「被飛到宮位的完整星系」，而不是單一忌星 token
          → 例如：武曲，貪狼/大夫
    """
    info = four_map.get(target_pal)
    if not info:
        return []

    # 1) 找第一個忌飛到的宮位
    first_dest_pal = None
    for dest_pal, tokens in info.get("by_big", {}).items():
        for tok in tokens:
            if extract_hua_type(tok) == "忌":
                first_dest_pal = dest_pal
                break
        if first_dest_pal:
            break
    if not first_dest_pal:
        return []

    # 2) 看該宮再飛出的忌（子忌）
    info2 = four_map.get(first_dest_pal)
    if not info2:
        return []

    result = []
    for dest_pal2, tokens2 in info2.get("by_big", {}).items():
        for tok2 in tokens2:
            if extract_hua_type(tok2) == "忌":
                # ⭐ 關鍵：這裡改成使用「該宮的完整星系」
                stars_dest = palace_star.get(dest_pal2, "")
                star_repr = stars_dest or tok2
                result.append((star_repr, f"{label_prefix}{dest_pal2}"))
    return result


def format_entry_list(pairs, empty_as_wu=False) -> str:
    if not pairs:
        return "無" if empty_as_wu else ""
    return "；".join(f"{a}/{b}" for a,b in pairs)

# ---- 流年專用：加上『對應大限宮位』 ----

def build_flow_to_big_map(flow_label_by_col: dict, big_label_by_col: dict, cols: list) -> dict:
    """建立『流年宮位 → 大限宮位』對照。"""
    mapping = {}
    for c in cols:
        f = flow_label_by_col.get(c, "")
        b = big_label_by_col.get(c, "")
        if f and b and f not in mapping:
            mapping[f] = f"大{b}"
    return mapping

def format_flow_entry_list(pairs, flow_to_big: dict, empty_as_wu: bool = False) -> str:
    """
    [( '貪狼祿','流夫' ), ...] → '貪狼祿/流夫/大財； ...'
    """
    if not pairs:
        return "無" if empty_as_wu else ""
    items = []
    for star_tok, flow_label in pairs:
        m = re.match(r"^流(.+)$", flow_label)
        big = flow_to_big.get(m.group(1), "") if m else ""
        if big:
            items.append(f"{star_tok}/{flow_label}/{big}")
        else:
            items.append(f"{star_tok}/{flow_label}")
    return "；".join(items)

def enhance_ji_with_big(hua_list, flow_to_big: dict) -> list:
    """
    '流田宮/天梁科' → '流田宮/天梁科/大財'
    """
    out = []
    for s in hua_list:
        m = re.match(r"^(流(.+?)宮)/(.*)$", s)
        if not m:
            out.append(s)
            continue
        pal = m.group(2)
        big = flow_to_big.get(pal, "")
        out.append(f"{m.group(1)}/{m.group(3)}/{big}" if big else s)
    return out

# === 化忌 → 宮位/科 轉換 ===

def _palace_name_from_code(code: str, cols: list, label_by_col: dict, label_prefix: str) -> str:
    for c in cols:
        if code in c:
            pal = label_by_col.get(c, "")
            if pal:
                return f"{label_prefix}{pal}宮"
    return f"{code}宮位"

def resolve_ji_for_stem_chart(stem: str, cols: list, label_by_col: dict, label_prefix: str):
    """
    HUA_JI_RESOLVE → ['prefix命宮/紫微科', ...]
    """
    if not stem or stem not in HUA_JI_RESOLVE:
        return []
    mapping = HUA_JI_RESOLVE[stem]
    out = []
    if stem == "壬":
        pals, star_k = mapping
        for code in pals:
            pal_name = _palace_name_from_code(code, cols, label_by_col, label_prefix)
            out.append(f"{pal_name}/{star_k}")
    else:
        code, star_k = mapping
        pal_name = _palace_name_from_code(code, cols, label_by_col, label_prefix)
        out.append(f"{pal_name}/{star_k}")
    return out

# ======================= 大限命/財/官/友 共用建構 =======================

def build_da_four_hua_and_palace_stars(data: dict, col_order: list, raw_text: str):
    """
    回傳：
      da_four: {'命'~'父': {'stem':干,'by_big':{宮位:[四化]}}}
      palace_star: {'命'~'父': '主星，輔星，兇星...'}
      big_label_by_col: {col: '命'~'父'}
      cols: 重新排序後欄位
    """
    cols = reorder_cols_by_palace(data, col_order)
    byear = parse_birth_year(raw_text)
    age = (CYEAR - byear) if byear else None
    anchor_col = safe_find_anchor_by_age(data, cols, age) if age is not None else ""
    ming_line = build_daxian_ming_row(cols, data, anchor_col)

    big_label_by_col = {c: (ming_line[i] if i < len(ming_line) else "") for i,c in enumerate(cols)}
    da_four = {}

    # 每一大限宮位的大限四化
    for label in PALACE_ORDER_CANONICAL:
        target_col = find_col_for_label(cols, ming_line, label)
        if not target_col:
            continue
        stem = get_stem_from_col(target_col)
        if not stem:
            continue
        cells_map = debug_four_hua_locate(f"大{label}四化(摘要用)", stem, cols, data)
        by_big = {}
        for c in cols:
            big_pal = big_label_by_col.get(c, "")
            tokens = cells_map.get(c, [])
            if big_pal and tokens:
                by_big[big_pal] = list(tokens)
        da_four[label] = {"stem": stem, "by_big": by_big}

    # 每一大限宮位的星系
    palace_star = {}
    for label in PALACE_ORDER_CANONICAL:
        idx = next((i for i,lab in enumerate(ming_line) if lab == label), None)
        if idx is None:
            continue
        col = cols[idx]
        bucket = data.get(col, {})
        parts = bucket.get("main", []) + bucket.get("aux", []) + bucket.get("mini", [])
        palace_star[label] = "，".join(parts) if parts else ""
    return da_four, palace_star, big_label_by_col, cols

def build_liu_four_hua_and_palace_stars(data: dict, col_order: list):
    """
    流年版：
      liu_four: 類似 da_four
      palace_star: 流年星系
      flow_label_by_col: {col:'命'~'父'}
    """
    cols = reorder_cols_by_palace(data, col_order)
    liu_row = build_liunian_row(cols, CYEAR)

    flow_label_by_col = {c: (liu_row[i] if i < len(liu_row) else "") for i,c in enumerate(cols)}
    liu_four = {}

    for label in PALACE_ORDER_CANONICAL:
        target_col = find_col_for_label(cols, liu_row, label)
        if not target_col:
            continue
        stem = get_stem_from_col(target_col)
        if not stem:
            continue
        cells_map = debug_four_hua_locate(f"流{label}四化(摘要用)", stem, cols, data)
        by_flow = {}
        for c in cols:
            pal = flow_label_by_col.get(c, "")
            tokens = cells_map.get(c, [])
            if pal and tokens:
                by_flow[pal] = list(tokens)
        liu_four[label] = {"stem": stem, "by_big": by_flow}

    palace_star = {}
    for label in PALACE_ORDER_CANONICAL:
        idx = next((i for i,lab in enumerate(liu_row) if lab == label), None)
        if idx is None:
            continue
        col = cols[idx]
        bucket = data.get(col, {})
        parts = bucket.get("main", []) + bucket.get("aux", []) + bucket.get("mini", [])
        palace_star[label] = "，".join(parts) if parts else ""
    return liu_four, palace_star, flow_label_by_col, cols

# ========================== v6：主表格（保留） ==========================

def render_markdown_table_v6(data: dict, col_order: list, year_stem: str, raw_text: str) -> str:
    cols = reorder_cols_by_palace(data, col_order)
    if DEBUG:
        debug_report_order(col_order, cols, data)

    header = ["原始資料", "宮干支"] + cols
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(["----","---"] + ["----"]*len(cols)) + " |",
    ]

    row = ["", "主星"]; [row.append("/".join(data[c]["main"]) if data[c]["main"] else "") for c in cols]; lines.append("| " + " | ".join(row) + " |")
    row = ["", "輔星"]; [row.append("/".join(data[c]["aux"])  if data[c]["aux"]  else "") for c in cols]; lines.append("| " + " | ".join(row) + " |")
    row = ["", "小星"]; [row.append("/".join(data[c]["mini"]) if data[c]["mini"] else "") for c in cols]; lines.append("| " + " | ".join(row) + " |")
    row = ["", "大限"]; [row.append(data[c]["daxian"]) for c in cols]; lines.append("| " + " | ".join(row) + " |")
    row = ["本命","宮位"]; [row.append(data[c]["abbr"]) for c in cols]; lines.append("| " + " | ".join(row) + " |")

    if year_stem and year_stem in YEAR_HUA:
        cell_map = debug_four_hua_locate("生年四化", year_stem, cols, data)
        row = ["", f"生年四化（{year_stem}）"]; [row.append("/".join(cell_map[c]) if cell_map[c] else "") for c in cols]; lines.append("| " + " | ".join(row) + " |")

    byear = parse_birth_year(raw_text)
    age = (CYEAR - byear) if byear else None
    anchor_col = safe_find_anchor_by_age(data, cols, age) if age is not None else ""
    ming_line = build_daxian_ming_row(cols, data, anchor_col)
    row = ["大限命","宮位"]; [row.append(v) for v in ming_line]; lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)

# ========================== v7：主表格（完整版） ==========================

def render_markdown_table_v7(data: dict, col_order: list, year_stem: str, raw_text: str) -> str:
    cols = reorder_cols_by_palace(data, col_order)
    if DEBUG:
        debug_report_order(col_order, cols, data)

    header = ["原始資料", "宮干支"] + cols
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(["----","---"] + ["----"]*len(cols)) + " |",
    ]

    # 主/輔/小/大限
    row = ["", "主星"]; [row.append("/".join(data[c]["main"]) if data[c]["main"] else "") for c in cols]; lines.append("| " + " | ".join(row) + " |")
    row = ["", "輔星"]; [row.append("/".join(data[c]["aux"])  if data[c]["aux"]  else "") for c in cols]; lines.append("| " + " | ".join(row) + " |")
    row = ["", "小星"]; [row.append("/".join(data[c]["mini"]) if data[c]["mini"] else "") for c in cols]; lines.append("| " + " | ".join(row) + " |")
    row = ["", "大限"]; [row.append(data[c]["daxian"]) for c in cols]; lines.append("| " + " | ".join(row) + " |")

    # 本命
    row = ["本命","宮位"]; [row.append(data[c]["abbr"]) for c in cols]; lines.append("| " + " | ".join(row) + " |")

    # 生年四化
    if year_stem and year_stem in YEAR_HUA:
        cell_map = debug_four_hua_locate("生年四化", year_stem, cols, data)
        row = ["", f"生年四化（{year_stem}）"]; [row.append("/".join(cell_map[c]) if cell_map[c] else "") for c in cols]; lines.append("| " + " | ".join(row) + " |")

    # 大限命｜宮位
    byear = parse_birth_year(raw_text)
    age = (CYEAR - byear) if byear else None
    anchor_col = safe_find_anchor_by_age(data, cols, age) if age is not None else ""
    ming_line = build_daxian_ming_row(cols, data, anchor_col)
    row = ["大限命","宮位"]; [row.append(v) for v in ming_line]; lines.append("| " + " | ".join(row) + " |")

    # 大限 12 宮四化
    for label in PALACE_ORDER_CANONICAL:
        if 'OUTPUT_SWITCH' in globals() and not OUTPUT_SWITCH["DA_FOUR_HUA"].get(label, True):
            continue
        target_col = find_col_for_label(cols, ming_line, label)
        stem = get_stem_from_col(target_col)
        cells_map = debug_four_hua_locate(f"大{label}四化", stem, cols, data)
        row = ["", f"大{label}四化（{stem}）"]
        for c in cols:
            row.append("/".join(cells_map[c]) if cells_map[c] else "")
        lines.append("| " + " | ".join(row) + " |")

    # 流年命
    liu_row = build_liunian_row(cols, CYEAR)
    row = [f"流年命（{CYEAR}）","宮位"]; [row.append(v) for v in liu_row]; lines.append("| " + " | ".join(row) + " |")

    stem_year = year_stem_of_year(CYEAR)
    dz = zodiac_of_year(CYEAR)
    col_branch = get_col_with_branch(cols, dz)
    stem_branch = get_stem_from_col(col_branch)

    year_cells_map = debug_four_hua_locate("流命四化(天干)", stem_year, cols, data)
    if stem_branch and stem_branch != stem_year:
        if 'OUTPUT_SWITCH' not in globals() or OUTPUT_SWITCH["LIU_MING_FOUR_HUA"].get("YEAR_STEM_LINE", True):
            row = ["", f"流命四化（{stem_year}）"]; [row.append("/".join(year_cells_map[c]) if year_cells_map[c] else "") for c in cols]; lines.append("| " + " | ".join(row) + " |")
        br_cells_map = debug_four_hua_locate("流命四化(地支欄天干)", stem_branch, cols, data)
        if 'OUTPUT_SWITCH' not in globals() or OUTPUT_SWITCH["LIU_MING_FOUR_HUA"].get("BRANCH_STEM_LINE", True):
            row = ["", f"流命四化（{stem_branch}）"]; [row.append("/".join(br_cells_map[c]) if br_cells_map[c] else "") for c in cols]; lines.append("| " + " | ".join(row) + " |")
        if DEBUG:
            print(f"DEBUG[LIUNIAN] 兩行輸出：天干={stem_year}；地支欄天干={stem_branch}")
    else:
        if 'OUTPUT_SWITCH' not in globals() or OUTPUT_SWITCH["LIU_MING_FOUR_HUA"].get("YEAR_STEM_LINE", True):
            row = ["", f"流命四化（{stem_year}）"]; [row.append("/".join(year_cells_map[c]) if year_cells_map[c] else "") for c in cols]; lines.append("| " + " | ".join(row) + " |")
        if DEBUG:
            print(f"DEBUG[LIUNIAN] 合併輸出：天干={stem_year}")

    # 流年 12 宮四化
    for label in PALACE_ORDER_CANONICAL:
        if 'OUTPUT_SWITCH' in globals() and not OUTPUT_SWITCH["LIU_FOUR_HUA"].get(label, True):
            continue
        target_col = find_col_for_label(cols, liu_row, label)
        stem = get_stem_from_col(target_col)
        cells_map = debug_four_hua_locate(f"流{label}四化", stem, cols, data)
        row = ["", f"流{label}四化（{stem}）"]
        for c in cols:
            row.append("/".join(cells_map[c]) if cells_map[c] else "")
        lines.append("| " + " | ".join(row) + " |")

    # 流月 + 流日
    base_idx = liuyue_base_index(cols, data, liu_row)
    month_stems = LIUYUE_MONTH_STEMS.get(CYEAR)
    if not month_stems:
        ystem = year_stem_of_year(CYEAR)
        start = STEMS.index(ystem) if ystem in STEMS else 0
        month_stems = [STEMS[(start+i)%10] for i in range(12)]
        if DEBUG:
            print(f"DEBUG[LIUYUE] 未提供 {CYEAR} 月干表，改用年干推算：{month_stems}")

    for i in range(12):
        m_no = i + 1
        if 'OUTPUT_SWITCH' in globals() and m_no not in OUTPUT_SWITCH["LIU_YUE"]["MONTHS"]:
            continue

        # 流月命
        row_labels = build_liuyue_row_by_month(cols, base_idx, m_no)
        if 'OUTPUT_SWITCH' not in globals() or OUTPUT_SWITCH["LIU_YUE"].get("SHOW_PALACE_ROW", True):
            row = [f"流月命（{CYEAR}-{m_no:02d}）","宮位"]; [row.append(v) for v in row_labels]; lines.append("| " + " | ".join(row) + " |")

        # 流月四化
        if 'OUTPUT_SWITCH' not in globals() or OUTPUT_SWITCH["LIU_YUE"].get("SHOW_HUA_ROW", True):
            m_stem = month_stems[i]
            m_cells_map = debug_four_hua_locate(f"流月{m_no:02d}四化", m_stem, cols, data)
            row = ["", f"流月四化（{m_stem}）"]; [row.append("/".join(m_cells_map[c]) if m_cells_map[c] else "") for c in cols]; lines.append("| " + " | ".join(row) + " |")

        # 流日（表格模式）
        if 'OUTPUT_SWITCH' in globals() and OUTPUT_SWITCH.get("LIU_RI", {}).get("ENABLE", False):
            year_cfg = LIURI_CONFIG.get(CYEAR, {})
            ri_cfg = year_cfg.get(m_no)
            if ri_cfg:
                total_days = ri_cfg.get("days", 0) or 0
                if total_days > 0:
                    max_days = OUTPUT_SWITCH["LIU_RI"].get("MAX_DAYS", 0) or total_days
                    max_days = min(max_days, total_days)
                    for d in range(1, max_days + 1):
                        if OUTPUT_SWITCH["LIU_RI"].get("SHOW_PALACE_ROW", True):
                            day_labels = build_liuri_palace_row_for_day(cols, row_labels, d)
                            row = [f"流日命（{CYEAR}-{m_no:02d}-{d:02d}）", "宮位"]; [row.append(v) for v in day_labels]; lines.append("| " + " | ".join(row) + " |")
                        if OUTPUT_SWITCH["LIU_RI"].get("SHOW_HUA_ROW", True):
                            d_stem = day_stem_for(CYEAR, m_no, d)
                            if d_stem:
                                d_cells_map = debug_four_hua_locate(f"流日{m_no:02d}-{d:02d}四化", d_stem, cols, data)
                                row = ["", f"流日四化（{d_stem}）"]
                                for c in cols:
                                    row.append("/".join(d_cells_map[c]) if d_cells_map[c] else "")
                                lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)

# ======================= 大限命/財/官/友 摘要 =======================
# ======================= 輔助：格式化「入」的輸出 (含空宮判斷) =======================

def helper_format_in_line(
    hua_type: str,     # "祿", "權", "科", "忌"
    main_io: dict,     # 本宮的 IO 資料
    opp_io: dict,      # 對宮的 IO 資料 (若本宮非空宮則為 None)
    is_empty: bool,    # 本宮是否為空宮
    flow_to_big: dict = None # 流年用：流->大限 對照表
) -> str:
    """
    格式化四化「入」的字串。
    若 is_empty 為 True 且 opp_io 有資料，會在後方追加 ｜(空宮，抓對宮主星) ...
    """
    key = f"{hua_type}入"
    
    # 1. 本宮原本的輸出
    if flow_to_big:
        txt_main = format_flow_entry_list(main_io.get(key, []), flow_to_big, empty_as_wu=True)
    else:
        txt_main = format_entry_list(main_io.get(key, []), empty_as_wu=True)
    
    # 2. 若為空宮，追加對宮資訊
    if is_empty and opp_io:
        if flow_to_big:
            txt_opp = format_flow_entry_list(opp_io.get(key, []), flow_to_big, empty_as_wu=False)
        else:
            txt_opp = format_entry_list(opp_io.get(key, []), empty_as_wu=False)
        
        # 如果對宮也沒有四化飛入，txt_opp 可能是空字串，這裡補上"無"以求版面整齊，或視需求留空
        if not txt_opp:
            txt_opp = "無"
            
        return f"{txt_main}｜(空宮，抓對宮主星) {txt_opp}"
    
    return txt_main

# ======================= 大限命/財/官/友 摘要 =======================

def render_da_summary(data: dict, col_order: list, year_stem: str, raw_text: str) -> str:
    da_four, palace_star, big_label_by_col, cols = build_da_four_hua_and_palace_stars(data, col_order, raw_text)

    # === 計算目前所在大限區間與年紀 ===
    byear = parse_birth_year(raw_text)
    age = (CYEAR - byear) if byear else "未知"
    
    daxian_range = ""
    if isinstance(age, int):
        # 利用前面已經重排過的 cols，找出 age 所在的大限欄位
        anchor_col = safe_find_anchor_by_age(data, cols, age)
        if anchor_col:
            daxian_range = data.get(anchor_col, {}).get("daxian", "")  # 例如 "0~9"

    lines = []

    # 定義通用的標頭字串 (方便重複使用)
    header_age = f"目前年紀 : {age}"
    header_range = f"大限區間 : {daxian_range}"

    # ================= 大命 =================
    lines.append(header_age)
    lines.append(header_range)
    
    res_ming = compute_in_out_for_palace(da_four, palace_star, "命", label_prefix="大")
    sub_ji_ming = compute_sub_ji_for_palace(da_four, palace_star, "命", label_prefix="大")
    stem_ming = da_four.get("命", {}).get("stem", "")

    lines.append(f"大命星系 : {palace_star.get('命', '')}")
    lines.append(f"大命忌出 : {format_entry_list(res_ming.get('忌出', []))}")
    lines.append(f"該宮忌出 : {format_entry_list(sub_ji_ming)}")
    if stem_ming:
        hua_ming_parts = resolve_ji_for_stem_chart(stem_ming, cols, big_label_by_col, label_prefix="大")
        lines.append("化大命忌 : " + "；".join(hua_ming_parts))
    else:
        lines.append("化大命忌 : ")
    lines.append("")

    # ================= 大財 =================
    lines.append(header_age)
    lines.append(f'"{header_range}"')
    
    # 準備資料
    da_cai_stars = palace_star.get("財", "")
    is_cai_empty = not has_main_star(da_cai_stars)
    
    cai_io = compute_in_out_for_palace(da_four, palace_star, "財", label_prefix="大")
    
    # 若為空宮，預先計算對宮(福德)的 IO
    cai_opp_io = None
    if is_cai_empty:
        opp_pal = OPPOSITE_PALACE.get("財") # 福
        if opp_pal:
            cai_opp_io = compute_in_out_for_palace(da_four, palace_star, opp_pal, label_prefix="大")

    cai_info = da_four.get("財")
    cai_stem = cai_info["stem"] if cai_info else ""

    lines.append(format_da_star_line("財", palace_star))
    lines.append(f"大財祿入 : {helper_format_in_line('祿', cai_io, cai_opp_io, is_cai_empty)}")
    lines.append(f"大財祿出 : {format_entry_list(cai_io['祿出'])}")
    lines.append(f"大財權入 : {helper_format_in_line('權', cai_io, cai_opp_io, is_cai_empty)}")
    lines.append(f"大財權出 : {format_entry_list(cai_io['權出'])}")
    lines.append(f"大財科入 : {helper_format_in_line('科', cai_io, cai_opp_io, is_cai_empty)}")
    lines.append(f"大財科出 : {format_entry_list(cai_io['科出'])}")
    lines.append(f"大財忌入 : {helper_format_in_line('忌', cai_io, cai_opp_io, is_cai_empty)}")
    lines.append(f"大財忌出 : {format_entry_list(cai_io['忌出'])}")
    
    if cai_stem:
        hua_cai_parts = resolve_ji_for_stem_chart(cai_stem, cols, big_label_by_col, label_prefix="大")
        lines.append("化大財忌 : " + "；".join(hua_cai_parts))
    else:
        lines.append("化大財忌 : ")
    lines.append("")

    # ================= 大官 =================
    lines.append(header_age)
    lines.append(f'"{header_range}"')

    # 準備資料
    da_guan_stars = palace_star.get("官", "")
    is_guan_empty = not has_main_star(da_guan_stars)

    guan_io = compute_in_out_for_palace(da_four, palace_star, "官", label_prefix="大")
    
    # 若為空宮，預先計算對宮(夫妻)的 IO
    guan_opp_io = None
    if is_guan_empty:
        opp_pal = OPPOSITE_PALACE.get("官") # 夫
        if opp_pal:
            guan_opp_io = compute_in_out_for_palace(da_four, palace_star, opp_pal, label_prefix="大")

    guan_info = da_four.get("官")
    guan_stem = guan_info["stem"] if guan_info else ""

    lines.append(format_da_star_line("官", palace_star))
    lines.append(f"大官祿入 : {helper_format_in_line('祿', guan_io, guan_opp_io, is_guan_empty)}")
    lines.append(f"大官祿出 : {format_entry_list(guan_io['祿出'])}")
    lines.append(f"大官權入 : {helper_format_in_line('權', guan_io, guan_opp_io, is_guan_empty)}")
    lines.append(f"大官權出 : {format_entry_list(guan_io['權出'])}")
    lines.append(f"大官科入 : {helper_format_in_line('科', guan_io, guan_opp_io, is_guan_empty)}")
    lines.append(f"大官科出 : {format_entry_list(guan_io['科出'])}")
    lines.append(f"大官忌入 : {helper_format_in_line('忌', guan_io, guan_opp_io, is_guan_empty)}")
    lines.append(f"大官忌出 : {format_entry_list(guan_io['忌出'])}")

    if guan_stem:
        hua_guan_parts = resolve_ji_for_stem_chart(guan_stem, cols, big_label_by_col, label_prefix="大")
        lines.append("化大官忌 : " + "；".join(hua_guan_parts))
    else:
        lines.append("化大官忌 : ")
    lines.append("")

    # 大友
    lines.append(f"大友星系 : {palace_star.get('僕', '')}")
    lines.append("")

    return "\n".join(lines)


# ======================= 流年命/財/官/友 摘要 =======================

def render_liu_summary(data: dict, col_order: list, year_stem: str, raw_text: str) -> str:
    # 1. 取得標準的宮干資料 (地支干)
    liu_four_palace, palace_star, flow_label_by_col, cols = build_liu_four_hua_and_palace_stars(data, col_order)
    da_four, palace_star_big, big_label_by_col, cols2 = build_da_four_hua_and_palace_stars(data, col_order, raw_text)
    
    flow_to_big = build_flow_to_big_map(flow_label_by_col, big_label_by_col, cols)

    # === 計算目前所在年紀與流年 ===
    byear = parse_birth_year(raw_text)
    age = (CYEAR - byear) if byear else "未知"
    
    # 定義通用的標頭字串
    header_age = f"目前年紀 : {age}"
    header_year = f"目前流年 : {CYEAR}"

    lines = []

    # ================= 1. 流命 (特殊處理：拆分為流年干與地支干) =================
    lines.append(header_age)
    lines.append(header_year)
    
    # --- 準備「流年干」專用的混合映射表 ---
    stem_year = year_stem_of_year(CYEAR)
    liu_four_year_mixed = copy.deepcopy(liu_four_palace)
    
    # 找出流命所在的欄位，並用流年干重新計算該宮的四化分佈
    liu_row = build_liunian_row(cols, CYEAR)
    target_col_ming = find_col_for_label(cols, liu_row, "命")
    
    if target_col_ming:
         # 計算流年干的四化落點
         cells_map_year = debug_four_hua_locate(f"流命YearStem({stem_year})", stem_year, cols, data)
         by_flow_year = {}
         for c in cols:
             pal = flow_label_by_col.get(c, "")
             tokens = cells_map_year.get(c, [])
             if pal and tokens:
                 by_flow_year[pal] = list(tokens)
         
         # 覆蓋『命』宮的定義為流年干
         liu_four_year_mixed['命'] = {"stem": stem_year, "by_big": by_flow_year}

    # --- 區塊 A：流年干 ---
    lines.append(f"流年干 ({stem_year}) :")
    
    res_ming_y = compute_in_out_for_palace(liu_four_year_mixed, palace_star, "命", label_prefix="流")
    sub_ji_ming_y = compute_sub_ji_for_palace(liu_four_year_mixed, palace_star, "命", label_prefix="流")
    
    lines.append(f"流命星系 : {palace_star.get('命', '')}")
    lines.append(f"流命忌出 : {format_flow_entry_list(res_ming_y.get('忌出', []), flow_to_big)}")
    lines.append(f"該宮忌出 : {format_flow_entry_list(sub_ji_ming_y, flow_to_big)}")
    
    # 化流命忌 (流年干版)
    hua_ming_parts_y = resolve_ji_for_stem_chart(stem_year, cols, flow_label_by_col, label_prefix="流")
    hua_ming_parts_y = enhance_ji_with_big(hua_ming_parts_y, flow_to_big)
    lines.append("化流命忌 : " + ("；".join(hua_ming_parts_y) if hua_ming_parts_y else ""))
    
    lines.append("") # 空行分隔

    # --- 區塊 B：地支干 (原本邏輯) ---
    stem_ming_palace = liu_four_palace.get("命", {}).get("stem", "")
    lines.append(f"地支干 ({stem_ming_palace}) :")
    
    res_ming_p = compute_in_out_for_palace(liu_four_palace, palace_star, "命", label_prefix="流")
    sub_ji_ming_p = compute_sub_ji_for_palace(liu_four_palace, palace_star, "命", label_prefix="流")
    
    lines.append(f"流命星系 : {palace_star.get('命', '')}")
    lines.append(f"流命忌出 : {format_flow_entry_list(res_ming_p.get('忌出', []), flow_to_big)}")
    lines.append(f"該宮忌出 : {format_flow_entry_list(sub_ji_ming_p, flow_to_big)}")
    
    hua_ming_parts_p = []
    if stem_ming_palace:
        hua_ming_parts_p = resolve_ji_for_stem_chart(stem_ming_palace, cols, flow_label_by_col, label_prefix="流")
        hua_ming_parts_p = enhance_ji_with_big(hua_ming_parts_p, flow_to_big)
    lines.append("化流命忌 : " + ("；".join(hua_ming_parts_p) if hua_ming_parts_p else ""))
    
    lines.append("")
    
    # ================= 流財 =================
    lines.append(header_age)
    lines.append(header_year)

    # 準備資料
    liu_cai_stars = palace_star.get("財", "")
    is_cai_empty = not has_main_star(liu_cai_stars)

    cai_io = compute_in_out_for_palace(liu_four_palace, palace_star, "財", label_prefix="流")
    
    # 若為空宮，預先計算對宮(流福)的 IO
    cai_opp_io = None
    if is_cai_empty:
        opp_pal = OPPOSITE_PALACE.get("財") # 福
        if opp_pal:
            cai_opp_io = compute_in_out_for_palace(liu_four_palace, palace_star, opp_pal, label_prefix="流")

    cai_info = liu_four_palace.get("財")
    cai_stem = cai_info["stem"] if cai_info else ""

    lines.append(format_liu_star_line("財", palace_star))
    lines.append(f"流財祿入 : {helper_format_in_line('祿', cai_io, cai_opp_io, is_cai_empty, flow_to_big)}")
    lines.append(f"流財祿出 : {format_flow_entry_list(cai_io['祿出'], flow_to_big)}")
    lines.append(f"流財權入 : {helper_format_in_line('權', cai_io, cai_opp_io, is_cai_empty, flow_to_big)}")
    lines.append(f"流財權出 : {format_flow_entry_list(cai_io['權出'], flow_to_big)}")
    lines.append(f"流財科入 : {helper_format_in_line('科', cai_io, cai_opp_io, is_cai_empty, flow_to_big)}")
    lines.append(f"流財科出 : {format_flow_entry_list(cai_io['科出'], flow_to_big)}")
    lines.append(f"流財忌入 : {helper_format_in_line('忌', cai_io, cai_opp_io, is_cai_empty, flow_to_big)}")
    lines.append(f"流財忌出 : {format_flow_entry_list(cai_io['忌出'], flow_to_big)}")
    
    if cai_stem:
        hua_cai_parts = resolve_ji_for_stem_chart(cai_stem, cols, flow_label_by_col, label_prefix="流")
        hua_cai_parts = enhance_ji_with_big(hua_cai_parts, flow_to_big)
        lines.append("化流財忌 : " + "；".join(hua_cai_parts))
    else:
        lines.append("化流財忌 : ")
    lines.append("")

    # ================= 流官 =================
    lines.append(header_age)
    lines.append(header_year)

    # 準備資料
    liu_guan_stars = palace_star.get("官", "")
    is_guan_empty = not has_main_star(liu_guan_stars)

    guan_io = compute_in_out_for_palace(liu_four_palace, palace_star, "官", label_prefix="流")

    # 若為空宮，預先計算對宮(流夫)的 IO
    guan_opp_io = None
    if is_guan_empty:
        opp_pal = OPPOSITE_PALACE.get("官") # 夫
        if opp_pal:
            guan_opp_io = compute_in_out_for_palace(liu_four_palace, palace_star, opp_pal, label_prefix="流")

    guan_info = liu_four_palace.get("官")
    guan_stem = guan_info["stem"] if guan_info else ""

    lines.append(format_liu_star_line("官", palace_star))
    lines.append(f"流官祿入 : {helper_format_in_line('祿', guan_io, guan_opp_io, is_guan_empty, flow_to_big)}")
    lines.append(f"流官祿出 : {format_flow_entry_list(guan_io['祿出'], flow_to_big)}")
    lines.append(f"流官權入 : {helper_format_in_line('權', guan_io, guan_opp_io, is_guan_empty, flow_to_big)}")
    lines.append(f"流官權出 : {format_flow_entry_list(guan_io['權出'], flow_to_big)}")
    lines.append(f"流官科入 : {helper_format_in_line('科', guan_io, guan_opp_io, is_guan_empty, flow_to_big)}")
    lines.append(f"流官科出 : {format_flow_entry_list(guan_io['科出'], flow_to_big)}")
    lines.append(f"流官忌入 : {helper_format_in_line('忌', guan_io, guan_opp_io, is_guan_empty, flow_to_big)}")
    lines.append(f"流官忌出 : {format_flow_entry_list(guan_io['忌出'], flow_to_big)}")
    
    if guan_stem:
        hua_guan_parts = resolve_ji_for_stem_chart(guan_stem, cols, flow_label_by_col, label_prefix="流")
        hua_guan_parts = enhance_ji_with_big(hua_guan_parts, flow_to_big)
        lines.append("化流官忌 : " + "；".join(hua_guan_parts))
    else:
        lines.append("化流官忌 : ")
    lines.append("")

    # 流友
    lines.append(f"流友星系 : {palace_star.get('僕', '')}")
    lines.append("")

    return "\n".join(lines)

# ======================= 流月命／遷 運勢摘要 =======================

def render_liuyue_ming_qian_fortunes(data: dict, col_order: list, raw_text: str) -> str:
    """
    整年流月運勢（每月一行）：
      2026年1月 : 本月運勢平穩
      2026年2月 : 太陽祿/月命｜把握機會，順勢而為，好運指數80分
    """
    cols = reorder_cols_by_palace(data, col_order)
    liunian_row = build_liunian_row(cols, CYEAR)
    base_idx = liuyue_base_index(cols, data, liunian_row)

    month_stems = LIUYUE_MONTH_STEMS.get(CYEAR)
    if not month_stems:
        ystem = year_stem_of_year(CYEAR)
        start = STEMS.index(ystem) if ystem in STEMS else 0
        month_stems = [STEMS[(start + i) % 10] for i in range(12)]

    lines = []
    for month_no in range(1, 13):
        m_stem = month_stems[month_no - 1]
        liuyue_row = build_liuyue_row_by_month(cols, base_idx, month_no)
        month_cells_map = debug_four_hua_locate(f"流月{month_no:02d}四化(運勢)", m_stem, cols, data)
        line = compute_yue_fortune_for_month(CYEAR, month_no, cols, liuyue_row, m_stem, month_cells_map)
        lines.append(line)
    return "\n".join(lines)

# ======================= 流日命／遷 運勢摘要 =======================

def render_liuri_ming_qian_fortunes(data: dict, col_order: list, raw_text: str) -> str:
    """
    整年流日運勢（每天一行），格式：
      國曆｜農曆 :
      2026.2.17｜2026年1月1日 : 運勢 平，忌時 : 亥時(21:00~23:00)
    """
    if CYEAR not in LIURI_CONFIG:
        return ""

    cols = reorder_cols_by_palace(data, col_order)
    liunian_row = build_liunian_row(cols, CYEAR)
    base_idx = liuyue_base_index(cols, data, liunian_row)
    year_cfg = LIURI_CONFIG[CYEAR]
    solar_start = LIURI_LUNAR_YEAR_START_SOLAR.get(CYEAR)

    lines = []
    if solar_start is not None:
        lines.append("國曆｜農曆 :")

    day_offset_from_lunar_0101 = 0
    max_days_global = 0
    if 'OUTPUT_SWITCH' in globals():
        max_days_global = OUTPUT_SWITCH.get("LIU_RI", {}).get("MAX_DAYS", 0) or 0

    for month_no in sorted(year_cfg.keys()):
        cfg = year_cfg[month_no]
        total_days = cfg.get("days", 0) or 0
        if total_days <= 0:
            continue

        liuyue_row = build_liuyue_row_by_month(cols, base_idx, month_no)
        days_this_month = total_days
        if max_days_global > 0:
            days_this_month = min(days_this_month, max_days_global)

        for day_no in range(1, days_this_month + 1):
            d_stem = day_stem_for(CYEAR, month_no, day_no)
            if not d_stem:
                continue
            liuri_row = build_liuri_palace_row_for_day(cols, liuyue_row, day_no)
            day_cells_map = debug_four_hua_locate(f"流日{month_no:02d}-{day_no:02d}四化(運勢)", d_stem, cols, data)

            lunar_line = compute_ri_fortune_for_day(
                CYEAR, month_no, day_no,
                cols, liuri_row,
                d_stem, day_cells_map,
                data,
            )

            if solar_start is not None:
                g_date = solar_start + timedelta(days=day_offset_from_lunar_0101)
                solar_str = f"{g_date.year}.{g_date.month}.{g_date.day}"
                full_line = f"{solar_str}｜{lunar_line}"
            else:
                full_line = lunar_line

            lines.append(full_line)
            day_offset_from_lunar_0101 += 1

    return "\n".join(lines)


# ======================= 主程式：命盤計算入口 =======================

def run_chart_from_text(input_text: str, target_year: int = 2026) -> str:
    """
    接收一整段命盤文字（RAW 格式），跑完所有計算，
    回傳整段輸出（包含表格 + 摘要）。
    """
    global CYEAR, OUTPUT_SWITCH

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        RAW = input_text

        data, col_order, year_stem = parse_chart(RAW)

        TARGET_YEAR = target_year
        CYEAR = TARGET_YEAR if TARGET_YEAR in (2025, 2026) else current_year()

        OUTPUT_SWITCH = {
            "DA_FOUR_HUA": {lbl: True for lbl in PALACE_ORDER_CANONICAL},
            "LIU_MING_FOUR_HUA": {
                "YEAR_STEM_LINE": True,
                "BRANCH_STEM_LINE": True
            },
            "LIU_FOUR_HUA": {lbl: True for lbl in PALACE_ORDER_CANONICAL},
            "LIU_YUE": {
                "MONTHS": list(range(1, 13)),
                "SHOW_PALACE_ROW": True,
                "SHOW_HUA_ROW": True
            },
            "LIU_RI": {
                "ENABLE": True,
                "MAX_DAYS": 0,
                "SHOW_PALACE_ROW": True,
                "SHOW_HUA_ROW": True
            }
        }

        table = render_markdown_table_v7(data, col_order, year_stem, RAW)
        liuyue_summary = render_liuyue_ming_qian_fortunes(data, col_order, RAW)


        print("\n==== 大限命/財/官/友 摘要 ====\n")
        da_summary = render_da_summary(data, col_order, year_stem, RAW)
        print(da_summary)

        print("==== 流年命/財/官/友 摘要 ====\n")
        liu_summary = render_liu_summary(data, col_order, year_stem, RAW)
        print(liu_summary)
        liuri_summary = render_liuri_ming_qian_fortunes(data, col_order, RAW)

        print("\n==== 流月命/遷 運勢 ====\n")
        print(liuyue_summary)

        print("\n==== 流日命/遷 運勢 ====\n")
        print(liuri_summary)

        #print(f"\n==== 本次輸出年份：{CYEAR} ====\n")
        #print(table)

    result_str = buf.getvalue()
    return result_str if result_str.strip() else "沒有輸出內容，請檢查命盤格式或程式流程。"

# ======================= Flask Web 介面 =======================

app = Flask(__name__)

HTML_PAGE = """
<!doctype html>
<html lang="zh-Hant">
<head>
    <meta charset="utf-8">
    <title>紫微命盤流年 / 流月 / 流日分析（Web 版）</title>
    <style>
        body { font-family: sans-serif; margin: 20px; }
        textarea { width: 100%; height: 300px; font-family: monospace; }
        pre { white-space: pre-wrap; background: #f5f5f5; padding: 10px; border-radius: 4px; }
        .btn { padding: 8px 16px; font-size: 14px; }
        .field { margin-bottom: 12px; }
    </style>
</head>
<body>
    <h1>紫微命盤流年 / 流月 / 流日分析（Web 版）</h1>

    <form method="post">
        <div class="field">
            <label>目標年份（例如 2026）：</label>
            <input type="number" name="year" value="{{ year }}" />
        </div>

        <div class="field">
            <label>在這裡貼上命盤文字（原本 RAW 的那種格式）：</label><br>
            <textarea name="raw_text">{{ raw_text }}</textarea>
        </div>

        <button class="btn" type="submit">開始解析命盤</button>
    </form>

    {% if result %}
        <h2>解析結果：</h2>
        <pre>{{ result }}</pre>
    {% endif %}
</body>
</html>
"""

@app.route("/", methods=["GET", "POST"])
def index():
    raw_text = ""
    result = ""
    year = 2026

    if request.method == "POST":
        raw_text = request.form.get("raw_text", "")
        year_str = request.form.get("year", "").strip()
        
        if year_str:
            try:
                year = int(year_str)
            except ValueError:
                year = 2026

        if raw_text.strip():
            try:
                # 呼叫主程式進行運算
                result = run_chart_from_text(raw_text, target_year=year)
            except Exception as e:
                result = f"計算過程出錯：{e}"

    return render_template_string(HTML_PAGE, raw_text=raw_text, result=result, year=year)

if __name__ == "__main__":
    # 啟動 Flask 伺服器
    app.run(host="0.0.0.0", port=5000, debug=True)