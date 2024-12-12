import os
import time  # Добавьте этот импорт
import shutil
import asyncio
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from telegram_bot import TelegramBot

class FileMonitor:
    def __init__(self, config):
        self.config = config
        self.observer = Observer()

    def run(self):
        for src, dest in self.config['FOLDER_MAPPINGS'].items():
            # Проверим, существует ли исходная папка
            if not os.path.exists(src):
                print(f"Ошибка: Папка {src} не существует.")
                continue

            event_handler = FileHandler(src, dest)
            self.observer.schedule(event_handler, src, recursive=True)

        self.observer.start()
        try:
            while True:
                time.sleep(1)  # Задержка в 1 секунду
        except KeyboardInterrupt:
            self.observer.stop()
        self.observer.join()

class FileHandler(FileSystemEventHandler):
    def __init__(self, src, dest):
        self.src = src
        self.dest = dest

    def on_modified(self, event):
        if not event.is_directory:
            self.copy_file(event.src_path)

    def copy_file(self, src_path):
        relative_path = os.path.relpath(src_path, self.src)
        dest_path = os.path.join(self.dest, relative_path)
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        shutil.copy2(src_path, dest_path)

        message = f"Файл {os.path.basename(src_path)} скопирован из {self.src} в {self.dest}"
        send_telegram_message(message)  # Передаем сообщение в Telegram-бот

def send_telegram_message(message, config):
    # Функция отправки сообщений в Telegram (вызывается после копирования)
    bot = TelegramBot(config)
    asyncio.run(bot.send_telegram_message(message))  # Отправляем сообщение
