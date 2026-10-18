import cv2
import math
import os
import shutil
import subprocess
from collections import defaultdict

import numpy as np
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

from cv_engine.predictor import EngagementPredictor


# ============================================================
# CONFIG
# ============================================================
MAX_OUTPUT_WIDTH = 1920
MAX_OUTPUT_HEIGHT = 1080

MP_MIN_FACE_SIZE = (25, 25)   # Smaller threshold catches distant students
MP_TILE_COLS = 5              # Split frame into 4×5 overlapping tiles
MP_TILE_ROWS = 4              # Finer grid so each tile covers fewer faces → BlazeFace detects more
MP_TILE_OVERLAP = 0.30        # 30% overlap prevents faces at tile edges being cut off
MP_TILE_NMS_IOU = 0.30        # Lower IoU: nearby students have similar-sized boxes

MAX_MISSING_FRAMES = 35
NEW_TRACK_CONFIRMATION = 3
MIN_FINAL_PREDICTIONS = 3

MAX_MATCH_DISTANCE = 200.0
MIN_MATCH_IOU = 0.02
MAX_FEATURE_FACE_DISTANCE = 600.0

# Learned DAiSEE score + measured visual cues.
FEATURE_WEIGHTS = {
    "model": 0.50,
    "gaze": 0.15,
    "head": 0.10,
    "expression": 0.05,
    "posture": 0.10,
    "movement": 0.10,
}

FONT = cv2.FONT_HERSHEY_SIMPLEX


# ============================================================
# MODEL PATHS
# ============================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, "..", ".."))
MP_DIR = os.path.join(PROJECT_ROOT, "cv_engine", "models", "mediapipe")
FACE_MODEL_PATH = os.path.join(MP_DIR, "face_landmarker.task")
POSE_MODEL_PATH = os.path.join(MP_DIR, "pose_landmarker_lite.task")


# ============================================================
# HELPERS
# ============================================================
def clamp(value, low, high):
    return max(low, min(high, float(value)))


def center_of(box):
    x, y, w, h = box
    return (x + w / 2.0, y + h / 2.0)


def distance_between(a, b):
    ca = center_of(a)
    cb = center_of(b)
    return math.hypot(ca[0] - cb[0], ca[1] - cb[1])


def calculate_iou(a, b):
    x1, y1, w1, h1 = a
    x2, y2, w2, h2 = b
    xa = max(x1, x2)
    ya = max(y1, y2)
    xb = min(x1 + w1, x2 + w2)
    yb = min(y1 + h1, y2 + h2)
    inter = max(0, xb - xa) * max(0, yb - ya)
    area1 = max(1, w1 * h1)
    area2 = max(1, w2 * h2)
    union = area1 + area2 - inter
    return inter / union if union > 0 else 0.0


def area_similarity(a, b):
    _, _, w1, h1 = a
    _, _, w2, h2 = b
    ar1 = max(1, w1 * h1)
    ar2 = max(1, w2 * h2)
    return min(ar1 / ar2, ar2 / ar1)


def bbox_from_landmarks(landmarks, width, height):
    xs = [p.x for p in landmarks]
    ys = [p.y for p in landmarks]
    x1 = int(clamp(min(xs) * width, 0, width - 1))
    y1 = int(clamp(min(ys) * height, 0, height - 1))
    x2 = int(clamp(max(xs) * width, 0, width - 1))
    y2 = int(clamp(max(ys) * height, 0, height - 1))
    return (x1, y1, max(1, x2 - x1), max(1, y2 - y1))


def crop_box(frame, box, pad=0.0):
    x, y, w, h = box
    px = int(w * pad)
    py = int(h * pad)
    x1 = max(0, x - px)
    y1 = max(0, y - py)
    x2 = min(frame.shape[1], x + w + px)
    y2 = min(frame.shape[0], y + h + py)
    return frame[y1:y2, x1:x2]


def face_histogram(face_crop):
    if face_crop is None or face_crop.size == 0:
        return None
    small = cv2.resize(face_crop, (64, 64), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [16, 16], [0, 180, 0, 256])
    cv2.normalize(hist, hist)
    return hist


def histogram_similarity(h1, h2):
    if h1 is None or h2 is None:
        return None
    try:
        # Bhattacharyya distance: 0 is identical, 1 is very different.
        d = cv2.compareHist(h1, h2, cv2.HISTCMP_BHATTACHARYYA)
        return clamp(1.0 - d, 0.0, 1.0)
    except Exception:
        return None


def predicted_box(track):
    x, y, w, h = track["bbox"]
    vx, vy = track.get("velocity", (0.0, 0.0))
    return (int(x + vx), int(y + vy), w, h)


