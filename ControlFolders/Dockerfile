# Dockerfile
# Базовый образ Python 3.9 (облегчённая версия slim для уменьшения размера контейнера)
FROM python:3.9-slim

# Установка рабочей директории внутри контейнера
WORKDIR /app

# Установка зависимостей приложения
COPY requirements.txt requirements.txt
RUN pip install --upgrade pip --no-cache-dir -r requirements.txt

# Копирование папки app в контейнер
COPY app/ ./app/

# Указание команды для запуска приложения
CMD ["python", "app/main.py"]
