from flask import Flask, render_template, Response, jsonify, request
import cv2
import mediapipe as mp
import numpy as np
import pickle
import threading
import time
import os
import subprocess
from collections import deque

app = Flask(__name__)

# ── Load models ───────────────────────────────────────────────────────────────
BASE = os.path.dirname(os.path.abspath(__file__))

letter_model = word_model = le_letters = le_words = None

def load_models():
    global letter_model, word_model, le_letters, le_words
    try:
        from tensorflow.keras.models import load_model
        letter_model = load_model(os.path.join(BASE, 'models/letter_model.h5'))
        word_model   = load_model(os.path.join(BASE, 'models/word_model.h5'))
        with open(os.path.join(BASE, 'models/label_encoder_letters.pkl'), 'rb') as f:
            le_letters = pickle.load(f)
        with open(os.path.join(BASE, 'models/label_encoder_words.pkl'), 'rb') as f:
            le_words = pickle.load(f)
        print(f"✅ Models loaded — {len(le_letters.classes_)} letters, {len(le_words.classes_)} words")
    except Exception as e:
        print(f"[WARN] Model load failed: {e}")

load_models()

# ── MediaPipe ─────────────────────────────────────────────────────────────────
mp_hands    = mp.solutions.hands
mp_holistic = mp.solutions.holistic
mp_drawing  = mp.solutions.drawing_utils

hands_sol    = mp_hands.Hands(max_num_hands=2, min_detection_confidence=0.5, min_tracking_confidence=0.5)
holistic_sol = mp_holistic.Holistic(min_detection_confidence=0.5, min_tracking_confidence=0.5)

POSE_UPPER = [11,12,13,14,15,16,23,24,25,26,27,28]

# ── App state ─────────────────────────────────────────────────────────────────
state = {
    "mode": "LETTER",
    "language": "English",
    "word_buffer": [],
    "sentence_words": [],
    "final_sentence": "",
    "translated_sentence": "",
    "detected": "",
    "confidence": 0.0,
    "suggestions": [],
    "camera_on": False,
    "hold_progress": 0,
    "recent_signs": [],
}

# word mode
frame_sequence    = deque(maxlen=30)
word_pred_history = deque(maxlen=5)
prev_word_feats   = None
word_frame_count  = 0
last_word         = ""
letter_hold_count = 0
last_letter       = ""
LETTER_STABLE     = 10
WORD_STABLE       = 5

cap = None
output_frame = None
frame_lock   = threading.Lock()

LANGUAGES = ["English","Hindi","Telugu","Tamil","Bengali",
             "Kannada","Malayalam","Marathi","Punjabi","Urdu","Kashmiri"]

DICTIONARY = sorted(set([
    "HELLO","HELP","HAPPY","HUNGRY","THANK","TIRED","SORRY","STOP",
    "PLEASE","FOOD","FINE","WATER","WANT","GOOD","GO","NAME","NICE",
    "YES","YOU","NO","UNDERSTAND","COME","BAD","LIKE","LOVE","KNOW",
    "INDIA","ABOUT","AFTER","ALL","AND","ARE","AT","BE","BECAUSE",
    "BIG","BUT","CAN","DAY","DO","DOWN","EACH","EVEN","EVERY","FEEL",
    "FOR","GET","GIVE","HAS","HAVE","HERE","IF","IN","IS","IT","JUST",
    "KNOW","LAST","LONG","LOOK","MAKE","MANY","ME","MORE","MY","NEED",
    "NEW","NOW","OF","ON","ONE","ONLY","OR","OUR","OUT","PEOPLE",
    "RIGHT","SAY","SEE","SHE","SO","SOME","STILL","TAKE","THAN",
    "THEIR","THEM","THEN","THERE","THEY","THIS","TIME","TO","TOO",
    "TWO","UP","US","USE","VERY","WAY","WE","WELL","WHEN","WHICH",
    "WHO","WILL","WITH","WOULD",
]))

