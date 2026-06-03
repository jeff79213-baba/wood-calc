# 部署操作手冊

## 兩種使用模式總覽

### 模式 A：自己用（區域網路 / 開發階段）

```
你的手機 APP ──Wi-Fi──→ 你的電腦（跑後端）
                          └─ FastAPI + SAM 模型
```

#### 條件
- 手機和電腦**必須在同一個 Wi-Fi 網路**
- **電腦不能關機**，後端程式必須持續執行
- 僅限你自己或同個區網內的人使用

#### 優點
- **完全免費**
- 資料不經過第三方雲端
- 開發測試方便

#### 缺點
- 電腦關機就不能用
- 手機不能離太遠（Wi-Fi 訊號範圍）
- 多人同時使用時效能看電腦規格

---

### 模式 B：給別人用（正式上線 / 雲端部署）

```
任何人手機 APP ──4G/Wi-Fi──→ 雲端主機（跑後端）
                               └─ FastAPI + SAM 模型
```

#### 條件
- 需要一台雲端伺服器（月租約 $10-30 USD）
- 需申請一個固定 IP 或網域名稱
- 後端程式部署到雲端後可 24 小時運作

#### 優點
- **任何人都可以隨時使用**
- 不受地域限制（有網路就行）
- 可橫向擴展（多人同時使用）

#### 缺點
- 每月有伺服器費用
- 需要管理雲端主機（防火牆、更新等）

---

## 模式 A：詳細步驟（自己用）

### 前置準備

| 項目 | 說明 |
|------|------|
| 硬體 | Windows 電腦一台 + 手機一支（Android / iOS） |
| 網路 | 手機與電腦連同一個 Wi-Fi |
| 下載 | Python 3.11、SAM 模型檔 |

### Step 1 — 確認電腦區域 IP

```powershell
ipconfig
```

看「無線區域網路介面卡」的 **IPv4 位址**，例如 `192.168.1.100` \
**這個 IP 等等會用到，先記下來。**

### Step 2 — Windows 防火牆開通 Port 8000

```powershell
# 以系統管理員身分執行 PowerShell
netsh advfirewall firewall add rule name="InteriorMatAPI" dir=in action=allow protocol=TCP localport=8000
```

### Step 3 — 啟動後端

```powershell
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

看到 `Uvicorn running on http://0.0.0.0:8000` 表示成功。

### Step 4 — 用手機測試

1. **手機瀏覽器測試：** 手機打開瀏覽器，輸入 `http://192.168.1.100:8000/docs`
   - 應該看到 Swagger API 文件（可以和電腦同時操作）
2. **手機上傳照片：**
   - 找一張房間照片存在手機裡
   - 在 Swagger 找到 `POST /api/spatial/upload`
   - 用手機瀏覽器選取手機內的照片上傳
3. **查看結果圖片：**
   - 替換完成後，回傳的 `result_image` 是一個路徑
   - 用手機瀏覽器開 `http://192.168.1.100:8000/uploads/results/xxx.jpg`

### Step 5 — 用手機 App 測試（需要先編譯 Flutter App）

編譯 APK 或使用除錯模式：

```bash
# 在 Flutter 專案目錄下
flutter run  # USB 連接手機
```

或打包 APK：

```bash
flutter build apk --debug
```

安裝 APK 到手機後，在 App 設定中將 API 網址設為 `http://192.168.1.100:8000`

---

## 模式 B：詳細步驟（給別人用 / 雲端部署）

### 前置準備

| 項目 | 費用 | 說明 |
|------|------|------|
| 雲端主機 | $10-30 USD/月 | 建議有 GPU 的機型（如 AWS g4dn.xlarge） |
| 網域名稱（選用） | $10-15 USD/年 | 方便記憶，如 `matswap.myapp.com` |
| SSL 憑證（選用） | 免費 | Let's Encrypt 提供 |

### Step 1 — 租用雲端主機（以 DigitalOcean 為例）

1. 註冊 [DigitalOcean](https://digitalocean.com)
2. 建立 Droplet：
   - **Image:** Ubuntu 22.04
   - **Plan:** 建議至少 4GB RAM / 2 CPU
   - **Region:** 離你的使用者越近越好
3. 記下主機的 **Public IP**（例如 `123.45.67.89`）

### Step 2 — SSH 進入主機安裝環境

```bash
ssh root@123.45.67.89

# 安裝 Python
apt update && apt install -y python3.11 python3.11-venv python3-pip

# 安裝 CUDA（如果有 GPU）
# 請參考 https://developer.nvidia.com/cuda-downloads
```

### Step 3 — 上傳後端程式

```bash
# 在本機打包
cd backend
tar czf backend.tar.gz .

# 上傳到雲端主機
scp backend.tar.gz root@123.45.67.89:/root/

# SSH 到主機解壓
ssh root@123.45.67.89
tar xzf backend.tar.gz
cd backend
```

### Step 4 — 安裝套件 + 下載 SAM 模型

```bash
pip install -r requirements.txt

# 下載 SAM 模型（約 375 MB）
mkdir -p models
wget https://dl.fbaipublicfiles.com/segment_anything/sam_vit_b_01ec64.pth -O models/sam_vit_b_01ec64.pth
```

### Step 5 — 設定環境變數

編輯 `.env`：

```
DATABASE_URL=sqlite+aiosqlite:///./app.db
DEVICE=cpu
```

若有 GPU：

```
DEVICE=cuda
```

### Step 6 — 用 Supervisor 保持服務不中斷

```bash
pip install supervisor
echo_supervisord_conf > /etc/supervisord.conf
```

編輯 `/etc/supervisord.conf`，在底部加入：

```ini
[program:interior_mat]
command=/usr/bin/python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
directory=/root/backend
autostart=true
autorestart=true
stderr_logfile=/var/log/backend.err.log
stdout_logfile=/var/log/backend.out.log
```

啟動：

```bash
supervisord -c /etc/supervisord.conf
```

### Step 7 — 開啟防火牆

```bash
ufw allow 8000/tcp
ufw enable
```

### Step 8 — 測試

手機瀏覽器打開 `http://123.45.67.89:8000/docs` \
應該看到 Swagger API 文件。

### Step 9 — 設定網域 + HTTPS（選用但建議）

使用 Nginx 反向代理 + Let's Encrypt：

```bash
apt install -y nginx certbot python3-certbot-nginx
```

編輯 `/etc/nginx/sites-available/interior-mat`：

```nginx
server {
    server_name matswap.myapp.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    client_max_body_size 50M;
}
```

啟用並取得 SSL：

```bash
ln -s /etc/nginx/sites-available/interior-mat /etc/nginx/sites-enabled/
nginx -t
systemctl reload nginx

certbot --nginx -d matswap.myapp.com
```

---

## 常見狀況排除

### 手機連不上電腦的 API

```powershell
# 先確認電腦端有在聽
netstat -ano | findstr :8000

# 再用 ping 確認手機與電腦連通
# 手機安裝 Ping 工具 App，ping 你的電腦 IP
```

### 防火牆擋住

```powershell
# 關閉防火牆測試（記得測完再打開）
netsh advfirewall set allprofiles state off

# 測試完成後
netsh advfirewall set allprofiles state on
```

### SAM 分割太慢（超過 2 分鐘）

```powershell
# 降低圖片解析度，編輯 config.py 的 max_image_size
max_image_size: 1024  # 原 2048
```

### SQLite 資料庫錯誤

```powershell
# 刪除舊的資料庫重新建立
Remove-Item backend/app.db -ErrorAction SilentlyContinue
```
