"""nnU-Net 推理服务"""

import os
import json
import shutil
import asyncio
import uuid
from pathlib import Path
from typing import Optional, Callable, List, Dict, Tuple

from ..config import settings
from ..services.file_manager import file_manager


class nnUNetRunner:
    """运行 nnU-Net 推理"""

    def __init__(self):
        self.model_dir = settings.MODEL_DIR
        self.nnunet_raw = settings.NNUNET_RAW
        self.nnunet_preprocessed = settings.NNUNET_PREPROCESSED
        self.nnunet_results = settings.NNUNET_RESULTS

        os.environ["nnUNet_raw"] = str(self.nnunet_raw)
        os.environ["nnUNet_preprocessed"] = str(self.nnunet_preprocessed)
        os.environ["nnUNet_results"] = str(self.model_dir)

        print("nnUNetRunner 初始化:")
        print(f"  - 模型目录: {self.model_dir}")
        print(f"  - nnUNet_raw: {self.nnunet_raw}")
        print(f"  - nnUNet_results: {os.environ['nnUNet_results']}")

    def prepare_input(self, case_id: str, temp_dirs: Optional[List[Path]] = None) -> Optional[Path]:
        """准备 nnU-Net 输入格式（每次推理使用独立目录，实现case隔离的独立性）"""
        task_dir = self.nnunet_raw / "Dataset001_WebUpload" / "imagesTs" / f"web_{case_id}_{uuid.uuid4().hex[:8]}"
        task_dir.mkdir(parents=True, exist_ok=True)
        if temp_dirs is not None:
            temp_dirs.append(task_dir)

        imaging_path = file_manager.get_file_path(case_id, "imaging")
        if not imaging_path:
            return None

        target_name = f"{case_id}_0000.nii.gz"
        target_path = task_dir / target_name


        # 同盘优先硬链接，避免大文件复制耗时；失败则回退复制
        try:
            os.link(imaging_path, target_path)
        except Exception:
            shutil.copy2(imaging_path, target_path)

        return task_dir

    @staticmethod
    def _normalize_model_config(model_config: str) -> str:
        """仅支持 3d_fullres / 3d_lowres"""
        value = (model_config or "").strip().lower()
        if value not in {"3d_fullres", "3d_lowres"}:
            raise ValueError(f"不支持的模型属性: {model_config}")
        return value

    @staticmethod
    def _parse_trainer_dir_name(trainer_dir_name: str) -> Optional[Tuple[str, str, str]]:
        parts = trainer_dir_name.split("__")
        if len(parts) < 3:
            return None
        trainer_name = "__".join(parts[:-2])
        plans_name = parts[-2]
        config_name = parts[-1]
        return trainer_name, plans_name, config_name

    def _collect_available_configs(self, dataset_path: Path) -> Dict[str, Dict[str, str | Path]]:
        config_map: Dict[str, Dict[str, str | Path]] = {}
        for trainer_dir in dataset_path.glob("nnUNetTrainer*"):
            parsed = self._parse_trainer_dir_name(trainer_dir.name)
            if not parsed:
                continue
            trainer_name, plans_name, config_name = parsed
            if config_name in {"3d_fullres", "3d_lowres"}:
                config_map[config_name] = {
                    "trainer_dir": trainer_dir,
                    "trainer_name": trainer_name,
                    "plans_name": plans_name,
                }
        return config_map

    async def run_inference(self, case_id: str,
                            progress_callback: Optional[Callable] = None,
                            model_name: str = "default",
                            fold: Optional[int] = None,
                            model_config: str = "3d_fullres",
                            temp_dirs: Optional[List[Path]] = None) -> bool:
        """运行 nnU-Net 推理"""
        result_dir = None

        try:
            if progress_callback:
                progress_callback(10, "准备输入数据...")

            input_dir = self.prepare_input(case_id, temp_dirs)
            if not input_dir:
                raise ValueError("无法准备输入数据")

            if progress_callback:
                progress_callback(20, "加载模型...")

            model_info = self._find_model(model_name, model_config)
            if not model_info:
                raise ValueError(f"找不到模型: {model_name}")

            trainer_dir, trainer_name, plans_name, fold_args, checkpoint_name, dataset_name, config_name = model_info

            # 单线程场景：fold 未指定时默认使用全部可用 folds
            if fold is not None:
                selected_fold = str(fold)
                if selected_fold not in fold_args:
                    raise ValueError(f"Fold {selected_fold} 不可用，可用 folds: {fold_args}")
                selected_folds = [selected_fold]
            else:
                selected_folds = list(fold_args)
                print(f"[nnUNetRunner] fold 未指定，默认使用 全fold: {selected_folds}")

            result_dir = self.nnunet_results / case_id
            result_dir.mkdir(parents=True, exist_ok=True)
            if temp_dirs is not None:
                temp_dirs.append(result_dir)

            cmd = [
                "nnUNetv2_predict",
                "-i", str(input_dir),
                "-o", str(result_dir),
                "-d", dataset_name,
                "-tr", trainer_name,
                "-p", plans_name,
                "-c", config_name,
                "-npp", str(settings.NNUNET_NPP),
                "-nps", str(settings.NNUNET_NPS),
                "-chk", checkpoint_name,
                "-f",
            ]
            cmd.extend(selected_folds)
            cmd.append("--disable_tta")

            if progress_callback:
                progress_callback(30, "开始推理...")

            process = await asyncio.create_subprocess_exec(*cmd)
            await process.wait()

            if process.returncode != 0:
                raise RuntimeError(f"nnU-Net 推理失败，退出码: {process.returncode}")

            if progress_callback:
                progress_callback(90, "保存结果...")

            result_file = result_dir / f"{case_id}.nii.gz"
            pred_dir = file_manager.get_case_dir(case_id, "prediction")
            target_file = pred_dir / "prediction.nii.gz"

            if result_file.exists():
                # 同盘优先 move，避免重复复制大体积 NIfTI
                try:
                    shutil.move(str(result_file), str(target_file))
                except Exception:
                    shutil.copy2(result_file, target_file)

                if result_dir.exists():
                    shutil.rmtree(result_dir, ignore_errors=True)
                if temp_dirs and result_dir in temp_dirs:
                    temp_dirs.remove(result_dir)

                # 清理单次输入文件，避免累积
                staged_input = input_dir / f"{case_id}_0000.nii.gz"
                if staged_input.exists():
                    staged_input.unlink(missing_ok=True)

                if progress_callback:
                    progress_callback(100, "推理完成")
                return True

            raise FileNotFoundError("推理结果文件未生成")

        except Exception as e:
            if result_dir and result_dir.exists():
                shutil.rmtree(result_dir, ignore_errors=True)
            if temp_dirs and result_dir in temp_dirs:
                temp_dirs.remove(result_dir)

            if progress_callback:
                progress_callback(0, f"错误: {str(e)}")
            raise

    def _find_model(self, model_name: str, model_config: str) -> tuple[Optional[Path], Optional[str], Optional[str], Optional[List[str]], Optional[str], Optional[str], Optional[str]]:
        """查找模型路径，返回 (trainer目录, trainer名称, plans名称, fold参数列表, 检查点名称, 数据集名称, 配置名称)"""
        print(f"\n🔍 查找模型: {model_name}")

        if not self.model_dir.exists():
            print(f"❌ 模型目录不存在: {self.model_dir}")
            return None, None, None, None, None, None, None

        if model_name and model_name != "default":
            dataset_path = self.model_dir / model_name
            if not dataset_path.exists():
                print(f"❌ 指定模型不存在: {dataset_path}")
                return None, None, None, None, None, None, None
        else:
            candidates = [d for d in self.model_dir.iterdir() if d.is_dir()]
            if not candidates:
                print("❌ 未找到任何模型")
                return None, None, None, None, None, None, None
            dataset_path = candidates[0]
            print(f"✅ 使用默认模型: {dataset_path.name}")

        trainer_dirs = list(dataset_path.glob("nnUNetTrainer*"))
        if not trainer_dirs:
            print("❌ 没有找到 nnUNetTrainer 目录")
            return None, None, None, None, None, None, None

        config_name = self._normalize_model_config(model_config)
        config_map = self._collect_available_configs(dataset_path)
        if not config_map:
            print("❌ 没有找到可用的模型属性目录(3d_fullres/3d_lowres)")
            return None, None, None, None, None, None, None

        if config_name not in config_map:
            available = sorted(config_map.keys())
            raise ValueError(f"模型 {dataset_path.name} 不支持 {config_name}，可用: {available}")

        selected = config_map[config_name]
        trainer_dir = selected["trainer_dir"]
        trainer_name = selected["trainer_name"]
        plans_name = selected["plans_name"]
        print(f"   Trainer: {trainer_dir.name}")

        available_folds = []
        checkpoint_name = "checkpoint_final.pth"

        for fold_dir in sorted(trainer_dir.glob("fold_*")):
            fold_num = fold_dir.name.split("_")[1]

            found_ckpt = None
            for ckpt_name in ["checkpoint_final.pth", "checkpoint_best.pth"]:
                if (fold_dir / ckpt_name).exists():
                    found_ckpt = ckpt_name
                    break

            if found_ckpt:
                available_folds.append(fold_num)
                checkpoint_name = found_ckpt
                print(f"   ✅ Fold {fold_num}: {found_ckpt}")

        if not available_folds:
            print("❌ 没有可用的 fold")
            return None, None, None, None, None, None, None

        dataset_name = dataset_path.name
        print(f"\n✅ 配置: 数据集={dataset_name}, 模型属性={config_name}, Folds={available_folds}, 检查点={checkpoint_name}")
        return trainer_dir, trainer_name, plans_name, available_folds, checkpoint_name, dataset_name, config_name

    def get_available_models(self) -> list:
        """获取可用模型列表"""
        models = []
        if not self.model_dir.exists():
            return models

        for task_dir in self.model_dir.iterdir():
            if task_dir.is_dir():
                models.append({
                    "name": task_dir.name,
                    "display_name": task_dir.name.replace("_", " ").title(),
                    "path": str(task_dir),
                    "description": self._get_model_description(task_dir)
                })

        return models

    def _get_model_description(self, model_path: Path) -> str:
        """读取模型描述"""
        info_file = model_path / "dataset.json"
        if info_file.exists():
            try:
                with open(info_file) as f:
                    data = json.load(f)
                    return data.get("description", "无描述")
            except Exception:
                pass
        return "nnU-Net 模型"


nnunet_runner = nnUNetRunner()