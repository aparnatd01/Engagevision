"""
cv_engine/verify_setup.py — System & Dependency Verification
══════════════════════════════════════════════════════════════════
Run this script to verify that all dependencies, paths, and system
requirements are met for the EngageVision AI engine.

Usage:
    python -m cv_engine.verify_setup
"""

import os
import sys
import platform

# Fix Windows console encoding for special characters
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')


def _print_header():
    print()
    print("=" * 65)
    print("  EngageVision — AI Engine Setup Verification")
    print("=" * 65)
    print()


def _check(name, passed, detail=""):
    status = "✅ PASS" if passed else "❌ FAIL"
    msg = f"  {status}  {name}"
    if detail:
        msg += f"  —  {detail}"
    print(msg)
    return passed


def verify_python():
    """Check Python version >= 3.9."""
    ver = sys.version_info
    ok = ver >= (3, 9)
    return _check(
        "Python version",
        ok,
        f"{ver.major}.{ver.minor}.{ver.micro}"
        + ("" if ok else " (need >= 3.9)")
    )


def verify_tensorflow():
    """Check TensorFlow is installed and reports version."""
    try:
        os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '3')
        import tensorflow as tf
        ver = tf.__version__
        # Check it's CPU build or has CPU support
        devices = tf.config.list_physical_devices()
        device_names = [d.device_type for d in devices]
        return _check(
            "TensorFlow",
            True,
            f"v{ver}, devices: {device_names}"
        )
    except ImportError:
        return _check("TensorFlow", False, "Not installed. Run: pip install tensorflow-cpu>=2.15.0")
    except Exception as e:
        return _check("TensorFlow", False, str(e))


def verify_opencv():
    """Check OpenCV is installed."""
    try:
        import cv2
        ver = cv2.__version__
        # Verify Haar cascade is accessible
        cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        has_cascade = os.path.isfile(cascade_path)
        return _check(
            "OpenCV",
            True,
            f"v{ver}, Haar cascade: {'found' if has_cascade else 'MISSING'}"
        )
    except ImportError:
        return _check("OpenCV", False, "Not installed. Run: pip install opencv-python>=4.10.0")


def verify_numpy():
    """Check NumPy is installed."""
    try:
        import numpy as np
        return _check("NumPy", True, f"v{np.__version__}")
    except ImportError:
        return _check("NumPy", False, "Not installed. Run: pip install numpy>=1.26.4")


def verify_pillow():
    """Check Pillow is installed."""
    try:
        import PIL
        return _check("Pillow", True, f"v{PIL.__version__}")
    except ImportError:
        return _check("Pillow", False, "Not installed. Run: pip install Pillow>=10.0.0")


def verify_pandas():
    """Check pandas is installed (needed for label parsing)."""
    try:
        import pandas as pd
        return _check("pandas", True, f"v{pd.__version__}")
    except ImportError:
        return _check("pandas", False, "Not installed. Run: pip install pandas")


def verify_ultralytics():
    """Check Ultralytics (YOLOv8) is installed."""
    try:
        import ultralytics
        return _check("Ultralytics (YOLO)", True, f"v{ultralytics.__version__}")
    except ImportError:
        return _check(
            "Ultralytics (YOLO)", False,
            "Not installed. Run: pip install ultralytics>=8.2.0"
        )


def verify_system():
    """Report system information."""
    print("\n  ── System Information ──")
    print(f"     OS:        {platform.system()} {platform.release()}")
    print(f"     Machine:   {platform.machine()}")
    print(f"     Processor: {platform.processor()}")

    # RAM
    try:
        import psutil
        ram_gb = psutil.virtual_memory().total / (1024 ** 3)
        ram_avail = psutil.virtual_memory().available / (1024 ** 3)
        print(f"     RAM:       {ram_gb:.1f} GB total, {ram_avail:.1f} GB available")
    except ImportError:
        print("     RAM:       (install psutil for details)")

    print()


