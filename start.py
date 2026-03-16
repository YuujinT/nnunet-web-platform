#!/usr/bin/env python3
"""
nnUNet 医学影像 Web 推理系统 一键启动
"""

import os
import sys
import subprocess
import webbrowser
import time
from pathlib import Path


def setup():
    """环境设置"""
    print("🔧 环境检查...")

    # 创建必要目录
    dirs = [
        "data/uploads", "data/predictions", "data/ground_truth",
        "data/nnunet_raw", "data/nnunet_preprocessed", "data/nnunet_results",
        "frontend/css", "frontend/js", "models"
    ]

    for d in dirs:
        Path(d).mkdir(parents=True, exist_ok=True)

    # 检查依赖
    req_file = Path("backend/requirements.txt")
    if req_file.exists():
        try:
            import fastapi
            import uvicorn
        except ImportError:
            print("📦 安装依赖...")
            subprocess.check_call([
                sys.executable, "-m", "pip", "install", "-r", str(req_file)
            ])

    print("✅ 环境就绪\n")


def main():
    print("""
    ╔══════════════════════════════════════════════════╗
    ║                                                  ║
    ║     🧠     “慧眼”医学图像Web识别平台             ║
    ║                                                  ║
    ║           上传 → 推理 → 对比 → 可视化            ║
    ║                                                  ║
    ╚══════════════════════════════════════════════════╝
    """)

    setup()

    # 启动服务器
    print("🚀 启动服务...")
    print("   📍 本地访问: http://localhost:8080")
    print("   📍 API文档:  http://localhost:8080/docs")
    print("   📍 数据目录: ./data/")
    print("\n按 Ctrl+C 停止\n")

    # 延迟打开浏览器
    def open_browser():
        time.sleep(2)
        webbrowser.open("http://localhost:8080")

    import threading
    threading.Thread(target=open_browser, daemon=True).start()

    # 启动
    os.chdir("backend")
    sys.path.insert(0, str(Path.cwd().parent))

    # start.py
    from backend.app.main import app
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8080,
        log_level="warning",
        access_log=False,
    )


if __name__ == "__main__":
    main()