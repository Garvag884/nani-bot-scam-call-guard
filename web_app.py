"""Web demo for Nani Bot - Scam Call Guard.

Run locally:  python3 web_app.py   ->  http://127.0.0.1:5000
Production:   gunicorn web_app:app
The API key stays on the server (GNANI_API_KEY env var); the browser never sees it.
"""
import os
import re
import tempfile
import time
from collections import defaultdict, deque

import requests
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template_string, request

from scoring import find_triggers, risk_level

load_dotenv()
API_KEY = os.environ["GNANI_API_KEY"]

WARNING_TEXT = "सावधान! यह स्कैम कॉल हो सकता है। अपनी कोई भी जानकारी साझा न करें।"
MAX_UPLOAD_MB = 10
MAX_REQUESTS_PER_HOUR = 15  # per IP, protects your API quota on a public site

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024

_hits = defaultdict(deque)
_warning_cache = {}


def rate_limited(ip):
  now = time.time()
  q = _hits[ip]
  while q and now - q[0] > 3600:
    q.popleft()
  if len(q) >= MAX_REQUESTS_PER_HOUR:
    return True
  q.append(now)
  return False


def transcribe(path):
  with open(path, "rb") as f:
    r = requests.post(
        "https://api.vachana.ai/stt/v3",
        headers={"X-API-Key-ID": API_KEY},
        files={"audio_file": (os.path.basename(path), f)},
        data={"model": "prisma-v3.0", "language_code": "hi-IN,en-IN"},
        timeout=60,
    )
  if r.status_code != 200:
    raise RuntimeError(f"Speech-to-text failed ({r.status_code})")
  return r.json()["transcript"]


def analyse(transcript):
  sentences = [s.strip() for s in re.split(r"[।?.!]", transcript) if s.strip()]
  found, timeline = {}, []
  for s in sentences:
    found = find_triggers(s, found)
    score, level = risk_level(found)
    timeline.append({"sentence": s, "score": score, "level": level})
  score, level = risk_level(found)
  triggers = [{"word": w, "category": c} for c, ws in found.items() for w in ws]
  return {
      "transcript": transcript,
      "timeline": timeline,
      "score": score,
      "level": level,
      "triggers": triggers,
  }


@app.get("/")
def index():
  return render_template_string(PAGE)


@app.post("/analyse")
def analyse_route():
  ip = request.headers.get("X-Forwarded-For", request.remote_addr or "?").split(",")[0].strip()
  if rate_limited(ip):
    return jsonify(error="Too many requests, please try again later."), 429
  f = request.files.get("audio")
  if not f or not f.filename:
    return jsonify(error="Please choose an audio file."), 400
  if not f.filename.lower().endswith((".wav", ".mp3", ".m4a", ".ogg", ".flac")):
    return jsonify(error="Unsupported file type. Use wav, mp3, m4a, ogg or flac."), 400
  with tempfile.TemporaryDirectory() as d:
    path = os.path.join(d, "call_audio" + os.path.splitext(f.filename)[1].lower())
    f.save(path)
    try:
      transcript = transcribe(path)
    except Exception as e:  # network / API errors
      return jsonify(error=str(e)), 502
  return jsonify(analyse(transcript))


