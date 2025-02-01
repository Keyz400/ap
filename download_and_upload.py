# download_and_upload.py

from config_and_init import (
    bot, router, dp, search_results_cache, episode_results_cache, progress_data, url_storage,
    get_driver, clean_ansi_codes, progress_hook
)
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, FSInputFile
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
import asyncio
import yt_dlp
from pyrogram import Client
from pyrogram.enums import ParseMode

async def update_progress(status_msg, url):
    while True:
        data = progress_data.get(url)
        if not data:
            break
        if data['status'] == 'finished':
            await status_msg.edit_text("Download complete! Starting upload...")
            break
        elif data['status'] == 'downloading':
            percent = data.get('_percent_str', '0%')
            speed = data.get('_speed_str', 'N/A')
            eta = data.get('_eta_str', 'N/A')
            message = (
                f"Downloading...\n"
                f"Progress: {percent}\n"
                f"Speed: {speed}\n"
                f"ETA: {eta}"
            )
            try:
                await status_msg.edit_text(message)
            except:
                pass
        await asyncio.sleep(10)

@router.callback_query(F.data.startswith("dl_"))
async def handle_download(callback: CallbackQuery):
    url_key = callback.data.split("_", 1)[1]
    url = url_storage.get(url_key)
    
    if not url:
        await callback.answer("Invalid download link!")
        return
    
    # Remove selection buttons
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    del url_storage[url_key]
    
    status_msg = await callback.message.answer("Starting download...")
    progress_data[url] = {'status': 'starting'}
    update_task = asyncio.create_task(update_progress(status_msg, url))
    
    ydl_opts = {
        'outtmpl': 'downloads/%(title)s.%(ext)s',
        'progress_hooks': [lambda d: progress_hook(d, url)],
        'quiet': True,
    }
    
    try:
        if not os.path.exists('downloads'):
            os.makedirs('downloads')
        
        loop = asyncio.get_event_loop()
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=True))
        
        # Get actual downloaded file path
        if 'entries' in info:
            video_info = info['entries'][0]
        else:
            video_info = info
        
        filename = ydl.prepare_filename(video_info)
        
        progress_data[url]['status'] = 'finished'
        await update_task
        
        if not os.path.exists(filename):
            await status_msg.edit_text("Error: Downloaded file not found.")
            return
        
        file_size = os.path.getsize(filename)
        
        if file_size > 2 * 1024**3:  # 2GB limit
            await status_msg.edit_text("File is too large after download.")
            os.remove(filename)
            return
        
        await status_msg.edit_text("Uploading to Telegram...")
        
        if file_size <= 50 * 1024 * 1024:  # 50MB
            await callback.message.reply_video(
                video=FSInputFile(filename),
                caption="Here's your video!"
            )
        else:
            await pyro_client.send_video(
                chat_id=callback.message.chat.id,
                video=filename,
                caption="Here's your video!",
                parse_mode=ParseMode.MARKDOWN,
                disable_notification=True
            )
        
        os.remove(filename)
        await status_msg.edit_text("Upload complete!")
        
    except Exception as e:
        await status_msg.edit_text(f"An error occurred: {str(e)}")
        if 'filename' in locals() and os.path.exists(filename):
            os.remove(filename)
    finally:
        if url in progress_data:
            del progress_data[url]

async def main():
    await pyro_client.start()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)
    await pyro_client.stop()

if __name__ == "__main__":
    asyncio.run(main())
