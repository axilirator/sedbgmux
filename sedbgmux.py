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
import argparse
import cmd2
import enum
import sys

from transport import TransportModem
from proto import DbgMuxFrame
from peer import DbgMuxPeer


class SEDbgMuxApp(cmd2.Cmd):
    DESC = 'DebugMux client for [Sony] Ericsson phones and modems'

    # Command categories
    CATEGORY_CONN = 'Connection management commands'
    CATEGORY_DBGMUX = 'DebugMux specific commands'

    def __init__(self, argv):
        super().__init__(allow_cli_args=False)

        self.intro = cmd2.style('Welcome to %s!' % self.DESC, fg=cmd2.fg.red)
        self.prompt = 'DebugMux (\'%s\')> ' % argv.serial_port
        self.default_category = 'Built-in commands'
        self.argv = argv

        # Init the transport layer and DebugMux peer
        self.transport = TransportModem(self.argv)
        self.peer = DbgMuxPeer(self.transport)

        # Modem connection state
        self.set_connected(False)

    def set_connected(self, state: bool) -> None:
        self.connected: bool = state
        if self.connected:
            self.enable_category(self.CATEGORY_DBGMUX)
        else:
            msg = 'You must be connected to use this command'
            self.disable_category(self.CATEGORY_DBGMUX, msg)

    @cmd2.with_category(CATEGORY_CONN)
    def do_connect(self, opts) -> None:
        ''' Connect to the modem and switch it to DebugMux mode '''
        self.transport.connect()
        self.set_connected(True)

    @cmd2.with_category(CATEGORY_CONN)
    def do_disconnect(self, opts) -> None:
        ''' Disconnect from the modem '''
        self.transport.disconnect()
        self.set_connected(False)

    @cmd2.with_category(CATEGORY_CONN)
    def do_status(self, opts) -> None:
        ''' Print connection info and statistics '''
        if not self.connected:
            self.poutput('Not connected')
            return
        self.poutput('Connected to \'%s\'' % self.argv.serial_port)
        self.poutput('Baudrate: %d' % self.argv.serial_baudrate)
        self.poutput('TxCount (Ns): %d' % self.peer.tx_count)
        self.poutput('RxCount (Nr): %d' % self.peer.rx_count)

    @cmd2.with_category(CATEGORY_DBGMUX)
    def do_enquiry(self, opts) -> None:
        ''' Enquiry target identifier and available Data Providers '''
        self.peer.send(DbgMuxFrame.MsgType.Enquiry)
        while True:
            f = self.peer.recv()
            if f['MsgType'] == DbgMuxFrame.MsgType.Ident:
                log.info("Identified target: '%s', IMEI=%s",
                         f['Msg']['Ident'][:-15],
                         f['Msg']['Ident'][-15:])
            elif f['MsgType'] == DbgMuxFrame.MsgType.DPAnnounce:
                log.info("Data Provider available (DPRef=0x%04x): '%s'",
                         f['Msg']['DPRef'], f['Msg']['Name'])

            # No more data in the buffer
            # FIXME: layer violation!
            if self.transport._sl.in_waiting == 0:
                break

        # ACKnowledge reception of the info
        self.peer.send(DbgMuxFrame.MsgType.Ack)

    ping_parser = cmd2.Cmd2ArgumentParser()
    ping_parser.add_argument('-p', '--payload',
                             type=str, default='Knock, knock!',
                             help='Ping payload')

    @cmd2.with_argparser(ping_parser)
    @cmd2.with_category(CATEGORY_DBGMUX)
    def do_ping(self, opts) -> None:
        ''' Send a Ping to the target, expect Pong '''
        log.info('Tx Ping with payload \'%s\'', opts.payload)
        self.peer.send(DbgMuxFrame.MsgType.Ping, opts.payload)

        f = self.peer.recv()
        assert f['MsgType'] == DbgMuxFrame.MsgType.Pong
        log.info('Rx Pong with payload \'%s\'', f['Msg'])
        self.peer.send(DbgMuxFrame.MsgType.Ack)

    establish_parser = cmd2.Cmd2ArgumentParser()
    establish_parser.add_argument('DPRef',
                                  type=lambda v: int(v, 16),
                                  help='DPRef of a Data Provider in hex')

    @cmd2.with_argparser(establish_parser)
    @cmd2.with_category(CATEGORY_DBGMUX)
    def do_establish(self, opts) -> None:
        ''' Establish connection with a Data Provider '''
        log.info("Establishing connection with DPRef=0x%04x", opts.DPRef)
        self.peer.send(DbgMuxFrame.MsgType.ConnEstablish,
                       dict(DPRef=opts.DPRef))

        f = self.peer.recv()
        assert f['MsgType'] == DbgMuxFrame.MsgType.ConnEstablished
        if f['Msg']['ConnRef'] == 0xffff:
            log.warning("Connection failed: unknown DPRef=0x%04x?", opts.DPRef)
            self.peer.send(DbgMuxFrame.MsgType.Ack)
            return

        log.info("Connection established (ConnRef=0x%04x)",
                 f['Msg']['ConnRef'])

        # Read the messages
        while True:
            f = self.peer.recv()

            if f['MsgType'] != DbgMuxFrame.MsgType.ConnData:
                log.warning('Unexpected frame: %s', f)
                self.peer.send(DbgMuxFrame.MsgType.Ack)
                continue
            try:  # FIXME: there can be binary data
                self.stdout.write(f['Msg']['Data'].decode())
            except:  # ... ignore it for now
                continue

            # ACKnowledge reception of a frame
            self.peer.send(DbgMuxFrame.MsgType.Ack)


ap = argparse.ArgumentParser(prog='sedbgmux', description=SEDbgMuxApp.DESC,
                             formatter_class=argparse.ArgumentDefaultsHelpFormatter)

group = ap.add_argument_group('Connection parameters')
group.add_argument('-p', '--serial-port', metavar='PORT', type=str, default='/dev/ttyACM0',
                   help='Serial port path (default %(default)s)')
group.add_argument('--serial-baudrate', metavar='BAUDRATE', type=int, default=115200,
                   help='Serial port speed (default %(default)s)')
group.add_argument('--serial-timeout', metavar='TIMEOUT', type=int,
                   help='Serial port timeout')

log.basicConfig(
    format='[%(levelname)s] %(filename)s:%(lineno)d %(message)s', level=log.INFO)

if __name__ == '__main__':
    argv = ap.parse_args()
    app = SEDbgMuxApp(argv)
    sys.exit(app.cmdloop())
