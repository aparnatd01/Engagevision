"""
cv_engine/model.py — MobileNetV2 Engagement Classification Model
══════════════════════════════════════════════════════════════════
Builds a MobileNetV2-based CNN fine-tuned for 4-class engagement
classification on the DAiSEE dataset.

Architecture:
    MobileNetV2 (ImageNet, frozen) → GlobalAveragePooling2D
    → Dropout(0.3) → Dense(128, ReLU) → Dropout(0.2) → Dense(4, Softmax)

Input:  224 × 224 × 3  (RGB face crop, normalized to [0, 1])
Output: 4 probabilities [p_very_low, p_low, p_high, p_very_high]
"""

import os
import logging

logger = logging.getLogger(__name__)


def _configure_cpu():
    """
    Configure TensorFlow for CPU performance.
    Thread settings are applied only if TensorFlow
    has not already been initialized.
    """
    os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '2')

    from cv_engine.config import (
        INTER_OP_PARALLELISM,
        INTRA_OP_PARALLELISM
    )

    import tensorflow as tf

    try:
        tf.config.threading.set_inter_op_parallelism_threads(
            INTER_OP_PARALLELISM
        )

        tf.config.threading.set_intra_op_parallelism_threads(
            INTRA_OP_PARALLELISM
        )

        logger.info(
            f"TF CPU threading: inter_op={INTER_OP_PARALLELISM}, "
            f"intra_op={INTRA_OP_PARALLELISM}"
        )

    except RuntimeError:
        logger.info(
            "TensorFlow already initialized; "
            "using existing CPU thread configuration."
        )

def build_model(num_classes=None, learning_rate=None):
    """
    Build the MobileNetV2-based engagement classification model.

    Returns a compiled Keras model ready for training or inference.

    Args:
        num_classes:    Number of output classes (default from config).
        learning_rate:  Optimizer learning rate (default from config).

    Returns:
        tf.keras.Model — compiled model.
    """
    _configure_cpu()

    from cv_engine.config import (
        IMG_SHAPE, NUM_CLASSES, LEARNING_RATE,
        DROPOUT_1, DROPOUT_2, DENSE_UNITS,
    )

    import tensorflow as tf
    import keras
    from keras import layers, Model
    from keras.applications import MobileNetV2

    if num_classes is None:
        num_classes = NUM_CLASSES
    if learning_rate is None:
        learning_rate = LEARNING_RATE

    # ── Base model (frozen backbone) ──────────────────────────────────────────
    base_model = MobileNetV2(
        weights='imagenet',
        include_top=False,
        input_shape=IMG_SHAPE,
    )
    base_model.trainable = False

    logger.info(
        f"MobileNetV2 base loaded: {len(base_model.layers)} layers (frozen), "
        f"input_shape={IMG_SHAPE}"
    )

    # ── Classification head ───────────────────────────────────────────────────
    inputs = keras.Input(shape=IMG_SHAPE, name='face_input')

    # MobileNetV2 preprocessing (scale pixels to [-1, 1])
    x = keras.applications.mobilenet_v2.preprocess_input(inputs)

    # Feature extraction
    x = base_model(x, training=False)

    # Classification layers
    x = layers.GlobalAveragePooling2D(name='global_avg_pool')(x)
    x = layers.Dropout(DROPOUT_1, name='dropout_1')(x)
    x = layers.Dense(DENSE_UNITS, activation='relu', name='dense_hidden')(x)
    x = layers.Dropout(DROPOUT_2, name='dropout_2')(x)
    outputs = layers.Dense(num_classes, activation='softmax', name='engagement_output')(x)

    model = Model(inputs=inputs, outputs=outputs, name='EngageVision_MobileNetV2')

    # ── Compile ───────────────────────────────────────────────────────────────
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=learning_rate),
        loss='sparse_categorical_crossentropy',
        metrics=['accuracy'],
    )

    logger.info(
        f"Model compiled: {model.count_params():,} total params, "
        f"lr={learning_rate}"
    )

    return model


def load_trained_model(model_path=None):
    """
    Load trained engagement weights into the exact model architecture.

    This avoids H5 architecture deserialization problems such as
    'Unknown layer: TrueDivide'.

    Args:
        model_path: Path to the trained .h5 model file.

    Returns:
        tf.keras.Model — trained model ready for inference.
    """

    _configure_cpu()

    from cv_engine.config import DEFAULT_MODEL_PATH

    if model_path is None:
        model_path = DEFAULT_MODEL_PATH

    if not os.path.isfile(model_path):
        raise FileNotFoundError(
            f"Engagement model not found at: {model_path}\n"
            f"Please train the model first."
        )

    logger.info(
        f"Loading trained weights from: {model_path}"
    )

    # Rebuild the exact architecture used during training
    model = build_model()

    # Load trained weights without deserializing the old H5 architecture
    model.load_weights(model_path)

    logger.info(
        f"Trained engagement weights loaded successfully from: "
        f"{model_path}"
    )

    return model

def get_model_summary(model=None):
    """
    Return a string summary of the model architecture.

    Args:
        model: A Keras model. If None, builds a fresh model.

    Returns:
        str — model summary text.
    """
    if model is None:
        model = build_model()

    summary_lines = []
    model.summary(print_fn=lambda line: summary_lines.append(line))
    return '\n'.join(summary_lines)
