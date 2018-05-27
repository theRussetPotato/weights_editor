from ..resources import variables

if variables.qt_version > 4:
    from PySide2 import QtGui
    from PySide2 import QtCore
    from PySide2 import QtWidgets
else:
    from PySide import QtGui
    from PySide import QtCore
    QtWidgets = QtGui


class CustomDoubleSpinbox(QtWidgets.QDoubleSpinBox):
    
    """
    Emits when enter is pressed.
    """
    
    enter_pressed = QtCore.Signal(float)
    
    def __init__(self, parent=None):
        super(CustomDoubleSpinbox, self).__init__(parent)
    
    def keyPressEvent(self, event):
        QtWidgets.QDoubleSpinBox.keyPressEvent(self, event)
        
        key_code = event.key()
        if key_code == 16777221 or key_code == 16777220: # Enter key
            self.enter_pressed.emit(self.value())