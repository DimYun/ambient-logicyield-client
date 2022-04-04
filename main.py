# -*- coding: utf-8 -*-

from PyQt5 import QtCore, QtWidgets, QtGui, uic
import time
import sqlite3
import serial
from serial.tools import list_ports
import os
import sys
import psutil
import logging

import SharedVars as shv
import ThreadCom

"""This module provides main structure and function of client program for get ambient data from PCB device"""

__version__ = "0.1.0"
__author__ = 'Yunovidov Dmitriy: Dm.Yunovidov@gmail.com'

logging.basicConfig(
    format='%(levelname)s, %(asctime)s, (%(module)s - %(funcName)s - %(lineno)d), %(message)s',
    handlers=[
            logging.FileHandler("main-log.log", 'w'),
            logging.StreamHandler(sys.stdout)
        ]
)

shv.logger = logging.getLogger()

shv.logger.setLevel(logging.DEBUG)


class MainWindow(QtWidgets.QMainWindow):
    datetime_format = 'dd-MM-yyyy HH:mm:ss'
    device_num = 1
    device_com = None
    db_conn = None
    db_path = 'test.db'
    thread = None  # COM data thread instance

    def __init__(self):
        super(QtWidgets.QMainWindow, self).__init__()
        uic.loadUi("client_main.ui", self)

        self.setWindowTitle("Client Ambient Data")

        self.setCentralWidget(self.centralwidget)
        self.setMenuBar(self.menubar)

        # Init QSystemTrayIcon
        self.tray_icon = QtWidgets.QSystemTrayIcon(self)
        self.tray_icon.setIcon(QtGui.QIcon("tray_icon.svg"))

        # Tray menu
        show_action = QtWidgets.QAction("Show", self)
        hide_action = QtWidgets.QAction("Hide", self)
        quit_action = QtWidgets.QAction("Exit", self)

        show_action.triggered.connect(self.show)
        hide_action.triggered.connect(self.hide)
        quit_action.triggered.connect(self.close)

        tray_menu = QtWidgets.QMenu()
        tray_menu.addAction(show_action)
        tray_menu.addAction(hide_action)
        tray_menu.addAction(quit_action)

        self.refresh()

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()

        self.pb_to_cloud.clicked.connect(self.start_com)
        #
        # self.pb_exit.clicked.connect(self.hide_it)
        # self.pb_save.clicked.connect(self.save_data)

        # Show program
        # self.show()
        # tray.setContextMenu(menu)
        # Configure statusbar
        # Setup timer for ambient data TODO: May slow down interface
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.generate_and_sent_signal)
        self.timer.start(5000)

        self.statusBar().showMessage("Dot Pulse ambient device No {}".format(self.device_num))
        shv.logger.info("Successfully init main class")

    def initdb(self):
        """
        Create necessary tables
        """
        shv.logger.debug("Init {} database and {} table in it".format(self.db_path, 'ambient_data'))
        self.db_conn = sqlite3.connect(self.db_path)
        cursor = self.db_conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ambient_data (
                unixtime integer,
                type text,
                value real
            )
            """)
        self.db_conn.commit()

    def start_com(self):
        """
        Start COM port data get tread
        :return:
        """
        shv.logger.debug("Init {} COM port connection and data thread".format(self.device_com))
        self.initdb()
        self.device_com = self.cb_devices.currentText()
        self.thread = ThreadCom.COMStartThread(device_com=self.device_com, db_path=self.db_path)
        self.thread.SER_UPDATE_SIGNAL.connect(lambda x: self.com_data(x))  # connect signal from thread
        self.thread.start()

    def refresh(self):
        """
        Set found COM ports in GUI interface
        :return: None
        """
        self.cb_devices.clear()
        self.cb_devices.addItems(self.available_com())
        self.cb_devices.setCurrentIndex(0)

    def available_com(self):
        """
        Scan system for available COM (virtual COM) ports
        :return: list with available COM ports
        """
        shv.logger.debug("Init scan for COM ports")
        if os.name == 'nt':
            # Windows
            all_ports = []
            for i in range(256):
                try:
                    s = serial.Serial(i)
                    all_ports.append('COM' + str(i + 1))
                    s.close()
                except serial.SerialException:
                    pass
            return all_ports
        else:
            # Mac / Linux
            all_ports = []
            for i in [port[0] for port in list_ports.comports()]:
                all_ports.append(i)
            return all_ports

    def com_data(self, x):
        """
        Function for serial thread signal. Catch data from COM port and process it
        :param x: int data form COM port monitor thread (1 or 2)
        :return: None
        """
        # TODO: set correct DB selection and graphics plot
        shv.logger.debug("Catch {} COM port signal".format(x))
        cursor = self.db_conn.cursor()
        dtype = 'CO2'
        cursor.execute("""
                    select unixtime, value from ambient_data where type = ? order by unixtime desc limit 10
                    """, (dtype, ))
        data = list(reversed([x for x in cursor.fetchall()]))
        self.l_date.setText('_'.join([str(x) for x in data[-1]]))

    def generate_and_sent_signal(self):
        """
        Generate OS resourses data and print it on statusBar each second
        :return: None
        """
        self.statusBar().showMessage(
            "Dot Pulse device No {0} \t CPU: {1} %, \t Memory usage: {2} %, \t Free space: {3} %".format(
                self.device_num,
                psutil.cpu_percent(),
                psutil.virtual_memory()[2],
                psutil.disk_usage('/')[3]
            )
        )

    def hide_it(self):
        """
        Hide program to tray
        :return: None
        """
        self.hide()
        self.tray_icon.showMessage(
            "Tray Program",
            "Application was minimized to Tray",
            QtWidgets.QSystemTrayIcon.Information,
            2000
        )

    def save_file_dialog(self):
        """
        Call file save dialog
        :return: name of the selected file or None
        """
        options = QtWidgets.QFileDialog.Options()
        options |= QtWidgets.QFileDialog.DontUseNativeDialog
        file_name, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "QFileDialog.getSaveFileName()",
            "",
            "All Files (*);;CSV Files (*.csv)",
            options=options
        )
        if file_name:
            print(file_name)
            return file_name
        else:
            return None

    def open_file_name_dialog(self):
        """
        Call file open dialog
        :return: file name or None
        """
        options = QtWidgets.QFileDialog.Options()
        options |= QtWidgets.QFileDialog.DontUseNativeDialog
        file_name, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "QFileDialog.getOpenFileName()",
            "",
            "All Files (*);;CSV Files (*.csv)",
            options=options
        )
        if file_name:
            print(file_name)
            return file_name
        else:
            return None

    def closeEvent(self, event):
        self.save_dialog()
        # self.timer.stop()
        # self.timer.deleteLater()
        self.deleteLater()
        event.accept()
        # else:
        #     event.ignore()

    def save_dialog(self):
        result = QtWidgets.QMessageBox.question(
            self,
            self.tr('Close window'),
            self.tr('Save changes?'),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.No
        )
        if result == QtWidgets.QMessageBox.Yes:
            self.save_data()
        else:
            pass


if __name__ == "__main__":
    import sys

    app = QtWidgets.QApplication(sys.argv)
    # app.setStyle("Fusion")
    main_window = MainWindow()
    main_window.show()
    sys.exit(app.exec_())