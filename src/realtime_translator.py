import cv2
import mediapipe as mp
import numpy as np
import pickle
import threading
from collections import deque
from tensorflow.keras.models import load_model
from nlp_helper import correct_sentence
from tts_helper import speak, setup_voice, get_available_languages, translate_text

# ─────────────────────────────────────────────
# LOAD MODELS
# ─────────────────────────────────────────────
print("📂 Loading models...")
letter_model = load_model('./models/letter_model.h5')
word_model   = load_model('./models/word_model.h5')

with open('./models/label_encoder_letters.pkl', 'rb') as f:
    le_letters = pickle.load(f)
with open('./models/label_encoder_words.pkl', 'rb') as f:
    le_words = pickle.load(f)

print(f"✅ Letter model: {len(le_letters.classes_)} classes")
print(f"✅ Word model:   {len(le_words.classes_)} classes")

# ─────────────────────────────────────────────
# DICTIONARY
# ─────────────────────────────────────────────
DICTIONARY = sorted(set([
    "HELLO","HELP","HAPPY","HUNGRY","HURT","HEAR","HOW","HAPPENED",
    "THANK","TIRED","THINK","TALK","TELL","TODAY","TRUST","THIRSTY",
    "SORRY","STOP","SLEEP","SPEAK","SURE",
    "PLEASE","PHONE","PLACE","PROMISE",
    "FOOD","FINE","FREE","FRIEND","FROM","FEVER",
    "WATER","WANT","WEAR","WELCOME","WHAT","WHERE","WHO","WORRY",
    "GOOD","GO","GRATEFUL","NAME","NICE","NOT","NUMBER",
    "YES","YOU","NO","UNDERSTAND","REPEAT","REALLY",
    "COME","COLD","BAD","BEAUTIFUL","BECOME","BORED","BRING",
    "MEDICINE","MEET","KIND","LEAVE","LIKE","LOVE","OLD","OUTSIDE",
    "DO","ENJOY","AGREE","ALL","ANGRY","APPRECIATE","AFRAID",
    "INDIA","INDIAN","ISL",
    "ABOUT","AFTER","AGAIN","ALSO","ALWAYS","AND","ARE","AT",
    "BACK","BE","BECAUSE","BEEN","BEFORE","BIG","BUT","BY",
    "CAN","COULD","DAY","DID","DOWN","EACH","EVEN","EVERY",
    "FEEL","FEW","FOR","GET","GIVE","GREAT","HAS","HAVE",
    "HER","HERE","HIM","HIS","IF","IN","INTO","IS","IT","ITS",
    "JUST","KNOW","LAST","LITTLE","LONG","LOOK","MAKE","MANY",
    "ME","MORE","MOST","MY","NEED","NEW","NEXT","NOW","OF",
    "OFF","ON","ONE","ONLY","OR","OTHER","OUR","OUT","OVER",
    "OWN","PEOPLE","RIGHT","SAID","SAME","SAY","SEE","SHE",
    "SHOULD","SO","SOME","STILL","SUCH","TAKE","THAN","THEIR",
    "THEM","THEN","THERE","THEY","THIS","TIME","TO","TOO","TWO",
    "UP","US","USE","VERY","WAY","WE","WELL","WERE","WHEN",
    "WHICH","WHILE","WHO","WILL","WITH","WOULD",
]))

def get_autocomplete(prefix, max_suggestions=4):
    if not prefix:
        return []
    prefix = prefix.upper()
    return [w for w in DICTIONARY if w.startswith(prefix)][:max_suggestions]

# ─────────────────────────────────────────────
# MEDIAPIPE
# ─────────────────────────────────────────────
mp_hands    = mp.solutions.hands
mp_holistic = mp.solutions.holistic
mp_drawing  = mp.solutions.drawing_utils

hands = mp_hands.Hands(max_num_hands=2,
                        min_detection_confidence=0.5,
                        min_tracking_confidence=0.5)
holistic = mp_holistic.Holistic(min_detection_confidence=0.5,
                                 min_tracking_confidence=0.5)

setup_voice(rate=150)
LANGUAGES        = get_available_languages()
current_lang_idx = 0

# ─────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────
SEQUENCE_LENGTH      = 30
LETTER_CONF_THRESH   = 0.75
WORD_CONF_THRESH     = 0.85
LETTER_STABLE_FRAMES = 10
WORD_STABLE_FRAMES   = 5
POSE_UPPER           = [11,12,13,14,15,16,23,24,25,26,27,28]

