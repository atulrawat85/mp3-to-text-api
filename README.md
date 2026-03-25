# MP3 to Text API - Cloud Relay Server

Convert audio/video files to text using **converter.app** backend via a cloud relay server (bypasses corporate firewalls like Zscaler).

## 🎯 Features

- ✅ Convert MP3, WAV, M4A, OGG, AAC, MP4, WebM to text
- ✅ Speaker detection (distinguish different speakers)
- ✅ Works inside restricted networks (Zscaler, corporate proxies)
- ✅ Simple REST API
- ✅ Free deployment options

## 🚀 Quick Start

### Local Development

```bash
# Clone repo
git clone https://github.com/YOUR_USERNAME/mp3-to-text-api.git
cd mp3-to-text-api

# Install dependencies
pip install -r requirements.txt

# Create .env file
cp .env.example .env
# Edit .env and set your API_KEY

# Run server
python main.py
# or
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Server runs at: `http://localhost:8000`

### Test Locally

```bash
python TEST.py
```

---

## 📡 Deploy to Cloud (Free Options)

### Option 1: Railway (Recommended - Easiest)

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login
railway login

# Deploy
railway init
railway up
```

Get your URL from Railway dashboard → copy it.

### Option 2: Render

1. Go to **render.com** → Sign up (GitHub)
2. Click **"New +"** → **"Web Service"**
3. Connect your GitHub repo
4. Settings:
   - **Name**: `mp3-to-text-api`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Add environment variables:
   - `API_KEY`: Your secret key
   - `WORKER`: `rx2`
6. Click **"Create Web Service"**

Get your URL: `https://mp3-to-text-api.onrender.com`

### Option 3: Heroku (Paid but reliable)

```bash
# Install Heroku CLI
# https://devcenter.heroku.com/articles/heroku-cli

heroku login
heroku create mp3-to-text-api
heroku config:set API_KEY=MySecretKey123
git push heroku main
```

---

## 📚 API Usage

### Health Check

```bash
curl http://localhost:8000/health
```

Response:
```json
{
  "status": "ok",
  "service": "mp3-to-text-relay",
  "upload_target": "https://rx2.converter.app/audio-to-text/uploader.php"
}
```

### Transcribe Audio

```bash
curl -X POST http://localhost:8000/transcribe \
  -H "x-api-key: MySecretKey123" \
  -F "file=@audio.mp3"
```

**Query Parameters:**
- `speaker_detect`: `Off` (default) or `On`

**Response:**
```json
{
  "success": true,
  "jobid": "abc123xyz",
  "filename": "audio.mp3",
  "file_size_kb": 2048.5,
  "speaker_detect": "Off",
  "text": "Hello, this is the transcribed content...",
  "worker": "rx2"
}
```

---

## 🐍 Python Client Example

```python
import requests

API_URL = "http://localhost:8000"  # or your cloud URL
API_KEY = "MySecretKey123"

def transcribe_audio(file_path, speaker_detect="Off"):
    """Transcribe audio file to text"""
    
    with open(file_path, "rb") as f:
        response = requests.post(
            f"{API_URL}/transcribe",
            headers={"x-api-key": API_KEY},
            files={"file": f},
            params={"speaker_detect": speaker_detect},
            timeout=600
        )
    
    data = response.json()
    
    if data.get("success"):
        return data["text"]
    else:
        raise Exception(f"Error: {data.get('detail')}")

# Usage
text = transcribe_audio("meeting.mp3", speaker_detect="On")
print(text)
```

---

## 🔐 Security

- **Never commit `.env`** — it's in `.gitignore`
- Use strong `API_KEY` in production
- Set environment variables on cloud platform (not in code)
- Use HTTPS only in production

---

## 🛠️ Troubleshooting

### 403 Forbidden Error
- Zscaler is blocking `converter.app`
- Solution: Deploy relay server on cloud (outside corporate network)

### SSL Certificate Error
- Disable SSL verification in client: `verify=False`

### Timeout
- Long audio files take time
- Increase timeout: `timeout=600` (10 minutes)

---

## 📝 Environment Variables

| Variable | Default | Description |
|---|---|---|
| `WORKER` | `rx2` | converter.app worker server |
| `ROOT` | `converter.app` | Root domain |
| `SLUG` | `audio-to-text` | API endpoint slug |
| `API_KEY` | `changeme` | Your API authentication key |

---

## 📄 License

MIT

---

## 👨‍💻 Author

Your Name

## 🤝 Contributing

Pull requests welcome!

---

## 📞 Support

Issues? Open a GitHub issue or email: support@example.com