@app.get("/warning.wav")
def warning_audio():
  """Spoken Hindi warning (generated once with Timbre TTS, then cached)."""
  if "wav" not in _warning_cache:
    r = requests.post(
        "https://api.vachana.ai/api/v1/tts/inference",
        headers={"X-API-Key-ID": API_KEY, "Content-Type": "application/json"},
        json={
            "text": WARNING_TEXT,
            "model": "timbre-v2.5",
            "voice": "Nalini",
            "audio_config": {
                "sample_rate": 48000,
                "num_channels": 1,
                "sample_width": 2,
                "encoding": "linear_pcm",
                "container": "wav",
            },
        },
        timeout=60,
    )
    if r.status_code != 200:
      return Response("warning audio unavailable", status=502)
    _warning_cache["wav"] = r.content
  return Response(_warning_cache["wav"], mimetype="audio/wav")


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Nani Bot - Scam Call Guard</title>
<style>
:root{--bg:#f6f7f9;--card:#fff;--ink:#1b1f24;--mute:#5d6671;--line:#e1e5ea;--accent:#1f4fd8;
--low:#1a7f4b;--lowbg:#e3f4ea;--med:#9a6400;--medbg:#fdf0d5;--high:#b3261e;--highbg:#fbe4e2}
@media (prefers-color-scheme:dark){:root{--bg:#14171c;--card:#1d2127;--ink:#eef1f4;--mute:#9aa4af;--line:#2d333b;
--accent:#7ea1ff;--low:#5fd493;--lowbg:#17372a;--med:#f1b94f;--medbg:#3b2f14;--high:#ff8a80;--highbg:#44201d}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:16px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:760px;margin:0 auto;padding:32px 16px 64px}
h1{font-size:26px;margin:0 0 4px}.sub{color:var(--mute);margin:0 0 24px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:20px;margin-bottom:16px}
input[type=file]{width:100%;padding:12px;border:1px dashed var(--line);border-radius:8px;background:transparent;color:var(--ink)}
button{margin-top:12px;padding:12px 20px;border:0;border-radius:8px;background:var(--accent);color:#fff;
font:600 16px inherit;cursor:pointer}button:disabled{opacity:.6;cursor:wait}
.badge{display:inline-block;padding:6px 14px;border-radius:999px;font-weight:700;letter-spacing:.04em}
.LOW{background:var(--lowbg);color:var(--low)}.MEDIUM{background:var(--medbg);color:var(--med)}
.HIGH{background:var(--highbg);color:var(--high)}
.row{display:flex;gap:12px;align-items:center;flex-wrap:wrap}.score{font-size:28px;font-weight:700}
.alert{background:var(--highbg);color:var(--high);border-radius:8px;padding:12px 16px;font-weight:600;margin-top:12px}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin-top:8px}
.chip{border:1px solid var(--line);border-radius:999px;padding:4px 12px;font-size:14px}
.chip small{color:var(--mute)}
.step{display:flex;gap:12px;align-items:flex-start;padding:10px 0;border-top:1px solid var(--line)}
.step:first-child{border-top:0}.step .badge{font-size:12px;padding:3px 10px;flex:none}
.step span.s{color:var(--mute);font-size:13px;flex:none;width:60px}
.err{color:var(--high);margin-top:12px}h2{font-size:18px;margin:0 0 8px}
.mute{color:var(--mute);font-size:14px}audio{width:100%;margin-top:12px}
</style></head><body><main>
<h1>Nani Bot - Scam Call Guard</h1>
<p class="sub">Upload a call recording. Speech-to-text transcribes it (Hindi + English), then each sentence is scored for scam signals.</p>
<form class="card" id="f">
<input type="file" id="audio" accept="audio/*" required>
<button id="go" type="submit">Analyse call</button>
<div class="mute" style="margin-top:8px">Audio is sent to the Gnani speech API for transcription and is not stored. Max 10 MB.</div>
<div class="err" id="err" role="alert"></div>
</form>
<div id="out" hidden>
 <div class="card"><div class="row"><span class="badge" id="lvl"></span>
 <span class="score" id="sc"></span><span class="mute">risk score</span></div>
 <div class="alert" id="al" hidden>Possible scam call detected. Do not share any information.</div>
 <audio id="wa" controls hidden></audio>
 <h2 style="margin-top:16px">Triggers detected</h2><div class="chips" id="tr"></div></div>
 <div class="card"><h2>Live sentence analysis</h2><div id="tl"></div></div>
 <div class="card"><h2>Transcript</h2><p id="tx" lang="hi"></p></div>
</div></main>
<script>
const $=id=>document.getElementById(id);
const esc=s=>s.replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
$('f').addEventListener('submit',async e=>{
 e.preventDefault();$('err').textContent='';$('out').hidden=true;
 const file=$('audio').files[0];if(!file)return;
 const fd=new FormData();fd.append('audio',file);
 $('go').disabled=true;$('go').textContent='Analysing...';
 try{
  const r=await fetch('/analyse',{method:'POST',body:fd});
  const d=await r.json();if(!r.ok)throw new Error(d.error||'Request failed');
  $('lvl').textContent=d.level;$('lvl').className='badge '+d.level;$('sc').textContent=d.score;
  $('tr').innerHTML=d.triggers.length?d.triggers.map(t=>`<span class="chip">${esc(t.word)} <small>${esc(t.category)}</small></span>`).join(''):'<span class="mute">None</span>';
  $('tl').innerHTML=d.timeline.map((s,i)=>`<div class="step"><span class="s">#${i+1} &middot; ${s.score}</span><span class="badge ${s.level}">${s.level}</span><span lang="hi">${esc(s.sentence)}</span></div>`).join('');
  $('tx').textContent=d.transcript;
  const high=d.level==='HIGH';$('al').hidden=!high;$('wa').hidden=!high;
  if(high){$('wa').src='/warning.wav';$('wa').play().catch(()=>{});}
  $('out').hidden=false;
 }catch(x){$('err').textContent=x.message}
 finally{$('go').disabled=false;$('go').textContent='Analyse call'}
});
</script></body></html>"""

if __name__ == "__main__":
  app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)))
