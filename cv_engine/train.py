"""
cv_engine/train.py — Training Script for DAiSEE Engagement Model
══════════════════════════════════════════════════════════════════
Standalone script to fine-tune MobileNetV2 on the DAiSEE dataset
for 4-class engagement classification.

Optimized for CPU execution (Intel i7-1355U, 16 GB RAM, no CUDA).

Usage:
    python -m cv_engine.train --dataset_dir DAiSEE/DataSet --labels_dir DAiSEE/Labels

    # Or with all defaults from config:
    python -m cv_engine.train
"""

import os
import sys
import time
import argparse
import logging

# Configure logging before any other imports
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%H:%M:%S',
)
logger = logging.getLogger('cv_engine.train')


def main():
    parser = argparse.ArgumentParser(
        description='Train MobileNetV2 engagement model on DAiSEE dataset'
    )
    parser.add_argument(
        '--dataset_dir', type=str, default=None,
        help='Path to DAiSEE DataSet directory (contains Train/Test/Validation)'
    )
    parser.add_argument(
        '--labels_dir', type=str, default=None,
        help='Path to DAiSEE Labels directory (contains *.csv files)'
    )
    parser.add_argument(
        '--output', type=str, default=None,
        help='Path to save the trained model (.h5)'
    )
    parser.add_argument(
        '--epochs', type=int, default=None,
        help='Number of training epochs'
    )
    parser.add_argument(
        '--batch_size', type=int, default=None,
        help='Training batch size'
    )

    args = parser.parse_args()

    # ── Import config and modules ─────────────────────────────────────────────
    from cv_engine.config import (
        DAISEE_DATASET_DIR, DAISEE_LABELS_DIR,
        TRAIN_LABELS_FILE, TEST_LABELS_FILE, VAL_LABELS_FILE,
        DEFAULT_MODEL_PATH, MODELS_DIR,
        EPOCHS, BATCH_SIZE, PATIENCE,
    )
    from cv_engine.model import build_model
    from cv_engine.dataset import (
        prepare_dataset, create_tf_dataset, compute_class_weights,
    )

    # Resolve paths
    dataset_dir = args.dataset_dir or DAISEE_DATASET_DIR
    labels_dir  = args.labels_dir or DAISEE_LABELS_DIR
    output_path = args.output or DEFAULT_MODEL_PATH
    epochs      = args.epochs or EPOCHS
    batch_size  = args.batch_size or BATCH_SIZE

    # ── Verify paths ──────────────────────────────────────────────────────────
    train_dir = os.path.join(dataset_dir, 'Train')
    test_dir  = os.path.join(dataset_dir, 'Test')
    val_dir   = os.path.join(dataset_dir, 'Validation')

    train_labels = os.path.join(labels_dir, TRAIN_LABELS_FILE)
    test_labels  = os.path.join(labels_dir, TEST_LABELS_FILE)
    val_labels   = os.path.join(labels_dir, VAL_LABELS_FILE)

    for path, name in [
        (train_dir, 'Training dataset'),
        (train_labels, 'Training labels'),
    ]:
        if not os.path.exists(path):
            logger.error(f"{name} not found: {path}")
            logger.error(
                "Please download the DAiSEE dataset from:\n"
                "  Official: https://people.iith.ac.in/vineethnb/resources/daisee/index.html\n"
                "  Kaggle:   https://www.kaggle.com/datasets/smeeshanthini/daisee"
            )
            sys.exit(1)

    # ── Print configuration ───────────────────────────────────────────────────
    print("=" * 65)
    print("  EngageVision — DAiSEE Engagement Model Training")
    print("=" * 65)
    print(f"  Dataset:    {dataset_dir}")
    print(f"  Labels:     {labels_dir}")
    print(f"  Output:     {output_path}")
    print(f"  Epochs:     {epochs}")
    print(f"  Batch size: {batch_size}")
    print(f"  Device:     CPU (optimized for Intel i7-1355U)")
    print("=" * 65)
    print()

    start_time = time.time()

    # ── Step 1: Prepare datasets ──────────────────────────────────────────────
    logger.info("Step 1/5: Preparing training dataset...")
    train_images, train_labels_arr = prepare_dataset(train_dir, train_labels)
    logger.info(f"  Training samples: {len(train_images)}")

    if len(train_images) == 0:
        logger.error("No training samples found! Check dataset structure.")
        sys.exit(1)

    logger.info("Step 2/5: Preparing validation dataset...")
    if os.path.isdir(val_dir) and os.path.isfile(val_labels):
        val_images, val_labels_arr = prepare_dataset(val_dir, val_labels)
        logger.info(f"  Validation samples: {len(val_images)}")
    else:
        # Split training data if no validation set
        split = int(len(train_images) * 0.85)
        val_images     = train_images[split:]
        val_labels_arr = train_labels_arr[split:]
        train_images   = train_images[:split]
        train_labels_arr = train_labels_arr[:split]
        logger.info(f"  No separate validation set; split from training: "
                     f"{len(train_images)} train, {len(val_images)} val")

    # ── Step 2: Compute class weights ─────────────────────────────────────────
    logger.info("Step 3/5: Computing class weights...")
    class_weights = compute_class_weights(train_labels_arr)

    # ── Step 3: Create TF datasets ────────────────────────────────────────────
    logger.info("Step 4/5: Building TF data pipelines...")
    train_ds = create_tf_dataset(
        train_images, train_labels_arr,
        batch_size=batch_size, augment=True, shuffle=True,
    )
    val_ds = create_tf_dataset(
        val_images, val_labels_arr,
        batch_size=batch_size, augment=False, shuffle=False,
    )

    # ── Step 4: Build and train model ─────────────────────────────────────────
    logger.info("Step 5/5: Building and training model...")
    import tensorflow as tf

    model = build_model()
    model.summary()

    # Callbacks
    os.makedirs(MODELS_DIR, exist_ok=True)

    callbacks = [
        tf.keras.callbacks.EarlyStopping(
            monitor='val_accuracy',
            patience=PATIENCE,
            restore_best_weights=True,
            verbose=1,
        ),
        tf.keras.callbacks.ModelCheckpoint(
            filepath=output_path,
            monitor='val_accuracy',
            save_best_only=True,
            verbose=1,
        ),
        tf.keras.callbacks.ReduceLROnPlateau(
            monitor='val_loss',
            factor=0.5,
            patience=3,
            min_lr=1e-6,
            verbose=1,
        ),
    ]

    # Train
    history = model.fit(
        train_ds,
        validation_data=val_ds,
        epochs=epochs,
        class_weight=class_weights,
        callbacks=callbacks,
        verbose=1,
    )

    # ── Step 5: Evaluate ──────────────────────────────────────────────────────
    elapsed = time.time() - start_time

    # Final evaluation on test set if available
    if os.path.isdir(test_dir) and os.path.isfile(test_labels):
        logger.info("Evaluating on test set...")
        test_images, test_labels_arr = prepare_dataset(test_dir, test_labels)
        if len(test_images) > 0:
            test_ds = create_tf_dataset(
                test_images, test_labels_arr,
                batch_size=batch_size, augment=False, shuffle=False,
            )
            test_loss, test_acc = model.evaluate(test_ds, verbose=0)
            logger.info(f"Test accuracy: {test_acc:.4f}, Test loss: {test_loss:.4f}")

    # Print summary
    best_val_acc = max(history.history.get('val_accuracy', [0]))
    best_train_acc = max(history.history.get('accuracy', [0]))

    print()
    print("=" * 65)
    print("  Training Complete!")
    print("=" * 65)
    print(f"  Duration:           {elapsed/60:.1f} minutes")
    print(f"  Best train accuracy: {best_train_acc:.4f}")
    print(f"  Best val accuracy:   {best_val_acc:.4f}")
    print(f"  Model saved to:     {output_path}")
    print(f"  Model size:         {os.path.getsize(output_path)/1024/1024:.1f} MB"
          if os.path.isfile(output_path) else "")
    print("=" * 65)
    print()
    print("  Next steps:")
    print("    1. Start the Flask app:  python run.py")
    print("    2. The monitoring analyzer will use this model automatically")
    print()


if __name__ == '__main__':
    main()
