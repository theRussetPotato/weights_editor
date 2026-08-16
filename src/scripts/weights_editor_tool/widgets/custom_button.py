from typing import Optional, Callable

from weights_editor_tool.qt import QtCore, QtGui, QtWidgets
from weights_editor_tool.widgets.instant_tooltip_dialog import InstantToolTipDialog
from weights_editor_tool import weights_editor_utils as utils


class CustomButton(QtWidgets.QPushButton):
    """
    An enhanced QPushButton that manages dual states, icons, and custom tooltips.

    This widget automates the switching of text and icons when toggled, integrates with the InstantToolTipDialog
    for snappier help text, and supports a 'Compact Mode' for space-saving layouts.

    Args:
        text (str): The default label for the button.
        icon (QPixmap, optional): The default icon.
        pressedIcon (QPixmap, optional): Icon to display when checked/active.
        pressedText (str, optional): Text to display when checked/active.
        iconSize (QSize, optional): The dimensions for the icon. Defaults to 13x13.
        toolTip (str, optional): The message for the InstantToolTipDialog.
        checkable (bool): If True, the button becomes a toggle switch.
        clickEvent (Callable, optional): Function to call on click.
        minimumWidth (int): Minimum width constraint. Defaults to 25.
        supportCompactMode (bool): Whether the button can hide its text in small layouts.
        parent (QWidget, optional): Parent widget for the button.
    """

    def __init__(
            self,
            text: str,
            icon: Optional[QtGui.QPixmap] = None,
            pressedIcon: Optional[QtGui.QPixmap] = None,
            pressedText: Optional[str] = None,
            iconSize: Optional[QtCore.QSize] = None,
            toolTip: Optional[str] = None,
            checkable: bool = False,
            clickEvent: Optional[Callable] = None,
            minimumWidth : int = 25,
            supportCompactMode: bool = True,
            parent: QtWidgets.QWidget = None) -> None:
        """
        Initializes the button and configures icons, signals, and mouse tracking.
        """
        super().__init__(parent=parent)

        if iconSize is None:
            iconSize = QtCore.QSize(13, 13)

        self._buttonText = text
        self._supportCompactMode = supportCompactMode
        self._inCompactMode = False
        self.pressedText = pressedText
        self.normalIcon = icon
        self.pressedIcon = pressedIcon
        self._toolTip = toolTip

        if checkable:
            self.setCheckable(checkable)
            self.toggled.connect(self._onToggled)

        self.setText(text)
        self.setAttribute(QtCore.Qt.WA_StyledBackground)
        self.setIconSize(iconSize)
        self.setMinimumWidth(minimumWidth)
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)

        if icon is not None:
            self.setIcon(utils.loadPixmap(icon))

        if toolTip is not None:
            self.setMouseTracking(True)

        if clickEvent is not None:
            self.clicked.connect(clickEvent)

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

    def updateText(self, text: str) -> None:
        """
        Updates the internal default text and refreshes the button's label.

        Args:
            text (str): The new label string.
        """
        self._buttonText = text
        self.setText(text)

    def enableCompactMode(self) -> None:
        """
        Hides the button text to save space if compact mode is supported.
        """
        if self._supportCompactMode:
            self._inCompactMode = True
            self.setText("")

    def disableCompactMode(self) -> None:
        """
        Restores the button text based on its current checked state.
        """
        if self._supportCompactMode:
            self._inCompactMode = False
            self._setTextByCheckedState()

    def _setTextByCheckedState(self) -> None:
        """Updates label text based on whether the button is toggled or not."""
        if self.isChecked():
            self.setText(self.pressedText)
        else:
            self.setText(self._buttonText)

    def _setIconByCheckedState(self) -> None:
        """Updates the icon based on whether the button is toggled or not."""
        if self.isChecked():
            self.setIcon(utils.loadPixmap(self.pressedIcon))
        else:
            self.setIcon(utils.loadPixmap(self.normalIcon))

    def _onToggled(self, *args) -> None:
        """
        Internal slot triggered when the button is checked or unchecked.
        Manages the visual transition of text and icons.
        """
        if not self._inCompactMode:
            self._setTextByCheckedState()

        if self.pressedIcon is not None:
            self._setIconByCheckedState()
