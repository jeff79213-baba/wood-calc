# 建材模擬 HTML 產生工具 — 使用說明

用這套工具，你可以在電腦上處理照片 → 產生單一 HTML 檔案 → 直接寄給客戶。

---

## 整套流程（3 步驟）

### 第 0 步：確認環境

```powershell
cd backend
pip install -r requirements.txt
```

（如果之前已經裝過可以跳過）

### 第 1 步：偵測區塊（輔助工具）

把你拍的房間照片放到 `tools/` 資料夾，執行：

```powershell
cd tools
python generate_regions.py room.jpg
```

它會：
1. 用 AI 自動找出房間的各個區塊（牆面、地板、天花板...）
2. 產出一張標記圖 `regions_room.jpg`，上面有編號
3. 產出設定檔 `regions_room.json`

**打開 `regions_room.jpg`**，確認每個編號對應到正確的區塊。

---

### 第 2 步：編輯專案設定

把 `regions_room.json` 的內容複製到 `project_config.json`，然後加上素材照片：

```json
{
  "project_name": "王先生客廳",
  "room_photo": "room.jpg",
  "regions": [
    {
      "name": "電視牆",
      "polygon": [[120,80],[680,80],[680,540],[120,540]],
      "materials": [
        { "name": "白色文化石", "image": "stone_white.jpg" },
        { "name": "灰色清水模", "image": "stone_gray.jpg" }
      ]
    },
    {
      "name": "地板",
      "polygon": [[50,550],[750,550],[750,780],[50,780]],
      "materials": [
        { "name": "淺橡木紋", "image": "wood_light.jpg" },
        { "name": "深胡桃木", "image": "wood_dark.jpg" }
      ]
    }
  ]
}
```

把你的素材照片也放到 `tools/` 資料夾。

---

### 第 3 步：產生 HTML

```powershell
python generate_html.py
```

完成後會在 `tools/output/` 資料夾產生一個 `.html` 檔案。

---

### 第 4 步：寄給客戶

這個 `.html` 檔案是**單一檔案**（所有圖片都包在裡面），你可以：
- 📧 Email 附件
- 💬 LINE 傳檔案
- 📱 WhatsApp 傳檔案
- ☁️ 上傳到任何雲端硬碟分享連結

**客戶打開就是一個互動網頁**：點區塊 → 選建材 → 即時切換看效果。

---

## 檔案清單

| 檔案 | 用途 |
|------|------|
| `project_config.json` | **你編輯的專案設定檔**（定義場景+區塊+素材） |
| `generate_regions.py` | 輔助工具：自動偵測區塊多邊形（省去手動填座標） |
| `generate_html.py` | **主工具**：讀取設定 → 算貼圖 → 產出 HTML |
| `output/` | 產出的 HTML 檔案放在這裡 |

---

## 常見問題

**Q：圖片很大，HTML 檔案會不會太大？**
A：照片會壓縮成 jpg 品質 85%，一般客廳場景 + 3-5 種素材約 **3-8 MB**，LINE 和 Email 都能傳。

**Q：客戶用手機打開會跑版嗎？**
A：已支援 RWD 自適應，手機電腦都能正常顯示。

**Q：一定要用 SAM 模型嗎？**
A：沒有 SAM 模型也能跑，會自動改用 GrabCut 降階分割。或者你也可以手動在 JSON 填座標。
