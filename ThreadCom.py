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
        print('\t\tYes, Thread is started!')
        self.db_conn = sqlite3.connect(self.db_path)
        try:
            self.ser = serial.Serial(self.device_com)
            self.ser.flushInput()
            self.ser.flushOutput()
            while self.is_start:
                line = self.ser.readline().strip()
                self.insert_data(line)
                #
                # if self.count_ard_reboot > 14400:
                #     print('Start arduino reboot')
                #     self.ser = None
                #     self.ser = None
                #     time.sleep(1)
                #     self.ser = serial.Serial(self.device_com, 9600, timeout=5)
                #     self.ser.flush()
                #     self.count_ard_reboot = 0
                # string_bytes = self.ser.readline()
                # print('\t\t catched string: ', string_bytes)
                # if string_bytes == '':
                #     string_bytes = '0'
                # if string_bytes:
                #     self.my_signal.emit(string_bytes)  # QtCore.SIGNAL('DevStatusMessage(QString)')
                # self.count_ard_reboot += 1
                # time.sleep(1)
        except serial.SerialException as var:
            print('Thread is stopped')
            self.is_start = False
            self.my_signal.emit('Serial is broken')

    def insert_data(self, line):
        """
        Parse data and insert into db
        """
        #TODO: split on 2 funct: split string (use tests) and insert
        splitted = line.decode('utf-8').split(',')
        if len(splitted) != 6 or not splitted[0] == 'LY':  # .startswith('2022'):
            # TODO: set flang for start of each line from arduino (first n bites)
            return  # partial data, skipping
        print(line)
        splitted = splitted[1:]  # drop data start symbols
        timestamp = list(map(int, splitted[0].split('_')))
        unixtime = int(time.mktime(datetime.datetime(*timestamp).timetuple()))

        cursor = self.db_conn.cursor()
        for i in range(1, 5):
            v_splitted = splitted[i].split('_')
            v_type = v_splitted[0]
            v_value = float(v_splitted[1])
            print(v_type, v_value)
            cursor.execute(
                """
                INSERT INTO ambient_data (
                    unixtime,
                    type,
                    value
                ) VALUES (?, ?, ?)
                """, (unixtime, v_type, v_value))
        self.db_conn.commit()
        self.SER_UPDATE_SIGNAL.emit('Data Ready')

    def quit(self):
        self.is_start = False