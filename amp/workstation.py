"""Editable REAPER audio and Fusion comparison projects; import review pending."""
from pathlib import Path
import shutil

from .core import write_json, probe
from .revision import retime_audio, timing_map


def export_workstation(recipe, config, clean, returns, videos, output):
    root=Path(output);root.mkdir(parents=True,exist_ok=True)
    fps=config['fps']; segments=timing_map(recipe,fps)
    for path,name in [(clean,'dialogue-source.wav'),(returns,'expressive-returns-source.wav')]:
        shutil.copyfile(path,root/name)
    rpp=['<REAPER_PROJECT 0.1 7.0 1','  SAMPLERATE 48000','  TEMPO 120']
    for name,file,gain in [('Dialogue','dialogue-source.wav',1),('Expressive returns','expressive-returns-source.wav',1)]:
        rpp.extend(['  <TRACK',f'    NAME "{name}"',f'    VOLPAN {gain} 0'])
        for s in segments:
            rpp.extend(['    <ITEM',f"      POSITION {s['output_start']:.12f}",
                        f"      LENGTH {s['output_end']-s['output_start']:.12f}",
                        f"      SOFFS {s['source_start']:.12f}",
                        f"      PLAYRATE {s['audio_speed']:.12f} 1 0 -1 0 0.0025",
                        '      VOLPAN 1 0 1 -1',f'      NAME "{name}: source {s["source_start"]:.3f}"',
                        '      <SOURCE WAVE',f'        FILE "{file}"','      >','    >'])
        rpp.append('  >')
    for i,s in enumerate(segments):
        rpp.append(f'  MARKER {i+1} {s["output_start"]:.12f} "source {s["source_start"]:.3f}; speed {s["audio_speed"]:.3f}"')
    rpp.append('>');(root/'god-here-directed-audio.rpp').write_text('\n'.join(rpp)+'\n')
    loaders=[]; names=[]
    for i,(name,path) in enumerate(videos.items()):
        target=root/Path(path).name;shutil.copyfile(path,target); node=f'Variant{i+1}';names.append(node)
        frames=int(next(s for s in probe(path)['streams'] if s['codec_type']=='video')['nb_frames'])
        loaders.append(f'''    {node} = Loader {{
      Clips = {{ Clip {{ ID = "Clip1", Filename = "{target.name}", FormatID = "QuickTimeMovies", Length = {frames} }} }},
      Inputs = {{ GlobalIn = Input {{ Value = 0 }}, GlobalOut = Input {{ Value = {frames-1} }} }},
      ViewInfo = OperatorInfo {{ Pos = {{ {i*180}, 0 }} }},
    }},''')
    loaders.append(f'''    SelectedEdition = MediaOut {{
      Inputs = {{ Input = Input {{ SourceOp = "{names[-1]}", Source = "Output" }} }},
      ViewInfo = OperatorInfo {{ Pos = {{ 180, 160 }} }},
    }},''')
    (root/'god-here-variant-review.comp').write_text('{ Tools = ordered() {\n'+'\n'.join(loaders)+'\n}, ActiveTool = "SelectedEdition" }\n')
    write_json(root/'editorial-time-map.json',{'fps':fps,'segments':segments,'recipe':recipe,
               'fusion_scope':'Editable media-backed comparison graph; region processing remains in Python sidecar, not falsely translated to native nodes',
               'reaper_scope':'Editable split items, source offsets, preserved-pitch playback rate, independent dialogue and return tracks',
               'native_import_status':'REAPER/Resolve unavailable here; application import and playback pending'})
    (root/'OPEN-FIRST.md').write_text('''# Editable workstation handoff

Open `god-here-directed-audio.rpp` in REAPER. Dialogue and expressive returns are separate tracks; items retain source offsets and rate changes. Solo, mute, trim, and adjust them independently. This is mixed recorded dialogue, not isolated actors. Route audio and set headroom before final export.

Open `god-here-variant-review.comp` in Fusion/Resolve. Relink local movie files if requested. Route a different Variant output to SelectedEdition to compare it. These media-backed branches preserve the rendered effects; the Python recipe is the editable authority for fields, typography, and tracking. Native compositing nodes for every Python operator have not been fabricated.

`editorial-time-map.json` records exact source/output timing. Native project syntax has been generated and structurally checked, but the applications are unavailable in this runtime; import, source-offset/rate interpretation, color management, and final sound levels require workstation review.
''')
    return root
