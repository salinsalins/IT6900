#!/usr/bin/env python
# -*- coding: utf-8 -*-
import time
import sys;
from multiprocessing import Lock

sys.path.append('../TangoUtils')

from EmultedIT6900AtComPort import EmultedIT6900AtComPort
from ComPort import ComPort

from config_logger import config_logger
from log_exception import log_exception

LF = b'\n'


class IT6900Exception(Exception):
    pass


class IT6900:
    ID_OK = 'ITECH'
    DEVICE_NAME = 'IT6900'
    DEVICE_FAMILY = 'IT6900 family Power Supply'
    _devices = []
    _lock = Lock()

    def __init__(self, port: str, *args, **kwargs):
        # defaults
        self.args = args
        self.kwargs = kwargs
        self.port = port.strip()
        # logger
        self.logger = kwargs.get('logger', config_logger())
        # timeout
        self.retries = kwargs.get('retries', 2)
        self.read_timeout = kwargs.get('read_timeout', 0.3)
        self.read_timeout_time = float('inf')
        self.suspend_to = 0.0
        self.suspend_delay = kwargs.get('suspend_delay', 6.0)
        self.reconnect_timeout_time = 0.0
        #
        self.command = b''
        self.response = b''
        # com port, id, and serial number
        self.com = None
        self.id = 'Unknown Device'
        self.type = 'Unknown Device'
        self.sn = ''
        # log prefix
        self.pre = f'{self.id} {self.port} '
        # max values
        self.max_voltage = float('inf')
        self.max_current = float('inf')
        #
        self.ready = False
        # io statistics
        self.io_count = 0
        self.io_error_count = 0
        self.avg_io_time = 0.0
        self.max_io_time = 0.0
        self.min_io_time = 1000.0
        #
        # create and open COM port
        self.com = self.create_com_port()
        # add to list
        with IT6900._lock:
            if self not in IT6900._devices:
                IT6900._devices.append(self)
        # further initialization (for possible async use)
        self.init()

    def init(self):
        # switch to remote mode
        self.switch_remote()
        self.clear_status()
        # read device id
        self.id = self.read_device_id(False)
        if not self.id_ok():
            self.suspend()
            self.logger.error(f'{self.pre}  Initialization error')
            return False
        self.ready = True
        # read serial number and type
        self.sn = self.read_serial_number()
        self.type = self.read_device_type()
        self.pre = f'{self.type} at {self.port} '
        # read maximal voltage and current
        try:
            if self.send_command(b'VOLT? MAX'):
                self.max_voltage = float(self.response[:-1])
            else:
                self.logger.warning(f'{self.pre} Max voltage can not be determined')
            if self.send_command(b'CURR? MAX'):
                self.max_current = float(self.response[:-1])
            else:
                self.logger.warning(f'{self.pre} Max current can not be determined')
        except KeyboardInterrupt:
            raise
        except:
            log_exception(self.logger, f'{self.pre} Init exception')
            self.suspend()
            return False
        self.logger.debug(f'{self.pre} Device has been initialized')
        return True

    def create_com_port(self):
        self.com = ComPort(self.port, *self.args, emulated=EmultedIT6900AtComPort, **self.kwargs)
        return self.com

    def close_com_port(self):
        self.ready = False
        try:
            self.com.close()
        except KeyboardInterrupt:
            raise
        except:
            log_exception(self.logger, f'{self.pre} COM port close exception')

    def send_command(self, command,
                     check_response: bool = None,
                     check_ready: bool = True) -> bool:
        # command (bytes or str) - input command
        # check_response (bool or None) - if None check response if command contains b'?'
        # returns True or False
        self.io_count += 1
        try:
            if check_ready and not self.ready:
                return False
            # convert str to bytes
            if isinstance(command, str):
                command = str.encode(command)
            # unify command
            command = command.upper().strip()
            if not command.endswith(LF):
                command += LF
            #
            result = False
            n = self.retries
            t0 = time.perf_counter()
            while n > 0:
                n -= 1
                self.response = b''
                t0 = time.perf_counter()
                # send command
                if not self.write(command):
                    continue
                # check response
                if check_response is None:
                    if b'?' in command:
                        check_response = True
                    else:
                        check_response = False
                if not check_response:
                    result = True
                else:
                    # read response (to LF by default)
                    result = self.read_response()
                # calculate time stats
                dt = time.perf_counter() - t0
                self.min_io_time = min(self.min_io_time, dt)
                self.max_io_time = max(self.max_io_time, dt)
                self.avg_io_time = (self.avg_io_time * (self.io_count - 1) + dt) / self.io_count
                #
                if result:
                    break
                self.io_error_count += 1
            dt = time.perf_counter() - t0
            if not result:
                self.suspend()
                self.logger.info(f'{self.pre} I/O ERROR {command} -> {self.response}, {result}, %4.0f ms', dt * 1000)
            else:
                self.logger.debug(f'{self.pre} {command} -> {self.response}, {result}, %4.0f ms', dt * 1000)
            return result
        except KeyboardInterrupt:
            raise
        except:
            self.io_error_count += 1
            log_exception(self, f'{self.pre} Command {command} exception')
            self.suspend()
            return False

    @property
    def timeout(self):
        if time.perf_counter() > self.read_timeout_time:
            return True
        return False

    @timeout.setter
    def timeout(self, value):
        if value is not None:
            self.read_timeout_time = time.perf_counter() + value
        else:
            self.read_timeout_time = float('inf')

    @property
    def ready(self):
        if time.perf_counter() < self.suspend_to:
            # self.logger.debug(f'{self.pre} Suspended')
            return False
        if self.suspend_to <= 0.0:
            return True
        # was suspended and expires
        self.close_com_port()
        val = self.init()
        return val

    @ready.setter
    def ready(self, value):
        self._ready = bool(value)
        if value:
            self.suspend_to = 0.0

    def read(self, size=1, timeout=None):
        result = b''
        if timeout is None:
            timeout = self.read_timeout
        self.timeout = timeout
        try:
            while len(result) < size:
                if self.com.in_waiting > 0:
                    r = self.com.read(1)
                    if len(r) > 0:
                        result += r
                if self.timeout:
                    self.logger.debug(f'{self.pre} read timeout')
                    return result
        except KeyboardInterrupt:
            raise
        except:
            log_exception(self.logger, f'{self.pre} read exception')
        return result

    def suspend(self):
        if time.perf_counter() < self.suspend_to:
            return
        self.suspend_to = time.perf_counter() + self.suspend_delay
        self.logger.debug(f'{self.pre} Suspended for {self.suspend_delay} s')

    def read_until(self, terminator=LF, size=None, timeout=None):
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
            self.logger.debug(f'{self.pre} Response %s without %s ', result, expected)
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
                self.logger.error(f'{self.pre} Write error %s of %s' % (length, len(cmd)))
                return False
            # dt = (time.perf_counter() - t0) * 1000.0
            # self.logger.debug('%s %s bytes in %4.0f ms', cmd, length, dt)
            return True
        except KeyboardInterrupt:
            raise
        except:
            log_exception(self.logger, f'{self.pre} Exception during write')
            return False

    def read_value(self, cmd, v_type=float):
        try:
            if self.send_command(cmd):
                return v_type(self.response)
            else:
                return None
        except KeyboardInterrupt:
            raise
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
            t_value = b'ON'
        else:
            t_value = b'OFF'
        cmd = b'OUTP ' + t_value
        v = self.read_value(cmd, bool)
        return True

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

    def read_device_id(self, check_ready=True):
        try:
            if self.send_command(b'*IDN?', check_ready=check_ready):
                return self.response[:-1].decode()
            else:
                return 'Unknown Device'
        except KeyboardInterrupt:
            raise
        except:
            return 'Unknown Device'

    def read_serial_number(self):
        try:
            if self.send_command(b'*IDN?'):
                serial_number = self.response[:-1].decode().split(',')[2]
                return serial_number
            else:
                return ""
        except KeyboardInterrupt:
            raise
        except:
            return ""

    def read_device_type(self):
        try:
            if self.send_command(b'*IDN?'):
                return self.response[:-1].decode().split(',')[1]
            else:
                return "Unknown Device"
        except KeyboardInterrupt:
            raise
        except:
            return "Unknown Device"

    def read_errors(self):
        if self.send_command(b'SYST:ERR?'):
            return self.response[:-1].decode()
        else:
            return ''

    def switch_local(self):
        return self.send_command(b'SYST:LOC', False, False)

    def clear_status(self):
        return self.send_command(b'*CLS', False, False)

    def switch_remote(self):
        return self.send_command(b'SYST:REM', False, False)

    def reconnect(self, port=None, *args, **kwargs):
        if time.perf_counter() < self.reconnect_timeout_time:
            return
        if port is not None:
            self.port = port.strip()
        if len(args) > 0:
            self.args = args
        if len(kwargs) > 0:
            self.kwargs = kwargs
        self.ready = False
        self.close_com_port()
        self.com = self.create_com_port()
        self.init()

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

    def id_ok(self, id=None):
        if id is None:
            id = self.id
        return id.startswith(self.ID_OK)


