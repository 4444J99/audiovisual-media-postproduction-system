"""External callback for the installed native palette lister."""
def onSelectRow(info):
    row = info.get('rowData', {})
    event_id = row.get('ID')
    if event_id:
        parent.Navigator.op('text_navigation').module.select(str(event_id))
