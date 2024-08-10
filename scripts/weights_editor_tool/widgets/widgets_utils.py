try:
    import shiboken2
    from PySide2.QtCore import *
    from PySide2.QtGui import *
    from PySide2.QtWidgets import *
    from PySide2.QtNetwork import *
except ImportError:
    import shiboken6 as shiboken2
    from PySide6.QtCore import *
    from PySide6.QtGui import *
    from PySide6.QtWidgets import *
    from PySide6.QtNetwork import *
