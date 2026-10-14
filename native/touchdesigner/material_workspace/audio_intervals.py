"""Align real streaming samples by native interval metadata, never stretch gaps."""
import numpy as np


def align(samples,start,rate,target_start,target_count,target_rate=44100):
    samples=np.asarray(samples,dtype=np.float32)
    if not len(samples):return np.zeros(target_count,np.float32)
    positions=(target_start+np.arange(target_count))/target_rate*rate-start
    return np.interp(positions,np.arange(len(samples)),samples,left=0,right=0).astype(np.float32)
