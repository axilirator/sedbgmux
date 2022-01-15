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
import serial
import cmd2
import enum
import sys

from proto import DbgMuxFrame
from peer import DbgMuxPeer

class SEDbgMuxApp(cmd2.Cmd):
	DESC = 'DebugMux client for [Sony] Ericsson phones and modems'

	def __init__(self, argv):
		super().__init__(allow_cli_args=False)

		self.intro = cmd2.style('Welcome to %s!' % self.DESC, fg=cmd2.fg.red)
		self.prompt = 'DebugMux (\'%s\')> ' % argv.serial_port
		self.argv = argv

		# Modem connection state
		self.connected = False

	def do_connect(self, opts) -> None:
		''' Connect to the modem and switch it to DebugMux mode '''
		slp = {
			'port'		: self.argv.serial_port,
			'baudrate'	: self.argv.serial_baudrate,
			'bytesize'	: 8,
			'parity'	: 'N',
			'stopbits'	: 1,
			'timeout'	: self.argv.serial_timeout,
			# 'xonoff'	: False,
			'rtscts'	: False,
			'dsrdtr'	: False,
		}
		self.sl = serial.Serial(**slp)

		# Test the modem
		self.transceive('AT', 'OK')
		# Enable DebugMux mode
		self.transceive('AT*EDEBUGMUX', 'CONNECT')
		# Init DebugMux peer
		self.peer = DbgMuxPeer(self.sl)
		self.connected = True

	def do_disconnect(self, opts) -> None:
		''' Disconnect from the modem '''
		self.sl.close()
		self.sl = None
		self.peer = None
		self.connected = False

	def do_enquiry(self, opts) -> None:
		''' Enquiry target identifier and available Data Providers '''
		self.peer.send(DbgMuxFrame.MsgType.Enquiry)
		while True:
			f = self.peer.recv()
			if f['MsgType'] == DbgMuxFrame.MsgType.Ident:
				msg = DbgMuxFrame.MsgIdent.parse(f['MsgData'])
				log.info("Identified target: '%s', IMEI=%s",
					 msg['Ident'][:-15], msg['Ident'][-15:])
			elif f['MsgType'] == DbgMuxFrame.MsgType.DPAnnounce:
				msg = DbgMuxFrame.MsgDPAnnounce.parse(f['MsgData'])
				log.info("Data Provider available (DPRef=0x%04x): '%s'",
					 msg['DPRef'], msg['Name'])

			# No more data in the buffer
			if self.sl.in_waiting == 0:
				break

		# ACKnowledge reception of the info
		self.peer.send(DbgMuxFrame.MsgType.Ack)

	ping_parser = cmd2.Cmd2ArgumentParser()
	ping_parser.add_argument('-p', '--payload',
				 type=str, default='Knock, knock!',
				 help='Ping payload')

	@cmd2.with_argparser(ping_parser)
	def do_ping(self, opts) -> None:
		''' Send a Ping to the target, expect Pong '''
		msg = DbgMuxFrame.MsgPingPong

		log.info('Tx Ping with payload \'%s\'', opts.payload)
		self.peer.send(DbgMuxFrame.MsgType.Ping, msg.build(opts.payload))

		f = self.peer.recv()
		assert(f['MsgType'] == DbgMuxFrame.MsgType.Pong)
		log.info('Rx Pong with payload \'%s\'', msg.parse(f['MsgData']))

	establish_parser = cmd2.Cmd2ArgumentParser()
	establish_parser.add_argument('DPRef',
				      type=lambda v: int(v, 16),
				      help='DPRef of a Data Provider in hex')

	@cmd2.with_argparser(establish_parser)
	def do_establish(self, opts) -> None:
		''' Establish connection with a Data Provider '''
		log.info("Establishing connection with DPRef=0x%04x", opts.DPRef)
		self.peer.send(DbgMuxFrame.MsgType.ConnEstablish,
			       DbgMuxFrame.MsgConnEstablish.build({ 'DPRef' : opts.DPRef }))

		f = self.peer.recv()
		assert(f['MsgType'] == DbgMuxFrame.MsgType.ConnEstablished)
		ConnRef = DbgMuxFrame.MsgConnEstablished.parse(f['MsgData'])['ConnRef']
		log.info("Connection established (ConnRef=0x%04x)", ConnRef)

		# Read the messages
		while True:
			f = self.peer.recv()

			if f['MsgType'] != DbgMuxFrame.MsgType.ConnData:
				log.warning('Unexpected frame: %s', f)
				self.peer.send(DbgMuxFrame.MsgType.Ack)
				continue
			try: # FIXME: there can be binary data
				msg = DbgMuxFrame.MsgConnData.parse(f['MsgData'])
				self.stdout.write(msg['Data'].decode())
			except: # ... ignore it for now
				continue

			# ACKnowledge reception of a frame
			self.peer.send(DbgMuxFrame.MsgType.Ack)

	def send_data(self, data: bytes) -> None:
		log.debug("MODEM <- %s", str(data))
		self.sl.write(data)

	def send_at_cmd(self, cmd: str, handle_echo:bool = True) -> None:
		self.send_data(cmd.encode() + b'\r')
		if handle_echo:
			self.sl.readline()

	def read_at_rsp(self) -> str:
		rsp = self.sl.readline()
		log.debug("MODEM -> %s", str(rsp))
		return rsp.rstrip().decode()

	def transceive(self, cmd: str, exp: str) -> None:
		while True:
			self.send_at_cmd(cmd)
			rsp = self.read_at_rsp()

			if rsp[:7] == '*EMRDY:':
				continue
			assert(rsp == exp)
			break

ap = argparse.ArgumentParser(prog='sedbgmux', description=SEDbgMuxApp.DESC,
			     formatter_class=argparse.ArgumentDefaultsHelpFormatter)

group = ap.add_argument_group('Connection parameters')
group.add_argument('-p', '--serial-port', metavar='PORT', type=str, default='/dev/ttyACM0',
		   help='Serial port path (default %(default)s)')
group.add_argument('--serial-baudrate', metavar='BAUDRATE', type=int, default=115200,
		   help='Serial port speed (default %(default)s)')
group.add_argument('--serial-timeout', metavar='TIMEOUT', type=int,
		   help='Serial port timeout')

log.basicConfig(format='[%(levelname)s] %(filename)s:%(lineno)d %(message)s', level=log.INFO)

if __name__ == '__main__':
	argv = ap.parse_args()
	app = SEDbgMuxApp(argv)
	sys.exit(app.cmdloop())
