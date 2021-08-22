from PySide2 import QtCore
from PySide2 import QtWidgets


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
        if key_code == QtCore.Qt.Key_Enter or key_code == QtCore.Qt.Key_Return:
            self.enter_pressed.emit(self.value())
