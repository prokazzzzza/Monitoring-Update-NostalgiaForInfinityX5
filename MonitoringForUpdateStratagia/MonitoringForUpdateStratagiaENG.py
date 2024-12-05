from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackContext, CallbackQueryHandler
from datetime import datetime, timedelta
from dotenv import load_dotenv
import requests
import logging
import aiohttp
import asyncio
import pytz
import re
import os

# Setting up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Loading environment variables from .env
load_dotenv()

# Configuration from the .env file
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")  # Telegram bot token
CHAT_ID = os.getenv("CHAT_ID")  # Chat ID for sending messages
FREQTRADE_BOT_TOKEN = os.getenv("FREQTRADE_BOT_TOKEN")  # Freqtrade bot token
FREQTRADE_CHAT_ID = os.getenv("CHAT_ID")  # Chat ID for Freqtrade
FILE_URL = os.getenv("FILE_URL")  # URL for downloading the file
LOCAL_FILE_PATH = os.getenv("LOCAL_FILE_PATH")  # Local file path
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL"))  # Update check interval
LINE_NUMBER = int(os.getenv("LINE_NUMBER"))  # Line number for extracting version
RETRY_LIMIT = int(os.getenv("RETRY_LIMIT"))  # Retry limit for downloading
RETRY_DELAY = int(os.getenv("RETRY_DELAY"))  # Delay between retries
REPO_URL = os.getenv("REPO_URL")  # GitHub repository URL
REMOTE_FILE_PATH = os.getenv("REMOTE_FILE_PATH")  # Path to the file in the repository
TIMEZONE = os.getenv("TIMEZONE")  # Timezone

# Logging incoming messages
async def log_telegram_message(update: Update):
    """Logs incoming messages in Telegram."""
    if update.message:
        logger.info(f"Incoming message from {update.message.from_user.username} ({update.message.from_user.id}): {update.message.text}")
    elif update.callback_query:
        logger.info(f"Incoming callback from {update.callback_query.from_user.username} ({update.callback_query.from_user.id}): {update.callback_query.data}")

