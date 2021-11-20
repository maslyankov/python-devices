# Uses https://github.com/Swind/pure-python-adb
import typing
from subprocess import PIPE, Popen
from time import sleep
from threading import Thread
import logging
from signal import SIGINT
from os import kill
from contextlib import contextmanager

from ppadb.client import Client as AdbPy

from utils import compare_sets
from android.ADBDevice import ADBDevice
import Client

try:
    from subprocess import CREATE_NEW_CONSOLE, CREATE_NO_WINDOW
except ImportError:
    # Not a windows machine
    CREATE_NEW_CONSOLE = 0
    CREATE_NO_WINDOW = 0

ADB = "adb"
SCRCPY = "scrcpy"


class AdbClient(Client.Client):
    """
    AdbClient class takes care of starting ADB, keeping connected devices list and etc.
    """

    def __init__(self, callbacks: dict[str, typing.Callable] = None, wait_for_gui: bool = False, adb_binary: str = ADB):
        super().__init__(
            callbacks=callbacks, wait_for_gui=wait_for_gui
        )
        self._adb_binary = adb_binary

        logging.log(logging.INFO, "Starting the ADB Server...")
        try:
            self.adb = Popen(
                [adb_binary, 'start-server'],
                stdin=PIPE,
                stdout=PIPE,
                stderr=PIPE)
            # self.adb.stdin.close()
            stdout, stderr = self.adb.communicate()
            if stdout:
                logging.log(logging.DEBUG, f"ADB Start Output: {stdout.decode()}")
            if stderr:
                logging.log(logging.DEBUG, f"ADB Start Error: {stderr.decode()}")
            self.adb.wait()
        except FileNotFoundError:
            logging.critical("Fatal error: adb not found!")
            logging.log(logging.INFO, f"Adb is set to: {adb_binary}")
            exit(1)

        self.client: AdbPy = AdbPy()

        self._run_watchdog: bool = True
        self._anticipate_root: set = set()

    @contextmanager
    def anticipate_root(self, serial: str) -> None:
        """
        A context manager for code that
        """
        self._anticipate_root.add(serial)
        yield
        self._anticipate_root.remove(serial)

    # ----- Main Stuff -----
    def _watchdog(self) -> None:
        """
        The watchdog itself
        """
        devices_set: set = set()
        started: bool = False
        while True:
            if not self._run_watchdog:
                break

            while self.wait_for_gui:  # Give time for the GUI to load
                sleep(1)
            self.callbacks['watchdog_starting'](
                action='watchdog_starting',
                type='android',
                error=False
            )

            try:
                devices_set: set = self.get_devices()
            except ConnectionResetError:
                logging.critical('ADB Server connection lost.')
                self.callbacks['error'](
                    action='get_devices',
                    type='android',
                    error=True
                )

            # logging.log(logging.DEBUG, f"Not minding the device updates as we are anticipating root!")
            try:
                if len(devices_set) > len(self.connected_devices):  # If New devices found
                    for count, diff_device in enumerate(compare_sets(self.connected_devices, devices_set)):
                        if diff_device in self._anticipate_root:
                            continue

                        if "connected" in self.callbacks:
                            self.callbacks['connected'](
                                action='connected',
                                serial=diff_device,
                                type='android',
                                error=False
                            )
                elif len(devices_set) < len(self.connected_devices):  # If a device has disconnected
                    for count, diff_device in enumerate(compare_sets(self.connected_devices, devices_set)):
                        if diff_device in self._anticipate_root:
                            continue

                        if "connected" in self.callbacks:
                            self.callbacks['disconnected'](
                                action='disconnected',
                                serial=diff_device,
                                type='android',
                                error=False
                            )
                self.connected_devices = devices_set
            except (TimeoutError, RuntimeError) as e:
                self.callbacks['error'](
                    action='get_devices',
                    type='android',
                    error=True,
                    details=e
                )
            else:
                if not started:
                    self.callbacks['watchdog_started'](
                        action='watchdog_started',
                        type='android',
                        error=False
                    )

                started = True

        logging.log(logging.DEBUG, "ADB Watchdog exiting...")

    def watchdog(self) -> None:
        """
        Starts the adb watchdog thread.
        """
        self.watchdog_thread = Thread(target=self._watchdog, args=(), daemon=True)
        self.watchdog_thread.name = 'ADBDevices-Watchdog'
        self.watchdog_thread.start()

    def kill_watchdog(self) -> None:
        """
        Kills the Watchdog thread
        """
        self._run_watchdog = False

    # ----- Getters -----
    def get_devices(self) -> set:
        """
        Get a list of devices from adb server
        :return:List
        """
        devices = set()
        for d in self.client.devices():
            devices.add(d.serial)
        return devices  # Return set of devices's serials

    def get_attached_devices(self) -> set:
        """
        Get a set of attached devices
        :return:List
        """
        return self.attached_devices

    # ----- Methods -----
    def kill_adb(self) -> None:
        """
        Kill opened adb process
        :return:None
        """
        self.adb.terminate()

    def attach_device(self, device_serial) -> None:
        """
        Add device to attached devices
        :param device_serial: Device serial
        :return: None
        """
        self.devices_obj[device_serial] = ADBDevice(self, device_serial)  # Assign device to object
        self.attached_devices.add(device_serial)

        self.devices_obj[device_serial].set_led_color('0FFF00', 'RGB1', 'global_rgb')  # Poly

    def detach_device(self, device_serial: str) -> None:
        """
        Remove device from attached devices
        :param device_serial: Device serial
        :return: None
        """

        # Finally detach device
        if self.attached_devices:
            try:
                logging.log(logging.INFO, f'Detaching device {device_serial}')
                try:
                    self.devices_obj[device_serial].kill_scrcpy()
                except KeyError:
                    return

                try:
                    self.attached_devices.remove(device_serial)
                except ValueError:
                    pass

                del self.devices_obj[device_serial]
            except ValueError as e:
                logging.warning(f"Not found in attached devices list")
                logging.exception(e)
                logging.log(logging.DEBUG, self.attached_devices)
            except KeyError as e:
                logging.warning(f"Not found in attached devices list")
                logging.exception(e)
                logging.log(logging.DEBUG, self.attached_devices)

    def reboot_and_wait_for_device(self, device_serial: str) -> typing.Optional[ADBDevice]:
        if device_serial not in self.connected_devices:
            logging.log(logging.ERROR, f"{device_serial} does not seem to be connected to the computer...")
            return

        if device_serial not in self.attached_devices:
            logging.log(logging.DEBUG, f"{device_serial} not attached... Attaching now...")

            self.attach_device(device_serial)

        self.devices_obj[device_serial].reboot()

        while device_serial not in self.connected_devices:
            sleep(1)

        return self.attach_device(device_serial)

    def root(self, device_serial: str) -> None:
        """
        Root the device
        :return:None
        """
        logging.log(logging.INFO, f"Rooting device {device_serial}")

        logging.log(logging.DEBUG, "set ant root on")
        with self.anticipate_root(device_serial):
            # CREATE_NO_WINDOW = 0x08000000
            try:
                root = Popen([self._adb_binary, '-s', device_serial, 'root'],
                             stdin=PIPE,
                             stdout=PIPE,
                             stderr=PIPE,
                             creationflags=CREATE_NO_WINDOW)

                root.stdin.close()
                stdout, stderr = root.communicate()
                if stderr:
                    try:
                        if b"unauthorized" in stderr:
                            raise ValueError(
                                f"Device not rooted (probably) or you didn't allow usb debugging.\n"
                                f"Rooting Errors: {stderr.decode()}"
                            )
                        else:
                            raise ValueError(f'Rooting Errors: {stderr.decode()}')
                    except ValueError as e:
                        logging.critical(e)
                if stdout:
                    logging.log(logging.INFO, "Rooting Output: {}".format(stdout.decode()))

                root.terminate()
            except FileNotFoundError:
                logging.log(logging.CRITICAL, f"Could not find ADB")

    @staticmethod
    def remount(self, device_serial) -> None:
        """
        Remount the device
        :return:None
        """
        logging.log(logging.INFO, f"Remount device serial: {device_serial}")
        # CREATE_NO_WINDOW = 0x08000000
        try:
            with self.anticipate_root(device_serial):
                remount = Popen([self._adb_binary, '-s', device_serial, 'remount'],
                                stdin=PIPE,
                                stdout=PIPE,
                                stderr=PIPE,
                                creationflags=CREATE_NO_WINDOW)
                remount.stdin.close()
                stdout, stderr = remount.communicate()
                if stderr:
                    logging.log(logging.ERROR, "Remount Errors: ".format(stderr.decode()))
                if stdout:
                    logging.warning("Remount Output: ".format(stdout.decode()))
                remount.terminate()
        except FileNotFoundError:
            logging.log(logging.CRITICAL, f"Could not find ADB")

    def disable_verity(self, device_serial: str) -> None:
        """
        Disabled verity of device
        :return:None
        """
        logging.log(logging.INFO, f"Disabling verity device serial: {device_serial}")
        # CREATE_NO_WINDOW = 0x08000000
        with self.anticipate_root(device_serial):
            disver = Popen([self._adb_binary, '-s', device_serial, 'disable-verity'],
                           stdin=PIPE,
                           stdout=PIPE,
                           stderr=PIPE,
                           creationflags=CREATE_NO_WINDOW)
            disver.stdin.close()
            stdout, stderr = disver.communicate()
            if stderr:
                logging.log(logging.ERROR, f"Dis verity Errors: {stderr.decode()}")
            if stdout:
                logging.warning(f"Dis verity Output: {stdout.decode()}")
            disver.terminate()

            logging.log(logging.INFO, 'Rebooting device after disabling verity!')
            # self.reboot()

    def open_shell(self, device_serial: str, cmd_str: str = None) -> Popen:
        """
        Open shell terminal of device
        :return:None
        """
        logging.log(logging.INFO, f"Opening shell terminal of: {device_serial}")
        args_list = [self._adb_binary, "-s", device_serial, "shell"]

        if cmd_str:
            if isinstance(cmd_str, str):
                args_list.append(cmd_str)
            else:
                logging.log(logging.ERROR, "Got cmd that is not str")
                logging.log(logging.DEBUG, f"cmd: '{cmd_str}' of type {type(cmd_str)}")

        return Popen(args_list, creationflags=CREATE_NEW_CONSOLE)

    @staticmethod
    def close_shell(subp: Popen) -> None:
        try:
            kill(subp.pid, SIGINT)
        except PermissionError:
            pass  # Happens when window does not exits, for ex: did not open at all
    
    @staticmethod
    def open_device_ctrl(device_obj, extra_args=None) -> None:
        """
        Open device screen view and control using scrcpy
        :return:None
        """
        exec_data = [SCRCPY, '--serial', device_obj.device_serial]

        logging.log(logging.INFO, f"Opening scrcpy for device {device_obj.device_serial}.")

        logging.log(logging.DEBUG, f"Scrcpy extra_args: {extra_args}")
        if extra_args:
            extra_args = extra_args.split(" ")
            exec_data.append(extra_args)

        try:
            new_scrcpy = Popen(
                exec_data,
                stdin=PIPE,
                stdout=PIPE,
                stderr=PIPE,
                creationflags=CREATE_NO_WINDOW
            )
        except FileNotFoundError:
            logging.log(logging.ERROR, f"Could not find scrcpy!")
        else:
            device_obj.scrcpy.append(new_scrcpy)
        # self.scrcpy[-1].stdin.close()
    
    @staticmethod
    def kill_scrcpy(device_obj: ADBDevice) -> None:
        logging.log(logging.DEBUG, f"Scrcpy list: {device_obj.scrcpy}")
        scrcpy_list = device_obj.scrcpy.copy()

        for process in scrcpy_list:
            try:
                stdout_data = process.communicate(input=b'\x03')[0]  # Send Ctrl+C
                logging.log(logging.DEBUG, stdout_data)
            except ValueError:
                logging.log(logging.WARNING, "Window was already closed!")

            logging.log(logging.DEBUG, f"killing {process.pid}")
            process.terminate()

            device_obj.scrcpy.remove(process)

        logging.log(logging.DEBUG, "Killed scrcpy windows for device")
        del scrcpy_list

    def __del__(self):
        self.kill_adb()
