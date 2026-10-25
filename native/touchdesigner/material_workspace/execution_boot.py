"""Native project lifecycle; never silently resume a saved execution."""
def onStart():
    parent.Vocabulary.op('text_performance').module.startup()


def onCreate():
    parent.Vocabulary.op('text_performance').module.startup()


def onExit():
    parent.Vocabulary.op('text_performance').module.shutdown()