class IT6900_Lambda(IT6900):
    ID_OK = 'TDK-LAMBDA'
    DEVICE_NAME = 'TDK-LAMBDA Genesys+'
    DEVICE_FAMILY = 'TDK-LAMBDA Genesys+ family Power Supply'


if __name__ == "__main__":
    pd1 = IT6900("COM3", baudrate=115200)
    # pd1.detect_baud()
    while True:
    # for i in range(100):
        cmd = "*IDN?"
        t_0 = time.time()
        v1 = pd1.send_command(cmd)
        dt1 = int((time.time() - t_0) * 1000.0)  # ms
        # print(pd1.port, cmd, '->', pd1.response, v1, '%4d ms ' % dt1)
        cmd = "VOLT?"
        t_0 = time.time()
        v1 = pd1.send_command(cmd)
        dt1 = int((time.time() - t_0) * 1000.0)  # ms
        # print(pd1.port, cmd, '->', pd1.response, v1, '%4d ms ' % dt1)
    print('Errors', pd1.read_errors())
    print('Total I/O:', pd1.io_count)
    print('Total Errors:', pd1.io_error_count)
    print('min I/O time:', pd1.min_io_time)
    print('max I/O time:', pd1.max_io_time)
    print('avg I/O time:', pd1.avg_io_time)
