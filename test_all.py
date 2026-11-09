import os

import requests
from dotenv import load_dotenv

from scoring import find_triggers, risk_level

load_dotenv()
api_key = os.environ["GNANI_API_KEY"]

# file name -> what it SHOULD be
files = {
    "scammer1_30s.wav": "scam",
    "generated-audio (13).wav": "scam",
    "generated-audio (14).wav": "scam",
    "generated-audio (10).wav": "normal",
    "generated-audio (11).wav": "normal",
    "generated-audio (12).wav": "normal",
    "Scam_A.wav": "scam",
    "Scam_B.wav": "scam",
    "Normal_A.wav": "normal",
    "Normal_B.wav": "normal",

    
}

def transcribe(path):
    with open(path, "rb") as f:
        r = requests.post(
            "https://api.vachana.ai/stt/v3",
            headers={"X-API-Key-ID": api_key},
            files={"audio_file": (path, f)},
            data={"model": "prisma-v3.0", "language_code": "hi-IN,en-IN"},
            timeout=60,
        )
    if r.status_code != 200:
        print(path, "failed:", r.status_code, r.text[:200])
        return None
    return r.json().get("transcript", "")

caught = missed = false_alarms = correct_normal = 0
for name, truth in files.items():
    if not os.path.exists(name):
        print(name, "-> file not found, skipping")
        continue
    text = transcribe(name)
    if text is None:
        continue
    found = find_triggers(text)
    score, level = risk_level(found)
    flagged = level == "HIGH"
    print(f"{name}: expected {truth}, got {level} (score {score}) {sorted(found)}")
    print("   transcript:", text)
    if truth == "scam" and flagged: caught += 1
    elif truth == "scam": missed += 1
    elif flagged: false_alarms += 1
    else: correct_normal += 1

print()
print("Scam calls caught:", caught, "| missed:", missed)
print("Normal calls fine:", correct_normal, "| false alarms:", false_alarms)