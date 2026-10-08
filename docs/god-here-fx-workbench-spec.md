# god-here — audiovisual FX workbench specification

October 8, 2026

Status: proposed module and patch specification. No new module runtime, media render, or integrated workbench is claimed by this document.

## Artistic requirement

Experiments must present stark, immediately perceptible changes. Design a rack of audiovisual effects with reusable controls and extreme demonstration presets. Subtle dramatic editing remains an available parameter range; it is not the default demonstration.

The earlier 84-variation atlas remains a library of possible meanings and relationships. This specification turns those possibilities into modules that can be instantiated, routed, modulated, automated, combined, and rendered.

A default demonstration must establish what the module does even without an explanatory note. High intensity means a large structural or perceptual change, not merely increased playback loudness.

The original/restored dialogue reference remains separately accessible. Expressive processing can be fully wet. A readable reference does not require every radical candidate to keep an intelligible dry voice mixed underneath.

## 1. Common module controls

Every instance exposes:

| Control | Responsibility |
|---|---|
| Bypass | Remove the instance from the processed path using explicit timing/latency behavior |
| Wet/dry | Compare and blend affected and unaffected branches |
| Target | Full frame, authored region, usable body/object layer, voice excerpt, text, room, or group |
| Intensity | Preset-defined macro that moves multiple relevant parameters into an unmistakable state |
| Timing | Start, end, onset, release, buffer boundaries, and source/output time map |
| Modulation | Keyframes, LFO/envelope, checked phrase cues, authored gestures, or other parameter sources |
| Routing | Input source, destination, bus, sidechain, send, and return where relevant |
| Seed/state | Retain stochastic choices and buffer/queue initial state |
| Solo/A-B | Hear/see an instance independently and compare against a reference |
| Preset | Named parameter configuration, including an extreme demonstration |

Not every module accepts every input type. Declare supported ports. An audio gate and a picture gate share an artistic control but process different data. Unsupported targets must remain explicit.

Voice, body, typography, and room may use independent source-time functions while sharing one output clock. When a body is retimed, its matte follows the same body source time. Caption timing and semantic-event timing require explicit mapping after editorial changes.

Neutral state, dry/wet blend, and latency behavior must be defined for each operator. Deliberate delay must not be cancelled automatically as accidental latency.

## 2. Initial thirteen-module rack

### FX-01 — Routing

Dominant operation: move a message between addresses.

Inputs: checked voice excerpts, image/word traces, region addresses.
Controls: origin, destination, travel time, path, copies, spread, arrival behavior.
Extreme demonstration: a voice and enormous word trace visibly cross the entire canvas, hit another territory, and scatter or reroute.
Variants: direct delivery, wrong recipient, broadcast, self-return, room recipient, offscreen destination.
Implementation shape: audio route/pan automation plus a corresponding authored path for visual/text material. Sound direction alone is insufficient for the default visible demonstration.

### FX-02 — Delay / Echo

Dominant operation: create distinctly displaced copies in time.

Inputs: audio and image/layer buffers; optional text/gesture history.
Controls: delay, taps, decay, temporal spread, copy scale, stereo/spatial spread.
Extreme demonstration: several large, separately timed bodies/frames or regions coexist while clearly separated phrase copies answer one another.
Variants: evenly spaced echoes, irregular taps, ping-pong destinations, nested delays, text surviving longer than image.
Implementation shape: finite taps with separate source-time offsets. Retain independently configurable audio and visual decay.

### FX-03 — Stutter

Dominant operation: capture and repeat a sharply bounded interval.

Inputs: phrase, word, gesture, frame region, or combined interval.
Controls: buffer length, repetition rate, repetition count, direction, gap, release.
Extreme demonstration: one audible word fragment and one conspicuous bodily movement hammer repeatedly, then abruptly release into the continuing scene.
Variants: word stutter, gesture stutter, picture-only stutter, staggered audio/picture, alternating captured intervals.
Implementation shape: checked source selection plus explicit repetition/time map. Editing boundaries remain distinct from automatically recognized word timings.

