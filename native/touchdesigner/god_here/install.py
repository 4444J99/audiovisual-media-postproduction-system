"""Rebuild the native comparison inside TouchDesigner, without replacing any OP.

Textport: exec(open(PATH_TO_THIS_FILE).read(), {"__file__": PATH_TO_THIS_FILE})
Then: build(source_file=YOUR_REGISTERED_SOURCE_PATH)
"""
import hashlib
import json
from pathlib import Path
import re


def build(source_file, parent_path="/project1", name="base_godhere_compare", code_root=None):
    repo = Path(code_root) if code_root else Path(__file__).resolve().parents[3]
    recipe = json.loads((repo / "native/touchdesigner/god_here/network.json").read_text(encoding="utf-8"))
    source = Path(source_file)
    if not source.is_absolute():
        source = Path(project.folder) / source
    expected = json.loads((repo / "web/fx/fixtures/message-impact.json").read_text(encoding="utf-8"))["source"]["sha256"]
    if hashlib.sha256(source.read_bytes()).hexdigest() != expected:
        raise ValueError("Source identity does not match the authored Message impact patch")
    parent_op = op(parent_path)
    if parent_op.op(name):
        raise ValueError("Destination exists; preserve it and choose an unused component name")
    c = parent_op.create(baseCOMP, name)
    c.par.parentshortcut = "GodhereCompare"
    page = c.appendCustomPage("Comparison")
    for definition in recipe["custom"]:
        kw = {"label": definition["label"]}
        p = getattr(page, "append" + definition["style"])(definition["name"], **kw)[0]
        if definition["style"] == "Menu":
            p.menuNames = definition["menuNames"]
            p.menuLabels = definition["menuLabels"]
        p.min, p.max = definition["min"], definition["max"]
        p.clampMin, p.clampMax = definition["clampMin"], definition["clampMax"]
        if definition["style"] != "Pulse":
            p.val = definition["value"]
    c.par.Sourcefile = str(source)
    c.par.Play = False
    c.par.Monitor = False
    # Create all targets before resolving any expression or DAT path.
    for node in recipe["nodes"]:
        n = c.op(node["name"]) or c.create(node["type"], node["name"])
        n.nodeX, n.nodeY = node["position"]
        n.viewer = True
        if node["type"] in ("executeDAT", "parameterexecuteDAT"):
            n.par.active = False
    for name, relative in recipe["bindings"].items():
        n = c.op(name)
        n.par.file = str(repo / relative)
        n.par.syncfile = True
        n.par.loadonstartpulse.pulse()
    for node in recipe["nodes"]:
        n = c.op(node["name"])
        indices = [int(m.group(1)) for key in node["pars"] if (m := re.match(r"vec(\d+)", key))]
        if indices:
            n.seq.vec.numBlocks = max(indices) + 1
        for key, value in node["pars"].items():
            if key in ("pageindex", "active") and node["type"] in ("executeDAT", "parameterexecuteDAT"):
                continue
            p = getattr(n.par, key)
            if isinstance(value, dict) and "expr" in value:
                p.expr = value["expr"]
            else:
                p.val = value
        for connection in node["inputs"]:
            n.inputConnectors[connection["index"]].connect(c.op(connection["from"]).outputConnectors[0])
    for definition in recipe["custom"]:
        p = getattr(c.par, definition["name"])
        if definition["expr"]:
            p.expr = definition["expr"]
        p.readOnly = definition["readOnly"]
    for n in list(c.children):
        if n.name.endswith("_compute") or n.name == "script_audio_callbacks":
            n.destroy()  # Only generated unused stubs inside this newly created component.
    for box in recipe.get("annotations", []):
        a = c.create(annotateCOMP)
        a.par.Titletext = box["title"]
        a.nodeX, a.nodeY = box["position"]
        a.nodeWidth, a.nodeHeight = box["size"]
    c.par.Play = False
    c.par.Monitor = False
    c.par.Mode = "expression"
    c.par.Reviewrange = "patch"
    c.par.Cuepoint = 95
    c.par.opviewer = "./null_comparison"
    c.display = True
    c.viewer = True
    c.op("execute_capture").par.active = True
    c.op("parexec_controls").par.active = True
    c.par.Cue.pulse()
    return c