# ─────────────────────────────────────────────
# STATE
# ─────────────────────────────────────────────
mode                = "LETTER"
letter_hold_count   = 0
last_letter         = ""
word_buffer         = []
sentence_words      = []
frame_sequence      = deque(maxlen=SEQUENCE_LENGTH)
word_frame_count    = 0
last_word           = ""
final_sentence      = ""
translated_sentence = ""
show_sentence       = False
suggestions         = []
selected_suggest    = -1
word_pred_history   = deque(maxlen=WORD_STABLE_FRAMES)
prev_word_features  = None

# ─────────────────────────────────────────────
# FEATURES
# ─────────────────────────────────────────────
def extract_letter_landmarks(hand_results):
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
            features.extend([0.0] * 42)
    return features

def extract_holistic_features(results):
    def hand_lm(hand):
        if hand:
            pts = np.array([[lm.x, lm.y, lm.z] for lm in hand.landmark]).flatten()
            pts[0::3] -= pts[0]; pts[1::3] -= pts[1]
            return pts
        return np.zeros(63)
    def pose_lm(pose):
        if pose:
            pts = np.array([[pose.landmark[i].x, pose.landmark[i].y, pose.landmark[i].z]
                            for i in POSE_UPPER]).flatten()
            sx = (pose.landmark[11].x + pose.landmark[12].x) / 2
            sy = (pose.landmark[11].y + pose.landmark[12].y) / 2
            pts[0::3] -= sx; pts[1::3] -= sy
            return pts
        return np.zeros(36)
    return np.concatenate([hand_lm(results.right_hand_landmarks),
                           hand_lm(results.left_hand_landmarks),
                           pose_lm(results.pose_landmarks)])

def hand_visible(r):
    return r.right_hand_landmarks is not None or r.left_hand_landmarks is not None

# ─────────────────────────────────────────────
# PREDICTION
# ─────────────────────────────────────────────
def predict_letter(hand_results):
    feats = np.array(extract_letter_landmarks(hand_results)).reshape(1, -1)
    pred  = letter_model.predict(feats, verbose=0)
    idx   = np.argmax(pred)
    return le_letters.classes_[idx], float(pred[0][idx])

def predict_word(sequence):
    arr  = np.array(sequence, dtype=np.float32).reshape(1, SEQUENCE_LENGTH, 324)
    pred = word_model.predict(arr, verbose=0)
    idx  = np.argmax(pred)
    return le_words.classes_[idx], float(pred[0][idx])

