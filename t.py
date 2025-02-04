import requests
from colorama import Fore, Style, init
from typing import List, Dict
import json
import os
from bs4 import BeautifulSoup
import re
import threading
import queue
from pathlib import Path
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
import sqlite3

# Load setup configuration
f = open("setup.json", "r")
setup = json.load(f)
f.close()
base_url = setup["gogoanime_main"]
download_folder = setup["downloads"]
captcha_v3 = setup["captcha_v3"]
download_quality = int(setup["download_quality"])
max_threads = setup["max_threads"]
max_requests_per_user = setup.get("max_requests_per_user", 3)
send_all_qualities = setup.get("send_all_qualities", True)
init(autoreset=True)

# Initialize Pyrogram client
app = Client(
    "anime_downloader_bot",
    api_id=28442198,
    api_hash="c713058e2c450270587dad1b09b3c80c",
    bot_token="7695062653:AAFyOBVXbZFV1OfmbCY5P5G9_2hmwRaARz4"
)

# Global variables to store user states
user_data = {}

def download_link(link):
    soup = BeautifulSoup(requests.get(link).text, "html.parser")
    base_download_url = BeautifulSoup(str(soup.find("li", {"class": "dowloads"})), "html.parser").a.get("href")
    id = base_download_url[base_download_url.find("id=") + 3:base_download_url.find("&typesub")]
    base_download_url = base_download_url[:base_download_url.find("id=")]
    title = BeautifulSoup(requests.post(f"{base_download_url}&id={id}").text, "html.parser")
    title = clean_filename(title.find("span", {"id": "title"}).text)
    response = requests.post(f"{base_download_url}&id={id}&captcha_v3={captcha_v3}")
    soup = BeautifulSoup(response.text, "html.parser")
    links = []
    for i in soup.find_all("div", {"class": "dowload"}):
        if str(BeautifulSoup(str(i), "html.parser").a).__contains__('download=""'):
            link = (BeautifulSoup(str(i), "html.parser").a.get("href"))
            quality = BeautifulSoup(str(i), "html.parser").a.string.replace(" ", "").replace("Download", "")
            try:
                quality = int(quality[2:quality.find("P")])
            except ValueError:
                quality = 0
            links.append({"quality": quality, "link": link})
    return links, title

def clean_filename(filename):
    return re.sub(r'[\\/*?:"<>|]', '¬ß', filename)

def get_names(response):
    return [[i.p.a.get("title"), i.p.a.get("href")] for i in response.find("ul", {"class": "items"}).find_all("li")]

def search(name: str):
    response = BeautifulSoup(requests.get(f"{base_url}/search.html?keyword={name}").text, "html.parser")
    try:
        pages = response.find("ul", {"class": "pagination-list"}).find_all("li")
        return [anime for page in pages for anime in get_names(
            BeautifulSoup(requests.get(f"{base_url}/search.html{page.a.get('href')}").text, "html.parser"))]
    except AttributeError:
        return get_names(response)

def create_links(anime: tuple):
    response = BeautifulSoup(requests.get(f"{base_url}{anime[1]}").text, "html.parser")
    base_url_cdn_api = re.search(r"base_url_cdn_api\s*=\s*'([^']*)'", str(response.find("script", {"src": ""}))).group(1)
    movie_id = response.find("input", {"id": "movie_id"}).get("value")
    last_ep = response.find("ul", {"id": "episode_page"}).find_all("a")[-1].get("ep_end")
    episodes_response = BeautifulSoup(
        requests.get(f"{base_url_cdn_api}ajax/load-list-episode?ep_start=0&ep_end={last_ep}&id={movie_id}").text,
        "html.parser").find_all("a")
    return [{
        "episode": re.search(r"</span>(.*?)</div", str(ep.find("div"))).group(1),
        "url": f'{base_url}{ep.get("href").replace(" ", "")}'
    } for ep in reversed(episodes_response)]

