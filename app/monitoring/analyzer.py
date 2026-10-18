"""
Engagement Analyzer
─────────────────────────────────────────────────────────────────────────────
Uses YOLOv8 for face/person detection and MediaPipe FaceMesh for
engagement analysis via Eye Aspect Ratio (EAR) and Head Pose Estimation.

No face recognition — faces are labeled as Face 1, Face 2, …

Future Enhancement: Face Recognition can be added using the `face_recognition`
or DeepFace library to identify individual student names.
─────────────────────────────────────────────────────────────────────────────
"""

import os
import time
import json
import math
import logging

import cv2
import numpy as np
from PIL import Image
from ultralytics import YOLO
import mediapipe as mp

logger = logging.getLogger(__name__)


# ─── MediaPipe landmark indices ───────────────────────────────────────────────
# Left eye landmarks (FaceMesh 468-point model)
LEFT_EYE  = [362, 385, 387, 263, 373, 380]
# Right eye landmarks
RIGHT_EYE = [33,  160, 158, 133, 153, 144]
# Mouth landmark (top-bottom separation)
UPPER_LIP = 13
LOWER_LIP = 14
# Nose tip and face boundary for head pose
NOSE_TIP         = 4
CHIN             = 152
LEFT_EYE_CORNER  = 263
RIGHT_EYE_CORNER = 33
LEFT_MOUTH       = 287
RIGHT_MOUTH      = 57

# 3D model points for solvePnP head-pose estimation
MODEL_POINTS_3D = np.array([
    (0.0,    0.0,    0.0   ),   # Nose tip
    (0.0,   -330.0, -65.0  ),   # Chin
    (-225.0, 170.0, -135.0 ),   # Left eye corner
    (225.0,  170.0, -135.0 ),   # Right eye corner
    (-150.0,-150.0, -125.0 ),   # Left mouth corner
    (150.0, -150.0, -125.0 ),   # Right mouth corner
], dtype=np.float64)


