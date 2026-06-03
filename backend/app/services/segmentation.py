"""
空間辨識與語意分割服務
- 使用 SAM (Segment Anything Model) 進行區域分割
- 生成區塊遮罩 (Mask) 與多邊形輪廓
- 可選配光源方向估計
"""
import cv2
import numpy as np
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass


@dataclass
class SegmentResult:
    label: str
    confidence: float
    mask: np.ndarray
    polygon: List[List[float]]
    bounding_box: List[float]


class SegmentationService:
    def __init__(self, model_type: str = "vit_b", checkpoint: str = None, device: str = "cpu"):
        self.model_type = model_type
        self.checkpoint = checkpoint
        self.device = device
        self._sam = None
        self._predictor = None

    def _load_model(self):
        if self._predictor is not None:
            return self._predictor

        import torch
        from segment_anything import sam_model_registry, SamPredictor

        sam = sam_model_registry[self.model_type](checkpoint=self.checkpoint)
        sam.to(device=self.device)
        self._predictor = SamPredictor(sam)
        return self._predictor

    def _load_automatic(self):
        if self._sam is not None:
            return self._sam

        import torch
        from segment_anything import sam_model_registry, SamAutomaticMaskGenerator

        sam = sam_model_registry[self.model_type](checkpoint=self.checkpoint)
        sam.to(device=self.device)
        self._sam = SamAutomaticMaskGenerator(
            model=sam,
            points_per_side=32,
            pred_iou_thresh=0.7,
            stability_score_thresh=0.85,
            crop_n_layers=1,
            crop_n_points_downscale_factor=2,
            min_mask_region_area=2000,
        )
        return self._sam

    def segment_automatic(self, image: np.ndarray) -> List[SegmentResult]:
        mask_generator = self._load_automatic()
        results = []

        if image.shape[0] > 1024 or image.shape[1] > 1024:
            scale = 1024 / max(image.shape[0], image.shape[1])
            new_w = int(image.shape[1] * scale)
            new_h = int(image.shape[0] * scale)
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            image_rgb = cv2.resize(image_rgb, (new_w, new_h))
        else:
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

        masks = mask_generator.generate(image_rgb)

        for i, m in enumerate(masks):
            mask = m["segmentation"]
            contours, _ = cv2.findContours(
                mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )

            polygon = []
            if contours:
                largest = max(contours, key=cv2.contourArea)
                epsilon = 0.005 * cv2.arcLength(largest, True)
                approx = cv2.approxPolyDP(largest, epsilon, True)
                polygon = approx.reshape(-1, 2).tolist()

            bbox = m["bbox"]
            bx, by, bw, bh = bbox

            results.append(SegmentResult(
                label=f"segment_{i}",
                confidence=float(m.get("predicted_iou", 0.0)),
                mask=mask,
                polygon=polygon,
                bounding_box=[float(bx), float(by), float(bw), float(bh)],
            ))

        results.sort(key=lambda r: r.confidence, reverse=True)
        return results

    def segment_with_points(
        self, image: np.ndarray, points: List[Tuple[float, float]], labels: List[int]
    ) -> List[SegmentResult]:
        predictor = self._load_model()

        if image.shape[0] > 1024 or image.shape[1] > 1024:
            scale = 1024 / max(image.shape[0], image.shape[1])
            new_w = int(image.shape[1] * scale)
            new_h = int(image.shape[0] * scale)
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            image_rgb = cv2.resize(image_rgb, (new_w, new_h))
            points = [(p[0] * scale, p[1] * scale) for p in points]
        else:
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

        predictor.set_image(image_rgb)

        point_coords = np.array(points, dtype=np.float32)
        point_labels = np.array(labels, dtype=np.int32)

        masks, scores, logits = predictor.predict(
            point_coords=point_coords,
            point_labels=point_labels,
            multimask_output=True,
        )

        results = []
        for i in range(masks.shape[0]):
            mask = masks[i]
            contours, _ = cv2.findContours(
                mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            polygon = []
            if contours:
                largest = max(contours, key=cv2.contourArea)
                epsilon = 0.005 * cv2.arcLength(largest, True)
                approx = cv2.approxPolyDP(largest, epsilon, True)
                polygon = approx.reshape(-1, 2).tolist()

            ys, xs = np.where(mask)
            if len(xs) > 0 and len(ys) > 0:
                bbox = [float(xs.min()), float(ys.min()), float(xs.max() - xs.min()), float(ys.max() - ys.min())]
            else:
                bbox = [0, 0, 0, 0]

            results.append(SegmentResult(
                label=f"point_segment_{i}",
                confidence=float(scores[i]),
                mask=mask,
                polygon=polygon,
                bounding_box=bbox,
            ))

        return results

    def estimate_lighting(self, image: np.ndarray, segments: List[SegmentResult]) -> Dict:
        """估算主要光源方向（選配進階功能）"""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        sobel_x = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=5)
        sobel_y = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=5)

        magnitude = np.sqrt(sobel_x ** 2 + sobel_y ** 2)
        direction = np.arctan2(sobel_y, sobel_x)

        # Weight by magnitude
        avg_dx = np.mean(sobel_x * magnitude) / (np.mean(magnitude) + 1e-6)
        avg_dy = np.mean(sobel_y * magnitude) / (np.mean(magnitude) + 1e-6)

        light_angle = np.arctan2(avg_dy, avg_dx)
        light_strength = np.mean(magnitude)

        return {
            "angle_deg": float(np.degrees(light_angle)),
            "strength": float(light_strength),
            "direction_vector": [float(avg_dx), float(avg_dy)],
        }

    def refine_mask_edges(self, mask: np.ndarray, edge_smoothing: int = 3) -> np.ndarray:
        """邊緣平滑處理"""
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (edge_smoothing, edge_smoothing))
        smoothed = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_CLOSE, kernel)
        smoothed = cv2.morphologyEx(smoothed, cv2.MORPH_OPEN, kernel)
        return smoothed
