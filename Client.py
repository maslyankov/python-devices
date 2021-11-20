import typing
import threading
import logging

CALLBACKS: set = {
    "error",
    "watchdog_starting",
    "connected",
    "disconnected"
}


def log_stuff(*kwargs, **args):
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    logger.log(logging.INFO, f"{str(kwargs)} ; {str(args)}")


class Client:
    def __init__(self, callbacks: dict = None, wait_for_gui: bool = False):
        logger = logging.getLogger()
        logger.setLevel(logging.DEBUG)

        self.watchdog_thread: typing.Optional[threading.Thread] = None
        self.connected_devices: set = set()  # to store connected devices

        # to store attached devices - devices that are connected
        # and we are attached to
        self.attached_devices: set = set()
        self.devices_obj: dict = dict()  # to store attached devices' objects

        self.wait_for_gui = wait_for_gui

        self.callbacks: dict = dict()
        if callbacks and set(callbacks).issubset(CALLBACKS):
            self.callbacks = callbacks
            for callback in set(callbacks).difference(CALLBACKS):
                self.callbacks[callback] = log_stuff
        else:
            for callback in CALLBACKS:
                self.callbacks[callback] = log_stuff
