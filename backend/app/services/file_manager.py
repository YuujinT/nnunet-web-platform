"""文件管理服务"""

import shutil
import zipfile
from pathlib import Path
from typing import List, Optional
import aiofiles

from ..config import settings
from ..models import CaseInfo


GROUND_TRUTH_FILENAME = "segmentation.nii.gz"
GROUND_TRUTH_LEGACY_FILENAMES = ("ground_truth.nii.gz", "gt.nii.gz")


class FileManager:
    """管理上传、预测和金标准文件"""

    def __init__(self):
        self.upload_dir = settings.UPLOAD_DIR
        self.prediction_dir = settings.PREDICTION_DIR
        self.gt_dir = settings.GROUND_TRUTH_DIR

    def get_case_dir(self, case_id: str, case_type: str = "upload") -> Path:
        """获取病例目录"""
        if case_type == "upload":
            base = self.upload_dir
        elif case_type == "prediction":
            base = self.prediction_dir
        elif case_type == "ground_truth":
            base = self.gt_dir
        else:
            raise ValueError(f"Unknown case type: {case_type}")

        case_dir = base / case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        return case_dir

    def list_cases(self) -> List[CaseInfo]:
        """列出所有病例"""
        cases = []

        # 扫描上传目录
        for case_dir in self.upload_dir.iterdir():
            if not case_dir.is_dir():
                continue

            case_id = case_dir.name
            case_info = self.get_case_info(case_id)
            cases.append(case_info)

        return sorted(cases, key=lambda x: x.created_at, reverse=True)

    def get_case_info(self, case_id: str) -> CaseInfo:
        """获取病例详细信息"""
        upload_dir = self.get_case_dir(case_id, "upload")
        pred_dir = self.get_case_dir(case_id, "prediction")
        gt_dir = self.get_case_dir(case_id, "ground_truth")

        # 检查成像文件 - 支持多种命名方式
        has_imaging = False
        imaging_candidates = [
            upload_dir / "imaging.nii.gz",
            upload_dir / "imaging.nii",
            upload_dir / f"{case_id}_0000.nii.gz",  # nnU-Net 格式
            upload_dir / f"{case_id}.nii.gz",
        ]

        # 也检查目录中任何 .nii 或 .nii.gz 文件
        if upload_dir.exists():
            for f in upload_dir.iterdir():
                if f.is_file() and (f.suffix == '.nii' or str(f).endswith('.nii.gz')):
                    lower_name = f.name.lower()
                    if 'ground_truth' not in lower_name and 'gt' not in lower_name and 'segmentation' not in lower_name:
                        has_imaging = True
                        # 标准化命名为 imaging.nii.gz
                        target = upload_dir / "imaging.nii.gz"
                        if f.name != "imaging.nii.gz":
                            try:
                                shutil.move(str(f), str(target))
                                has_imaging = True
                            except Exception as e:
                                print(f"重命名失败: {e}")
                        break

        # 如果没有找到，检查候选列表
        if not has_imaging:
            for candidate in imaging_candidates:
                if candidate.exists():
                    has_imaging = True
                    # 重命名为标准格式
                    target = upload_dir / "imaging.nii.gz"
                    if candidate != target:
                        try:
                            shutil.move(str(candidate), str(target))
                        except Exception as e:
                            print(f"重命名失败: {e}")
                    break

        # 检查预测文件
        pred_file = pred_dir / "prediction.nii.gz"
        has_prediction = pred_file.exists()

        # 检查金标准文件 - 优先查 gt_dir，再查 upload_dir，统一命名为 segmentation.nii.gz
        gt_file = gt_dir / GROUND_TRUTH_FILENAME
        upload_gt_candidates = [
            upload_dir / GROUND_TRUTH_FILENAME,
            *(upload_dir / name for name in GROUND_TRUTH_LEGACY_FILENAMES),
        ]

        has_ground_truth = gt_file.exists() or any(path.exists() for path in upload_gt_candidates)

        # 如果在 upload_dir 中找到，移动到 gt_dir 并标准化命名
        if not gt_file.exists():
            for candidate in upload_gt_candidates:
                if candidate.exists():
                    try:
                        gt_dir.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(candidate), str(gt_file))
                        has_ground_truth = True
                        break
                    except Exception as e:
                        print(f"移动金标准失败: {e}")

        # 获取文件大小
        file_sizes = {}
        for f in [upload_dir / "imaging.nii.gz", pred_file, gt_file]:
            if f.exists():
                file_sizes[f.name] = f.stat().st_size

        # 确定状态
        if has_prediction:
            status = "completed"
        elif has_imaging:
            status = "uploaded"
        else:
            status = "pending"

        return CaseInfo(
            id=case_id,
            name=case_id,
            status=status,
            has_imaging=has_imaging,
            has_prediction=has_prediction,
            has_ground_truth=has_ground_truth,
            file_sizes=file_sizes
        )

    async def save_upload(self, case_id: str, filename: str, data: bytes) -> Path:
        """保存上传的文件"""
        case_dir = self.get_case_dir(case_id, "upload")
        file_path = case_dir / filename

        # 异步写入
        async with aiofiles.open(file_path, 'wb') as f:
            await f.write(data)

        return file_path

    def extract_zip(self, case_id: str) -> List[str]:
        """解压上传的ZIP文件"""
        case_dir = self.get_case_dir(case_id, "upload")
        extracted = []

        for zip_file in case_dir.glob("*.zip"):
            with zipfile.ZipFile(zip_file, 'r') as zf:
                zf.extractall(case_dir)
                extracted.extend(zf.namelist())
            zip_file.unlink()  # 删除zip文件

        return extracted

    def convert_to_nifti(self, case_id: str) -> Optional[Path]:
        """将DICOM转换为NIfTI（如果需要）"""
        case_dir = self.get_case_dir(case_id, "upload")

        # 检查是否已有nifti文件
        nifti_files = list(case_dir.glob("*.nii*"))
        if nifti_files:
            # 标准化命名
            target = case_dir / "imaging.nii.gz"
            if nifti_files[0] != target:
                try:
                    shutil.move(str(nifti_files[0]), str(target))
                except Exception as e:
                    print(f"标准化命名失败: {e}")
            return target

        # 检查DICOM
        dicom_dirs = [d for d in case_dir.iterdir() if d.is_dir()]
        if not dicom_dirs:
            return None

        try:
            import SimpleITK as sitk

            # 读取DICOM序列
            reader = sitk.ImageSeriesReader()
            dicom_files = reader.GetGDCMSeriesFileNames(str(dicom_dirs[0]))
            if not dicom_files:
                return None

            reader.SetFileNames(dicom_files)
            image = reader.Execute()

            # 保存为NIfTI
            output_path = case_dir / "imaging.nii.gz"
            sitk.WriteImage(image, str(output_path))
            return output_path

        except Exception as e:
            print(f"DICOM conversion failed: {e}")
            return None

    def get_file_path(self, case_id: str, file_type: str) -> Optional[Path]:
        """获取文件路径"""
        if file_type == "imaging":
            case_dir = self.get_case_dir(case_id, "upload")
            # 优先返回标准化的 imaging.nii.gz
            target = case_dir / "imaging.nii.gz"
            if target.exists():
                return target

            # 查找任何 nifti 文件
            for name in ["imaging.nii", f"{case_id}_0000.nii.gz", f"{case_id}.nii.gz"]:
                path = case_dir / name
                if path.exists():
                    return path

        elif file_type == "prediction":
            case_dir = self.get_case_dir(case_id, "prediction")
            path = case_dir / "prediction.nii.gz"
            if path.exists():
                return path

        elif file_type == "ground_truth":
            # 优先查找 ground_truth 目录中的标准文件名
            case_dir = self.get_case_dir(case_id, "ground_truth")
            canonical = case_dir / GROUND_TRUTH_FILENAME
            if canonical.exists():
                return canonical

            # 兼容旧命名（ground_truth.nii.gz / gt.nii.gz）
            for legacy_name in GROUND_TRUTH_LEGACY_FILENAMES:
                legacy_path = case_dir / legacy_name
                if legacy_path.exists():
                    return legacy_path

            # 其次查找上传目录
            case_dir = self.get_case_dir(case_id, "upload")
            for name in (GROUND_TRUTH_FILENAME, *GROUND_TRUTH_LEGACY_FILENAMES):
                path = case_dir / name
                if path.exists():
                    return path

        return None

    def delete_case(self, case_id: str) -> bool:
        """删除病例"""
        try:
            for case_type in ["upload", "prediction", "ground_truth"]:
                case_dir = self.get_case_dir(case_id, case_type)
                if case_dir.exists():
                    shutil.rmtree(case_dir)
            return True
        except Exception as e:
            print(f"Delete failed: {e}")
            return False


file_manager = FileManager()
