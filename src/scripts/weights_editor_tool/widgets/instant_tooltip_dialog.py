from weights_editor_tool.qt import QtCore, QtGui, QtWidgets
from weights_editor_tool import qt


class InstantToolTipDialog(QtWidgets.QLabel):
    """
    A high-performance tooltip replacement that bypasses standard Qt delays.

    This widget acts as a singleton 'dialog' (a floating QLabel) that follows the mouse cursor.
    It provides immediate feedback to the user.

    Attributes:
        instance (InstantToolTipDialog): The singleton instance of the tooltip.
    """

    instance = None
    enabled = True

    def __init__(self, parent: QtWidgets.QWidget = None) -> None:
        """
        Initializes the tooltip.
        Sets window flags to ensure it behaves as a ToolTip (no taskbar icon, always on top).
        """
        super().__init__(parent=parent)

        self.setWindowFlags(QtCore.Qt.ToolTip)
        self.setStyleSheet("""
            QLabel {
                background-color: black;
                color: white;
                font-style: italic;
                font-weight: bold;
                padding: 8px;
            }
        """)

    @classmethod
    def create(cls):
        """
        Ensures a valid singleton instance exists.
        """
        if cls.instance is None or not qt.shiboken.isValid(cls.instance):
            cls.instance = InstantToolTipDialog()
            cls.instance.hide()

    @classmethod
    def moveDialogToMouse(cls) -> None:
        """
        Offsets the tooltip relative to the current cursor position.
        The tooltip is centered horizontally and placed slightly above the cursor.
        """
        cursorPos = QtGui.QCursor.pos()
        x = -cls.instance.width() / 2
        y = -cls.instance.height() - 10
        offset = QtCore.QPoint(x, y)
        cls.instance.move(cursorPos + offset)

    @classmethod
    def mouseEnteringEvent(cls, widget: QtWidgets.QWidget, text: str) -> None:
        """
        Triggers the tooltip display when a mouse enters a target widget's area.

        Args:
            widget (QtWidgets.QWidget): The widget being hovered over.
            text (str): The tooltip message to display.
        """
        if not cls.enabled:
            return

        if not widget.isEnabled():
            return

        if not text:
            return

        # Initialize the dialog.
        cls.create()
        cls.instance.setText(text)
        cls.moveDialogToMouse()
        cls.instance.show()

    @classmethod
    def mouseMovingEvent(cls) -> None:
        """
        Updates the position of the tooltip in real-time as the mouse moves across a widget, providing a 'sticky' feel.
        """
        if not cls.enabled:
            return

        if cls.instance.isVisible():
            cls.moveDialogToMouse()

    @classmethod
    def mouseLeavingEvent(cls, widget: QtWidgets.QWidget) -> None:
        """
        Immediately hides the tooltip when the mouse exits a widget.

        Args:
            widget (QtWidgets.QWidget): The widget being exited.
        """
        if not cls.enabled:
            return

        if not widget.isEnabled():
            return

        if not cls.instance.isVisible():
            return

        cls.instance.hide()

    @classmethod
    def mousePressingEvent(cls) -> None:
        """
        Safety feature: Hides the tooltip if the user clicks, ensuring it doesn't obstruct the user's
        view while they interact with a control.
        """
        if not cls.enabled:
            return

        if cls.instance.isVisible():
            cls.instance.hide()
