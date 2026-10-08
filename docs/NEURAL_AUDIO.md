DTLN enhancement is an executed production trial. It is independent of the
earlier spectral subtraction and manual visual masks.

The adapter uses the author-published `model_1.onnx` and `model_2.onnx` from
[breizhn/DTLN](https://github.com/breizhn/DTLN), pinned to commit
`1de1f15a8b5b7e1c44905618ff2ef70ca8277fbc`. Checksums are enforced before
inference. The MIT notice is retained in [DTLN-LICENSE.txt](DTLN-LICENSE.txt).
The model was introduced by Nils L. Westhausen and Bernd T. Meyer in
“Dual-Signal Transformation LSTM Network for Real-Time Noise Suppression,”
Interspeech 2020, DOI `10.21437/Interspeech.2020-2631`.

Install the adapter runtime with `python -m pip install onnxruntime`. The
baseline NumPy/SciPy dependencies remain required. Model downloads are explicit
in the run tool; the compositor itself does not fetch models.

```sh
python tools/run_neural_audio.py \
  --source /absolute/path/to/source.mp4 \
  --transcript projects/god-here/transcript.provisional.json \
  --dsp-candidate /absolute/path/to/conservative-unmatched.wav \
  --model-directory /absolute/path/to/models/dtln \
  --out /absolute/path/to/neural-audio
```

Both channels of the supplied stereo mixture are processed independently,
with recurrent states reset between channels. This preserves the source's
small stereo differences; it does not yield isolated voices. The fixed-rate
16 kHz model is preceded and followed by polyphase resampling. A full-strength
candidate and a restrained 70% learned / 30% original candidate are retained.
The latter retains some source energy above the model's 8 kHz Nyquist limit.
Title and credits use the original signal, with 150 ms scene handovers.

The streaming overlap buffer introduces a 384-sample output-index offset at
16 kHz. Offline inference flushes the final partial block and the complete
overlap tail, removes that offset, and preserves the exact source sample
count. This is distinct from the upstream 32 ms real-time block latency, which
includes the 128-sample collection interval. The identity-synthesis test
checks first samples, final samples, and a non-multiple block length. Actual
speech cross-correlation checks are recorded in the run report.

All full-scene candidates share one feasible active-speech loudness target;
the pilot candidates share their own target. The mask is the union of existing
automatic transcript intervals and serves only as the evaluation definition.
The report also measures delivered AAC trials, true peaks, timing, model
identity, and output hashes. The original and previous conservative DSP
candidate remain available for matched comparison.

The full-strength estimate may suppress quiet words, incidental sound, room
tone, or consonants, and may create audible artifacts. No transcript is
silently corrected and no missing word is synthesized. Preference, naturalness,
and intelligibility require listening to the randomized comparisons and
checking the actual performed language. Those acceptance decisions remain
pending.
