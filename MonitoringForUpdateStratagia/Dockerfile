FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN python -m pip install --no-cache-dir pip==26.2.1 \
    && python -m pip install --no-cache-dir -r requirements.txt \
    && python -m pip check

COPY app ./app
COPY config ./config
COPY main.py .
COPY Update/NostalgiaForInfinityX5.py ./Update/NostalgiaForInfinityX5.py

# Запуск бота
CMD ["python", "main.py"]
