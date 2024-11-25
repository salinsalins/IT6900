#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""IT6900 family power supply tango device server"""
import sys
import os

from tango import AttrQuality, AttrWriteType, DispLevel
from tango import DevState
from tango.server import Device, attribute, command

if os.path.realpath('../TangoUtils') not in sys.path: sys.path.append(os.path.realpath('../TangoUtils'))
import IT6900

from TangoServerPrototype import TangoServerPrototype

ORGANIZATION_NAME = 'BINP'
APPLICATION_NAME = 'IT6900 family Power Supply Tango Device Server'
APPLICATION_NAME_SHORT = 'IT6900_Server'
APPLICATION_VERSION = '1.5'


class IT6900_Server(TangoServerPrototype):
    server_version_value = APPLICATION_VERSION
    server_name_value = APPLICATION_NAME

    port = attribute(label="Port", dtype=str,
                     display_level=DispLevel.OPERATOR,
                     access=AttrWriteType.READ,
                     unit="", format="%s",
                     doc="TDKLambda port")

    device_type = attribute(label="PS Type", dtype=str,
                            display_level=DispLevel.OPERATOR,
                            access=AttrWriteType.READ,
                            unit="", format="%s",
                            doc="TDKLambda device type")

    output_state = attribute(label="Output", dtype=bool,
                             display_level=DispLevel.OPERATOR,
                             access=AttrWriteType.READ_WRITE,
                             unit="", format="",
                             doc="Output on/off state")

    voltage = attribute(label="Voltage", dtype=float,
                        display_level=DispLevel.OPERATOR,
                        access=AttrWriteType.READ,
                        unit="V", format="%6.3f",
                        min_value=0.0,
                        doc="Measured voltage")

    programmed_voltage = attribute(label="Programmed Voltage", dtype=float,
                                   display_level=DispLevel.OPERATOR,
                                   access=AttrWriteType.READ_WRITE,
                                   unit="V", format="%6.3f",
                                   min_value=0.0,
                                   doc="Programmed voltage")

    current = attribute(label="Current", dtype=float,
                        display_level=DispLevel.OPERATOR,
                        access=AttrWriteType.READ,
                        unit="A", format="%6.3f",
                        min_value=0.0,
                        doc="Measured current")

    programmed_current = attribute(label="Programmed Current", dtype=float,
                                   display_level=DispLevel.OPERATOR,
                                   access=AttrWriteType.READ_WRITE,
                                   unit="A", format="%6.3f",
                                   min_value=0.0,
                                   doc="Programmed current")

    power = attribute(label="Power", dtype=float,
                      display_level=DispLevel.OPERATOR,
                      access=AttrWriteType.READ,
                      unit="W", format="%8.3f",
                      min_value=0.0,
                      doc="Measured output power")

    def init_device(self):
        super().init_device()
        msg = f'{self.get_name()} IT6900 Initialization'
        self.logger.info(msg)
        self.set_state(DevState.INIT, msg)
        kwargs = {}
        args = ()
        port = self.config.get('port', 'COM3')
        baud = self.config.get('baudrate', 115200)
        kwargs['baudrate'] = baud
        kwargs['logger'] = self.logger
        tdklambda = self.config.pop('tdklambda', 'n')
        if tdklambda == 'y':
            self.it6900 = IT6900.IT6900_Lambda(port, *args, **kwargs)
        else:
            self.it6900 = IT6900.IT6900(port, *args, **kwargs)
        if self.it6900.initialized():
            # max voltage and current
            self.programmed_voltage.set_max_value(self.it6900.max_voltage)
            self.programmed_current.set_max_value(self.it6900.max_current)
            self.programmed_voltage.set_write_value(self.read_programmed_voltage())
            self.programmed_current.set_write_value(self.read_programmed_current())
            self.output_state.set_write_value(self.read_output_state())
            # set state to running
            msg = '%s %s at %s initialized successfully' % (self.get_name(), self.it6900.type, self.it6900.port)
            self.set_running(msg)
        else:
            msg = '%s initialization error' % self.get_name()
            self.set_fault(msg)

    def delete_device(self):
        self.it6900.ready = False
        self.it6900.close_com_port()
        super().delete_device()
        msg = '%s has been deleted' % self.get_name()
        self.logger.info(msg)

    def read_port(self):
        if self.it6900.initialized():
            return self.it6900.port
        return "Uninitialized"

    def read_device_type(self):
        if self.it6900.initialized():
            return self.it6900.type
        return "Uninitialized"

    def common_read(self, read_function, attrib, wrong_value=None):
        if not self.it6900.initialized():
            attrib.set_value(wrong_value)
            attrib.set_quality(AttrQuality.ATTR_INVALID)
            msg = "Read from offline device %s" % self.name
            self.set_fault(msg)
            return wrong_value
        value = read_function()
        if value is not None:
            attrib.set_value(value)
            attrib.set_quality(AttrQuality.ATTR_VALID)
            self.set_running()
            return value
        else:
            attrib.set_value(wrong_value)
            attrib.set_quality(AttrQuality.ATTR_INVALID)
            msg = "Invalid reading response for %s" % self.name
            self.set_fault(msg)
            return wrong_value

    def common_write(self, write_function, attrib, value):
        if not self.it6900.initialized():
            attrib.set_quality(AttrQuality.ATTR_INVALID)
            msg = "Write to offline device %s" % self.name
            self.set_fault(msg)
            return False
        if write_function(value):
            attrib.set_quality(AttrQuality.ATTR_VALID)
            self.set_running()
            return True
        attrib.set_quality(AttrQuality.ATTR_INVALID)
        msg = "Error writing to %s" % self.name
        self.set_fault(msg)
        return False

    def read_output_state(self):
        return self.common_read(self.it6900.read_output, self.output_state, False)
        # if self.it6900.initialized():
        #     value = self.it6900.read_output()
        #     if value is not None:
        #         qual = AttrQuality.ATTR_VALID
        #         self.set_running()
        #     else:
        #         qual = AttrQuality.ATTR_INVALID
        #         value = False
        #         self.set_fault()
        # else:
        #     value = False
        #     qual = AttrQuality.ATTR_INVALID
        #     self.set_fault('I/O to uninitialized device')
        # self.output_state.set_value(value)
        # self.output_state.set_quality(qual)
        # return value

    def write_output_state(self, value):
        return self.common_write(self.it6900.write_output, self.output_state, value)

    def read_power(self):
        return self.common_read(self.it6900.read_power, self.power)

    def read_voltage(self):
        return self.common_read(self.it6900.read_voltage, self.voltage, float('nan'))
        # if self.it6900.initialized():
        #     value = self.it6900.read_voltage()
        #     if value is not None:
        #         qual = AttrQuality.ATTR_VALID
        #         self.set_running()
        #     else:
        #         qual = AttrQuality.ATTR_INVALID
        #         value = float('nan')
        #         self.set_fault()
        # else:
        #     value = float('nan')
        #     qual = AttrQuality.ATTR_INVALID
        #     self.set_fault('I/O to uninitialized device')
        # self.voltage.set_value(value)
        # self.voltage.set_quality(qual)
        # return value

    def read_current(self):
        return self.common_read(self.it6900.read_current, self.current, float('nan'))
        # if self.it6900.initialized():
        #     value = self.it6900.read_current()
        #     if value is not None:
        #         qual = AttrQuality.ATTR_VALID
        #         self.set_running()
        #     else:
        #         qual = AttrQuality.ATTR_INVALID
        #         value = float('nan')
        #         self.set_fault()
        # else:
        #     value = float('nan')
        #     qual = AttrQuality.ATTR_INVALID
        #     self.set_fault('I/O to uninitialized device')
        # self.current.set_value(value)
        # self.current.set_quality(qual)
        # return value

    def read_programmed_voltage(self):
        return self.common_read(self.it6900.read_programmed_voltage, self.programmed_voltage, float('nan'))
        # if self.it6900.initialized():
        #     value = self.it6900.read_programmed_voltage()
        #     if value is not None:
        #         qual = AttrQuality.ATTR_VALID
        #         self.set_running()
        #     else:
        #         qual = AttrQuality.ATTR_INVALID
        #         value = float('nan')
        #         self.set_fault()
        # else:
        #     value = float('nan')
        #     qual = AttrQuality.ATTR_INVALID
        #     self.set_fault('I/O to uninitialized device')
        # self.programmed_voltage.set_value(value)
        # self.programmed_voltage.set_quality(qual)
        # return value

    def read_programmed_current(self):
        return self.common_read(self.it6900.read_programmed_current, self.programmed_current, float('nan'))
        # if self.it6900.initialized():
        #     value = self.it6900.read_programmed_current()
        #     if value is not None:
        #         qual = AttrQuality.ATTR_VALID
        #         self.set_running()
        #     else:
        #         qual = AttrQuality.ATTR_INVALID
        #         value = float('nan')
        #         self.set_fault()
        # else:
        #     value = float('nan')
        #     qual = AttrQuality.ATTR_INVALID
        #     self.set_fault('I/O to uninitialized device')
        # self.programmed_current.set_value(value)
        # self.programmed_current.set_quality(qual)
        # return value

    def write_programmed_voltage(self, value):
        return self.common_write(self.it6900.write_voltage, self.programmed_voltage, value)
        # if not self.it6900.initialized():
        #     msg = "Writing to offline device %s" % self.name
        #     self.logger.warning(msg)
        #     self.set_fault(msg)
        #     return False
        # else:
        #     result = self.it6900.write_voltage(value)
        # if result:
        #     self.programmed_voltage.set_quality(AttrQuality.ATTR_VALID)
        #     self.set_running()
        # else:
        #     self.programmed_voltage.set_quality(AttrQuality.ATTR_INVALID)
        #     self.set_fault()
        # return result

    def write_programmed_current(self, value):
        return self.common_write(self.it6900.write_current, self.programmed_current, value)
        # if not self.it6900.initialized():
        #     self.programmed_voltage.set_quality(AttrQuality.ATTR_INVALID)
        #     msg = "Writing to offline device %s" % self.name
        #     self.logger.warning(msg)
        #     self.set_fault(msg)
        #     return False
        # else:
        #     result = self.it6900.write_current(value)
        # if result:
        #     self.programmed_current.set_quality(AttrQuality.ATTR_VALID)
        #     self.set_running()
        # else:
        #     self.programmed_current.set_quality(AttrQuality.ATTR_INVALID)
        #     self.set_fault()
        # return result

    @command
    def reconnect(self):
        self.it6900.reconnect()
        self.it6900.switch_remote()

    @command
    def switch_remote(self):
        self.it6900.switch_remote()

    @command
    def clear_status(self):
        self.it6900.clear_status()

    @command(dtype_in=str, doc_in='Directly send command to the device',
             dtype_out=str, doc_out='Response from device without final LF')
    def send_command(self, cmd):
        if self.it6900.send_command(cmd):
            self.set_running('Command Ok')
        else:
            self.set_fault('Command Error')
        return self.it6900.response[:-1].decode()


if __name__ == "__main__":
    IT6900_Server.run_server()
