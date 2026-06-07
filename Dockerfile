FROM docker.io/library/python:3.12-slim

WORKDIR /app

# 配置 pip 使用腾讯云镜像
RUN pip config set global.index-url https://pypi.org/simple/

# 复制项目文件
COPY pyproject.toml .
COPY bot.py .
COPY src/ src/

# 安装 Python 依赖（所有包均有预编译 wheel，无需 gcc）
RUN pip install --no-cache-dir -e .

# 创建数据目录
RUN mkdir -p /app/data /app/logs

EXPOSE 8080

CMD ["python", "bot.py"]
