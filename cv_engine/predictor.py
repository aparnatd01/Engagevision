"""
cv_engine/predictor.py — Engagement Prediction (Inference)
══════════════════════════════════════════════════════════════════
The main inference module. Loads the trained MobileNetV2 model once
and provides a simple API for predicting engagement from face crops.

Usage:
    from cv_engine.predictor import EngagementPredictor

    predictor = EngagementPredictor()  # loads model once
    result = predictor.predict(face_crop_bgr)
    # result = {
    #     'engagement_pct': 71.5,
    #     'level': 'High',
    #     'probabilities': [0.02, 0.08, 0.25, 0.65],
    #     'class_label': 'Very High',
    #     'class_index': 3,
    # }
"""

import os
import logging

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class EngagementPredictor:
    """
    Loads the trained engagement model and provides prediction on
    individual face crops.

    Thread-safe for use in Flask request handlers (model is read-only
    after loading).
    """

    def __init__(self, model_path=None):
        """
        Initialize the predictor by loading the trained model.

        Args:
            model_path: Path to the .h5 model file. If None, uses the
                        default from config / ENGAGEMENT_MODEL_PATH env var.

        Raises:
            FileNotFoundError: If the model file does not exist.
        """
        from cv_engine.config import (
            DEFAULT_MODEL_PATH, IMG_SIZE, NUM_CLASSES,
            CLASS_NAMES, ENGAGEMENT_WEIGHTS,
            HIGH_THRESHOLD, MEDIUM_THRESHOLD,
        )

        self._img_size         = IMG_SIZE
        self._num_classes      = NUM_CLASSES
        self._class_names      = CLASS_NAMES
        self._weights          = ENGAGEMENT_WEIGHTS
        self._high_threshold   = HIGH_THRESHOLD
        self._medium_threshold = MEDIUM_THRESHOLD

        if model_path is None:
            model_path = DEFAULT_MODEL_PATH

        self._model_path = model_path
        self._model = None

        # Try to load the model
        if os.path.isfile(model_path):
            self._load_model(model_path)
        else:
            logger.warning(
                f"Engagement model not found at: {model_path}. "
                f"Predictor will run in FALLBACK mode (heuristic scores). "
                f"Train the model by running: python -m cv_engine.train"
            )

    def _load_model(self, model_path):
        """Load the Keras model from disk."""
        from cv_engine.model import load_trained_model
        try:
            self._model = load_trained_model(model_path)
            logger.info(f"Engagement model loaded successfully from: {model_path}")
        except Exception as e:
            logger.error(f"Failed to load engagement model: {e}")
            self._model = None

    @property
    def is_model_loaded(self):
        """Whether the trained model is loaded and ready for inference."""
        return self._model is not None

    def predict(self, face_crop_bgr):
        """
        Predict engagement level for a single face crop.

        Args:
            face_crop_bgr: BGR numpy array of any size (will be resized to
                           224×224). This is the raw face crop from OpenCV.

        Returns:
            dict with keys:
                engagement_pct  (float): 0-100 engagement percentage
                level           (str):   'High', 'Medium', or 'Low'
                probabilities   (list):  [p_very_low, p_low, p_high, p_very_high]
                class_label     (str):   Most likely DAiSEE class name
                class_index     (int):   Most likely DAiSEE class index (0-3)
        """
        if face_crop_bgr is None or face_crop_bgr.size == 0:
            return self._default_result()

        if self._model is not None:
            return self._predict_with_model(face_crop_bgr)
        else:
            return self._predict_fallback(face_crop_bgr)

    def predict_batch(self, face_crops_bgr):
        """
        Predict engagement for multiple face crops at once.

        More efficient than calling predict() in a loop because it
        runs a single model inference batch.

        Args:
            face_crops_bgr: List of BGR numpy arrays (any sizes).

        Returns:
            list[dict]: List of prediction results (same format as predict).
        """
        if not face_crops_bgr:
            return []

        if self._model is None:
            return [self._predict_fallback(crop) for crop in face_crops_bgr]

        # Preprocess all crops
        preprocessed = []
        valid_indices = []
        for i, crop in enumerate(face_crops_bgr):
            if crop is not None and crop.size > 0:
                processed = self._preprocess(crop)
                preprocessed.append(processed)
                valid_indices.append(i)

        if not preprocessed:
            return [self._default_result() for _ in face_crops_bgr]

        # Batch inference
        batch = np.array(preprocessed, dtype=np.float32)
        probabilities = self._model.predict(batch, verbose=0)

        # Build results
        results = [self._default_result() for _ in face_crops_bgr]
        for batch_idx, original_idx in enumerate(valid_indices):
            probs = probabilities[batch_idx].tolist()
            results[original_idx] = self._build_result(probs)

        return results

    def _predict_with_model(self, face_crop_bgr):
        """Run model inference on a single face crop."""
        processed = self._preprocess(face_crop_bgr)
        input_batch = np.expand_dims(processed, axis=0)  # (1, 224, 224, 3)

        probabilities = self._model.predict(input_batch, verbose=0)
        probs = probabilities[0].tolist()

        return self._build_result(probs)

    def _preprocess(self, face_crop_bgr):
        """
        Preprocess a face crop for model input.

        - Resize to 224×224
        - Convert BGR → RGB
        - Cast to float32 (keep [0, 255] range — model's built-in
          preprocess_input handles normalization to [-1, 1])
        """
        resized = cv2.resize(
            face_crop_bgr, self._img_size, interpolation=cv2.INTER_AREA
        )
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        return rgb.astype(np.float32)  # [0, 255] range

    def _build_result(self, probabilities):
        """
        Build the result dict from softmax probabilities.

        Uses weighted probability formula:
            engagement_pct = sum(prob_i × weight_i) × 100

        Args:
            probabilities: List of 4 floats [p_very_low, p_low, p_high, p_very_high].

        Returns:
            dict with engagement_pct, level, probabilities, class_label, class_index.
        """
        # Weighted engagement percentage
        engagement_pct = sum(
            p * w for p, w in zip(probabilities, self._weights)
        ) * 100.0
        engagement_pct = round(min(100.0, max(0.0, engagement_pct)), 1)

        # Map to level
        if engagement_pct >= self._high_threshold:
            level = 'High'
        elif engagement_pct >= self._medium_threshold:
            level = 'Medium'
        else:
            level = 'Low'

        # Most likely class
        class_index = int(np.argmax(probabilities))
        class_label = self._class_names[class_index]

        return {
            'engagement_pct': engagement_pct,
            'level':          level,
            'probabilities':  [round(p, 4) for p in probabilities],
            'class_label':    class_label,
            'class_index':    class_index,
            'is_fallback':    False,
        }

    def _predict_fallback(self, face_crop_bgr):
        """
        Fallback prediction when the trained model is not available.

        Uses a simple brightness/contrast heuristic as a placeholder.
        This ensures the pipeline works end-to-end even before training.
        """
        resized = cv2.resize(face_crop_bgr, self._img_size)
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)

        # Simple heuristics based on image properties
        brightness = float(np.mean(gray))
        contrast = float(np.std(gray))

        # Normalize to a 0-100 range (rough engagement proxy)
        bright_score = min(100.0, max(0.0, brightness / 2.0))
        contrast_score = min(100.0, max(0.0, contrast * 1.5))
        engagement_pct = round((bright_score * 0.4 + contrast_score * 0.6), 1)

        # Add controlled randomness for variation
        noise = np.random.normal(0, 5)
        engagement_pct = round(float(np.clip(engagement_pct + noise, 5.0, 95.0)), 1)

        if engagement_pct >= self._high_threshold:
            level = 'High'
        elif engagement_pct >= self._medium_threshold:
            level = 'Medium'
        else:
            level = 'Low'

        return {
            'engagement_pct': engagement_pct,
            'level':          level,
            'probabilities':  [0.25, 0.25, 0.25, 0.25],  # uniform (no model)
            'class_label':    'Unknown (fallback)',
            'class_index':    -1,
            'is_fallback':    True,   # ← heuristic score, NOT a real model prediction
        }

    @staticmethod
    def _default_result():
        """Return a default result for invalid/empty inputs."""
        return {
            'engagement_pct': 0.0,
            'level':          'Low',
            'probabilities':  [1.0, 0.0, 0.0, 0.0],
            'class_label':    'Very Low',
            'class_index':    0,
        }
