FROM python:3.9-slim

WORKDIR /app

# Копируем файлы в контейнер
COPY . .

# Устанавливаем зависимости
RUN pip install -r requirements.txt

# Запуск бота
CMD ["python", "main.py"]