def match_faces_to_tracks(faces, face_hists, tracks):
    """Greedy global matching. Only current detections can be assigned."""
    candidates = []
    for fi, face in enumerate(faces):
        for tid, track in tracks.items():
            ref = predicted_box(track)
            distance = distance_between(face, ref)
            size = area_similarity(face, track["bbox"])
            iou = calculate_iou(face, ref)
            limit = max(
                MAX_MATCH_DISTANCE,
                2.0 * max(face[2], face[3], track["bbox"][2], track["bbox"][3]),
            )
            if distance > limit:
                continue
            dist_score = min(distance / limit, 1.0)
            appearance = histogram_similarity(face_hists[fi], track.get("hist"))
            appearance_penalty = 0.5 if appearance is None else (1.0 - appearance)
            score = (
                0.42 * dist_score
                + 0.23 * (1.0 - iou)
                + 0.10 * (1.0 - size)
                + 0.25 * appearance_penalty
            )
            if iou >= MIN_MATCH_IOU:
                score -= 0.06
            candidates.append((score, distance, fi, tid))

    candidates.sort(key=lambda v: (v[0], v[1]))
    assignments = {}
    used_faces = set()
    used_tracks = set()
    for score, distance, fi, tid in candidates:
        if fi in used_faces or tid in used_tracks:
            continue
        assignments[fi] = tid
        used_faces.add(fi)
        used_tracks.add(tid)
    return assignments


# ============================================================
# MEDIA PIPE
# ============================================================
def create_face_landmarker():
    if not os.path.exists(FACE_MODEL_PATH):
        raise FileNotFoundError(f"Face Landmarker model not found: {FACE_MODEL_PATH}")
    base = python.BaseOptions(model_asset_path=FACE_MODEL_PATH)
    options = vision.FaceLandmarkerOptions(
        base_options=base,
        running_mode=vision.RunningMode.VIDEO,
        num_faces=10,
        min_face_detection_confidence=0.45,
        min_face_presence_confidence=0.45,
        min_tracking_confidence=0.45,
        output_face_blendshapes=True,
        output_facial_transformation_matrixes=True,
    )
    return vision.FaceLandmarker.create_from_options(options)


def create_face_feature_landmarker():
    """Create an IMAGE-mode Face Landmarker for each detected face crop.

    This avoids the unreliable full-frame Haar-box <-> MediaPipe landmark
    matching that was causing Gaze/Head/Face to stay Unknown.
    """
    if not os.path.exists(FACE_MODEL_PATH):
        raise FileNotFoundError(f"Face Landmarker model not found: {FACE_MODEL_PATH}")
    base = python.BaseOptions(model_asset_path=FACE_MODEL_PATH)
    options = vision.FaceLandmarkerOptions(
        base_options=base,
        running_mode=vision.RunningMode.IMAGE,
        num_faces=1,
        min_face_detection_confidence=0.35,
        min_face_presence_confidence=0.35,
        min_tracking_confidence=0.35,
        output_face_blendshapes=True,
        output_facial_transformation_matrixes=True,
    )
    return vision.FaceLandmarker.create_from_options(options)


def create_pose_landmarker():
    if not os.path.exists(POSE_MODEL_PATH):
        raise FileNotFoundError(f"Pose Landmarker model not found: {POSE_MODEL_PATH}")
    base = python.BaseOptions(model_asset_path=POSE_MODEL_PATH)
    options = vision.PoseLandmarkerOptions(
        base_options=base,
        running_mode=vision.RunningMode.VIDEO,
        num_poses=10,
        min_pose_detection_confidence=0.35,
        min_pose_presence_confidence=0.35,
        min_tracking_confidence=0.35,
    )
    return vision.PoseLandmarker.create_from_options(options)


def mp_image_from_bgr(frame):
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    return mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)


# ============================================================
# FEATURE ANALYSIS
# ============================================================
def _pt(landmarks, idx):
    if landmarks is None or idx >= len(landmarks):
        return None
    p = landmarks[idx]
    return np.array([p.x, p.y, p.z], dtype=np.float32)


def _dist2(a, b):
    if a is None or b is None:
        return None
    return float(np.linalg.norm(a[:2] - b[:2]))


