"""Frame-local learned person instance masks, with explicit source timing.

YOLOv8-seg inference uses an external ONNX checkpoint. The weights are not
vendored into this repository. Person detections do not establish performer
identity: the region association below is only an authored spatial hypothesis.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class PersonMask:
    box: np.ndarray
    confidence: float
    alpha: np.ndarray
    performer: str | None = None


def overlap_iou(box: np.ndarray, boxes: np.ndarray) -> np.ndarray:
    """Axis-aligned intersection over union, including degenerate boxes."""
    lo = np.maximum(box[:2], boxes[:, :2])
    hi = np.minimum(box[2:], boxes[:, 2:])
    intersection = np.maximum(hi - lo, 0).prod(axis=1)
    area = np.maximum(box[2:] - box[:2], 0).prod()
    others = np.maximum(boxes[:, 2:] - boxes[:, :2], 0).prod(axis=1)
    return intersection / np.maximum(area + others - intersection, 1e-9)


def nms(boxes: np.ndarray, scores: np.ndarray, threshold: float) -> list[int]:
    order = np.argsort(-scores, kind="stable")
    keep = []
    while len(order):
        current = int(order[0])
        keep.append(current)
        order = order[1:]
        if len(order):
            order = order[overlap_iou(boxes[current], boxes[order]) <= threshold]
    return keep


def union_alpha(masks: list[PersonMask], shape: tuple[int, int]) -> np.ndarray:
    """Empty detections produce an empty alpha, never reuse an earlier shot."""
    if not masks:
        return np.zeros(shape, dtype=np.float32)
    return np.maximum.reduce([m.alpha for m in masks]).clip(0, 1)


def preserve_bodies(source: np.ndarray, treatment: np.ndarray,
                    alpha: np.ndarray) -> np.ndarray:
    """Restore current source bodies over a separately composed room image."""
    if source.shape != treatment.shape or alpha.shape != source.shape[:2]:
        raise ValueError("Source, treatment, and person alpha dimensions disagree")
    if not np.isfinite(alpha).all():
        raise ValueError("Person alpha contains non-finite values")
    a = np.clip(alpha, 0, 1)[..., None]
    return np.rint(source.astype(np.float32) * a + treatment.astype(np.float32) * (1 - a)).clip(0, 255).astype(np.uint8)


class PersonSegmenter:
    """COCO class-zero instance segmentation in ONNX Runtime on CPU.

    Input: RGB, aspect-preserving bilinear resize, 114 gray letterbox padding,
    float32 [0,1], NCHW 1x3x640x640. Outputs: boxes/classes/coefficients and
    32 learned prototypes. Thresholded prototype logits are unletterboxed,
    resized to source geometry, cropped to the detection box, and lightly
    softened by a one-pixel Gaussian edge. No temporal mask propagation is
    performed, so cuts cannot carry a previous view's masks into a new view.
    """
    def __init__(self, model: str | Path, confidence: float = .25,
                 iou: float = .6, threads: int = 2):
        import onnxruntime as ort
        options = ort.SessionOptions()
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(str(model), options,
                                            providers=["CPUExecutionProvider"])
        self.confidence = confidence
        self.iou = iou
        self.input_name = self.session.get_inputs()[0].name
        shape = self.session.get_inputs()[0].shape
        if shape != [1, 3, 640, 640]:
            raise ValueError(f"Expected YOLOv8-seg 640 checkpoint, got {shape}")

    def __call__(self, rgb: np.ndarray, fields: list[dict] | None = None) -> list[PersonMask]:
        import cv2
        height, width = rgb.shape[:2]
        scale = min(640 / width, 640 / height)
        rw, rh = round(width * scale), round(height * scale)
        left, top = (640 - rw) // 2, (640 - rh) // 2
        canvas = np.full((640, 640, 3), 114, np.uint8)
        canvas[top:top + rh, left:left + rw] = cv2.resize(rgb, (rw, rh), interpolation=cv2.INTER_LINEAR)
        x = np.ascontiguousarray(canvas.transpose(2, 0, 1)[None], dtype=np.float32) / 255
        detections, prototypes = self.session.run(None, {self.input_name: x})
        predictions = detections[0].T
        if predictions.shape[1] != 116 or prototypes.shape[1] != 32:
            raise ValueError("Unexpected YOLOv8-seg checkpoint outputs")
        # Take only predictions whose winning COCO class is person.
        classes = np.argmax(predictions[:, 4:84], axis=1)
        candidates = predictions[(classes == 0) & (predictions[:, 4] >= self.confidence)]
        if not len(candidates):
            return []
        centers, sizes = candidates[:, :2], candidates[:, 2:4]
        boxes = np.concatenate((centers - sizes / 2, centers + sizes / 2), axis=1)
        scores = candidates[:, 4]
        selected = nms(boxes, scores, self.iou)
        logits = candidates[selected, 84:] @ prototypes[0].reshape(32, -1)
        result = []
        for index, mask_logits in zip(selected, logits):
            proto = mask_logits.reshape(160, 160)
            # Crop padding in prototype coordinates, then resize to original.
            a = cv2.resize(proto, (640, 640), interpolation=cv2.INTER_LINEAR)
            a = cv2.resize(a[top:top + rh, left:left + rw], (width, height), interpolation=cv2.INTER_LINEAR)
            box = boxes[index].copy()
            box[[0, 2]] = (box[[0, 2]] - left) / scale
            box[[1, 3]] = (box[[1, 3]] - top) / scale
            box[[0, 2]] = box[[0, 2]].clip(0, width)
            box[[1, 3]] = box[[1, 3]].clip(0, height)
            ys, xs = np.ogrid[:height, :width]
            inside = (xs >= box[0]) & (xs < box[2]) & (ys >= box[1]) & (ys < box[3])
            alpha = ((a > 0) & inside).astype(np.float32)
            alpha = cv2.GaussianBlur(alpha, (3, 3), .65)
            # Spatial association is recorded as provisional, not tracking.
            center_x = (box[0] + box[2]) / 2 / width
            performer = next((f["performer"] for f in (fields or [])
                              if f["span"][0] <= center_x < f["span"][1]), None)
            result.append(PersonMask(box, float(scores[index]), alpha, performer))
        return result
