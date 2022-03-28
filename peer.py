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

from typing import Any
from construct import Const, Container, Int16ul

from transport import Transport
from proto import DbgMuxFrame


class DbgMuxPeer:
    def __init__(self, io: Transport):
        self.tx_count: int = 0
        self.rx_count: int = 0
        self.io = io

    def send(self, msg_type: DbgMuxFrame.MsgType, msg: Any = b'') -> None:
        # Encode the inner message first
        msg_data = DbgMuxFrame.Msg.build(msg, MsgType=msg_type)

        c = Container({
            'TxCount': (self.tx_count + 1) % 256,
            'RxCount': self.rx_count % 256,
            'MsgType': msg_type,
            'MsgData': msg_data,
            'FCS': 0  # Calculated below
        })

        # ACK is a bit special
        if msg_type == DbgMuxFrame.MsgType.Ack:
            c['TxCount'] = 0xf1

        # There is a Checksum construct, but it requires all checksummed fields
        # to be wrapped into an additional RawCopy construct.  This is ugly and
        # inconvinient from the API point of view, so we calculate the FCS manually:
        frame = DbgMuxFrame.Frame.build(c)[:-2]  # strip b'\x00\x00'
        c['FCS'] = DbgMuxFrame.fcs_func(frame)

        log.debug('Tx frame (Ns=%03u, Nr=%03u, fcs=0x%04x) %s %s',
                  c['TxCount'], c['RxCount'], c['FCS'],
                  c['MsgType'], c['MsgData'].hex())

        self.io.write(frame + Int16ul.build(c['FCS']))

        # ACK is not getting accounted
        if msg_type != DbgMuxFrame.MsgType.Ack:
            self.tx_count += 1

    def recv(self) -> Container:
        frame: bytes = b''
        frame += self.io.read(2)  # Magic
        Const(b'\x42\x42').parse(frame[:2])
        frame += self.io.read(2)  # Length
        length: int = Int16ul.parse(frame[2:])
        frame += self.io.read(length)  # Rest

        c = DbgMuxFrame.Frame.parse(frame)

        log.debug('Rx frame (Ns=%03u, Nr=%03u, fcs=0x%04x) %s %s',
                  c['TxCount'], c['RxCount'], c['FCS'],
                  c['MsgType'], c['MsgData'].hex())

        # Parse the inner message
        c['Msg'] = DbgMuxFrame.Msg.parse(c['MsgData'], MsgType=c['MsgType'])

        self.rx_count += 1
        return c
