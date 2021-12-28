from PySide2 import QtCore
from PySide2 import QtWidgets


class CustomHeaderView(QtWidgets.QHeaderView):
    
    """
    Emits different mouse events.
    """
    
    header_left_clicked = QtCore.Signal(int)
    header_middle_clicked = QtCore.Signal(int)
    header_right_clicked = QtCore.Signal(int)
    
    def __init__(self, orientation, parent=None):
        super(CustomHeaderView, self).__init__(orientation, parent)
        self.last_index = 0

    def mousePressEvent(self, event):
        index = self.logicalIndexAt(event.x(), event.y())
        self.last_index = index
        
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.header_left_clicked.emit(index)
        elif event.button() == QtCore.Qt.MouseButton.MiddleButton:
            self.header_middle_clicked.emit(index)
        elif event.button() == QtCore.Qt.MouseButton.RightButton:
            self.header_right_clicked.emit(index)
        
        return QtWidgets.QHeaderView.mousePressEvent(self, event)


class VerticalHeaderView(CustomHeaderView):

    """
    Resizing vertical's width dynamically seems to be weird.
    Can only reliably do it by overriding `sizeHint`.
    """

    def __init__(self, orientation, parent=None):
        super(VerticalHeaderView, self).__init__(orientation, parent)
        self._size = QtCore.QSize(0, 0)

    def sizeHint(self):
        return self._size
