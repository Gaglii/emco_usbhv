import subprocess
import time

import hid

# Captured commands and responses from the device
# reset
# 00 00 00 00 00 0f ff 09
# get status
# 03 00 cc 00 00 0f ff 09
# set voltage (500 V)
# 01 xx yy 00 00 0f ff 09
# where xx is the low byte and yy is the high byte of the voltage variable
# voltage variable is twice the desired voltage
# e.g. for 500 V, xx = 0xff, yy = 0x03 (not exactly twice, seems there is a conversion table of function)
# 01 ff 03 00 00 0f ff 09
# enable output
# 02 80 cc 00 00 0f ff 09
# disable output
# 02 00 cc 00 00 0f ff 09

# response on get status command
# - contains actual set voltage and measured voltages
# 1B - status (0x80 if enabled, 0x00 if disabled)
# 2B - set voltage: big endian (opposite order of the set voltage command)
# 2B - measured voltage 1: big endian
# 2B - measured voltage 2: big endian

# this driver does not have any calibration curve for the voltage
# therefore, I would recommend to calibrate your module with a multimeter

# Reply queue (measured 2026-10-23 on a Raspberry Pi 4, supply behind a USB hub):
# the device can hold a backlog of old replies (30+), released in a burst on the
# next write. Commands seem to get duplicated on the bus (xhci "TRB DMA ptr not
# part of current TD" errors), each copy gets a reply, and a driver that reads one
# report per command falls behind: readback looks frozen and disable() seems
# ignored. So every command reads until the line goes quiet and keeps the newest
# reply, and enable/disable/set_voltage are verified with a fresh status.


class EMCOError(RuntimeError):
    pass


class EMCO_USBhv:
    # Vendor ID and Product ID of the device (USB20N)
    C_VENDOR_ID = 0x03eb
    # C_PRODUCT_ID = 0x201d

    # create a function which will list all available device's IDs correspoding to the vendor ID
    @staticmethod
    def list_devices():
        devices = hid.enumerate()
        return [(device['vendor_id'], device['product_id']) for device in devices if device['vendor_id'] == EMCO_USBhv.C_VENDOR_ID]
    
    # constructor
    def __init__(self, vendor_id=None, product_id=None):
        self.vendor_id = vendor_id
        self.product_id = product_id

        # if vendor_id and product_id are not provided, find the device
        if vendor_id is None or product_id is None:
            devices = EMCO_USBhv.list_devices()
            if len(devices) == 0:
                raise Exception('No EMCO USBhv device found')
            if len(devices) > 1:
                raise Exception('Multiple EMCO USBhv devices found, specify the vendor_id and product_id')
            self.vendor_id, self.product_id = devices[0]
        
        self.device = hid.device()
        self.device.open(self.vendor_id, self.product_id)
        self.status()           # flushes any backlog left from earlier sessions

    # destructor
    def __del__(self):
        self.device.close()
    
    def write_data(self, data):
        # add 0x00 to the beginning of the data
        data = [0x00] + data
        self.device.write(data)

    def read_data(self, length):
        return self.device.read(length)

    def transact(self, command, quiet_ms=60, retries=3):
        """Send *command* and return the newest reply once no more arrive for *quiet_ms*."""
        for _ in range(retries):
            self.write_data(command)
            reply = None
            while True:
                r = self.read_data_timeout(8, quiet_ms)
                if not r:
                    break
                reply = r
            if reply is not None:
                return reply
        raise EMCOError(f'no reply to command {bytes(command).hex(" ")}')

    def read_data_timeout(self, length, timeout_ms):
        return self.device.read(length, timeout_ms)

    def _verified(self, check, what, retries=3):
        """Re-read status until *check(status)* holds; raise after *retries* tries."""
        for _ in range(retries):
            s = self.status()
            if check(s):
                return s
            time.sleep(0.1)
        raise EMCOError(f'{what} not confirmed by the supply, last status {s}')

    @classmethod
    def usb_reset(cls, product_id=0x201d):
        """Software unplug/replug of the USB device (needs passwordless sudo and usbreset)."""
        subprocess.run(['sudo', '-n', 'usbreset', f'{cls.C_VENDOR_ID:04x}:{product_id:04x}'],
                       check=True, capture_output=True)
        time.sleep(1.0)
    
    def set_voltage(self, voltage):
        if voltage < 0 or voltage >= 2048:
            raise Exception('Voltage must be between 0 and 2000 V')
        
        v = voltage * 2
        voltage_high_byte = (v >> 8) & 0xFF
        voltage_low_byte = v & 0xFF
        command = [0x01, voltage_low_byte, voltage_high_byte, 0x00, 0x00, 0x0f, 0xff, 0x09]
        self.transact(command)
        self._verified(lambda s: s['set_voltage'] == voltage, f'set_voltage({voltage})')
        

    def enable(self):
        command = [0x02, 0x80, 0xcc, 0x00, 0x00, 0x0f, 0xff, 0x09]
        self.transact(command)
        self._verified(lambda s: s['enabled'], 'enable()')

    def disable(self):
        command = [0x02, 0x00, 0xcc, 0x00, 0x00, 0x0f, 0xff, 0x09]
        for _ in range(3):      # a lost disable is the dangerous case: resend, not just re-read
            self.transact(command)
            try:
                return self._verified(lambda s: not s['enabled'], 'disable()', retries=2)
            except EMCOError as e:
                last = e
        raise last

    def status(self):
        command = [0x03, 0x00, 0xcc, 0x00, 0x00, 0x0f, 0xff, 0x09]
        response = self.transact(command)
        if response[7] != 0x09 or response[0] not in (0x00, 0x80):
            raise EMCOError(f'unexpected status reply {bytes(response).hex(" ")}')
        status = {}
        #print(f'Status response: {response}')
        status['enabled'] = response[0] == 0x80
        status['set_voltage'] = ((response[1] << 8) | response[2]) / 2.0
        status['voltage_monitor1'] = ((response[3] << 8) | response[4]) / 2.0
        status['voltage_monitor2'] = ((response[5] << 8) | response[6]) / 2.0
        return status

    # set voltage directly by calling the object with the voltage value
    def __call__(self, voltage):
        self.set_voltage(voltage)
 

if __name__ == '__main__':
    import time

    # create an object of the class
    hv = EMCO_USBhv()

    # set the voltage to 500 V
    hv.set_voltage(500)

    # enable the output
    hv.enable()

    # get the status
    time.sleep(0.3)
    print(f'Status after setting 500 V and enabled: {hv.status()}')

    # disable the output
    hv.disable()

    # get the status
    time.sleep(0.3)
    print(f'Status after disabling: {hv.status()}')

    # set the voltage to 1000 V
    hv(1000)

    # enable the output
    hv.enable()

    # get the status
    time.sleep(0.3)
    print(f'Status after setting 1000 V and enabled: {hv.status()}')

    # disable the output
    hv.disable()

    # get the status
    time.sleep(0.3)
    print(f'Status after disabling: {hv.status()}')