# ─────────────────────────────────────────────
# UI
# ─────────────────────────────────────────────
def draw_ui(frame, detected, confidence, mode, word_buffer, sentence_words,
            final_sentence, translated_sentence, show_sentence,
            suggestions, selected_suggest, hold_progress, current_language):
    h, w = frame.shape[:2]

    overlay = frame.copy()
    cv2.rectangle(overlay, (0,0), (w,75), (20,20,20), -1)
    cv2.addWeighted(overlay, 0.75, frame, 0.25, 0, frame)

    mode_color = (34,177,76) if mode == "LETTER" else (0,120,255)
    cv2.rectangle(frame, (10,10), (145,60), mode_color, -1)
    cv2.putText(frame, f"MODE: {mode}", (18,43),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255,255,255), 2)

    cv2.putText(frame, f"{detected}  {confidence:.0%}", (160,30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,255,200), 2)

    cv2.rectangle(frame, (w-210,10), (w-10,60), (60,40,80), -1)
    cv2.putText(frame, f"[L] {current_language}", (w-205,43),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (220,180,255), 2)

    if mode == "LETTER" and hold_progress > 0:
        bar_w = int((hold_progress / LETTER_STABLE_FRAMES) * 180)
        cv2.rectangle(frame, (160,40), (340,58), (50,50,50), -1)
        cv2.rectangle(frame, (160,40), (160+bar_w,58), (0,220,120), -1)
        cv2.putText(frame, "hold", (345,54), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (150,150,150), 1)

    panel_y  = h - 220
    overlay2 = frame.copy()
    cv2.rectangle(overlay2, (0,panel_y), (w,h), (10,10,10), -1)
    cv2.addWeighted(overlay2, 0.82, frame, 0.18, 0, frame)

    cv2.putText(frame, f"Spelling:  {''.join(word_buffer)}_", (15,panel_y+30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,220,0), 2)

    if suggestions:
        cv2.putText(frame, "Suggestions:", (15,panel_y+62),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150,150,150), 1)
        sx = 130
        for i, sug in enumerate(suggestions):
            is_sel = (i == selected_suggest)
            color  = (0,200,255) if is_sel else (180,180,180)
            bg     = (40,80,100) if is_sel else (40,40,40)
            tw     = len(sug)*11+16
            cv2.rectangle(frame, (sx-4,panel_y+48), (sx+tw,panel_y+72), bg, -1)
            cv2.putText(frame, f"{i+1}.{sug}", (sx,panel_y+66),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 1)
            sx += tw+12

    cv2.line(frame, (10,panel_y+80), (w-10,panel_y+80), (60,60,60), 1)
    sent_str = "Sentence:  " + "  ›  ".join(sentence_words)
    cv2.putText(frame, sent_str[:68], (15,panel_y+108),
                cv2.FONT_HERSHEY_SIMPLEX, 0.62, (180,180,255), 2)
    cv2.line(frame, (10,panel_y+120), (w-10,panel_y+120), (60,60,60), 1)

    if show_sentence and final_sentence:
        cv2.rectangle(frame, (10,panel_y+126), (w-10,panel_y+148), (0,50,0), -1)
        cv2.putText(frame, f"EN: {final_sentence[:70]}", (18,panel_y+143),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.58, (0,255,120), 2)

    if show_sentence and translated_sentence and current_language != "English":
        cv2.rectangle(frame, (10,panel_y+152), (w-10,panel_y+175), (0,30,60), -1)
        cv2.putText(frame, f"{current_language[:3]}: {translated_sentence[:65]}",
                    (18,panel_y+170), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (100,200,255), 2)

    cv2.putText(frame, "[M] Mode  [SPACE] Word  [1-4] Suggest  [L] Language",
                (10,h-20), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (120,120,120), 1)
    cv2.putText(frame, "[ENTER] Speak  [BKSP] Undo  [C] Clear  [Q] Quit",
                (10,h-7),  cv2.FONT_HERSHEY_SIMPLEX, 0.38, (120,120,120), 1)
    return frame

# ─────────────────────────────────────────────
# MAIN LOOP
# ─────────────────────────────────────────────
cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 960)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 540)

print("\n🚀 LEXISIGN — ISL Translator started!")
print("  [M] Mode  [L] Language  [SPACE] Confirm word")
print("  [1-4] Autocomplete  [ENTER] Speak  [BKSP] Undo  [C] Clear  [Q] Quit\n")
print(f"  Languages: {', '.join(LANGUAGES)}\n")

