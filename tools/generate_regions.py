"""
區塊多邊形產出輔助工具
========================
如果你不想手動在 JSON 裡填座標，用這個工具幫你自動偵測。

使用方式：
  1. 把房間照片放到 tools/ 目錄
  2. 執行：python generate_regions.py room.jpg
  3. 它會顯示 SAM 自動分割的區塊 + 圖片標記
  4. 產出 regions_output.json，貼到 project_config.json 使用

進階方式（半自動）：
  python generate_regions.py room.jpg --labels 牆面,地板,天花板
  它會找面積最大的三個區塊，依序對應標籤
"""
import sys
import json
import cv2
import numpy as np
from pathlib import Path

TOOLS_DIR = Path(__file__).parent


def simplify_polygon(contour, epsilon_factor: float = 0.008) -> list:
    """簡化多邊形輪廓，減少點數"""
    peri = cv2.arcLength(contour, True)
    epsilon = peri * epsilon_factor
    approx = cv2.approxPolyDP(contour, epsilon, True)
    return approx.reshape(-1, 2).tolist()


def filter_structural_segments(segments, img_w, img_h):
    """
    過濾掉家具/物品，只保留結構性區塊（牆面、地板、天花板）

    過濾條件：
    1. 面積太小 (< 5%) → 跳過（桌、椅、燈具）
    2. 不碰觸邊緣且面積 < 15% → 跳過（牆面/地板通常延伸到邊緣）
    3. 完全被另一個區塊包住 → 跳過（桌上的物品）
    """
    total = img_w * img_h
    candidates = []

    for seg in segments:
        pts = np.array(seg["polygon"])
        area = seg["area"]
        ratio = area / total
        if ratio < 0.04 or len(pts) < 3:
            continue

        xs = pts[:, 0]
        ys = pts[:, 1]
        cx, cy = xs.mean(), ys.mean()

        touches = {
            "top": ys.min() <= 8,
            "bottom": ys.max() >= img_h - 8,
            "left": xs.min() <= 8,
            "right": xs.max() >= img_w - 8,
        }
        touches_count = sum(touches.values())

        # 判斷區塊輪廓的方正程度
        try:
            rect = cv2.minAreaRect(pts.astype(np.float32))
            box = cv2.boxPoints(rect)
            rect_a = cv2.contourArea(box)
            regularity = area / rect_a if rect_a > 0 else 0
        except Exception:
            regularity = 0

        # ✅ 保留條件
        keep = False
        if ratio > 0.25:
            keep = True  # 超大區塊，直接保留
        elif touches_count >= 2 and ratio > 0.05:
            keep = True  # 碰觸多邊緣 + 夠大 → 牆面/地板
        elif touches_count >= 1 and ratio > 0.10:
            keep = True  # 碰觸單邊 + 很大 → 可能是天花板
        elif regularity > 0.55 and ratio > 0.12:
            keep = True  # 很方正 → 可能是牆面

        if keep:
            # 根據位置建議命名
            y_ratio = cy / img_h
            if y_ratio > 0.75 and touches.get("bottom"):
                label = "地板"
            elif y_ratio < 0.25 and touches.get("top"):
                label = "天花板"
            elif touches.get("left") and not touches.get("right"):
                label = "左牆"
            elif touches.get("right") and not touches.get("left"):
                label = "右牆"
            elif touches_count >= 2:
                label = "主牆"
            else:
                label = "牆面"

            seg["_label"] = label
            seg["_y_ratio"] = y_ratio
            seg["_cx"], seg["_cy"] = int(cx), int(cy)
            candidates.append(seg)

    # 移除互相重疊的區塊（保留大的、去掉小的）
    final = []
    for seg_a in sorted(candidates, key=lambda s: -s["area"]):
        a_pts = np.array(seg_a["polygon"])
        a_mask = np.zeros((img_h, img_w), dtype=np.uint8)
        cv2.fillPoly(a_mask, [a_pts.astype(np.int32).reshape((-1, 1, 2))], 1)

        overlapping = False
        for seg_b in final:
            b_pts = np.array(seg_b["polygon"])
            # 檢查 centroid 是否在另一個區塊內
            cx_b, cy_b = int(seg_b["_cx"]), int(seg_b["_cy"])
            if cv2.pointPolygonTest(b_pts.astype(np.float32), (float(seg_a["_cx"]), float(seg_a["_cy"])), False) >= 0:
                overlapping = True
                break
            if cv2.pointPolygonTest(a_pts.astype(np.float32), (float(cx_b), float(cy_b)), False) >= 0:
                overlapping = True
                break

        if not overlapping:
            final.append(seg_a)

    # 避免同類型重複（最多 2 個牆面、1 個地板、1 個天花板）
    type_count = {}
    result = []
    for seg in final:
        lbl = seg["_label"]
        max_count = 2 if "牆" in lbl else 1
        if type_count.get(lbl, 0) < max_count:
            type_count[lbl] = type_count.get(lbl, 0) + 1
            result.append(seg)

    # 依位置排序（上 → 下）：天花板 → 牆面 → 地板
    pos_order = {"天花板": 0, "左牆": 1, "主牆": 2, "右牆": 3, "牆面": 4, "地板": 5}
    result.sort(key=lambda s: (pos_order.get(s["_label"], 9), s["_y_ratio"]))
    return result


