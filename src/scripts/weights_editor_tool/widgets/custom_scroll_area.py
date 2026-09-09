from weights_editor_tool.qt import QtCore, QtWidgets


class CustomScrollArea(QtWidgets.QScrollArea):
    """
    A specialized QScrollArea that enforces a preferred height.
    """
    def __init__(self, parent: QtWidgets.QWidget = None) -> None:
        super().__init__(parent=parent)
