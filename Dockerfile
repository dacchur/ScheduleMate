FROM python:3.11-slim

WORKDIR /app

# 시스템 의존성 설치
RUN apt-get update && apt-get install -y \
    wget \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

# Python 패키지 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright Chromium 설치
RUN playwright install chromium
# RUN playwright install-deps chromium

# 애플리케이션 코드 복사
COPY src/ ./src/
COPY config/ ./config/

# 로그/스크린샷 디렉토리 생성
RUN mkdir -p logs screenshots

# 기본 실행: 스케줄러 모드 (매주 토요일 20:00 KST)
CMD ["python", "src/main.py"]
