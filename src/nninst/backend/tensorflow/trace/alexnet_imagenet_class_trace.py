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

import argparse
import itertools
import sys
from functools import partial

from nninst import mode
from nninst.backend.tensorflow.dataset import imagenet_raw
from nninst.backend.tensorflow.dataset.config import IMAGENET_RAW_TRAIN
from nninst.backend.tensorflow.dataset.imagenet_preprocessing import (
    alexnet_preprocess_image,
)
from nninst.backend.tensorflow.model import AlexNet
from nninst.backend.tensorflow.model.config import ALEXNET
from nninst.backend.tensorflow.trace.common import (
    class_trace,
    class_trace_compact,
    class_trace_growth,
    class_unique_trace_compact,
    full_trace,
    merged_class_trace_compact,
    save_class_traces_low_latency,
    save_class_traces_v2,
    self_similarity,
)
from nninst.backend.tensorflow.trace.utils import (
    get_entry_points,
    get_select_seed_fn,
    get_variant,
)
from nninst.trace import (
    get_hybrid_backward_trace,
    get_per_input_unstructured_trace,
    get_trace,
    get_type2_trace,
    get_type3_trace,
    get_type4_trace,
    get_type7_trace,
    merge_simple_trace,
)
from nninst.utils.ray import ray_init

__all__ = ["alexnet_imagenet_class_trace", "alexnet_imagenet_self_similarity"]


def dataset_fn(*args, **kwargs):
    return imagenet_raw.train(
        *args, **kwargs, class_from_zero=True, preprocessing_fn=alexnet_preprocess_image
    )


data_config = IMAGENET_RAW_TRAIN.copy(dataset_fn=dataset_fn)

name = "alexnet_imagenet"

alexnet_imagenet_class_trace = class_trace(
    name=name, model_config=ALEXNET, data_config=data_config, use_raw=True
)

alexnet_imagenet_class_trace_compact = class_trace_compact(
    alexnet_imagenet_class_trace, name=name, model_config=ALEXNET
)

alexnet_imagenet_merged_class_trace_compact = merged_class_trace_compact(
    alexnet_imagenet_class_trace_compact, name=name
)

alexnet_imagenet_class_unique_trace_compact = class_unique_trace_compact(
    alexnet_imagenet_class_trace_compact,
    alexnet_imagenet_merged_class_trace_compact,
    name=name,
    min_id=0,
    max_id=1000,
)

alexnet_imagenet_class_trace_growth = class_trace_growth(
    name=name, model_config=ALEXNET, data_config=data_config, use_raw=True
)

save_alexnet_imagenet_class_traces_low_latency = save_class_traces_low_latency(
    name=name, model_config=ALEXNET, data_config=data_config, use_raw=True
)

alexnet_imagenet_trace = full_trace(
    name=name, class_trace_fn=alexnet_imagenet_class_trace
)

