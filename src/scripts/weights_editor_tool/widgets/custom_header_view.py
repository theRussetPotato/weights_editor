from weights_editor_tool.qt import QtCore, QtGui, QtWidgets


class CustomHeaderView(QtWidgets.QHeaderView):
    """
    An enhanced header for QTableView that helps expose different mouse click actions.

    Signals:
        headerLeftClicked (int): Emitted with the logical index on left-click.
        headerMiddleClicked (int): Emitted with the logical index on middle-click.
        headerRightClicked (int): Emitted with the logical index on right-click.
    """

    headerLeftClicked = QtCore.Signal(int)
    headerMiddleClicked = QtCore.Signal(int)
    headerRightClicked = QtCore.Signal(int)
    
    def __init__(self, orientation: QtCore.Qt.Orientation, parent: QtWidgets.QWidget = None) -> None:
        """
        Initializes the header and tracks the last index interacted with.
        """
        super(CustomHeaderView, self).__init__(orientation, parent)
        self.lastIndex = 0

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        """
        Determines which logical index was clicked based on coordinates and emits the corresponding signal for the mouse button used.

        Args:
            event (QMouseEvent): The mouse press event.
        """
        index = self.logicalIndexAt(event.x(), event.y())
        self.lastIndex = index
        
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.headerLeftClicked.emit(index)
        elif event.button() == QtCore.Qt.MouseButton.MiddleButton:
            self.headerMiddleClicked.emit(index)
        elif event.button() == QtCore.Qt.MouseButton.RightButton:
            self.headerRightClicked.emit(index)
        
        return QtWidgets.QHeaderView.mousePressEvent(self, event)


class VerticalHeaderView(CustomHeaderView):
    """
    A vertical-specific header that allows for manual size hinting.

    In complex layouts, vertical headers often fail to resize their width correctly when the content changes.
    This class overrides the `sizeHint` to allow the table to force a specific width.
    """
    def __init__(self, parent: QtWidgets.QWidget = None) -> None:
        """
        Initializes the vertical header with a default zero-size hint.
        """
        super(VerticalHeaderView, self).__init__(QtCore.Qt.Vertical, parent)
        self.size = QtCore.QSize(0, 0)

    def sizeHint(self) -> QtCore.QSize:
        """
        Returns the manually set size hint.

        Returns:
            The custom size used to determine header width.
        """
        return self.size
