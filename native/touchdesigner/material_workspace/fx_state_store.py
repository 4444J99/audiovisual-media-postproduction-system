"""Private atomic FX checkpoints with finite bytes and verified array payloads."""
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import threading
import time
import uuid
import numpy as np

MAX_BYTES = 1024 * 1024 * 1024
STORE_BYTES = 2 * MAX_BYTES
MAX_ARRAYS = 16384
JOBS={}
JOB_LOCK=threading.Lock()


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):h.update(block)
    return h.hexdigest()


def write(root, metadata, arrays, deadline=None):
    root = Path(root);root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if root.is_symlink():raise ValueError('FX checkpoint root must be an owned directory')
    if len(arrays) > MAX_ARRAYS:raise ValueError('FX checkpoint array count exceeds bounds')
    size = sum(a.nbytes + 4096 for a in arrays.values())
    if size > MAX_BYTES:raise ValueError('FX checkpoint exceeds one GiB')
    existing = 0;count = 0
    for path in root.rglob('*'):
        count += 1
        if count > 65536 or path.is_symlink():raise ValueError('FX store inventory exceeds bounds')
        if path.is_file():existing += path.stat().st_size
    if existing + size > STORE_BYTES:raise ValueError('FX checkpoint store is full; no retained state was discarded')
    if shutil.disk_usage(root).free < size + 512 * 1024 * 1024:raise ValueError('Insufficient free space for bounded FX checkpoint')
    folder = root / uuid.uuid4().hex;folder.mkdir(mode=0o700)
    manifest = {'schema': 'god-here.fx-checkpoint/1', 'metadata': metadata, 'arrays': {}}
    for i, (name, array) in enumerate(arrays.items()):
        if deadline is not None and time.monotonic()>deadline:raise TimeoutError('Native FX writer deadline reached; partial state retained')
        if array.dtype.hasobject or array.nbytes > MAX_BYTES:raise ValueError('Unsafe FX checkpoint array')
        filename = 'a' + str(i) + '.npy';path = folder / filename
        with path.open('xb') as target:
            os.chmod(path, 0o600);np.save(target, array, allow_pickle=False);target.flush();os.fsync(target.fileno())
        manifest['arrays'][name] = {'file': filename, 'sha256': digest(path), 'bytes': path.stat().st_size,
                                   'dtype': array.dtype.str, 'shape': list(array.shape)}
    payload = json.dumps(manifest, sort_keys=True, allow_nan=False).encode('utf-8')
    if len(payload) > 4 * 1024 * 1024:raise ValueError('FX checkpoint manifest exceeds bounds')
    temporary = folder / 'pending.json'
    with temporary.open('xb') as target:
        os.chmod(temporary, 0o600);target.write(payload);target.flush();os.fsync(target.fileno())
    os.replace(temporary, folder / 'complete.json')
    descriptor = os.open(folder, os.O_RDONLY)
    try:os.fsync(descriptor)
    finally:os.close(descriptor)
    return folder


def submit(root,metadata,arrays,commit):
    """One I/O worker; its callback must use only filesystem/SQLite APIs."""
    with JOB_LOCK:
        if any(job['thread'].is_alive() for job in JOBS.values()):raise ValueError('Native FX writer is already active')
        if len(JOBS)>=128:raise ValueError('Native FX writer job capacity reached; no evidence discarded')
        identity=uuid.uuid4().hex;job={'state':'running','folder':None,'error':None,'sequence':None,'started':time.monotonic()}
        for array in arrays.values():array.flags.writeable=False
        def run():
            try:
                folder=write(root,metadata,arrays,deadline=job['started']+30)
                job['folder']=str(folder)
                sequence=commit(folder,digest(folder/'complete.json'))
                with JOB_LOCK:job.update(state='complete',sequence=sequence,elapsed=time.monotonic()-job['started'])
            except Exception as error:
                with JOB_LOCK:job.update(state='failed',error=str(error),elapsed=time.monotonic()-job['started'])
        worker=threading.Thread(target=run,name='godhere-fx-checkpoint-io',daemon=True)
        job['thread']=worker;JOBS[identity]=job;worker.start()
    return identity


def poll(identity):
    with JOB_LOCK:
        if identity not in JOBS:raise ValueError('Unknown native FX writer job')
        job=JOBS[identity];result={k:v for k,v in job.items() if k!='thread'}
        result['alive']=job['thread'].is_alive();result['overdue']=result['alive'] and time.monotonic()-job['started']>30
        return result


def read(folder):
    folder = Path(folder);path = folder / 'complete.json'
    if folder.is_symlink() or path.is_symlink() or path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError('Invalid FX checkpoint manifest')
    manifest = json.loads(path.read_text(encoding='utf-8'))
    if manifest.get('schema') != 'god-here.fx-checkpoint/1' or len(manifest['arrays']) > MAX_ARRAYS:
        raise ValueError('Invalid FX checkpoint schema/count')
    if sum(row['bytes'] for row in manifest['arrays'].values()) > MAX_BYTES:raise ValueError('FX checkpoint exceeds bounds')
    arrays = {}
    for name, row in manifest['arrays'].items():
        filename = row['file']
        if not filename.startswith('a') or not filename.endswith('.npy') or not filename[1:-4].isdigit():
            raise ValueError('Invalid FX checkpoint filename')
        path = folder / filename
        if path.is_symlink() or path.stat().st_size != row['bytes'] or digest(path) != row['sha256']:
            raise ValueError('FX checkpoint payload integrity mismatch')
        with path.open('rb') as source:
            if np.lib.format.read_magic(source)!=(1,0):raise ValueError('Unsupported FX array file version')
            shape, fortran, dtype=np.lib.format.read_array_header_1_0(source)
            if dtype not in (np.dtype('uint8'),np.dtype('float32'),np.dtype('float64')) or len(shape)>4 or any(n<0 for n in shape):
                raise ValueError('Unsafe FX array header')
            data_bytes=math.prod(shape)*dtype.itemsize
            if data_bytes>MAX_BYTES or source.tell()+data_bytes!=row['bytes']:
                raise ValueError('Invalid FX array allocation size')
        a = np.load(path, allow_pickle=False)
        if a.dtype.str != row['dtype'] or list(a.shape) != row['shape'] or a.dtype.hasobject:
            raise ValueError('FX checkpoint array contract mismatch')
        arrays[name] = a
    return manifest['metadata'], arrays
