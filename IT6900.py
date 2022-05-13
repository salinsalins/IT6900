#!/usr/bin/env python
# -*- coding: utf-8 -*-
import time
import sys
import serial

from EmultedIT6900AtComPort import EmultedIT6900AtComPort
from ComPort import ComPort

sys.path.append('../TangoUtils')
from Moxa import MoxaTCPComPort
from config_logger import config_logger
from log_exception import log_exception

LF = b'\n'
DEVICE_NAME = 'IT6900'
DEVICE_FAMILY = 'IT6900 family Power Supply'
ID_OK = 'ITECH Ltd., IT69'
MIN_TIMEOUT = 0.1
READ_TIMEOUT = 0.5


class IT6900Exception(Exception):
    pass


class IT6900:

    def __init__(self, port: str, *args, **kwargs):
        # configure logger
        self.logger = kwargs.get('logger', config_logger())
        # parameters
        self.io_count = 0
        self.io_error_count = 0
        self.avg_io_time = 0.0
        self.max_io_time = 0.0
        self.min_io_time = 1000.0
        #
        self.port = port.strip()
        self.args = args
        self.kwargs = kwargs
        #
        self.command = b''
        self.response = b''
        # timeouts
        self.timeout_time = float('inf')
        # default com port, id, and serial number
        self.com = None
        self.id = 'Unknown Device'
        self.type = 'Unknown Device'
        self.sn = ''
        self.max_voltage = float('inf')
        self.max_current = float('inf')
        self.ready = False
        # create and open COM port
        self.com = self.create_com_port()
        if self.com is None:
            self.logger.error('Can not open serial port')
            self.ready = False
            return
        # further initialization (for possible async use)
        self.init()

    def init(self):
        # switch to remote mode
        self.switch_remote()
        self.clear_status()
        # device id, sn and type
        self.id = self.read_device_id()
        if not self.id.startswith(ID_OK):
            self.ready = False
            self.logger.error('%s initialization error', DEVICE_NAME)
            return
        self.ready = True
        self.sn = self.read_serial_number()
        self.type = self.read_device_type()
        # read maximal voltage and current
        if self.send_command(b'VOLT? MAX'):
            self.max_voltage = float(self.response[:-1])
        if self.send_command(b'CURR? MAX'):
            self.max_current = float(self.response[:-1])
        msg = 'Device has been initialized %s' % self.id
        self.logger.debug(msg)

    def create_com_port(self):
        self.com = ComPort(self.port, *self.args, emulated=EmultedIT6900AtComPort, **self.kwargs)
        if self.com.ready:
            self.logger.debug('Port %s is ready', self.port)
        else:
            self.logger.error('Port %s creation error', self.port)
        return self.com

    def close_com_port(self):
        self.ready = False
        try:
            self.com.close()
        except:
            log_exception(self)

    def send_command(self, cmd, check_response=None):
        self.io_count += 1
        try:
            # unify command
            cmd = cmd.upper().strip()
            # convert str to bytes
            if isinstance(cmd, str):
                cmd = str.encode(cmd)
            if not cmd.endswith(LF):
                cmd += LF
            self.response = b''
            t0 = time.perf_counter()
            # write command
            if not self.write(cmd):
                return False
            if check_response is None:
                if b'?' in cmd:
                    check_response = True
                else:
                    check_response = False
            if not check_response:
                return True
            # read response (to LF by default)
            result = self.read_response()
            # reding time stats
            dt = time.perf_counter() - t0
            self.min_io_time = min(self.min_io_time, dt)
            self.max_io_time = max(self.max_io_time, dt)
            self.avg_io_time = (self.avg_io_time * (self.io_count - 1) + dt) / self.io_count
            if not result:
                self.io_error_count += 1
            self.logger.debug('%s -> %s, %s, %4.0f ms', cmd, self.response, result, dt * 1000)
            return result
        except:
            self.io_error_count += 1
            log_exception(self, 'Command %s exception', cmd)
            return False

    @property
    def timeout(self):
        if time.perf_counter() > self.timeout_time:
            return True
        return False

    @timeout.setter
    def timeout(self, value):
        if value is not None:
            self.timeout_time = time.perf_counter() + value
        else:
            self.timeout_time = float('inf')

    def read(self, size=1, timeout=None):
        result = b''
        self.timeout = timeout
        try:
            while len(result) < size:
                if self.com.in_waiting > 0:
                    r = self.com.read(1)
                    if len(r) > 0:
                        result += r
                if self.timeout:
                    self.logger.error('Reading timeout')
                    return result
        except:
            log_exception(self)
        return result

    def read_until(self, terminator=LF, size=None, timeout=READ_TIMEOUT):
        result = b''
        r = b''
        while terminator not in r:
            r = self.read(1, timeout=timeout)
            if len(r) <= 0:
                return result
            result += r
            if size is not None and len(result) >= size:
                return result
        return result

    def read_response(self, expected=LF):
        result = self.read_until(expected)
        self.response = result
        if expected not in result:
            self.logger.error('Response %s without %s ', result, expected)
            return False
        return True

    def write(self, cmd):
        # t0 = time.perf_counter()
        try:
            # reset buffers
            self.com.reset_input_buffer()
            self.com.reset_output_buffer()
            # write command
            length = self.com.write(cmd)
            if len(cmd) != length:
                self.logger.error('Write error %s of %s' % (length, len(cmd)))
                return False
            # dt = (time.perf_counter() - t0) * 1000.0
            # self.logger.debug('%s %s bytes in %4.0f ms', cmd, length, dt)
            return True
        except:
            log_exception(self, 'Exception during write')
            return False

    def read_value(self, cmd, v_type=float):
        try:
            if self.send_command(cmd):
                return v_type(self.response)
            else:
                return None
        except:
            self.logger.debug('Can not convert %s to %s', self.response, v_type)
            return None

    def write_value(self, cmd, value):
        if isinstance(cmd, str):
            cmd = cmd.encode()
        cmd1 = cmd.upper().strip()
        cmd2 = cmd1 + b' ' + str(value).encode() + b';' + cmd1 + b'?'
        v = self.read_value(cmd2, type(value))
        return value == v

    def write_output(self, value: bool):
        if value:
            t_value = 'ON'
        else:
            t_value = 'OFF'
        self.write_value(b'OUTP', t_value)
        return bool(self.response[:-1]) == value

    def write_voltage(self, value: float):
        return self.write_value(b'VOLT', value)

    def write_current(self, value: float):
        return self.write_value(b'CURR', value)

    def read_output(self):
        if not self.send_command(b'OUTP?'):
            return None
        response = self.response.upper()
        if response.startswith((b'ON', b'1')):
            return True
        if response.startswith((b'OFF', b'0')):
            return False
        self.logger.info('Unexpected response %s' % response)
        return None

    def read_current(self):
        return self.read_value(b'MEAS:CURR?')

    def read_programmed_current(self):
        return self.read_value(b'CURR?')

    def read_voltage(self):
        return self.read_value(b'MEAS:VOLT?')

    def read_programmed_voltage(self):
        return self.read_value(b'VOLT?')

    def read_power(self):
        return self.read_value(b'MEAS:POW?')

    def read_device_id(self):
        try:
            if self.send_command(b'*IDN?'):
                return self.response[:-1].decode()
            else:
                return 'Unknown Device'
        except:
            return 'Unknown Device'

    def read_serial_number(self):
        try:
            if self.send_command(b'*IDN?'):
                serial_number = self.response[:-1].decode().split(',')[2]
                return serial_number
            else:
                return ""
        except:
            return ""

    def read_device_type(self):
        try:
            if self.send_command(b'*IDN?'):
                return self.response[:-1].decode().split(',')[1]
            else:
                return "Unknown Device"
        except:
            return "Unknown Device"

    def read_errors(self):
        if self.send_command(b'SYST:ERR?'):
            return self.response[:-1].decode()
        else:
            return ''

    def switch_local(self):
        return self.send_command(b'SYST:LOC', False)

    def clear_status(self):
        return self.send_command(b'*CLS', False)

    def switch_remote(self):
        return self.send_command(b'SYST:REM', False)

    def reconnect(self, port=None, *args, **kwargs):
        if port is not None:
            self.port = port.strip()
        if len(args) > 0:
            self.args = args
        if len(kwargs) > 0:
            self.kwargs = kwargs
        self.ready = False
        self.close_com_port()
        self.com = self.create_com_port()
        # self.com.reset_output_buffer()
        # self.com.reset_input_buffer()
        # self.send_command('*IDN?', False)
        self.init()
        # print(self.read_errors())

    def initialized(self):
        return self.ready

    def detect_baud(self):
        if self.ready:
            return
        bauds = (115200, 9600, 4800, 19200, 38400, 57600)
        #bauds = (115200,)
        for baud in bauds:
            self.logger.debug('Try reconnect at %s', baud)
            self.kwargs['baudrate'] = baud
            time.sleep(2.0)
            self.reconnect()
            if self.ready:
                self.logger.debug('Reconnected successfully at %s', baud)
                return


if __name__ == "__main__":
    pd1 = IT6900("COM3", baudrate=115200, emulated=EmultedIT6900AtComPort)
    # pd1.detect_baud()
    for i in range(100):
        cmd = "*IDN?"
        t_0 = time.time()
        v1 = pd1.send_command(cmd)
        dt1 = int((time.time() - t_0) * 1000.0)  # ms
        print(pd1.port, cmd, '->', pd1.response, v1, '%4d ms ' % dt1)
        cmd = "VOLT?"
        t_0 = time.time()
        v1 = pd1.send_command(cmd)
        dt1 = int((time.time() - t_0) * 1000.0)  # ms
        print(pd1.port, cmd, '->', pd1.response, v1, '%4d ms ' % dt1)
    print('Errors', pd1.read_errors())
    print('Total I/O:', pd1.io_count)
    print('Total Errors:', pd1.io_error_count)
    print('min I/O time:', pd1.min_io_time)
    print('max I/O time:', pd1.max_io_time)
    print('avg I/O time:', pd1.avg_io_time)
