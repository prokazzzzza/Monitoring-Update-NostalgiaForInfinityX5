# config.py
import os
from dotenv import load_dotenv

def load_config():
    load_dotenv()
    source_folders = os.getenv('SOURCE_FOLDERS', '').split(',')
    dest_folders = os.getenv('DEST_FOLDERS', '').split(',')
    
    if not source_folders or not dest_folders:
        raise ValueError("Не указаны папки для мониторинга.")
    
    # Проверка на совпадение длины списков
    if len(source_folders) != len(dest_folders):
        raise ValueError("Количество исходных и целевых папок должно быть одинаковым.")

    folder_mappings = dict(zip(source_folders, dest_folders))

    # Проверяем наличие токена и чата
    telegram_token = os.getenv('TELEGRAM_TOKEN')
    chat_id = os.getenv('CHAT_ID')
    if not telegram_token or not chat_id:
        raise ValueError("Не указаны TELEGRAM_TOKEN или CHAT_ID.")

    return {
        'FOLDER_MAPPINGS': folder_mappings,
        'TELEGRAM_TOKEN': telegram_token,
        'CHAT_ID': chat_id
    }
