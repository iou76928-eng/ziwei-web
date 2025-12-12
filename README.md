# 紫微斗數智慧分析 Web 版

這個專案提供一個 Flask 驅動的網頁介面，透過 Selenium 爬蟲抓取公開的紫微斗數命盤資料，送入核心運算後自動整理成九個分析區塊，方便快速閱讀與解讀。

## 主要功能
- **自動抓取命盤**：使用 headless Chrome 連線到 `https://fate.windada.com/cgi-bin/fate`，填入出生年月日時與性別後取得命盤原始資料。
- **核心運算與解析**：`ziwei_core.py` 解析命盤文字、計算大限/流年/流月/流日資料，並保留生年四化等檢核邏輯。
- **九區塊重組**：`zh2_logic.py` 將核心輸出轉成九個主題區塊（大限課題、流年財帛、客戶類型等），並為四化、運勢標示上色，生成 HTML 供前端呈現。
- **網頁介面**：`app_ui.py` 提供單頁表單，輸入出生資訊與目標流年即可觸發整套流程並顯示結果；同時附帶原始命盤文字以便除錯。

## 環境需求
- Python 3.9+。
- Google Chrome / Chromium 與對應的 ChromeDriver（Selenium 會呼叫 headless 瀏覽器）。
- 依照 `requirements.txt` 安裝的套件：`flask`、`selenium`、`beautifulsoup4`、`gunicorn`、`webdriver-manager`。

## 安裝步驟
1. 建立虛擬環境並安裝依賴：
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. 確認系統已有 Chrome/Chromium 與相容版本的 ChromeDriver；若沒有可使用 `webdriver-manager` 協助下載，或自行放置在 PATH 中。

## 執行方式
1. 啟動伺服器：
   ```bash
   python app_ui.py
   ```
   伺服器預設在 `http://127.0.0.1:5000` 啟動。
2. 開啟瀏覽器並輸入網址，填入表單的性別與出生年月日時，必要時指定「分析流年」，按下「開始分析」即可。
3. 等待「命盤解析中」提示結束後，下方會顯示九個區塊的分析結果；展開「查看原始命盤數據」可檢視取得的原始文字。

## 檔案結構與流程
- `app_ui.py`：Flask 路由與 HTML 樣板；負責觸發 Selenium 爬蟲、呼叫核心運算與區塊整理，最後將結果渲染到頁面上。
- `ziwei_core.py`：命盤解析與運算核心，將爬回的文字轉成可程式處理的結構並產出分析結果。
- `zh2_logic.py`：將核心分析的文字輸出轉換成九區塊 HTML，包含標題替換、宮位對應與關鍵詞上色。
- `render.yaml`：Render 部署設定（若需在 Render 平台上架）。

## 使用提示
- 伺服器端會以互斥鎖確保同一時間只有一個 Selenium 工作，避免記憶體佔用過高。
- 若爬蟲失敗（例如表單變動或網站延遲），頁面會顯示錯誤訊息；可先檢查 ChromeDriver 是否相容或重試。
- 部署到雲端時，可視需求將 `app.run` 的 `debug` 關閉（預設為 False），並使用 `gunicorn` 作為生產伺服器。

