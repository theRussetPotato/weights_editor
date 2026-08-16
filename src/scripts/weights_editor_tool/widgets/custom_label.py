from typing import Optional

from weights_editor_tool.qt import QtCore, QtGui, QtWidgets
from weights_editor_tool.widgets.instant_tooltip_dialog import InstantToolTipDialog


class CustomLabel(QtWidgets.QLabel):
    """
    An extension of QLabel that integrates with the InstantToolTipDialog.

    Standard QLabels do not always broadcast mouse events to their parents efficiently for custom tooltip logic.
    This subclass ensures that any text label in the UI can display a fast-response tooltip upon hovering.

    Args:
        text (str): The string to be displayed in the label.
        toolTip (str, optional): The message for the InstantToolTipDialog.
        parent (QWidget, optional): Parent widget for the label.
    """

    def __init__(self, text: str, toolTip: Optional[str] = None, parent: Optional[QtWidgets.QWidget] = None) -> None:
        """
        Initializes the label and enables mouse tracking if a tooltip is provided.
        """
        super().__init__(parent=parent)
        self._toolTip = toolTip
        self.setText(text)
        if toolTip is not None:
            self.setMouseTracking(True)

    def enterEvent(self, event: QtGui.QEnterEvent) -> None:
        """
        Signals the InstantToolTipDialog to appear with the stored tooltip text.
        """
        super().enterEvent(event)
        InstantToolTipDialog.mouseEnteringEvent(self, self._toolTip)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        """
        Updates the position of the InstantToolTipDialog to follow the cursor while over the label.
        """
        super().mouseMoveEvent(event)
        InstantToolTipDialog.mouseMovingEvent()

    def leaveEvent(self, event: QtCore.QEvent) -> None:
        """
        Signals the InstantToolTipDialog to hide when the mouse leaves the label's boundaries.
        """
        super().leaveEvent(event)
        InstantToolTipDialog.mouseLeavingEvent(self)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        """
        Ensures the tooltip is hidden if the user clicks on the label.
        """
        super().mousePressEvent(event)
        InstantToolTipDialog.mousePressingEvent()
