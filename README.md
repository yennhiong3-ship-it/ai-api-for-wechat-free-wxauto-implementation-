# WeChat Bot

A WeChat robot based on wxauto4 (open source) with AI API integration and OCR support.

## Features

- AI-powered chat replies via OpenAI-compatible API
- OCR image recognition (EasyOCR)
- Multi-message splitting for long replies
- Group chat support with configurable blacklist
- Customizable system prompt via prompt.txt

## Requirements

- Windows 64-bit
- Python 3.9 ~ 3.12
- WeChat client (logged in)

## Quick Start

### 1. Install Dependencies

Double-click `install.bat`, or run manually:

```bat
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

> Note: PyTorch will be installed as CPU version (~200MB). EasyOCR downloads models on first run (~200MB).

### 2. Configure

Create a `.env` file in the project root:

```env
API_KEY=your_api_key_here
API_BASE_URL=https://api.example.com
```

See `main.py` for all available environment variables.

### 3. Run

Double-click `start.bat`, or run:

```bat
.venv\Scripts\python main.py
```

## Project Structure

| File | Description |
|------|-------------|
| `main.py` | Main program entry |
| `requirements.txt` | Python dependencies |
| `install.bat` | One-click dependency installer |
| `start.bat` | One-click launcher |
| `prompt.txt` | System prompt template |
| `chat_cfg.json` | Chat configuration |
| `blacklist.txt` | Blacklisted users (one per line) |
| `.env` | API key and settings (git-ignored) |

## Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| openai | >=1.0.0 | AI API client |
| python-dotenv | >=1.0.0 | Environment config |
| wxauto4 | >=4.0.0 | WeChat automation (open source) |
| easyocr | >=1.7.0 | OCR image recognition |
| torch | >=2.0.0 | Deep learning (CPU) |
| Pillow | >=10.0.0 | Image processing |

## Configuration Reference

Set these in `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `API_KEY` | (required) | API access key |
| `API_BASE_URL` | `https://api.deepseek.com` | API endpoint |
| `MAX_HISTORY_LENGTH` | `10` | Conversation history length |
| `REPLY_TIMEOUT` | `120` | API response timeout (seconds) |
| `DISABLE_GROUPS` | `true` | Disable group chat replies |
| `POLL_MIN` | `1.5` | Min poll interval (seconds) |
| `POLL_MAX` | `3.0` | Max poll interval (seconds) |
| `IMG_DIR` | `./images` | Image cache directory |

## Troubleshooting

**Installation fails with network error:**
```bat
.venv\Scripts\python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

**wxauto4 import fails:**
- Ensure you are on Windows 64-bit
- WeChat client must be installed and logged in
- Python version must be 3.9 ~ 3.12

**PyTorch import fails:**
```bat
.venv\Scripts\python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
```

## Credits

- [wxauto](https://github.com/cluic/wxauto) - WeChat automation library (open source)
- [EasyOCR](https://github.com/JaidedAI/EasyOCR) - OCR engine

## License

For personal use only. Use of WeChat automation may violate WeChat Terms of Service. Use at your own risk.
