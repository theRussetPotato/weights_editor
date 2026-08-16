from weights_editor_tool.qt import QtCore, QtGui, QtWidgets
from weights_editor_tool.classes.hotkey import Hotkey


class HotkeyEdit(QtWidgets.QLineEdit):
    """
    A specialized input for capturing and displaying hotkey combinations.
    """

    keyPressed = QtCore.Signal(QtWidgets.QLineEdit, QtGui.QKeyEvent)

    def __init__(
            self,
            hotkeySettingsKey: str,
            hotkey: Hotkey,
            parent: QtWidgets.QWidget = None) -> None:
        """
        Initializes the edit with the current hotkey object's string representation.

        Args:
            hotkeySettingsKey (str): The dictionary key for this hotkey in settings.
            hotkey (Hotkey): The hotkey data object to manage.
            parent (QWidget, optional): Parent widget.
        """
        self.hotkeySettingsKey = hotkeySettingsKey
        self.hotkey = hotkey
        QtWidgets.QLineEdit.__init__(self, self.hotkey.keyToString(), parent=parent)

    def keyPressEvent(self, keyEvent: QtGui.QKeyEvent) -> None:
        """
        Intercepts key presses to serialize modifier keys and the primary key code.
        Updates the internal hotkey object and the displayed text.

        Args:
            keyEvent (QKeyEvent): The raw key event from the keyboard.
        """
        # Exit if only a modifier key is pressed.
        keyCode = keyEvent.key()
        modifierKeys = [QtCore.Qt.Key_Control, QtCore.Qt.Key_Shift, QtCore.Qt.Key_Alt]
        if keyCode in modifierKeys:
            return

        newHotkey = Hotkey.serializeKeyEvent(keyEvent)
        #if not keyEvent.text():
            #return

        keyValues = Hotkey.serializeKeyEvent(keyEvent)

        self.hotkey.shift = keyValues["shift"]
        self.hotkey.ctrl = keyValues["ctrl"]
        self.hotkey.alt = keyValues["alt"]
        self.hotkey.key = keyValues["key"]

        self.setText(self.hotkey.keyToString())

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        """
        Automatically selects all text on click to facilitate quick overwriting.

        Args:
            event (QMouseEvent): The mouse click event.
        """
        self.selectAll()
