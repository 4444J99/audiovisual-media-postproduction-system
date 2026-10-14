import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

import execution_journal as journal


class ExecutionJournalTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.path=Path(self.directory.name)/'history.sqlite'
        self.score={'source_sha256':'a'*64,'events':[{'unit':'a','start_frame':30,'end_frame':60,'speed':1},{'unit':'b','start_frame':90,'end_frame':120,'speed':1}]}
        with sqlite3.connect(self.path) as db:
            db.execute('CREATE TABLE performances(id TEXT,score TEXT)')
            db.execute('INSERT INTO performances VALUES (?,?)',('reserved',json.dumps(self.score)))
        self.owner={'pid':1,'node':1,'session':'first'}

    def begin(self):return journal.begin(self.path,'reserved',self.score,'new',self.owner)

    def test_reserved_score_is_immutable(self):
        changed={**self.score,'events':[]}
        with self.assertRaises(ValueError):journal.begin(self.path,'reserved',changed,'replay',self.owner)

    def test_stale_end_cannot_complete_without_start(self):
        run=self.begin();journal.request(self.path,run,0,30)
        with self.assertRaises(ValueError):journal.complete_event(self.path,run,0,59)
        with self.assertRaises(ValueError):journal.transition(self.path,run,'complete')
        self.assertEqual(journal.get(self.path,run)['completed'],[])

    def test_observed_full_run_and_terminal_state(self):
        run=self.begin()
        for index,start,end in [(0,30,60),(1,90,120)]:
            journal.request(self.path,run,index,start);journal.observe(self.path,run,index,start,first=True)
            journal.complete_event(self.path,run,index,end-1)
        journal.transition(self.path,run,'complete')
        self.assertEqual(journal.get(self.path,run)['status'],'complete')
        with self.assertRaises(ValueError):journal.transition(self.path,run,'playing')

    def test_live_owner_is_not_interrupted(self):
        run=self.begin();result=journal.reconcile(self.path,lambda row:True)
        self.assertEqual(result['live_owners'],[run]);self.assertEqual(result['interrupted'],[])

    def test_recovery_inherits_only_observed_prefix(self):
        run=self.begin();journal.request(self.path,run,0,30);journal.observe(self.path,run,0,30,True);journal.complete_event(self.path,run,0,59)
        journal.request(self.path,run,1,90);journal.observe(self.path,run,1,100,True)
        journal.reconcile(self.path,lambda row:False)
        recovered=journal.begin(self.path,'reserved',self.score,'recovery',{**self.owner,'session':'second'},run)
        row=journal.get(self.path,recovered)
        self.assertEqual((row['event_index'],row['source_frame'],row['completed']),(1,100,[0]))
        self.assertEqual(journal.get(self.path,run)['status'],'interrupted')

    def test_skipping_an_event_is_rejected(self):
        run=self.begin()
        with self.assertRaises(ValueError):journal.request(self.path,run,1,90)

    def test_finished_recovery_is_not_offered_again(self):
        run=self.begin();journal.reconcile(self.path,lambda row:False)
        recovered=journal.begin(self.path,'reserved',self.score,'recovery',self.owner,run)
        for index,start,end in [(0,30,60),(1,90,120)]:
            journal.request(self.path,recovered,index,start);journal.observe(self.path,recovered,index,start,True)
            journal.complete_event(self.path,recovered,index,end-1)
        journal.transition(self.path,recovered,'complete')
        self.assertIsNone(journal.latest_interrupted(self.path))

    def test_out_of_bounds_observation_is_rejected(self):
        run=self.begin();journal.request(self.path,run,0,30)
        with self.assertRaises(ValueError):journal.observe(self.path,run,0,120,True)

    def test_capacity_preserves_a_terminal_record(self):
        run=self.begin()
        with sqlite3.connect(self.path) as db:
            for sequence in range(1,127):
                db.execute('INSERT INTO execution_events VALUES (?,?,?,?,?,?,?)',(run,sequence,'fixture',0,None,0,'{}'))
        with self.assertRaises(ValueError):journal.transition(self.path,run,'paused')
        journal.transition(self.path,run,'failed','Event capacity')
        self.assertEqual(journal.get(self.path,run)['status'],'failed')
        with sqlite3.connect(self.path) as db:self.assertEqual(db.execute('SELECT count(*) FROM execution_events').fetchone()[0],128)


if __name__=='__main__':unittest.main()
