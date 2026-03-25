import requests
from urllib3.exceptions import InsecureRequestWarning

# Suppress SSL warnings
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

url = "http://localhost:8000/transcribe"
headers = {"x-api-key": "your_secret_key_here"}

with open("captcha_audio.mp3", "rb") as f:
    response = requests.post(
        url,
        headers=headers,
        files={"file": ("captcha_audio.mp3", f, "audio/mpeg")},
        verify=False  # ← DISABLED SSL
    )

print("Status Code:", response.status_code)
data = response.json()
print("\nResponse:")
print(data)

if data.get("success"):
    print("\n✓ Transcribed Text:\n", data["text"])
else:
    print("\n✗ Error:", data.get("detail"))
