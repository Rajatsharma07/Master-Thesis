from tensorflow.keras import layers
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import models
import config as cn
from src.loss import coral_loss
import datetime
import os
from tensorflow.keras.callbacks import CSVLogger


def merged_network(
    input_shape,
    source_model,
    target_model,
    additional_loss=coral_loss,
    num_classes=10,
    percent=0.25,
    feature_extractor_shape=256,
):
    """
    This method creates merged network having concatenation of Source & Target Models.

    """
    in_1 = layers.Input(shape=input_shape)
    source_model = source_model(in_1)
    source_model = models.Model(in_1, source_model, name="Source_Model")
    source_model.trainable = True
    source_model.summary()

    in_2 = layers.Input(shape=input_shape)
    target_model = target_model(in_2, training=True)
    target_model = models.Model(in_2, target_model, name="Target_Model")
    target_model.trainable = True
    target_model.summary()

    concat = layers.Concatenate()([source_model.output, target_model.output])
    concat = layers.Conv2D(
        feature_extractor_shape,
        kernel_size=1,
        kernel_initializer=cn.initializer,
        name="DownsampleConvolution",
    )(concat)

    classifier_input = layers.Input(
        (
            target_model.output.shape[1],
            target_model.output.shape[2],
            target_model.output.shape[3],
        )
    )
    x = layers.GlobalAveragePooling2D()(classifier_input)
    x = layers.BatchNormalization(name="bn_top1")(x)
    x = layers.Activation("relu")(x)
    x = layers.Dropout(0.3)(x)
    x = layers.Dense(64, kernel_initializer=cn.initializer)(x)
    x = layers.BatchNormalization(name="bn_top2")(x)
    x = layers.Activation("relu")(x)
    x = layers.Dropout(0.3)(x)
    prediction = layers.Dense(
        num_classes, kernel_initializer=cn.initializer, activation="softmax"
    )(x)

    classifier_model = models.Model(classifier_input, prediction, name="Classifier")
    classifier_model.summary()

    final_output = classifier_model(concat)

    merged_model = models.Model([source_model.input, target_model.input], final_output)

    source_scores = tf.reshape(source_model.output, [-1, feature_extractor_shape])
    target_scores = tf.reshape(target_model.output, [-1, feature_extractor_shape])

    coral_loss = additional_loss(
        model=merged_model,
        source_output=source_scores,
        target_output=target_scores,
        percent_lambda=percent,
    )
    merged_model.add_metric(coral_loss, name="coral_loss", aggregation="mean")

    return merged_model


class Custom_Eval(tf.keras.callbacks.Callback):
    def __init__(self, val_data):
        super().__init__()
        self.validation_data = val_data
        self.loss_fn = keras.losses.SparseCategoricalCrossentropy(from_logits=True)
        self.acc_metric = keras.metrics.SparseCategoricalAccuracy(
            name="custom_accuracy_metric"
        )

    def on_epoch_end(self, epoch, logs):
        # create the new nodes for each layer in the path
        x = self.model.layers[3](self.validation_data[0], training=False)
        y_pred = self.model.layers[6](x, training=False)

        # ip1 = keras.Input(shape=(32,32,3))
        # # ip1 = self.model.layers[3].input_shape[1:]
        # op1 = self.model.layers[3](ip1)
        # # create the model
        # op_mdl1 = Model(ip1, op1)
        # o1 = op_mdl1(self.validation_data[0])
        # print(o1[0])

        # create the new nodes for each layer in the path
        # ip2 = keras.Input(shape=(1,1,256))
        # op2 = self.model.layers[6](ip2)
        # op_mdl2 = Model(ip2, op2)

        # loss, acc = mdl.evaluate(self.validation_data[0], self.validation_data[1], verbose=0)
        loss = self.loss_fn(self.validation_data[1], y_pred)
        logs["custom_accuracy"] = self.acc_metric.result().numpy()
        logs["custom_loss"] = loss.numpy()
        tf.summary.scalar("Custom Evaluation loss", data=loss.numpy(), step=epoch)
        tf.summary.scalar(
            "Custom Evaluation Accuracy",
            data=self.acc_metric.result().numpy(),
            step=epoch,
        )
        print("Custom_accuracy: %.4f" % (float(self.acc_metric.result()),))
        print(f"Custom_loss: {loss}, Epoch: {epoch}")
        self.acc_metric.reset_states()


def callbacks_fn(combination, source_model, sample_seed):
    my_dir = combination + "_" + source_model + "_" + sample_seed
    if os.path.exists(cn.MODEL_PATH):
        checkpoint_path = os.path.join(cn.MODEL_PATH, my_dir)
        os.makedirs(checkpoint_path)
        checkpoint_path = os.path.join(
            checkpoint_path,
            "weights.{epoch:02d}-{val_loss:.2f}.hdf5",
        )
    print(f"\nModel Checkpoint path: {checkpoint_path}\n")

    csv_logger = os.path.join(cn.LOGS_DIR, my_dir)
    os.makedirs(csv_logger)
    print(f"\nModel CSV logs path: {csv_logger}/logs.csv\n")
    csv_logger = CSVLogger(
        os.path.join(csv_logger, "logs.csv"),
        append=True,
        separator=";",
    )

    tb_logdir = os.path.join(cn.TENSORBOARD_DIR, my_dir)
    os.makedirs(tb_logdir)
    tb_logdir = os.path.join(
        tb_logdir, datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    )

    file_writer = tf.summary.create_file_writer(tb_logdir + "/custom_evaluation")
    file_writer.set_as_default()
    tensorboard_callback = tf.keras.callbacks.TensorBoard(tb_logdir, histogram_freq=1)
    print(f"\nTensorboard logs path: {tb_logdir}\n")

    cp_callback = tf.keras.callbacks.ModelCheckpoint(
        filepath=checkpoint_path,
        save_weights_only=True,
        save_best_only=True,
        verbose=1,
        monitor="val_accuracy",
    )

    reduce_lr_callback = tf.keras.callbacks.ReduceLROnPlateau(
        monitor="val_loss", factor=0.2, patience=1, min_lr=0.000001
    )
    return csv_logger, cp_callback, tensorboard_callback, reduce_lr_callback, tb_logdir