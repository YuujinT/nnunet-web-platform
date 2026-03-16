"""推理路由"""

import uuid
from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import Optional

from ..models import InferenceRequest, InferenceResponse, TaskStatus
from ..services.nnunet_runner import nnunet_runner
from ..services.file_manager import file_manager

router = APIRouter(prefix="/api/inference", tags=["inference"])

# 内存中的任务状态存储（生产环境应使用 Redis）
tasks = {}


@router.post("/start", response_model=InferenceResponse)
async def start_inference(
        request: InferenceRequest,
        background_tasks: BackgroundTasks,
):
    """启动推理任务"""
    # 检查病例是否存在
    case_info = file_manager.get_case_info(request.case_id)
    if not case_info.has_imaging:
        raise HTTPException(status_code=404, detail="病例没有影像数据")

    # 生成任务ID
    task_id = str(uuid.uuid4())

    # 初始化任务状态
    tasks[task_id] = TaskStatus(
        task_id=task_id,
        status="queued",
        progress=0,
        message="任务已加入队列"
    )

    print(f"[inference] case={request.case_id} model={request.model_name} config={request.model_variant} fold={request.fold}")

    # 后台运行推理
    background_tasks.add_task(
        run_inference_task,
        task_id=task_id,
        case_id=request.case_id,
        model_name=request.model_name,
        fold=request.fold,
        model_config=request.model_variant,
    )

    return InferenceResponse(
        task_id=task_id,
        case_id=request.case_id,
        status="queued",
        message="推理任务已启动"
    )


async def run_inference_task(task_id: str, case_id: str,
                             model_name: str, fold: Optional[int], model_config: str):
    """后台推理任务"""
    temp_dirs = []  # 跟踪临时目录用于清理

    try:
        tasks[task_id].status = "running"
        tasks[task_id].message = "开始推理..."

        def progress_callback(progress: int, message: str):
            tasks[task_id].progress = progress
            tasks[task_id].message = message

        # 运行推理
        success = await nnunet_runner.run_inference(
            case_id=case_id,
            progress_callback=progress_callback,
            model_name=model_name,
            fold=fold,
            model_config=model_config,
            temp_dirs=temp_dirs  # 传递引用用于清理
        )

        if success:
            tasks[task_id].status = "completed"
            tasks[task_id].progress = 100
            tasks[task_id].message = "推理完成"
            tasks[task_id].result = {
                "case_id": case_id,
                "has_prediction": True
            }
        else:
            tasks[task_id].status = "failed"
            tasks[task_id].message = "推理失败"

    except Exception as e:
        tasks[task_id].status = "failed"
        tasks[task_id].message = f"错误: {str(e)}"
        tasks[task_id].error = str(e)
    finally:
        # 清理临时文件
        for d in temp_dirs:
            if d.exists():
                import shutil
                shutil.rmtree(d, ignore_errors=True)


@router.get("/status/{task_id}", response_model=TaskStatus)
async def get_task_status(task_id: str):
    """获取任务状态"""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="任务不存在")
    return tasks[task_id]
