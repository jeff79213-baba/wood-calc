"""
建材模擬 HTML 產生工具
========================
用途：在你的電腦上處理照片 → 產生單一 HTML 檔案 → 寄給客戶

使用方式：
  1. 編輯 project_config.json（指定房間照片、區塊、素材）
  2. 把所有照片放到 tools/ 目錄下
  3. 執行：python generate_html.py
  4. 產出：output/王先生客廳.html（單一檔案，可直接寄出）

原理：所有圖片轉為 base64 內嵌在 HTML 中，
      客戶不需要連你的電腦，不需要上網，打開就能用。
"""
import json
import os
import sys
import base64
import cv2
import numpy as np
from pathlib import Path

# ─── 設定 ─────────────────────────────────────────────
TOOLS_DIR = Path(__file__).parent
OUTPUT_DIR = TOOLS_DIR / "output"
CONFIG_FILE = TOOLS_DIR / "project_config.json"

# ─── 核心函式 ─────────────────────────────────────────

def perspective_warp_texture(texture: np.ndarray, polygon: list, output_w: int, output_h: int) -> np.ndarray:
    """將素材紋理做透視變換，貼合到目標多邊形區域"""
    dst_pts = np.array(polygon, dtype=np.float32)

    if len(dst_pts) < 4:
        rect = cv2.boundingRect(dst_pts.reshape(-1, 2).astype(np.int32))
        dst_pts = np.array([
            [rect[0], rect[1]],
            [rect[0] + rect[2], rect[1]],
            [rect[0] + rect[2], rect[1] + rect[3]],
            [rect[0], rect[1] + rect[3]],
        ], dtype=np.float32)

    if len(dst_pts) > 4:
        rect = cv2.minAreaRect(dst_pts.reshape(-1, 2))
        dst_pts = cv2.boxPoints(rect)

    th, tw = texture.shape[:2]
    src_pts = np.array([
        [0, 0], [tw - 1, 0], [tw - 1, th - 1], [0, th - 1],
    ], dtype=np.float32)

    try:
        M = cv2.getPerspectiveTransform(src_pts, dst_pts)
        warped = cv2.warpPerspective(texture, M, (output_w, output_h))
    except cv2.error:
        warped = cv2.resize(texture, (output_w, output_h))

    return warped


