from weights_editor_tool.qt import QtWidgets


class PresetButton(QtWidgets.QPushButton):
    """
    An interactive button representing a numeric weight preset.
    """

    def __init__(
            self,
            value : float,
            minValue: float,
            maxValue: float,
            parent: QtWidgets.QWidget = None) -> None:
        """
        Initializes the button with its preset value and input constraints.

        Args:
            value (float): The initial preset value.
            minValue (float): Minimum allowable value for the input dialog.
            maxValue (float): Maximum allowable value for the input dialog.
            parent (QWidget, optional): Parent widget.
        """
        super().__init__(f"{value}", parent)

        self.value = value
        self._minValue = minValue
        self._maxValue = maxValue

        self.clicked.connect(self._inputNewValue)

    def _inputNewValue(self) -> None:
        """
        Spawns a QInputDialog to let the user redefine the button's value.
        Updates the button text if the change is accepted.
        """
        value, accepted = QtWidgets.QInputDialog.getDouble(
            self,
            "Enter Value",
            "Enter a new value to use for this preset:",
            self.value,
            self._minValue,
            self._maxValue,
            2)

        if accepted:
            self.value = value
            self.setText(f"{value}")
