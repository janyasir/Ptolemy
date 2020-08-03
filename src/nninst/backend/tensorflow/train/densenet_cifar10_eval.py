#  Copyright 2017 The TensorFlow Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
"""Convolutional Neural Network Estimator for MNIST, built with tf.layers."""

import os

import tensorflow as tf

from nninst.backend.tensorflow.dataset import cifar10_main
from nninst.backend.tensorflow.model.densenet import DenseNet, pp_mean
from nninst.backend.tensorflow.utils import new_session_config
from nninst.utils.fs import abspath

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "1"


def model_fn(features, labels, mode):
    """The model_fn argument for creating an Estimator."""
    model = DenseNet()
    image = features
    if isinstance(image, dict):
        image = features["image"]

    if mode == tf.estimator.ModeKeys.EVAL:
        logits = model(image, training=False)
        loss = tf.losses.sparse_softmax_cross_entropy(labels=labels, logits=logits)
        return tf.estimator.EstimatorSpec(
            mode=tf.estimator.ModeKeys.EVAL,
            loss=loss,
            eval_metric_ops={
                "accuracy": tf.metrics.accuracy(
                    labels=labels, predictions=tf.argmax(logits, axis=1)
                )
            },
        )


def eval(batch_size: int = 64, label: str = None):
    # tf.logging.set_verbosity(tf.logging.INFO)
    if label is None:
        model_dir = abspath("tf/densenet/model/")
    else:
        model_dir = abspath(f"tf/densenet/model_{label}/")
    data_dir = abspath("/home/yxqiu/data/cifar10-raw")

    estimator_config = tf.estimator.RunConfig(
        session_config=new_session_config(parallel=0)
    )
    classifier = tf.estimator.Estimator(
        model_fn=model_fn, model_dir=model_dir, config=estimator_config
    )

    # Evaluate the model and print results
    def eval_input_fn():
        return cifar10_main.test(
            data_dir=data_dir,
            batch_size=batch_size,
            normed=False,
            transform_fn=lambda ds: ds.map(
                lambda image, label: ((image - pp_mean) / 128.0 - 1, label)
            ),
        )

    eval_results = classifier.evaluate(input_fn=eval_input_fn)
    print(label)
    print("Evaluation results:\n\t%s" % eval_results)
    print()


if __name__ == "__main__":
    eval()