def multiply_blend(scene: np.ndarray, texture_warped: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """保留原始場景光影的 multiply 混合"""
    scene_f = scene.astype(np.float32) / 255.0
    tex_f = texture_warped.astype(np.float32) / 255.0

    scene_gray = cv2.cvtColor(scene, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    lighting = cv2.cvtColor(scene_gray, cv2.COLOR_GRAY2BGR)

    blended = tex_f * (lighting * 0.7 + 0.3)
    blended = np.clip(blended, 0, 1) * 255

    mask_3ch = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR).astype(np.float32) / 255.0

    result = scene_f * 255 * (1 - mask_3ch) + blended * mask_3ch
    return np.clip(result, 0, 255).astype(np.uint8)


def create_region_mask(polygon: list, w: int, h: int, feather: int = 3) -> np.ndarray:
    """建立區塊遮罩（含邊緣羽化）"""
    mask = np.zeros((h, w), dtype=np.uint8)
    pts = np.array(polygon, dtype=np.int32).reshape((-1, 1, 2))
    cv2.fillPoly(mask, [pts], 255)

    if feather > 0:
        k = feather * 2 + 1
        mask = cv2.GaussianBlur(mask.astype(np.float32), (k, k), feather)
        mask = np.clip(mask, 0, 255).astype(np.uint8)

    return mask


def crop_to_region(image: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """將圖片非遮罩區域設為透明，保留區塊內內容"""
    result = cv2.cvtColor(image, cv2.COLOR_BGR2BGRA)
    result[:, :, 3] = mask
    return result


def img_to_base64(img: np.ndarray, fmt: str = ".jpg") -> str:
    """將 OpenCV 影像轉為 base64 字串"""
    if img.shape[2] == 4:
        fmt = ".png"
        success, buf = cv2.imencode(fmt, img)
    else:
        params = [cv2.IMWRITE_JPEG_QUALITY, 85]
        success, buf = cv2.imencode(fmt, img, params)

    if not success:
        return ""
    return base64.b64encode(buf.tobytes()).decode("utf-8")


def mime_type(fmt: str) -> str:
    return {"jpg": "image/jpeg", ".jpg": "image/jpeg", ".png": "image/png"}.get(fmt, "image/jpeg")


def load_image(path: str) -> np.ndarray:
    """載入圖片，支援中文路徑"""
    img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        print(f"  ❌ 無法載入圖片: {path}")
    return img


# ─── HTML 範本 ─────────────────────────────────────────

def generate_html(
    project_name: str,
    room_base64: str,
    regions_data: list,
    region_overlays: dict,
) -> str:
    """
    regions_data = [
        {"name": "電視牆", "materials": [{"name": "石材A", "id": "mat_0"}, ...]},
        ...
    ]
    region_overlays = {
        "電視牆": {
            "mat_0": "base64...",
            "mat_1": "base64...",
        },
        ...
    }
    """
    regions_json = json.dumps(regions_data, ensure_ascii=False)
    overlays_json = json.dumps(region_overlays, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.5, user-scalable=yes">
<title>{project_name} — 建材模擬</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }}
body {{ background:#1a1a1a; display:flex; flex-direction:column; align-items:center; min-height:100vh; }}
.header {{ width:100%; max-width:1000px; padding:15px 20px 10px; color:#fff; }}
.header h1 {{ font-size:20px; font-weight:700; }}
.header .hint {{ font-size:13px; color:#aaa; margin-top:3px; }}
.viewer {{ position:relative; width:100%; max-width:1000px; background:#000; border-radius:8px; overflow:hidden; }}
.viewer img {{ width:100%; display:block; }}
.overlay-layer {{ position:absolute; top:0; left:0; width:100%; height:100%; pointer-events:none; }}
.overlay-layer img {{ position:absolute; top:0; left:0; width:100%; height:100%; object-fit:contain; }}
.region-label {{ position:absolute; padding:4px 12px; background:rgba(0,0,0,0.65); color:#fff; font-size:13px; border-radius:4px; pointer-events:none; white-space:nowrap; font-weight:600; }}
.panel {{ width:100%; max-width:1000px; padding:15px 0 30px; }}
.panel-tabs {{ display:flex; gap:8px; flex-wrap:wrap; margin-bottom:12px; }}
.tab {{ padding:8px 18px; border-radius:20px; border:none; font-size:14px; font-weight:600; cursor:pointer; background:#333; color:#aaa; transition:all .2s; }}
.tab.active {{ background:#ff6b00; color:#fff; }}
.tab:hover:not(.active) {{ background:#444; color:#ddd; }}
.mat-grid {{ display:grid; grid-template-columns:repeat(auto-fill, minmax(100px, 1fr)); gap:10px; }}
.mat-card {{ background:#2a2a2a; border-radius:8px; overflow:hidden; cursor:pointer; border:2px solid transparent; transition:all .2s; }}
.mat-card:hover {{ border-color:#ff6b00; transform:translateY(-2px); }}
.mat-card.active {{ border-color:#ff6b00; box-shadow:0 0 12px rgba(255,107,0,0.4); }}
.mat-card img {{ width:100%; aspect-ratio:1/1; object-fit:cover; display:block; }}
.mat-card .name {{ padding:6px 8px; font-size:12px; color:#ccc; text-align:center; }}
.footer {{ padding:10px 20px 20px; color:#666; font-size:12px; text-align:center; max-width:1000px; }}
@media (max-width:600px) {{ .mat-grid {{ grid-template-columns:repeat(auto-fill, minmax(75px, 1fr)); }} .mat-card .name {{ font-size:11px; }} }}
</style>
</head>
<body>
<div class="header">
  <h1>🏠 {project_name}</h1>
  <div class="hint">點選下方區塊標籤，再選擇您想要的建材樣式</div>
</div>

<div class="viewer" id="viewer">
  <img id="base-img" src="data:image/jpeg;base64,{room_base64}" alt="原始場景">
  <div class="overlay-layer" id="overlay-layer">
  </div>
</div>

<div class="panel" id="panel">
  <div class="panel-tabs" id="tabs"></div>
  <div class="mat-grid" id="mat-grid"></div>
</div>

<div class="footer">此模擬由電腦生成，實際效果以現場施工為準</div>

<script>
const regions = {regions_json};
const overlays = {overlays_json};

let activeRegion = regions.length > 0 ? regions[0].name : null;
let activeMats = {{}};

function init() {{
  // 建立 overlay 圖層容器
  const layer = document.getElementById('overlay-layer');
  regions.forEach(r => {{
    r.materials.forEach(m => {{
      const img = document.createElement('img');
      img.id = 'overlay-' + m.id;
      img.style.display = 'none';
      img.src = 'data:image/png;base64,' + (overlays[r.name]?.[m.id] || '');
      layer.appendChild(img);
    }});
  }});

  // 建立分頁
  const tabs = document.getElementById('tabs');
  regions.forEach((r, i) => {{
    const btn = document.createElement('button');
    btn.className = 'tab' + (i === 0 ? ' active' : '');
    btn.textContent = r.name;
    btn.onclick = () => switchRegion(r.name);
    btn.id = 'tab-' + r.name;
    tabs.appendChild(btn);
  }});

  // 顯示第一個區域的素材
  if (regions.length > 0) renderMaterials(regions[0]);
}}

function switchRegion(name) {{
  activeRegion = name;
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  const region = regions.find(r => r.name === name);
  if (region) renderMaterials(region);
}}

function renderMaterials(region) {{
  const grid = document.getElementById('mat-grid');
  grid.innerHTML = '';
  region.materials.forEach(m => {{
    const card = document.createElement('div');
    card.className = 'mat-card' + (activeMats[region.name] === m.id ? ' active' : '');
    card.onclick = () => selectMaterial(region.name, m.id);
    const imgSrc = overlays[region.name]?.[m.id] || '';
    card.innerHTML = '<img src="data:image/png;base64,' + imgSrc + '"><div class="name">' + m.name + '</div>';
    grid.appendChild(card);
  }});
}}

function selectMaterial(regionName, matId) {{
  activeMats[regionName] = matId;

  // 隱藏所有該區的 overlay
  const region = regions.find(r => r.name === regionName);
  region.materials.forEach(m => {{
    const img = document.getElementById('overlay-' + m.id);
    if (img) img.style.display = 'none';
  }});

  // 顯示選中的
  const selected = document.getElementById('overlay-' + matId);
  if (selected) selected.style.display = 'block';

  // 更新卡片樣式
  document.querySelectorAll('.mat-card').forEach(c => c.classList.remove('active'));
  renderMaterials(region);
}}

window.onload = init;
</script>
</body>
</html>"""


# ─── 主流程 ─────────────────────────────────────────

def main():
    print("=" * 55)
    print("  建材模擬 HTML 產生工具")
    print("  Interior Material Swap — HTML Generator")
    print("=" * 55)

    # 1. 讀取設定
    if not CONFIG_FILE.exists():
        print(f"\n❌ 找不到設定檔: {CONFIG_FILE}")
        print("   請先編輯 tools/project_config.json")
        sys.exit(1)

    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)

    project_name = config.get("project_name", "未命名專案")
    room_path = TOOLS_DIR / config["room_photo"]
    regions = config["regions"]

    print(f"\n📋 專案: {project_name}")
    print(f"   區塊數: {len(regions)}")

    # 2. 載入房間照片
    print(f"\n📷 載入房間照片: {room_path.name}")
    room = load_image(str(room_path))
    if room is None:
        sys.exit(1)

    h, w = room.shape[:2]
    print(f"   尺寸: {w} x {h}")

    # 3. 處理每個區塊 + 素材
    OUTPUT_DIR.mkdir(exist_ok=True)

    all_materials = []
    region_overlays = {}
    total = sum(len(r["materials"]) for r in regions)
    count = 0

    for ri, region in enumerate(regions):
        rname = region["name"]
        polygon = region["polygon"]
        mats = region["materials"]

        print(f"\n📍 區塊 [{ri+1}/{len(regions)}]: {rname}")
        print(f"   素材數量: {len(mats)}")

        mask = create_region_mask(polygon, w, h)

        region_overlays[rname] = {}
        region_mats = []

        for mi, mat in enumerate(mats):
            count += 1
            mname = mat["name"]
            mat_path = TOOLS_DIR / mat["image"]
            mat_id = f"r{ri}_m{mi}"

            print(f"   [{count}/{total}] {mname}...", end="", flush=True)

            region_mats.append({"name": mname, "id": mat_id})

            mat_img = load_image(str(mat_path))
            if mat_img is None:
                print(" ⏭ 略過")
                continue

            warped = perspective_warp_texture(mat_img, polygon, w, h)
            blended = multiply_blend(room, warped, mask)
            overlay_img = crop_to_region(blended, mask)

            b64 = img_to_base64(overlay_img)
            region_overlays[rname][mat_id] = b64

            print(f" ✅")

        all_materials.append({
            "name": rname,
            "materials": region_mats,
        })

    # 4. 房間照片轉 base64
    print(f"\n🔄 編碼房間照片...", end="", flush=True)
    room_b64 = img_to_base64(room)
    print(" ✅")

    # 5. 產生 HTML
    print(f"📄 產生 HTML...", end="", flush=True)
    html = generate_html(project_name, room_b64, all_materials, region_overlays)

    safe_name = project_name.replace(" ", "_").replace("/", "_")
    output_path = OUTPUT_DIR / f"{safe_name}.html"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(" ✅")

    # 6. 統計
    total_size = output_path.stat().st_size
    filesize_mb = total_size / (1024 * 1024)
    print(f"\n{'=' * 55}")
    print(f"  ✅ 完成！產出檔案:")
    print(f"     {output_path}")
    print(f"     檔案大小: {filesize_mb:.1f} MB")
    print(f"     可直接寄送或透過 LINE/WhatsApp 傳送")
    print(f"{'=' * 55}")


if __name__ == "__main__":
    main()
