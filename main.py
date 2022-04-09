# -*- coding: utf-8 -*-

from PyQt5 import QtCore, QtWidgets, QtGui, uic
import matplotlib
matplotlib.use('Qt5Agg')

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg, NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure

import time
import sqlite3
import serial
from serial.tools import list_ports
import os
import sys
import psutil
import logging
import random
import datetime

import DataProcess as dp
import SharedVars as shv
import ThreadCom

"""This module provides main structure and function of client program for get ambient data from PCB device"""
# Plots: https://www.pythonguis.com/tutorials/plotting-matplotlib/

__version__ = "0.1.0"
__author__ = 'Yunovidov Dmitriy: Dm.Yunovidov@gmail.com'


class MplCanvas(FigureCanvasQTAgg):

    def __init__(self, parent=None, width=5, height=4, dpi=150):
        fig = Figure(figsize=(width, height), dpi=dpi)
        self.axes = fig.add_subplot(111)
        super(MplCanvas, self).__init__(fig)


class MainWindow(QtWidgets.QMainWindow):
    datetime_format = 'dd-MM-yyyy HH:mm:ss'
    device_num = 1
    device_com = None
    db_conn = None
    db_path = 'test.db'
    thread = None  # COM data thread instance
    all_data_x = None  # list(range(50))
    all_data_y = None  # [random.randint(0, 10) for i in range(50)]
    tabs = {}  # tab structure for each data type {dtype: [widget, canvas, toolbar, layout]}
    _plot_ref = {}

    def __init__(self):
        super(QtWidgets.QMainWindow, self).__init__()
        self.init_logger()  # init logging
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

        self.pb_com_connect.clicked.connect(self.start_com)
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
        # self.timer.timeout.connect(self.update_plot)
        self.timer.start(5000)

        # setting date format
        self.dte_start_date.setDisplayFormat("dd.MM.yyyy HH:mm")
        self.dte_end_date.setDisplayFormat("dd.MM.yyyy HH:mm")

        self.pb_plot_data.clicked.connect(self.plot_solid_data)
        self.chb_real_time.stateChanged.connect(self.is_realtime_check)

        self.statusBar().showMessage("Dot Pulse ambient device No {}".format(self.device_num))
        self.initdb()

        shv.logger.info("Successfully init main class")

    def is_realtime_check(self):
        if self.chb_real_time.isChecked():
            self.dte_start_date.setEnabled(False)
            self.dte_end_date.setEnabled(False)
            self.pb_plot_data.setEnabled(False)
            self.update_plot()
        else:
            self.dte_start_date.setEnabled(True)
            self.dte_end_date.setEnabled(True)
            self.pb_plot_data.setEnabled(True)

    def update_plot(self, new_data=None):
        if self.all_data_x is None:
            return
        else:
            # Create infrastructure
            for dtype in ['CO2', 'T', 'R', 'P']:
                if dtype not in self.tabs:
                    self.tabs[dtype] = []
                    self._plot_ref[dtype] = None
                    self.tabs[dtype].append(QtWidgets.QWidget())
                    self.tabw_data.addTab(self.tabs[dtype][0], dtype)
                    # Add matplotlib widgets for each tab
                    self.tabs[dtype].append(MplCanvas(self, width=10, height=10, dpi=150))
                    self.tabs[dtype].append(NavigationToolbar(self.tabs[dtype][1], self))
                    self.tabs[dtype].append(QtWidgets.QVBoxLayout())
                    self.tabs[dtype][3].addWidget(self.tabs[dtype][2])
                    self.tabs[dtype][3].addWidget(self.tabs[dtype][1])
                    self.tabs[dtype][0].setLayout(self.tabs[dtype][3])

                if self._plot_ref[dtype] is None and self.chb_real_time.isChecked():
                    # When start real time data plot
                    data = self.get_db_data(dtype)
                    self.all_data_y[dtype] = []
                    self.all_data_x = list(range(50))
                    for unixtime_and_value in data[-50:]:
                        # self.all_data_x.append(unixtime_and_value[0])
                        self.all_data_y[dtype].append(unixtime_and_value[1])
                    while len(self.all_data_y[dtype]) < 50:
                        self.all_data_y[dtype].insert(0, 0)

                    plot_refs = self.tabs[dtype][1].axes.plot(
                        self.all_data_x,
                        self.all_data_y[dtype],
                        'r'
                    )
                    self._plot_ref[dtype] = plot_refs[0]
                    # self.tabs[dtype][1].draw()
                # # Drop off the first y element, append a new one.
                # self.all_data_y = self.all_data_y[1:] + [random.randint(0, 50)]
                # self.all_data_x = self.all_data_x[1:] + [self.all_data_x[-1] + 1]

                # Note: we no longer need to clear the axis.
                elif self._plot_ref[dtype] is None and not self.chb_real_time.isChecked():
                    # First time we have no plot reference, so do a normal plot.
                    # .plot returns a list of line <reference>s, as we're
                    # only getting one we can take the first element.
                    plot_refs = self.tabs[dtype][1].axes.plot(
                        self.all_data_x,
                        self.all_data_y[dtype],
                        'r'
                    )
                    self._plot_ref[dtype] = plot_refs[0]
                else:
                    # We have a reference, we can use it to update the data for that line.
                    self.all_data_y[dtype] = self.all_data_y[dtype][1:] + [new_data[dtype]]
                    # self._plot_ref[dtype].set_xdata(self.all_data_x)
                    self._plot_ref[dtype].set_ydata(self.all_data_y[dtype])
                    # Trigger the canvas to update and redraw.
                self.tabs[dtype][1].draw()

    def init_logger(self):
        """
        Initiate logging
        :return: None
        """
        shv.logger = logging.getLogger('main_logger')
        shv.logger.setLevel(logging.DEBUG)
        # create file handler which logs even debug messages
        fh = logging.FileHandler('main-log.log', 'w')
        fh.setLevel(logging.DEBUG)
        # create console handler with a higher log level
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        # create class handler with a higher log level for user messages
        clh = logging.StreamHandler(dp.InfoWindow())
        clh.setLevel(logging.WARNING)
        # create formatter and add it to the handlers
        formatter = logging.Formatter(
            '%(levelname)s, %(asctime)s, (%(module)s - %(funcName)s - %(lineno)d), %(message)s'
        )
        ch.setFormatter(formatter)
        fh.setFormatter(formatter)
        clh.setFormatter(formatter)
        # add the handlers to logger
        shv.logger.addHandler(clh)
        shv.logger.addHandler(ch)
        shv.logger.addHandler(fh)

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
        :param x: str, data line form COM port monitor thread
        :return: None
        """
        # TODO: insert new data in tv, plot realtime data if set checkbox and start date
        if self.chb_real_time.isChecked():  # plot data in real time
            splitted = x.split(',')
            timestamp = list(map(int, splitted[0].split('_')))
            unixtime = int(time.mktime(datetime.datetime(*timestamp).timetuple()))
            com_data_now = {
                'unixtime': unixtime
            }
            for i in range(1, 5):
                v_splitted = splitted[i].split('_')
                v_type = v_splitted[0]
                v_value = float(v_splitted[1])
                com_data_now[v_type] = v_value

            self.update_plot(new_data=com_data_now)

            # Get data form DB
            if self.all_data_x is None:
                start_td_value = self.dte_start_date.dateTime()  # getting current datetime in QDatetime
                start_unixtime = start_td_value.toSecsSinceEpoch()
                self.all_data_y = {}
                for dtype in ['CO2', 'T', 'R', 'P']:
                    data = self.get_db_data(dtype)
                    self.all_data_y[dtype] = []
                    self.all_data_x = []
                    for unixtime_value in data:
                        if unixtime_value[0] >= start_unixtime:
                            self.all_data_x.append(unixtime_value[0])
                            self.all_data_y[dtype].append(unixtime_value[1])

        # # TODO: set correct DB selection and graphics plot
        # shv.logger.debug("Catch {} COM port signal".format(x))
        # cursor = self.db_conn.cursor()
        # dtype = 'CO2'
        # cursor.execute("""
        #             select unixtime, value from ambient_data where type = ? order by unixtime desc limit 10
        #             """, (dtype, ))
        # data = list(reversed([x for x in cursor.fetchall()]))
        # self.l_date.setText('_'.join([str(x) for x in data[-1]]))

    def get_db_data(self, dtype):
        cursor = self.db_conn.cursor()
        cursor.execute(
            """
            select unixtime, value from ambient_data where type = ? order by unixtime desc limit 10
            """,
            (dtype,)
        )
        data = list(
            reversed(
                [x for x in cursor.fetchall()]
            )
        )
        return data

    def plot_solid_data(self):
        # Get data form DB
        start_td_value = self.dte_start_date.dateTime()  # getting current datetime in QDatetime
        start_unixtime = start_td_value.toSecsSinceEpoch()

        end_td_value = self.dte_end_date.dateTime()  # getting current datetime in QDatetime
        end_unixtime = end_td_value.toSecsSinceEpoch()
        self.all_data_y = {}
        for dtype in ['CO2', 'T', 'R']:
            cursor = self.db_conn.cursor()
            cursor.execute(
                """
                select unixtime, value from ambient_data where type = ? order by unixtime desc limit 10
                """,
                (dtype,)
            )
            data = list(
                reversed(
                    [x for x in cursor.fetchall()]
                )
            )
            self.all_data_y[dtype] = []
            self.all_data_x = []
            for unixtime_value in data:
                if unixtime_value[0] >= start_unixtime and unixtime_value[0] <= end_unixtime:
                    self.all_data_x.append(unixtime_value[0])
                    self.all_data_y[dtype].append(unixtime_value[1])
        self.update_plot()

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