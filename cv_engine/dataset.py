"""
cv_engine/dataset.py — DAiSEE Dataset Preparation Utilities
══════════════════════════════════════════════════════════════════
Handles parsing DAiSEE CSV labels, extracting frames from video
clips, detecting/cropping faces, and building TF dataset pipelines.

DAiSEE Structure:
    DAiSEE/
    ├── DataSet/
    │   ├── Train/{subject}/{clip_id}/ → .jpg frames (or .avi videos)
    │   ├── Test/...
    │   └── Validation/...
    └── Labels/
        ├── TrainLabels.csv
        ├── TestLabels.csv
        └── ValidationLabels.csv

Label CSV Format:
    ClipID, Boredom, Engagement, Confusion, Frustration
    110001/1100011001.avi, 0, 2, 1, 0
"""

import os
import logging
import random

import cv2
import numpy as np

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# LABEL PARSING
# ═══════════════════════════════════════════════════════════════════════════════

def parse_labels(csv_path):
    """
    Parse a DAiSEE label CSV file and extract the Engagement column.

    Args:
        csv_path: Path to TrainLabels.csv, TestLabels.csv, or
                  ValidationLabels.csv.

    Returns:
        dict: {clip_id: engagement_label} where engagement_label is 0-3.
              clip_id is the relative path like '110001/1100011001'.
    """
    import pandas as pd

    if not os.path.isfile(csv_path):
        raise FileNotFoundError(f"Label file not found: {csv_path}")

    df = pd.read_csv(csv_path)

    # Normalize column names (strip whitespace)
    df.columns = df.columns.str.strip()

    # Find the ClipID and Engagement columns
    clip_col = None
    eng_col = None
    for col in df.columns:
        col_lower = col.lower()
        if 'clip' in col_lower or col_lower == df.columns[0].lower():
            clip_col = col
        if 'engagement' in col_lower:
            eng_col = col

    if clip_col is None:
        clip_col = df.columns[0]
    if eng_col is None:
        raise ValueError(
            f"Could not find 'Engagement' column in {csv_path}. "
            f"Available columns: {list(df.columns)}"
        )

    labels = {}
    for _, row in df.iterrows():
        clip_id = str(row[clip_col]).strip()
        # Remove file extension if present
        if clip_id.endswith('.avi') or clip_id.endswith('.csv'):
            clip_id = os.path.splitext(clip_id)[0]
        engagement = int(row[eng_col])
        labels[clip_id] = engagement

    logger.info(
        f"Parsed {len(labels)} labels from {os.path.basename(csv_path)} "
        f"(Engagement distribution: "
        f"VL={sum(1 for v in labels.values() if v==0)}, "
        f"L={sum(1 for v in labels.values() if v==1)}, "
        f"H={sum(1 for v in labels.values() if v==2)}, "
        f"VH={sum(1 for v in labels.values() if v==3)})"
    )

    return labels


# ═══════════════════════════════════════════════════════════════════════════════
# FRAME EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════════

