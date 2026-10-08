# Room-tone rack

The rack reconstructs the same eight screened pause portions into independent low, mid and high streams. All eligible portions contribute to each band before reuse. Each stream has its own seed and irregular fragment order, source-fragment RMS stabilization (bounded ±4 dB), cosine overlap crossfades, stereo-linked soft-knee compression, a dry path and an FX return.

| Band | Crossover range | Ratio | Attack / release | FX |
|---|---|---|---|---|
| Low | 25–180 Hz | 2.5:1 | 90 / 1000 ms | Soft saturation; low-band guard |
| Mid | 180–2400 Hz | 1.8:1 | 40 / 700 ms | 31/53 ms early reflections; mid-band guard |
| High | Above 2400 Hz | 2:1 | 20 / 450 ms | 9.5 kHz rolloff, irregular slow ±0.5 dB modulation; high-band guard |

The complementary residual crossover sums back to the filtered input before independent processing. Band definitions are filter ranges rather than brick-wall partitions. The default FX blend is 25%. A common output gain places the combined bed at −42 dBFS RMS; three final layers sum to it, as do the six dry-contribution/FX-return stems. There is no gate or automatic compressor makeup gain. FX returns share the same final gain as their dry contributions.

Crossfades request 120–220 ms and are capped to one third of the fragment duration. Short source portions consequently use shorter joins; cosine amplitude weights are normalized during overlap-add. This is not a repeating clip loop. Reused source portions and every output join remain in the per-band edit maps.

Run:

```sh
python tools/run_roomrack.py --source /path/source.mp4 \
  --inventory /path/outputs/room-tone/room-tone-report.json \
  --output /path/outputs/room-rack
```

The default is a conservative support bed. Dynamics, spectral balance, joins and FX naturalness require listening with the dialogue. Individual effects can be bypassed or rebalanced using the six stems. No new original room recording is implied.
