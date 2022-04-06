from PyQt5 import QtGui, QtCore, QtWidgets


class InfoWindow:
    def __init__(self, parent = None):
        self.parent = None

    def write(self, logmessage, *args, **kwargs):
        """
        Show information window to user
        :param logmessage: information in logging message
        :return: None
        """
        # saved_args = locals()  # print locals() to see what pass
        logmessage = logmessage.split(',')
        logtype = logmessage[0]
        logtime = logmessage[1]
        logdata = logmessage[3]
        logtext = logmessage[4]
        QtWidgets.QMessageBox.about(
            self.parent,
            '{} {}'.format(logtype, logdata),
            '{} {} \n {}: {}'.format(
                logtype,
                logdata,
                logtime,
                logtext
            )
        )