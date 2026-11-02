# EMCO USB_HV control module in Python with HID API

This is a Python module to control the EMCO USB_HV power module via the HID API. The module is based on the reverse engineering of the USB protocol used by the EMCO USBhv Series control software. It was tested with USB20N power module.

![Photo of HV power supply USB20N](./emco_usbhv_photo.jpg)

## Installation

Install with

    pip install .

or, to work on the driver itself (edits take effect without reinstalling),

    pip install -e .

### Permissions

On Linux remember to set correct permissions for the USB device. You can do it by creating a udev rule. Create a file `/etc/udev/rules.d/99-emco-usbhv.rules` with the following content:
```bash
SUBSYSTEM=="usb", ATTR{idVendor}=="03eb", ATTR{idProduct}=="201d", MODE="0666"
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="03eb", ATTRS{idProduct}=="201d", MODE="0666"
```
or simply run the following command:
```bash
echo 'SUBSYSTEM=="usb", ATTR{idVendor}=="03eb", ATTR{idProduct}=="201d", MODE="0666"' | sudo tee /etc/udev/rules.d/99-emco-usbhv.rules
echo 'SUBSYSTEM=="hidraw", ATTRS{idVendor}=="03eb", ATTRS{idProduct}=="201d", MODE="0666"' | sudo tee -a /etc/udev/rules.d/99-emco-usbhv.rules
```
Then reload the udev rules:
```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
```

Note:
The first line is needed by older hidapi wheels that use the libusb backend (e.g. hidapi == 0.9.0.post3).
The second line is needed by newer ones that use the hidraw backend (e.g. hidapi == 0.14.0.post2).
Keeping both does no harm.

## Usage

```python
from emco_usbhv import EMCO_USBhv, EMCOError

hv = EMCO_USBhv()          # finds the single EMCO device (vendor 0x03eb)
hv.set_voltage(500)        # integer volts, 0-2047
hv.enable()
print(hv.status())         # {'enabled': True, 'set_voltage': 500.0,
                           #  'voltage_monitor1': ..., 'voltage_monitor2': ...}
hv.disable()
```

`set_voltage()`, `enable()` and `disable()` read the status back and raise `EMCOError` if the
supply did not take the command (`disable()` also resends it). The voltage monitors are
uncalibrated; check your module against a multimeter.

See also the `if __name__ == '__main__'` block in [emco_usbhv/emco_usbhv.py](emco_usbhv/emco_usbhv.py).

### Reply backlog

The supply can hold a backlog of old replies and release them in a burst on the next write
(seen on a Raspberry Pi 4 with the supply behind a USB hub, together with xhci
"TRB DMA ptr not part of current TD" kernel errors). A driver that reads one reply per command
then falls behind: the readback looks frozen and `disable()` seems ignored. This driver
therefore reads until the line goes quiet and keeps the newest reply. Details in the comment at
the top of [emco_usbhv/emco_usbhv.py](emco_usbhv/emco_usbhv.py).

If the device is wedged, `EMCO_USBhv.usb_reset()` does a software unplug/replug. It needs the
`usbreset` tool and passwordless `sudo` for it.

## GUI Application

The module also includes a simple GUI application to control the EMCO USB_HV power module. The application is based on the `tkinter` library.

Run the application with the following command:
```bash
python emco_usbhv_app.py
```
