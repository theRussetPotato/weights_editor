from weights_editor_tool.widgets.widgets_utils import *


class CustomDoubleSpinbox(QDoubleSpinBox):
    
    """
    Emits when enter is pressed.
    """
    
    enter_pressed = Signal(float)
    
    def __init__(self, parent=None):
        super(CustomDoubleSpinbox, self).__init__(parent)
    
    def keyPressEvent(self, event):
        QDoubleSpinBox.keyPressEvent(self, event)
        
        key_code = event.key()
        if key_code == Qt.Key_Enter or key_code == Qt.Key_Return:
            self.enter_pressed.emit(self.value())
