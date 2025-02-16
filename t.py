import json
import re
from urllib.parse import quote_plus
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from time import sleep
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from bs4 import BeautifulSoup
import requests

# Initialize Pyrogram client
app = Client(
    "animepahe_bot",
    api_id=4030671,
    api_hash="c1806a30e8c9c69a4a1bb59c28f37318",
    bot_token="7990775956:AAFPn4NE7HJcKxPkHI6f9EldeR3PUMplzNY"
)

# Global variables to store user states
user_data = {}

class AnimePaheClient:
    '''
    Anime Client for AnimePahe site
    '''
    def __init__(self, config):
        self.base_url = config.get('base_url', 'https://animepahe.ru/')
        self.search_url = self.base_url + config.get('search_url', 'api?m=search&q=')
        self.episodes_list_url = self.base_url + config.get('episodes_list_url', 'api?m=release&sort=episode_asc&id=')
        self.download_link_url = self.base_url + config.get('download_link_url', 'api?m=links&p=kwik&id=')
        self.episode_url = self.base_url + config.get('episode_url', 'play/{anime_id}/{episode_id}')
        self.anime_id = ''  # anime id. required to create referer link
        self.selector_strategy = config.get('alternate_resolution_selector', 'lowest')
        self.hls_size_accuracy = config.get('hls_size_accuracy', 0)
        self.request_timeout = config.get('request_timeout', 10)
        self.session = requests.Session()

    def _get_new_cookies(self, url, check_condition, max_retries=3, wait_time_in_secs=5):
        chrome_options = Options()
        chrome_options.add_argument("--headless")  # Run Chrome in headless mode
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        
        # Use webdriver_manager to automatically manage ChromeDriver
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        driver.get(url)
        retry_cnt = 1
        while retry_cnt <= max_retries:
            try:
                driver.find_element(By.XPATH, check_condition)
                break
            except NoSuchElementException:
                retry_cnt += 1
                sleep(wait_time_in_secs)
        if retry_cnt > max_retries:
            driver.quit()
            raise Exception(f'Failed to load site within {max_retries * wait_time_in_secs} seconds')
        all_cookies = driver.get_cookies()
        driver.quit()
        cookies = {}
        for cookie in all_cookies:
            cookies[cookie['name']] = cookie['value']
        return cookies

    def _get_site_cookies(self, url):
        cookies = self.session.cookies.get_dict()
        if cookies:
            resp = self.session.get(url, cookies=cookies)
            if resp.status_code == 200:
                return cookies
        cookies = self._get_new_cookies(url, '/html/body/header/nav/a/img')
        self.session.cookies.update(cookies)
        return cookies

    def search(self, keyword, search_limit=10):
        self.cookies = self._get_site_cookies(self.base_url)
        search_key = quote_plus(keyword)
        search_url = self.search_url + search_key
        response = self.session.get(search_url, cookies=self.cookies).json()
        response = response['data'] if response['total'] > 0 else None
        if response is not None:
            response = {idx + 1: result for idx, result in enumerate(response)}
        return response

    def fetch_episodes_list(self, target):
        session = target.get('session')
        episodes_data = []
        self.anime_id = session
        list_episodes_url = self.episodes_list_url + session
        raw_data = self.session.get(list_episodes_url, cookies=self.cookies).json()
        last_page = int(raw_data['last_page'])
        episodes_data = raw_data['data']
        if last_page > 1:
            for pgno in range(2, last_page + 1):
                episodes_data.extend(self.session.get(f'{list_episodes_url}&page={pgno}', cookies=self.cookies).json().get('data', []))
        return episodes_data

    def fetch_episode_links(self, episodes, ep_ranges):
        download_links = {}
        ep_start, ep_end, specific_eps = ep_ranges['start'], ep_ranges['end'], ep_ranges.get('specific_no', [])
        for episode in episodes:
            if (float(episode.get('episode')) >= ep_start and float(episode.get('episode')) <= ep_end) or (float(episode.get('episode')) in specific_eps):
                episode_link = self.episode_url.format(anime_id=self.anime_id, episode_id=episode.get('session'))
                links = self._get_kwik_links_v2(episode_link)
                if links is None:
                    continue
                download_links[episode.get('episode')] = links
        return download_links

    def _get_kwik_links_v2(self, ep_link):
        response = self.session.get(ep_link, cookies=self.cookies)
        soup = BeautifulSoup(response.text, 'html.parser')
        links = soup.select('div#resolutionMenu button')
        sizes = soup.select('div#pickDownload a')
        resolutions = {}
        for l, s in zip(links, sizes):
            resltn = l['data-resolution']
            current_audio = l['data-audio']
            current_codec = l['data-av1']
            if resltn in resolutions and current_codec != '1':
                continue
            if current_audio == 'eng':
                continue
            resolutions[resltn] = {
                'kwik': l['data-src'],
                'audio': current_audio,
                'codec': current_codec,
                'filesize': s.text.strip()
            }
        return resolutions

    def fetch_m3u8_links(self, target_links, resolution, episode_prefix):
        get_ep_name = lambda resltn: f"{episode_prefix}{' ' if episode_prefix.lower().endswith('movie') and len(target_links.items()) <= 1 else f' {ep} '}- {resltn}P.mp4"
        final_dict = {}
        for ep, link in target_links.items():
            buttons = []
            for res, res_data in link.items():
                kwik_link = res_data['kwik']
                raw_content = self.get_m3u8_content(kwik_link, ep)
                ep_link = self.parse_m3u8_link(raw_content)
                buttons.append({
                    'quality': res,
                    'link': ep_link
                })
            final_dict[ep] = buttons
        return final_dict

    def get_m3u8_content(self, kwik_link, ep_no):
        referer_link = kwik_link
        response = self.session.get(kwik_link, headers={'Referer': referer_link})
        return response.text

    def parse_m3u8_link(self, text):
        x = r"\}\('(.*)'\)*,*(\d+)*,*(\d+)*,*'((?:[^'\\]|\\.)*)'\.split\('\|'\)*,*(\d+)*,*(\{\})"
        p, a, c, k, e, d = re.findall(x, text)[0]
        p, a, c, k, e, d = p, int(a), int(c), k.split('|'), int(e), {}
        def e(c):
            x = '' if c < a else e(int(c / a))
            c = c % a
            return x + (chr(c + 29) if c > 35 else '0123456789abcdefghijklmnopqrstuvwxyz'[c])
        for i in range(c): d[e(i)] = k[i] or e(i)
        parsed_js_code = re.sub(r'\b(\w+)\b', lambda e: d.get(e.group(0)) or e.group(0), p)
        parsed_link = re.search(r'http.*\.m3u8', parsed_js_code).group(0)
        return parsed_link

