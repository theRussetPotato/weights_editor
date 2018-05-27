from ..resources import variables

if variables.qt_version > 4:
    from PySide2 import QtGui
    from PySide2 import QtCore
    from PySide2 import QtWidgets
else:
    from PySide import QtGui
    from PySide import QtCore
    QtWidgets = QtGui


class CustomHeaderView(QtWidgets.QHeaderView):
    
    """
    Emits different mouse events.
    """
    
    header_left_clicked = QtCore.Signal(int)
    header_middle_clicked = QtCore.Signal(int)
    header_right_clicked = QtCore.Signal(int)
    
    def __init__(self, parent=None):
        super(CustomHeaderView, self).__init__(QtCore.Qt.Horizontal, parent)
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