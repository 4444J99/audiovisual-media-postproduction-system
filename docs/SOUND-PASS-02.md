# god-here sound and person-mask pass 02

This pass executes the previously unrun trained enhancement and segmentation branches, adds a source-derived nonlooping room bed, and makes a source-timed foley score concrete. The unchanged source remains the reference. The new full film and A–E proof are workprints for listening, contour and artistic review.

## Sound construction

DTLN's two pretrained ONNX stages process both channels of the supplied mixture at 16 kHz, then return to 48 kHz. The full learned estimate and 70% learned / 30% original blend are separate candidates. Recurrent buffer delay is flushed and compensated. Five correlation checks show 0 ms offset; four delivered pilot trials differ by only 0.01 LU in the provisional active-speech mask. Those measurements do not determine which version sounds better. The higher-frequency dry portion and untouched title/credits remain in the restrained blend.

Silero VAD runs on the source to screen every one of the 32 provisional transcript gaps. The inventory records exclusions as well as accepted portions. Phrase protection and transient screening leave eight eligible portions, totaling 4.42 seconds, from seven gaps. A seeded shuffle uses every portion before reuse, prevents adjacent repeats, slightly varies rate and gain, and crossfades joins into a 112-second stereo bed. No fixed clip is looped. Recorded samples recur; the construction does not claim 112 seconds of unique original silence. The source-pause audition and complete source/output edit map accompany the bed. Its reconstructed VAD maximum is 0.0572, below the screening threshold 0.12; human checking for quiet words, breathing, clinks and audible joins remains necessary.

The foley score contains 47 newly authored procedural events. Movement/clothing and inferred chair support, glass handling/contact, and short sip gestures are timed from inspected source frames. The score records the evidence and timing confidence for each event. Glass work concerns drinking vessels; no spectacle adjustment was confirmed. The stove/simmer hypothesis is based on the screenplay and visible kitchen setting, with burner activity unverified. It has its own nonperiodic stem and an optional mix, and is excluded from the default composed workprint.

The final sound pass preserves the provisional trained dialogue core, adds room tone at -42 dBFS RMS before scene fades, adds the restrained foley-main at +9 dB relative to its authored stem level, and uses newly rendered expressive returns from the same repaired mixture. A single fixed headroom trim applies equally to every delivered mix stem. The repaired core still contains some original room and incidental sounds: these new layers support it rather than claiming surgical replacement. Individual performer voices have not been isolated.

## Picture construction

YOLOv8n-seg produces actual learned COCO person-instance masks in both camera views. The full person union holds current bodies over the five-region room treatment; the five pilot mask tracks offer independent spatial controls. The association to P01–P05 is a provisional detection-box centroid assignment against each view's registered regions, not verified identity tracking. Face/hand edges, hair, thin objects, held cups, temporal shimmer and overlaps require moving-image review. P02 has 20 missed detection frames around 57.733–59.567 seconds; the report lists them individually. Missing mask pixels fall through to the fixed-field treatment. If a mask fails, the accepted fixed-field composition is available as a concrete fallback. No depth measurement or hidden-space reconstruction is implied.

| Proof | Picture | Sound |
|---|---|---|
| A | Original | Level-matched original |
| B | Original | Restrained trained-dialogue blend |
| C | Five regions | The same dialogue as B |
| D | Five regions | Same dialogue level plus room, foley and expressive returns |
| E | Learned bodies over five regions | The same composed sound as D |

All proofs use source frames 2554–3214 inclusive, 661 frames / 22.033333 seconds. Full workprints use 3360 frames / 112 seconds. The default stove bus is muted; its separate audition gives a reviewable alternative.

## Regenerate

Install FFmpeg/ffprobe and `python -m pip install -e '.[learned]'`. Preserve the source hash recorded in the project manifest. Start with the existing baseline render, then run:

```sh
python tools/run_neural_audio.py --source /path/source.mp4 \
  --transcript projects/god-here/transcript.provisional.json \
  --dsp-candidate /path/outputs/audio/conservative-unmatched.wav \
  --model-directory /path/models/dtln --out /path/outputs/neural-audio
python tools/run_roomtone.py --source /path/source.mp4 \
  --model /path/models/silero-vad/silero_vad.onnx --output /path/outputs/room-tone
python tools/run_foley.py /path/source.mp4 /path/outputs/foley
python tools/run_segmentation.py --source /path/source.mp4 \
  --config projects/god-here/composition.json --model /path/models/yolov8n-seg.onnx \
  --output /path/outputs/segmentation
python tools/finish_sound_pass.py --source /path/source.mp4 --outputs /path/outputs
python tools/check.py
```

The exact model URLs, revisions and hashes are in the run scripts/reports. DTLN and Silero are MIT; DTLN attribution/license is retained in `DTLN-LICENSE.txt`. The external YOLO checkpoint is AGPL-3.0 and is not vendored in the repository. See `NEURAL_AUDIO.md` and `SEGMENTATION.md` for each model's limitations and provenance.

The package contains films, trial audio, 48 kHz / 24-bit FLAC stems, masks, source-timed scores, source maps and validation records. It does not certify performed text as captions. Human listening, mask acceptance, real-device playback and venue calibration remain review gates.
