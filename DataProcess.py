from PyQt5 import QtGui, QtCore, QtWidgets
import TableImplementation
import SharedVars as shv


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


def set_table_data(
        data_to_table,
        tv_data_widget,
        time_stamp
):
    """
    Process and display data in QTableView widget
    :param data_to_table: list, data lists for each iteration
    :param tv_data_widget: PyQt5.Widgets.QTableView, main table for display COM data
    :param time_stamp: str, time
    :return: int, if process without errors, None otherwise
    """
    shv.logger.debug('\t gat data to table: {}'.format(data_to_table))
    shv.all_headers[1].insert(0, time_stamp)
    data_line = []
    for data_type in data_to_table:
        shv.all_headers[0].append(
            '{} {}'.format(
                data_type,
                shv.all_units[data_type]
            )
        )
        data_line.append(data_to_table[data_type])
    shv.all_table_data.insert(0, data_to_table[data_line])

    shv.logger.debug('\t set new table for QWidget')
    tv_model = TableImplementation.MyTableModel(
        shv.all_table_data,
        shv.all_headers
    )
    tv_data_widget.setModel(tv_model)
    return 1