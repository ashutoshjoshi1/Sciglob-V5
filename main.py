import sys
from PyQt5.QtWidgets import QApplication, QSplashScreen
from PyQt5.QtGui import QPixmap
from gui.main_window import MainWindow

def main():
    app = QApplication(sys.argv)
    # Splash screen
    splash_pix = QPixmap("asset/splash.jpg")
    if not splash_pix.isNull():
        splash = QSplashScreen(splash_pix)
        splash.show()
        app.processEvents()
    win = MainWindow()
    win.show()
    if 'splash' in locals():
        splash.finish(win)
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
