import os
import tensorflow as tf
from tensorflow.keras import layers
from tensorflow import keras
import src.config as cn
import math
from src.utils import extract_mnist_m, create_paths, shuffle_dataset

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"
# Create a generator
rng = tf.random.Generator.from_seed(123, alg="philox")

data_augmentation = keras.Sequential(
    [
        layers.experimental.preprocessing.RandomContrast(0.1, 0.3),
        layers.experimental.preprocessing.RandomZoom(0.1),
        layers.experimental.preprocessing.RandomFlip("horizontal_and_vertical"),
        layers.experimental.preprocessing.RandomRotation(
            0.2, interpolation="nearest", fill_mode="nearest"
        ),
    ]
)


def resize_and_rescale(image, new_size, is_greyscale):
    image = tf.cast(image, tf.float32)
    if is_greyscale:
        image = tf.expand_dims(image, axis=-1)
        image = tf.image.grayscale_to_rgb(image)
    image = tf.image.resize(
        image,
        [new_size, new_size],
        method="nearest",
    )
    image = image / 255.0

    return image


def read_images(file, label):
    image = tf.io.read_file(file)
    image = tf.image.decode_jpeg(image, channels=3)
    image = tf.cast(image, tf.float32)
    image = tf.keras.applications.vgg16.preprocess_input(image)
    image = tf.image.resize(image, [227, 227], method="nearest")
    image = image / 255.0
    return image, label


def prepare_office_ds(source_directory, target_directory, params):
    source_images_list, source_labels_list = create_paths(source_directory)
    target_images_list, target_labels_list = create_paths(target_directory)

    ds_repetition_value = math.ceil(len(source_images_list) / len(target_images_list))

    source_ds = tf.data.Dataset.from_tensor_slices(
        (source_images_list, source_labels_list)
    )
    source_ds = source_ds.map(read_images, num_parallel_calls=cn.AUTOTUNE)

    source_ds = source_ds.map(
        lambda x, y: (data_augmentation(x, training=True), y),
        num_parallel_calls=cn.AUTOTUNE,
    ).shuffle(len(source_images_list), reshuffle_each_iteration=True)

    target_ds_original = tf.data.Dataset.from_tensor_slices(
        (target_images_list, target_labels_list)
    )
    target_ds_original = target_ds_original.map(
        read_images, num_parallel_calls=cn.AUTOTUNE
    ).shuffle(len(target_images_list), reshuffle_each_iteration=True)

    target_ds = target_ds_original.repeat(ds_repetition_value)

    source_images, target_images, source_labels, target_labels = [], [], [], []
    for x, y in tf.data.Dataset.zip((source_ds, target_ds)):
        source_images.append(x[0])
        target_images.append(y[0])
        source_labels.append(x[1])
        target_labels.append(y[1])

    ds_train = tf.data.Dataset.from_tensor_slices(
        ((source_images, target_images), source_labels)
    )
    ds_train = ds_train.batch(params["batch_size"]).prefetch(buffer_size=cn.AUTOTUNE)

    x1, y1 = [], []
    for x, y in target_ds_original:
        x1.append(x)
        y1.append(y)

    ds_test = (
        tf.data.Dataset.from_tensor_slices(((x1, x1), y1))
        .batch(params["batch_size"])
        .prefetch(buffer_size=cn.AUTOTUNE)
    )

    train_count = [x for x in ds_train]
    tf.compat.v1.logging.info("Batch count of training set: " + str(len(train_count)))

    test_count = [x for x in ds_test]
    tf.compat.v1.logging.info("Batch count of test set: " + str(len(test_count)))

    return ds_train, ds_test


def augment(
    image_source,
    image_target,
    label,
    new_size,
    source_is_greyscale,
    target_is_greyscale,
):

    image0 = resize_and_rescale(image_source, new_size, source_is_greyscale)
    image1 = resize_and_rescale(image_target, new_size, target_is_greyscale)
    # if int(channels) == 3:
    #     if tf.random.uniform((), minval=0, maxval=1) < 0.1:
    #         image = tf.tile(tf.image.rgb_to_grayscale(image), [1, 1, 3])
    image0 = tf.image.random_brightness(image0, max_delta=0.5)
    image0 = tf.image.random_contrast(image0, lower=0.1, upper=0.5)
    image0 = tf.image.adjust_saturation(image0, 3)
    # a left upside down flipped
    # image0 = tf.image.random_flip_left_right(image0)  # 50%
    # image0 = tf.image.random_flip_up_down(image0)  # 50%
    return ((image0, image1), label)


