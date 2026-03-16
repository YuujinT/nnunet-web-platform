# backend/app/routers/models.py
from fastapi import APIRouter, HTTPException
from pathlib import Path
from typing import List, Dict
from ..config import settings

router = APIRouter(prefix="/api/models", tags=["models"])

@router.get("")
async def list_models():
    """获取所有可用的 nnU-Net 模型"""
    try:
        model_dir = settings.MODEL_DIR  # 指向项目根目录下的 models/
        if not model_dir.exists():
            return []

        models = []
        # 遍历模型目录，收集模型信息
        for model_path in model_dir.iterdir():
            if model_path.is_dir():
                models.append({
                    "name": model_path.name,
                    "display_name": model_path.name.replace("_", " ").title(),
                    "path": str(model_path),
                    "description": f"nnU-Net 模型: {model_path.name}"
                })
        return models
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"加载模型失败: {str(e)}")