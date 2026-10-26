#!/usr/bin/env python3
"""One bounded localhost browser probe. Synthetic media is never production evidence.

Serve only public web code and in-memory synthetic assets for three minutes.
No original media, uploads, persistent server, or provider/browser launch.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import struct
import sys
import threading
import wave
import zlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tests.composition.fixtures import record
from amp.composition.performance_cli import retained_engine_identity


def sha(value):
    return hashlib.sha256(value).hexdigest()


def chunk(name, data):
    return struct.pack('>I', len(data)) + name + data + struct.pack('>I', zlib.crc32(name + data))


def fixtures():
    png = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 120, 1, 8, 2, 0, 0, 0))
           + chunk(b'IDAT', zlib.compress(b'\0' + b'\xff\0\0' * 120)) + chunk(b'IEND', b''))
    audio = io.BytesIO()
    with wave.open(audio, 'wb') as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(44100)
        stream.writeframes(struct.pack('<h', 1000) * 176400)
    wav = audio.getvalue()
    page = dict(file='atlas.png', sha256=sha(png), bytes=len(png), width=120, height=1)
    manifest = dict(schema='amps.prepared-material.v1',
                    media=dict(fps=30, duration=4, columns=120, framesPerPage=120,
                               picture=dict(width=1, height=1), matte=dict(width=1, height=1)),
                    assets=dict(picture=[page], matte=[page]),
                    audio=dict(file='source.wav', sha256=sha(wav), bytes=len(wav), channels=1,
                               samples=176400, sample_rate=44100))
    material = json.dumps(manifest).encode()
    saved = record().to_dict()
    saved['runtime']['materials'][0].update(sha256=sha(material), bytes=len(material))
    saved['runtime']['engine_sha256'] = retained_engine_identity(ROOT)
    saved['runtime']['profile'].update(admitted=True, byte_caps=dict(
        decoded_audio_bytes=100_000_000, texture_bytes=100_000_000, event_history_bytes=1_000_000))
    saved['provenance'] = dict(fixture='synthetic-browser-regression', artistic_acceptance='pending')
    return {'record.json': json.dumps(saved).encode(), 'clip.material.json': material,
            'atlas.png': png, 'source.wav': wav}


class Handler(SimpleHTTPRequestHandler):
    payloads = fixtures()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / 'web'), **kwargs)

    def do_GET(self):
        if self.path.startswith('/__performance_fixture/'):
            payload = self.payloads.get(self.path.rsplit('/', 1)[-1])
            if payload is None:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Length', str(len(payload)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(payload)
        else:
            super().do_GET()

    def log_message(self, *args):
        pass


if __name__ == '__main__':
    os.nice(10)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    timer = threading.Timer(180, server.shutdown)
    timer.daemon = True
    timer.start()
    print(json.dumps(dict(port=server.server_port, pid=os.getpid(), deadline_seconds=180,
                          evidence_scope='synthetic browser regression only')), flush=True)
    try:
        server.serve_forever()
    finally:
        timer.cancel()
        server.server_close()
