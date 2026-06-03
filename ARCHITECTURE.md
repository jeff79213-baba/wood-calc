# 室內建材即時模擬替換 App — 完整技術架構文件

## 1. 技術堆疊建議 (Tech Stack)

### 前端 (Mobile)
| 層級 | 技術 | 理由 |
|------|------|------|
| 框架 | **Flutter** (Dart) | 跨平台、Impeller GPU 渲染引擎有利紋理貼圖預覽、強生態系 |
| 相機 | `camera` / `image_picker` | 整合平台原生相機 |
| 狀態管理 | Riverpod | 輕量、型別安全 |
| HTTP | Dio | 支援 multipart 上傳、攔截器 |
| 圖片顯示 | `ExtendedImage` / `CustomPainter` | 大圖縮放、遮罩疊加 |

### 後端 (AI Inference Server)
| 層級 | 技術 | 理由 |
|------|------|------|
| Web 框架 | **FastAPI** (Python 3.11+) | Async 原生、自動生成 OpenAPI |
| 資料庫 | **PostgreSQL** + `pgvector` | 儲存素材特徵向量以支援相似度搜尋 |
| Cache | Redis | 暫存處理中的分割結果 |
| ORM | SQLAlchemy 2.0 (async) | 成熟的 Async ORM |

### AI / 電腦視覺
| 任務 | 模型 | 部署方式 |
|------|------|----------|
| 語意分割 (主力) | **SAM 2** (Meta) | Cloud GPU 推理 |
| 輕量分割 (離線) | **MobileSAM** / EfficientSAM | ONNX Runtime / TFLite |
| 紋理特徵提取 | ResNet-18 Embedding | ONNX 輸出 512 維向量 |
| 影像處理 | OpenCV 4.10 | 透視變換、色彩分析、混合 |
| 主色提取 | K-Means 聚類 | OpenCV 內建 |

### DevOps
- **Container:** Docker
- **GPU Inference:** NVIDIA Triton 或自建 FastAPI + PyTorch
- **Model Registry:** MLflow 或 S3

---

## 2. 系統架構

```
┌─────────────────────────────────────────────────────────┐
│                    Flutter App (Mobile)                  │
│  ┌──────────┐  ┌──────────────┐  ┌───────────────────┐ │
│  │ 相機模組  │  │ 素材庫列表    │  │ 空間照片 + 遮罩疊加 │ │
│  │ 拍照/選圖  │  │ Grid 瀏覽     │  │ 點選區塊觸發替換   │ │
│  └────┬─────┘  └──────┬───────┘  └────────┬──────────┘ │
│       └───────────────┬────────────────────┘            │
└───────────────────────┼─────────────────────────────────┘
                        │ HTTP REST API (JSON)
                        ▼
┌──────────────────────────────────────────────────────────┐
│                 FastAPI Backend Server                    │
│                                                          │
│  ┌────────────────┐  ┌──────────────────────────────┐   │
│  │ material API   │  │ spatial API                  │   │
│  │ POST /upload   │  │ POST /upload (分割)          │   │
│  │ GET /list      │  │ GET /{id}/segments           │   │
│  │ DELETE /{id}   │  │ POST /{id}/replace (貼圖)    │   │
│  └───────┬────────┘  └────────┬─────────────────────┘   │
│          │                    │                          │
│  ┌───────▼────────────────────▼─────────────────────┐   │
│  │              Service Layer                        │   │
│  │  ┌──────────────────┐  ┌────────────────────┐    │   │
│  │  │ MaterialProcessor │  │ SegmentationService │    │   │
│  │  │ ・去透視校正      │  │ ・SAM 分割          │    │   │
│  │  │ ・裁切/無縫處理   │  │ ・邊緣平滑          │    │   │
│  │  │ ・特徵提取(色+向量)│  │ ・光源估計(選配)    │    │   │
│  │  └──────────────────┘  └────────┬───────────┘    │   │
│  │                                 │                │   │
│  │  ┌──────────────────────────────▼─────────────┐  │   │
│  │  │        TextureMapper                        │  │   │
│  │  │  ・Homography 透視變換                      │  │   │
│  │  │  ・光影保留混合 (multiply blend)            │  │   │
│  │  │  ・邊緣羽化融合                             │  │   │
│  │  │  ・批次多區塊替換                           │  │   │
│  │  └────────────────────────────────────────────┘  │   │
│  └───────────────────────────────────────────────────┘   │
│                                                          │
│  ┌──────────────────────────────────────────────────┐    │
│  │  PostgreSQL (pgvector) / Redis / Filesystem      │    │
│  └──────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────┘
```