# Add /start command
@app.on_message(filters.command("start"))
def start(client, message):
    message.reply_text(
        "👋 Hi! I'm AnimePahe Bot. Use /search <anime_name> to find anime episodes and download links."
    )

# Add /help command
@app.on_message(filters.command("help"))
def help(client, message):
    message.reply_text(
        "📚 **Commands:**\n"
        "- /start: Start the bot\n"
        "- /help: Show this help message\n"
        "- /search <anime_name>: Search for anime\n\n"
        "Example: `/search one piece`"
    )

@app.on_message(filters.command("search"))
def search_anime(client, message):
    name = " ".join(message.command[1:])
    if not name:
        return message.reply_text("Please provide an anime name 🛑 \n\nExample: `/search one piece`")
    
    # Send waiting message
    wait_msg = message.reply_text("🔍 Searching... Please wait")
    try:
        results = anime_pahe_client.search(name)
        # Delete waiting message after fetching results
        client.delete_messages(message.chat.id, wait_msg.id)
        
        if not results:
            return message.reply_text("No results for your search 🫤 Try using a different keyword or spelling.")
        
        user_data[message.from_user.id] = {
            "results": results,
            "page": 0,
            "message_id": message.id,
            "active_requests": 0
        }
        show_search_results(message.from_user.id, message)
    except Exception as e:
        client.delete_messages(message.chat.id, wait_msg.id)
        message.reply_text(f"An error occurred: {str(e)}")

def show_search_results(user_id, message):
    data = user_data[user_id]
    page = data["page"]
    results = data["results"]
    start_idx = page * 10
    end_idx = start_idx + 10
    keyboard = [
        [InlineKeyboardButton(f"{i}. {item['title']}", callback_data=f"select_{start_idx + i - 1}")]
        for i, item in enumerate(list(results.values())[start_idx:end_idx], 1)
    ]
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("◀️ Back", callback_data="search_back"))
    if end_idx < len(results):
        nav_buttons.append(InlineKeyboardButton("Next ▶️", callback_data="search_next"))
    if nav_buttons:
        keyboard.append(nav_buttons)
    reply_markup = InlineKeyboardMarkup(keyboard)
    try:
        app.edit_message_text(
            chat_id=message.chat.id,
            message_id=user_data[user_id]["message_id"],
            text=f"Search results (Page {page + 1}):",
            reply_markup=reply_markup
        )
    except Exception as e:
        new_message = message.reply_text(f"Search results (Page {page + 1}):", reply_markup=reply_markup)
        user_data[user_id]["message_id"] = new_message.id

