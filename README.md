# WeChat AI Bot

An AI-powered WeChat automation framework based on wxauto4, supporting OpenAI-compatible APIs, OCR image recognition, configurable prompts, and multi-session message handling.

> Windows-only WeChat automation solution with AI API integration.
With a separator, the AI will use this separator to send multiple messages at a time, making it more anthropomorphic.
---

## Features

* OpenAI-compatible API support
* OCR image recognition via EasyOCR
* Multi-message splitting for long replies
* Group chat support with configurable blacklist
* Configurable system prompt (`prompt.txt`)
* Randomized polling interval
* Session history management
* Windows WeChat automation via wxauto4

---

## Requirements

* Windows 10 / 11 (64-bit)
* Python 3.9 ~ 3.12
* Desktop WeChat client (logged in)

---

## Quick Start

### 1. Clone Repository

```bash
git clone https://github.com/YOUR_USERNAME/wechat-ai-bot.git
cd wechat-ai-bot
```

---

### 2. Install Dependencies

Run:

```bat
install.bat
```

Or manually:

```bat
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

> EasyOCR and PyTorch CPU models will be downloaded automatically on first launch.

---

### 3. Configure Environment Variables

Create a `.env` file in the project root:

```env
API_KEY=your_api_key_here
API_BASE_URL=https://api.deepseek.com
```

Example:

```env
API_KEY=sk-xxxxxxxx
API_BASE_URL=https://api.openai.com/v1
```

---

### 4. Run

Run:

```bat
start.bat
```

Or manually:

```bat
.venv\Scripts\python main.py
```

---

## Project Structure

| File               | Description                      |
| ------------------ | -------------------------------- |
| `main.py`          | Main program entry               |
| `requirements.txt` | Python dependencies              |
| `install.bat`      | Dependency installer             |
| `start.bat`        | Launcher                         |
| `prompt.txt`       | System prompt                    |
| `chat_cfg.json`    | Chat configuration               |
| `blacklist.txt`    | Blacklisted users                |
| `.env`             | API configuration (not included) |

---

## Configuration Reference

Environment variables:

| Variable             | Default                    | Description               |
| -------------------- | -------------------------- | ------------------------- |
| `API_KEY`            | Required                   | API access key            |
| `API_BASE_URL`       | `https://api.deepseek.com` | API endpoint              |
| `MAX_HISTORY_LENGTH` | `10`                       | Conversation history size |
| `REPLY_TIMEOUT`      | `120`                      | API timeout               |
| `DISABLE_GROUPS`     | `true`                     | Disable group reply       |
| `POLL_MIN`           | `1.5`                      | Min polling interval      |
| `POLL_MAX`           | `3.0`                      | Max polling interval      |
| `IMG_DIR`            | `./images`                 | OCR image cache           |

---

## Troubleshooting

### Dependency Installation Failure

Use Tsinghua mirror:

```bat
.venv\Scripts\python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

---

### wxauto4 Import Failure

* Ensure Windows 64-bit
* Ensure WeChat desktop client is installed
* Ensure WeChat is logged in
* Ensure Python version is 3.9 ~ 3.12

---

### PyTorch Import Failure

```bat
.venv\Scripts\python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
```

---

## Security Notice

Do NOT upload:

* `.env`
* API keys
* session files
* logs
* personal chat history

Recommended `.gitignore`:

```gitignore
.venv/
__pycache__/
*.pyc
.env
*.log
images/
```

---

## Disclaimer

This project is intended for educational and research purposes only.

Users are solely responsible for complying with applicable laws and platform Terms of Service. Automating WeChat may violate Tencent WeChat policies. Use at your own risk.

---

## Credits

* wxauto
  https://github.com/cluic/wxauto

* EasyOCR
  https://github.com/JaidedAI/EasyOCR

---

## License

This project is licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).

See the `LICENSE` file for details.
