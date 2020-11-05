"""
Copyright (c) 2018-2020 Intel Corporation

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

      http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

from functools import singledispatch
from PIL import Image
import numpy as np
from ..representation import (
    SegmentationPrediction, SegmentationAnnotation,
    StyleTransferAnnotation, StyleTransferPrediction,
    SuperResolutionPrediction, SuperResolutionAnnotation,
    ImageProcessingPrediction, ImageProcessingAnnotation,
    ImageInpaintingAnnotation, ImageInpaintingPrediction
)
from ..postprocessor.postprocessor import PostprocessorWithSpecificTargets, ApplyToOption
from ..postprocessor import ResizeSegmentationMask
from ..config import NumberField
from ..utils import get_size_from_config


class Resize(PostprocessorWithSpecificTargets):

    __provider__ = 'resize'

    prediction_types = (StyleTransferPrediction, ImageProcessingPrediction,
                        SegmentationPrediction, SuperResolutionPrediction,
                        ImageInpaintingPrediction)
    annotation_types = (StyleTransferAnnotation, ImageProcessingAnnotation,
                        SegmentationAnnotation, SuperResolutionAnnotation,
                        ImageInpaintingPrediction)

    @classmethod
    def parameters(cls):
        parameters = super().parameters()
        parameters.update({
            'dst_width': NumberField(
                value_type=int, optional=True, min_value=1, description="Destination width for resize"
            ),
            'dst_height': NumberField(
                value_type=int, optional=True, min_value=1, description="Destination height for resize."
            ),
            'size': NumberField(
                value_type=int, optional=True, min_value=1,
                description="Destination size for resize for both dimensions (height and width)."
            )
        })
        return parameters

    def configure(self):
        self.dst_height, self.dst_width = get_size_from_config(self.config, allow_none=True)
        self._required_both = True

    def process_image(self, annotations, predictions):
        @singledispatch
        def resize(entry, height, width):
            return entry

        @resize.register(StyleTransferAnnotation)
        @resize.register(StyleTransferPrediction)
        @resize.register(SuperResolutionAnnotation)
        @resize.register(SuperResolutionPrediction)
        @resize.register(ImageProcessingAnnotation)
        @resize.register(ImageProcessingPrediction)
        @resize.register(ImageInpaintingAnnotation)
        @resize.register(ImageInpaintingPrediction)
        def _(entry, height, width):
            entry.value = entry.value.astype(np.uint8)
            data = Image.fromarray(entry.value)
            data = data.resize((width, height), Image.BICUBIC)
            entry.value = np.array(data)

            return entry

        @resize.register(SegmentationPrediction)
        def _(entry, height, width):
            if len(entry.mask.shape) == 2:
                entry.mask = ResizeSegmentationMask.segm_resize(entry.mask, width, height)
                return entry

            entry_mask = []
            for class_mask in entry.mask:
                resized_mask = ResizeSegmentationMask.segm_resize(class_mask, width, height)
                entry_mask.append(resized_mask)
            entry.mask = np.array(entry_mask)

            return entry

        @resize.register(SegmentationAnnotation)
        def _(entry, height, width):
            entry.mask = ResizeSegmentationMask.segm_resize(entry.mask, width, height)

            return entry

        @singledispatch
        def set_sizes(entry):
            height = self.dst_height if self.dst_height else self.image_size[0]
            width = self.dst_width if self.dst_width else self.image_size[1]

            return height, width

        @set_sizes.register(SuperResolutionAnnotation)
        @set_sizes.register(SuperResolutionPrediction)
        def _(entry):
            height = self.dst_height if self.dst_height else entry.value.shape[0]
            width = self.dst_width if self.dst_width else entry.value.shape[1]

            return height, width

        @set_sizes.register(SegmentationPrediction)
        def _(entry):
            if self._deprocess_predictions:
                return self.image_size[:2]
            height = self.dst_height if self.dst_height else self.image_size[0]
            width = self.dst_width if self.dst_width else self.image_size[1]

            return height, width

        if self.apply_to is None or self.apply_to in [ApplyToOption.PREDICTION, ApplyToOption.ALL]:
            if annotations:
                for annotation, prediction in zip(annotations, predictions):
                    height, width = set_sizes(annotation or prediction)
                    resize(prediction, height, width)
            else:
                for prediction in predictions:
                    height, width = set_sizes(prediction)
                    resize(prediction, height, width)

        if self.apply_to is None or self.apply_to in [ApplyToOption.ANNOTATION, ApplyToOption.ALL]:
            for annotation in annotations:
                if annotation is None:
                    continue
                height, width = set_sizes(annotation)
                resize(annotation, height, width)

        return annotations, predictions
