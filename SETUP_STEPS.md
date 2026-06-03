# 從零開始搭建完整步驟

這份文件記錄從無到有 Setup 這套「室內建材即時模擬替換 App」的所有步驟。

---

## Step 1：下載安裝 Python 3.11

| 項目 | 說明 |
|------|------|
| 下載網址 | https://www.python.org/downloads/ |
| 版本 | 3.11 或 3.12 |
| 勾選 | ✅ Add Python to PATH |

安裝完成後打開 PowerShell 確認：

```powershell
python --version
pip --version
```

---

## Step 2：下載專案程式碼

專案在 `C:\Users\TW-10\Documents\建材用\`，已經存在。

確認資料夾內容：

```powershell
cd C:\Users\TW-10\Documents\建材用
Get-ChildItem
```

應該看到：
```
ARCHITECTURE.md
backend/
mobile/
index.html
.gitignore
```

---

## Step 3：下載 SAM 模型（唯一要手動抓的檔案）

這是 AI 做影像分割必要的模型權重檔。

### 方式一：瀏覽器下載

打開這個網址：
```
https://dl.fbaipublicfiles.com/segment_anything/sam_vit_b_01ec64.pth
```
會自動下載（約 375 MB），完成後把檔案放到：

```
backend/models/sam_vit_b_01ec64.pth
```

### 方式二：用 PowerShell 下載

```powershell
cd backend
New-Item -ItemType Directory -Path models -Force
Invoke-WebRequest -Uri "https://dl.fbaipublicfiles.com/segment_anything/sam_vit_b_01ec64.pth" -OutFile "models/sam_vit_b_01ec64.pth"
```

> ⚠️ 進度條跑完前不要關閉視窗，檔案約 375 MB，依網路速度可能需要 5-15 分鐘。

---

## Step 4：安裝 Python 套件

```powershell
cd backend
pip install -r requirements.txt
```

安裝過程會自動下載：
- FastAPI + Uvicorn（網頁伺服器）
- OpenCV（影像處理）
- PyTorch（深度學習框架）
- Segment Anything（Meta 的分割模型）
- SQLAlchemy（資料庫操作）
- 其他依賴套件

全部安裝約需要 3-8 分鐘（看網路速度）。

---

## Step 5：啟動後端服務

```powershell
cd backend
uvicorn app.main:app --reload --port 8000
```

看到這樣的訊息表示成功：

```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete.
```

**保持這個視窗開啟，不能關閉。**

---

## Step 6：用瀏覽器測試 API

打開瀏覽器，網址輸入：
```
http://127.0.0.1:8000/docs
```

你會看到一個互動式 API 文件頁面（Swagger UI），上面列出所有可用的功能。

---

## Step 7：實際操作測試（六個動作）

### 測試 A — 確認服務正常

在 Swagger 頁面找到 `GET /api/health`，點「Try it out」→「Execute」

預期回應：
```json
{
  "status": "ok",
  "service": "Interior Material Swap API"
}
```

---

### 測試 B — 上傳素材照片

1. 找一張建材照片（磁磚、木板、石材都可以），存到電腦桌面
2. 在 Swagger 找到 `POST /api/materials/upload`
3. 點「Try it out」
4. 填寫：
   - **file:** 選擇你準備好的建材照片
   - **name:** 「白色磁磚」（自己取名）
   - **category:** `tile`（可選 tile / wood / stone / fabric）
   - **user_id:** `default`
5. 按 Execute
6. 等待約 2-5 秒

成功回應範例：
```json
{
  "id": "a1b2c3d4-...",
  "name": "白色磁磚",
  "category": "tile",
  "dominant_colors": [[240, 240, 235], [230, 225, 220], ...],
  "created_at": "2026-06-02T..."
}
```

> 把回傳的 `id` 複製下來，下一步會用到。

---

### 測試 C — 查看素材庫

找到 `GET /api/materials`，按 Execute。

會看到剛才上傳的所有素材列表。

---

### 測試 D — 上傳空間照片 + AI 分割

1. 找一張房間照片（客廳、浴室、臥室皆可）
2. 在 Swagger 找到 `POST /api/spatial/upload`
3. 點「Try it out」
4. 填寫：
   - **file:** 房間照片
   - **name:** 「客廳」
   - **room_type:** `living_room`（可選 living_room / bathroom / bedroom / kitchen）
   - **user_id:** `default`
5. 按 Execute
6. ⏳ **等待 30-60 秒**（SAM 模型在 CPU 上跑分割）

成功回應範例：
```json
{
  "project_id": "x1y2z3...",
  "segments_count": 8,
  "segments": [
    {
      "id": "seg_001...",
      "label": "segment_0",
      "confidence": 0.92,
      "polygon": [[120, 45], [500, 45], [500, 300], ...],
      "bounding_box": [100, 30, 450, 320]
    },
    ...
  ],
  "lighting": {
    "angle_deg": 45.3,
    "strength": 120.5,
    "direction_vector": [0.7, 0.6]
  }
}
```

> 把 `project_id` 和其中一個 `segments[].id` 複製下來。

---

### 測試 E — 紋理替換（貼圖）

1. 找到 `POST /api/spatial/{project_id}/replace`
2. 點「Try it out」
3. 在 `project_id` 欄位貼上剛才的 project_id
4. Request body 填寫：
```json
{
  "segment_id": "貼上 segment_id",
  "material_id": "貼上 material_id",
  "blend_mode": "multiply"
}
```
5. 按 Execute
6. 等待約 3-5 秒

成功回應：
```json
{
  "replacement_id": "rpl_001...",
  "result_image": "uploads/results/result_xxx.jpg"
}
```

---

### 測試 F — 查看結果圖片

打開瀏覽器，輸入：
```
http://127.0.0.1:8000/uploads/results/result_xxx.jpg
```

（把檔名換成你實際得到的）

你應該會看到**原始房間照片 + 指定區塊已被替換為素材紋理**的合成結果。

---

## Step 8：讓手機也能測試（同一個 Wi-Fi）

### 8a — 找到電腦的區域網路 IP

```powershell
ipconfig
```

找「無線區域網路介面卡 Wi-Fi」或「乙太網路卡」下面的 **IPv4 位址**，例如：
```
IPv4 位址 . . . . . . . . . . . : 192.168.1.100
```

記下這個 IP（後面都用這個代替）。

### 8b — 開防火牆

```powershell
# 以系統管理員身分執行
netsh advfirewall firewall add rule name="InteriorMatAPI" dir=in action=allow protocol=TCP localport=8000
```

### 8c — 重新啟動後端（讓手機可連）

先關掉原本的 Uvicorn（按 Ctrl+C），然後重開：

```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

