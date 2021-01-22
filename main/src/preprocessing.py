import os
import tensorflow as tf
import src.config as cn
import math
from src.utils import extract_mnist_m, create_paths, shuffle_dataset

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"


def augment_ds(image, label):
    # Make Images Greyscale
    image = tf.cond(
        tf.random.uniform(shape=[], minval=0, maxval=1) < 0.1,
        lambda: tf.tile(tf.image.rgb_to_grayscale(image), [1, 1, 3]),
        lambda: image,
    )
    noise = tf.random.normal(
        shape=tf.shape(image), mean=0.0, stddev=1, dtype=tf.float32
    )
    # Adding Gaussian Noise
    image = tf.cond(
        tf.random.uniform(shape=[], minval=0, maxval=1) < 0.1,
        lambda: tf.add(image, noise),
        lambda: image,
    )

    # Colour Augmentations
    image = tf.image.random_brightness(image, max_delta=0.2)
    image = tf.image.random_contrast(image, lower=0.1, upper=0.3)
    image = tf.image.adjust_saturation(image, 2)

    # Rotating Images
    image = tf.cond(
        tf.random.uniform(shape=[], minval=0, maxval=1) < 0.1,
        lambda: tf.image.rot90(image, k=1),
        lambda: image,
    )

    # Flipping Images
    image = tf.image.random_flip_left_right(image)
    image = tf.image.random_flip_up_down(image)

    return image, label


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


def read_images(file, new_size):
    image = tf.io.read_file(file)
    image = tf.image.decode_jpeg(image, channels=3)
    image = tf.cast(image, tf.float32)
    image = tf.keras.applications.vgg16.preprocess_input(image)
    image = tf.image.resize(image, [new_size, new_size], method="nearest")
    # image = image / 255.0
    return image


def prepare_office_ds(source_directory, target_directory, params, source_is_less=False):

    source_images_list, source_labels_list = create_paths(source_directory)
    target_images_list, target_labels_list = create_paths(target_directory)

    if source_is_less:
        source_images_list = source_images_list * math.ceil(
            len(target_images_list) / len(source_images_list)
        )
        source_labels_list = source_labels_list * math.ceil(
            len(target_labels_list) / len(source_labels_list)
        )
    else:
        ds_repetition_value = math.ceil(
            len(source_images_list) / len(target_images_list)
        )

    source_ds = tf.data.Dataset.from_tensor_slices(
        (source_images_list, source_labels_list)
    )
    source_ds = (
        source_ds.map(
            lambda x, y: (
                read_images(x, params["resize"]),
                y,
            ),
            num_parallel_calls=cn.AUTOTUNE,
        )
        .cache()
        .shuffle(len(source_images_list), reshuffle_each_iteration=True)
    )

    source_ds = source_ds.map(
        (lambda x, y: augment_ds(x, y)), num_parallel_calls=cn.AUTOTUNE
    )

    target_ds_original = tf.data.Dataset.from_tensor_slices(
        (target_images_list, target_labels_list)
    )

    target_ds_original = (
        target_ds_original.map(
            lambda x, y: (
                read_images(x, params["resize"]),
                y,
            ),
            num_parallel_calls=cn.AUTOTUNE,
        )
        .cache()
        .shuffle(len(target_images_list), reshuffle_each_iteration=True)
    )

    target_ds = (
        target_ds_original
        if source_is_less
        else target_ds_original.repeat(ds_repetition_value)
    )

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
    image0 = tf.image.random_brightness(image0, max_delta=0.5)
    image0 = tf.image.random_contrast(image0, lower=0.1, upper=0.5)
    image0 = tf.image.adjust_saturation(image0, 3)
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

        return prepare_office_ds(source_directory, target_directory, params, True)

    elif params["combination"] == 4:
        source_directory = cn.OFFICE_DS_PATH / "webcam"
        target_directory = cn.OFFICE_DS_PATH / "dslr"

        return prepare_office_ds(source_directory, target_directory, params)

    elif params["combination"] == 5:
        source_directory = cn.OFFICE_DS_PATH / "dslr"
        target_directory = cn.OFFICE_DS_PATH / "amazon"

        return prepare_office_ds(source_directory, target_directory, params, True)

    elif params["combination"] == 6:
        source_directory = cn.OFFICE_DS_PATH / "dslr"
        target_directory = cn.OFFICE_DS_PATH / "webcam"

        return prepare_office_ds(source_directory, target_directory, params, True)

    elif (params["combination"]) == 7:
        (mnistx_train, mnisty_train), (_, _) = tf.keras.datasets.mnist.load_data()

        mnistmx_train, _ = extract_mnist_m(cn.MNIST_M_PATH)
        mnistmx_train, mnistmy_train = shuffle_dataset(mnistmx_train, mnisty_train)
        ds_train = tf.data.Dataset.from_tensor_slices(
            ((mnistx_train, mnistmx_train), mnisty_train)
        )

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
            .shuffle(mnisty_train.shape[0], reshuffle_each_iteration=True)
            .batch(params["batch_size"])
            .prefetch(buffer_size=cn.AUTOTUNE)
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
            .prefetch(buffer_size=cn.AUTOTUNE)
        )
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
            .shuffle(mnistmy_train.shape[0], reshuffle_each_iteration=True)
            .batch(params["batch_size"])
            .prefetch(buffer_size=cn.AUTOTUNE)
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
            .prefetch(buffer_size=cn.AUTOTUNE)
        )

        train_count = [x for x in ds_train]
        tf.compat.v1.logging.info(
            "Batch count of training set: " + str(len(train_count))
        )

        test_count = [x for x in ds_test]
        tf.compat.v1.logging.info("Batch count of test set: " + str(len(test_count)))

        return ds_train, ds_test