@app.on_callback_query()
def handle_callback(client, callback):
    user_id = callback.from_user.id
    data = callback.data
    if user_id not in user_data:
        return callback.answer("Session expired ⏳ Start over", show_alert=True)
    try:
        if data.startswith("select_"):
            index = int(data.split("_")[1])
            selected_anime = list(user_data[user_id]["results"].values())[index]
            try:
                episodes = anime_pahe_client.fetch_episodes_list({"session": selected_anime["session"]})
                user_data[user_id].update({
                    "episodes": episodes,
                    "page": 0,
                    "selected_anime": selected_anime["title"],
                    "message_id": callback.message.id
                })
                show_episodes(user_id, callback)
            except Exception as e:
                callback.message.reply_text(f"An error occurred: {str(e)}")
        elif data.startswith("episode_"):
            user_data[user_id]["active_requests"] += 1
            index = int(data.split("_")[1])
            selected_episode = user_data[user_id]["episodes"][index]
            wait_msg = callback.message.reply_text("⏳ Fetching download links...")
            try:
                target_links = anime_pahe_client.fetch_episode_links([selected_episode], {"start": selected_episode["episode"], "end": selected_episode["episode"]})
                resolution = 1080  # Default resolution
                episode_prefix = f"{user_data[user_id]['selected_anime']} Episode"
                final_links = anime_pahe_client.fetch_m3u8_links(target_links, resolution, episode_prefix)
                
                buttons = []
                for ep, qualities in final_links.items():
                    for quality in qualities:
                        buttons.append([
                            InlineKeyboardButton(
                                f"📥 {quality['quality']}p Download",
                                url=quality['link']
                            )
                        ])
                if buttons:
                    callback.message.reply_text(
                        f"**🔗 Download links for Episode {selected_episode['episode']}:**",
                        reply_markup=InlineKeyboardMarkup(buttons)
                    )
                else:
                    callback.message.reply_text("⚠️ No valid download links found")
            except Exception as e:
                callback.message.reply_text(f"An error occurred: {str(e)}")
            finally:
                client.delete_messages(callback.message.chat.id, wait_msg.id)
                user_data[user_id]["active_requests"] -= 1
        elif data in ["search_back", "search_next"]:
            user_data[user_id]["page"] += -1 if data == "search_back" else 1
            show_search_results(user_id, callback.message)
        elif data in ["episodes_back", "episodes_next"]:
            user_data[user_id]["page"] += -1 if data == "episodes_back" else 1
            show_episodes(user_id, callback)
    except Exception as e:
        callback.message.reply_text(f"An unexpected error occurred: {str(e)}")
    finally:
        callback.answer()

def show_episodes(user_id, callback):
    data = user_data[user_id]
    page = data["page"]
    episodes = data["episodes"]
    start_idx = page * 10
    end_idx = start_idx + 10
    keyboard = [
        [InlineKeyboardButton(f"Episode {ep['episode']}", callback_data=f"episode_{start_idx + i - 1}")]
        for i, ep in enumerate(episodes[start_idx:end_idx], 1)
    ]
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("◀️ Back", callback_data="episodes_back"))
    if end_idx < len(episodes):
        nav_buttons.append(InlineKeyboardButton("Next ▶️", callback_data="episodes_next"))
    if nav_buttons:
        keyboard.append(nav_buttons)
    reply_markup = InlineKeyboardMarkup(keyboard)
    try:
        app.edit_message_text(
            chat_id=callback.message.chat.id,
            message_id=callback.message.id,
            text=f"Selected: {data['selected_anime']}\nEpisodes (Page {page + 1}):",
            reply_markup=reply_markup
        )
    except Exception as e:
        print(f"Error updating episodes: {e}")

if __name__ == "__main__":
    # Initialize AnimePaheClient
    anime_pahe_client = AnimePaheClient(config={
        "base_url": "https://animepahe.ru/",
        "search_url": "api?m=search&q=",
        "episodes_list_url": "api?m=release&sort=episode_asc&id=",
        "download_link_url": "api?m=links&p=kwik&id=",
        "episode_url": "play/{anime_id}/{episode_id}",
        "request_timeout": 10
    })
    app.run()
