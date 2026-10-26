"""Finite canonical labels for resolved events, preserving meaningful draw order.

Independent array ordering is not a new graph. Same-z overlapping picture order
is meaningful in the retained compositor and is represented as an explicit edge.
Highly ambiguous graphs fail closed at a finite work budget, never claim a
universal or unbounded uniqueness oracle.
"""
from __future__ import annotations

from collections import Counter
import json


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def canonical_events(events, material_ids):
    indices = {event["id"]: index for index, event in enumerate(events)}
    attributes, edges = [], []
    for index, event in enumerate(events):
        node = {key: value for key, value in event.items()
                if key not in {"id", "parent_id", "reused_from", "couplings"}}
        if "material_id" in node:
            node["material_id"] = material_ids[node["material_id"]]
        attributes.append(node)
        for field in ("parent_id", "reused_from"):
            if event.get(field) is not None:
                edges.append((index, indices[event[field]], _json({"role": field})))
        for slot, coupling in enumerate(event.get("couplings", [])):
            label = {key: value for key, value in coupling.items() if key != "source_event_id"}
            edges.append((index, indices[coupling["source_event_id"]],
                          _json({"role": "coupling", "slot": slot, **label})))
    layers = {}
    for index, event in enumerate(events):
        if event.get("picture"):
            layers.setdefault(event["z_index"], []).append(index)
    for layer in layers.values():
        active = []
        for index in sorted(layer, key=lambda i: (events[i]["start_frame"], i)):
            active = [prior for prior in active if events[prior]["end_frame"] > events[index]["start_frame"]]
            for prior in active:
                edges.append((min(index, prior), max(index, prior), '{"role":"visual-order"}'))
                if len(edges) > 100_000:
                    raise ValueError("Performance graph exceeds canonicalization work budget")
            active.append(index)
    if len(edges) > 100_000:
        raise ValueError("Performance graph exceeds canonicalization work budget")
    labels = [_json(node) for node in attributes]
    colors = {label: index for index, label in enumerate(sorted(set(labels)))}
    initial = tuple(colors[label] for label in labels)
    outgoing = [Counter() for _ in events]
    incoming = [Counter() for _ in events]
    for source, target, label in edges:
        outgoing[source][target, label] += 1
        incoming[target][source, label] += 1
    work = [0, 0]

    def refine(values):
        while len(set(values)) < len(values):
            work[0] += len(events) + len(edges)
            if work[0] > 5_000_000:
                raise ValueError("Performance graph exceeds canonicalization work budget")
            signatures = [_json([values[i],
                sorted((label, values[j], count) for (j, label), count in outgoing[i].items()),
                sorted((label, values[j], count) for (j, label), count in incoming[i].items())])
                for i in range(len(events))]
            palette = {value: index for index, value in enumerate(sorted(set(signatures)))}
            refined = tuple(palette[value] for value in signatures)
            if len(set(refined)) == len(set(values)):
                return refined
            values = refined
        return values

    def twins(a, b):
        def external(mapping):
            return {key: count for key, count in mapping.items() if key[0] not in {a, b}}
        if external(outgoing[a]) != external(outgoing[b]) or external(incoming[a]) != external(incoming[b]):
            return False
        self_a = {label: count for (j, label), count in outgoing[a].items() if j == a}
        self_b = {label: count for (j, label), count in outgoing[b].items() if j == b}
        cross_a = {label: count for (j, label), count in outgoing[a].items() if j == b}
        cross_b = {label: count for (j, label), count in outgoing[b].items() if j == a}
        return self_a == self_b and cross_a == cross_b

    def search(values, depth=0):
        work[1] += 1
        if work[1] > 10_000 or depth > 256:
            raise ValueError("Performance graph exceeds canonicalization work budget")
        values = refine(values)
        cells = {}
        for index, color in enumerate(values):
            cells.setdefault(color, []).append(index)
        ambiguous = [(len(cell), color, cell) for color, cell in cells.items() if len(cell) > 1]
        if not ambiguous:
            order = sorted(range(len(events)), key=values.__getitem__)
            ranks = {old: new for new, old in enumerate(order)}
            return _json({"vertices": [attributes[index] for index in order],
                          "edges": sorted((ranks[a], ranks[b], label) for a, b, label in edges)})
        candidates = min(ambiguous)[2]
        representatives, results = [], []
        for index in candidates:
            if any(twins(index, prior) for prior in representatives):
                continue
            representatives.append(index)
            individualized = list(values)
            individualized[index] = max(values) + 1
            results.append(search(tuple(individualized), depth + 1))
        return min(results)

    return json.loads(search(initial))
