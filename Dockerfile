FROM python:3.11-slim-bookworm

# Keep browser auth packages out of Wealth's application interpreter.
ENV TOSSCTL_AUTH_HELPER_PYTHON=/opt/toss-auth/venv/bin/python \
    TOSSCTL_AUTH_HELPER_DIR=/opt/toss-auth/helper \
    TOSSCTL_AUTH_HELPER_BROWSER_CHANNEL=chromium \
    TOSSCTL_AUTH_HELPER_QUIET=1 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/toss-auth/ms-playwright

COPY ops/toss-auth/requirements.txt /opt/toss-auth/requirements.txt
RUN python -m venv /opt/toss-auth/venv \
    && /opt/toss-auth/venv/bin/python -m pip install --no-cache-dir --only-binary=:all: -r /opt/toss-auth/requirements.txt \
    && /opt/toss-auth/venv/bin/python -m playwright install --with-deps --no-shell chromium \
    && rm -rf /var/lib/apt/lists/*

# This path is separate from the existing /opt/toss-wts/tossctl bind mount.
COPY vendor/tossctl-auth-helper/ /opt/toss-auth/helper/
COPY ops/toss-auth/browser_smoke.py /opt/toss-auth/browser_smoke.py
# No Toss/server access, including Chromium background traffic. Fail the image
# build if either native or emulated target architecture cannot launch Chromium.
RUN --network=none /opt/toss-auth/venv/bin/python /opt/toss-auth/browser_smoke.py

WORKDIR /app

# 의존성만 먼저 복사해서 캐시를 최대한 활용
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 나머지 소스 복사
COPY . .

# 데이터 저장 폴더 (볼륨으로 마운트할 예정)
RUN mkdir -p /app/data

EXPOSE 4829

# 컨테이너 밖에서 접속 가능하도록 0.0.0.0 바인딩
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "4829"]
