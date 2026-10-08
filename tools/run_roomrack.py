import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from amp.roomrack import build
parser=argparse.ArgumentParser()
parser.add_argument('--source',required=True)
parser.add_argument('--inventory',required=True)
parser.add_argument('--output',required=True)
a=parser.parse_args()
r=build(a.source,a.inventory,a.output)
print({k:r[k] for k in ['duration_seconds','crossovers_hz','output_rms_dbfs']})
