from PyQt5 import QtCore
import requests
import time
import sqlite3
import SharedVars as shv


class SendThread (QtCore.QThread):
    # Class for get ambient data

    def __init__(self, db_path, parent=None):
        QtCore.QThread.__init__(self, parent)
        self.db_path = db_path
        self.db_conn = None
        self.last_send = {}
        self.shifr = {
            'P': 'air_pressure',
            'R': 'humidity',
            'T': 'temperature'
        }
        self.is_run = True

    def run(self):
        shv.logger.info("Run thread for Send data")
        self.db_conn = sqlite3.connect(self.db_path, check_same_thread=False)

        while self.is_run:
            seen_data = False
            for dtype in ['T', 'R', 'P']:
                cursor = self.db_conn.cursor()
                cursor.execute(
                    """
                    select unixtime from send_status where type = ? 
                    """,  # limit 10
                    (dtype,)
                )
                res = cursor.fetchall()
                if res:
                    self.last_send[dtype] = res[0][0]

                cursor.execute(
                    """
                    select unixtime, value from ambient_data where type = ? AND unixtime > ? limit 1
                    """,  # limit 10
                    (dtype, self.last_send.get(dtype, 0))
                )
                res = cursor.fetchall()
                if not res:
                    continue

                seen_data = True
                try:
                    pure_dtype = self.shifr[dtype]
                    back_url = 'http://192.168.0.15:9000/ambient-data/'
                    rres = requests.post(
                        back_url,
                        json={
                            'device_id': '00000000-0000-0000-0000-000000000000',
                            'data_type': pure_dtype,
                            'start_ts': str(res[0][0]),
                            'data_pack': [str(int(res[0][1]))]
                        }
                    )
                    rres.raise_for_status()
                    if dtype in self.last_send:
                        cursor.execute(
                            """
                            update send_status SET unixtime = ? WHERE type = ?
                            """,
                            (res[0][0], dtype)
                        )
                    else:
                        cursor.execute(
                            """
                            insert into send_status (unixtime, type) values (?, ?)
                            """,
                            (res[0][0], dtype)
                        )
                    self.db_conn.commit()
                except Exception as exc:
                    print('%r', exc)
                    shv.logger.error('%r', exc)

            if not seen_data:
                time.sleep(5)

    def quit(self):
        shv.logger.info("Thread is stopped")
        self.is_run = False
