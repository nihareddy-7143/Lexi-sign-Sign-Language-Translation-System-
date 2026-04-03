import pyttsx3
import threading
import os
import tempfile
from gtts import gTTS

LANGUAGES = {
    "English":   {"code": "en", "gtts": "en"},
    "Hindi":     {"code": "hi", "gtts": "hi"},
    "Telugu":    {"code": "te", "gtts": "te"},
    "Tamil":     {"code": "ta", "gtts": "ta"},
    "Bengali":   {"code": "bn", "gtts": "bn"},
    "Kannada":   {"code": "kn", "gtts": "kn"},
    "Malayalam": {"code": "ml", "gtts": "ml"},
    "Marathi":   {"code": "mr", "gtts": "mr"},
    "Punjabi":   {"code": "pa", "gtts": "pa"},
    "Urdu":      {"code": "ur", "gtts": "ur"},
    "Kashmiri":  {"code": "ur", "gtts": "ur"},
}

try:
    from deep_translator import GoogleTranslator
    TRANSLATION_AVAILABLE = True
    print("✅ Translation available")
except Exception:
    TRANSLATION_AVAILABLE = False
    print("[WARN] deep-translator not installed. Run: pip install deep-translator")

def translate_text(text, target_language="English"):
    if target_language == "English" or not TRANSLATION_AVAILABLE:
        return text
    lang_code = LANGUAGES.get(target_language, {}).get("code", "en")
    if lang_code == "en":
        return text
    try:
        translated = GoogleTranslator(source="en", target=lang_code).translate(text)
        print(f"  [TTS] Translated to {target_language}: {translated}")
        return translated
    except Exception as e:
        print(f"  [TTS] Translation failed: {e}")
        return text

_engine = None

def setup_voice(rate=150):
    global _engine
    try:
        _engine = pyttsx3.init()
        _engine.setProperty("rate", rate)
        voices = _engine.getProperty("voices")
        for v in voices:
            if "david" in v.name.lower() or "zira" in v.name.lower():
                _engine.setProperty("voice", v.id)
                break
        print("✅ TTS engine ready")
    except Exception as e:
        print(f"[WARN] pyttsx3 setup failed: {e}")
        _engine = None

def _speak_gtts(text, lang_code):
    try:
        import pygame
        tts = gTTS(text=text, lang=lang_code, slow=False)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
            tmp_path = f.name
        tts.save(tmp_path)
        pygame.mixer.init()
        pygame.mixer.music.load(tmp_path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.wait(100)
        pygame.mixer.music.unload()
        os.remove(tmp_path)
    except Exception as e:
        print(f"  [TTS] gTTS playback failed: {e}")

def _speak_pyttsx3(text):
    global _engine
    try:
        if _engine is None:
            setup_voice()
        _engine.say(text)
        _engine.runAndWait()
    except Exception as e:
        print(f"  [TTS] pyttsx3 failed: {e}")

def speak(text, language="English", async_mode=True):
    if not text:
        return
    def _run():
        translated = translate_text(text, language)
        if language == "English":
            _speak_pyttsx3(translated)
        else:
            lang_code = LANGUAGES.get(language, {}).get("gtts", "en")
            _speak_gtts(translated, lang_code)
    if async_mode:
        threading.Thread(target=_run, daemon=True).start()
    else:
        _run()

def get_available_languages():
    return list(LANGUAGES.keys())

if __name__ == "__main__":
    setup_voice()
    test = "I am fine. Thank you."
    for lang in ["English", "Hindi", "Telugu"]:
        print(f"\nSpeaking in {lang}...")
        speak(test, language=lang, async_mode=False)