# Logging sent messages
def send_telegram_message(token, chat_id, message):
    """Sends a message to Telegram and logs the response."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message}
    response = requests.post(url, json=payload)
    logger.info(f"Sending message: {message}")
    logger.info(f"Response from Telegram API: {response.text}")
    response.raise_for_status()  # Will raise an exception if there is an error

# Function to restart Freqtrade
async def reload_freqtrade(update: Update, context: CallbackContext):
    """Sends a command to restart Freqtrade in another bot."""
    logger.info("Processing the 'Restart Freqtrade' button.")
    try:
        # Sending the restart command
        send_telegram_message(FREQTRADE_BOT_TOKEN, FREQTRADE_CHAT_ID, "/reload_config")
        message = "The Freqtrade restart command has been sent."

        # Check if callback_query exists and send a response
        if update and update.callback_query:
            await update.callback_query.message.reply_text(message)
        else:
            logger.warning("Restart initiated without interaction from Telegram.")

        logger.info("The Freqtrade restart command was successfully sent.")
    except Exception as e:
        logger.error(f"Error sending restart command: {e}")

        # Send an error message if callback_query exists
        if update and update.callback_query:
            await update.callback_query.message.reply_text(f"❌ Failed to send the command: {e}")

# Asynchronous file download with retries
async def download_file_with_retries(url, save_path, retries=RETRY_LIMIT, delay=RETRY_DELAY):
    """Asynchronous version of file download with retries."""
    async with aiohttp.ClientSession() as session:
        for attempt in range(1, retries + 1):
            try:
                logger.info(f"Attempt {attempt}/{retries} to download...")
                async with session.get(url) as response:
                    response.raise_for_status()  # Raises an error on unsuccessful response
                    with open(save_path, "wb") as f:
                        f.write(await response.read())
                logger.info("File downloaded successfully.")
                return
            except Exception as e:
                logger.error(f"Attempt {attempt}/{retries} failed: {e}")
                if attempt < retries:
                    await asyncio.sleep(delay)  # Delay before the next attempt
                else:
                    logger.error("All attempts exhausted.")
                    raise

# Fetch the content of a remote file from GitHub
async def fetch_file_content(repo_url, file_path):
    """Fetches the content of a file from GitHub."""
    api_url = f"https://raw.githubusercontent.com/{repo_url}/main/{file_path}"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(api_url) as response:
                response.raise_for_status()
                return await response.text()
        except Exception as e:
            logger.error(f"Error fetching the file: {e}")
            return None

# Extract the version from the file content
def extract_version_from_content(content):
    """Extracts the version from the file content."""
    try:
        match = re.search(r'return\s+[\'\"](v[\d.]+)[\'\"]', content)
        return match.group(1) if match else "Unknown version"
    except Exception as e:
        logger.error(f"Error extracting version: {e}")
        return "Version extraction error"

# Extract the version from the local file
def extract_version_from_line(file_path, line_number=LINE_NUMBER):
    """Extracts the version from the specified line of the file."""
    if not os.path.exists(file_path):
        return "File not found"
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            lines = file.readlines()
            if len(lines) >= line_number:
                line = lines[line_number - 1].strip()  # Get the 69th line
                match = re.search(r'return\s+[\'\"](v[\d.]+)[\'\"]', line)
                return match.group(1) if match else "Unknown version"
    except Exception as e:
        logger.error(f"Error extracting version: {e}")
    return "Unknown version"

# Get the version of the remote file
async def check_remote_version():
    """Checks the version of the file on GitHub."""
    content = await fetch_file_content(REPO_URL, REMOTE_FILE_PATH)
    if content:
        version = extract_version_from_content(content)
        logger.info(f"Remote file version: {version}")
        return version
    else:
        logger.error("Failed to fetch file content.")
        return "Download error"

# Function to download the file and notify with a restart
async def check_for_updates():
    """Checks for updates on the remote server and downloads the file if an update is found."""
    local_version = extract_version_from_line(LOCAL_FILE_PATH)
    remote_version = await check_remote_version()

    if local_version != remote_version:
        # If the versions don't match, download the new file
        await download_file_with_retries(FILE_URL, LOCAL_FILE_PATH)
        message = f"✅ Update found! New version: {remote_version} successfully downloaded.\n\n Restarting Freqtrade..."
        send_telegram_message(TELEGRAM_TOKEN, CHAT_ID, message)
        logger.info(f"Update downloaded. Local version is now: {remote_version}")

        # After downloading the file, restart Freqtrade
        await reload_freqtrade(None, None)  # Empty values are passed if no specific update is required through Telegram
    else:
        logger.info(f"No updates found. Local version: {local_version}")

# Asynchronous task for periodic update check
async def periodic_update_check():
    """Periodically checks for updates."""
    timezone = pytz.timezone(TIMEZONE)  # Use the timezone from .env
    while True:
        await check_for_updates()  # Check for updates
        # Update the next check time considering the timezone
        next_check_time = datetime.now(timezone) + timedelta(seconds=CHECK_INTERVAL)
        next_check_time_str = next_check_time.strftime('%d-%m-%Y %H:%M:%S')
        
        # Output the next check time to the terminal (Docker)
        logger.info(f"Next update check at: {next_check_time_str}")
        
        await asyncio.sleep(CHECK_INTERVAL)  # Wait for the specified interval

# Version check handler function
async def check_version(update: Update, context: CallbackContext):
    """Checks the current version of the local file and the version on the server (GitHub)."""
    logger.info("Handling 'Check version' button.")

    # Get the version of the local file
    local_version = extract_version_from_line(LOCAL_FILE_PATH)
    logger.info(f"Local version: {local_version}")

    # Get the version of the remote file
    remote_version = await check_remote_version()

    # Compare versions
    if local_version == remote_version:
        version_status = "✅  No updates found"
    else:
        version_status = f"📥  New version found on GitHub: {remote_version}"

    # Format the message
    message = f"Local file version: {local_version}\n" \
              f"Version on server (GitHub): {remote_version}\n" \
              f"{version_status}"

    if update.callback_query:
        await update.callback_query.message.reply_text(message)

# Handler for the "📜 Latest Commits" button
async def check_commits(update: Update, context: CallbackContext):
    """Check commits in the GitHub repository."""
    logger.info("Processing the 'Check Latest Commits' button.")
    commits = await get_commits_from_github(REPO_URL)
    
    # If commits were retrieved
    if commits:
        # Extract the header with the date and the commits
        header = commits[0]
        commits_message = "\n".join(commits[1:])
        commits_message = f"{header}\n{commits_message}"
    else:
        commits_message = "No commits for this period."
    
    if update.callback_query:  # Check if callback_query exists
        logger.info(f"Sending message: {commits_message}")
        await update.callback_query.message.reply_text(commits_message)


async def get_commits_from_github(repo_url):
    """Get commits from the GitHub repository made on the latest date when they were pushed."""
    
    # Construct the URL for the GitHub API request
    api_url = f"https://api.github.com/repos/{repo_url}/commits?per_page=100"  # Fetch 100 commits for analysis
    
    async with aiohttp.ClientSession() as session:
        try:
            # Send the request to GitHub API
            async with session.get(api_url) as response:
                response.raise_for_status()  # Check for successful response status
                
                commits = await response.json()  # Parse the JSON response
                
                if not commits:
                    return ["No commits in the repository."]
                
                # Sort commits by date in descending order
                commits.sort(key=lambda x: x['commit']['author']['date'], reverse=True)
                
                # Get the date of the latest commit
                last_commit_date = datetime.fromisoformat(commits[0]['commit']['author']['date'].replace('Z', '+00:00')).date()
                
                # Extract only those commits made on the last day
                filtered_commits = [
                    commit for commit in commits
                    if datetime.fromisoformat(commit['commit']['author']['date'].replace('Z', '+00:00')).date() == last_commit_date
                ]
                
                # Format the commit list with only the time in the specified timezone
                tz = pytz.timezone(TIMEZONE)  # Get the timezone from the environment variable
                commit_list = [
                    f"{commit['sha'][:7]} {commit['commit']['message']} at {datetime.fromisoformat(commit['commit']['author']['date'].replace('Z', '+00:00')).astimezone(tz).strftime('%H:%M:%S')}" 
                    for commit in filtered_commits
                ]
                
                if not commit_list:
                    return [f"No commits on {last_commit_date}."]

                # Header with emoji and date
                header = f"📜 Latest Commits from {last_commit_date}"
                
                # Return the header and the list of commits
                return [header] + commit_list
        
        except aiohttp.ClientError as e:
            logger.error(f"Error while requesting GitHub API: {e}")
            return ["Error while retrieving commits."]
        except Exception as e:
            logger.error(f"Unknown error: {e}")
            return ["Failed to retrieve commit data."]

# Asynchronous file download from the server
async def download_file(update: Update, context: CallbackContext):
    """Forcibly download the file from the server if the version is outdated."""
    logger.info("Handling 'Download update' button.")
    try:
        # Get the version of the local file
        local_version = extract_version_from_line(LOCAL_FILE_PATH)
        
        # Get the version of the file from the server
        await download_file_with_retries(FILE_URL, LOCAL_FILE_PATH, retries=1, delay=0)
        server_version = extract_version_from_line(LOCAL_FILE_PATH)
        
        if local_version == server_version:
            # If the versions match, notify that no update is needed
            message = f"The local file version ({local_version}) is up to date. No update needed."
            if update.callback_query:  # Check if callback_query exists
                await update.callback_query.message.reply_text(message)
            logger.info("No update needed. Version is up to date.")
        else:
            # If the versions are different, download the new version
            await download_file_with_retries(FILE_URL, LOCAL_FILE_PATH)
            message = f"✅  New version ({server_version}) successfully downloaded!"
            if update.callback_query:  # Check if callback_query exists
                await update.callback_query.message.reply_text(message)
            logger.info("New version successfully downloaded.")
    
    except Exception as e:
        logger.error(f"Error downloading file: {e}")
        if update.callback_query:  # Check if callback_query exists
            await update.callback_query.message.reply_text(f"❌  Failed to download the file: {e}")

# Function to convert time into a readable format
def format_time_interval(seconds):
    """Converts time interval into the format 'hours:minutes:seconds'."""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60
    if hours > 0:
        return f"{hours} hrs {minutes} min {seconds} sec"
    elif minutes > 0:
        return f"{minutes} min {seconds} sec"
    else:
        return f"{seconds} sec"

# Updated start function with new information
async def start(update: Update, context: CallbackContext):
    """Sends a welcome message and buttons for action selection."""
    await log_telegram_message(update)  # Log the incoming message
    logger.info("Bot received the /start command")

    # Get the local file version
    local_version = extract_version_from_line(LOCAL_FILE_PATH)
    
    # Log the local file version
    logger.info(f"Local version: {local_version}")
    
    # Get the server file version
    try:
        server_file_content = await fetch_file_content(REPO_URL, REMOTE_FILE_PATH)
        server_version = extract_version_from_content(server_file_content)
    except Exception as e:
        logger.error(f"Error while downloading file to get the version: {e}")
        server_version = "Failed to get version from server"
    
    # Log the server version
    logger.info(f"Server version: {server_version}")
    
    # Compare the versions
    if local_version == server_version:
        version_status = "✅  No updates found"
    else:
        version_status = f"📥 New version found on GitHub: {server_version}"

    # Convert the interval into a more readable format
    formatted_check_interval = format_time_interval(CHECK_INTERVAL)
    
    # Form the welcome message
    start_message = (
        "🤖 Welcome!\n"
        "This bot is designed for monitoring updates of the NostalgiaForInfinityX5 strategy.\n\n"
        f"📊  Initial Information:\n"
        f"📂  Local file version: {local_version}\n"
        f"🌐  Server version: {server_version}\n"
        f"{version_status}\n"
        f"🕒  Update check interval: {formatted_check_interval}\n\n"
        "📌 Main functions:\n"
        "1️⃣ Check the current file version.\n"
        "2️⃣ Download strategy updates.\n"
        "3️⃣ Display the latest commits from GitHub.\n"
        "4️⃣ Restart Freqtrade after updating.\n\n"
        "Use the buttons below to manage."
    )

    # Send the welcome message and buttons
    keyboard = [
        [InlineKeyboardButton("🔍 Check file version", callback_data='check_version')],
        [InlineKeyboardButton("📥 Download update", callback_data='download_file')],
        [InlineKeyboardButton("📜 Latest commits", callback_data='check_commits')],
        [InlineKeyboardButton("🔄 Restart Freqtrade", callback_data='reload_freqtrade')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        await update.message.reply_text(start_message, reply_markup=reply_markup)

def main():
    """Main function to run the bot and periodically check for updates."""
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Add all handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(check_version, pattern='check_version'))
    application.add_handler(CallbackQueryHandler(download_file, pattern='download_file'))
    application.add_handler(CallbackQueryHandler(check_commits, pattern='check_commits'))
    application.add_handler(CallbackQueryHandler(reload_freqtrade, pattern='reload_freqtrade'))

    # Start the background task to check for updates
    asyncio.get_event_loop().create_task(periodic_update_check())

    # Run the Telegram bot
    application.run_polling()

if __name__ == "__main__":
    main()