while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        break

    frame            = cv2.flip(frame, 1)
    img_rgb          = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    detected         = ""
    confidence       = 0.0
    current_language = LANGUAGES[current_lang_idx]

    if mode == "LETTER":
        hand_results = hands.process(img_rgb)
        if hand_results.multi_hand_landmarks:
            for hl in hand_results.multi_hand_landmarks:
                mp_drawing.draw_landmarks(
                    frame, hl, mp_hands.HAND_CONNECTIONS,
                    mp_drawing.DrawingSpec(color=(0,255,0), thickness=2, circle_radius=3),
                    mp_drawing.DrawingSpec(color=(255,255,0), thickness=2))
            label, conf = predict_letter(hand_results)
            if conf >= LETTER_CONF_THRESH:
                detected   = label
                confidence = conf
                if label == last_letter:
                    letter_hold_count += 1
                else:
                    letter_hold_count = 0
                    last_letter = label
                if letter_hold_count >= LETTER_STABLE_FRAMES:
                    word_buffer.append(label.upper())
                    suggestions = get_autocomplete("".join(word_buffer))
                    print(f"🔤 Letter: {label}  |  Word: {''.join(word_buffer)}")
                    letter_hold_count = 0
                    last_letter = ""
        else:
            letter_hold_count = 0

    else:
        hol_results = holistic.process(img_rgb)
        if hol_results.right_hand_landmarks:
            mp_drawing.draw_landmarks(frame, hol_results.right_hand_landmarks,
                mp_holistic.HAND_CONNECTIONS,
                mp_drawing.DrawingSpec(color=(0,255,0), thickness=2, circle_radius=3),
                mp_drawing.DrawingSpec(color=(255,255,0), thickness=2))
        if hol_results.left_hand_landmarks:
            mp_drawing.draw_landmarks(frame, hol_results.left_hand_landmarks,
                mp_holistic.HAND_CONNECTIONS,
                mp_drawing.DrawingSpec(color=(255,100,0), thickness=2, circle_radius=3),
                mp_drawing.DrawingSpec(color=(255,200,0), thickness=2))

        if hand_visible(hol_results):
            frame_feats = extract_holistic_features(hol_results)
            velocity    = frame_feats - prev_word_features if prev_word_features is not None else np.zeros(162)
            prev_word_features = frame_feats.copy()
            frame_sequence.append(np.concatenate([frame_feats, velocity]))
            word_frame_count += 1

            if len(frame_sequence) == SEQUENCE_LENGTH and word_frame_count % 5 == 0:
                label, conf = predict_word(list(frame_sequence))
                if conf >= WORD_CONF_THRESH:
                    detected   = label
                    confidence = conf
                    word_pred_history.append(label)
                    if (len(word_pred_history) == WORD_STABLE_FRAMES and
                            len(set(word_pred_history)) == 1 and label != last_word):
                        sentence_words.append(label)
                        last_word = label
                        word_pred_history.clear()
                        frame_sequence.clear()
                        print(f"📝 Word confirmed: {label} ({conf:.0%})")
                else:
                    word_pred_history.clear()
        else:
            frame_sequence.clear()
            prev_word_features = None
            word_pred_history.clear()
            word_frame_count = 0

    frame = draw_ui(frame, detected, confidence, mode, word_buffer, sentence_words,
                    final_sentence, translated_sentence, show_sentence,
                    suggestions, selected_suggest, letter_hold_count, current_language)

    cv2.imshow("LEXISIGN — ISL Translator", frame)
    key = cv2.waitKey(1) & 0xFF

    if key == ord('q'):
        break
    elif key == ord('m'):
        mode = "WORD" if mode == "LETTER" else "LETTER"
        frame_sequence.clear(); word_pred_history.clear()
        word_frame_count = letter_hold_count = 0
        last_letter = last_word = ""; suggestions = []
        prev_word_features = None
        print(f"🔄 Mode: {mode}")
    elif key == ord('l'):
        current_lang_idx = (current_lang_idx + 1) % len(LANGUAGES)
        print(f"🌐 Language: {LANGUAGES[current_lang_idx]}")
    elif key == ord('c'):
        word_buffer.clear(); sentence_words.clear()
        final_sentence = translated_sentence = ""
        show_sentence  = False
        last_letter = last_word = ""
        letter_hold_count = 0; suggestions = []; selected_suggest = -1
        frame_sequence.clear(); word_pred_history.clear()
        prev_word_features = None
        print("🗑️  Cleared")
    elif key == 8:
        if mode == "LETTER" and word_buffer:
            removed = word_buffer.pop()
            suggestions = get_autocomplete("".join(word_buffer))
            print(f"⬅️  Removed letter: {removed}")
        elif sentence_words:
            print(f"⬅️  Removed word: {sentence_words.pop()}")
    elif key == 32:
        if mode == "LETTER":
            if word_buffer:
                word = "".join(word_buffer)
                sentence_words.append(word)
                print(f"📝 Word confirmed: {word}")
                word_buffer.clear(); suggestions = []; selected_suggest = -1
            elif detected:
                word_buffer.append(detected.upper())
                suggestions = get_autocomplete("".join(word_buffer))
        elif mode == "WORD" and detected and detected != last_word:
            sentence_words.append(detected)
            last_word = detected
            word_pred_history.clear(); frame_sequence.clear()
            print(f"📝 Word force-added: {detected}")
    elif key in [ord('1'), ord('2'), ord('3'), ord('4')]:
        idx = key - ord('1')
        if idx < len(suggestions):
            sentence_words.append(suggestions[idx])
            print(f"✅ Autocomplete: {suggestions[idx]}")
            word_buffer.clear(); suggestions = []; selected_suggest = -1
    elif key == 13:
        if sentence_words:
            print(f"\n🔄 Generating: {sentence_words}")
            final_sentence      = correct_sentence(sentence_words)
            translated_sentence = translate_text(final_sentence, current_language)
            show_sentence       = True
            print(f"✅ English : {final_sentence}")
            if current_language != "English":
                print(f"✅ {current_language}: {translated_sentence}")
            threading.Thread(target=speak,
                             args=(final_sentence, current_language),
                             daemon=True).start()

cap.release()
cv2.destroyAllWindows()
print("👋 Closed.")