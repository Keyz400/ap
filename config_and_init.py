# config_and_init.py

import asyncio
import cloudscraper
import requests
import re
import os
import uuid
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, FSInputFile
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
import yt_dlp
from pyrogram import Client
from pyrogram.enums import ParseMode
import re as regex

# Configuration
BOT_TOKEN = "7466027003:AAFDFPQ3KWhZZb5cCDanOiE0cLES7Z6bTrY"
API_ID = 4030671
API_HASH = "c1806a30e8c9c69a4a1bb59c28f37318"

# Initialize clients
bot = Bot(token=BOT_TOKEN)
router = Router()
dp = Dispatcher()
dp.include_router(router)

# Pyrogram client for large file uploads
pyro_client = Client(
    "my_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True
)

# Storage
search_results_cache = {}
episode_results_cache = {}
progress_data = {}
url_storage = {}

# Cache Chrome driver
service = Service(ChromeDriverManager().install())
driver = None

def get_driver():
    global driver
    if driver is None:
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

def clean_ansi_codes(text):
    """Remove ANSI escape codes from text"""
    ansi_escape = regex.compile(r'\x1b\[([0-9;]*[mGKH])')
    return ansi_escape.sub('', text)

def progress_hook(d, url):
    """Process progress data and clean ANSI codes"""
    if d['status'] == 'downloading':
        # Clean ANSI codes from progress data
        cleaned_data = {}
        for key, value in d.items():
            if isinstance(value, str):
                cleaned_data[key] = clean_ansi_codes(value)
            else:
                cleaned_data[key] = value
        progress_data[url] = cleaned_data
    elif d['status'] == 'finished':
        progress_data[url] = d