def analyze_face_features(face_result, face_box=None, frame_shape=None):
    """Analyze a single face result whose landmarks are local to its face crop.

    Unknown means the measurement was genuinely unavailable. No fallback score
    is fabricated, so fusion can safely exclude missing modalities.
    """
    if face_result is None or not face_result.face_landmarks:
        return {
            "gaze": ("Unknown", None),
            "head": ("Unknown", None),
            "expression": ("Unknown", None),
        }

    best = face_result.face_landmarks[0]

    # Iris landmarks (468-477) are available in the Face Landmarker mesh.
    left_iris = [_pt(best, i) for i in range(468, 473)]
    right_iris = [_pt(best, i) for i in range(473, 478)]
    left_iris = [p for p in left_iris if p is not None]
    right_iris = [p for p in right_iris if p is not None]

    gaze_label, gaze_score = "Unknown", None
    if left_iris and right_iris:
        li = np.mean(left_iris, axis=0)
        ri = np.mean(right_iris, axis=0)
        lc1, lc2 = _pt(best, 33), _pt(best, 133)
        rc1, rc2 = _pt(best, 362), _pt(best, 263)
        if all(p is not None for p in (lc1, lc2, rc1, rc2)):
            lr = (li[0] - min(lc1[0], lc2[0])) / max(1e-5, abs(lc1[0] - lc2[0]))
            rr = (ri[0] - min(rc1[0], rc2[0])) / max(1e-5, abs(rc1[0] - rc2[0]))
            ratio = clamp((lr + rr) / 2.0, 0.0, 1.0)
            if ratio < 0.33:
                gaze_label, gaze_score = "Side-Left", 45.0
            elif ratio > 0.67:
                gaze_label, gaze_score = "Side-Right", 45.0
            else:
                gaze_label, gaze_score = "Front", 90.0

    # Head pose from normalized face geometry in the local crop.
    nose = _pt(best, 1)
    left_cheek = _pt(best, 234)
    right_cheek = _pt(best, 454)
    chin = _pt(best, 152)
    head_label, head_score = "Unknown", None
    if all(p is not None for p in (nose, left_cheek, right_cheek, chin)):
        mid_x = (left_cheek[0] + right_cheek[0]) / 2.0
        width = max(1e-5, abs(right_cheek[0] - left_cheek[0]))
        yaw = (nose[0] - mid_x) / width
        vertical = chin[1] - nose[1]
        if yaw < -0.16:
            head_label, head_score = "Left", 55.0
        elif yaw > 0.16:
            head_label, head_score = "Right", 55.0
        elif vertical < 0.32:
            head_label, head_score = "Up", 65.0
        elif vertical > 0.48:
            head_label, head_score = "Down", 45.0
        else:
            head_label, head_score = "Front", 90.0

    # Facial cue from eye openness and mouth opening.
    expression_label, expression_score = "Unknown", None
    ltop, lbot = _pt(best, 159), _pt(best, 145)
    rtop, rbot = _pt(best, 386), _pt(best, 374)
    lleft, lright = _pt(best, 33), _pt(best, 133)
    rleft, rright = _pt(best, 362), _pt(best, 263)
    upper_lip, lower_lip = _pt(best, 13), _pt(best, 14)
    mouth_l, mouth_r = _pt(best, 61), _pt(best, 291)

    vals = (ltop, lbot, rtop, rbot, lleft, lright, rleft, rright,
            upper_lip, lower_lip, mouth_l, mouth_r)
    if all(p is not None for p in vals):
        left_eye = _dist2(ltop, lbot) / max(1e-5, _dist2(lleft, lright))
        right_eye = _dist2(rtop, rbot) / max(1e-5, _dist2(rleft, rright))
        eye_open = (left_eye + right_eye) / 2.0
        mouth_open = _dist2(upper_lip, lower_lip) / max(1e-5, _dist2(mouth_l, mouth_r))
        if eye_open < 0.16:
            expression_label, expression_score = "Eyes-Low", 35.0
        elif mouth_open > 0.42:
            expression_label, expression_score = "Mouth-Open", 65.0
        else:
            expression_label, expression_score = "Neutral", 75.0

    return {
        "gaze": (gaze_label, gaze_score),
        "head": (head_label, head_score),
        "expression": (expression_label, expression_score),
    }


def analyze_pose_features(pose_result, face_box, frame_shape):
    if pose_result is None or not pose_result.pose_landmarks:
        return ("Unknown", None)
    fw, fh = frame_shape[1], frame_shape[0]
    fc = np.array(center_of(face_box), dtype=np.float32)
    best = None
    best_dist = float("inf")
    for landmarks in pose_result.pose_landmarks:
        if len(landmarks) < 25:
            continue
        nose = landmarks[0]
        c = np.array([nose.x * fw, nose.y * fh], dtype=np.float32)
        d = float(np.linalg.norm(c - fc))
        if d < best_dist:
            best_dist = d
            best = landmarks
    if best is None or best_dist > max(face_box[2], face_box[3]) * 4.0:
        return ("Unknown", None)

    def xy(i):
        p = best[i]
        return np.array([p.x * fw, p.y * fh], dtype=np.float32)

    nose = xy(0)
    ls, rs = xy(11), xy(12)
    lh, rh = xy(23), xy(24)
    shoulder = (ls + rs) / 2.0
    hip = (lh + rh) / 2.0
    torso = hip - shoulder
    torso_angle = abs(math.degrees(math.atan2(torso[0], -torso[1])))
    head_offset = abs(nose[0] - shoulder[0]) / max(1.0, np.linalg.norm(torso))
    # Threshold raised from 25° → 40°: seated classroom students have natural
    # forward lean of ~15-30°, which was incorrectly classifying all of them as
    # "Leaning" (score 60.0).  40° better separates attentive vs. genuinely
    # slouched posture.
    if torso_angle > 40:
        return ("Leaning", 60.0)
    if head_offset > 0.45:
        return ("Head-Down", 40.0)
    return ("Upright", 90.0)


def movement_feature(track, face):
    # Use center_before_update (set just before previous_center is overwritten)
    # so we compare the face position from the PREVIOUS detection frame.
    old = track.get("center_before_update") or track.get("previous_center")
    if track is None or old is None:
        return ("Unknown", None)
    new = center_of(face)
    d = math.hypot(new[0] - old[0], new[1] - old[1])
    scale = max(face[2], face[3], 1)
    normalized = d / scale
    if normalized < 0.12:
        return ("Normal", 85.0)
    if normalized < 0.35:
        return ("Moving", 65.0)
    return ("Active", 45.0)


