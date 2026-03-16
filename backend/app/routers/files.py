"""文件服务路由"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse, RedirectResponse
import aiofiles

from ..services.file_manager import file_manager

router = APIRouter(prefix="/api/files", tags=["files"])

CANONICAL_FILENAMES = {
    "imaging": "imaging.nii.gz",
    "prediction": "prediction.nii.gz",
    "ground_truth": "segmentation.nii.gz",
}
GROUND_TRUTH_ALIASES = {"segmentation.nii.gz", "ground_truth.nii.gz", "gt.nii.gz"}


def _is_valid_filename(file_type: str, filename: str) -> bool:
    if file_type == "ground_truth":
        return filename in GROUND_TRUTH_ALIASES
    return filename == CANONICAL_FILENAMES.get(file_type)


@router.get("/{case_id}/{file_type}")
async def get_file(case_id: str, file_type: str):
    """
    获取病例文件（兼容旧版，会自动重定向到带扩展名的版本）

    file_type: imaging | prediction | ground_truth
    """
    filename = CANONICAL_FILENAMES.get(file_type)
    if not filename:
        raise HTTPException(status_code=400, detail="无效的文件类型")

    # 重定向到带扩展名的版本
    return RedirectResponse(url=f"/api/files/{case_id}/{file_type}/{filename}")


@router.get("/{case_id}/{file_type}/{filename}")
async def get_file_with_name(case_id: str, file_type: str, filename: str):
    """
    获取病例文件（带完整文件名）

    - case_id: 病例ID
    - file_type: imaging | prediction | ground_truth
    - filename: 完整的文件名（如 imaging.nii.gz）
    """
    if not _is_valid_filename(file_type, filename):
        expected = CANONICAL_FILENAMES.get(file_type)
        if not expected:
            raise HTTPException(status_code=400, detail="无效的文件类型")
        raise HTTPException(status_code=400, detail=f"文件名应为 {expected}")

    # 获取文件路径
    file_path = file_manager.get_file_path(case_id, file_type)

    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    # 获取文件大小
    file_size = file_path.stat().st_size

    # 手动设置 headers
    headers = {
        "Content-Type": "application/octet-stream",
        "Content-Disposition": f"attachment; filename={filename}",
        "Content-Length": str(file_size),
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
        "Cache-Control": "no-cache",
        # 关键：不设置 Content-Encoding
    }

    async def file_iterator():
        """流式读取文件，避免一次性加载到内存"""
        try:
            async with aiofiles.open(file_path, 'rb') as f:
                while chunk := await f.read(8192 * 1024):  # 8MB chunks
                    yield chunk
        except Exception as e:
            print(f"读取文件失败: {e}")
            raise

    return StreamingResponse(
        file_iterator(),
        headers=headers,
        media_type="application/octet-stream"
    )


@router.head("/{case_id}/{file_type}/{filename}")
async def head_file_with_name(case_id: str, file_type: str, filename: str):
    """
    HEAD 请求，用于检查文件是否存在和获取大小
    浏览器和 Niivue 可能会先发送 HEAD 请求检查文件
    """
    if not _is_valid_filename(file_type, filename):
        raise HTTPException(status_code=400, detail="无效的文件名")

    file_path = file_manager.get_file_path(case_id, file_type)

    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    file_size = file_path.stat().st_size

    from fastapi.responses import Response
    return Response(
        status_code=200,
        headers={
            "Content-Type": "application/octet-stream",
            "Content-Disposition": f"attachment; filename={filename}",
            "Content-Length": str(file_size),
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
            "Cache-Control": "no-cache",
        }
    )


@router.options("/{case_id}/{file_type}/{filename}")
async def options_file_with_name(case_id: str, file_type: str, filename: str):
    """
    OPTIONS 请求，用于 CORS 预检
    浏览器在跨域请求前会发送 OPTIONS 请求
    """
    from fastapi.responses import Response
    return Response(
        status_code=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Max-Age": "86400",  # 24小时
        }
    )


@router.get("/{case_id}/{file_type}/info")
async def get_file_info(case_id: str, file_type: str):
    """
    获取文件信息（不返回文件内容）
    可用于前端检查文件是否存在和获取大小
    """
    file_path = file_manager.get_file_path(case_id, file_type)

    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    file_size = file_path.stat().st_size

    # 确定文件名
    filename = CANONICAL_FILENAMES.get(file_type, file_path.name)

    return {
        "exists": True,
        "filename": filename,
        "size": file_size,
        "size_formatted": _format_size(file_size),
        "path": str(file_path),
        "type": file_type,
        "url": f"/api/files/{case_id}/{file_type}/{filename}"
    }


def _format_size(bytes_val: int) -> str:
    """格式化文件大小"""
    if bytes_val == 0:
        return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_val < 1024:
            return f"{bytes_val:.2f} {unit}"
        bytes_val /= 1024
    return f"{bytes_val:.2f} TB"