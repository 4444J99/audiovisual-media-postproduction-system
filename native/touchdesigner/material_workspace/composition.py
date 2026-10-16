"""Add an editable first composition without changing the material banks."""
import json
from pathlib import Path


def install(workspace, code_root, catalog_path):
    if workspace.op('base_composition'):
        raise ValueError('Composition already exists; preserve manual edits')
    namespace = {}
    exec((Path(code_root) / 'native/touchdesigner/material_workspace/build.py').read_text(encoding="utf-8"), namespace)
    custom = namespace['custom']
    bank = workspace.create('baseCOMP', 'base_composition')
    bank.par.parentshortcut = 'Composition'
    bank.nodeX, bank.nodeY = 0, 300
    custom(bank, 'Title', 'Str', 'Working composition · independent ingredients', readonly=True)
    catalog = json.loads(Path(catalog_path).read_text(encoding="utf-8"))
    metadata = {a['node_name']: a for a in catalog['assets']}
    requests = [
        ('base_room', 'track_room_tone_m4a_5548', 'track_room', .15, True),
        ('base_dialogue_audio', 'track_god_here_independent_time_player_html_voice_orig_b2ad', 'track_dialogue', 1, False),
        ('base_room', 'media_god_here_layer_study_03_package_provisional_room_23c8', 'layer_room_plate', 1, False),
    ]
    requests += [('base_foley', t.name, 'track_' + t.name.split('_m4a')[0][6:], .2, True)
                 for t in workspace.op('base_foley').children if hasattr(t.par, 'File')]
    requests += [('base_layers', t.name, 'layer_actor_' + str(t.par.Title).split('actor-mattes/')[1].split('/')[0], 1, True)
                 for t in workspace.op('base_layers').children
                 if hasattr(t.par, 'Title') and 'actor-mattes/' in str(t.par.Title)]
    entries = []
    for i, (source_bank, source_name, name, gain, enabled) in enumerate(requests):
        source = workspace.op(source_bank + '/' + source_name)
        track = bank.copy(source, name=name)
        track.nodeX, track.nodeY = (i % 3) * 350, -(i // 3) * 240
        track.par.Enabled = enabled
        track.par.Preview = False
        track.par.Play = False
        track.par.Gain = gain
        track.par.Mute = False
        track.par.Solo = False
        track.par.Pan = 0
        track.par.Clock = 'source' if name != 'track_dialogue' else 'local'
        duration = metadata[source_name].get('duration', 0)
        if str(track.par.Kind) == 'sequence':
            duration = metadata[source_name].get('frames', 90) / float(track.par.Framerate)
        custom(track, 'Duration', 'Float', duration, readonly=True)
        custom(track, 'Alignment', 'Str',
               'Unresolved; audition independently' if name == 'track_dialogue' else
               'Recovered source interval' if name.startswith('layer_actor') else
               'Full-length source-clock material' if name.startswith('track_') else
               'Provisional plate; optional', readonly=True)
        if track.op('null_picture'):
            custom(track, 'Layerorder', 'Int', i, label='Layer order (higher is in front)')
            track.op('level_opacity').par.opacity.expr = (
                'parent.Track.par.Opacity if parent.Track.par.Enabled and '
                '(parent.Track.par.Kind != "sequence" or parent.Track.par.Clock != "source" or '
                '0 <= (parent.Materials.par.Time-parent.Track.par.Sourceoffset)*parent.Track.par.Speed+'
                'parent.Track.par.Offset < parent.Track.par.Duration) else 0')
        media = track.op('audiofile_material') or track.op('movie_material')
        if media is not None and name != 'layer_room_plate':
            media.par.index.expr = (
                'max(0,(parent.Materials.par.Time-parent.Track.par.Sourceoffset)*'
                'parent.Track.par.Speed+parent.Track.par.Offset)*parent.Track.par.' +
                ('Samplerate' if str(track.par.Kind) == 'audio' else 'Framerate'))
            if str(track.par.Kind) == 'sequence':
                media.par.play.expr = "True if parent.Track.par.Clock == 'source' else parent.Track.par.Play"
                media.par.reloadpulse.pulse()
                selected = track.create('selectTOP', 'select_footage')
                selected.nodeX, selected.nodeY = 175, 210
                selected.par.top.expr = (
                    "parent.Materials.op('base_original/media_original_film_paired_camera_soundtrack_41f8/movie_material') "
                    "if parent.Track.par.Clock == 'source' and parent.Track.par.Speed == 1 "
                    "and parent.Track.par.Offset == 0 else op('movie_footage')")
                track.op('glsl_cutout').inputConnectors[0].connect(selected.outputConnectors[0])
        track.allowCooking = enabled
        entries.append(track)
    bank.store('asset_ids', [t.name for t in entries])
    bank.store('asset_titles', [t.name.replace('_', ' ') for t in entries])
    workspace.par.Category.menuNames = ['base_composition'] + list(workspace.par.Category.menuNames)
    workspace.par.Category.menuLabels = ['00 · Working composition'] + list(workspace.par.Category.menuLabels)
    workspace.par.Program.menuNames = ['original', 'selected', 'composition']
    workspace.par.Program.menuLabels = ['Untreated original', 'Selected material', 'Working composition']
    workspace.par.Category = 'base_composition'
    workspace.par.Material = entries[0].name
    workspace.par.Program = 'composition'
    workspace.par.Status = 'Working composition · source-aligned layers; dialogue alignment remains open'
    original = op(workspace.fetch('original'))
    original.op('movie_material').par.play.expr = 'parent.Materials.par.Play'
    original.op('movie_material').par.play.mode = ParMode.EXPRESSION
    original_relative = original.path[len(workspace.path)+1:] + '/null_picture'
    workspace.op('select_program').par.top.expr = (
        "parent.Materials.op('null_composition') if parent.Materials.par.Program == 'composition' else "
        "(parent.Materials.op(str(parent.Materials.par.Category)+'/'+str(parent.Materials.par.Material)+'/null_picture') "
        "or parent.Materials.op('" + original_relative + "')) if parent.Materials.par.Program == 'selected' "
        "else parent.Materials.op('" + original_relative + "')")
    composite = workspace.op('composite_layers')
    composite.par.tops.expr = (
        "' '.join('base_composition/'+t.name+'/null_picture' for t in sorted("
        "[t for t in parent.Materials.op('base_composition').children if t.isCOMP and hasattr(t.par,'Layerorder')], "
        "key=lambda t: int(t.par.Layerorder), reverse=True) if t.par.Enabled) + ' " + original_relative + "'")
    workspace.par.Cuepoint = 70
    workspace.par.Cue.pulse()
    return bank
