# bot_handlers.py

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

@router.message(Command("start"))
async def start_command(message: Message):
    await message.reply("Welcome! Send me a URL, and I'll try to find the download link for you.\n\n"
                        "You can also search for anime episodes using /search <anime_name>")

@router.message(Command("search"))
async def search_anime(message: Message):
    query = message.text.replace("/search", "").strip()
    if not query:
        await message.reply("Please enter an anime name. Example:\n`/search One Piece`", parse_mode="Markdown")
        return

    search_url = f"https://www.gogoanime3.net/search.html?keyword={query.replace(' ', '%20')}"
    try:
        scraper = cloudscraper.create_scraper()
        response = scraper.get(search_url)
        if response.status_code != 200:
            await message.reply("Failed to fetch search results. Try again later.")
            return

        soup = BeautifulSoup(response.content, "html.parser")
        search_results = soup.select("div.last_episodes > ul > li")
        if not search_results:
            await message.reply("No anime found with that name. Try a different keyword.")
            return

        anime_list = [(result.a["title"].strip(), "https://www.gogoanime3.net" + result.a["href"]) for result in search_results]
        user_id = message.from_user.id
        search_results_cache[user_id] = anime_list
        await send_search_results(message, user_id, page=0)

    except Exception as e:
        await message.reply(f"An error occurred: {e}")

async def send_search_results(message, user_id, page=0, edit=False):
    if user_id not in search_results_cache:
        await message.reply("No search results found. Try searching again.")
        return

    results = search_results_cache[user_id]
    per_page = 5
    paginated_results = results[page * per_page : (page + 1) * per_page]

    keyboard = InlineKeyboardBuilder()
    for title, link in paginated_results:
        anime_id = link.split("/")[-1]
        keyboard.button(text=title, callback_data=f"anime_{anime_id}")

    keyboard.adjust(1)
    navigation_buttons = []
    if page > 0:
        navigation_buttons.append(InlineKeyboardButton(text="⬅️ Back", callback_data=f"page_{user_id}_{page-1}"))
    if (page + 1) * per_page < len(results):
        navigation_buttons.append(InlineKeyboardButton(text="➡️ Next", callback_data=f"page_{user_id}_{page+1}"))
    
    keyboard.row(*navigation_buttons)

    if edit:
        await message.edit_text("🔍 **Search Results:**", reply_markup=keyboard.as_markup(), parse_mode="Markdown", disable_web_page_preview=True)
    else:
        await message.reply("🔍 **Search Results:**", reply_markup=keyboard.as_markup(), parse_mode="Markdown", disable_web_page_preview=True)

@router.callback_query(F.data.startswith("page_"))
async def search_pagination(callback: CallbackQuery):
    _, user_id, page = callback.data.split("_")
    if int(user_id) == callback.from_user.id:
        await send_search_results(callback.message, callback.from_user.id, int(page), edit=True)
        await callback.answer()

@router.callback_query(F.data.startswith("anime_"))
async def fetch_episodes(callback: CallbackQuery):
    anime_id = callback.data.split("_")[1]
    anime_url = f"https://www.gogoanime3.net/category/{anime_id}"

    try:
        scraper = cloudscraper.create_scraper()
        response = scraper.get(anime_url)
        if response.status_code != 200:
            await callback.answer("Failed to fetch episode list. Try again later.")
            return

        soup = BeautifulSoup(response.content, "html.parser")
        episode_links = soup.select("ul#episode_page > li > a")
        if not episode_links:
            await callback.answer("No episodes found for this anime.")
            return

        start_ep, end_ep = int(episode_links[0]["ep_start"]), int(episode_links[-1]["ep_end"])
        episodes = [(f"Episode {i}", f"https://www.gogoanime3.net/{anime_id}-episode-{i}") for i in range(max(1, start_ep), end_ep + 1)]
        user_id = callback.from_user.id
        episode_results_cache[user_id] = episodes
        await send_episode_results(callback, user_id, anime_id, page=0)
        await callback.answer()

    except Exception as e:
        await callback.answer(f"An error occurred: {e}")

async def send_episode_results(callback, user_id, anime_id, page=0):
    if user_id not in episode_results_cache:
        await callback.message.edit_text("No episode data found. Try again.")
        return

    episodes = episode_results_cache[user_id]
    per_page = 5
    paginated_episodes = episodes[page * per_page : (page + 1) * per_page]

    keyboard = InlineKeyboardBuilder()
    for title, link in paginated_episodes:
        episode_id = link.split("/")[-1]
        keyboard.button(text=title, callback_data=f"bypass_{episode_id}")

    keyboard.adjust(1)
    navigation_buttons = []
    if page > 0:
        navigation_buttons.append(InlineKeyboardButton(text="⬅️ Back", callback_data=f"ep_{anime_id}_{page-1}"))
    if (page + 1) * per_page < len(episodes):
        navigation_buttons.append(InlineKeyboardButton(text="➡️ Next", callback_data=f"ep_{anime_id}_{page+1}"))

    keyboard.row(*navigation_buttons)
    await callback.message.edit_reply_markup(reply_markup=keyboard.as_markup())

@router.callback_query(F.data.startswith("ep_"))
async def episode_pagination(callback: CallbackQuery):
    _, anime_id, page = callback.data.split("_")
    await send_episode_results(callback, callback.from_user.id, anime_id, int(page))
    await callback.answer()

@router.callback_query(F.data.startswith("bypass_"))
async def bypass_episode_link(callback: CallbackQuery):
    episode_id = callback.data.split("_")[1]
    episode_url = f"https://www.gogoanime3.net/{episode_id}"

    try:
        response = requests.get(episode_url, timeout=10)
        if response.status_code != 200:
            await callback.answer("Failed to retrieve the episode page.")
            return

        soup = BeautifulSoup(response.content, 'html.parser')
        found_link = None
        for link in soup.find_all('a', href=True):
            href = link['href']
            if href.startswith('https://s3embtaku.pro/download'):
                found_link = urljoin(episode_url, href)
                break

        if not found_link:
            await callback.message.reply("No direct download link found.")
            return

        driver = get_driver()
        try:
            driver.get(found_link)
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.XPATH, "//div[@id='content-download']//a[contains(@href,'download.php')]"))
            )

            elements = driver.find_elements(By.XPATH, "//div[@id='content-download']//a[contains(@href,'download.php')]")
            download_links = []
            
            for elem in elements:
                href = elem.get_attribute("href")
                link_text = elem.text
                quality_match = re.search(r'(\d{3,4}p)', link_text, re.IGNORECASE)
                quality = quality_match.group(1).upper() if quality_match else "Unknown"
                download_links.append((quality, href))

            if download_links:
                keyboard = InlineKeyboardBuilder()
                for quality, url in download_links:
                    url_key = str(uuid.uuid4())
                    url_storage[url_key] = url
                    keyboard.button(text=quality, callback_data=f"dl_{url_key}")
                keyboard.adjust(2)
                await callback.message.reply("Select quality:", reply_markup=keyboard.as_markup())
            else:
                await callback.message.reply("No download links found on the page.")

        except Exception as e:
            await callback.message.reply(f"Error extracting links: {str(e)}")

    except Exception as e:
        await callback.message.reply(f"An error occurred: {e}")
