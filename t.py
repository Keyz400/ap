import asyncio
import sys
import re
from datetime import datetime
from urllib.parse import urlparse
from playwright.async_api import async_playwright
from loguru import logger
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# Configuration
ANIME_HOST = "https://www3.animeflv.net"
TOKEN = "7466027003:AAFDFPQ3KWhZZb5cCDanOiE0cLES7Z6bTrY"
TIMEOUT = 30000
CONCURRENT_APP = 32
CONCURRENT_PER_REQUEST = 4
USER_STATES = {}
global_semaphore = asyncio.Semaphore(CONCURRENT_APP)

# Utility functions
def get_order_idx(tab_names):
    priority = ["Mediafire", "Mega", "Google Drive", "Streamtape"]
    for p in priority:
        for idx, tab in enumerate(tab_names):
            if p.lower() in tab["title"].lower():
                return idx
    return 0

async def close_not_allowed_popups(page):
    try:
        await page.close()
    except Exception:
        pass

def parse_episode_range(range_str):
    if "-" in range_str:
        start, end = map(int, range_str.split("-"))
        return range(start, end + 1)
    return [int(range_str)]

# Link extraction functions
async def get_streamtape_download_link(search_page, link):
    await search_page.goto(link)
    await search_page.wait_for_selector("#videolink", timeout=TIMEOUT)
    script = await search_page.content()
    match = re.search(r"document\.getElementById\(.*?\)\.innerHTML = (.*?)\s", script)
    if match:
        content = match.group(1).replace("'", "").split("+")[1]
        return f"https:{content.strip()}"
    return None

async def get_mediafire_link(page):
    frame = page.frames[1]
    await frame.wait_for_selector("a#downloadButton", timeout=TIMEOUT)
    return await frame.get_attribute("a#downloadButton", "href")

async def get_mega_link(page):
    await page.wait_for_selector("a.mega-button", timeout=TIMEOUT)
    return await page.get_attribute("a.mega-button", "href")

async def get_gdrive_link(page):
    await page.wait_for_selector("a.btn.btn-primary", timeout=TIMEOUT)
    return await page.get_attribute("a.btn.btn-primary", "href")

get_tab_download_link = {
    "mediafire": get_mediafire_link,
    "mega": get_mega_link,
    "google drive": get_gdrive_link,
}

# Core scraping functions
async def get_streaming_links(anime: str, last_episode=None):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)  # Ensure headless mode is enabled
        page = await browser.new_page()
        await page.goto(f"{ANIME_HOST}/anime/{anime}")
        episodes_box = await page.wait_for_selector("#episodeList", timeout=TIMEOUT)

        all_episodes = []
        while True:
            current_episodes = await episodes_box.query_selector_all("li.fa-play-circle:not(.Next)")
            if len(current_episodes) > len(all_episodes):
                all_episodes = current_episodes
                await episodes_box.evaluate("element => element.scrollBy(0, element.scrollHeight)")
                await page.wait_for_timeout(500)
            else:
                break

        episodes_info = []
        for episode in all_episodes:
            a_element = await episode.query_selector("a")
            p_element = await a_element.query_selector("p")
            episode_name = await p_element.inner_text()
            episode_link = await a_element.get_attribute("href")
            episodes_info.append({
                "link": f"{ANIME_HOST}{episode_link}",
                "name": episode_name,
            })

        await browser.close()
        return episodes_info[::-1]

async def get_single_episode_download_link(episode_link: str):
    async with global_semaphore:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)  # Ensure headless mode is enabled
            context = await browser.new_context(ignore_https_errors=True)
            page = await context.new_page()
            page.on("popup", close_not_allowed_popups)
            search_page = await context.new_page()
            search_page.on("popup", close_not_allowed_popups)

            await page.goto(episode_link)
            download_table = await page.wait_for_selector("table.Dwnl", timeout=TIMEOUT)
            download_options = await download_table.query_selector_all("a")
            download_links = [await option.get_attribute("href") for option in download_options]

            for link in download_links:
                if "streamtape" in link:
                    parsed_link = await get_streamtape_download_link(search_page, link)
                    if parsed_link:
                        await context.close()
                        return {"service": "streamtape", "link": parsed_link}

            navbar = await page.wait_for_selector("ul[role='tablist']", timeout=TIMEOUT)
            tabs = await navbar.query_selector_all("li")
            tab_names = [{
                "title": await tab.get_attribute("title"),
                "tab": await tab.query_selector("a"),
            } for tab in tabs]

            for idx in [get_order_idx(tab_names)]:
                try:
                    service = tab_names[idx]["title"]
                    await tab_names[idx]["tab"].click()
                    download_link = await get_tab_download_link.get(service.lower(), lambda *_: None)(page)
                    if download_link:
                        await context.close()
                        return {"service": service, "link": download_link}
                except Exception:
                    continue

            await context.close()
            return None

