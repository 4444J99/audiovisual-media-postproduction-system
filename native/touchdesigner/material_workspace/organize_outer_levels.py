"""Label the session and project entry levels without changing operator paths."""

GROUPS = [
    ('/', 'annotate_composition', '01 Composition', [.22, .33, .22],
     'Open project1, then the workspace, to compose.\nperform displays the same project in a presentation window.',
     [('project1', 25, 0, 500, 300, 'Composition project: open to reach the material workspace.'),
      ('perform', 625, 0, 300, 300, 'Presentation window displaying /project1.')]),
    ('/', 'annotate_connections', '02 Tool connections', [.25, .28, .35],
     'Live assistance: TDMCP and TD Atlas.\nKeep these connections available.',
     [('TDMCP', 25, -550, 300, 170, 'TouchDesigner MCP connection.'),
      ('tdatlas', 400, -550, 300, 170, 'TD Atlas live inspection and editing bridge.')]),
    ('/', 'annotate_settings', '03 Settings', [.30, .22, .33],
     'Project variables and\nlocal settings.',
     [('local', 825, -550, 300, 170, 'TouchDesigner project variables and local settings.')]),
    ('/project1', 'annotate_workspace', '01 Start here', [.22, .33, .22],
     'Open this workspace for sources, tracks, framing, effects, text and sound.\nThe source banks and working areas are labeled inside.',
     [('container_godhere_workspace', 25, 0, 725, 350,
       'Current material and composition workspace. Open to begin.')]),
    ('/project1', 'annotate_history', '02 Earlier studies', [.35, .30, .18],
     'Left: first source player. Right: comparison experiment.\nBoth were already disabled; retained as development history.',
     [('base_godhere', 25, -500, 300, 150, 'Earlier source player: original picture and paired audio.'),
      ('base_godhere_compare', 400, -500, 350, 150, 'Earlier Message-impact comparison experiment.')]),
]


def arrange(session_root):
    """Return annotation requests after applying only geometry and comments."""
    resolved = []
    for parent, name, title, color, text, entries in GROUPS:
        container = session_root.op(parent)
        nodes = [container.op(entry[0]) for entry in entries]
        if any(node is None for node in nodes):
            raise ValueError('Expected entry-level component missing in ' + parent)
        resolved.append((parent, name, title, color, text, entries, nodes))
    annotations = []
    for parent, name, title, color, text, entries, nodes in resolved:
        for node, (_, x, y, width, height, comment) in zip(nodes, entries):
            node.nodeX, node.nodeY = x, y
            node.nodeWidth, node.nodeHeight = width, height
            node.comment = comment
        left = min(n.nodeX for n in nodes) - 25
        bottom = min(n.nodeY for n in nodes) - 25
        right = max(n.nodeX + n.nodeWidth for n in nodes) + 25
        top = max(n.nodeY + n.nodeHeight for n in nodes) + 180
        annotations.append(dict(parent=parent, name=name, title=title,
                                text=text, color=color, font_size=20,
                                position=[left, bottom], size=[right-left, top-bottom],
                                nodes=[n.name for n in nodes]))
    return annotations


def verify(session_root, groups):
    """Check actual annotation containment and separation on both levels."""
    errors = []
    boxes = []
    for group in groups:
        container = session_root.op(group['parent'])
        box = container.op(group['name'])
        if box is None:
            errors.append('Missing annotation: ' + group['name'])
            continue
        boxes.append(box)
        for name in group['nodes']:
            node = container.op(name)
            if not (node.nodeX >= box.nodeX + 25
                    and node.nodeX + node.nodeWidth <= box.nodeX + box.nodeWidth - 25
                    and node.nodeY >= box.nodeY + 25
                    and node.nodeY + node.nodeHeight <= box.nodeY + box.nodeHeight - 180):
                errors.append('Containment: ' + node.path)
    for index, a in enumerate(boxes):
        for b in boxes[index+1:]:
            if a.parent() != b.parent():
                continue
            if not (a.nodeX + a.nodeWidth + 20 <= b.nodeX
                    or b.nodeX + b.nodeWidth + 20 <= a.nodeX
                    or a.nodeY + a.nodeHeight + 20 <= b.nodeY
                    or b.nodeY + b.nodeHeight + 20 <= a.nodeY):
                errors.append('Overlap: ' + a.path + ' / ' + b.path)
    return errors
