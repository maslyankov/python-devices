import threading
import time
import logging

# import cv2
from cv2 import cv2

from utils import compare_sets
import usbcam.USBCamDevice
import Client


def get_ports_dict() -> tuple[dict[str, dict], set[str]]:
    is_working: bool = True
    dev_port: int = 0
    working_ports = dict()
    available_ports = set()
    while is_working:
        camera: cv2.VideoCapture = cv2.VideoCapture(dev_port)
        if not camera.isOpened():
            is_working = False
            logging.log(logging.DEBUG, f"Port {dev_port} is not working.")
        else:
            is_reading, img = camera.read()
            w = camera.get(3)
            h = camera.get(4)
            if is_reading:
                logging.log(logging.DEBUG, f"Port {dev_port} is working and returns images ({h} x {w})")
                working_ports[dev_port] = {
                    'id': dev_port,
                    'frame_size': {
                        'height': h,
                        'width': w
                    }
                }
            else:
                logging.log(logging.DEBUG, f"Port dev_port for camera ( {h} x {w}) is present but does not return images.")
                available_ports.add(dev_port)
        dev_port += 1

    return working_ports, available_ports


def select_camera(last_index):
    number = 0
    hint = "Select a camera (0 to " + str(last_index) + "): "
    try:
        number = int(input(hint))
        # select = int(select)
    except Exception:
        print("It's not a number!")
        return select_camera(last_index)

    if number > last_index:
        print("Invalid number! Retry!")
        return select_camera(last_index)

    return number


def open_camera_stream_console():
    # print OpenCV version
    print("OpenCV version: " + cv2.__version__)

    client_obj = USBCamClient()

    # Get camera list
    device_list = list(get_ports_dict()[0])
    index = 0

    for name in device_list:
        print(f"{index}: {name}")
        index += 1

    last_index = index - 1

    if last_index < 0:
        print("No device is connected")
        return

    # Select a camera
    camera_number = select_camera(last_index)

    cam_obj = client_obj.attach_device(port=camera_number)

    # Open camera
    cam_obj.open_camera_stream_windowed()


class USBCamClient(Client.Client):
    def __init__(self, callbacks=None):
        super().__init__(callbacks=callbacks)

    # ----- Main Stuff -----
    def _watchdog(self):
        time.sleep(1)  # Let's give the GUI time to load
        while True:
            ports_dict = get_ports_dict()[0]
            devices_set = set(ports_dict.values())

            if len(devices_set) > len(self.connected_devices):  # If New devices found
                for count, diff_device in enumerate(compare_sets(self.connected_devices, devices_set)):
                    friendly_name = list(ports_dict.keys)[diff_device]
                    serial = friendly_name.replace(' ', '').lower()

                    if "connected" in self.callbacks:
                        self.callbacks['connected'](
                            action='connected',
                            serial=serial,
                            port=diff_device,
                            type='usb_cam',
                            friendly_name=friendly_name,
                            error=False
                        )
            elif len(devices_set) < len(self.connected_devices):  # If a device has disconnected
                for count, diff_device in enumerate(compare_sets(self.connected_devices, devices_set)):
                    friendly_name = list(ports_dict.keys)[diff_device]
                    serial = friendly_name.replace(' ', '').lower()

                    if "disconnected" in self.callbacks:
                        self.callbacks['disconnected'](
                                action='disconnected',
                                serial=serial,
                                port=diff_device,
                                type='usb_cam',
                                friendly_name=friendly_name,
                                error=False
                        )

            self.connected_devices = devices_set

    def init_watchdog(self):
        self.watchdog_thread = threading.Thread(target=self._watchdog, args=(), daemon=True)
        self.watchdog_thread.name = 'USBCameras-Watchdog'

        logging.log(logging.INFO, f"Starting {self.watchdog_thread.name} Thread")
        self.watchdog_thread.start()

    def attach_device(self, port, device_serial=None) -> usbcam.USBCamDevice.USBCamDevice:
        """
        Add device to attached devices
        :param port:
        :param device_serial: Device serial
        :return: None
        """
        logging.log(logging.INFO, f"Attaching device {device_serial} at {port}")

        if not device_serial:
            device_serial = f'cam_{port}'

        self.devices_obj[device_serial] = usbcam.USBCamDevice.USBCamDevice(device_serial,
                                                                           port)  # Assign device to object
        self.attached_devices.add(device_serial)

        return self.devices_obj[device_serial]

    def detach_device(self, device_serial):
        """
        Remove device from attached devices
        :param device_serial: Device serial
        :param device_obj: Device object
        :return: None
        """
        logging.log(logging.INFO, f'Detaching device {device_serial}')

        # Finally detach device
        try:
            self.attached_devices.remove(device_serial)
            del self.devices_obj[device_serial]
        except ValueError:
            logging.log(logging.ERROR, f"Not found in attached devices list\n{self.attached_devices}")


if __name__ == '__main__':
    logging.getLogger().setLevel("DEBUG")
    open_camera_stream_console()
