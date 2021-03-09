import tensorflow as tf
from tensorflow import keras
from tensorflow.keras.utils import plot_model
import os
import tensorflow_model_optimization as tfmot
from pathlib import Path
import src.config as cn
from src.models import get_model
from src.preprocessing import fetch_data
import src.utils as utils


def train_test(params):

    my_dir = (
        str(cn.DATASET_COMBINATION[params["combination"]])
        + "_"
        + str(params["architecture"])
        + "_"
        + str(params["loss_function"])
        + "_"
        + str(params["lambda_loss"])
    )

    if not params["technique"]:
        my_dir = my_dir + "_Original"

    if params["prune"]:
        tf.compat.v1.logging.info("Pruning is activated")
        my_dir = my_dir + "_" + str(params["prune_val"])

    assert os.path.exists(cn.LOGS_DIR), "LOGS_DIR doesn't exist"
    experiment_logs_path = os.path.join(cn.LOGS_DIR, my_dir)
    Path(experiment_logs_path).mkdir(parents=True, exist_ok=True)
    utils.define_logger(os.path.join(experiment_logs_path, "experiments.log"))
    tf.compat.v1.logging.info("\n")
    tf.compat.v1.logging.info("Parameters: " + str(params))
    assert (
        params["mode"].lower() == "train_test"
    ), "change training mode to 'train_test'"

    tf.compat.v1.logging.info(
        "Fetched the architecture function: " + params["architecture"]
    )

    if params["use_multiGPU"]:
        # Create a MirroredStrategy.
        strategy = tf.distribute.MirroredStrategy()
        print("Number of devices: {}".format(strategy.num_replicas_in_sync))

        # Open a strategy scope.
        with strategy.scope():
            model = None
            tf.compat.v1.logging.info("Using Mutliple GPUs for training ...")
            tf.compat.v1.logging.info("Building the model ...")

            model = get_model(
                input_shape=params["input_shape"],
                num_classes=params["output_classes"],
                lambda_loss=params["lambda_loss"],
                additional_loss=params["loss_function"],
                prune=params["prune"],
                prune_val=params["prune_val"],
                technique=params["technique"],
            )

            # print(model.summary())
            """ Model Compilation """
            tf.compat.v1.logging.info("Compiling the model ...")
            model.compile(
                optimizer=keras.optimizers.Adam(learning_rate=params["learning_rate"]),
                loss=tf.keras.losses.SparseCategoricalCrossentropy(from_logits=True),
                metrics=["accuracy"],
            )
    else:
        # Create model
        tf.compat.v1.logging.info("Building the model ...")

        model = None

        model = get_model(
            input_shape=params["input_shape"],
            num_classes=params["output_classes"],
            lambda_loss=params["lambda_loss"],
            additional_loss=params["loss_function"],
            prune=params["prune"],
            prune_val=params["prune_val"],
            technique=params["technique"],
        )

        # print(model.summary())
        """ Model Compilation """
        tf.compat.v1.logging.info("Compiling the model ...")
        model.compile(
            optimizer=keras.optimizers.Adam(learning_rate=params["learning_rate"]),
            loss=tf.keras.losses.SparseCategoricalCrossentropy(from_logits=True),
            metrics=["accuracy"],
        )

    """ Create callbacks """
    tf.compat.v1.logging.info("Creating the callbacks ...")
    callbacks, log_dir = utils.callbacks_fn(params, my_dir)

    tf.compat.v1.logging.info("Calling data preprocessing pipeline...")
    ds_train, ds_test = fetch_data(params)

    """ Model Training """
    tf.compat.v1.logging.info("Training Started....")

    # mnist = tf.keras.datasets.mnist
    # (mnistx_train, mnisty_train), (
    #     mnistx_test,
    #     mnisty_test,
    # ) = mnist.load_data()

    # mnistx_train = tf.image.resize(
    #     tf.reshape(mnistx_train[:4000], shape=[-1, 28, 28, 1]),
    #     [71, 71],
    #     method="nearest",
    #     preserve_aspect_ratio=False,
    #     antialias=True,
    #     name=None,
    # )
    # mnistx_train = tf.image.grayscale_to_rgb(mnistx_train)

    # mnistx_train = tf.cast(mnistx_train, tf.float32)
    # mnistx_train = tf.keras.applications.xception.preprocess_input(mnistx_train)

    hist = None
    hist = model.fit(
        ds_train,
        validation_data=ds_test,
        epochs=params["epochs"],
        verbose=1,
        callbacks=callbacks,
    )
    tf.compat.v1.logging.info("Training finished....")

    """ Plotting """
    tf.compat.v1.logging.info("Creating accuracy & loss plots...")
    utils.loss_accuracy_plots(
        hist=hist,
        log_dir=log_dir,
        params=params,
    )

    """ Evaluate on Target Dataset"""
    results = model.evaluate(ds_test)
    tf.compat.v1.logging.info(
        f"Test Set evaluation results for run {Path(log_dir).name} : Accuracy: {results[1]}, Loss: {results[0]}"
    )

    """ Model Saving """
    if params["save_model"]:
        tf.compat.v1.logging.info("Saving the model...")
        model_path = os.path.join(
            cn.MODEL_PATH, (Path(log_dir).parent).name, Path(log_dir).name
        )
        Path(model_path).mkdir(parents=True, exist_ok=True)
        model.save(os.path.join(model_path, "model"))
        tf.compat.v1.logging.info(f"Model successfully saved at: {model_path}")

    """ Pruned Model Saving """
    if params["prune"]:
        model_for_export = tfmot.sparsity.keras.strip_pruning(model)
        tf.compat.v1.logging.info(f"Pruned Model summary: {model_for_export.summary()}")

        tf.compat.v1.logging.info("Saving Pruned Model...")
        model_path = os.path.join(
            cn.MODEL_PATH, (Path(log_dir).parent).name, Path(log_dir).name
        )
        Path(model_path).mkdir(parents=True, exist_ok=True)
        model_for_export.save(os.path.join(model_path, "pruned_model"))
        tf.compat.v1.logging.info(f"Pruned Model successfully saved at: {model_path}")

        tf.compat.v1.logging.info(
            "Size of gzipped pruned model without stripping: %.2f bytes"
            % (utils.get_gzipped_model_size(model))
        )

        tf.compat.v1.logging.info(
            "Size of gzipped pruned model with stripping: %.2f bytes"
            % (utils.get_gzipped_model_size(model_for_export))
        )

    return model, hist, results
