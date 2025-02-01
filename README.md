Here’s a **`README.md`** file for your GitHub repository, along with instructions on how to host the bot on a **VPS** and **Render**.

---

## **README.md**

```markdown
# Anime Download Bot 🤖

A Telegram bot that allows users to search for anime, fetch episodes, and download them directly from supported sources. The bot uses `yt-dlp` for downloading and `Pyrogram` for handling large file uploads.

---

## Features ✨

- Search for anime by name.
- Fetch episodes for a specific anime.
- Download episodes in various qualities.
- Upload downloaded files to Telegram (supports files up to 2GB using Pyrogram).

---

## Prerequisites 📋

- Python 3.8 or higher
- Telegram Bot Token
- Pyrogram API ID and API Hash
- ChromeDriver (for Selenium)

---

## Installation 🛠️

1. Clone the repository:
   ```bash
   git clone https://github.com/your-username/anime-download-bot.git
   cd anime-download-bot
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Set up environment variables:
   Create a `.env` file in the root directory and add the following:
   ```
   BOT_TOKEN=your-telegram-bot-token
   API_ID=your-pyrogram-api-id
   API_HASH=your-pyrogram-api-hash
   ```

4. Run the bot:
   ```bash
   python download_and_upload.py
   ```

---

## Hosting 🚀

### **1. Hosting on a VPS**

#### Step 1: Set up a VPS
- Use a VPS provider like **DigitalOcean**, **Linode**, or **AWS**.
- Create a Ubuntu server (20.04 or higher).

#### Step 2: Install dependencies
SSH into your VPS and run:
```bash
sudo apt update
sudo apt install python3-pip python3-venv git unzip
```

#### Step 3: Install ChromeDriver
```bash
wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo apt install ./google-chrome-stable_current_amd64.deb
sudo apt install -y chromium-chromedriver
```

#### Step 4: Clone and run the bot
```bash
git clone https://github.com/your-username/anime-download-bot.git
cd anime-download-bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python download_and_upload.py
```

#### Step 5: Run the bot in the background
Use `tmux` or `screen` to keep the bot running after closing the SSH session:
```bash
sudo apt install tmux
tmux new -s anime-bot
python download_and_upload.py
```
Press `Ctrl+B`, then `D` to detach from the session.

---

### **2. Hosting on Render**

#### Step 1: Create a Render account
- Sign up at [Render](https://render.com/).

#### Step 2: Create a new Web Service
- Go to the Render dashboard and click **New Web Service**.
- Connect your GitHub repository.

#### Step 3: Configure the Web Service
- Set the following environment variables in the Render dashboard:
  ```
  BOT_TOKEN=your-telegram-bot-token
  API_ID=your-pyrogram-api-id
  API_HASH=your-pyrogram-api-hash
  ```
- Set the **Start Command** to:
  ```bash
  python download_and_upload.py
  ```

#### Step 4: Deploy
- Click **Create Web Service** to deploy your bot.

---

## Environment Variables 🔑

| Variable   | Description                          |
|------------|--------------------------------------|
| `BOT_TOKEN`| Your Telegram bot token              |
| `API_ID`   | Pyrogram API ID                      |
| `API_HASH` | Pyrogram API Hash                    |

---

## Contributing 🤝

Contributions are welcome! Please open an issue or submit a pull request.

---

## License 📄

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
``
