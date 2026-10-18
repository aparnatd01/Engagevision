"""
cv_engine/config.py — Central Configuration
═══════════════════════════════════════════════════════════════════
All model, dataset, and inference constants in one place.
Optimized for CPU execution on Intel i7-1355U / 16 GB RAM.
"""

import os

# ═══════════════════════════════════════════════════════════════════════════════
# MODEL ARCHITECTURE
# ═══════════════════════════════════════════════════════════════════════════════

# MobileNetV2 expects 224×224 RGB input
IMG_HEIGHT = 224
IMG_WIDTH  = 224
IMG_SIZE   = (IMG_HEIGHT, IMG_WIDTH)
IMG_SHAPE  = (IMG_HEIGHT, IMG_WIDTH, 3)

# ═══════════════════════════════════════════════════════════════════════════════
# DAiSEE ENGAGEMENT CLASSES
# ═══════════════════════════════════════════════════════════════════════════════

# DAiSEE labels the "Engagement" column with 4 levels (0-3)
NUM_CLASSES = 4
CLASS_NAMES = ['Very Low', 'Low', 'High', 'Very High']

# Mapping: DAiSEE numeric → index
# 0 = Very Low, 1 = Low, 2 = High, 3 = Very High
DAISEE_LABEL_MAP = {0: 'Very Low', 1: 'Low', 2: 'High', 3: 'Very High'}

# ═══════════════════════════════════════════════════════════════════════════════
# ENGAGEMENT SCORING — DAiSEE → EngageVision High/Medium/Low
# ═══════════════════════════════════════════════════════════════════════════════

# Weights for computing a continuous 0-100% engagement score from softmax probs.
# Softmax output order: [p_very_low, p_low, p_high, p_very_high]
# Formula: engagement_pct = sum(prob_i * weight_i) * 100
ENGAGEMENT_WEIGHTS = [0.0, 0.33, 0.66, 1.0]

# Thresholds for mapping percentage → EngageVision level
HIGH_THRESHOLD   = 66.0   # ≥ 66% → High   (Green)
MEDIUM_THRESHOLD = 50.0   # ≥ 33% → Medium  (Yellow/Amber)
# < 33% → Low (Red)

# ═══════════════════════════════════════════════════════════════════════════════
# TRAINING HYPERPARAMETERS (CPU-optimized)
# ═══════════════════════════════════════════════════════════════════════════════

BATCH_SIZE    = 16       # CPU-safe for 16 GB RAM
EPOCHS        = 30       # Sufficient for transfer learning (with early stopping)
LEARNING_RATE = 1e-4     # Conservative for fine-tuning frozen backbone
DROPOUT_1     = 0.3      # After GlobalAveragePooling
DROPOUT_2     = 0.2      # After Dense(128)
DENSE_UNITS   = 128      # Hidden layer size
PATIENCE      = 7        # Early stopping patience (epochs)

# Data augmentation (training only)
AUGMENTATION = {
    'rotation_range':      15,
    'width_shift_range':   0.1,
    'height_shift_range':  0.1,
    'horizontal_flip':     True,
    'brightness_range':    (0.8, 1.2),
    'zoom_range':          0.1,
    'fill_mode':           'nearest',
}

# Class weights to handle DAiSEE imbalance
# DAiSEE is heavily skewed toward "High" engagement;
# these approximate weights compensate (refined during training)
DEFAULT_CLASS_WEIGHTS = {0: 2.5, 1: 1.8, 2: 0.6, 3: 1.0}

# ═══════════════════════════════════════════════════════════════════════════════
# DATASET PATHS (DAiSEE structure)
# ═══════════════════════════════════════════════════════════════════════════════

# Expected DAiSEE directory layout:
#   DAiSEE/
#   ├── DataSet/
#   │   ├── Train/        (subject folders → video folders → .jpg frames)
#   │   ├── Test/
#   │   └── Validation/
#   └── Labels/
#       ├── TrainLabels.csv
#       ├── TestLabels.csv
#       └── ValidationLabels.csv

DAISEE_DATASET_DIR   = os.environ.get('DAISEE_DATASET_DIR', 'DAiSEE/DataSet')
DAISEE_LABELS_DIR    = os.environ.get('DAISEE_LABELS_DIR',  'DAiSEE/Labels')
TRAIN_LABELS_FILE    = 'TrainLabels.csv'
TEST_LABELS_FILE     = 'TestLabels.csv'
VAL_LABELS_FILE      = 'ValidationLabels.csv'

# Max frames to extract per 10-second video clip during preprocessing
MAX_FRAMES_PER_CLIP = 3

# ═══════════════════════════════════════════════════════════════════════════════
# MODEL FILE PATHS
# ═══════════════════════════════════════════════════════════════════════════════

# Directory for storing trained model weights
MODELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'models')

# Default model file path (can be overridden via .env ENGAGEMENT_MODEL_PATH)
DEFAULT_MODEL_PATH = os.environ.get(
    'ENGAGEMENT_MODEL_PATH',
    os.path.join(MODELS_DIR, 'engagement_model.h5')
)

# ═══════════════════════════════════════════════════════════════════════════════
# CPU OPTIMIZATION
# ═══════════════════════════════════════════════════════════════════════════════

# Intel i7-1355U has 10 cores (2P + 8E).
# Set TF threading for optimal CPU utilization.
INTER_OP_PARALLELISM = 2    # Number of independent ops to run in parallel
INTRA_OP_PARALLELISM = 8    # Threads within a single op (e.g., matrix multiply)