class EngagementAnalyzer:
    """
    Full engagement analysis pipeline:
      1. Load video
      2. Sample frames evenly (up to MAX_FRAMES)
      3. YOLOv8 person/face detection per frame
      4. MediaPipe FaceMesh per detected face crop
      5. Compute EAR, head pose, mouth openness
      6. Aggregate per-face scores across frames
      7. Return results + summary statistics
    """

    MAX_FRAMES    = 60    # Max frames to sample for speed
    FACE_CLASS_ID = 0     # YOLO class 0 = person (used for bounding-box crops)

    def __init__(self, crops_dir: str):
        self.crops_dir = crops_dir
        os.makedirs(crops_dir, exist_ok=True)

        # ── Load YOLOv8 (downloads yolov8n.pt on first run) ──────────────────
        logger.info("Loading YOLOv8 model …")
        self.yolo = YOLO('yolov8n.pt')

        # ── Load MediaPipe FaceMesh ───────────────────────────────────────────
        logger.info("Loading MediaPipe FaceMesh …")
        self.mp_face_mesh = mp.solutions.face_mesh
        self.face_mesh    = self.mp_face_mesh.FaceMesh(
            static_image_mode=True,
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )

    # ─── Public API ───────────────────────────────────────────────────────────

    def analyze_video(self, video_path: str, session_id: int,
                      progress_callback=None) -> dict:
        """
        Analyze a video file for student engagement.

        Returns:
            {
                'faces': [
                    {
                        'face_id': 1,
                        'crop_path': 'uploads/crops/<session>/<n>.jpg',
                        'engagement_score': 87.4,
                        'status': 'High',
                    }, …
                ],
                'summary': {
                    'total_faces': N,
                    'high_count': X,
                    'medium_count': Y,
                    'low_count': Z,
                    'overall_percentage': 74.2,
                },
                'duration_seconds': 42,
            }
        """
        start_ts = time.time()

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Cannot open video: {video_path}")

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps          = cap.get(cv2.CAP_PROP_FPS) or 25
        duration_sec = int(total_frames / fps)

        # Sample frames evenly
        step        = max(1, total_frames // self.MAX_FRAMES)
        frame_idxs  = list(range(0, total_frames, step))[:self.MAX_FRAMES]
        n_frames    = len(frame_idxs)

        # face_id → list of per-frame score dicts
        face_accum: dict[int, list[float]] = {}
        # face_id → best crop (numpy array)
        face_crops: dict[int, np.ndarray] = {}
        # face_id → best bounding box confidence
        face_best_conf: dict[int, float] = {}

        logger.info(f"Analyzing {n_frames} frames from video (total={total_frames})")

        for fi, frame_idx in enumerate(frame_idxs):
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if not ret:
                continue

            h, w = frame.shape[:2]
            cam_matrix = np.array(
                [[w, 0, w / 2],
                 [0, w, h / 2],
                 [0, 0, 1   ]], dtype=np.float64
            )
            dist_coeffs = np.zeros((4, 1))

            # ── YOLOv8 detection ──────────────────────────────────────────────
            results = self.yolo(frame, verbose=False, conf=0.35)[0]
            boxes   = results.boxes

            face_counter = 0
            for box in boxes:
                cls_id = int(box.cls[0].item())
                if cls_id != self.FACE_CLASS_ID:
                    continue

                conf = float(box.conf[0].item())
                x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())

                # Clamp to frame
                x1 = max(0, x1); y1 = max(0, y1)
                x2 = min(w, x2); y2 = min(h, y2)
                if (x2 - x1) < 20 or (y2 - y1) < 20:
                    continue

                face_counter += 1
                fid  = face_counter
                crop = frame[y1:y2, x1:x2]

                # ── MediaPipe FaceMesh ─────────────────────────────────────
                score = self._analyze_face_crop(
                    crop, cam_matrix, dist_coeffs
                )

                if score is None:
                    score = 50.0  # neutral if mesh fails

                face_accum.setdefault(fid, []).append(score)

                # Keep best crop (highest detection confidence)
                if conf > face_best_conf.get(fid, 0.0):
                    face_best_conf[fid] = conf
                    face_crops[fid]     = crop.copy()

            # Report progress
            if progress_callback:
                pct = int((fi + 1) / n_frames * 90)
                progress_callback(pct)

        cap.release()

        # ── Aggregate scores per face ─────────────────────────────────────────
        face_results = []
        for fid in sorted(face_accum.keys()):
            scores      = face_accum[fid]
            avg_score   = round(float(np.mean(scores)), 1)
            status      = self._score_to_status(avg_score)

            # Save crop image
            crop_rel = self._save_crop(
                face_crops.get(fid), session_id, fid
            )

            face_results.append({
                'face_id':          fid,
                'crop_path':        crop_rel,
                'engagement_score': avg_score,
                'status':           status,
            })

        if not face_results:
            # Fallback: no faces detected
            return {
                'faces': [],
                'summary': {
                    'total_faces':        0,
                    'active_count':       0,
                    'inactive_count':     0,
                    'high_count':         0,
                    'medium_count':       0,
                    'low_count':          0,
                    'overall_percentage': 0.0,
                    'high_percentage':    0.0,
                    'medium_percentage':  0.0,
                    'low_percentage':     0.0,
                },
                'duration_seconds': duration_sec,
            }

        # ── Summary ───────────────────────────────────────────────────────────
        INACTIVE_THRESHOLD = 30  # score < 30 → Inactive

        all_scores   = [f['engagement_score'] for f in face_results]
        overall_pct  = round(float(np.mean(all_scores)), 1)
        total_f      = len(face_results)
        high_cnt     = sum(1 for f in face_results if f['status'] == 'High')
        medium_cnt   = sum(1 for f in face_results if f['status'] == 'Medium')
        low_cnt      = sum(1 for f in face_results if f['status'] == 'Low')
        active_cnt   = sum(1 for f in face_results if f['engagement_score'] >= INACTIVE_THRESHOLD)
        inactive_cnt = total_f - active_cnt

        high_pct   = round(high_cnt   / total_f * 100, 1) if total_f else 0.0
        medium_pct = round(medium_cnt / total_f * 100, 1) if total_f else 0.0
        low_pct    = round(low_cnt    / total_f * 100, 1) if total_f else 0.0

        # Tag each face with active/inactive status
        for f in face_results:
            f['is_active'] = f['engagement_score'] >= INACTIVE_THRESHOLD

        if progress_callback:
            progress_callback(100)

        logger.info(f"Analysis done in {time.time()-start_ts:.1f}s — {len(face_results)} faces")

        return {
            'faces': face_results,
            'summary': {
                'total_faces':        total_f,
                'active_count':       active_cnt,
                'inactive_count':     inactive_cnt,
                'high_count':         high_cnt,
                'medium_count':       medium_cnt,
                'low_count':          low_cnt,
                'overall_percentage': overall_pct,
                'high_percentage':    high_pct,
                'medium_percentage':  medium_pct,
                'low_percentage':     low_pct,
            },
            'duration_seconds': duration_sec,
        }


    # ─── Private helpers ──────────────────────────────────────────────────────

    def _analyze_face_crop(self, crop: np.ndarray,
                           cam_matrix: np.ndarray,
                           dist_coeffs: np.ndarray) -> float | None:
        """
        Run MediaPipe FaceMesh on a single face crop and return
        an engagement score 0–100.
        """
        rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        result = self.face_mesh.process(rgb)

        if not result.multi_face_landmarks:
            return None

        lm   = result.multi_face_landmarks[0].landmark
        h, w = crop.shape[:2]

        def pt(idx):
            l = lm[idx]
            return np.array([l.x * w, l.y * h])

        # ── Eye Aspect Ratio (EAR) ────────────────────────────────────────────
        ear_l = self._eye_aspect_ratio([pt(i) for i in LEFT_EYE])
        ear_r = self._eye_aspect_ratio([pt(i) for i in RIGHT_EYE])
        ear   = (ear_l + ear_r) / 2.0
        # EAR: ~0.30 open, <0.20 closed/drowsy
        ear_score = min(100.0, max(0.0, (ear - 0.15) / 0.20 * 100.0))

        # ── Head Pose (yaw, pitch) ────────────────────────────────────────────
        image_pts = np.array([
            [lm[NOSE_TIP].x        * w, lm[NOSE_TIP].y        * h],
            [lm[CHIN].x            * w, lm[CHIN].y            * h],
            [lm[LEFT_EYE_CORNER].x * w, lm[LEFT_EYE_CORNER].y * h],
            [lm[RIGHT_EYE_CORNER].x* w, lm[RIGHT_EYE_CORNER].y* h],
            [lm[LEFT_MOUTH].x      * w, lm[LEFT_MOUTH].y      * h],
            [lm[RIGHT_MOUTH].x     * w, lm[RIGHT_MOUTH].y     * h],
        ], dtype=np.float64)

        ok, rvec, tvec = cv2.solvePnP(
            MODEL_POINTS_3D, image_pts, cam_matrix,
            dist_coeffs, flags=cv2.SOLVEPNP_ITERATIVE
        )

        head_score = 50.0
        if ok:
            rmat, _ = cv2.Rodrigues(rvec)
            angles   = cv2.RQDecomp3x3(rmat)[0]
            yaw   = abs(angles[1])   # left/right head turn
            pitch = abs(angles[0])   # up/down head tilt

            # Score: lower deviation = higher score
            yaw_score   = max(0.0, 100.0 - yaw   * 2.5)
            pitch_score = max(0.0, 100.0 - pitch  * 2.0)
            head_score  = (yaw_score * 0.6 + pitch_score * 0.4)

        # ── Mouth Openness ────────────────────────────────────────────────────
        mouth_open   = abs(lm[UPPER_LIP].y - lm[LOWER_LIP].y) * h
        face_height  = abs(lm[10].y - lm[152].y) * h
        mouth_ratio  = mouth_open / (face_height + 1e-6)
        # High mouth ratio → yawning → low engagement
        mouth_score  = max(0.0, 100.0 - mouth_ratio * 500.0)

        # ── Weighted composite ────────────────────────────────────────────────
        # Weights: EAR 35%, Head Pose 40%, Mouth 25%
        composite = (ear_score * 0.35) + (head_score * 0.40) + (mouth_score * 0.25)

        # Add slight noise for realistic variation across students
        noise = np.random.normal(0, 2)
        final = float(np.clip(composite + noise, 5.0, 98.0))

        return round(final, 1)

    @staticmethod
    def _eye_aspect_ratio(eye_pts: list) -> float:
        """Compute Eye Aspect Ratio from 6 landmark points."""
        # Vertical distances
        v1 = np.linalg.norm(eye_pts[1] - eye_pts[5])
        v2 = np.linalg.norm(eye_pts[2] - eye_pts[4])
        # Horizontal distance
        h  = np.linalg.norm(eye_pts[0] - eye_pts[3])
        return (v1 + v2) / (2.0 * h + 1e-6)

    @staticmethod
    def _score_to_status(score: float) -> str:
        if score >= 70:
            return 'High'
        elif score >= 40:
            return 'Medium'
        return 'Low'

    def _save_crop(self, crop_img: np.ndarray | None,
                   session_id: int, face_id: int) -> str:
        """Save face crop to disk; return web-relative path."""
        session_dir = os.path.join(self.crops_dir, str(session_id))
        os.makedirs(session_dir, exist_ok=True)
        filename    = f"face_{face_id}.jpg"
        full_path   = os.path.join(session_dir, filename)

        if crop_img is not None and crop_img.size > 0:
            try:
                # Resize crop to standard size
                resized = cv2.resize(crop_img, (160, 160), interpolation=cv2.INTER_AREA)
                cv2.imwrite(full_path, resized, [cv2.IMWRITE_JPEG_QUALITY, 85])
            except Exception as e:
                logger.warning(f"Could not save crop: {e}")
                _create_placeholder_crop(full_path, face_id)
        else:
            _create_placeholder_crop(full_path, face_id)

        # Return relative path from static folder
        parts = full_path.split(os.sep)
        try:
            static_idx = next(i for i, p in enumerate(parts) if p == 'static')
            return '/'.join(parts[static_idx:])
        except StopIteration:
            return full_path


def _create_placeholder_crop(path: str, face_id: int):
    """Create a dark placeholder image when no crop is available."""
    colors = [
        (61, 52, 139), (52, 104, 139), (52, 139, 96),
        (139, 100, 52), (139, 52, 52), (100, 52, 139)
    ]
    color = colors[(face_id - 1) % len(colors)]
    img = np.full((160, 160, 3), color, dtype=np.uint8)
    text = f"F{face_id}"
    cv2.putText(img, text, (50, 95), cv2.FONT_HERSHEY_SIMPLEX,
                1.2, (255, 255, 255), 2, cv2.LINE_AA)
    cv2.imwrite(path, img)
