import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, JSON, Text
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import DeclarativeBase, relationship
import uuid


class Base(DeclarativeBase):
    pass


class Material(Base):
    __tablename__ = "materials"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(64), nullable=False, index=True)
    name = Column(String(128), nullable=False)
    category = Column(String(32), nullable=False, default="tile")

    original_image = Column(Text, nullable=False)
    processed_texture = Column(Text, nullable=True)
    thumbnail = Column(Text, nullable=True)

    texture_feature = Column(ARRAY(Float), nullable=True)
    dominant_colors = Column(JSON, nullable=True)
    is_seamless = Column(Integer, default=0)

    width_cm = Column(Float, nullable=True)
    height_cm = Column(Float, nullable=True)

    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    replacements = relationship("Replacement", back_populates="material")


class Project(Base):
    __tablename__ = "projects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(64), nullable=False, index=True)
    name = Column(String(128), nullable=False)
    room_type = Column(String(32), nullable=True)

    original_photo = Column(Text, nullable=False)
    result_photo = Column(Text, nullable=True)

    image_width = Column(Integer, nullable=True)
    image_height = Column(Integer, nullable=True)

    lighting_direction = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    segments = relationship("Segment", back_populates="project", cascade="all, delete-orphan")


class Segment(Base):
    __tablename__ = "segments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    label = Column(String(32), nullable=False)
    confidence = Column(Float, default=0.0)

    mask_polygon = Column(JSON, nullable=False)
    mask_image = Column(Text, nullable=True)
    bounding_box = Column(JSON, nullable=True)

    sort_order = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    project = relationship("Project", back_populates="segments")
    replacements = relationship("Replacement", back_populates="segment", cascade="all, delete-orphan")


class Replacement(Base):
    __tablename__ = "replacements"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    segment_id = Column(UUID(as_uuid=True), ForeignKey("segments.id"), nullable=False)
    material_id = Column(UUID(as_uuid=True), ForeignKey("materials.id"), nullable=False)

    result_image = Column(Text, nullable=True)
    params = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    project = relationship("Project")
    segment = relationship("Segment", back_populates="replacements")
    material = relationship("Material", back_populates="replacements")