def fuse_scores(model_score, feature_values):
    """Fuse only actually measured features. No unknown=50 fallback."""
    values = {"model": model_score}
    values.update(feature_values)
    numerator = 0.0
    denominator = 0.0
    for name, weight in FEATURE_WEIGHTS.items():
        value = values.get(name)
        if value is None:
            continue
        numerator += float(value) * weight
        denominator += weight
    if denominator <= 0:
        return float(model_score), {"used_features": ["model"]}
    return numerator / denominator, {
        "used_features": [k for k in FEATURE_WEIGHTS if values.get(k) is not None]
    }


def level_from_score(score):
    if score >= 66.0:
        return "High"
    if score >= 33.0:
        return "Medium"
    return "Low"


# ============================================================
# DRAWING
# ============================================================
def draw_text(frame, text, x, y, scale=0.55, thickness=2):
    cv2.putText(frame, text, (int(x), int(y)), FONT, scale, (0, 0, 0), thickness + 2, cv2.LINE_AA)
    cv2.putText(frame, text, (int(x), int(y)), FONT, scale, (255, 255, 255), thickness, cv2.LINE_AA)


def draw_student_annotation(frame, face, display_id, pct, level):
    # This function is called ONLY inside the current-face loop.
    x, y, w, h = face
    cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
    id_y = y - 10 if y > 35 else y + 22
    result_y = y + h + 22
    if result_y > frame.shape[0] - 8:
        result_y = y - 36
    draw_text(frame, f"Student {display_id}", x, id_y, 0.58, 2)
    draw_text(frame, f"{pct:.1f}% | {level}", x, result_y, 0.58, 2)


def validate_and_score_crop(crop):
    """Evaluate face crop quality and return (crop, score). Higher score = sharper, larger, valid face crop."""
    if crop is None or crop.size == 0:
        return None, 0.0
    h, w = crop.shape[:2]
    if w < 25 or h < 25:
        return None, 0.0
    aspect = w / max(1.0, float(h))
    if aspect < 0.45 or aspect > 2.2:
        return None, 0.0
    std = float(crop.std())
    if std < 12.0:  # Flat / blank / desk / solid wall
        return None, 0.0
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    score = (w * h) * (1.0 + min(std, 80.0) / 80.0) * (1.0 + min(sharpness, 400.0) / 400.0)
    return crop, score


# ============================================================
# TRACK CREATION
# ============================================================
def create_track(face, hist, frame_number, track_id=1):
    return {
        "track_id": track_id,
        "bbox": face,
        "hist": hist,
        "velocity": (0.0, 0.0),
        "previous_center": center_of(face),
        "first_seen": frame_number,
        "last_seen": frame_number,
        "missing": 0,
        "consecutive_hits": 1,
        "confirmed": False,
        "display_id": None,
        "engagement_sum": 0.0,
        "prediction_count": 0,
        "last_pct": 0.0,
        "last_level": "Unknown",
        "last_class": "Unknown",
        "feature_sums": defaultdict(float),
        "feature_counts": defaultdict(int),
        "last_features": {},
        "best_crop": None,
        "best_crop_score": 0.0,
        "crop_path": None,
    }


# ============================================================
# TILED FACE DETECTION
# ============================================================
def create_tile_face_landmarker():
    """Create an IMAGE-mode Face Landmarker for tiled multi-face detection.

    IMAGE mode is used (not VIDEO) because each tile is an independent
    crop, and the temporal tracking in VIDEO mode would be confused by
    tiles that show different spatial regions of the same frame.

    Configured with low confidence (0.20) to catch small distant faces;
    false positives from tiles are cleaned up by NMS and the confirmation
    tracker (NEW_TRACK_CONFIRMATION = 3 consecutive detection passes).
    """
    if not os.path.exists(FACE_MODEL_PATH):
        raise FileNotFoundError(f"Face Landmarker model not found: {FACE_MODEL_PATH}")
    base = python.BaseOptions(model_asset_path=FACE_MODEL_PATH)
    options = vision.FaceLandmarkerOptions(
        base_options=base,
        running_mode=vision.RunningMode.IMAGE,
        num_faces=15,
        min_face_detection_confidence=0.20,
        min_face_presence_confidence=0.20,
    )
    return vision.FaceLandmarker.create_from_options(options)


