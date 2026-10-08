# Learned body masks

The second workprint runs a pretrained YOLOv8n-seg instance segmentation model
on every dialogue frame. ONNX Runtime returns learned person masks, which are
separate from the authored five regions. The regions still determine how the
room changes; the masks let the current recorded bodies remain visible over
that treatment, including arms crossing a region boundary.

The full scene has a lossless 640×360 union-alpha track on the source clock and
a 1280×720 body-preserving picture. The 661-frame proof also exports five
independently addressable mask estimates and a three-panel review movie.
Title and credit frames have empty masks and retain the source picture.

## Reproduce

Install the `learned` optional dependency group, or install
`onnxruntime` and `opencv-python-headless` alongside the base dependencies.
Then, from the repository root:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python tools/run_segmentation.py \
  --source ../project_sources/02-2020-04-26-god-s-ears-second-draft.mp4 \
  --config projects/god-here/composition.json \
  --model ../models/yolov8n-seg.onnx \
  --output ../outputs/segmentation
```

The tool downloads the pinned external ONNX checkpoint if absent and checks
its SHA-256 before inference. Model weights are not included in this repository.
The export inherits the upstream checkpoint's AGPL-3.0 license, recorded in the
machine-readable report. Its upstream documentation and conversion record are:

- https://docs.ultralytics.com/models/yolov8/
- https://docs.ultralytics.com/tasks/segment/
- https://huggingface.co/unileon-robotics/YOLO8-ONNX/blob/223bf64bbb0fe4f20b759f20c493130f4e848a76/README.md

Source analysis first uses a 640×360 area downsample. Model input uses RGB
values scaled to [0,1], a bilinear aspect-preserving resize,
114-gray letterbox padding and a 1×3×640×640 float32 tensor. Person detections
use a 0.25 confidence threshold and 0.6 overlap suppression. Mask coefficients
combine the learned prototypes; positive logits are cropped to the detection
box, returned to source geometry and softened at the edge by one pixel.

## Identity and review limits

P01–P05 mask tracks use each detection's horizontal center and the authored
layout for the current camera view. That is a provisional spatial association,
not a learned identity tracker or a verified screenplay-name mapping. Multiple
detections associated with the same region are unioned; a missing detection
produces empty alpha. Inference is independent at every frame, so a camera cut
cannot propagate a mask from the previous view.

All five mask controls have detections in every proof frame. That measures
availability, not accuracy. Moving-image review still needs to judge edges,
occlusion, cups, glasses, missed pixels, duplicate detections, and foreground
ghosts caused by the original region transformations. The five fixed regions
remain a usable comparison when a finer mask is unstable.

Across the complete dialogue scene, four controls have detections in all
3,064 frames. P02 has no associated detection in 20 frames around
57.733–59.567 seconds. Those exact intervals are listed in the report for
targeted review; the masks do not invent a hidden body behind an occluder.

A MediaPipe selfie-segmentation ONNX trial was actually run first and rejected:
it returned nearly empty alpha in the wide alternate view. Its failure record
is retained with the production results. The accepted trial uses COCO instance
segmentation; SAM 2 and temporal identity tracking have not been run.
