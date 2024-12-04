# 📜 Monitoring-Update-NostalgiaForInfinityX5

Этот проект предназначен для мониторинга обновлений стратегии в репозитории GitHub https://github.com/iterativv/NostalgiaForInfinity автоматического обновления при появлении новой версии и отправки уведомлений через Telegram, а также перезапуск Freqtrade после скачивания новой версии или в ручном режиме через бота.

---
[![photo_2024-12-04_17-36-09.jpg](https://s.iimg.su/s/04/th_2Gm2kxzvQvCAL4eksNXSvUAue3GcKsQdQxFL7Pdq.jpg)](https://iimg.su/i/YNlCg)
[![photo_2024-12-04_17-36-14.jpg](https://s.iimg.su/s/04/th_uVfvFd9iFf4NHCri4sODIlPaW0YUBjUoomyooZKz.jpg)](https://iimg.su/i/UjZpV)

## 🧑‍💻 Установка и настройка

### 1. 🔥 Клонирование репозитория

Для начала, клонируйте репозиторий проекта на свой ПК:

```bash
git clone https://github.com/prokazzzzza/Monitoring-Update-NostalgiaForInfinityX5.git
cd Monitoring-Update-NostalgiaForInfinityX5
```
### 2. ⚙️ Настройка файла .env
В корневой папке репозитория есть файл Example.env. Переименуйте его в .env и настройте параметры.
```bash
mv Example.env .env
```
Отредактируйте файл .env, заменив переменные на свои значения:

# 🐳 Запуск проекта в Docker
Этот проект использует [Docker](https://www.docker.com/) для изоляции среды. Для запуска в Docker выполните следующие шаги.

### 1. Убедитесь, что у вас установлен Docker. Если нет, следуйте официальной инструкции по установке Docker.

### 2. В корне проекта выполните команду для сборки Docker-образа:
```bash
docker build -t monitoring-update-nostalgia .
```
### 3. Запустите Docker-контейнер:
```bash
docker run --env-file .env monitoring-update-nostalgia
```
# 📁 Структура проекта
Проект состоит из нескольких файлов и папок, важные из которых:

Dockerfile — описание конфигурации для сборки Docker-образа.
.env — конфигурационный файл, в котором настраиваются параметры для работы с проектом (токены, пути и т.д.).
Update/ — папка для хранения загруженных обновлений стратегии.
monitor_update.py — основной скрипт, который отслеживает обновления стратегии и отправляет уведомления в Telegram.

# ⚡ Как работает скрипт
### Мониторинг обновлений стратегии:

Скрипт периодически проверяет репозиторий GitHub на наличие изменений в файле стратегии, используя указанный FILE_URL.
Если версия стратегии изменяется, файл обновляется в локальной папке LOCAL_FILE_PATH.
Если обновление найдено, скрипт отправляет уведомление в Telegram.

### Автоматическая перезагрузка Freqtrade:

После того как обновление стратегии будет обнаружено и файл будет скачан, скрипт автоматически отправляет команду на перезагрузку бота Freqtrade с использованием Telegram-бота 🤖.
Для этого используется токен, указанный в переменной FREQTRADE_BOT_TOKEN. Бот отправляет команду на перезагрузку стратегии, чтобы новая версия вступила в силу.
Использование Freqtrade:

С помощью Telegram-бота можно проверять новую версию стратегии, просматривать коммиты скачаной стратегии, а так же перезапускать Freqtrade.

# ⏲️ Настройка интервала обновлений
В .env файле вы можете настроить переменную CHECK_INTERVAL, которая определяет, как часто будет проверяться обновление стратегии. Рекомендуется устанавливать значение в пределах нескольких минут.

# 📊 Логирование
Все лог-сообщения будут выводиться в консоль Docker-контейнера.
После выполнения всех шагов ваш проект будет настроен для мониторинга обновлений стратегии с использованием Docker и Telegram, с автоматическим перезапуском Freqtrade при обновлении стратегии.

### Если возникнут вопросы, не стесняйтесь обращаться! ✉️
