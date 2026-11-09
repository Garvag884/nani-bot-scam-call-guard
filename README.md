# Nani Bot - Scam Call Guard

Real-time scam call detector for **Hindi + English** calls, built for the Gnani.ai Great Indian AI Internship Challenge 2026.

It transcribes a call with **Gnani Vachana speech-to-text**, scores every sentence for known scam patterns, and speaks a Hindi warning (Gnani Timbre text-to-speech) the moment the call looks dangerous.

**Live demo:** _add your Render link here_

## How it works

1. **Transcribe** the call audio with Vachana STT (`prisma-v3.0`, `hi-IN,en-IN`).
2. **Split** the transcript into sentences and look for scam signals, sentence by sentence, so the risk score climbs as the call goes on.
3. **Score** the signals and set a risk level: LOW, MEDIUM or HIGH.
4. On **HIGH**, speak a Hindi warning with Timbre TTS: *"सावधान! यह स्कैम कॉल हो सकता है। अपनी कोई भी जानकारी साझा न करें।"*

### Scam signals (`scoring.py`)

| Category | Points | Examples |
|---|---|---|
| authority | 2 | police, CBI, cyber crime, inspector, bank, income tax |
| threat | 3 | arrest, digital arrest, drugs, case, block |
| secrecy | 3 | "किसी को भी मत बताइए" |
| stay_on_line | 2 | "लाइन पर बने रहिये" |
| asks_secret | 4 | OTP, PIN, password, details, account number |
| asks_money | 4 | transfer, UPI, "पैसे भेज दीजिए" |
| asks_link | 4 | link, click, download, APK |
| lure | 3 | lottery, prize, refund, cashback |
| emergency | 3 | accident, hospital, "मुसीबत" |
| urgency | 2 | जल्दी, अभी, तुरंत, urgent |

Each category counts once. **HIGH** needs at least 3 categories and a score of 11 or more. **MEDIUM** is a score of 6 or more, or any request for a secret such as an OTP. Everything else is LOW.
English keywords match whole words only (so "spinning" does not trigger "pin"); Hindi keywords match as substrings.

## Features

- Live sentence-by-sentence risk analysis with the triggered words shown
- Spoken Hindi warning on HIGH risk
- Repeat-caller memory (SQLite) that warns when a number has called before
- Trusted-contacts whitelist that skips analysis
- Audit log for every call (`call_audit_report.json` latest, `call_audit_log.jsonl` history)
- Two ways to use it: a terminal app and a web demo

## Results

Tested on 5 recordings with real STT output:

| Result | Count |
|---|---|
| Scam calls flagged HIGH | 3 of 3 |
| Normal calls kept below HIGH | 2 of 2 |
| False alarms | 0 |

The sample is small, so treat it as a sanity check rather than a benchmark.

## Run it

You need Python 3 and a Gnani API key.

```bash
pip install -r requirements.txt
cp .env.example .env        # then put your real key in .env
```

**Terminal app**
```bash
python3 app.py
```
Enter a 12-digit dummy number, answer `yes`, then give an audio file such as `Scam_A.wav`.

**Web demo**
```bash
python3 web_app.py
```
Open http://127.0.0.1:5000 and upload a call recording.

**Test on the sample recordings**
```bash
python3 test_all.py
```

## Deploy

The web demo runs on any host that supports Python (for example Render):

- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn web_app:app --timeout 120 --workers 1`
- Environment variable: `GNANI_API_KEY`

## Files

| File | Purpose |
|---|---|
| `app.py` | Terminal app |
| `web_app.py` | Flask web demo |
| `scoring.py` | Scam signals and risk rules, shared by both apps |
| `test_all.py` | Runs the sample recordings and reports accuracy |
| `Scam_*.wav`, `Normal_*.wav`, `scammer1_30s.wav` | Sample recordings |

## Privacy and security

- The API key lives in `.env` or a server environment variable and is never committed or sent to the browser.
- Uploaded audio is processed for transcription and is not stored.
- The web demo limits each visitor to 15 analyses per hour to protect the API quota.

## Limitations

- Detection is keyword-based, so a scammer who avoids these words can slip through. The scoring rules are in one file to make them easy to extend.
- Accuracy depends on the speech-to-text transcript.
- Phone numbers are dummy 12-digit values for demo purposes.