# Telegram bot components
def create_episode_keyboard(episodes):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(ep["name"], callback_data=f"ep_{idx}")]
        for idx, ep in enumerate(episodes)
    ])

def create_search_keyboard(results):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(res["title"], callback_data=f"anime_{res['id']}")]
        for res in results
    ])

async def search_anime(query):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)  # Ensure headless mode is enabled
        page = await browser.new_page()
        await page.goto(f"{ANIME_HOST}/browse?q={query}")
        await page.wait_for_selector(".List-Animes", timeout=TIMEOUT)
        articles = await page.query_selector_all("article.Anime")
        
        results = []
        for article in articles:
            link = await article.query_selector("a")
            href = await link.get_attribute("href")
            title = await (await article.query_selector("h3.Title")).inner_text()
            results.append({"id": href.split("/")[-1], "title": title})
        
        await browser.close()
        return results

# Telegram handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 Welcome to AnimeFLV Downloader!\nUse /search <anime_name> to find anime")

async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args)
    if not query:
        return await update.message.reply_text("❌ Please provide a search query")
    
    try:
        results = await search_anime(query)
        if not results:
            return await update.message.reply_text("❌ No results found")
        
        USER_STATES[update.effective_user.id] = {"results": results}
        await update.message.reply_text(
            "🔍 Search Results:",
            reply_markup=create_search_keyboard(results)
        )
    except Exception as e:
        logger.error(f"Search error: {e}")
        await update.message.reply_text("❌ Search failed. Please try again.")

async def handle_anime_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    anime_id = query.data.split("_")[1]
    user_id = query.from_user.id
    
    try:
        episodes = await get_streaming_links(anime_id)
        if not episodes:
            return await query.edit_message_text("❌ No episodes available")
        
        USER_STATES[user_id] = {"episodes": episodes}
        await query.edit_message_text(
            f"📺 Available Episodes ({len(episodes)}):",
            reply_markup=create_episode_keyboard(episodes)
        )
    except Exception as e:
        logger.error(f"Episodes error: {e}")
        await query.edit_message_text("❌ Failed to fetch episodes")

async def handle_episode_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    ep_idx = int(query.data.split("_")[1])
    episodes = USER_STATES.get(user_id, {}).get("episodes")
    
    if not episodes or ep_idx >= len(episodes):
        return await query.edit_message_text("❌ Invalid episode selection")
    
    try:
        episode = episodes[ep_idx]
        download_info = await get_single_episode_download_link(episode["link"])
        if not download_info:
            return await query.edit_message_text("❌ No download links found")
        
        message = (
            f"📺 {episode['name']}\n"
            f"🔗 {download_info['service']} Link:\n"
            f"<code>{download_info['link']}</code>"
        )
        await query.edit_message_text(message, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Download error: {e}")
        await query.edit_message_text("❌ Failed to get download link")

# Bot setup
async def main():
    logger.remove(0)
    logger.add(sys.stdout, format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{message}</cyan>", level="INFO")
    
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("search", search))
    app.add_handler(CallbackQueryHandler(handle_anime_select, pattern="^anime_"))
    app.add_handler(CallbackQueryHandler(handle_episode_select, pattern="^ep_"))
    
    logger.info("Bot started")
    await app.run_polling()

# Handle event loop if it's already running
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except RuntimeError as e:
        if str(e) == "This event loop is already running":
            loop = asyncio.get_event_loop()
            loop.run_until_complete(main())
        else:
            raise e