def verify_model_file():
    """Check if the trained engagement model exists."""
    from cv_engine.config import DEFAULT_MODEL_PATH, MODELS_DIR
    exists = os.path.isfile(DEFAULT_MODEL_PATH)
    detail = DEFAULT_MODEL_PATH
    if exists:
        size_mb = os.path.getsize(DEFAULT_MODEL_PATH) / (1024 * 1024)
        detail += f" ({size_mb:.1f} MB)"
    else:
        detail += " (not yet trained)"
    return _check("Engagement model (.h5)", exists, detail)


def verify_model_builds():
    """Verify the model architecture builds without errors."""
    try:
        from cv_engine.model import build_model
        model = build_model()
        param_count = model.count_params()
        return _check(
            "Model architecture",
            True,
            f"MobileNetV2 + engagement head, {param_count:,} params"
        )
    except Exception as e:
        return _check("Model architecture", False, str(e))


def verify_dataset():
    """Check if DAiSEE dataset directory exists."""
    from cv_engine.config import DAISEE_DATASET_DIR, DAISEE_LABELS_DIR
    ds_exists = os.path.isdir(DAISEE_DATASET_DIR)
    lb_exists = os.path.isdir(DAISEE_LABELS_DIR)

    _check(
        "DAiSEE dataset directory",
        ds_exists,
        DAISEE_DATASET_DIR + (" (found)" if ds_exists else " (not found — needed for training only)")
    )
    return _check(
        "DAiSEE labels directory",
        lb_exists,
        DAISEE_LABELS_DIR + (" (found)" if lb_exists else " (not found — needed for training only)")
    )


def verify_cv_engine_structure():
    """Check that the cv_engine package structure is correct."""
    base = os.path.dirname(os.path.abspath(__file__))
    required_files = [
        '__init__.py',
        'config.py',
        'model.py',
        'dataset.py',
        'predictor.py',
        'train.py',
    ]

    all_ok = True
    for fname in required_files:
        fpath = os.path.join(base, fname)
        exists = os.path.isfile(fpath)
        if not exists:
            all_ok = False
            _check(f"cv_engine/{fname}", False, "Missing!")

    models_dir = os.path.join(base, 'models')
    if not os.path.isdir(models_dir):
        all_ok = False
        _check("cv_engine/models/", False, "Directory missing!")

    if all_ok:
        _check("cv_engine package structure", True, f"All {len(required_files)} modules present")

    return all_ok


def main():
    _print_header()

    results = []

    # ── Core dependencies ─────────────────────────────────────────────────────
    print("  ── Core Dependencies ──")
    results.append(verify_python())
    results.append(verify_tensorflow())
    results.append(verify_opencv())
    results.append(verify_numpy())
    results.append(verify_pillow())
    results.append(verify_pandas())
    results.append(verify_ultralytics())

    # ── System info ───────────────────────────────────────────────────────────
    verify_system()

    # ── Package structure ─────────────────────────────────────────────────────
    print("  ── CV Engine Structure ──")
    results.append(verify_cv_engine_structure())

    # ── Model ─────────────────────────────────────────────────────────────────
    print("\n  ── Model ──")
    results.append(verify_model_file())

    # Only try building model if TensorFlow is available
    tf_ok = results[1]  # TensorFlow check was index 1
    if tf_ok:
        results.append(verify_model_builds())

    # ── Dataset ───────────────────────────────────────────────────────────────
    print("\n  ── Dataset (for training) ──")
    verify_dataset()

    # ── Summary ───────────────────────────────────────────────────────────────
    passed = sum(1 for r in results if r)
    total = len(results)
    all_critical_ok = all(results[:5])  # Python, TF, CV2, NumPy, Pillow

    print()
    print("=" * 65)
    print(f"  Results: {passed}/{total} checks passed")

    if all_critical_ok:
        print("  ✅ All critical dependencies are installed!")
        if not results[8] if len(results) > 8 else True:
            print("  ⚠️  Model not trained yet. Run:")
            print("     python -m cv_engine.train --dataset_dir path/to/DAiSEE/DataSet \\")
            print("                               --labels_dir path/to/DAiSEE/Labels")
    else:
        print("  ❌ Missing critical dependencies. Run:")
        print("     pip install -r requirements.txt")

    print("=" * 65)
    print()

    sys.exit(0 if all_critical_ok else 1)


if __name__ == '__main__':
    main()
