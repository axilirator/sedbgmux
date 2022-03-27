#!/usr/bin/env python3

# This file is a part of sedbgmux, an open source DebugMux client.
# Copyright (c) 2022  Vadim Yanitskiy <axilirator@gmail.com>
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

import logging as log
import serial
import abc


class Transport(abc.ABC):
    ''' Abstract transport layer for DebugMux '''

    def connect(self, opts: dict) -> None:
        ''' Establish connection to the target and enter DebugMux mode '''

    def disconnect(self) -> None:
        ''' Escape DebugMux mode and terminate connection with the target '''

    def write(self, data: bytes) -> int:
        ''' Write the given data bytes '''

    def read(self, length: int = 0) -> bytes:
        ''' Read the given number of bytes '''


class TransportModem(Transport):
    ''' Modem based transport layer for DebugMux '''

    def __init__(self, opts: dict) -> None:
        self.modem_port = opts.serial_port
        self.modem_baudrate = opts.serial_baudrate
        self.modem_timeout = opts.serial_timeout

    def connect(self) -> None:
        ''' Establish connection to the target and enter DebugMux mode '''
        self._sl = serial.Serial(port=self.modem_port,
                                 baudrate=self.modem_baudrate,
                                 bytesize=8, parity='N', stopbits=1,
                                 timeout=self.modem_timeout,
                                 # xonoff=False,
                                 rtscts=False,
                                 dsrdtr=False)

        # Test the modem
        self.transceive('AT', 'OK')
        # Enable DebugMux mode
        self.transceive('AT*EDEBUGMUX', 'CONNECT')

    def disconnect(self) -> None:
        ''' Escape DebugMux mode and terminate connection with the target '''
        # TODO: escape DebugMux mode
        self._sl.close()
        del self._sl

    def write(self, data: bytes) -> int:
        ''' Write the given data bytes '''
        return self._sl.write(data)

    def read(self, length: int = 0) -> bytes:
        ''' Read the given number of bytes '''
        return self._sl.read(length)

    def send_at_cmd(self, cmd: str, handle_echo: bool = True) -> None:
        ''' Send an AT command to the modem '''
        data: bytes = cmd.encode() + b'\r'
        log.debug('MODEM <- %s', str(data))
        self.write(data)
        while handle_echo:
            rdata: bytes = self._sl.readline()
            line: str = rdata.rstrip().decode()
            if not line:
                continue  # Ignore empty lines
            if line == cmd:
                break
            log.debug('MODEM -> %s', str(rdata))

    def read_at_rsp(self) -> str:
        ''' Read an AT command response from the modem '''
        while True:
            rdata: bytes = self._sl.readline()
            line: str = rdata.rstrip().decode()
            if not line:
                continue  # Ignore empty lines
            log.debug('MODEM -> %s', str(rdata))
            if line.startswith(('+', '*')):
                continue  # Ignore events reported by the modem
            return line

    def transceive(self, cmd: str, exp: str) -> None:
        self.send_at_cmd(cmd)
        rsp = self.read_at_rsp()
        assert rsp == exp