def detect_regions_from_image(image_path: str) -> list:
    """
    從圖片路徑偵測區塊，回傳 list of dict:
    [{"name": str, "polygon": [[x,y], ...], "area": int, "confidence": float}]
    自動縮小大圖加速處理，座標會對應回原始尺寸。
    """
    img = cv2.imdecode(np.fromfile(image_path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"無法載入圖片: {image_path}")

    h, w = img.shape[:2]

    # ── 縮小大圖加速（限制最長邊 800px）──
    max_dim = 800
    scale = 1.0
    if w > max_dim or h > max_dim:
        scale = max_dim / max(w, h)
        new_w = int(w * scale)
        new_h = int(h * scale)
        img_small = cv2.resize(img, (new_w, new_h))
    else:
        img_small = img

    sh, sw = img_small.shape[:2]

    sam_checkpoint = Path(__file__).parent.parent / "backend" / "models" / "sam_vit_b_01ec64.pth"
    segments_data = []
    sam_available = False

    if sam_checkpoint.exists():
        try:
            sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
            from app.services.segmentation import SegmentationService

            svc = SegmentationService(model_type="vit_b", checkpoint=str(sam_checkpoint), device="cpu")
            results = svc.segment_automatic(img_small)

            for i, seg in enumerate(results):
                polygon = simplify_polygon(np.array(seg.polygon, dtype=np.int32))
                if len(polygon) >= 3:
                    # 座標還原回原始尺寸
                    if scale != 1.0:
                        polygon = [[int(x / scale), int(y / scale)] for x, y in polygon]
                    segments_data.append({
                        "index": i,
                        "polygon": polygon,
                        "area": int(cv2.contourArea(np.array(polygon, dtype=np.int32))),
                        "confidence": round(seg.confidence, 3),
                    })
            sam_available = True
        except Exception:
            pass

    if not sam_available:
        # 使用 K-means 色彩分群：牆面、地板、天花板通常顏色不同
        pixels = img_small.reshape(-1, 3).astype(np.float32)
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
        k = max(5, min(8, sw * sh // 50000))
        _, labels, _ = cv2.kmeans(pixels, k, None, criteria, 10, cv2.KMEANS_RANDOM_CENTERS)

        for i in range(k):
            mask = (labels == i).reshape(sh, sw).astype(np.uint8) * 255
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))

            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for c in contours:
                polygon = simplify_polygon(c)
                area = cv2.contourArea(c)
                min_area = (sw * sh) * 0.03
                if area > min_area and len(polygon) >= 3:
                    if scale != 1.0:
                        polygon = [[int(x / scale), int(y / scale)] for x, y in polygon]
                    segments_data.append({
                        "index": len(segments_data),
                        "polygon": polygon,
                        "area": int(cv2.contourArea(np.array(polygon, dtype=np.int32))),
                        "confidence": 0.5,
                    })

    # ── 過濾家具雜物，只留結構區塊 ──
    filtered = filter_structural_segments(segments_data, w, h)
    if filtered:
        return filtered

    # 如果過濾後沒東西，退回原始結果（至少讓用戶有東西可以點）
    segments_data.sort(key=lambda s: s["area"], reverse=True)
    return segments_data[:5]


def main():
    if len(sys.argv) < 2:
        print("用法: python generate_regions.py <房間照片> [--labels 牆面,地板,天花板]")
        sys.exit(1)

    image_path = TOOLS_DIR / sys.argv[1]
    if not image_path.exists():
        print(f"❌ 找不到圖片: {image_path}")
        sys.exit(1)

    labels = None
    if "--labels" in sys.argv:
        idx = sys.argv.index("--labels")
        if idx + 1 < len(sys.argv):
            labels = [l.strip() for l in sys.argv[idx + 1].split(",")]

    print(f"📷 載入圖片: {image_path.name}")
    img = cv2.imdecode(np.fromfile(str(image_path), dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        print("❌ 無法載入")
        sys.exit(1)

    h, w = img.shape[:2]
    print(f"   尺寸: {w} x {h}")

    print("🔍 偵測區塊中...")
    segments_data = detect_regions_from_image(str(image_path))

    if not segments_data:
        print("❌ 沒有找到任何區塊")
        sys.exit(1)

    print(f"\n📊 找到 {len(segments_data)} 個區塊（依面積排序）:")

    # 生成標記圖片
    vis = img.copy()
    colors = [
        (255, 0, 0), (0, 255, 0), (0, 0, 255),
        (255, 255, 0), (255, 0, 255), (0, 255, 255),
        (128, 0, 0), (0, 128, 0), (0, 0, 128),
    ]

    output_regions = []

    for i, seg in enumerate(segments_data):
        color = colors[i % len(colors)]
        pts = np.array(seg["polygon"], dtype=np.int32).reshape((-1, 1, 2))
        cv2.polylines(vis, [pts], True, color, 3)

        # 標記編號
        cx = int(np.mean([p[0] for p in seg["polygon"]]))
        cy = int(np.mean([p[1] for p in seg["polygon"]]))
        label_str = str(i)
        if labels and i < len(labels):
            label_str = f"{i}: {labels[i]}"
        cv2.putText(vis, label_str, (cx - 20, cy + 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)

        seg_label = labels[i] if labels and i < len(labels) else f"區塊{i}"
        output_regions.append({
            "name": seg_label,
            "polygon": seg["polygon"],
        })

        area_ping = seg["area"] / 32400  # 粗略估算坪數
        print(f"   [{i}] {seg_label} | 面積: {seg['area']:>6} px (~{area_ping:.1f} 坪) | 信心: {seg.get('confidence', '-')}")

    # 儲存標記圖
    vis_path = TOOLS_DIR / f"regions_{Path(sys.argv[1]).stem}.jpg"
    cv2.imencode(".jpg", vis, [cv2.IMWRITE_JPEG_QUALITY, 90])[1].tofile(str(vis_path))
    print(f"\n🖼️  標記圖已儲存: {vis_path.name}（打開確認區塊編號是否正確）")

    # 輸出 JSON
    if not labels:
        print(f"\n💡 區塊已自動命名為 區塊0, 區塊1, ...")
        print(f"   開啟 {vis_path.name} 確認每個編號對應到正確的位置")
        print(f"   然後在 project_config.json 中填入素材路徑")

    output = {
        "project_name": Path(sys.argv[1]).stem,
        "room_photo": sys.argv[1],
        "regions": output_regions,
    }

    output_path = TOOLS_DIR / f"regions_{Path(sys.argv[1]).stem}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n📄 設定檔已產出: {output_path.name}")
    print(f"   可直接取代 project_config.json 的內容")
    print(f"\n👉 下一步：編輯 project_config.json，為每個區塊指定素材圖片")


if __name__ == "__main__":
    main()
