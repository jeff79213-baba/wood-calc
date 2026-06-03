"""
素材管理 API
POST /api/materials/upload  - 上傳素材照片，自動裁切與特徵提取
GET  /api/materials         - 素材庫列表
GET  /api/materials/{id}    - 素材詳情
DELETE /api/materials/{id}   - 刪除素材
"""
import os
import uuid
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db import get_session
from app.models.material import Material
from app.services.material_processor import MaterialProcessor
from app.config import settings

router = APIRouter(prefix="/api/materials", tags=["materials"])
processor = MaterialProcessor()


@router.post("/upload", status_code=201)
async def upload_material(
    file: UploadFile = File(...),
    name: str = Form(...),
    category: str = Form("tile"),
    user_id: str = Form("default"),
    session: AsyncSession = Depends(get_session),
):
    ext = os.path.splitext(file.filename)[1] or ".jpg"
    filename = f"{uuid.uuid4()}{ext}"
    filepath = os.path.join(settings.upload_dir_materials, filename)

    contents = await file.read()
    with open(filepath, "wb") as f:
        f.write(contents)

    import cv2
    import numpy as np
    img_array = np.frombuffer(contents, np.uint8)
    image = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

    if image is None:
        raise HTTPException(status_code=400, detail="無法解碼圖片")

    result = processor.process(image)

    texture_filename = f"texture_{uuid.uuid4()}.jpg"
    texture_path = os.path.join(settings.upload_dir_materials, texture_filename)
    cv2.imwrite(texture_path, result["texture"])

    thumb_filename = f"thumb_{uuid.uuid4()}.jpg"
    thumb_path = os.path.join(settings.upload_dir_materials, thumb_filename)
    cv2.imwrite(thumb_path, result["thumbnail"])

    material = Material(
        user_id=user_id,
        name=name,
        category=category,
        original_image=filepath,
        processed_texture=texture_path,
        thumbnail=thumb_path,
        texture_feature=result["feature_vector"],
        dominant_colors=result["dominant_colors"],
    )
    session.add(material)
    await session.commit()
    await session.refresh(material)

    return {
        "id": str(material.id),
        "name": material.name,
        "category": material.category,
        "dominant_colors": material.dominant_colors,
        "created_at": material.created_at.isoformat(),
    }


@router.get("")
async def list_materials(
    user_id: str = "default",
    category: str = None,
    session: AsyncSession = Depends(get_session),
):
    query = select(Material).where(Material.user_id == user_id)
    if category:
        query = query.where(Material.category == category)
    query = query.order_by(Material.created_at.desc())

    result = await session.execute(query)
    materials = result.scalars().all()

    return [
        {
            "id": str(m.id),
            "name": m.name,
            "category": m.category,
            "thumbnail": m.thumbnail,
            "dominant_colors": m.dominant_colors,
            "created_at": m.created_at.isoformat(),
        }
        for m in materials
    ]


@router.get("/{material_id}")
async def get_material(
    material_id: str,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(Material).where(Material.id == material_id)
    )
    material = result.scalar_one_or_none()
    if not material:
        raise HTTPException(status_code=404, detail="素材不存在")

    return {
        "id": str(material.id),
        "name": material.name,
        "category": material.category,
        "original_image": material.original_image,
        "processed_texture": material.processed_texture,
        "thumbnail": material.thumbnail,
        "dominant_colors": material.dominant_colors,
        "is_seamless": material.is_seamless,
        "created_at": material.created_at.isoformat(),
    }


@router.delete("/{material_id}", status_code=204)
async def delete_material(
    material_id: str,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(Material).where(Material.id == material_id)
    )
    material = result.scalar_one_or_none()
    if not material:
        raise HTTPException(status_code=404, detail="素材不存在")

    for path in [material.original_image, material.processed_texture, material.thumbnail]:
        if path and os.path.exists(path):
            os.remove(path)

    await session.delete(material)
    await session.commit()
