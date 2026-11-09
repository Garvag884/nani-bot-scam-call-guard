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

from scoring import SIGNS, find_triggers, risk_level

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
      "catalog": {c: pts for c, (pts, _) in SIGNS.items()},
  }


SAMPLES = {
    "tax-refund": ("Scam_A.wav", "Fake tax officer", "Offers a refund, asks for bank details"),
    "family-emergency": ("Scam_B.wav", "Family emergency", "Claims an accident, asks for money"),
    "digital-arrest": ("scammer1_30s.wav", "Digital arrest", "Fake cyber crime inspector, asks for an OTP"),
    "bank-branch": ("Normal_A.wav", "Bank branch", "Your cheque book is ready for pickup"),
    "delivery": ("Normal_B.wav", "Delivery update", "Order arrives tomorrow, track it in the app"),
}
_sample_cache = {}
HERE = os.path.dirname(os.path.abspath(__file__))


@app.get("/")
def index():
  samples = [{"key": k, "title": t, "desc": d} for k, (_, t, d) in SAMPLES.items()]
  return render_template_string(PAGE, samples=samples)


@app.post("/analyse-sample/<key>")
def analyse_sample(key):
  """Runs one of the bundled sample calls. Results are cached to save API quota."""
  if key not in SAMPLES:
    return jsonify(error="Unknown sample call."), 404
  if key not in _sample_cache:
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "?").split(",")[0].strip()
    if rate_limited(ip):
      return jsonify(error="Too many requests, please try again later."), 429
    path = os.path.join(HERE, SAMPLES[key][0])
    if not os.path.exists(path):
      return jsonify(error="Sample recording is missing on the server."), 404
    try:
      _sample_cache[key] = analyse(transcribe(path))
    except Exception as e:
      return jsonify(error=str(e)), 502
  return jsonify(_sample_cache[key])


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


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Nani Bot - Scam call guard</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:wght@500;700&family=Hind:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root{--bg:#E9EEF0;--panel:#fff;--ink:#13242C;--mute:#566872;--line:#D3DCE0;--brand:#0E5A6B;--brand-ink:#fff;
--low:#2C7A57;--lowbg:#DDF0E6;--med:#9A5F00;--medbg:#FBEBC8;--high:#B8281E;--highbg:#FADFDB;--track:#DCE4E7}
@media (prefers-color-scheme:dark){:root{--bg:#0F1A1F;--panel:#16252C;--ink:#E6EEF1;--mute:#93A7B0;--line:#27383F;
--brand:#5FC0D3;--brand-ink:#06242B;--low:#6FD1A0;--lowbg:#173A2B;--med:#F0B957;--medbg:#3B2E12;--high:#FF8B7F;--highbg:#471F1B;--track:#223540}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:17px/1.55 "Hind",system-ui,-apple-system,"Segoe UI",sans-serif}
h1,h2,h3,.brand{font-family:"Bricolage Grotesque","Hind",system-ui,sans-serif;margin:0;letter-spacing:-.01em}
:focus-visible{outline:3px solid var(--brand);outline-offset:2px}
.wrap{max-width:1080px;margin:0 auto;padding:20px 20px 64px}
header{display:flex;align-items:center;gap:10px;padding:8px 0 28px}
.brand{font-weight:700;font-size:20px}.tag{color:var(--mute);font-size:15px}
.dot{width:12px;height:12px;border-radius:50%;background:var(--brand)}
.hero h1{font-size:clamp(34px,6vw,56px);line-height:1.05;font-weight:700;max-width:14ch}
.hero p{color:var(--mute);max-width:52ch;margin:14px 0 32px;font-size:18px}
.grid{display:grid;grid-template-columns:minmax(0,340px) minmax(0,1fr);gap:24px;align-items:start}
@media (max-width:860px){.grid{grid-template-columns:1fr}}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:20px}
.panel h2{font-size:19px;margin-bottom:12px}
.drop{display:block;border:2px dashed var(--line);border-radius:12px;padding:22px 14px;text-align:center;cursor:pointer;color:var(--mute);transition:border-color .15s,background .15s}
.drop:hover,.drop.over{border-color:var(--brand);background:color-mix(in srgb,var(--brand) 8%,transparent)}
.drop strong{display:block;color:var(--ink);font-weight:600}
.drop input{position:absolute;opacity:0;width:1px;height:1px}
.drop:focus-within{outline:3px solid var(--brand);outline-offset:2px}
.btn{width:100%;margin-top:12px;padding:12px 16px;border:0;border-radius:10px;background:var(--brand);color:var(--brand-ink);font:600 17px "Hind",system-ui,sans-serif;cursor:pointer}
.btn:disabled{opacity:.55;cursor:wait}
.note{color:var(--mute);font-size:14px;margin:10px 0 0}
.sep{height:1px;background:var(--line);margin:22px 0 18px}
.samples{display:grid;gap:8px}
.sample{display:block;width:100%;text-align:left;padding:10px 12px;border:1px solid var(--line);border-radius:10px;background:transparent;color:var(--ink);font:inherit;cursor:pointer}
.sample:hover:not(:disabled){border-color:var(--brand)}.sample:disabled{opacity:.55;cursor:wait}
.sample b{display:block;font-weight:600}.sample span{color:var(--mute);font-size:14px}
.err{color:var(--high);margin:10px 0 0;font-size:15px}
.empty{border:2px dashed var(--line);border-radius:12px;padding:44px 20px;text-align:center;color:var(--mute)}
.empty b{display:block;color:var(--ink);font:700 20px "Bricolage Grotesque",sans-serif;margin-bottom:6px}
.verdict{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap}
.vword{font:700 clamp(30px,5vw,44px)/1 "Bricolage Grotesque",sans-serif}
.vscore{color:var(--mute)}
.LOW{--c:var(--low);--cbg:var(--lowbg)}.MEDIUM{--c:var(--med);--cbg:var(--medbg)}.HIGH{--c:var(--high);--cbg:var(--highbg)}
.vword{color:var(--c,var(--mute))}
.meter{position:relative;height:16px;border-radius:999px;background:var(--track);margin:16px 0 6px;overflow:hidden}
.fill{position:absolute;inset:0 auto 0 0;width:0;background:var(--c,var(--mute));border-radius:999px;transition:width .5s cubic-bezier(.2,.8,.2,1),background .3s}
.tick{position:absolute;top:0;bottom:0;width:2px;background:var(--panel)}
.scale{display:flex;justify-content:space-between;color:var(--mute);font-size:13px}
[hidden]{display:none!important}
.alert{display:flex;gap:12px;align-items:flex-start;margin-top:16px;padding:14px 16px;border-radius:12px;background:var(--highbg);color:var(--high);font-weight:600;animation:pop .35s ease-out}
@keyframes pop{from{transform:translateY(-6px);opacity:0}to{transform:none;opacity:1}}
.alert audio{width:100%;margin-top:10px}
h3{font-size:16px;margin:24px 0 10px}
.sig{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:6px 18px;padding:0;margin:0;list-style:none}
.sig li{display:flex;gap:8px;align-items:center;color:var(--mute);font-size:15px}
.sig i{flex:none;width:10px;height:10px;border-radius:50%;border:2px solid var(--line)}
.sig li.on{color:var(--ink);font-weight:500}.sig li.on i{background:var(--high);border-color:var(--high)}
.sig em{margin-left:auto;font-style:normal;color:var(--mute);font-size:13px}
.call{display:grid;gap:2px;margin:0;padding:0;list-style:none}
.line{display:grid;grid-template-columns:86px 1fr;gap:12px;padding:10px 0;border-top:1px solid var(--line);animation:pop .3s ease-out}
.line:first-child{border-top:0}
.pill{align-self:start;text-align:center;padding:2px 0;border-radius:999px;background:var(--cbg);color:var(--c);font-weight:600;font-size:13px}
.txt{line-height:1.75}.txt small{display:block;color:var(--mute);font-size:13px;line-height:1.3}
mark{background:var(--highbg);color:var(--high);border-radius:5px;padding:1px 4px;font-weight:600}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
</style></head><body><div class="wrap">
<header><span class="dot" aria-hidden="true"></span><span class="brand">Nani Bot</span><span class="tag">Scam call guard</span></header>
<section class="hero"><h1>Is this call a scam?</h1>
<p>Upload a call recording in Hindi or English. Nani Bot transcribes it and flags scam tactics sentence by sentence.</p></section>
<div class="grid">
<aside class="panel" aria-label="Choose a call">
 <h2>Check a call</h2>
 <form id="f">
  <label class="drop" id="drop"><input type="file" id="audio" accept="audio/*">
   <strong id="dname">Drop a recording here</strong>
   <span id="dhint">or click to choose a file (wav, mp3, m4a, up to 10 MB)</span></label>
  <button class="btn" id="go" type="submit">Analyse call</button>
 </form>
 <div class="err" id="err" role="alert"></div>
 <p class="note">Audio is sent to the Gnani speech API for transcription and is not stored.</p>
 <div class="sep"></div>
 <h2>Or try a sample call</h2>
 <div class="samples" id="samples"></div>
</aside>
<section class="panel" aria-live="polite" aria-label="Call analysis">
 <div class="empty" id="empty"><b>No call yet</b>Pick a sample or upload a recording. The risk score builds up as the call goes on.</div>
 <div id="mon" hidden>
  <div class="verdict" id="vd"><span class="vword" id="vw">Low risk</span><span class="vscore" id="vs">Score 0</span></div>
  <div class="meter" aria-hidden="true"><div class="fill" id="fill"></div><span class="tick" style="left:30%"></span><span class="tick" style="left:55%"></span></div>
  <div class="scale" aria-hidden="true"><span>Low</span><span>Medium</span><span>High</span></div>
  <div class="alert" id="al" hidden><span aria-hidden="true">&#9888;</span><div>Possible scam call. Do not share any OTP, PIN, password or money.<audio id="wa" controls hidden></audio></div></div>
  <h3>Scam tactics found</h3><ul class="sig" id="sig"></ul>
  <h3>The call, sentence by sentence</h3><ol class="call" id="call"></ol>
 </div>
</section></div></div>
<script>
const SAMPLES = {{ samples|tojson }};
const LABEL = {authority:"Poses as an authority",threat:"Threatens you",secrecy:"Asks you to keep it secret",
 stay_on_line:"Keeps you on the line",asks_secret:"Asks for OTP, PIN or details",asks_money:"Asks for money",
 asks_link:"Pushes a link or app",lure:"Offers a prize or refund",emergency:"Fakes an emergency",urgency:"Creates urgency"};
const NAME = {LOW:"Low risk",MEDIUM:"Medium risk",HIGH:"High risk"};
const $ = id => document.getElementById(id);
const sleep = ms => new Promise(r => setTimeout(r, ms));
const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
let run = 0, busy = false;

$("samples").innerHTML = SAMPLES.map(s =>
  `<button class="sample" type="button" data-k="${s.key}"><b>${s.title}</b><span>${s.desc}</span></button>`).join("");

function setBusy(b, label){ busy=b; $("go").disabled=b; document.querySelectorAll(".sample").forEach(x=>x.disabled=b);
  $("go").textContent = b ? (label||"Analysing...") : "Analyse call"; }
function esc(s){ return s.replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c])); }
function rx(words){
  const parts = [...new Set(words)].sort((a,b)=>b.length-a.length).map(w=>{
    const e = w.replace(/[.*+?^${}()|[\]\\]/g,"\\$&");
    return /^[\x00-\x7F]+$/.test(w) ? `(?<![A-Za-z0-9])${e}(?![A-Za-z0-9])` : e; });
  return parts.length ? new RegExp("("+parts.join("|")+")","gi") : null;
}
function paint(level, score){
  const m = $("mon"); m.className = level; $("vw").textContent = NAME[level];
  $("vs").textContent = "Score " + score; $("fill").style.width = Math.min(100, score/20*100) + "%";
}
async function show(d){
  const my = ++run;
  $("empty").hidden = true; $("mon").hidden = false; $("al").hidden = true; $("wa").hidden = true; $("call").innerHTML = "";
  $("sig").innerHTML = Object.keys(LABEL).map(c=>`<li data-c="${c}"><i></i>${LABEL[c]}<em>+${d.catalog[c]}</em></li>`).join("");
  paint("LOW", 0);
  const words = d.triggers.map(t=>t.word), catOf = {}; d.triggers.forEach(t=>catOf[t.word.toLowerCase()] = t.category);
  const re = rx(words); let warned = false;
  for (let i=0;i<d.timeline.length;i++){
    if (my !== run) return;
    const s = d.timeline[i];
    const html = re ? s.sentence.split(re).map((p,j)=> j%2 ? `<mark title="${LABEL[catOf[p.toLowerCase()]]||""}">${esc(p)}</mark>` : esc(p)).join("") : esc(s.sentence);
    if (re) s.sentence.split(re).forEach((p,j)=>{ if (j%2){ const li=document.querySelector(`#sig li[data-c="${catOf[p.toLowerCase()]}"]`); if(li) li.classList.add("on"); }});
    const li = document.createElement("li"); li.className = "line " + s.level;
    li.innerHTML = `<span class="pill">${s.level.toLowerCase()}</span><span class="txt" lang="hi">${html}</span>`;
    $("call").appendChild(li); paint(s.level, s.score);
    if (s.level==="HIGH" && !warned){ warned = true; $("al").hidden = false; $("wa").hidden = false; $("wa").src="/warning.wav"; $("wa").play().catch(()=>{}); }
    if (!reduce && i < d.timeline.length-1) await sleep(750);
  }
  $("mon").scrollIntoView({behavior: reduce?"auto":"smooth", block:"nearest"});
}
async function post(url, body, label){
  if (busy) return; $("err").textContent = ""; setBusy(true, label);
  try{
    const r = await fetch(url, {method:"POST", body}); const d = await r.json();
    if (!r.ok) throw new Error(d.error || "Something went wrong. Try again.");
    await show(d);
  }catch(x){ $("err").textContent = x.message; }
  finally{ setBusy(false); }
}
$("f").addEventListener("submit", e=>{ e.preventDefault(); const f=$("audio").files[0];
  if(!f){ $("err").textContent="Choose a recording first, or try a sample call."; return; }
  const fd=new FormData(); fd.append("audio", f); post("/analyse", fd); });
document.querySelectorAll(".sample").forEach(b=>b.addEventListener("click",()=>post("/analyse-sample/"+b.dataset.k,null,"Analysing...")));
function picked(){ const f=$("audio").files[0]; if(f){ $("dname").textContent=f.name; $("dhint").textContent=(f.size/1048576).toFixed(1)+" MB - ready to analyse"; } }
$("audio").addEventListener("change", picked);
const drop=$("drop");
["dragenter","dragover"].forEach(t=>drop.addEventListener(t,e=>{e.preventDefault();drop.classList.add("over")}));
["dragleave","drop"].forEach(t=>drop.addEventListener(t,e=>{e.preventDefault();drop.classList.remove("over")}));
drop.addEventListener("drop",e=>{ if(e.dataTransfer.files.length){ $("audio").files=e.dataTransfer.files; picked(); }});
</script></body></html>
"""

if __name__ == "__main__":
  app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)))
