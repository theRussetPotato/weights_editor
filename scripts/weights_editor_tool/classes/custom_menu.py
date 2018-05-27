from ..resources import variables

if variables.qt_version > 4:
    from PySide2 import QtGui
    from PySide2 import QtCore
    from PySide2 import QtWidgets
else:
    from PySide import QtGui
    from PySide import QtCore
    QtWidgets = QtGui


class CustomMenu(QtWidgets.QMenu):
    
    showing = QtCore.Signal()
    
    def __init__(self, label, parent=None):
        QtWidgets.QMenu.__init__(self, label, parent=parent)
    
    def showEvent(self, event):
        self.showing.emit()