### FX-04 — Granular Processing

Dominant operation: atomize material into many short units and reassemble it.

Inputs: speech fragments, cropped image pieces, text units, gesture intervals.
Controls: grain size, density, source scatter, pitch/speed range, spatial scatter, ordering.
Extreme demonstration: the phrase and corresponding visual territory break into a dense cloud of scattered fragments, then reorganize.
Variants: coarse syllables/large tiles, fine phonemes/small tiles, ordered fragments, shuffled fragments, fragments borrowed from several checked intervals.
Implementation shape: audio grains with envelopes; temporally/spatially sampled visual units. Sound and image granularity are linked by an authored rule, not assumed to be physically identical.

### FX-05 — Reverse

Dominant operation: reverse an explicitly selected relationship.

Inputs: audio/picture buffers, routing paths, event sequences.
Controls: mode, span, speed, forward/reverse mix, pivot, direction.
Extreme demonstration: a gesture visibly rewinds while another layer moves forward; a word/voice route shoots back into its source.
Variants: playback reversal, route reversal, event-order reversal, mixed forward/reverse layers, an attempted reset that leaves residue.
Implementation shape: separate modes. Reversing the spatial route does not require reversing intelligible speech.

### FX-06 — Freeze / Hold

Dominant operation: suspend one component while others continue.

Inputs: frame, usable layer, audio grain, word, region state.
Controls: capture moment, held target, duration, micro-motion, decay, release.
Extreme demonstration: one person becomes a clearly immobile cutout while the room/group continues; their held word or vocal grain persists independently.
Variants: frozen body, frozen room, frozen word, spectral/granular voice hold, staggered releases.
Implementation shape: direct frame holds for picture; a qualified granular/spectral method for sustained audio. An isolated sample is not assumed to create a musically useful sustained voice.
Dependency: clean plate/usable matte for independent body suspension; otherwise use a whole-region hold or openly collaged alternative.

### FX-07 — Feedback

Dominant operation: feed processed output back through its own effect.

Inputs: delay/transform returns, picture buffers, text histories.
Controls: return gain, delay, scale/rotation per pass, decay, threshold, reset.
Extreme demonstration: copies multiply into tunnels or spirals until they occupy the frame; sound returns build into an unmistakable repeating system.
Variants: shrinking tunnel, expanding invasion, rotational recurrence, accumulating word loops, long self-sustaining tail.
Implementation shape: bounded buffered feedback. Audio/sample/frame delays break instantaneous cycles; finite energy and explicit reset/release remain execution requirements.
Distinction: Delay creates scheduled copies; Feedback creates recursive copies changed by prior passes.

### FX-08 — Queue / Overflow

Dominant operation: collect distinct arrivals until capacity changes reception.

Inputs: checked phrase/image/text events with arrival timestamps.
Controls: capacity, arrival rate, release rate, priority, overflow destination, compression/density.
Extreme demonstration: messages pile into a visibly packed territory, then burst into another region or release as a rapid avalanche.
Variants: first-in/first-out, last-in/first-out, important line buried, oldest item displaced, acknowledgment clears one item.
Implementation shape: stateful event queue. It can produce sound/visual density without simply repeating the same buffer.
Distinction: Queue stores arrivals; Feedback recirculates its own previous output.

### FX-09 — Gate / Erase

Dominant operation: stop transmission or remove selected components.

Inputs: voice, region, body, typography, returns.
Controls: threshold/cue, open window, edge speed, removed component, tail retention, reopening.
Extreme demonstration: an entire character-associated layer or territory vanishes abruptly while the voice/gesture return remains conspicuous.
Variants: receiver unavailable, source erased, body stays/voice stops, address remains/body disappears, delayed reopening.
Implementation shape: independent gain/alpha/routing gates. Removal requires a background fill or an explicitly authored hole/collage; it does not implicitly reconstruct hidden scenery.

