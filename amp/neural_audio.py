"""Pinned, stateful DTLN speech-enhancement inference.

This processes the recorded mixture. It does not isolate performers, restore
missing words, or establish listening acceptance. No model training is implied.

DTLN streaming structure adapted from Nils L. Westhausen's MIT-licensed
real_time_processing_onnx.py; copyright (c) 2020 Nils L. Westhausen.
The complete upstream license is retained in docs/DTLN-LICENSE.txt.
"""
from pathlib import Path
import hashlib

import numpy as np
from scipy import signal

MODEL_REVISION = "1de1f15a8b5b7e1c44905618ff2ef70ca8277fbc"
MODEL_SHA256 = {
    "model_1.onnx": "22b91cae3855e5a0620e66a917ca6c82c58db0e842c770f58d86751c5e8d4ae3",
    "model_2.onnx": "e20c92f9233fccf29cddf86970d0d0161a03aebccc26d6f4d5639c4d5ec2e639",
}
MODEL_RATE = 16000
BLOCK_LENGTH = 512
BLOCK_SHIFT = 128
# Streaming output index 0 corresponds to input index -384. Offline rendering
# flushes the tail and removes this offset; collection of the next 128 samples
# adds another 8 ms to the author's quoted real-time 32 ms block latency.
STREAM_OFFSET = BLOCK_LENGTH - BLOCK_SHIFT


def verify_models(directory):
    paths = []
    for filename, expected in MODEL_SHA256.items():
        path = Path(directory) / filename
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"DTLN model checksum mismatch: {filename}")
        paths.append(path)
    return paths


class DTLN:
    """A new instance starts both recurrent state tensors at zero."""

    def __init__(self, model_directory):
        import onnxruntime as ort
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        self.sessions = [ort.InferenceSession(str(path), sess_options=options,
                                             providers=["CPUExecutionProvider"])
                         for path in verify_models(model_directory)]

    def process(self, samples):
        x = np.asarray(samples, dtype=np.float32)
        if x.ndim != 1:
            raise ValueError("DTLN expects one 16 kHz mixture channel")
        if not np.isfinite(x).all():
            raise ValueError("Non-finite DTLN input")
        names = [[inp.name for inp in s.get_inputs()] for s in self.sessions]
        states = [np.zeros((1, 2, 128, 2), np.float32) for _ in self.sessions]

        def block(buffer):
            spectrum = np.fft.rfft(buffer)
            magnitude = np.abs(spectrum).reshape(1, 1, -1).astype(np.float32)
            mask, states[0] = self.sessions[0].run(None, {names[0][0]: magnitude,
                                                        names[0][1]: states[0]})
            estimated = np.fft.irfft(magnitude * mask * np.exp(1j * np.angle(spectrum)),
                                     n=BLOCK_LENGTH).reshape(1, 1, -1).astype(np.float32)
            output, states[1] = self.sessions[1].run(None, {names[1][0]: estimated,
                                                          names[1][1]: states[1]})
            return output.reshape(-1)

        return overlap_stream(x, block)


def overlap_stream(samples, process_block):
    """Flush and compensate the exact buffer offset without trimming endings."""
    x = np.asarray(samples, dtype=np.float32)
    blocks = (len(x) + STREAM_OFFSET + BLOCK_SHIFT - 1) // BLOCK_SHIFT
    padded = np.pad(x, (0, blocks * BLOCK_SHIFT - len(x)))
    output = np.zeros(blocks * BLOCK_SHIFT, np.float32)
    in_buffer = np.zeros(BLOCK_LENGTH, np.float32)
    out_buffer = np.zeros(BLOCK_LENGTH, np.float32)
    for idx in range(blocks):
        start = idx * BLOCK_SHIFT
        in_buffer[:-BLOCK_SHIFT] = in_buffer[BLOCK_SHIFT:]
        in_buffer[-BLOCK_SHIFT:] = padded[start:start + BLOCK_SHIFT]
        out_buffer[:-BLOCK_SHIFT] = out_buffer[BLOCK_SHIFT:]
        out_buffer[-BLOCK_SHIFT:] = 0
        out_buffer += np.asarray(process_block(in_buffer), np.float32)
        output[start:start + BLOCK_SHIFT] = out_buffer[:BLOCK_SHIFT]
    return output[STREAM_OFFSET:STREAM_OFFSET + len(x)].copy()


def enhance_48k(samples, model_directory, blend=.70, scene=(5.033333, 107.166667)):
    """Return an aligned 48 kHz stereo candidate and its pure model estimate.

    Independent channel inference preserves the supplied stereo perspective.
    The model operates at 16 kHz, so upper frequencies rely on the dry portion
    of the restrained blend. The untreated source is retained outside scene.
    """
    x = np.asarray(samples, dtype=np.float32)
    if x.ndim != 2 or x.shape[1] != 2:
        raise ValueError("Expected 48 kHz stereo")
    if not 0 <= blend <= 1:
        raise ValueError("Blend must be between zero and one")
    model = DTLN(model_directory)
    estimated = []
    for channel in range(2):
        down = signal.resample_poly(x[:, channel], 1, 3).astype(np.float32)
        up = signal.resample_poly(model.process(down), 3, 1)
        estimated.append(up[:len(x)])
    neural = np.column_stack(estimated).astype(np.float32)
    env = np.zeros(len(x), np.float32)
    a, b = max(0, round(scene[0] * 48000)), min(len(x), round(scene[1] * 48000))
    env[a:b] = blend
    n = min(round(.15 * 48000), (b - a) // 2)
    if n > 0:
        env[a:a+n] *= np.linspace(0, 1, n)
        env[b-n:b] *= np.linspace(1, 0, n)
    candidate = x * (1 - env[:, None]) + neural * env[:, None]
    return candidate.astype(np.float32), neural
