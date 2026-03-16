"""Pydantic 数据模型"""

from datetime import datetime
from typing import Optional, List, Dict, Literal
from pydantic import BaseModel, Field


class CaseBase(BaseModel):
    id: str = Field(..., description="病例ID")
    name: str = Field(..., description="病例名称")
    created_at: datetime = Field(default_factory=datetime.now)
    status: Literal["pending", "uploaded", "preprocessing", "inferencing",
    "completed", "failed"] = "pending"


class CaseInfo(CaseBase):
    has_imaging: bool = False
    has_prediction: bool = False
    has_ground_truth: bool = False
    file_sizes: Dict[str, int] = Field(default_factory=dict)
    metadata: Dict = Field(default_factory=dict)

    # 添加前端需要的路径字段
    imaging_path: Optional[str] = None
    prediction_path: Optional[str] = None
    ground_truth_path: Optional[str] = None
    # 添加前端期望的 case_name 别名兼容
    case_name: Optional[str] = Field(None, description="病例名称(前端兼容)")
    case_id: Optional[str] = Field(None, description="病例ID(前端兼容)")
    upload_time: Optional[str] = Field(None, description="上传时间")
    data_type: Optional[str] = Field("NIfTI", description="数据类型")
    data_size: Optional[str] = Field(None, description="数据大小")

    def model_post_init(self, __context):
        """初始化后处理，设置兼容字段"""
        if self.case_name is None:
            self.case_name = self.name
        if self.case_id is None:
            self.case_id = self.id
        # 格式化上传时间
        if self.upload_time is None and self.created_at:
            self.upload_time = self.created_at.strftime("%Y-%m-%d %H:%M:%S")
        # 计算数据大小
        if self.data_size is None and self.file_sizes:
            total_bytes = sum(self.file_sizes.values())
            self.data_size = self._format_size(total_bytes)

    @staticmethod
    def _format_size(bytes_val: int) -> str:
        """格式化文件大小"""
        if bytes_val == 0:
            return "0 B"
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes_val < 1024:
                return f"{bytes_val:.2f} {unit}"
            bytes_val /= 1024
        return f"{bytes_val:.2f} TB"


class InferenceRequest(BaseModel):
    case_id: str
    model_name: str = "default"
    fold: Optional[int] = None  # 使用特定fold，None表示所有fold集成
    model_variant: Literal["3d_fullres", "3d_lowres"] = "3d_fullres"



class InferenceResponse(BaseModel):
    task_id: str
    case_id: str
    status: str
    message: str


class TaskStatus(BaseModel):
    task_id: str
    status: Literal["queued", "running", "completed", "failed"]
    progress: int = Field(0, ge=0, le=100)
    message: str
    result: Optional[Dict] = None
    error: Optional[str] = None


class UploadResponse(BaseModel):
    success: bool
    case_id: str
    message: str
    files_received: List[str]