### FX-10 — Displacement / Deformation

Dominant operation: change geometry in a visible, controllable way.

Inputs: image/region/layer, modulation signal, displacement field.
Controls: magnitude, field scale, direction, frequency, coupling, boundary/spill.
Extreme demonstration: a character’s territory folds, stretches, tears, or flows across a large part of the canvas while neighboring territories remain identifiable.
Variants: radial collapse, sideways shear, wave propagation, elastic extension, turbulent room, displacement driven by selected voice.
Implementation shape: authored fields or procedural geometry. Apply relevant transforms consistently to layer alpha. Containment and deliberate spill are separate states.

### FX-11 — Voice / Body / Region Exchange

Dominant operation: exchange source ownership among visible addresses.

Inputs: independently addressable voice excerpts, body/region layers, source identity mappings.
Controls: permutation, swap pairs, transition, time offset, retained component, random seed.
Extreme demonstration: regions or usable body layers visibly trade positions while their voices remain behind; a second preset moves voices while bodies stay.
Variants: voice swap, region swap, gesture exchange, histories exchanged, cyclic ownership among all five addresses.
Implementation shape: explicit source-to-destination mapping. This is authored reassignment, not a claim that the performers spoke different lines.
Dependency: region/crop exchange can precede fine body extraction. Do not require plausible generated lip movement for an openly artificial exchange.

### FX-12 — Typography / Word Material

Dominant operation: turn language into large-scale visual matter.

Inputs: checked words, written-source phrases explicitly identified as such, font/layout assets.
Controls: size, repetition, fragmentation, persistence, aperture/fill, spatial attachment.
Extreme demonstration: a word fills the canvas, becomes an image aperture, breaks into many pieces, or physically blocks another territory.
Variants: enormous correction, repeated inbox wall, word after body, syllable particles, text on room surfaces, shape changing between how/why/what.
Implementation shape: standalone text layer plus masking/geometry/temporal controls. Expressive text and readable captions remain separate outputs.

### FX-13 — Signal Damage / Bitcrush

Dominant operation: deliberately reduce signal resolution and distort its representation.

Inputs: audio, image, selected region, optional text raster.
Controls: audio quantization, sample-rate reduction, visual block size, tonal levels, drive, bandwidth.
Extreme demonstration: picture becomes a coarse two-tone mosaic while speech becomes conspicuously quantized or restricted to a narrow resonant band.
Variants: coarse pixels/clear voice, damaged voice/clear picture, coupled resolution reduction, moving islands of clean signal, damaged text occupying the room.
Implementation shape: explicit quantization, reduction/filtering, and nonlinear processing with separate output-level control. Structural degradation and increased playback loudness are separate parameters.

## 3. Modular routing

Support serial chains, parallel branches, sends/returns, and sidechains.

Examples:
- Routing → Delay → Feedback: a message travels, produces echoes, then grows into a recursive return.
- Stutter → Granular → Reverse: captured speech/movement is hammered, atomized, and reassembled backward.
- Queue → Displacement → Gate: collected messages deform a territory until its reception closes.
- Freeze in one branch plus uninterrupted room in another: suspension becomes immediately visible.
- Voice/Body Exchange plus Typography: visible ownership changes while words expose the reassignment.

Module order changes the result. Stutter before Reverse is a different composition from Reverse before Stutter. Save ordered graphs, not just unordered lists of selected effects.

A source region can receive its own rack; shared buses can impose group behavior. The reusable engine accepts arbitrary target counts. god-here supplies the five-character arrangement as project configuration.

Sidechain sources may include authored envelopes, speech amplitude, checked phrase cues, and gesture curves. A sidechain can affect a different destination than its source. Separate automatic measurement from the artistic mapping assigned to it.

## 4. Default stark patches

### Patch A — Message impact

