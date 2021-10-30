import threading
import logging


CALLBACKS: set = {
    "connected",
    "disconnected"
}


def log_stuff(*kwargs, **args):
    logging.log(logging.INFO, f"{str(kwargs)} ; {str(args)}")


class Client:
    def __init__(self, callbacks=None, wait_for_gui=False):
        self.watchdog_thread: threading.Thread = None
        self.connected_devices: set = set()  # to store connected devices

        self.attached_devices: set = set()  # to store attached devices - devices that are connected and we are attached to
        self.devices_obj: dict = dict()  # to store attached devices' objects

        self.wait_for_gui = wait_for_gui

        self.callbacks: dict = dict()
        if set(callbacks).intersection(CALLBACKS):
            self.callbacks = callbacks
        else:
            for callback in CALLBACKS:
                self.callbacks[callback] = log_stuff