# ── Feature extraction ────────────────────────────────────────────────────────
def extract_letter_features(hand_results):
    features = []
    detected = hand_results.multi_hand_landmarks or []
    for i in range(2):
        if i < len(detected):
            hl = detected[i]
            xs = [lm.x for lm in hl.landmark]
            ys = [lm.y for lm in hl.landmark]
            mx, my = min(xs), min(ys)
            for lm in hl.landmark:
                features.extend([lm.x - mx, lm.y - my])
        else:
            features.extend([0.0]*42)
    return features

def extract_holistic_features(results):
    def hand_lm(hand):
        if hand:
            pts = np.array([[lm.x,lm.y,lm.z] for lm in hand.landmark]).flatten()
            pts[0::3] -= pts[0]; pts[1::3] -= pts[1]
            return pts
        return np.zeros(63)
    def pose_lm(pose):
        if pose:
            pts = np.array([[pose.landmark[i].x,pose.landmark[i].y,pose.landmark[i].z]
                            for i in POSE_UPPER]).flatten()
            sx = (pose.landmark[11].x + pose.landmark[12].x)/2
            sy = (pose.landmark[11].y + pose.landmark[12].y)/2
            pts[0::3] -= sx; pts[1::3] -= sy
            return pts
        return np.zeros(36)
    return np.concatenate([hand_lm(results.right_hand_landmarks),
                           hand_lm(results.left_hand_landmarks),
                           pose_lm(results.pose_landmarks)])

def hand_visible(r):
    return r.right_hand_landmarks is not None or r.left_hand_landmarks is not None

def get_suggestions(prefix, n=4):
    if not prefix: return []
    return [w for w in DICTIONARY if w.startswith(prefix.upper())][:n]

# ── Camera loop ───────────────────────────────────────────────────────────────
def camera_loop():
    global cap, output_frame, prev_word_feats, word_frame_count
    global letter_hold_count, last_letter, last_word

    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 960)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 540)

    while state["camera_on"]:
        ret, frame = cap.read()
        if not ret: break
        frame   = cv2.flip(frame, 1)
        img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        if state["mode"] == "LETTER":
            hr = hands_sol.process(img_rgb)
            if hr.multi_hand_landmarks:
                for hl in hr.multi_hand_landmarks:
                    mp_drawing.draw_landmarks(
                        frame, hl, mp_hands.HAND_CONNECTIONS,
                        mp_drawing.DrawingSpec(color=(0,255,120), thickness=2, circle_radius=3),
                        mp_drawing.DrawingSpec(color=(255,220,0), thickness=2))
                feats = np.array(extract_letter_features(hr)).reshape(1,-1)
                pred  = letter_model.predict(feats, verbose=0)
                idx   = np.argmax(pred)
                conf  = float(pred[0][idx])
                label = le_letters.classes_[idx]
                if conf >= 0.75:
                    state["detected"]   = label
                    state["confidence"] = conf
                    if label == last_letter:
                        letter_hold_count += 1
                    else:
                        letter_hold_count = 0
                        last_letter = label
                    state["hold_progress"] = letter_hold_count / LETTER_STABLE
                    if letter_hold_count >= LETTER_STABLE:
                        state["word_buffer"].append(label)
                        state["suggestions"] = get_suggestions("".join(state["word_buffer"]))
                        letter_hold_count = 0
                        last_letter = ""
                else:
                    state["detected"] = ""
                    state["hold_progress"] = 0
            else:
                letter_hold_count = 0
                state["hold_progress"] = 0

        else:  # WORD mode
            hol = holistic_sol.process(img_rgb)
            if hol.right_hand_landmarks:
                mp_drawing.draw_landmarks(frame, hol.right_hand_landmarks, mp_holistic.HAND_CONNECTIONS,
                    mp_drawing.DrawingSpec(color=(0,255,120), thickness=2, circle_radius=3),
                    mp_drawing.DrawingSpec(color=(255,220,0), thickness=2))
            if hol.left_hand_landmarks:
                mp_drawing.draw_landmarks(frame, hol.left_hand_landmarks, mp_holistic.HAND_CONNECTIONS,
                    mp_drawing.DrawingSpec(color=(255,100,0), thickness=2, circle_radius=3),
                    mp_drawing.DrawingSpec(color=(255,200,0), thickness=2))

            if hand_visible(hol):
                ff = extract_holistic_features(hol)
                vel = ff - prev_word_feats if prev_word_feats is not None else np.zeros(162)
                prev_word_feats = ff.copy()
                frame_sequence.append(np.concatenate([ff, vel]))
                word_frame_count += 1

                if len(frame_sequence) == 30 and word_frame_count % 5 == 0:
                    arr  = np.array(list(frame_sequence), dtype=np.float32).reshape(1,30,324)
                    pred = word_model.predict(arr, verbose=0)
                    idx  = np.argmax(pred)
                    conf = float(pred[0][idx])
                    label = le_words.classes_[idx]
                    if conf >= 0.85:
                        state["detected"]   = label
                        state["confidence"] = conf
                        word_pred_history.append(label)
                        if (len(word_pred_history) == WORD_STABLE and
                                len(set(list(word_pred_history))) == 1 and
                                label != last_word):
                            state["sentence_words"].append(label)
                            state["recent_signs"].insert(0, label)
                            state["recent_signs"] = state["recent_signs"][:5]
                            last_word = label
                            word_pred_history.clear()
                            frame_sequence.clear()
                    else:
                        word_pred_history.clear()
            else:
                frame_sequence.clear()
                prev_word_feats = None
                word_pred_history.clear()
                word_frame_count = 0

        with frame_lock:
            output_frame = frame.copy()

    if cap: cap.release()