def detect_faces_tiled(frame, tile_landmarker, validator_landmarker=None):
    """Detect faces using overlapping tiles for robust small-face detection.

    MediaPipe BlazeFace operates at 192×192 internally, so faces smaller
    than ~10% of the tile width are often missed.  Using a 4×5 grid of
    overlapping tiles means each face is proportionally larger inside its
    tile, enabling reliable detection even for students sitting far from the
    camera in a wide classroom shot.

    Returns a list of (x, y, w, h) bounding boxes in full-frame coordinates,
    de-duplicated across all tiles and validated against non-face artifacts (clocks, walls).
    """
    fh, fw = frame.shape[:2]

    # Calculate tile dimensions with overlap
    tile_w = fw // MP_TILE_COLS
    tile_h = fh // MP_TILE_ROWS
    overlap_x = int(tile_w * MP_TILE_OVERLAP)
    overlap_y = int(tile_h * MP_TILE_OVERLAP)

    all_boxes = []

    for row in range(MP_TILE_ROWS):
        for col in range(MP_TILE_COLS):
            # Tile origin extended by overlap on all sides
            x0 = max(0, col * tile_w - overlap_x)
            y0 = max(0, row * tile_h - overlap_y)
            x1 = min(fw, (col + 1) * tile_w + overlap_x)
            y1 = min(fh, (row + 1) * tile_h + overlap_y)

            tile = frame[y0:y1, x0:x1]
            tw, th = tile.shape[1], tile.shape[0]

            # Skip degenerate tiles
            if tw < 64 or th < 64:
                continue

            rgb = cv2.cvtColor(tile, cv2.COLOR_BGR2RGB)
            mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            result = tile_landmarker.detect(mp_img)

            if not result or not result.face_landmarks:
                continue

            for face_lms in result.face_landmarks:
                # Bbox in tile-local coordinates
                box = bbox_from_landmarks(face_lms, tw, th)
                lx, ly, lw, lh = box

                # Skip boxes that are too small in the tile to be real faces
                if lw < MP_MIN_FACE_SIZE[0] or lh < MP_MIN_FACE_SIZE[1]:
                    continue

                # Wider aspect-ratio window: angled/turned faces can appear
                # taller or wider depending on perspective.
                ratio = lw / max(1.0, float(lh))
                if ratio < 0.40 or ratio > 2.0:
                    continue

                # Map tile-local coords to full-frame coordinates
                gx = lx + x0
                gy = ly + y0
                all_boxes.append((gx, gy, lw, lh))

    # NMS: remove duplicate detections that overlap across tile boundaries
    if not all_boxes:
        return []

    # Sort by area descending (larger = closer/more confident)
    all_boxes.sort(key=lambda b: b[2] * b[3], reverse=True)
    keep = []
    for box in all_boxes:
        is_dup = False
        for kept in keep:
            if calculate_iou(box, kept) > MP_TILE_NMS_IOU:
                is_dup = True
                break
        if not is_dup:
            keep.append(box)

    # Secondary validation: reject false positives (clocks, wall patterns, desks)
    if validator_landmarker is not None:
        validated = []
        for box in keep:
            crop = crop_box(frame, box, pad=0.12)
            if crop is None or crop.size == 0:
                continue
            rgb_crop = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
            mp_crop = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_crop)
            v_res = validator_landmarker.detect(mp_crop)
            if v_res and v_res.face_landmarks:
                validated.append(box)
        return validated

    return keep


# ============================================================
# VIDEO PROCESSING
# ============================================================
def _predictor_result(predictor, face_crop):
    if face_crop is None or face_crop.size == 0:
        return None
    try:
        return predictor.predict(face_crop)
    except Exception as exc:
        print(f"Engagement prediction failed: {exc}")
        return None


