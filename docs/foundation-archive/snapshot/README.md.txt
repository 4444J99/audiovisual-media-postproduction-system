# audiovisual-media-postproduction-system

A directable audiovisual postproduction system that translates creative notes into reproducible edits: audio restoration and design, dialogue and performance revision, animated typography, tracked reframing, detail reconstruction, compositing, and new editions from existing media.

**Status: foundation proposal. No audiovisual renderer, restored soundtrack, AI reconstruction, or finished new edition is implemented by this scaffold.** The included executable checks validate planning records, not media quality.

## Central workflow

Creative note -> intended change -> source targets -> proposed operations -> rendered alternatives -> review -> accepted revision.

Creative direction remains actionable after capture. A note can change the treatment of dialogue, delivery, gesture, reaction, framing, movement, typography, sound, or environment. Operations should work together rather than become unrelated effect demos.

## First-class responsibilities

| Responsibility | Scope |
|---|---|
| Audio | Repair, dialogue clarity, tonal and level consistency, ambience, spatial sound, and authored sound design. |
| Dialogue and performance | Pauses, overlaps, delivery, reactions, gesture timing, editorial relationships, and explicitly identified reconstruction. |
| Text and motion | Animated typography, titles, language as a visual element, and separately readable captions. |
| Virtual cinematography | Tracked faces, objects and movements; reframing, push-ins, stabilization, and temporally reviewed detail reconstruction. |
| Compositing | Masks, independent layers, scene changes, character-associated regions, and controlled interactions between them. |
| Direction and review | Structured feedback, alternative interpretations, source/output time maps, comparison, acceptance, and revision lineage. |
| Execution and editions | Reproducible processing, finishing, generative arrangements, and later interactive or installation outputs. |

`god-here` is the first creative project; *God's Ears* is its source work. The reusable system must not hardcode this project's five characters, two camera views, phrases, or visual treatment. Character-region distortion is one compositing capability, not the system's definition.

## Start here

- [Architecture and contracts](docs/architecture.md)
- [Concentric roadmap](docs/roadmap.md) and [machine-readable epic backlog](planning/epics.json)
- [god-here production brief and first proof](projects/god-here/README.md)
- [Revision-proposal schema](schemas/revision-proposal.schema.json) and [illustrative proposal](examples/revision-proposal.json)
- [Standards adoption record](docs/standards-adoption.md) and [agent instructions](AGENTS.md)

## Check the foundation

Python 3.11+ and the development dependency are needed for contract validation only:

```sh
python -m pip install -r requirements-dev.txt
python tools/validate_foundation.py
```

This checks the schema, example, planning dependencies, local documentation links, and negative cases. It does not execute media operations or certify an audiovisual result.

## Media and publication boundary

Keep source recordings, transcripts, performance notes, model weights, private storage locators, and rendered media out of public Git by default. Register authorized assets in a controlled manifest; publish specific materials only after an explicit decision. Generated or reconstructed detail must not be described as recovered historical fact.

No new shoot or new recording is a prerequisite for the planned workflow. Licensing of software, models, artwork, and source performances requires separate decisions. No license grant or model-provider connection is created by this foundation.