def generate_frames():
    global output_frame
    blank = np.zeros((540,960,3), dtype=np.uint8)
    while True:
        with frame_lock:
            frame = output_frame.copy() if output_frame is not None else blank.copy()
        ret, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if ret:
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buf.tobytes() + b'\r\n')
        time.sleep(0.033)

# ── Routes ────────────────────────────────────────────────────────────────────

@app.route('/')
def landing():
    return render_template('landing.html')

@app.route('/bidirectional')
def isl_translate_v7():
    return render_template('isl_translator_v7.html')


@app.route('/translate')
def index():
    return render_template('index.html',
                           languages=LANGUAGES,
                           letter_classes=len(le_letters.classes_) if le_letters else 0,
                           word_classes=len(le_words.classes_)   if le_words   else 0)


@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/camera', methods=['POST'])
def toggle_camera():
    action = request.json.get('action')
    if action == 'start' and not state["camera_on"]:
        state["camera_on"] = True
        threading.Thread(target=camera_loop, daemon=True).start()
    elif action == 'stop':
        state["camera_on"] = False
    return jsonify({"camera_on": state["camera_on"]})

@app.route('/api/state')
def get_state():
    return jsonify({
        "detected":    state["detected"],
        "confidence":  round(state["confidence"]*100),
        "mode":        state["mode"],
        "language":    state["language"],
        "word_buffer": "".join(state["word_buffer"]),
        "sentence":    " › ".join(state["sentence_words"]),
        "final":       state["final_sentence"],
        "translated":  state["translated_sentence"],
        "suggestions": state["suggestions"],
        "hold":        round(state["hold_progress"]*100),
        "recent":      state["recent_signs"],
        "camera_on":   state["camera_on"],
    })

