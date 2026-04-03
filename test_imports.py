try:
    from PySide6.QtWidgets import QApplication
    print("PySide6.QtWidgets OK")
    from PySide6.QtCore import Qt
    print("PySide6.QtCore OK")
    from PySide6.QtGui import QColor
    print("PySide6.QtGui OK")
    import psutil
    print("psutil OK")
    import pynput
    print("pynput OK")
    import pyperclip
    print("pyperclip OK")
    import docx
    print("python-docx OK")
    print("All core imports OK")
except Exception as e:
    import traceback
    traceback.print_exc()
