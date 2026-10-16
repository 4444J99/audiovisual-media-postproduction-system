import json
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

import execution_journal as journal
import scene_actions as actions


class SceneActionsTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / 'history.sqlite'
        self.score = {'events': [{'start_frame': 30, 'end_frame': 90, 'speed': 1}]}
        self.owner = {'pid': 1, 'node': 1, 'session': 'fixture'}
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('CREATE TABLE performances(id TEXT,score TEXT)')
            db.execute('INSERT INTO performances VALUES (?,?)', ('fixture', json.dumps(self.score)))
        self.run = self.begin()

    def begin(self, mode='new', parent_run=None):
        run = journal.begin(self.path, 'fixture', self.score, mode, self.owner, parent_run)
        journal.request(self.path, run, 0, 30)
        journal.observe(self.path, run, 0, 30, first=True)
        return run

    def record(self, kind='attend', field=1, payload=None, frame=40):
        return actions.record(self.path, self.run, 0, frame, kind, field, payload or {})

    def test_action_and_checkpoint_commit_together(self):
        row = self.record()
        self.assertEqual(journal.get(self.path, self.run)['source_frame'], 40)
        self.assertEqual(actions.rows(self.path, self.run), [row])
        self.assertEqual(journal.get(self.path, self.run)['score'], self.score)

    def test_invalid_or_backward_clock_cannot_change_history(self):
        self.record(frame=45)
        for frame in (44, 90, float('nan')):
            with self.assertRaises(ValueError):
                self.record(frame=frame)
        self.assertEqual(len(actions.rows(self.path, self.run)), 1)
        self.assertEqual(journal.get(self.path, self.run)['source_frame'], 45)

    def test_hold_refuse_message_attention_release(self):
        initial = actions.empty()
        def apply(state, kind, field, payload=None):
            return actions.reduce(state, {'action': kind, 'field': field, 'payload': payload or {}, 'event_index': 0})
        state = apply(initial, 'attend', 2)
        self.assertEqual((actions.gain(state, 2, 0), actions.gain(state, 1, 0)), (1, .25))
        state = apply(state, 'hold', 1, {'spec': {'slot': 1, 'start_frame': 300, 'end_frame': 320}, 'frame': 310})
        state = apply(state, 'message', 1, {'text': 'receiver'})
        state = apply(state, 'refuse', 3)
        self.assertEqual((actions.gain(state, 3, 0), actions.gain(state, 3, 1)), (.25, 0))
        later = apply(state, 'refuse', 3, {'target_event': 4})
        self.assertEqual((actions.gain(later, 3, 1), actions.gain(later, 3, 4)), (.25, 0))
        self.assertEqual(apply(state, 'release', -1), initial)
        self.assertEqual(initial, actions.empty())
        with self.assertRaises(ValueError):
            apply(state, 'hold', 0, {'spec': {'slot': 0, 'start_frame': 0, 'end_frame': 20}, 'frame': 10})
        with self.assertRaises(ValueError):
            apply(state, 'message', 1, {'text': 'x' * 129})

    def test_replay_snapshot_and_recovery_prefix(self):
        self.record('attend', 2, frame=40)
        self.record('message', 1, {'text': 'receiver'}, frame=50)
        journal.transition(self.path, self.run, 'stopped')
        replay = self.begin('replay')
        state, queue = actions.bind(self.path, replay, self.run)
        self.assertEqual(state, actions.empty())
        self.assertEqual(len(queue), 2)
        actions.realize(self.path, replay, queue[0])
        journal.observe(self.path, replay, 0, 45)
        journal.transition(self.path, replay, 'interrupted')
        recovered = journal.begin(self.path, 'fixture', self.score, 'recovery', self.owner, replay)
        state, pending = actions.bind(self.path, recovered, replay, recovery=True)
        self.assertEqual(state['attention'], 2)
        self.assertEqual([a['source_frame'] for a in pending], [50])
        self.assertEqual(len(actions.rows(self.path, recovered)), 1)

    def test_live_or_different_source_cannot_bind(self):
        replay = self.begin('replay')
        with self.assertRaises(ValueError):
            actions.bind(self.path, replay, self.run)

    def test_replay_checkpoint_and_duplicate_realization(self):
        action = self.record(frame=40)
        journal.transition(self.path, self.run, 'stopped')
        replay = self.begin('replay')
        actions.bind(self.path, replay, self.run)
        with self.assertRaises(ValueError):
            actions.realize(self.path, replay, action, 39)
        actions.realize(self.path, replay, action, 42)
        self.assertEqual(journal.get(self.path, replay)['source_frame'], 42)
        with self.assertRaises(ValueError):
            actions.realize(self.path, replay, action, 42)
        with self.assertRaises(ValueError):
            actions.record(self.path, replay, 0, 41, 'attend', 2, {})

    def test_new_recovery_actions_survive_another_interruption(self):
        self.record('attend', 2, frame=40)
        journal.transition(self.path, self.run, 'interrupted')
        recovered = journal.begin(self.path, 'fixture', self.score, 'recovery', self.owner, self.run)
        actions.bind(self.path, recovered, self.run, recovery=True)
        journal.request(self.path, recovered, 0, 40)
        journal.observe(self.path, recovered, 0, 40, first=True)
        actions.record(self.path, recovered, 0, 45, 'message', 1, {'text': 'receiver'})
        journal.transition(self.path, recovered, 'interrupted')
        again = journal.begin(self.path, 'fixture', self.score, 'recovery', self.owner, recovered)
        state, queue = actions.bind(self.path, again, recovered, recovery=True)
        self.assertEqual(state['attention'], 2)
        self.assertEqual(state['messages'], {'1': 'receiver'})
        self.assertEqual(queue, [])

    def test_capacity_failure_keeps_checkpoint_and_terminal_space(self):
        for _ in range(actions.LIMIT):
            self.record()
        with self.assertRaises(ValueError):
            self.record(frame=41)
        self.assertEqual(journal.get(self.path, self.run)['source_frame'], 40)
        self.assertEqual(len(actions.rows(self.path, self.run)), actions.LIMIT)
        journal.transition(self.path, self.run, 'stopped')

    def test_same_frame_post_checkpoint_action_stays_queued(self):
        first=self.record('attend',2,frame=40)
        self.record('message',1,{'text':'later'},frame=40)
        journal.transition(self.path,self.run,'interrupted')
        recovered=journal.begin(self.path,'fixture',self.score,'recovery',self.owner,self.run)
        state,pending=actions.bind(self.path,recovered,self.run,recovery=True,inherit_origins=[[first['origin_run'],first['origin_sequence']]])
        self.assertEqual(state['attention'],2);self.assertEqual(state['messages'],{})
        self.assertEqual([a['action'] for a in pending],['message'])
        self.assertEqual(len(actions.rows(self.path,recovered)),1)


if __name__ == '__main__':
    unittest.main()
