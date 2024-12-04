# Используем официальный образ Python как базовый
FROM python:3.9-slim

# Устанавливаем рабочую директорию внутри контейнера
WORKDIR /app

# Копируем requirements.txt в контейнер
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем все файлы проекта в рабочую директорию контейнера
COPY . .

# Копируем нужный скрипт в зависимости от переменной окружения LANGUAGE
ARG LANGUAGE 
COPY MonitoringForUpdateStratagia$LANGUAGE.py /app/MonitoringForUpdateStratagia.py

# Команда для запуска бота
CMD ["python", "MonitoringForUpdateStratagia.py"]
