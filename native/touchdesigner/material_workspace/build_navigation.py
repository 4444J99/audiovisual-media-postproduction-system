"""Add the native source panel using TouchDesigner's installed palette lister."""
import hashlib
from pathlib import Path


def build(workspace, code_root, palette_tox):
    if workspace.op('container_source_navigation'):
        raise ValueError('Navigation exists; preserve manual edits')
    code = Path(code_root) / 'native/touchdesigner/material_workspace'
    namespace = {}
    exec((code / 'build.py').read_text(encoding='utf-8'), namespace)
    node = namespace['node']
    n = node(workspace, 'containerCOMP', 'container_source_navigation', 1500, 650,
             w=1360, h=900, parentshortcut='Navigator')
    bundle = n.loadTox(str(palette_tox))
    n.copy(bundle.op('listerConfig'), name='listerConfig')
    lister = n.copy(bundle.op('lister'), name='list_records')
    lister.par.callbacks='./internalCallbacks'
    lister.par.ext0object='op("./ListerExt").module.ListerExt(me)'
    lister.par.ext0promote=True;lister.par.parentshortcut='Lister'
    lister.par.Configcomp.expr="me.parent().op('listerConfig')"
    lister.par.reinitextensions.pulse()
    bundle.destroy()
    for i, name in enumerate(['table_records','table_visible','table_gaps','table_voice_study']):
        node(n,'tableDAT',name,i*175,-250)
    node(n,'textDAT','text_navigation',0,-450,language='python',file=str(code/'navigation.py'),syncfile=True)
    node(n,'parameterexecuteDAT','parexec_navigation',175,-450,active=False,language='python')
    for i,name in enumerate(['parameter_filters','parameter_record','parameter_transport','parameter_sound','parameter_picture']):
        node(n,'parameterCOMP',name,i*175,250,builtin=False,custom=True)
    node(n,'containerCOMP','container_program',900,0)
    evidence=node(n,'containerCOMP','container_evidence',350,-650,x=335,y=0,w=355,h=145,pvscrollbar='auto')
    node(evidence,'textCOMP','text_evidence',0,0)
    original=op(workspace.fetch('original'))
    digest=hashlib.sha256()
    with open(str(original.par.File),'rb') as media:
        for block in iter(lambda:media.read(1024*1024),b''):digest.update(block)
    result=n.op('text_navigation').module.install(workspace,code_root,digest.hexdigest())
    n.op('text_navigation').module.refresh()
    return result
