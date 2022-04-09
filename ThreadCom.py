from PyQt5 import QtCore, QtWidgets
import serial
import time
import sqlite3
import datetime
import SharedVars as shv


class COMStartThread (QtCore.QThread):
    # Class for get ambient data
    ser = None  # serial device
    my_signal = QtCore.pyqtSignal()  # QtCore.pyqtSignal()
    count_ard_reboot = 0
    SER_UPDATE_SIGNAL = QtCore.pyqtSignal('QString')
    is_start = False

    def __init__(self, device_com, db_path, parent=None):
        QtCore.QThread.__init__(self, parent)
        self.device_com = device_com
        self.is_start = True
        self.db_path = db_path
        self.db_conn = None

    def run(self):
        shv.logger.info("Run thread for COM device")
        self.db_conn = sqlite3.connect(self.db_path)
        try:
            self.ser = serial.Serial(self.device_com)
            self.ser.flushInput()
            self.ser.flushOutput()
            while self.is_start:
                line = self.ser.readline().strip()
                self.insert_data(line)
        except serial.SerialException as var:
            shv.logger.error("Serial Exception, thread is stopped: {}".format(var))
            self.is_start = False
            self.my_signal.emit('Serial is broken')

    def insert_data(self, line):
        """
        Parse COM data and insert them into db
        :param line: str, line with COM data
        :return: None
        """
        # TODO: split on 2 funct: split string (use tests) and insert
        try:
            splitted = line.decode('utf-8').split(',')
        except UnicodeDecodeError as e:
            shv.logger.warning("UnicodeDecodeError {}".format(e))
            return
        if len(splitted) != 6 or not splitted[0] == 'LY':
            return  # partial data, skipping
        shv.logger.info("Get valid COM data: {}".format(line))
        splitted = splitted[1:]  # drop data start symbols
        timestamp = list(map(int, splitted[0].split('_')))
        unixtime = int(time.mktime(datetime.datetime(*timestamp).timetuple()))

        cursor = self.db_conn.cursor()
        for i in range(1, 5):
            v_splitted = splitted[i].split('_')
            v_type = v_splitted[0]
            v_value = float(v_splitted[1])
            shv.logger.debug("Get type:value COM data: {}: {}".format(v_type, v_value))
            cursor.execute(
                """
                INSERT INTO ambient_data (
                    unixtime,
                    type,
                    value
                ) VALUES (?, ?, ?)
                """, (unixtime, v_type, v_value))
        self.db_conn.commit()
        shv.logger.info("Write data, sent signal".format(line))
        self.SER_UPDATE_SIGNAL.emit(','.join(splitted))

    def quit(self):
        shv.logger.info("Thread is stopped")
        self.is_start = False
