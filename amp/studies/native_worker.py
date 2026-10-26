"""Fixed retained-native worker, supervised as one group by the study executor."""
import json
import os
from pathlib import Path
import resource
import sys

# Fixed code-relative package root, including outside a checkout. The supervisor
# starts this exact script with isolated Python; ambient PYTHONPATH is not used.
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))

from amp.execution import execute,preflight
from amp.media_resolver import ContractError,read_json
from amp.studies.execution_artifacts import bounded_identity


def main():
    try:
        job=read_json(sys.argv[1],role='study-native-job',limit=4*1024**2)
        maximum=job['max_file_bytes']
        if type(maximum) is not int or not 1<=maximum<=2*1024**3:raise ContractError('study_resource_profile_invalid')
        resource.setrlimit(resource.RLIMIT_FSIZE,(maximum,maximum));os.nice(10)
        output=Path(job['output'])
        if output!=Path(sys.argv[1]).resolve().parent/'native':raise ContractError('study_worker_output_invalid')
        plan=preflight(job['binding_path'],locations=job['locations'],inventories=job['inventories'],
            expected_binding_identity=job['expected_binding_identity'],identity_reader=lambda path,role,expected:
                bounded_identity(path,role,expected,deadline=job['deadline_monotonic']))
        # Native children stay inside this supervised worker process group.
        receipt=execute(plan,output,isolate_process_group=False)
        print(json.dumps(receipt,sort_keys=True,allow_nan=False));return 0
    except ContractError as error:
        print(json.dumps({'status':'blocked','error':{'code':error.code}}));return 2
    except (OSError,ValueError,KeyError,TypeError,IndexError,AttributeError,StopIteration):
        print(json.dumps({'status':'blocked','error':{'code':'study_native_execution_failed'}}));return 2


if __name__=='__main__':raise SystemExit(main())