加上 `--host 0.0.0.0` 才會接受來自手機的連線。

### 8d — 手機測試

1. 確保手機連的是**同一個 Wi-Fi**
2. 手機打開瀏覽器，輸入 `http://192.168.1.100:8000/docs`
3. 你應該看到和電腦上一模一樣的 Swagger 頁面
4. 用手機選取照片上傳測試

---

## 常見問題

### Q1：pip install 很慢怎麼辦？

```powershell
# 改用國內鏡像
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### Q2：python 指令找不到？

重新安裝 Python，確認 ✅ Add Python to PATH 有勾選。

或手動加入 PATH：

```powershell
$env:Path += ";C:\Users\TW-10\AppData\Local\Programs\Python\Python311"
```

### Q3：Port 8000 被佔用？

```powershell
# 找出誰在用
netstat -ano | findstr :8000

# 殺掉該 Process
taskkill /PID <號碼> /F
```

### Q4：上傳後圖片不存在？

檢查 `backend/uploads/` 裡面有沒有對應的資料夾：

```powershell
Get-ChildItem backend/uploads/ -Recurse
```

### Q5：分割結果不理想？

- 換一張照片試試（光線均勻、不要有太多雜物）
- 照片解析度不要太高（建議 1080p）
- 確保房間界線清楚（牆面、地板對比明顯）

---

## 最終檔案結構（完成後的樣子）

```
C:\Users\TW-10\Documents\建材用\
├── ARCHITECTURE.md          ← 技術架構說明
├── DEPLOY_GUIDE.md          ← 部署操作手冊（自己用 / 雲端）
├── SETUP_STEPS.md           ← 本文件（從零搭建步驟）
├── index.html               ← 原本的木工計算器
├── .gitignore
├── backend\
│   ├── .env                 ← 設定檔
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app.db               ← SQLite 資料庫（自動產生）
│   ├── models\
│   │   └── sam_vit_b_01ec64.pth  ← SAM 模型（你下載的 375MB）
│   ├── uploads\
│   │   ├── materials\       ← 素材照片存放處
│   │   ├── rooms\           ← 空間照片存放處
│   │   └── results\         ← 合成結果存放處
│   └── app\
│       ├── main.py
│       ├── config.py
│       ├── db.py
│       ├── routers\
│       │   ├── material.py
│       │   └── spatial.py
│       ├── services\
│       │   ├── material_processor.py
│       │   ├── segmentation.py
│       │   └── texture_mapping.py
│       └── models\
│           └── material.py
└── mobile\
    ├── api_client.dart
    └── segmentation_view.dart
```
