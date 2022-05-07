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
import ThreadSend

"""This module provides main structure and function of client program for get ambient data from PCB device"""
# Plots: https://www.pythonguis.com/tutorials/plotting-matplotlib/

__version__ = "0.1.0"
__author__ = 'Yunovidov Dmitriy: Dm.Yunovidov@gmail.com'


class MplCanvas(FigureCanvasQTAgg):
    """
    Class for matplotlib canvas
    """
    def __init__(self, parent=None, width=5, height=4, dpi=150):
        fig = Figure(figsize=(width, height), dpi=dpi)
        self.axes = fig.add_subplot(111)
        super(MplCanvas, self).__init__(fig)


def init_logger():
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
    ch.setLevel(logging.DEBUG)
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


class MainWindow(QtWidgets.QMainWindow):
    datetime_format = 'dd-MM-yyyy HH:mm:ss'
    device_num = 1
    device_com = None
    db_conn = None
    db_path = 'test.db'
    thread = None  # COM data thread instance
    send_thread = None  # Send data to server thread
    tabs = {}  # tab structure for each data type {sens_dtype: [widget, canvas, toolbar, layout]}
    _plot_ref = {
        'realtime_plot': {},
        'datetime_plot': {}
    }  # plot structure for realtime plot updates {sens_dtype: [widget, canvas, toolbar, layout]}
    all_data_x = {
        'realtime_plot': {},
        'datetime_plot': {}
    }
    all_data_y = {
        'realtime_plot': {},
        'datetime_plot': {}
    }
    visible_data_len = 50

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
        self.timer.timeout.connect(self.update_statusbar)
        # self.timer.timeout.connect(self.update_plot)
        self.timer.start(5000)

        # setting date format
        self.dte_start_date.setDisplayFormat("dd.MM.yyyy HH:mm")
        self.dte_end_date.setDisplayFormat("dd.MM.yyyy HH:mm")

        self.pb_plot_data.clicked.connect(self.update_plot)
        self.chb_real_time.stateChanged.connect(self.is_realtime_check)

        self.pb_to_cloud.clicked.connect(self.load_to_cloud)

        self.statusBar().showMessage("Dot Pulse ambient device No {}".format(self.device_num))
        self.initdb()

        shv.logger.info("Successfully init main class")

    def load_to_cloud(self):
        """
        Start thread to load data to cloud
        :return:
        """
        if self.send_thread is None:
            shv.logger.info("Successfully init thread to sent data to server")
            self.send_thread = ThreadSend.SendThread(db_path=self.db_path)

        if self.pb_to_cloud.text() == 'Load to Cloud':
            shv.logger.debug("\tstart loading data to server")
            self.send_thread.start()
            self.pb_to_cloud.setText('Uploading to Cloud')
        else:
            shv.logger.debug("\tstop loading data to server")
            self.send_thread.quit()
            self.pb_to_cloud.setText('Load to Cloud')

    def is_realtime_check(self):
        """
        Set behavior for realtime update data on plots
        :return:
        """
        if self.chb_real_time.isChecked():
            shv.logger.debug("\tstart realtime plot of sensors data")
            self.dte_start_date.setEnabled(False)
            self.dte_end_date.setEnabled(False)
            self.pb_plot_data.setEnabled(False)
            self.update_plot()
        else:
            shv.logger.debug("\tstop realtime plot of sensors data")
            self.dte_start_date.setEnabled(True)
            self.dte_end_date.setEnabled(True)
            self.pb_plot_data.setEnabled(True)

    def update_plot(self, new_data=None):
        """
        Set new data on plots after sensors
        :param new_data: dict, new data unit from sensors
        :return:
        """
        for sens_dtype in shv.all_dtype:  # take each data type from sensors: CO2, T, P, R
            if sens_dtype not in self.tabs:  # for initial start, when none of tab created
                shv.logger.debug("\tcreate tab infrastructure")
                self.tabs[sens_dtype] = []
                self._plot_ref[sens_dtype] = None
                self.tabs[sens_dtype].append(QtWidgets.QWidget())  # set widget for new tab
                self.tabw_data.addTab(self.tabs[sens_dtype][0], sens_dtype)  # set widget as new tab in QTabWidget
                # Add matplotlib widgets for widget in tab in QTabWidget
                self.tabs[sens_dtype].append(MplCanvas(self, width=10, height=10, dpi=150))
                self.tabs[sens_dtype].append(NavigationToolbar(self.tabs[sens_dtype][1], self))
                self.tabs[sens_dtype].append(QtWidgets.QVBoxLayout())  # add layout and fill it with widgets
                self.tabs[sens_dtype][3].addWidget(self.tabs[sens_dtype][2])
                self.tabs[sens_dtype][3].addWidget(self.tabs[sens_dtype][1])
                self.tabs[sens_dtype][0].setLayout(self.tabs[sens_dtype][3])
                for k in self.all_data_x:
                    self.all_data_x[k][sens_dtype] = None
                    self.all_data_y[k][sens_dtype] = None
                    self._plot_ref[k][sens_dtype] = None

            if self._plot_ref['realtime_plot'][sens_dtype] is None and self.chb_real_time.isChecked():
                # For initial realtime plot, after tab structure is creates
                shv.logger.debug("\tset initial realtime plot for {}".format(sens_dtype))
                data = self.get_db_data(sens_dtype, limit=self.visible_data_len)  # get DB data for sensor
                if not data:
                    shv.logger.warning("There is no data on DB")
                    return
                self.all_data_x['realtime_plot'][sens_dtype] = list(range(self.visible_data_len))  # set number of visible values of unixtime
                self.all_data_y['realtime_plot'][sens_dtype] = []
                for unixtime_and_value in data:
                    self.all_data_y['realtime_plot'][sens_dtype].append(unixtime_and_value[1])  # add value
                while len(self.all_data_y['realtime_plot'][sens_dtype]) < self.visible_data_len:  # add 0 data to fulfill set len
                    self.all_data_y['realtime_plot'][sens_dtype].insert(0, 0)
                self.tabs[sens_dtype][1].axes.clear()  # clear of previose plot
                plot_refs = self.tabs[sens_dtype][1].axes.plot(
                    self.all_data_x['realtime_plot'][sens_dtype],
                    self.all_data_y['realtime_plot'][sens_dtype],
                    'r'
                )  # plot data on axes in tab
                self._plot_ref['realtime_plot'][sens_dtype] = plot_refs[0]  # save plot for further update
            elif self._plot_ref['realtime_plot'][sens_dtype] is not None and self.chb_real_time.isChecked():
                # Update data on realtime plot
                shv.logger.debug("\tupdate realtime plot for {}".format(sens_dtype))
                if new_data is None:  # initialize data before but no COM connection
                    self.tabs[sens_dtype][1].axes.clear()  # clear of previose plot
                    plot_refs = self.tabs[sens_dtype][1].axes.plot(
                        self.all_data_x['realtime_plot'][sens_dtype],
                        self.all_data_y['realtime_plot'][sens_dtype],
                        'r'
                    )  # plot data on axes in tab
                    self._plot_ref['realtime_plot'][sens_dtype] = plot_refs[0]
                else:
                    self.all_data_y[
                        'realtime_plot'
                    ][sens_dtype] = self.all_data_y[
                                            'realtime_plot'
                                    ][sens_dtype][1:] + [new_data[sens_dtype]]
                    self._plot_ref['realtime_plot'][sens_dtype].set_ydata(
                        self.all_data_y['realtime_plot'][sens_dtype]
                    )
            else:
                # Plot datetime_plot
                shv.logger.debug("\tset initial non realtime plot for {}".format(sens_dtype))
                unixtime_start = self.dte_start_date.dateTime().toSecsSinceEpoch()
                unixtime_stop = self.dte_end_date.dateTime().toSecsSinceEpoch()
                shv.logger.debug("\tunixtime start: {} and end: {}".format(
                    unixtime_start, unixtime_stop
                ))
                # TODO: get data from DB based on unixtime values
                data = self.get_db_data(
                    sens_dtype, limit=10000
                )  # get DB data for sensor
                if not data:
                    shv.logger.warning("There is no data on DB")
                    return
                valid_data = [x for x in data if unixtime_start < x[0] < unixtime_stop]
                self.all_data_x['datetime_plot'][sens_dtype] = []
                self.all_data_y['datetime_plot'][sens_dtype] = []
                for unixtime_and_value in valid_data:
                    self.all_data_x['datetime_plot'][sens_dtype].append(unixtime_and_value[0])
                    self.all_data_y['datetime_plot'][sens_dtype].append(unixtime_and_value[1])
                self.tabs[sens_dtype][1].axes.clear()  # clear of previose plot
                plot_refs = self.tabs[sens_dtype][1].axes.plot(
                    self.all_data_x['datetime_plot'][sens_dtype],
                    self.all_data_y['datetime_plot'][sens_dtype],
                    'r'
                )
                self._plot_ref['datetime_plot'][sens_dtype] = plot_refs[0]
            self.tabs[sens_dtype][1].draw()  # trigger the canvas to update and redraw.

    def initdb(self):
        """
        Initiate database and create tables and indexes
        """
        shv.logger.info(
            "Init {} database and {} table in it".format(self.db_path, 'ambient_data')
        )
        self.db_conn = sqlite3.connect(self.db_path, check_same_thread=False)
        cursor = self.db_conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ambient_data (
                unixtime integer,
                type text,
                value real
            )
            """)
        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uk_ambient_data on ambient_data (
                type,
                unixtime
            )
            """)
        # DB for last send status
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS send_status (
                unixtime integer,
                type text
            )
            """)
        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uk_send_status on send_status (
                type
            )
            """)
        self.db_conn.commit()

    def start_com(self):
        """
        Start tread for getting ambient data from COM device
        :return:
        """
        if self.pb_com_connect.text() == 'Connect Device':
            self.device_com = self.cb_devices.currentText()
            shv.logger.debug(
                "\tinit {} COM port connection and data thread".format(self.device_com)
            )
            # TODO: some random error appear when thread is started and get corrupt data
            self.thread = ThreadCom.COMStartThread(
                device_com=self.device_com,
                db_path=self.db_path
            )
            self.thread.SER_UPDATE_SIGNAL.connect(
                lambda x: self.com_data(x)
            )  # connect signal from thread
            self.thread.start()
            self.pb_com_connect.setText('Stop Connection')
        else:
            shv.logger.debug(
                "\tstop {} COM port connection and data thread".format(self.device_com)
            )
            self.thread.quit()
            self.pb_com_connect.setText('Connect Device')

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

    def com_data(self, com_data):
        """
        Function for process COM data thread signal
        :param com_data: str, data line form thread for ambient data COM device
        :return: None
        """
        # TODO: set table for display time interval data or to realtime data
        if com_data == 'Serial is broken':
            shv.logger.debug(
                "\tstop {} COM port connection and data thread".format(self.device_com)
            )
            self.pb_com_connect.setText('Connect Device')
            return

        shv.logger.debug("\t get COM data: {}".format(com_data))
        com_data_now = {}
        splitted = com_data.split(',')
        for i in range(1, 5):
            v_splitted = splitted[i].split('_')
            v_type = v_splitted[0]
            v_value = float(v_splitted[1])
            com_data_now[v_type] = v_value
        dp.set_table_data(
            data_to_table=com_data_now,
            tv_data_widget=self.tv_comdata,
            time_stamp=splitted[0]
        )

        if self.chb_real_time.isChecked():
            shv.logger.debug("\t start realtime plot")
            timestamp = list(map(int, splitted[0].split('_')))
            unixtime = int(time.mktime(datetime.datetime(*timestamp).timetuple()))
            com_data_now['unixtime'] = unixtime
            self.update_plot(new_data=com_data_now)

    def get_db_data(self, sens_dtype, limit=100):
        """
        Get some data from DB with setting limits
        :param sens_dtype: str, identifier for type of sensor data (CO2, T, R, P)
        :param limit: int, limit value for get last data from DB
        :return: list, structure of tuples with values of unixtime and float value [(unixtime, value), ...]
        """
        cursor = self.db_conn.cursor()
        cursor.execute(
            """
            select unixtime, value from ambient_data where type = ? order by unixtime desc limit ?
            """,  # limit 10
            (sens_dtype, limit)
        )
        data = list(
            reversed(
                [x for x in cursor.fetchall()]
            )
        )  # crate list with tuples, newest come first
        return data

    def update_statusbar(self):
        """
        Generate OS resources data and print it on statusBar each second
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

    init_logger()
    app = QtWidgets.QApplication(sys.argv)
    # app.setStyle("Fusion")
    main_window = MainWindow()
    main_window.show()
    sys.exit(app.exec_())