# -*- coding: utf-8 -*-

import time
from threading import Lock

COMMANDS = (b'OUTP?', b'VOLT?', b'MEAS:VOLT?', b'CURR?', b'MEAS:CURR?', b'*IDN?', b'*SN?',
            b'MEAS:POW?', b'SYST:ERR?', b'SYST:LOC', b'*CLS', b'SYST:REM', b'VOLT? MAX',
            b'CURR? MAX')
LF = b'\n'

class EmultedIT6900AtComPort:
    SN = 123456
    RESPONSE_DELAY = 0.035
    ID = 'ITECH Ltd., IT6900EMULATED,  800774011776810024,  1.14-1.08'

    def __init__(self, port, *args, **kwargs):
        self.port = port
        self.last_address = -1
        self.lock = Lock()
        self.online = False
        self.last_write = b''
        self.pv = {}
        self.pc = {}
        self.mv = {}
        self.mc = {}
        self.out = {}
        self.sn = {}
        self.id = {}
        self.t = {}
        self.write_error = False
        self.add_device()

    def close(self):
        self.last_write = b''
        self.online = False
        return True

    def add_device(self):
        if self.last_address not in self.pv:
            self.id[self.last_address] = EmultedIT6900AtComPort.ID
            self.pv[self.last_address] = 0.0
            self.pc[self.last_address] = 0.0
            self.mv[self.last_address] = 0.0
            self.mc[self.last_address] = 0.0
            self.out[self.last_address] = False
            self.sn[self.last_address] = str(EmultedIT6900AtComPort.SN).encode()
            EmultedIT6900AtComPort.SN += 1

    def write(self, cmd, timeout=None):
        self.last_write = cmd
        self.write_error = False
        commands = cmd[:-1].split(b';')
        for c in commands:
            try:
                if c.startswith(b'ADDR '):
                    self.last_address = int(self.last_write[5:])
                    self.add_device()
                elif c.startswith(b'VOLT '):
                    self.pv[self.last_address] = float(cmd[3:])
                elif c.startswith(b'CURR '):
                    self.pc[self.last_address] = float(cmd[3:])
                elif c.startswith(b'OUTP ON') or c.startswith(b'OUTP 1'):
                    self.out[self.last_address] = True
                elif c.startswith(b'OUTP OF') or c.startswith(b'OUTP 0'):
                    self.out[self.last_address] = False
                else:
                    if c not in COMMANDS:
                        self.write_error = True
                self.t[self.last_address] = time.perf_counter()
                return len(cmd)
            except:
                self.write_error = True
                self.t[self.last_address] = time.perf_counter()
                return len(cmd)

    def read(self, size=1, timeout=None):
        if self.last_write == b'':
            return b''
        if time.perf_counter() - self.t[self.last_address] < self.RESPONSE_DELAY:
            return b''
        self.t[self.last_address] = time.perf_counter()
        if self.write_error:
            self.last_write = b''
            return b''
        # if self.last_write.startswith(b'ADR '):
        #     self.last_write = b''
        #     return b'OK\r'
        if self.last_write.startswith(b'MEAS:POW?'):
            if self.out[self.last_address]:
                self.mv[self.last_address] = self.pv[self.last_address]
            else:
                self.mv[self.last_address] += 0.5
                if self.mv[self.last_address] > 10.0:
                    self.mv[self.last_address] = 0.0
            self.last_write = b''
            return str(self.mv[self.last_address]).encode() + LF
        if self.last_write.startswith(b'VOLT?'):
            self.last_write = b''
            return str(self.pv[self.last_address]).encode() + LF
        if self.last_write.startswith(b'MEAS:VOLT?'):
            if self.out[self.last_address]:
                self.mv[self.last_address] = self.pv[self.last_address]
            else:
                self.mv[self.last_address] += 0.5
                if self.mv[self.last_address] > 10.0:
                    self.mv[self.last_address] = 0.0
            self.last_write = b''
            return str(self.mv[self.last_address]).encode() + LF
        if self.last_write.startswith(b'CURR?'):
            self.last_write = b''
            return str(self.pc[self.last_address]).encode() + LF
        if self.last_write.startswith(b'MEAS:CURR?'):
            if self.out[self.last_address]:
                self.mc[self.last_address] = self.pc[self.last_address]
            else:
                self.mv[self.last_address] += 1.0
                if self.mv[self.last_address] > 100.0:
                    self.mv[self.last_address] = 0.0
            self.last_write = b''
            return str(self.mv[self.last_address]).encode() + LF
        if self.last_write.startswith(b'*IDN?'):
            self.last_write = b''
            return b'ITECH Ltd., IT6932EMULATED, 800774011776810024,  1.14-1.08\n'
        if self.last_write.startswith(b'OUTP?'):
            self.last_write = b''
            if self.out[self.last_address]:
                return b'ON\n'
            else:
                return b'OFF\n'
        if self.last_write.startswith(b'SYST:ERR?'):
            self.last_write = b''
            if self.write_error:
                return b'Unknown command\n'
            else:
                return b'No error\n'
        self.last_write = b''
        return b''

    def reset_input_buffer(self, timeout=None):
        return True

    def reset_output_buffer(self, timeout=None):
        return True

    def isOpen(self):
        return True

    @property
    def in_waiting(self):
        return 1
