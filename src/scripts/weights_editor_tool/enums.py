"""Enums used across the tool."""

class ColorTheme:
    Max = 0
    Maya = 1
    Softimage = 2
    MaximumInfluences = 3


class WeightOperation:
    Absolute = 0
    Relative = 1
    Percentage = 2


class SmoothOperation:
    PreserveInfs = 0
    AddInfs = 1
    Normal = 2
    AllInfluences = 3
