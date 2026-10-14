"""Explicit actions; selecting a source record never seeks or enables media."""
def onValueChange(par, prev):
    if par.name == 'View':
        n = parent.Navigator
        n.store('selected', {})
        n.par.Record = ''
        n.par.Detail = 'Select a row to inspect its evidence and available media.'
        n.par.Linked.menuNames = ['none']
        n.par.Linked.menuLabels = ['No supported media association']
        n.par.Linked = 'none'
    if par.name in ('View', 'Query', 'Person', 'Kind'):
        parent.Navigator.op('text_navigation').module.refresh()


def onPulse(par):
    module = parent.Navigator.op('text_navigation').module
    if par.name == 'Cuestart': module.cue()
    elif par.name == 'Cueend': module.cue(end=True)
    elif par.name == 'Cuestudy': module.cue_study()
    elif par.name == 'Openlink': module.open_link()
