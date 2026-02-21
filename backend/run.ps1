# Windows 下推荐：不用 --reload，避免请求被父进程占用导致 404/无响应
# 在 backend 目录执行: .\run.ps1
& "$PSScriptRoot\.venv\Scripts\python.exe" -m uvicorn main:app --host 0.0.0.0 --port 8000
