import re

# ─── HappyTransformer ─────────────────────────────────────────────────────────
try:
    from happytransformer import HappyTextToText, TTSettings
    print("📦 Loading grammar model (first run downloads ~1GB)...")
    _happy = HappyTextToText("T5", "vennify/t5-base-grammar-correction")
    _args  = TTSettings(num_beams=5, min_length=1, max_length=100)
    GRAMMAR_AVAILABLE = True
    print("✅ Grammar model loaded!")
except Exception as e:
    print(f"[WARN] HappyTransformer not available: {e}")
    GRAMMAR_AVAILABLE = False

# ─── Word normalisation map ───────────────────────────────────────────────────
NORM_MAP = {
    "ME": "I", "MINE": "mine", "MY": "my",
    "HELLO": "Hello", "HI": "Hi", "GOODBYE": "Goodbye", "BYE": "Bye",
    "THANK YOU": "Thank you", "THANK": "Thank you",
    "SORRY": "Sorry", "PLEASE": "Please",
    "WELCOME": "You are welcome", "EXCUSE ME": "Excuse me",
    "YES": "Yes", "NO": "No",
    "FOOD": "food", "WATER": "water", "GOOD": "good",
    "HAPPY": "happy", "SAD": "sad", "SICK": "sick",
    "TIRED": "tired", "HUNGRY": "hungry", "THIRSTY": "thirsty",
    "HELP": "help", "WANT": "want", "NEED": "need",
    "LIKE": "like", "LOVE": "love", "KNOW": "know",
    "UNDERSTAND": "understand", "COME": "come", "GO": "go",
    "EAT": "eat", "DRINK": "drink",
    # Multi-word phrases
    "MY NAME":            "My name is",
    "I AM FINE":          "I am fine",
    "HOW ARE YOU":        "How are you",
    "NICE TO MEET YOU":   "Nice to meet you",
    "GOOD MORNING":       "Good morning",
    "GOOD AFTERNOON":     "Good afternoon",
    "GOOD EVENING":       "Good evening",
    "I LOVE YOU":         "I love you",
    "I AM":               "I am",
    "I WANT":             "I want",
    "I NEED":             "I need",
    "THANK YOU VERY MUCH":"Thank you very much",
}

def _normalise_words(words):
    out   = []
    i     = 0
    upper = [w.upper() for w in words]
    while i < len(upper):
        matched = False
        for length in range(min(4, len(upper) - i), 0, -1):
            phrase = " ".join(upper[i:i+length])
            if phrase in NORM_MAP:
                out.append(NORM_MAP[phrase])
                i += length
                matched = True
                break
        if not matched:
            out.append(words[i].capitalize())
            i += 1
    return out

def _rule_based_fix(words):
    normalised = _normalise_words(words)
    text       = " ".join(normalised)
    patterns = [
        # "I Apeksha" → "I am Apeksha"
        (r"\bI\s+(?!am|will|can|have|had|was|love|want|need|like|know)([A-Z][a-z]+)\b", r"I am \1"),
        # "My name X" → "My name is X"
        (r"\bMy name\s+(?!is)([A-Z][a-z]+)\b", r"My name is \1"),
        # "I hungry/tired/..." → "I am hungry/..."
        (r"\bI\s+(hungry|thirsty|tired|sick|happy|sad|angry|fine|good|sorry|ready)\b", r"I am \1"),
        # double spaces
        (r"\s+", " "),
    ]
    for pattern, replacement in patterns:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text.strip()

def correct_sentence(words):
    if not words:
        return ""
    rough = _rule_based_fix(words)
    print(f"  [NLP] Rule-based: {rough}")
    if GRAMMAR_AVAILABLE:
        try:
            result    = _happy.generate_text(f"grammar: {rough}", args=_args)
            corrected = result.text.strip()
            print(f"  [NLP] Corrected : {corrected}")
        except Exception as e:
            print(f"  [NLP] ML failed: {e}")
            corrected = rough
    else:
        corrected = rough
    if corrected:
        corrected = corrected[0].upper() + corrected[1:]
        if not corrected.endswith((".", "!", "?")):
            corrected += "."
    return corrected

if __name__ == "__main__":
    tests = [
        ["I", "APEKSHA"],
        ["MY NAME", "APEKSHA"],
        ["I", "HUNGRY"],
        ["HELLO", "I", "GOOD"],
        ["THANK YOU", "HELP"],
        ["HOW ARE YOU", "I", "FINE"],
    ]
    print("\n── NLP Test Results ──────────────────────")
    for w in tests:
        print(f"  {w} → {correct_sentence(w)}")