"""Tests for Wing 11 Archival Provenance, Documentary Ethics & Counter-Archive framework (Issues #110-113, W11)."""
import unittest

from amp.studies.provenance_archive import (
    build_provenance_lineage_graph,
    export_counter_archive_packet,
    seal_archival_study_ledger,
    verify_documentary_ethics_disclosure,
)


class ProvenanceArchiveStudiesTests(unittest.TestCase):
    def setUp(self):
        self.unit_id = "BM-01"
        self.studies_clean = [
            {"study_id": "study-sep-01", "operator": "amp.roomstretch.v1", "metadata": {"wing": "wing_1_sound"}},
            {"study_id": "study-surface-01", "operator": "amp.render.v1", "metadata": {"wing": "wing_2_surface"}},
        ]
        self.studies_with_undisclosed_cf = [
            {"study_id": "study-sep-01", "operator": "amp.roomstretch.v1", "metadata": {"wing": "wing_1_sound"}},
            {
                "study_id": "study-inpaint-01",
                "operator": "amp.render.v1",
                "metadata": {"wing": "wing_5_inpaint", "is_counterfactual": True, "ethics_disclosure": False},
            },
        ]
        self.studies_with_disclosed_cf = [
            {"study_id": "study-sep-01", "operator": "amp.roomstretch.v1", "metadata": {"wing": "wing_1_sound"}},
            {
                "study_id": "study-inpaint-01",
                "operator": "amp.render.v1",
                "metadata": {"wing": "wing_5_inpaint", "is_counterfactual": True, "ethics_disclosure": True},
            },
        ]

    def test_build_provenance_lineage_graph(self):
        graph = build_provenance_lineage_graph(self.unit_id, self.studies_clean)
        self.assertEqual(graph["schema"], "amps.god_here.lineage_graph.v1")
        self.assertEqual(graph["unit_id"], self.unit_id)
        # Root node + 2 studies = 3 nodes
        self.assertEqual(graph["node_count"], 3)
        self.assertEqual(graph["edge_count"], 2)
        root = graph["nodes"][0]
        self.assertEqual(root["type"], "documentary_source")
        self.assertFalse(root["is_counterfactual"])

    def test_verify_documentary_ethics_disclosure(self):
        # Disclosed counterfactual pass
        graph_ok = build_provenance_lineage_graph(self.unit_id, self.studies_with_disclosed_cf)
        audit_ok = verify_documentary_ethics_disclosure(graph_ok)
        self.assertTrue(audit_ok["ethical_disclosure_verified"])
        self.assertEqual(audit_ok["undisclosed_branches"], [])

        # Undisclosed counterfactual failure
        graph_fail = build_provenance_lineage_graph(self.unit_id, self.studies_with_undisclosed_cf)
        audit_fail = verify_documentary_ethics_disclosure(graph_fail)
        self.assertFalse(audit_fail["ethical_disclosure_verified"])
        self.assertGreater(len(audit_fail["undisclosed_branches"]), 0)

    def test_seal_archival_study_ledger_and_export_packet(self):
        graph = build_provenance_lineage_graph(self.unit_id, self.studies_clean)
        ledger = seal_archival_study_ledger("comp-001", [graph])

        self.assertEqual(ledger["schema"], "amps.god_here.sealed_archival_ledger.v1")
        self.assertTrue(ledger["sealed"])
        self.assertEqual(len(ledger["ledger_sha256"]), 64)

        packet = export_counter_archive_packet(ledger)
        self.assertEqual(packet["schema"], "amps.god_here.counter_archive_packet.v1")
        self.assertTrue(packet["preserves_omitted_takes"])
        self.assertTrue(packet["preserves_truthful_provenance"])
        self.assertIn("ARCHIVE-PACKET-", packet["packet_id"])

        # Rejection of unsealed ledger
        with self.assertRaises(ValueError):
            export_counter_archive_packet({"sealed": False})


if __name__ == "__main__":
    unittest.main()
