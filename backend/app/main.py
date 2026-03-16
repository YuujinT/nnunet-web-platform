"""FastAPI 主应用"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pathlib import Path

from .routers import cases, inference, files, models
from .config import settings

app = FastAPI(
    title=settings.APP_NAME,
    description="nnU-Net Web 推理与可视化平台",
    version=settings.VERSION
)

# CORS - 从环境变量读取或限制为开发/生产域名
allowed_origins = settings.CORS_ORIGINS if hasattr(settings, 'CORS_ORIGINS') else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API 路由 - 必须在静态文件之前注册
app.include_router(cases.router)
app.include_router(inference.router)
app.include_router(files.router)
app.include_router(models.router)

# 健康检查端点
@app.get("/api/health")
async def health_check():
    """健康检查"""
    return {
        "status": "ok",
        "version": settings.VERSION,
        "data_dir": str(settings.DATA_DIR),
        "model_dir": str(settings.MODEL_DIR)
    }

# 静态文件（前端）- 使用自定义处理支持SPA路由
frontend_dir = settings.BASE_DIR / "frontend"

class SPAStaticFiles(StaticFiles):
    """支持SPA的静态文件处理，所有未匹配路由返回index.html"""
    async def get_response(self, path: str, scope):
        try:
            response = await super().get_response(path, scope)
            return response
        except Exception:
            # 任何错误都返回index.html（前端路由处理）
            index_path = Path(self.directory) / "index.html"
            if index_path.exists():
                return FileResponse(index_path)
            raise

if frontend_dir.exists():
    # 使用SPA模式处理前端路由
    app.mount("/", SPAStaticFiles(directory=frontend_dir, html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=settings.HOST,
        port=settings.PORT,
        log_level=settings.UVICORN_LOG_LEVEL,
        access_log=settings.UVICORN_ACCESS_LOG,
    )
