from typing import Callable, Any, Dict
from dataclasses import dataclass, field

from weights_editor_tool.qt import QtCore, QtGui
from weights_editor_tool import qt
from weights_editor_tool.dataclasses import HotkeyData


class Hotkey:
    """
    Represents a customizable keyboard shortcut within the tool.

    This class manages the mapping between a specific key combination
    (including modifiers like Ctrl, Shift, and Alt) and a target function.
    """

    def __init__(self, caption, key, func=None, ctrl=False, shift=False, alt=False):
        """
        Initializes a new Hotkey instance.

        Args:
            caption (str): A descriptive name for the hotkey action.
            key (int): The Qt Key code (e.g., QtCore.Qt.Key_P).
            func (Callable, optional): The function to execute when triggered.
            ctrl (bool): Whether the Control modifier is required.
            shift (bool): Whether the Shift modifier is required.
            alt (bool): Whether the Alt modifier is required.
        """
        self.caption = caption
        self.key = key
        self.func = func
        self.ctrl = ctrl
        self.shift = shift
        self.alt = alt

    @staticmethod
    def serializeKeyEvent(keyEvent: QtGui.QKeyEvent) -> dict[str, Any]:
        """
        Converts a raw QKeyEvent into a dictionary of modifier states and key codes.

        Args:
            keyEvent (QtGui.QKeyEvent): The event captured from a widget's keyPressEvent.

        Returns:
            A dictionary containing 'shift', 'ctrl', 'alt', and 'key'.
        """
        # This is annoying, but holding "shift" yields different keycodes which won't trigger properly.
        # For example, "shift + 1" will register as "shift + !" and won't trigger when pressing the keys.
        # As a workaround, numbers and symbols require mappings to map to the key before shift modifies it.
        shiftMappings = {
            QtCore.Qt.Key_Exclam: QtCore.Qt.Key_1,
            QtCore.Qt.Key_At: QtCore.Qt.Key_2,
            QtCore.Qt.Key_NumberSign: QtCore.Qt.Key_3,
            QtCore.Qt.Key_Dollar: QtCore.Qt.Key_4,
            QtCore.Qt.Key_Percent: QtCore.Qt.Key_5,
            QtCore.Qt.Key_AsciiCircum: QtCore.Qt.Key_6,
            QtCore.Qt.Key_Ampersand: QtCore.Qt.Key_7,
            QtCore.Qt.Key_Asterisk: QtCore.Qt.Key_8,
            QtCore.Qt.Key_ParenLeft: QtCore.Qt.Key_9,
            QtCore.Qt.Key_ParenRight: QtCore.Qt.Key_0,
            QtCore.Qt.Key_BraceLeft: QtCore.Qt.Key_BracketLeft,
            QtCore.Qt.Key_BraceRight: QtCore.Qt.Key_BracketRight,
            QtCore.Qt.Key_Colon: QtCore.Qt.Key_Semicolon,
            QtCore.Qt.Key_Question: QtCore.Qt.Key_Slash,
            QtCore.Qt.Key_QuoteDbl: QtCore.Qt.Key_Apostrophe,
            QtCore.Qt.Key_Greater: QtCore.Qt.Key_Period,
            QtCore.Qt.Key_Less: QtCore.Qt.Key_Comma,
            QtCore.Qt.Key_AsciiTilde: QtCore.Qt.Key_QuoteLeft,
            QtCore.Qt.Key_Underscore: QtCore.Qt.Key_Minus,
            QtCore.Qt.Key_Plus: QtCore.Qt.Key_Equal,
        }
        key = shiftMappings.get(keyEvent.key(), keyEvent.key())

        modifiers = keyEvent.modifiers()

        # Compatible for both PySide2 and PySide6.
        return {
            "shift": (modifiers & QtCore.Qt.ShiftModifier) == QtCore.Qt.ShiftModifier,
            "ctrl": (modifiers & QtCore.Qt.ControlModifier) == QtCore.Qt.ControlModifier,
            "alt": (modifiers & QtCore.Qt.AltModifier) == QtCore.Qt.AltModifier,
            "key": key
        }

    @classmethod
    def fromHotkeyData(cls, hotkeyData: HotkeyData, func: Callable = None) -> 'Hotkey':
        """
        Creates a Hotkey instance from a HotkeyData storage object.

        Args:
            hotkeyData (HotkeyData): The data object typically retrieved from settings.
            func (Callable, optional): The function to assign to this hotkey.

        Returns:
            A new Hotkey instance.
        """
        return cls(
            hotkeyData.name,
            hotkeyData.key,
            ctrl=hotkeyData.ctrl,
            shift=hotkeyData.shift,
            alt=hotkeyData.alt,
            func=func
        )

    def toHotkeyData(self) -> HotkeyData:
        """
        Converts the current hotkey instance into a HotkeyData object for storage.

        Returns:
            A serializable version of this hotkey.
        """
        return HotkeyData(
            name=self.caption,
            key=self.key,
            ctrl=self.ctrl,
            shift=self.shift,
            alt=self.alt)

    def keyCode(self) -> int:
        """
        Calculates the combined integer value of the key and its modifiers.

        Returns:
            The bitwise ORed value of the key and active modifiers.
        """
        if qt.QT_VERSION == 2:
            ctrl = QtCore.Qt.CTRL if self.ctrl else 0
            shift = QtCore.Qt.SHIFT if self.shift else 0
            alt = QtCore.Qt.ALT if self.alt else 0
            return self.key | ctrl | shift | alt
        else:
            ctrl = QtCore.Qt.KeyboardModifier.ControlModifier if self.ctrl else QtCore.Qt.KeyboardModifier.NoModifier
            shift = QtCore.Qt.KeyboardModifier.ShiftModifier if self.shift else QtCore.Qt.KeyboardModifier.NoModifier
            alt = QtCore.Qt.KeyboardModifier.AltModifier if self.alt else QtCore.Qt.KeyboardModifier.NoModifier
            modifier = ctrl | shift | alt
            key = QtCore.Qt.Key(self.key)
            return QtCore.QKeyCombination(modifier, key)

    def keyToString(self) -> str:
        """
        Returns a human-readable string representation of the hotkey.

        Example: "Ctrl + Shift + P"

        Returns:
            The formatted hotkey string.
        """
        ctrl = "Ctrl" if self.ctrl else None
        shift = "Shift" if self.shift else None
        alt = "Alt" if self.alt else None
        key = QtGui.QKeySequence(self.key).toString()
        return " + ".join(filter(None, [ctrl, shift, alt, key]))
