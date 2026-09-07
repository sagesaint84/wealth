FROM python:3.11-slim

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
