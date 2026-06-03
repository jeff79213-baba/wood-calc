"""
互動替換與紋理貼圖核心演算法
- 透視變換 (Homography) 將素材貼合至目標區塊
- 光影混合 (Multiply Blend / Shadow Retention)
- 邊緣羽化融合
"""
import cv2
import numpy as np
from typing import List, Tuple, Optional


class TextureMapper:
    def __init__(self):
        pass

    def apply_texture(
        self,
        scene: np.ndarray,
        texture: np.ndarray,
        mask: np.ndarray,
        polygon: List[List[float]],
        blend_mode: str = "multiply",
        feather_radius: int = 5,
    ) -> np.ndarray:
        """
        核心紋理貼圖功能

        Args:
            scene: 原始空間照片 (BGR)
            texture: 素材紋理 (BGR)
            mask: 二值遮罩 (HxW, uint8)
            polygon: 區塊多邊形輪廓點
            blend_mode: 混合模式 (multiply / overlay / normal)
            feather_radius: 邊緣羽化半徑

        Returns:
            合成後的影像 (BGR)
        """
        result = scene.copy()
        h, w = scene.shape[:2]

        if len(polygon) < 3:
            return result

        poly_pts = np.array(polygon, dtype=np.int32).reshape((-1, 1, 2))

        # 1. 計算透視變換矩陣
        M, mapped_texture = self._perspective_warp(texture, poly_pts, w, h)

        if mapped_texture is None:
            mapped_texture = self._fallback_fill(texture, poly_pts, w, h)

        # 2. 確保遮罩與 mapped_texture 一致
        mask_binary = (mask > 0).astype(np.uint8) * 255

        # 3. 邊緣羽化
        if feather_radius > 0:
            mask_binary = self._feather_mask(mask_binary, feather_radius)

        # 4. 光影保留混合
        blended = self._blend(scene, mapped_texture, mask_binary, blend_mode)

        # 5. 合成
        mask_3ch = cv2.cvtColor(mask_binary, cv2.COLOR_GRAY2BGR) / 255.0
        result = (result * (1 - mask_3ch) + blended * mask_3ch).astype(np.uint8)

        return result

    def _perspective_warp(
        self,
        texture: np.ndarray,
        dst_poly: np.ndarray,
        output_w: int,
        output_h: int,
    ) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """計算素材到目標多邊形的透視變換"""
        dst_pts = dst_poly.reshape(-1, 2).astype(np.float32)

        if len(dst_pts) < 4:
            return None, None

        if len(dst_pts) > 4:
            # 使用最小外接矩形取4個角點
            rect = cv2.minAreaRect(dst_pts)
            dst_pts = cv2.boxPoints(rect)

        # 對應的素材四角
        th, tw = texture.shape[:2]
        src_pts = np.array([
            [0, 0],
            [tw - 1, 0],
            [tw - 1, th - 1],
            [0, th - 1],
        ], dtype=np.float32)

        try:
            M = cv2.getPerspectiveTransform(src_pts, dst_pts)
            warped = cv2.warpPerspective(texture, M, (output_w, output_h))
            return M, warped
        except cv2.error:
            return None, None

    def _fallback_fill(
        self,
        texture: np.ndarray,
        dst_poly: np.ndarray,
        output_w: int,
        output_h: int,
    ) -> np.ndarray:
        """當透視變換失敗時的備援方案：使用遮罩填充"""
        mask_fill = np.zeros((output_h, output_w), dtype=np.uint8)
        cv2.fillPoly(mask_fill, [dst_poly], 255)

        texture_resized = cv2.resize(texture, (output_w, output_h))
        result = np.zeros((output_h, output_w, 3), dtype=np.uint8)
        result[mask_fill > 0] = texture_resized[mask_fill > 0]
        return result

    def _feather_mask(self, mask: np.ndarray, radius: int) -> np.ndarray:
        """邊緣羽化，使貼圖邊界更自然"""
        if radius < 1:
            return mask
        kernel_size = radius * 2 + 1
        blurred = cv2.GaussianBlur(mask.astype(np.float32), (kernel_size, kernel_size), radius)
        return blurred

    def _blend(
        self,
        scene: np.ndarray,
        texture_warped: np.ndarray,
        mask: np.ndarray,
        mode: str = "multiply",
    ) -> np.ndarray:
        """
        光影保留混合

        multiply: 保留原始場景的明暗變化，適合保留陰影
        overlay: 增加對比度
        normal: 直接覆蓋
        """
        scene_f = scene.astype(np.float32)
        tex_f = texture_warped.astype(np.float32)
        mask_3ch = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
        m = mask_3ch / 255.0

        if mode == "multiply":
            # 提取場景的亮度資訊
            scene_gray = cv2.cvtColor(scene, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
            lighting = cv2.cvtColor(scene_gray, cv2.COLOR_GRAY2BGR)

            # 紋理 * 亮度 = 保留陰影
            base = (tex_f / 255.0) * (lighting + 0.3) / 1.3
            blended = (base * 255).astype(np.float32)

        elif mode == "overlay":
            scene_norm = scene_f / 255.0
            tex_norm = tex_f / 255.0

            mask_condition = scene_norm < 0.5
            blended = np.where(
                mask_condition,
                2 * scene_norm * tex_norm,
                1 - 2 * (1 - scene_norm) * (1 - tex_norm),
            )
            blended = blended * 255

        else:  # normal
            blended = tex_f

        # 只在遮罩區域內混和
        result = scene_f * (1 - m) + blended * m
        result = np.clip(result, 0, 255)

        return result.astype(np.uint8)

    def batch_replace(
        self,
        scene: np.ndarray,
        replacements: List[dict],
    ) -> np.ndarray:
        """
        批次替換多個區塊

        replacements: [
            {
                "texture": np.ndarray,
                "mask": np.ndarray,
                "polygon": List[List[float]],
                "blend_mode": str,
            },
            ...
        ]
        """
        result = scene.copy()
        for r in replacements:
            result = self.apply_texture(
                scene=result,
                texture=r["texture"],
                mask=r["mask"],
                polygon=r["polygon"],
                blend_mode=r.get("blend_mode", "multiply"),
                feather_radius=r.get("feather_radius", 5),
            )
        return result
