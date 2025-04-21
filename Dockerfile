FROM python:3.13-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 复制项目文件
COPY . /app/

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# 创建日志目录
RUN mkdir -p /app/logs

# 暴露web服务端口
EXPOSE 58181

# 设置容器启动命令
CMD ["python", "main.py"] 