def _make_h264_copy(input_path):
    """Create a browser-friendly H.264 copy when FFmpeg is available."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return input_path
    base, _ = os.path.splitext(input_path)
    h264_path = base + "_h264.mp4"
    cmd = [
        ffmpeg, "-y", "-i", input_path,
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", "-an", h264_path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0 and os.path.exists(h264_path) and os.path.getsize(h264_path) > 0:
            return h264_path
    except Exception as exc:
        print(f"H.264 conversion skipped: {exc}")
    return input_path


def process_video(video_path, output_path, crops_dir=None):
    """
    Multimodal video processing with stable, sequential student tracking
    and verified face crops.
    """
    predictor = EngagementPredictor()
    if not predictor.is_model_loaded:
        raise RuntimeError("Trained engagement model is not loaded.")
    if not os.path.exists(video_path):
        raise FileNotFoundError(video_path)

    # ------------------------------------------------------------
    # Speed controls
    # ------------------------------------------------------------
    DETECTION_INTERVAL = 3
    PREDICTION_EVERY_DETECTIONS = 3

    print("\n====================================", flush=True)
    print("EngageVision Multimodal Processing", flush=True)
    print("====================================", flush=True)
    print(f"Input: {video_path}", flush=True)
    print("Engagement model: LOADED", flush=True)
    print("Speed optimization: ENABLED", flush=True)
    print(f"Face detection: MediaPipe tiled detector (every {DETECTION_INTERVAL} frames)", flush=True)
    print(f"AI/features: every {PREDICTION_EVERY_DETECTIONS} detection passes", flush=True)

    face_feature_landmarker = create_face_feature_landmarker()
    pose_landmarker = create_pose_landmarker()
    tile_face_landmarker = create_tile_face_landmarker()

    print(f"MediaPipe Tiled Face Detector: LOADED (IMAGE mode, {MP_TILE_ROWS}x{MP_TILE_COLS} tiles, conf={0.20})", flush=True)
    print("MediaPipe Face Feature Landmarker: LOADED (per-face crop)", flush=True)
    print("MediaPipe Pose Landmarker: LOADED", flush=True)
    print("Eye/Gaze: ENABLED", flush=True)
    print("Head Pose: ENABLED", flush=True)
    print("Facial Cues: ENABLED", flush=True)
    print("Body Posture: ENABLED", flush=True)
    print("Movement: ENABLED", flush=True)
    print("Unknown features: EXCLUDED FROM FUSION", flush=True)
    print("Sequential student IDs: ENABLED", flush=True)
    print("Current-face-only labels: ENABLED", flush=True)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    ow = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    oh = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    scale = min(
        MAX_OUTPUT_WIDTH / max(1, ow),
        MAX_OUTPUT_HEIGHT / max(1, oh),
        1.0,
    )
    width = int(ow * scale)
    height = int(oh * scale)

    print(f"Original resolution: {ow} x {oh}", flush=True)
    print(f"FPS: {fps}", flush=True)
    print(f"Total frames: {total_frames}", flush=True)
    print(f"Output resolution: {width} x {height}", flush=True)
    print("Processing video...", flush=True)

    tracks = {}
    archived = {}
    next_internal_id = 1

    frame_no = 0
    detection_passes = 0
    max_faces = 0
    total_predictions = 0

    # Missing frames tolerance adapted to FPS (~3.5 seconds of head turning / looking down)
    max_missing = max(35, int(fps * 3.5))

    # Store detection boxes and matched track IDs per frame for annotation:
    # frame_detections[frame_no] = [(face_box, tid, current_pct, current_lvl), ...]
    frame_detections = defaultdict(list)

    try:
        # ========================================================
        # PASS 1: Face Detection, Tracking & Multimodal Prediction
        # ========================================================
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            frame_no += 1

            if scale < 1.0:
                frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)

            run_detection = (frame_no == 1 or frame_no % DETECTION_INTERVAL == 0)

            faces = []
            face_hists = []
            assignments = {}
            current_ids = set()

            if run_detection:
                detection_passes += 1
                faces = detect_faces_tiled(frame, tile_face_landmarker, validator_landmarker=face_feature_landmarker)
                max_faces = max(max_faces, len(faces))

                face_hists = [face_histogram(crop_box(frame, f)) for f in faces]

                for track in tracks.values():
                    track["missing"] += 1

                # 1. Match against currently active tracks
                assignments = match_faces_to_tracks(faces, face_hists, tracks)

                # 2. Spatial Re-identification: Match unmatched faces against lost/archived tracks at same desk
                unmatched_faces = [fi for fi in range(len(faces)) if fi not in assignments]
                if unmatched_faces and archived:
                    reid_candidates = []
                    for fi in unmatched_faces:
                        face = faces[fi]
                        for tid, track in archived.items():
                            # Only consider tracks seen within ~20 seconds
                            if (frame_no - track["last_seen"]) > (fps * 20):
                                continue
                            ref = track["bbox"]
                            dist = distance_between(face, ref)
                            limit = max(130.0, 1.4 * max(face[2], face[3], track["bbox"][2], track["bbox"][3]))
                            if dist > limit:
                                continue
                            iou = calculate_iou(face, ref)
                            app = histogram_similarity(face_hists[fi], track.get("hist"))
                            app_pen = 0.5 if app is None else (1.0 - app)
                            score = 0.50 * (dist / limit) + 0.20 * (1.0 - iou) + 0.30 * app_pen
                            reid_candidates.append((score, dist, fi, tid))

                    reid_candidates.sort(key=lambda x: (x[0], x[1]))
                    used_arch = set()
                    for sc, dist, fi, tid in reid_candidates:
                        if fi in assignments or tid in used_arch:
                            continue
                        # Re-activate track from archived back to active tracks!
                        track = archived.pop(tid)
                        tracks[tid] = track
                        assignments[fi] = tid
                        used_arch.add(tid)

                # 3. Create new tracks for still unmatched faces
                for fi, face in enumerate(faces):
                    if fi in assignments:
                        continue
                    tid = next_internal_id
                    next_internal_id += 1
                    tracks[tid] = create_track(face, face_hists[fi], frame_no, track_id=tid)
                    assignments[fi] = tid

                # 4. Update matched tracks
                for fi, face in enumerate(faces):
                    tid = assignments[fi]
                    current_ids.add(tid)
                    track = tracks[tid]

                    old_center = track["previous_center"]
                    new_center = center_of(face)
                    dx = new_center[0] - old_center[0]
                    dy = new_center[1] - old_center[1]
                    ovx, ovy = track["velocity"]
                    track["velocity"] = (0.70 * ovx + 0.30 * dx, 0.70 * ovy + 0.30 * dy)

                    # Save old_center BEFORE overwriting so movement_feature()
                    # can compare previous vs. current position correctly.
                    track["center_before_update"] = old_center
                    track["previous_center"] = new_center
                    track["bbox"] = face
                    track["hist"] = face_hists[fi]
                    track["last_seen"] = frame_no
                    track["missing"] = 0
                    track["consecutive_hits"] += 1

                    # Check face crop quality with a tight face margin (pad=0.08)
                    cand_crop = crop_box(frame, face, pad=0.08)
                    valid_c, c_score = validate_and_score_crop(cand_crop)
                    if valid_c is not None and c_score > track.get("best_crop_score", 0.0):
                        track["best_crop"] = cv2.resize(valid_c, (160, 160), interpolation=cv2.INTER_AREA)
                        track["best_crop_score"] = c_score

                    if not track["confirmed"] and track["consecutive_hits"] >= NEW_TRACK_CONFIRMATION:
                        track["confirmed"] = True

                run_prediction = (detection_passes % PREDICTION_EVERY_DETECTIONS == 0)
                pose_result = None

                if run_prediction and faces:
                    mp_img = mp_image_from_bgr(frame)
                    timestamp_ms = int(round(frame_no * 1000.0 / fps))
                    pose_result = pose_landmarker.detect_for_video(mp_img, timestamp_ms)

                    for fi, face in enumerate(faces):
                        tid = assignments[fi]
                        track = tracks[tid]

                        crop = crop_box(frame, face)
                        result = _predictor_result(predictor, crop)
                        if result is None:
                            continue

                        total_predictions += 1
                        model_pct = float(result.get("engagement_pct", 0.0))

                        face_feature_crop = crop_box(frame, face, pad=0.18)
                        feature_info = {
                            "gaze": ("Unknown", None),
                            "head": ("Unknown", None),
                            "expression": ("Unknown", None),
                        }

                        if face_feature_crop is not None and face_feature_crop.size > 0:
                            feature_result = face_feature_landmarker.detect(mp_image_from_bgr(face_feature_crop))
                            feature_info = analyze_face_features(feature_result, face, frame.shape)

                        posture_label, posture_score = analyze_pose_features(pose_result, face, frame.shape)
                        movement_label, movement_score = movement_feature(track, face)

                        raw_features = {
                            "gaze": feature_info["gaze"],
                            "head": feature_info["head"],
                            "expression": feature_info["expression"],
                            "posture": (posture_label, posture_score),
                            "movement": (movement_label, movement_score),
                        }

                        numeric = {"model": model_pct}
                        labels = {}

                        for name, pair in raw_features.items():
                            label, score = pair
                            labels[name] = label
                            if score is not None:
                                numeric[name] = float(score)
                                track["feature_sums"][name] += float(score)
                                track["feature_counts"][name] += 1

                        fused, meta = fuse_scores(model_pct, {k: v for k, v in numeric.items() if k != "model"})
                        level = level_from_score(fused)
                        print(
    f"[SCORE] Model={model_pct:.1f}, "
    f"Features={numeric}, "
    f"Final={fused:.1f}, "
    f"Level={level}",
    flush=True
)

                        track["engagement_sum"] += fused
                        track["prediction_count"] += 1
                        track["last_pct"] = fused
                        track["last_level"] = level
                        track["last_class"] = result.get("class_label", "Unknown")
                        track["last_features"] = labels

                # Record detection bboxes and active tracks for this frame
                for fi, face in enumerate(faces):
                    tid = assignments[fi]
                    track = tracks.get(tid)
                    if track is not None:
                        frame_detections[frame_no].append((face, tid, track["last_pct"], track["last_level"]))

                for tid, track in list(tracks.items()):
                    if tid not in current_ids:
                        track["consecutive_hits"] = 0

                expired = [tid for tid, track in tracks.items() if track["missing"] > max_missing]
                for tid in expired:
                    archived[tid] = tracks.pop(tid)

            if frame_no % 25 == 0:
                print(f"Frame {frame_no} / {total_frames}", flush=True)

    finally:
        tile_face_landmarker.close()
        face_feature_landmarker.close()
        pose_landmarker.close()

    # ============================================================
    # CONFIRMATION, DEDUPLICATION & SEQUENTIAL FINAL STUDENT NUMBERING (1 .. N)
    # ============================================================
    all_tracks = {}
    all_tracks.update(archived)
    all_tracks.update(tracks)

    # Spatial Track Deduplication / Cluster Merging:
    # If two tracks represent the same physical seat in the classroom, merge them
    track_list = sorted(all_tracks.values(), key=lambda t: t.get("consecutive_hits", 0), reverse=True)
    merged_into = {}

    for i in range(len(track_list)):
        t1 = track_list[i]
        tid1 = t1["track_id"]
        if tid1 in merged_into:
            continue
        c1 = center_of(t1["bbox"])
        for j in range(i + 1, len(track_list)):
            t2 = track_list[j]
            tid2 = t2["track_id"]
            if tid2 in merged_into:
                continue
            c2 = center_of(t2["bbox"])
            dist = math.hypot(c1[0] - c2[0], c1[1] - c2[1])
            max_dim = max(t1["bbox"][2], t1["bbox"][3], t2["bbox"][2], t2["bbox"][3])

            # Use a conservative threshold: only merge if centers are within 0.5× the
            # larger face dimension, with a floor of 40px.  The previous 1.2× threshold
            # was wide enough to collapse two adjacent real students (whose face centers
            # are typically 1–2 face-widths apart) into one track, which caused the
            # same Student ID to appear on two different faces in the output video.
            if dist < max(40.0, 0.5 * max_dim):
                merged_into[tid2] = tid1
                t1["engagement_sum"] += t2.get("engagement_sum", 0.0)
                t1["prediction_count"] += t2.get("prediction_count", 0)
                t1["consecutive_hits"] += t2.get("consecutive_hits", 0)
                for name, total in t2.get("feature_sums", {}).items():
                    t1["feature_sums"][name] += total
                    t1["feature_counts"][name] += t2.get("feature_counts", {}).get(name, 0)
                if t2.get("best_crop_score", 0.0) > t1.get("best_crop_score", 0.0):
                    t1["best_crop"] = t2["best_crop"]
                    t1["best_crop_score"] = t2["best_crop_score"]
                t1["first_seen"] = min(t1["first_seen"], t2["first_seen"])
                t1["last_seen"] = max(t1["last_seen"], t2["last_seen"])
                if t2.get("confirmed", False):
                    t1["confirmed"] = True

    # Genuine confirmed students
    min_preds = max(1, min(MIN_FINAL_PREDICTIONS, total_predictions // max(1, len(all_tracks) * 2)))
    valid_tracks = [
        t for tid, t in all_tracks.items()
        if tid not in merged_into and t["confirmed"] and (t["prediction_count"] >= min_preds or t.get("consecutive_hits", 0) >= 6)
    ]
    if not valid_tracks:
        valid_tracks = [
            t for tid, t in all_tracks.items()
            if tid not in merged_into and t["confirmed"] and t["prediction_count"] > 0
        ]
    if not valid_tracks:
        valid_tracks = [
            t for tid, t in all_tracks.items()
            if tid not in merged_into and t["prediction_count"] > 0
        ]

    # Sort deterministically by natural classroom spatial coordinates (top-to-bottom, left-to-right)
    valid_tracks.sort(key=lambda t: (t["bbox"][1], t["bbox"][0]))

    if crops_dir:
        os.makedirs(crops_dir, exist_ok=True)

    track_id_to_student = {}
    results = []

    for sequential_id, track in enumerate(valid_tracks, start=1):
        track["final_id"] = sequential_id
        track_id_to_student[track["track_id"]] = track

        # Save actual face crop belonging to this student
        crop_path = None
        if crops_dir:
            crop_filename = f"student_{sequential_id}.jpg"
            crop_abs = os.path.join(crops_dir, crop_filename)
            if track["best_crop"] is not None:
                cv2.imwrite(crop_abs, track["best_crop"], [cv2.IMWRITE_JPEG_QUALITY, 95])
                crop_path = crop_abs
            track["crop_path"] = crop_path

        overall = track["engagement_sum"] / max(1, track["prediction_count"])
        feature_scores = {}
        for name, total in track["feature_sums"].items():
            count = track["feature_counts"].get(name, 0)
            if count:
                feature_scores[name] = total / count

        results.append({
            "student_id": sequential_id,
            "engagement_pct": round(overall, 2),
            "level": level_from_score(overall),
            "predictions": track["prediction_count"],
            "last_class": track["last_class"],
            "features": track["last_features"],
            "feature_scores": feature_scores,
            "crop_path": crop_path,
        })

    # ============================================================
    # PASS 2: Output Video Generation with Final Sequential IDs
    # ============================================================
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    out = cv2.VideoWriter(
        output_path,
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (width, height),
    )
    if not out.isOpened():
        cap.release()
        raise RuntimeError("Could not create output video.")

    try:
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        draw_frame_no = 0

        while True:
            ok, frame = cap.read()
            if not ok:
                break
            draw_frame_no += 1

            if scale < 1.0:
                frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)

            visible_count = 0
            if draw_frame_no in frame_detections:
                # Guard: each unique sequential Student ID must appear at most once
                # per frame.  Without this, two raw track IDs that were spatially
                # merged into the same root both resolve to the same final_id and
                # would be drawn on two different face boxes with identical labels.
                annotated_sids = set()
                for face_box, raw_tid, cur_pct, cur_lvl in frame_detections[draw_frame_no]:
                    tid = merged_into.get(raw_tid, raw_tid)
                    if tid in track_id_to_student:
                        st = track_id_to_student[tid]
                        sid = st["final_id"]
                        if sid in annotated_sids:
                            continue  # already drew this student ID in this frame
                        annotated_sids.add(sid)
                        pct = cur_pct if cur_pct > 0 else (st["engagement_sum"] / max(1, st["prediction_count"]))
                        lvl = cur_lvl if cur_lvl != "Unknown" else level_from_score(pct)
                        draw_student_annotation(frame, face_box, sid, pct, lvl)
                        visible_count += 1

            draw_text(frame, f"Students detected: {len(results)} | Visible: {visible_count}", 18, 32, 0.60, 2)
            draw_text(frame, "Multimodal AI: ON", 18, 62, 0.60, 2)
            draw_text(frame, f"Frame: {draw_frame_no}/{total_frames}", 18, 92, 0.60, 2)

            out.write(frame)

    finally:
        cap.release()
        out.release()
        cv2.destroyAllWindows()

    print("Processing completed.", flush=True)

    if not os.path.exists(output_path):
        raise RuntimeError("Processed output video was not created.")

    browser_output = _make_h264_copy(output_path)

    return {
        "frames_processed": frame_no,
        "max_faces_detected": max_faces,
        "total_predictions": total_predictions,
        "students_tracked": len(results),
        "students": results,
        "output_path": browser_output,
        "original_output_path": output_path,
        "width": width,
        "height": height,
        "fps": fps,
    }
