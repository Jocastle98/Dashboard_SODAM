# 소담촌 마곡점 매출 대시보드
# 어느 호스팅에서도 같은 방식으로 뜨도록 컨테이너로 고정한다.

FROM python:3.11-slim

# POS 데이터가 euc-kr이고 화면·로그가 한글이다. 로케일과 시간대를 명시한다.
ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    LANG=C.UTF-8 \
    TZ=Asia/Seoul

WORKDIR /app

# 의존성을 먼저 복사해 레이어 캐시를 살린다
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY collector/ ./collector/
COPY server/ ./server/
COPY web/ ./web/
COPY db/ ./db/

# DB와 원본 파일이 쌓이는 곳. 호스팅의 영속 디스크를 여기 마운트한다.
# 마운트하지 않으면 재배포 때마다 데이터가 사라진다 (docs/06 참고).
VOLUME ["/app/data"]

EXPOSE 8000

# $PORT를 주는 호스팅(Render 등)과 안 주는 곳 모두 대응
CMD ["sh", "-c", "uvicorn server.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
