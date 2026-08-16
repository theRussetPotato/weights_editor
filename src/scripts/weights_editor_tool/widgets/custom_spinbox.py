from typing import Optional, Callable

from weights_editor_tool.qt import QtCore, QtGui, QtWidgets
from weights_editor_tool.widgets.instant_tooltip_dialog import InstantToolTipDialog
from weights_editor_tool import weights_editor_utils as utils


class CustomSpinBoxLineEdit(QtWidgets.QLineEdit):
    """
    A line edit specifically for the CustomSpinBox, to replace its default line edit with.
    This exposes the instant tool tip to better track the mouse.

    Args:
        toolTip (str): The message for the InstantToolTipDialog.
        parent (QWidget, optional): Parent widget for the button.
    """

    def __init__(self, toolTip: str, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent=parent)
        self._toolTip = toolTip

    def enterEvent(self, event: QtGui.QEnterEvent) -> None:
        """Triggers the InstantToolTipDialog when the mouse hovers over."""
        super().enterEvent(event)
        InstantToolTipDialog.mouseEnteringEvent(self, self._toolTip)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        """Updates the InstantToolTipDialog position to follow the cursor."""
        super().mouseMoveEvent(event)
        InstantToolTipDialog.mouseMovingEvent()

    def leaveEvent(self, event: QtCore.QEvent) -> None:
        """Hides the InstantToolTipDialog when the mouse exits the button area."""
        super().leaveEvent(event)
        InstantToolTipDialog.mouseLeavingEvent(self)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        """Dismisses the InstantToolTipDialog immediately upon clicking."""
        super().mousePressEvent(event)
        InstantToolTipDialog.mousePressingEvent()


class CustomSpinBox(QtWidgets.QSpinBox):
    """
    A spinbox that supports custom the InstantToolTipDialog.

    Args:
        value (int): The initial value.
        minValue (int, optional): The spinbox's minimum value.
        maxValue (int, optional): The spinbox's maximum value.
        toolTip (str, optional): The message for the InstantToolTipDialog.
        label (QLabel, optional): A label that's paired with this.
        minimumWidth (int): Minimum width constraint.
        valueChangedEvent (Callable, optional): Function to call when the value changes.
        parent (QWidget, optional): Parent widget for the button.
    """

    def __init__(
            self,
            value: int,
            minValue: Optional[int] = None,
            maxValue: Optional[int] = None,
            toolTip: Optional[str] = None,
            label: Optional[QtWidgets.QLabel] = None,
            minimumWidth : int = 60,
            valueChangedEvent: Optional[Callable] = None,
            parent: QtWidgets.QWidget = None) -> None:
        super().__init__(parent=parent)

        self._lineEdit = CustomSpinBoxLineEdit(toolTip, parent=self)
        self._toolTip = toolTip
        self._label = None

        self.setMinimumWidth(minimumWidth)
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        self.setLineEdit(self._lineEdit)
        self.setValue(value)

        if minValue is not None:
            self.setMinimum(minValue)

        if maxValue is not None:
            self.setMaximum(maxValue)

        if toolTip is not None:
            self.setMouseTracking(True)
            self._lineEdit.setMouseTracking(True)

        if label is not None:
            self._label = label

        if valueChangedEvent is not None:
            self.valueChanged.connect(valueChangedEvent)

    def enableCompactMode(self) -> None:
        if self._label is not None:
            self._label.setHidden(True)

    def disableCompactMode(self) -> None:
        if self._label is not None:
            self._label.setVisible(True)
