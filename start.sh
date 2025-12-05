#!/bin/bash

# Opinion Whale Tracker 启动脚本

echo "================================="
echo "Opinion Whale Tracker"
echo "================================="

# 检查虚拟环境
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# 激活虚拟环境
source venv/bin/activate

# 安装依赖
echo "Installing dependencies..."
pip install -q -r backend/requirements.txt

# 启动后端服务 (后台运行)
echo "Starting backend server on port 8000..."
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000 --lifespan off &
BACKEND_PID=$!
cd ..

# 等待后端启动
sleep 3

# 启动前端服务
echo "Starting frontend server on port 8080..."
cd frontend
python3 -m http.server 8080 &
FRONTEND_PID=$!
cd ..

echo ""
echo "================================="
echo "Services started!"
echo "================================="
echo "Backend API: http://localhost:8000"
echo "Frontend UI: http://localhost:8080"
echo "API Docs:    http://localhost:8000/docs"
echo "================================="
echo ""
echo "Press Ctrl+C to stop all services"

# 等待用户中断
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" SIGINT SIGTERM

wait