@app.route('/api/action', methods=['POST'])
def action():
    global last_word, last_letter, letter_hold_count
    cmd = request.json.get('cmd')

    if cmd == 'mode':
        state["mode"] = "WORD" if state["mode"] == "LETTER" else "LETTER"
        frame_sequence.clear(); word_pred_history.clear()
        letter_hold_count = 0; last_letter = ""; last_word = ""
        state["detected"] = ""; state["hold_progress"] = 0

    elif cmd == 'clear':
        state["word_buffer"].clear(); state["sentence_words"].clear()
        state["final_sentence"] = ""; state["translated_sentence"] = ""
        state["suggestions"] = []; state["detected"] = ""
        last_word = ""; last_letter = ""; letter_hold_count = 0
        frame_sequence.clear(); word_pred_history.clear()

    elif cmd == 'backspace':
        if state["word_buffer"]:
            state["word_buffer"].pop()
            state["suggestions"] = get_suggestions("".join(state["word_buffer"]))
        elif state["sentence_words"]:
            state["sentence_words"].pop()

    elif cmd == 'confirm_word':
        if state["word_buffer"]:
            word = "".join(state["word_buffer"])
            state["sentence_words"].append(word)
            state["recent_signs"].insert(0, word)
            state["recent_signs"] = state["recent_signs"][:5]
            state["word_buffer"].clear()
            state["suggestions"] = []

    elif cmd == 'autocomplete':
        idx = request.json.get('idx', 0)
        if idx < len(state["suggestions"]):
            chosen = state["suggestions"][idx]
            state["sentence_words"].append(chosen)
            state["recent_signs"].insert(0, chosen)
            state["recent_signs"] = state["recent_signs"][:5]
            state["word_buffer"].clear()
            state["suggestions"] = []

    elif cmd == 'generate':
        from src.nlp_helper import correct_sentence
        from src.tts_helper import speak, translate_text
        if state["sentence_words"]:
            state["final_sentence"] = correct_sentence(state["sentence_words"])
            state["translated_sentence"] = translate_text(state["final_sentence"], state["language"])
            threading.Thread(
                target=speak,
                args=(state["final_sentence"], state["language"]),
                daemon=True
            ).start()

    elif cmd == 'language':
        state["language"] = request.json.get('lang', 'English')

    return jsonify({"ok": True, "state": state["mode"]})

@app.route('/api/collect/words')
def get_collect_words():
    """Return word list with collection counts for Collect Data tab."""
    try:
        import pickle as pkl
        from collections import Counter
        path = os.path.join(BASE, 'data/own_word_landmarks.pkl')
        if os.path.exists(path):
            with open(path,'rb') as f:
                data = pkl.load(f)
            counts = Counter(data['labels'])
        else:
            counts = {}
    except:
        counts = {}

    WORD_GROUPS = {
        "Greetings & Basics": ["HELLO","THANK YOU","PLEASE","SORRY","YES","NO","HELP","STOP","WAIT","GO"],
        "Daily Needs":        ["WATER","FOOD","MEDICINE","SLEEP","EAT","DRINK","COME","GOOD","FINE","MORE"],
        "Feelings":           ["HAPPY","SAD","ANGRY","TIRED","SICK","LOVE","LIKE","SCARED","BORED","PAIN"],
        "Questions":          ["WHO","WHAT","WHERE","WHEN","WHY","HOW","WHICH","DO","CAN","IS"],
        "People & Places":    ["MY NAME","FRIEND","FAMILY","MOTHER","FATHER","HOME","SCHOOL","INDIA","DOCTOR","WORK"],
    }

    result = []
    for group, words in WORD_GROUPS.items():
        result.append({"group": group, "words": [
            {"word": w, "count": counts.get(w, 0)} for w in words
        ]})
    return jsonify(result)

@app.route('/api/model/stats')
def model_stats():
    return jsonify({
        "letter_classes": len(le_letters.classes_) if le_letters else 0,
        "word_classes":   len(le_words.classes_)   if le_words   else 0,
        "letter_words":   list(le_letters.classes_) if le_letters else [],
        "word_words":     list(le_words.classes_)   if le_words   else [],
    })

# ── Tutor Lessons API ───────────────────────────────────────

# ── Tutor Lessons API ───────────────────────────────────────

ALPHABETS = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
NUMBERS   = list(map(str, range(1,10)))
WORDS = ["I_Love_You", "my_name", "No", "Thank_you", "water", "yes"]

@app.route('/api/tutor/lesson/<lesson_type>')
def tutor_lesson(lesson_type):

    if lesson_type == "alphabets":
        return jsonify({
            "type": "alphabets",
            "items": ALPHABETS
        })

    elif lesson_type == "numbers":
        return jsonify({
            "type": "numbers",
            "items": NUMBERS
        })

    elif lesson_type == "words":
        return jsonify({
            "type": "words",
            "items": WORDS
        })

    return jsonify({"error": "Invalid lesson"}), 400

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000, threaded=True)