def extract_frames_from_video(video_path, max_frames=3):
    """
    Extract evenly-spaced frames from a video file.

    Args:
        video_path: Path to .avi video clip.
        max_frames: Maximum number of frames to extract.

    Returns:
        list[np.ndarray]: List of BGR frame arrays.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        logger.warning(f"Cannot open video: {video_path}")
        return []

    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total <= 0:
        cap.release()
        return []

    # Pick evenly-spaced frame indices
    if total <= max_frames:
        indices = list(range(total))
    else:
        step = total / max_frames
        indices = [int(i * step) for i in range(max_frames)]

    frames = []
    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        if ret and frame is not None:
            frames.append(frame)

    cap.release()
    return frames


def load_frames_from_directory(frame_dir, max_frames=3):
    """
    Load pre-extracted frame images (.jpg/.png) from a directory.

    Some DAiSEE distributions provide pre-extracted frames instead
    of video files.

    Args:
        frame_dir:  Directory containing frame images.
        max_frames: Maximum number of frames to load.

    Returns:
        list[np.ndarray]: List of BGR frame arrays.
    """
    if not os.path.isdir(frame_dir):
        return []

    image_files = sorted([
        f for f in os.listdir(frame_dir)
        if f.lower().endswith(('.jpg', '.jpeg', '.png'))
    ])

    if not image_files:
        return []

    # Sample evenly if too many
    if len(image_files) > max_frames:
        image_files = random.sample(image_files, max_frames)

    frames = []
    for fname in image_files:
        fpath = os.path.join(frame_dir, fname)
        img = cv2.imread(fpath)
        if img is not None:
            frames.append(img)

    return frames


# ═══════════════════════════════════════════════════════════════════════════════
# FACE DETECTION AND CROPPING
# ═══════════════════════════════════════════════════════════════════════════════

# Lazy-loaded face detector
_face_cascade = None


def _get_face_cascade():
    """Get the OpenCV Haar cascade face detector (lazy loaded)."""
    global _face_cascade
    if _face_cascade is None:
        cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        _face_cascade = cv2.CascadeClassifier(cascade_path)
        if _face_cascade.empty():
            raise RuntimeError(
                f"Failed to load Haar cascade from: {cascade_path}"
            )
    return _face_cascade


def detect_and_crop_face(frame, target_size=(224, 224)):
    """
    Detect the largest face in a frame and crop+resize it.

    DAiSEE videos typically contain a single student's face.
    We detect the largest face and resize it to the model's input size.

    Args:
        frame:       BGR numpy array (video frame or image).
        target_size: Output size as (width, height).

    Returns:
        np.ndarray or None: Resized face crop (BGR, target_size), or
                            None if no face is detected.
    """
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    cascade = _get_face_cascade()

    faces = cascade.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=5,
        minSize=(30, 30),
    )

    if len(faces) == 0:
        # Fallback: use the entire frame as a "face" (DAiSEE clips are
        # already face-centric, so this is often acceptable)
        return cv2.resize(frame, target_size, interpolation=cv2.INTER_AREA)

    # Pick the largest face (by area)
    x, y, w, h = max(faces, key=lambda f: f[2] * f[3])

    # Add padding (10% on each side) for context
    pad_w = int(w * 0.1)
    pad_h = int(h * 0.1)
    fx = max(0, x - pad_w)
    fy = max(0, y - pad_h)
    fw = min(frame.shape[1], x + w + pad_w)
    fh = min(frame.shape[0], y + h + pad_h)

    face_crop = frame[fy:fh, fx:fw]

    if face_crop.size == 0:
        return None

    return cv2.resize(face_crop, target_size, interpolation=cv2.INTER_AREA)


# ═══════════════════════════════════════════════════════════════════════════════
# DATASET BUILDING
# ═══════════════════════════════════════════════════════════════════════════════

def prepare_dataset(dataset_dir, labels_csv, max_frames_per_clip=None):
    """
    Build numpy arrays of face crops and engagement labels from DAiSEE.

    Walks through the dataset directory, extracts frames from each
    video/image clip, detects and crops faces, and pairs them with
    the corresponding engagement label.

    IMPORTANT: Images are stored as uint8 [0-255] to save memory.
    The model's built-in preprocess_input layer handles normalization
    to [-1, 1] during forward pass. Do NOT normalize here.

    Args:
        dataset_dir:         Path to Train/, Test/, or Validation/ directory.
        labels_csv:          Path to the corresponding labels CSV file.
        max_frames_per_clip: Max frames per clip (default from config).

    Returns:
        tuple: (images, labels)
            images: np.ndarray of shape (N, 224, 224, 3), dtype uint8, [0-255]
            labels: np.ndarray of shape (N,), dtype int32, values 0-3
    """
    from cv_engine.config import IMG_SIZE, MAX_FRAMES_PER_CLIP as DEFAULT_MAX

    if max_frames_per_clip is None:
        max_frames_per_clip = DEFAULT_MAX

    # Parse labels
    clip_labels = parse_labels(labels_csv)

    images = []
    labels = []
    processed = 0
    skipped = 0

    # Walk through subject directories
    if not os.path.isdir(dataset_dir):
        raise FileNotFoundError(f"Dataset directory not found: {dataset_dir}")
    subjects = sorted(os.listdir(dataset_dir))
    subjects = sorted(os.listdir(dataset_dir))[:2]
    for subject in subjects:
        subject_dir = os.path.join(dataset_dir, subject)
        if not os.path.isdir(subject_dir):
            continue

        clips = sorted(os.listdir(subject_dir))
        for clip in clips:
            clip_dir = os.path.join(subject_dir, clip)

            # Build the clip ID to match label CSV format
            clip_id = f"{subject}/{clip}"

            # Find the engagement label — try multiple key formats
            # DAiSEE CSVs may use just the clip name (e.g. '1100011001')
            # or subject/clip (e.g. '110001/1100011001')
            label = clip_labels.get(clip_id)
            if label is None:
                label = clip_labels.get(clip)
                if label is None:
                    skipped += 1
                    continue

                        # Extract frames
            if os.path.isdir(clip_dir):

                # First try pre-extracted image frames
                frames = load_frames_from_directory(
                    clip_dir,
                    max_frames=max_frames_per_clip
                )

                # If no images, look for AVI inside the clip folder
                if not frames:
                    avi_path = os.path.join(
                        clip_dir,
                        f"{clip}.avi"
                    )

                    if os.path.isfile(avi_path):
                        frames = extract_frames_from_video(
                            avi_path,
                            max_frames=max_frames_per_clip
                        )
                    else:
                        # Search for any AVI inside the folder
                        avi_files = [
                            f for f in os.listdir(clip_dir)
                            if f.lower().endswith(".avi")
                        ]

                        if avi_files:
                            avi_path = os.path.join(
                                clip_dir,
                                avi_files[0]
                            )

                            frames = extract_frames_from_video(
                                avi_path,
                                max_frames=max_frames_per_clip
                            )

            elif os.path.isfile(clip_dir) and clip.lower().endswith(".avi"):

                frames = extract_frames_from_video(
                    clip_dir,
                    max_frames=max_frames_per_clip
                )

            else:
                frames = []

            if not frames:
                skipped += 1
                continue

            # Process each frame — keep as uint8 to save memory
            # (model's preprocess_input handles [0,255] → [-1,1])
            for frame in frames:
                face = detect_and_crop_face(frame, target_size=IMG_SIZE)
                if face is not None:
                    images.append(face)  # uint8, [0-255]
                    labels.append(label)
                    processed += 1

    logger.info(
        f"Dataset prepared: {processed} face samples from "
        f"{len(clip_labels)} clips "
        f"(skipped {skipped} clips with missing labels/data)"
    )

    if processed == 0:
        logger.warning("No samples were prepared! Check dataset paths and labels.")
        return np.array([], dtype=np.uint8), np.array([], dtype=np.int32)

    return np.array(images, dtype=np.uint8), np.array(labels, dtype=np.int32)


def create_tf_dataset(images, labels, batch_size=None, augment=False, shuffle=True):
    """
    Create a tf.data.Dataset from numpy arrays.

    Images are expected as uint8 [0-255]. They are cast to float32
    inside the pipeline (NOT normalized — the model's built-in
    preprocess_input handles [0,255] → [-1,1] during forward pass).

    Args:
        images:     np.ndarray of shape (N, 224, 224, 3), uint8 [0-255].
        labels:     np.ndarray of shape (N,), int32.
        batch_size: Batch size (default from config).
        augment:    Whether to apply data augmentation.
        shuffle:    Whether to shuffle the dataset.

    Returns:
        tf.data.Dataset — batched, with float32 images in [0, 255].
    """
    import tensorflow as tf
    from cv_engine.config import BATCH_SIZE

    if batch_size is None:
        batch_size = BATCH_SIZE

    dataset = tf.data.Dataset.from_tensor_slices((images, labels))

    if shuffle:
        dataset = dataset.shuffle(buffer_size=min(len(images), 10000))

    # Cast uint8 → float32 (keep [0, 255] range for preprocess_input)
    dataset = dataset.map(
        lambda img, lbl: (tf.cast(img, tf.float32), lbl),
        num_parallel_calls=tf.data.AUTOTUNE,
    )

    if augment:
        dataset = dataset.map(
            _augment_fn,
            num_parallel_calls=tf.data.AUTOTUNE,
        )

    dataset = dataset.batch(batch_size)
    dataset = dataset.prefetch(tf.data.AUTOTUNE)

    return dataset


def _augment_fn(image, label):
    """Apply data augmentation to a single image-label pair.

    Input image is float32 in [0, 255] range.
    Output is clipped to [0, 255] to stay compatible with preprocess_input.
    """
    import tensorflow as tf

    # Random horizontal flip
    image = tf.image.random_flip_left_right(image)
    # Random brightness (scale delta for [0,255] range)
    image = tf.image.random_brightness(image, max_delta=30.0)
    # Random contrast
    image = tf.image.random_contrast(image, lower=0.85, upper=1.15)
    # Random saturation
    image = tf.image.random_saturation(image, lower=0.85, upper=1.15)
    # Clip to [0, 255]
    image = tf.clip_by_value(image, 0.0, 255.0)

    return image, label


def compute_class_weights(labels):
    """
    Compute class weights from label distribution to handle imbalance.

    Args:
        labels: np.ndarray of integer labels.

    Returns:
        dict: {class_index: weight} suitable for model.fit(class_weight=...).
    """
    from collections import Counter

    counts = Counter(labels.tolist())
    total = len(labels)
    n_classes = max(counts.keys()) + 1

    weights = {}
    for cls in range(n_classes):
        count = counts.get(cls, 1)
        weights[cls] = total / (n_classes * count)

    logger.info(f"Computed class weights: {weights}")
    return weights
