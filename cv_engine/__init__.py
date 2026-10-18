"""
cv_engine — DAiSEE + MobileNetV2 Engagement Classification Engine
══════════════════════════════════════════════════════════════════
CPU-optimized engagement predictor trained on the DAiSEE dataset.

Usage (inference):
    from cv_engine.predictor import EngagementPredictor
    predictor = EngagementPredictor()
    result = predictor.predict(face_crop_bgr)
    # → {'engagement_pct': 71.5, 'level': 'High', 'probabilities': [...]}

Usage (training):
    python -m cv_engine.train --dataset_dir path/to/DAiSEE
"""

from cv_engine.predictor import EngagementPredictor

__all__ = ['EngagementPredictor']
