"""
空間辨識與紋理替換 API
POST /api/spatial/upload       - 上傳空間照片並執行分割
GET  /api/spatial/{id}/segments - 取得分割區塊列表
POST /api/spatial/{id}/replace  - 對指定區塊執行紋理替換
"""
import os
import uuid
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Form, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db import get_session
from app.models.material import Project, Segment, Material, Replacement
from app.services.segmentation import SegmentationService
from app.services.texture_mapping import TextureMapper
from app.config import settings

router = APIRouter(prefix="/api/spatial", tags=["spatial"])

seg_service = SegmentationService(
    model_type=settings.sam_model_type,
    checkpoint=settings.sam_checkpoint,
    device=settings.device,
)
tex_mapper = TextureMapper()

import cv2
import numpy as np


@router.post("/upload", status_code=201)
async def upload_room(
    file: UploadFile = File(...),
    name: str = Form("未命名專案"),
    room_type: str = Form(None),
    user_id: str = Form("default"),
    session: AsyncSession = Depends(get_session),
):
    ext = os.path.splitext(file.filename)[1] or ".jpg"
    filename = f"{uuid.uuid4()}{ext}"
    filepath = os.path.join(settings.upload_dir_rooms, filename)

    contents = await file.read()
    with open(filepath, "wb") as f:
        f.write(contents)

    img_array = np.frombuffer(contents, np.uint8)
    image = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

    if image is None:
        raise HTTPException(status_code=400, detail="無法解碼圖片")

    h, w = image.shape[:2]

    project = Project(
        user_id=user_id,
        name=name,
        room_type=room_type,
        original_photo=filepath,
        image_width=w,
        image_height=h,
    )
    session.add(project)
    await session.flush()

    try:
        segments = seg_service.segment_automatic(image)
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=f"分割失敗: {str(e)}")

    created_segments = []
    for i, seg in enumerate(segments[:20]):
        db_segment = Segment(
            project_id=project.id,
            label=seg.label,
            confidence=seg.confidence,
            mask_polygon=seg.polygon,
            bounding_box=seg.bounding_box,
            sort_order=i,
        )
        session.add(db_segment)
        created_segments.append({
            "id": str(db_segment.id),
            "label": seg.label,
            "confidence": seg.confidence,
            "polygon": seg.polygon,
            "bounding_box": seg.bounding_box,
        })

    lighting = seg_service.estimate_lighting(image, segments)
    project.lighting_direction = lighting

    await session.commit()

    return {
        "project_id": str(project.id),
        "name": project.name,
        "image_width": w,
        "image_height": h,
        "segments_count": len(created_segments),
        "segments": created_segments,
        "lighting": lighting,
    }


@router.get("/{project_id}/segments")
async def get_segments(
    project_id: str,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(Segment)
        .where(Segment.project_id == project_id)
        .order_by(Segment.sort_order)
    )
    segments = result.scalars().all()

    return [
        {
            "id": str(s.id),
            "label": s.label,
            "confidence": s.confidence,
            "polygon": s.mask_polygon,
            "bounding_box": s.bounding_box,
        }
        for s in segments
    ]


@router.post("/{project_id}/replace")
async def replace_segment(
    project_id: str,
    body: dict = Body(...),
    session: AsyncSession = Depends(get_session),
):
    segment_id = body.get("segment_id")
    material_id = body.get("material_id")
    blend_mode = body.get("blend_mode", "multiply")

    if not segment_id or not material_id:
        raise HTTPException(status_code=400, detail="需要 segment_id 與 material_id")

    project_r = await session.execute(
        select(Project).where(Project.id == project_id)
    )
    project = project_r.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="專案不存在")

    seg_r = await session.execute(
        select(Segment).where(Segment.id == segment_id)
    )
    segment = seg_r.scalar_one_or_none()
    if not segment:
        raise HTTPException(status_code=404, detail="區塊不存在")

    mat_r = await session.execute(
        select(Material).where(Material.id == material_id)
    )
    material = mat_r.scalar_one_or_none()
    if not material:
        raise HTTPException(status_code=404, detail="素材不存在")

    scene = cv2.imread(project.original_photo)
    texture = cv2.imread(material.processed_texture)

    if scene is None or texture is None:
        raise HTTPException(status_code=500, detail="影像讀取失敗")

    mask = np.zeros((project.image_height, project.image_width), dtype=np.uint8)
    poly = np.array(segment.mask_polygon, dtype=np.int32).reshape((-1, 1, 2))
    cv2.fillPoly(mask, [poly], 255)

    result_img = tex_mapper.apply_texture(
        scene=scene,
        texture=texture,
        mask=mask,
        polygon=segment.mask_polygon,
        blend_mode=blend_mode,
    )

    result_filename = f"result_{uuid.uuid4()}.jpg"
    result_path = os.path.join(settings.upload_dir_results, result_filename)
    cv2.imwrite(result_path, result_img)

    replacement = Replacement(
        project_id=project.id,
        segment_id=segment.id,
        material_id=material.id,
        result_image=result_path,
        params={"blend_mode": blend_mode},
    )
    session.add(replacement)
    project.result_photo = result_path
    await session.commit()

    return {
        "replacement_id": str(replacement.id),
        "result_image": result_path,
    }


@router.post("/{project_id}/replace-batch")
async def batch_replace(
    project_id: str,
    body: dict = Body(...),
    session: AsyncSession = Depends(get_session),
):
    """批次替換多個區塊，確保光影一致"""
    replacements_data = body.get("replacements", [])
    if not replacements_data:
        raise HTTPException(status_code=400, detail="需要至少一個替換項目")

    project_r = await session.execute(
        select(Project).where(Project.id == project_id)
    )
    project = project_r.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="專案不存在")

    scene = cv2.imread(project.original_photo)

    replacement_items = []
    for item in replacements_data:
        seg_r = await session.execute(
            select(Segment).where(Segment.id == item["segment_id"])
        )
        segment = seg_r.scalar_one_or_none()
        if not segment:
            continue

        mat_r = await session.execute(
            select(Material).where(Material.id == item["material_id"])
        )
        material = mat_r.scalar_one_or_none()
        if not material:
            continue

        texture = cv2.imread(material.processed_texture)
        if texture is None:
            continue

        mask = np.zeros((project.image_height, project.image_width), dtype=np.uint8)
        poly = np.array(segment.mask_polygon, dtype=np.int32).reshape((-1, 1, 2))
        cv2.fillPoly(mask, [poly], 255)

        replacement_items.append({
            "texture": texture,
            "mask": mask,
            "polygon": segment.mask_polygon,
            "blend_mode": item.get("blend_mode", "multiply"),
        })

    result_img = tex_mapper.batch_replace(scene, replacement_items)

    result_filename = f"batch_result_{uuid.uuid4()}.jpg"
    result_path = os.path.join(settings.upload_dir_results, result_filename)
    cv2.imwrite(result_path, result_img)

    project.result_photo = result_path
    await session.commit()

    return {
        "result_image": result_path,
    }
