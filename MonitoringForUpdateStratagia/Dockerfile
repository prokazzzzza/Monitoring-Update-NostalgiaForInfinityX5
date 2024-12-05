# Используем официальный образ Python как базовый / Use the official Python image as the base
FROM python:3.9-slim

# Устанавливаем рабочую директорию внутри контейнера / Set the working directory inside the container
WORKDIR /app

# Копируем requirements.txt в контейнер / Copy requirements.txt into the container
COPY requirements.txt .

# Устанавливаем зависимости / Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Копируем все файлы проекта в рабочую директорию контейнера / Copy all project files into the container's working directory
COPY . .

# Копируем нужный скрипт в зависимости от переменной окружения LANGUAGE / Copy the required script based on the LANGUAGE environment variable
ARG LANGUAGE 
COPY MonitoringForUpdateStratagia$LANGUAGE.py /app/MonitoringForUpdateStratagia.py

# Команда для запуска бота / Command to run the bot
CMD ["python", "MonitoringForUpdateStratagia.py"]
