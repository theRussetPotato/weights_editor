from ..resources import variables

if variables.qt_version > 4:
    from PySide2 import QtGui
    from PySide2 import QtCore
    from PySide2 import QtWidgets
else:
    from PySide import QtGui
    from PySide import QtCore
    QtWidgets = QtGui


class GroupboxFrame(QtWidgets.QFrame):
    
    """
    Inheriting this just so it's easy to find it with QObject.findChild()
    """
    
    def __init__(self, parent=None):
        QtWidgets.QFrame.__init__(self, parent=parent)