alexnet_imagenet_self_similarity = self_similarity(
    name=name, trace_fn=alexnet_imagenet_class_trace, class_ids=range(0, 1000, 10)
)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--type",
        type=str,
        default="EP",
        help="Different types of path extraction, default EP, pick between BwCU, BwAB and FwAB",
    )
    parser.add_argument(
        "--cumulative_threshold",
        type=float,
        default=0.5,
        help="cumulative threshold theta, default 0.5",
    )
    parser.add_argument(
        "--absolute_threshold",
        type=float,
        default=0.1,
        help="absolute threshold phi, default None",
    )
    params, unparsed = parser.parse_known_args()
    from nninst.backend.tensorflow.attack.calc_per_layer_metrics import (
        get_per_layer_metrics,
    )

    # mode.check(False)
    # mode.debug()
    mode.local()
    # mode.distributed()
    # ray_init("dell")
    # ray_init(include_webui=True)
    ray_init(num_cpus=16)
    # ray_init("r730")

    label = "import"
    # label = "without_dropout"
    # label = "import_old"

    # variant = "intersect"
    if params.absolute_threshold == 0:
        t = None
    else:
        t = params.absolute_threshold
    print(f"generate class trace for label {label}")
    # pdb.set_trace()
    for threshold, absolute_threshold in itertools.product(
        # [
        # 1.0,
        # 0.9,
        # 0.7,
        #    0.5,
        # 0.3,
        # 0.1,
        # ]
        [params.cumulative_threshold],
        #[
        #None,
        # 0.05,
        # 0.1,
        # 0.2,
        # 0.3,
        # 0.4,
         #]
        [t],
    ):
        per_layer_metrics = lambda: get_per_layer_metrics(
            ALEXNET, threshold=threshold, absolute_threshold=absolute_threshold
        )
        # hybrid_backward_traces = [
        #     [
        #         partial(
        #             get_hybrid_backward_trace,
        #             output_threshold=per_layer_metrics(),
        #             input_threshold=per_layer_metrics(),
        #             type_code=type_code,
        #         ),
        #         f"type{type_code}_trace",
        #         f"density_from_{threshold:.1f}",
        #     ]
        #     for type_code in [
        #         # "21111111", # == type2
        #         "21111112",
        #         "21111122",
        #         "21111222",
        #         "21112222",
        #         "21122222",
        #         "21222222",
        #         "22222222",
        #         # "42222222", # == type4
        #     ]
        # ]
        if params.type == "EP":
            type_ = [get_trace, None, None]
        elif params.type == "BwCU":
            type_ = [
                partial(get_type2_trace, output_threshold=per_layer_metrics()),
                "type2_trace",
                f"density_from_{threshold:.1f}",
            ]
        elif params.type == "BwAB":
            type_ = [
                partial(
                    get_type4_trace,
                    output_threshold=per_layer_metrics(),
                    input_threshold=per_layer_metrics(),
                ),
                "type4_trace",
                f"density_from_{threshold:.1f}_absolute_{absolute_threshold:.2f}",
            ]
        elif params.type == "FwAB":
            type_ = [
                partial(
                    get_per_input_unstructured_trace,
                    output_threshold=per_layer_metrics(),
                    input_threshold=per_layer_metrics(),
                ),
                "per_input_unstructured_class_trace",
                f"density_from_{threshold:.1f}",
            ]
        else:
            print("path construction type not supported")
            sys.exit()

        for (example_num, layer_num, seed_threshold, trace_info) in itertools.product(
            [
                0,
                # 100,
                # 200,
                # 300,
                # 400,
                # 700,
                # 1000,
            ],
            [
                0,
                # 4,
            ],
            [
                None,
                # 0.5,
                # 0.1,
                # 0.01,
                # 0.001,
            ],
            [
                type_
                # [get_trace, None, None],  # type1
                # [
                #     partial(get_type2_trace, output_threshold=per_layer_metrics()),
                #     "type2_trace",
                #     f"density_from_{threshold:.1f}",
                # ],
                # [
                #     partial(get_type3_trace, input_threshold=per_layer_metrics()),
                #     "type3_trace",
                #     f"density_from_{threshold:.1f}",
                # ],
                # [
                #     partial(
                #         get_type4_trace,
                #         output_threshold=per_layer_metrics(),
                #         input_threshold=per_layer_metrics(),
                #     ),
                #     "type4_trace",
                #     f"density_from_{threshold:.1f}",
                # ],
                # [
                #     partial(
                #         get_type4_trace,
                #         output_threshold=per_layer_metrics(),
                #         input_threshold=per_layer_metrics(),
                #     ),
                #     "type4_trace",
                #     f"density_from_{threshold:.1f}_absolute_{absolute_threshold:.2f}",
                # ],
                # [partial(get_unstructured_trace, density=per_layer_metrics),
                #  "unstructured_class_trace",
                #  f"density_from_{threshold:.1f}"], # type5
                # [
                #     partial(
                #         get_per_receptive_field_unstructured_trace,
                #         output_threshold=per_layer_metrics(),
                #     ),
                #     "per_receptive_field_unstructured_class_trace",
                #     f"density_from_{threshold:.1f}",
                # ], # type6
                # [
                #     partial(
                #         get_type7_trace,
                #         density=per_layer_metrics(),
                #         input_threshold=per_layer_metrics(),
                #     ),
                #     "type7_trace",
                #     f"density_from_{threshold:.1f}",
                # ],
                # [
                #     partial(
                #         get_per_input_unstructured_trace,
                #         output_threshold=per_layer_metrics(),
                #         input_threshold=per_layer_metrics(),
                #     ),
                #     "per_input_unstructured_class_trace",
                #     f"density_from_{threshold:.1f}",
                # ], # type8
                # *hybrid_backward_traces
            ],
        ):
            trace_fn, trace_type, trace_parameter = trace_info
            entry_points = get_entry_points(AlexNet.graph().load(), layer_num)
            select_seed_fn = get_select_seed_fn(seed_threshold)
            variant = get_variant(example_num, layer_num, seed_threshold)

            trace_fn = partial(
                trace_fn, select_seed_fn=select_seed_fn, entry_points=entry_points
            )
            save_class_traces_v2(
                partial(
                    alexnet_imagenet_class_trace,
                    trace_fn=trace_fn,
                    trace_type=trace_type,
                    trace_parameter=trace_parameter,
                    threshold=threshold,
                    label=label,
                    variant=variant,
                    # example_num=example_num, example_upperbound=1000,
                    example_num=1000,
                    example_upperbound=1000,
                    merge_fn=merge_simple_trace,
                    # parallel=4,
                    # cache=False,
                ),
                range(0, 1000),
            )

            save_class_traces_v2(
                partial(
                    alexnet_imagenet_class_trace_compact,
                    trace_type=trace_type,
                    trace_parameter=trace_parameter,
                    threshold=threshold,
                    label=label,
                    variant=variant,
                    # cache=False,
                ),
                range(0, 1000),
            )

            # class_trace_size(
            #     alexnet_imagenet_class_trace_compact,
            #     name=name,
            #     threshold=threshold,
            #     label=label,
            #     variant=variant,
            #     trace_type=trace_type,
            #     trace_parameter=trace_parameter,
            # ).save()

        # save_merged_traces(
        #     alexnet_imagenet_merged_class_trace_compact, 0, 1000, threshold=threshold, label=label, variant=variant)
        # save_class_traces(
        #     alexnet_imagenet_class_unique_trace_compact, range(1000), threshold=threshold, label=label, variant=variant)

        # alexnet_imagenet_trace(threshold=threshold, label=label, class_ids=range(0, 1000)).save()

        # check_class_traces(alexnet_imagenet_class_trace, range(0, 1000), threshold, label, compress=True)

        # alexnet_imagenet_self_similarity(threshold, label, variant=variant).save()

        # trace = alexnet_imagenet_trace(threshold, label).load()
        # for key in [TraceKey.POINT, TraceKey.EDGE, TraceKey.WEIGHT]:
        #     print(f"{key}: {calc_density_compact(trace, key)}")

        # trace = alexnet_imagenet_class_unique_trace_compact(0, threshold, label).load()
        # for key in [TraceKey.POINT, TraceKey.EDGE, TraceKey.WEIGHT]:
        #     print(f"{key}: {calc_density_compact(trace, key)}")

        # for class_id in range(0, 1000):
        #     trace_size = calc_trace_size(
        #         alexnet_imagenet_class_trace_compact(class_id, threshold, label, variant).load(), key=TraceKey.EDGE,
        #         compact=True)
        #     print(f"class: {class_id}, size: {trace_size}")