---

## 3. 資料庫設計 (Database Schema)

### Entity Relationship

```
users (外部身份提供, 簡化為 user_id string)
    │
    ├── materials       素材庫
    │     id (UUID PK)
    │     user_id
    │     name / category / width_cm / height_cm
    │     original_image / processed_texture / thumbnail
    │     texture_feature (ARRAY<FLOAT> 512維 pgvector)
    │     dominant_colors (JSONB [[r,g,b],...])
    │     is_seamless
    │     created_at / updated_at
    │
    └── projects        空間專案
          id (UUID PK)
          user_id / name / room_type
          original_photo / result_photo
          image_width / image_height
          lighting_direction (JSONB)
          created_at / updated_at
               │
               └── segments    分割區塊
                     id (UUID PK)
                     project_id (FK)
                     label / confidence
                     mask_polygon (JSONB [[x,y],...])
                     bounding_box (JSONB [x,y,w,h])
                     sort_order
                     created_at
                          │
                          └── replacements    替換記錄
                                id (UUID PK)
                                project_id (FK)
                                segment_id (FK)
                                material_id (FK)
                                result_image
                                params (JSONB blend_mode etc.)
                                created_at
```

---

## 4. 核心流程圖

### 素材上流程
```
[拍照/選圖] → MaterialProcessor.detect_and_crop()
            → correct_perspective()  去透視歪斜
            → make_seamless()        無縫紋理處理
            → extract_dominant_colors()  K-Means 主色
            → extract_feature()       ResNet Embedding
            → 存入 DB + 檔案系統
```

### 空間分割流程
```
[拍照/選圖] → SegmentationService.segment_automatic()
            → SAM AutomaticMaskGenerator
            → 產生 masks + scores + polygons
            → 邊緣平滑 (Morphology)
            → 輪廓簡化 (approxPolyDP)
            → 儲存 Segment 到 DB
            → (選配) estimate_lighting()
            → 回傳 polygons 給前端繪製
```

### 紋理替換流程 (核心)
```
[前端] 點選區塊 + 選擇素材
       │
       ▼
[後端] TextureMapper.apply_texture()
       │
       ├── 1. _perspective_warp()
       │    素材四角 → 目標多邊形四角
       │    cv2.getPerspectiveTransform()
       │    cv2.warpPerspective()
       │
       ├── 2. _feather_mask()    邊緣羽化
       │
       ├── 3. _blend("multiply")
       │    提取場景灰階亮度
       │    紋理 × (亮度 + 0.3) / 1.3
       │    → 保留原始陰影與立體感
       │
       └── 4. 合成 + 儲存結果
```

---

## 5. API 端點一覽

| Method | Path | 說明 |
|--------|------|------|
| GET | `/api/health` | 健康檢查 |
| POST | `/api/materials/upload` | 上傳素材 (multipart) |
| GET | `/api/materials` | 素材庫列表 |
| GET | `/api/materials/{id}` | 素材詳情 |
| DELETE | `/api/materials/{id}` | 刪除素材 |
| POST | `/api/spatial/upload` | 上傳空間照片 + 自動分割 |
| GET | `/api/spatial/{id}/segments` | 取得分割區塊 |
| POST | `/api/spatial/{id}/replace` | 替換單一區塊紋理 |
| POST | `/api/spatial/{id}/replace-batch` | 批次替換多區塊 |

---

## 6. 開發入門

```bash
# 後端
cd backend
pip install -r requirements.txt
# 下載 SAM 模型放入 models/
# wget https://dl.fbaipublicfiles.com/segment_anything/sam_vit_b_01ec64.pth
uvicorn app.main:app --reload --port 8000

# 前端
cd mobile
flutter pub add dio
# 將 api_client.dart 整合進專案
# 設定 baseUrl: http://<server-ip>:8000
```

---

## 7. 未來擴充

- **On-device 推論:** 將 MobileSAM 轉 ONNX，使用 `onnxruntime-mobile` 在手機端直接分割
- **AR 即時預覽:** 整合 ARKit/ARCore，透過相機即時預覽材質貼附效果
- **相似素材推薦:** 使用 pgvector 以圖搜圖
- **3D 場景重建:** 整合 NeRF 或 Gaussian Splatting 生成完整 3D 模型
