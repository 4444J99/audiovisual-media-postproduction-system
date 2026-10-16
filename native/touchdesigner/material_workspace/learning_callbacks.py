"""Native event forwarding; guide behavior has one source module."""


def onPulse(par):
    parent.Learn.op('text_learning').module.onPulse(par)


def onValueChange(par, prev):
    parent.Learn.op('text_learning').module.onValueChange(par, prev)
