# -*- coding: utf-8 -*-

from PyQt5 import QtGui, QtCore, QtWidgets


class MyTableModel(QtCore.QAbstractTableModel):
    # class for tables model

    def __init__(self, datain=[[]], headerdata=[], parent=None, *args):
        """
        :param datain: a list of lists with data
        :param headerdata: a two list in list with headers data
        :param parent: parent class
        :param args: None
        """
        QtCore.QAbstractTableModel.__init__(self, parent, *args)
        self.arraydata = datain
        self.headerdata = headerdata

    def rowCount(self, parent):
        return len(self.arraydata)

    def columnCount(self, parent):
        return len(self.arraydata[0])

    def flags(self, index):
        return QtCore.Qt.ItemIsEditable | QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable

    def data(self, index, role):
        if role == QtCore.Qt.EditRole:
            row = index.row()
            column = index.column()
            return self.arraydata[row][column]

        if role == QtCore.Qt.ToolTipRole:
            # row = index.row()
            # column = index.column()
            return 'data for peak'

        if role == QtCore.Qt.DisplayRole:
            row = index.row()
            column = index.column()
            value = self.arraydata[row][column]
            return value

    def setData(self, index, value, role=QtCore.Qt.EditRole):
        if role == QtCore.Qt.EditRole:
            row = index.row()
            column = index.column()
            if value.isValid():
                # May be use try, IndexError exept if None value
                value = value.toPyObject()
                self.arraydata[row][column] = value
                self.dataChanged.emit(index, index)
                return True
        return False

    def headerData(self, section, orientation, role):
        if role == QtCore.Qt.DisplayRole:
            if orientation == QtCore.Qt.Horizontal:
                if section < len(self.headerdata[0]):
                    return self.headerdata[0][section]
                else:
                    return 'not implemented'
                # return QtCore.QString(self.headerdata[0].column())
            else:
                if section < len(self.headerdata[1]):
                    return self.headerdata[1][section]
                else:
                    return 'not implemented'
                # return QtCore.QString(self.headerdata[1].column())

    def insertRow(self, position, rows, parent=QtCore.QModelIndex()):
        self.beginInsertRows(parent, position, position + rows - 1)
        for i in range(rows):
            default_values = '0'
            self.arraydata.insert(position, default_values)
        self.endInsertRows()
        return True

    def insertColumns(self, position, columns, parent=QtCore.QModelIndex()):
        self.beginInsertColumns(parent, position, position + columns - 1)
        row_count = len(self.arraydata)
        for i in range(columns):
            for j in range(row_count):
                self.arraydata[j].insert(position, '0')
        self.endInsertColumns()
        return True
