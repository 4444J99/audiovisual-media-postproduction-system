"""Check source-record identity and temporal association boundaries locally."""
import importlib.util
import json
import sys
from pathlib import Path


def verify(source_records):
    spec=importlib.util.spec_from_file_location('navigation',Path(__file__).with_name('navigation.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    records=json.loads(Path(source_records).read_text(encoding='utf-8'))
    layers={actor:'base_composition/layer_actor_'+actor for actor in module.MATTE_CANDIDATES.values()}
    rows=module.derive(records,True,layers)
    assert len(rows)==174
    assert len({r['event_id'] for r in rows})==174
    assert sum(r['event_kind']=='dialogue' for r in rows)==35
    assert all(0<=r['start_s']<r['end_s']<=112.014 for r in rows)
    assert all(r['start_s']<76 and r['end_s']>70 for r in rows if r['candidate'])
    assert all('Provisional' in r['candidate_note'] for r in rows if r['candidate'])
    by_id={r['event_id']:r for r in rows}
    assert (by_id['P06']['start_s'],by_id['P06']['end_s'])==(by_id['P07']['start_s'],by_id['P07']['end_s'])
    unmatched=module.derive(records,False,layers)
    assert all(r['source_match']!='hash verified' and not r['candidate'] for r in unmatched)
    assert not any(r['candidate'] for r in module.derive(records,True,{}))
    return {'records':len(rows),'dialogue':35,'visual':139,
            'interval_limited_provisional_actor_links':sum(bool(r['candidate']) for r in rows),
            'mismatched_source_links_withheld':True,'shared_phrase_windows_preserved':True}


if __name__=='__main__':
    print(json.dumps(verify(sys.argv[1]),indent=2))
