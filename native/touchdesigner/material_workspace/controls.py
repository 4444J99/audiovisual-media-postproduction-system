"""Native source-bank controls; no edits outside this material workspace."""
def onValueChange(par, prev):
    workspace = parent.Materials
    owner = par.owner
    if owner == workspace:
        if par.name == 'Play' and par.eval(): root.time.play = True
        if par.name == 'Category':
            bank = workspace.op(str(par))
            choices = bank.fetch('asset_ids', [])
            workspace.par.Material.menuNames = choices
            workspace.par.Material.menuLabels = bank.fetch('asset_titles', [])
            if choices: workspace.par.Material = choices[0]
        if par.name in ('Category', 'Material'):
            target = workspace.op(str(workspace.par.Category)+'/'+str(workspace.par.Material))
            if target:
                previous = workspace.fetch('preview_asset', None)
                if previous and previous != target.path and op(previous):
                    old = op(previous); old.par.Preview = False
                    old.allowCooking = bool(old.par.Enabled)
                target.par.Preview = True
                target.allowCooking = True
                workspace.store('preview_asset', target.path)
    elif hasattr(owner.par, 'Enabled') and par.name in ('Enabled', 'Preview'):
        owner.allowCooking = bool(owner.par.Enabled or owner.par.Preview)
    if par.name == 'Play' and par.eval(): root.time.play = True
    return


def onPulse(par):
    return
