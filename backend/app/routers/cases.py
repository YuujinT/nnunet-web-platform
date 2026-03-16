"""病例管理路由"""

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from typing import List, Optional
import uuid
import shutil
import aiofiles

from ..models import CaseInfo, UploadResponse
from ..services.file_manager import file_manager

router = APIRouter(prefix="/api/cases", tags=["cases"])

GROUND_TRUTH_FILENAME = "segmentation.nii.gz"


def _add_paths_to_case_info(info: CaseInfo) -> CaseInfo:
    """为病例信息添加文件路径"""
    if info.has_imaging:
        info.imaging_path = f"/api/files/{info.id}/imaging/imaging.nii.gz"
    if info.has_prediction:
        info.prediction_path = f"/api/files/{info.id}/prediction/prediction.nii.gz"
    if info.has_ground_truth:
        info.ground_truth_path = f"/api/files/{info.id}/ground_truth/{GROUND_TRUTH_FILENAME}"
    return info


@router.get("", response_model=List[CaseInfo])
async def list_cases():
    """获取所有病例列表"""
    cases = file_manager.list_cases()
    return [_add_paths_to_case_info(case) for case in cases]


@router.get("/{case_id}", response_model=CaseInfo)
async def get_case(case_id: str):
    """获取单个病例信息"""
    info = file_manager.get_case_info(case_id)
    # 只要有成像数据或预测数据就返回
    if not info.has_imaging and not info.has_prediction:
        raise HTTPException(status_code=404, detail="病例不存在")
    return _add_paths_to_case_info(info)


@router.post("/upload", response_model=UploadResponse)
async def upload_case(
        files: List[UploadFile] = File(...),
        case_name: Optional[str] = Form(None),
        has_ground_truth: bool = Form(False)
):
    """
    上传新病例

    - files: 支持 .nii.gz, .nii, .dcm, .zip
    - case_name: 自定义病例名，不传则自动生成
    - has_ground_truth: 是否同时上传金标准
    """
    try:
        # 生成病例ID
        case_id = case_name or f"case_{uuid.uuid4().hex[:8]}"
        received_files = []
        gt_content = None
        imaging_content = None
        gt_filename = None
        imaging_filename = None

        # 第一步：收集所有文件内容
        for file in files:
            filename = file.filename.lower()
            content = await file.read()
            received_files.append(file.filename)

            # 判断是否为金标准
            is_ground_truth = (
                "segmentation" in filename or
                "ground_truth" in filename or
                "gt" in filename or
                filename.startswith("gt.")
            )

            # 如果明确标记有金标准，且只有一个非金标准文件，则视为配对
            if has_ground_truth and len(files) == 2:
                if is_ground_truth:
                    gt_content = content
                    gt_filename = file.filename
                else:
                    imaging_content = content
                    imaging_filename = file.filename
            else:
                # 自动判断
                if is_ground_truth:
                    gt_content = content
                    gt_filename = file.filename
                else:
                    imaging_content = content
                    imaging_filename = file.filename

        # 第二步：保存文件到对应位置
        # 保存成像文件
        if imaging_content:
            upload_dir = file_manager.get_case_dir(case_id, "upload")
            # 始终保存为 imaging.nii.gz
            imaging_path = upload_dir / "imaging.nii.gz"
            async with aiofiles.open(imaging_path, 'wb') as f:
                await f.write(imaging_content)
            print(f"保存成像文件: {imaging_path}")
        else:
            raise HTTPException(status_code=400, detail="未找到成像文件")

        # 保存金标准文件（如果有）
        if gt_content:
            gt_dir = file_manager.get_case_dir(case_id, "ground_truth")
            gt_path = gt_dir / GROUND_TRUTH_FILENAME
            async with aiofiles.open(gt_path, 'wb') as f:
                await f.write(gt_content)
            print(f"保存金标准文件: {gt_path}")

        # 第三步：处理 ZIP 解压（如果上传的是 zip）
        if any(f.endswith('.zip') for f in received_files):
            extracted = file_manager.extract_zip(case_id)
            received_files.extend(extracted)
            # 解压后重新标准化命名
            file_manager.get_case_info(case_id)  # 这会触发标准化

        # 第四步：转换 DICOM（如果需要）
        # 检查是否是 DICOM 目录
        upload_dir = file_manager.get_case_dir(case_id, "upload")
        dicom_dirs = [d for d in upload_dir.iterdir() if d.is_dir()]
        if dicom_dirs and not (upload_dir / "imaging.nii.gz").exists():
            nifti_path = file_manager.convert_to_nifti(case_id)
            if nifti_path:
                print(f"DICOM 转换完成: {nifti_path}")

        # 第五步：确保文件被正确标准化命名
        # 重新扫描目录并重命名
        for f in upload_dir.iterdir():
            if f.is_file():
                fname = f.name.lower()
                if fname.endswith('.nii') or fname.endswith('.nii.gz'):
                    if 'ground_truth' not in fname and 'gt' not in fname and 'segmentation' not in fname:
                        if f.name != "imaging.nii.gz":
                            target = upload_dir / "imaging.nii.gz"
                            try:
                                shutil.move(str(f), str(target))
                                print(f"标准化命名: {f.name} -> imaging.nii.gz")
                            except Exception as e:
                                print(f"重命名失败: {e}")

        # 验证上传结果
        case_info = file_manager.get_case_info(case_id)
        if not case_info.has_imaging:
            raise HTTPException(status_code=500, detail="文件保存后无法识别，请检查文件格式")

        return UploadResponse(
            success=True,
            case_id=case_id,
            message=f"成功上传 {len(received_files)} 个文件",
            files_received=received_files
        )

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"上传错误: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{case_id}")
async def delete_case(case_id: str):
    """删除病例"""
    success = file_manager.delete_case(case_id)
    if not success:
        raise HTTPException(status_code=500, detail="删除失败")
    return {"message": "删除成功"}


@router.post("/{case_id}/copy-ground-truth")
async def copy_ground_truth(case_id: str, source_case_id: str):
    """从其他病例复制金标准（用于对比相同数据）"""
    try:
        source_gt = file_manager.get_file_path(source_case_id, "ground_truth")
        if not source_gt:
            raise HTTPException(status_code=404, detail="源病例没有金标准")

        target_dir = file_manager.get_case_dir(case_id, "ground_truth")
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_gt, target_dir / GROUND_TRUTH_FILENAME)

        return {"message": "金标准复制成功"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))