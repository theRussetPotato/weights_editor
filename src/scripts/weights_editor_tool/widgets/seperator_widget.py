from weights_editor_tool.qt import QtCore, QtGui, QtWidgets


class SeperatorWidget(QtWidgets.QFrame):
    """
    Creates a thin line to use as a seperator.
    """

    def __init__(self) -> None:
        """
        Initializes the view, configures custom headers, and sets up context menu actions.
        """
        super(SeperatorWidget, self).__init__()
        self.setObjectName("seperatorWidget")
        self.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        self.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
