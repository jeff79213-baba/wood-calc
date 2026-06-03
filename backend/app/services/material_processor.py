"""
素材影像處理服務
- 自動裁切與去透視校正
- 紋理特徵提取 (ResNet embedding)
- 主色調分析
"""
import cv2
import numpy as np
from PIL import Image
from typing import Optional, Tuple, List


class MaterialProcessor:
    def __init__(self):
        self._feature_extractor = None

    def _load_feature_extractor(self):
        if self._feature_extractor is None:
            import torch
            import torchvision.models as models
            model = models.resnet18(weights=models.ResNet18_Weights.IMAGENET1K_V1)
            self._feature_extractor = torch.nn.Sequential(*list(model.children())[:-1])
            self._feature_extractor.eval()
        return self._feature_extractor

    def detect_and_crop(self, image: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edged = cv2.Canny(blurred, 30, 150)

        contours, _ = cv2.findContours(edged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return image

        largest = max(contours, key=cv2.contourArea)
        x, y, w, h = cv2.boundingRect(largest)
        return image[y:y + h, x:x + w]

    def correct_perspective(self, image: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edged = cv2.Canny(blurred, 30, 150)

        contours, _ = cv2.findContours(edged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return image

        largest = max(contours, key=cv2.contourArea)
        peri = cv2.arcLength(largest, True)
        approx = cv2.approxPolyDP(largest, 0.02 * peri, True)

        if len(approx) != 4:
            return image

        pts = np.array([p[0] for p in approx], dtype=np.float32)
        rect = self._order_points(pts)

        (tl, tr, br, bl) = rect
        width_a = np.linalg.norm(br - bl)
        width_b = np.linalg.norm(tr - tl)
        max_width = max(int(width_a), int(width_b))

        height_a = np.linalg.norm(tr - br)
        height_b = np.linalg.norm(tl - bl)
        max_height = max(int(height_a), int(height_b))

        dst = np.array([
            [0, 0],
            [max_width - 1, 0],
            [max_width - 1, max_height - 1],
            [0, max_height - 1],
        ], dtype=np.float32)

        M = cv2.getPerspectiveTransform(rect, dst)
        warped = cv2.warpPerspective(image, M, (max_width, max_height))
        return warped

    def _order_points(self, pts: np.ndarray) -> np.ndarray:
        rect = np.zeros((4, 2), dtype=np.float32)
        s = pts.sum(axis=1)
        rect[0] = pts[np.argmin(s)]
        rect[2] = pts[np.argmax(s)]
        diff = np.diff(pts, axis=1)
        rect[1] = pts[np.argmin(diff)]
        rect[3] = pts[np.argmax(diff)]
        return rect

    def make_seamless(self, image: np.ndarray) -> np.ndarray:
        h, w = image.shape[:2]
        if h < 32 or w < 32:
            return image
        src = cv2.copyMakeBorder(image, 0, 0, 0, 0, cv2.BORDER_REPLICATE)
        try:
            dst = cv2.resize(src, (w // 2, h // 2))
            return dst
        except Exception:
            return image

    def extract_dominant_colors(self, image: np.ndarray, k: int = 5) -> List[List[int]]:
        pixels = image.reshape(-1, 3)
        pixels = np.float32(pixels)
        _, labels, centers = cv2.kmeans(
            pixels, k, None,
            (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0),
            10, cv2.KMEANS_RANDOM_CENTERS
        )
        counts = np.bincount(labels.flatten())
        sorted_indices = np.argsort(counts)[::-1]
        return [centers[i].astype(int).tolist() for i in sorted_indices]

    def extract_feature(self, image: np.ndarray) -> np.ndarray:
        import torch
        from torchvision import transforms
        model = self._load_feature_extractor()

        transform = transforms.Compose([
            transforms.ToPILImage(),
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ])

        tensor = transform(image).unsqueeze(0)
        with torch.no_grad():
            feature = model(tensor).squeeze().numpy()
        return feature / (np.linalg.norm(feature) + 1e-8)

    def process(self, image: np.ndarray) -> dict:
        cropped = self.detect_and_crop(image)
        perspective_corrected = self.correct_perspective(cropped)
        texture = self.make_seamless(perspective_corrected)
        colors = self.extract_dominant_colors(perspective_corrected)
        feature = self.extract_feature(perspective_corrected)

        return {
            "texture": texture,
            "thumbnail": cv2.resize(perspective_corrected, (256, 256)),
            "dominant_colors": colors,
            "feature_vector": feature.tolist(),
        }