def fetch_data(params):

    if params["combination"] == 1:
        source_directory = cn.OFFICE_DS_PATH / "amazon"
        target_directory = cn.OFFICE_DS_PATH / "webcam"

        return prepare_office_ds(source_directory, target_directory, params)

    elif params["combination"] == 2:
        source_directory = cn.OFFICE_DS_PATH / "amazon"
        target_directory = cn.OFFICE_DS_PATH / "dslr"

        return prepare_office_ds(source_directory, target_directory, params)

    elif params["combination"] == 3:
        source_directory = cn.OFFICE_DS_PATH / "webcam"
        target_directory = cn.OFFICE_DS_PATH / "amazon"

        return prepare_office_ds(source_directory, target_directory, params)

    elif params["combination"] == 4:
        source_directory = cn.OFFICE_DS_PATH / "webcam"
        target_directory = cn.OFFICE_DS_PATH / "dslr"

        return prepare_office_ds(source_directory, target_directory, params)

    elif params["combination"] == 5:
        source_directory = cn.OFFICE_DS_PATH / "dslr"
        target_directory = cn.OFFICE_DS_PATH / "amazon"

        return prepare_office_ds(source_directory, target_directory, params)

    elif params["combination"] == 6:
        source_directory = cn.OFFICE_DS_PATH / "dslr"
        target_directory = cn.OFFICE_DS_PATH / "webcam"

        return prepare_office_ds(source_directory, target_directory, params)

    elif (params["combination"]) == 7:
        (mnistx_train, mnisty_train), (_, _) = tf.keras.datasets.mnist.load_data()

        mnistmx_train, _ = extract_mnist_m(cn.MNIST_M_PATH)
        mnistmx_train, mnistmy_train = shuffle_dataset(mnistmx_train, mnisty_train)
        ds_train = tf.data.Dataset.from_tensor_slices(
            ((mnistx_train, mnistmx_train), mnisty_train)
        )

        # ds_custom_val = tf.data.Dataset.from_tensor_slices(
        #     (mnistmx_train, mnistmy_train)
        # )

        ds_test = tf.data.Dataset.from_tensor_slices(
            ((mnistmx_train, mnistmx_train), mnistmy_train)
        )

        # Setup for train dataset
        ds_train = (
            ds_train.map(
                lambda x, y: augment(x[0], x[1], y, params["resize"], True, False),
                num_parallel_calls=cn.AUTOTUNE,
            )
            .cache()
            .batch(params["batch_size"])
            .prefetch(cn.AUTOTUNE)
            # .shuffle(mnisty_train.shape[0])
        )

        # Setup for test Dataset
        ds_test = (
            ds_test.map(
                (
                    lambda x, y: (
                        (
                            resize_and_rescale(x[0], params["resize"], False),
                            resize_and_rescale(x[1], params["resize"], False),
                        ),
                        y,
                    )
                ),
                num_parallel_calls=cn.AUTOTUNE,
            )
            .batch(params["batch_size"])
            .prefetch(cn.AUTOTUNE)
        )

        # # Setup for Custom Val Dataset
        # ds_custom_val = (
        #     ds_custom_val.map(
        #         (lambda x, y: (resize_and_rescale(x, params["resize"], False), y)),
        #         num_parallel_calls=cn.AUTOTUNE,
        #     )
        #     .batch(params["batch_size"])
        #     .prefetch(cn.AUTOTUNE)
        # )

        train_count = [x for x in ds_train]
        tf.compat.v1.logging.info(
            "Batch count of training set: " + str(len(train_count))
        )

        test_count = [x for x in ds_test]
        tf.compat.v1.logging.info("Batch count of test set: " + str(len(test_count)))

        return ds_train, ds_test

    elif params["combination"] == 8:

        (mnistx_train, mnisty_train), (_, _) = tf.keras.datasets.mnist.load_data()

        mnistmx_train, _ = extract_mnist_m(cn.MNIST_M_PATH)
        mnistmy_train = mnisty_train

        mnistx_train, mnisty_train = shuffle_dataset(mnistx_train, mnisty_train)

        ds_train = tf.data.Dataset.from_tensor_slices(
            ((mnistmx_train, mnistx_train), mnistmy_train)
        )

        ds_test = tf.data.Dataset.from_tensor_slices(
            ((mnistx_train, mnistx_train), mnisty_train)
        )

        # Setup for train dataset
        ds_train = (
            ds_train.map(
                (lambda x, y: augment(x[0], x[1], y, params["resize"], False, True)),
                num_parallel_calls=cn.AUTOTUNE,
            )
            .cache()
            .batch(params["batch_size"])
            .prefetch(cn.AUTOTUNE)
        )

        # Setup for test Dataset
        ds_test = (
            ds_test.map(
                (
                    lambda x, y: (
                        (
                            resize_and_rescale(x[0], params["resize"], True),
                            resize_and_rescale(x[1], params["resize"], True),
                        ),
                        y,
                    )
                ),
                num_parallel_calls=cn.AUTOTUNE,
            )
            .batch(params["batch_size"])
            .prefetch(cn.AUTOTUNE)
        )

        train_count = [x for x in ds_train]
        tf.compat.v1.logging.info(
            "Batch count of training set: " + str(len(train_count))
        )

        test_count = [x for x in ds_test]
        tf.compat.v1.logging.info("Batch count of test set: " + str(len(test_count)))

        return ds_train, ds_test