@app.on_message(filters.command("start"))
def start(client, message):
    message.reply_text("Welcome 🍎 \nTo the Anime Download Bot!\n\nSearch for and download anime using the command `/search <anime_name>`. \n\nExample: `/search one piece`")

@app.on_message(filters.command("search"))
def search_anime(client, message):
    name = " ".join(message.command[1:])
    if not name:
        return message.reply_text("Please provide an anime name 🛑 \n\nExample: `/search one piece`")
    
    # Send and track waiting message
    wait_msg = message.reply_text("🔍 Searching... Please wait")
    
    animes = search(name)
    
    # Delete waiting message
    client.delete_messages(message.chat.id, wait_msg.id)
    
    if not animes:
        return message.reply_text("No results for your search 🫤 Try using a different keyword or spelling.")
    
    user_data[message.from_user.id] = {
        "animes": animes,
        "page": 0,
        "message_id": message.id,
        "active_requests": 0
    }
    show_search_results(message.from_user.id, message)

def show_search_results(user_id, message):
    data = user_data[user_id]
    page = data["page"]
    animes = data["animes"]
    start_idx = page * 10
    end_idx = start_idx + 10

    keyboard = [
        [InlineKeyboardButton(f"{i}. {anime[0]}", callback_data=f"select_{start_idx + i - 1}")]
        for i, anime in enumerate(animes[start_idx:end_idx], 1)
    ]

    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("◀️ Back", callback_data="search_back"))
    if end_idx < len(animes):
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

@app.on_callback_query()
def handle_callback(client, callback):
    user_id = callback.from_user.id
    data = callback.data

    if user_id not in user_data:
        return callback.answer("Session expired ⏳ Start over", show_alert=True)

    if user_data[user_id].get("active_requests", 0) >= max_requests_per_user:
        return callback.answer(f"Please wait... You can only have {max_requests_per_user} active request(s) at a time.", show_alert=True)

    try:
        if data.startswith("select_"):
            index = int(data.split("_")[1])
            selected_anime = user_data[user_id]["animes"][index]
            user_data[user_id].update({
                "episodes": create_links(selected_anime),
                "page": 0,
                "selected_anime": selected_anime[0],
                "message_id": callback.message.id
            })
            show_episodes(user_id, callback)

        elif data in ["search_back", "search_next"]:
            user_data[user_id]["page"] += -1 if data == "search_back" else 1
            show_search_results(user_id, callback.message)

        elif data in ["episodes_back", "episodes_next"]:
            user_data[user_id]["page"] += -1 if data == "episodes_back" else 1
            show_episodes(user_id, callback)

        elif data.startswith("episode_"):
            user_data[user_id]["active_requests"] += 1
            index = int(data.split("_")[1])
            selected_episode = user_data[user_id]["episodes"][index]
            
            wait_msg = callback.message.reply_text("⏳ Fetching download links...")
            
            links, title = download_link(selected_episode["url"])
            
            client.delete_messages(callback.message.chat.id, wait_msg.id)
            
            # Create inline buttons in horizontal rows
            buttons = []
            row = []
            if send_all_qualities:
                for i, link in enumerate(links, 1):
                    row.append(InlineKeyboardButton(
                        f"📥 {link['quality']}p",
                        url=link['link']
                    ))
                    if i % 2 == 0:  # 2 buttons per row
                        buttons.append(row)
                        row = []
                if row:  # Add remaining buttons if any
                    buttons.append(row)
            else:
                default_link = next((link for link in links if link["quality"] == download_quality), None)
                if default_link:
                    buttons.append([
                        InlineKeyboardButton(
                            f"📥 {download_quality}p Download",
                            url=default_link['link']
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
        print(f"Callback error: {e}")
    finally:
        if user_id in user_data:
            user_data[user_id]["active_requests"] = max(0, user_data[user_id].get("active_requests", 0) - 1)
    callback.answer()

try:
    app.run()
except sqlite3.OperationalError as e:
    print(f"Database error: {e}. Stop other instances first.")
except Exception as e:
    print(f"Critical error: {e}")