Routing → Delay → Displacement, with Typography on a parallel branch.
A giant phrase travels across the frame, lands in another territory, creates several delayed copies, and visibly buckles the receiving space.
Macro: Impact controls visual scale, deformation depth, copy density, and envelope. Sound level is independently managed.

### Patch B — Closed inbox

Queue → Feedback → Gate.
Distinct arrivals pack a region. Recurrence builds. The region closes abruptly, but prior returns keep spreading outside it.
Macro: Capacity crisis controls queue capacity/release, recursive return, and gate timing.

### Patch C — Out, but still here

Gate on the body/region branch; Delay/Freeze on gesture, word, and voice branches.
The person visibly disappears. A large gesture fragment and word remain; a voice repeats from the empty address.
Macro: Persistence controls which components survive and how long.

### Patch D — Correction machine

Stutter on how/why/what → Typography → Voice/Body/Region Exchange.
Questions become strongly repeated units. Huge words replace one another. Regions or voices trade ownership at each correction.
Macro: Authority cycles control targets, timing, and size.

### Patch E — Fractured utterance

Stutter → Granular → Reverse → Freeze.
A phrase and associated picture fracture into short units; some run backward; one residual unit becomes held matter.
Macro: Fragmentation controls unit size, density, scatter, and held residue.

### Patch F — Room takeover

Routing to room → Displacement → Feedback; body treatment bypassed initially.
The room bends and recursively fills with incoming image/word traces while bodies remain visible anchors where feasible.
Macro: Takeover controls spread, field magnitude, recursive scale, and persistence.

These are creative presets without verified source intervals. They are not completed media outputs.

## 5. Workbench surface

Use a dominant full-canvas preview plus an FX rack that can be shown or hidden. The artwork preview is the space where the effect’s behavior is assessed.

The rack exposes:
- ordered module cards with bypass, target, wet/dry, Intensity, and expanded controls;
- drag/reorder or another explicit ordering mechanism;
- sends/returns and source/destination selection;
- solo and A/B comparison;
- preset switching without losing the current custom state;
- parameter automation and macro assignment;
- export/import of the patch/score.

Preview and offline render use the same parameter meanings and time maps. Document approximations when a preview backend cannot reproduce an offline operation.

Target positions, travel paths, field extents, and text size should use normalized composition coordinates or explicit region-local coordinates. Horizontal and vertical layouts can therefore supply different arrangements without reducing a module’s visible magnitude to tiny pixel values.

## 6. Default demonstration and review

Each module’s first demonstration should be full-screen, soloed, and set to a deliberately strong preset. Show the unchanged source briefly, switch the effect clearly on, exercise a control, and return to bypass.

Assess:
1. Is the change unmistakable without explanatory text?
2. Can a viewer identify its dominant behavior?
3. Does changing a control produce a clear, repeatable difference?
4. Does bypass remove the operation using the declared timing behavior?
5. Does the module still work in an ordered chain and on a shared bus?
6. Does the saved patch reproduce its source selections, parameter changes, and stochastic choices?

Perceptual review is required; parameter values and image metrics alone cannot prove the effect is obvious.

Start with region/full-frame versions where bodies are not yet cleanly separated. Use body, object, shadow, and reflection layers as qualified inputs when they become available. Learned processing may supply inputs; it is not a prerequisite for every procedural effect.

## 7. Integration handoff

This document supplies proposed modules, parameters, and stark presets for the agents implementing the workbench. It does not modify their code or claim that the current repository has these operators.

The earlier variation IDs can become preset tags:
- TR → Routing, Delay, Displacement.
- RV → Reverse, Exchange.
- IN → Queue, Feedback, Typography.
- OF → Gate, Queue, Routing.
- OU → Gate, Freeze, Delay.
- SP → Stutter, Granular, Reverse, Typography.
- DR → arbitrary authored rack/automation patches.

Keep artistic relationships as selectable compositions. Build the reusable effect systems as the workbench’s instruments.

