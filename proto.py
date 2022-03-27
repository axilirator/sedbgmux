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

from construct import *

import crcmod


class DbgMuxFrame:
    ''' DebugMux frame definition '''

    # Kudos to Stefan @Sec Zehl for finding the CRC function parameters
    fcs_func = crcmod.mkCrcFun(0x11021, rev=True, initCrc=0x0, xorOut=0xffff)

    MsgType = Enum(subcon=Int8ul,
        Enquiry             = 0x65,  # 'e'
        Ident               = 0x66,  # 'f'
        Ping                = 0x67,  # 'g'
        Pong                = 0x68,  # 'h'
        DPAnnounce          = 0x69,  # 'i'
        # TODO:             = 0x6a,  # 'j'
        ConnEstablish       = 0x6b,  # 'k'
        ConnEstablished     = 0x6c,  # 'l'
        ConnTerminate       = 0x6d,  # 'm'
        ConnTerminated      = 0x6e,  # 'n'
        ConnData            = 0x6f,  # 'o'
        # TODO:             = 0x70,  # 'p'
        Ack                 = 0x71,  # 'q'
    )

    Frame = Struct(
        'Magic' / Const(b'\x42\x42'),
        'Length' / Rebuild(Int16ul, lambda ctx: len(ctx.MsgData) + 5),
        'TxCount' / Int8ul,
        'RxCount' / Int8ul,
        'MsgType' / MsgType,
        'MsgData' / Bytes(lambda ctx: ctx.Length - 5),
        'FCS' / Int16ul,  # fcs_func() on all preceeding fields
    )

    # MsgType.Ident structure
    MsgIdent = Struct(
        'Magic' / Bytes(4),  # TODO
        'Ident' / PascalString(Int8ul, 'ascii'),
    )

    # MsgType.{Ping,Pong} structure
    MsgPingPong = PascalString(Int8ul, 'ascii')

    # MsgType.DPAnnounce structure
    MsgDPAnnounce = Struct(
        'DPRef' / Int16ul,
        'Name' / PascalString(Int8ul, 'ascii'),
    )

    # MsgType.ConnEstablish[ed] structure
    MsgConnEstablish = Struct('DPRef' / Int16ul)
    MsgConnEstablished = Struct(
        'DPRef' / Int16ul,
        'ConnRef' / Int16ul,
        'DataBlockLimit' / Int16ul,
    )

    # MsgType.ConnTerminate[ed] structure
    MsgConnTerminate = Struct('ConnRef' / Int16ul)
    MsgConnTerminated = Struct(
        'DPRef' / Int16ul,
        'ConnRef' / Int16ul,
    )

    # MsgType.ConnData structure
    MsgConnData = Struct(
        'ConnRef' / Int16ul,
        'Data' / GreedyBytes,
    )

    # Complete message definition
    Msg = Switch(this.MsgType, default=GreedyBytes, cases={
        MsgType.Enquiry             : Const(b''),
        MsgType.Ident               : MsgIdent,
        MsgType.Ping                : MsgPingPong,
        MsgType.Pong                : MsgPingPong,
        MsgType.DPAnnounce          : MsgDPAnnounce,
        MsgType.ConnEstablish       : MsgConnEstablish,
        MsgType.ConnEstablished     : MsgConnEstablished,
        MsgType.ConnTerminate       : MsgConnTerminate,
        MsgType.ConnTerminated      : MsgConnTerminated,
        MsgType.ConnData            : MsgConnData,
        MsgType.Ack                 : Const(b''),
    })
