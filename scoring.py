"""Shared scam-signal scoring used by app.py and test_all.py."""
import re

SIGNS = {
    "authority": (
        2,
        [
            "cbi",
            "police",
            "पुलिस",
            "cyber crime",
            "क्राइम ब्रांच",
            "inspector",
            "इंस्पेक्टर",
            "customs",
            "कस्टम",
            "बैंक",
            "bank",
            "income tax",
            "इनकम टैक्स",
        ],
    ),
    "threat": (
        3,
        [
            "arrest",
            "digital arrest",
            "अरेस्ट",
            "drugs",
            "ड्रग्स",
            "case",
            "केस",
            "पकड़ा",
            "ब्लॉक",
            "block",
            "बंद हो जाएगा",
        ],
    ),
    "secrecy": (
        3,
        ["मत बताइए", "मत बताइये", "मत बताना", "किसी को भी मत", "किसी को मत"],
    ),
    "stay_on_line": (2, ["बने रहिए", "बने रहिये", "लाइन पर"]),
    "asks_secret": (
        4,
        [
            "ओटीपी",
            "otp",
            "पिन",
            "pin",
            "पासवर्ड",
            "password",
            "verification",
            "kyc",
            "details",
            "डिटेल्स",
            "खाता नंबर",
            "account number",
        ],
    ),
    "asks_money": (
        4,
        [
            "ट्रांसफर",
            "transfer",
            "पैसे भेज",
            "भेज दीजिए",
            "भेज दो",
            "भेजिए",
            "फीस",
            "upi",
        ],
    ),
    "asks_link": (
        4,
        ["लिंक", "link", "क्लिक", "click", "डाउनलोड", "download", "apk", "ऐप"],
    ),
    "lure": (
        3,
        [
            "इनाम",
            "बधाई",
            "जीता",
            "लॉटरी",
            "lottery",
            "prize",
            "रिफंड",
            "refund",
            "cashback",
        ],
    ),
    "emergency": (
        3,
        ["मुसीबत", "accident", "एक्सीडेंट", "अस्पताल", "hospital", "पुलिस ने पकड़"],
    ),
    "urgency": (2, ["जल्दी", "अभी", "तुरंत", "फौरन", "urgent"]),
}


HIGH_MIN_SCORE = 11
HIGH_MIN_CATEGORIES = 3
MEDIUM_MIN_SCORE = 6


def _matches(word, text):
  """English keywords must match whole words ('pin' != 'spinning'); Hindi uses substring."""
  if word.isascii():
    return re.search(rf"(?<![a-z0-9]){re.escape(word)}(?![a-z0-9])", text) is not None
  return word in text


def find_triggers(text, found_words=None):
  """Adds keywords found in `text` to found_words {category: [words]} and returns it."""
  found_words = {} if found_words is None else found_words
  text = text.lower()
  for cat, (_, words) in SIGNS.items():
    for w in words:
      if _matches(w, text) and w not in found_words.setdefault(cat, []):
        found_words[cat].append(w)
  return {c: w for c, w in found_words.items() if w}


def risk_level(found_words):
  """Returns (score, level). HIGH needs >=3 categories and score >= 11."""
  categories = set(found_words)
  score = sum(SIGNS[c][0] for c in categories)
  if len(categories) >= HIGH_MIN_CATEGORIES and score >= HIGH_MIN_SCORE:
    return score, "HIGH"
  if score >= MEDIUM_MIN_SCORE or "asks_secret" in categories:
    return score, "MEDIUM"
  return score, "LOW"
