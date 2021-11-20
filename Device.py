import os
import logging
import xml.etree.cElementTree as ET
import pathlib


DEVICES_SETTINGS_DIR = 'devices'
pathlib.Path(DEVICES_SETTINGS_DIR).mkdir(parents=True, exist_ok=True)


class Device:
    def __init__(self, serial: str, logs_enabled: bool = False, logs_filter: str = ''):
        logging.info("Attaching to device...")
        self.device_serial: str = serial
        self.logs_enabled: bool = logs_enabled
        self.logs_filter: str = logs_filter

        self.is_recording_video: bool = False

        self.device_settings_persistence = {
            "test1": "asd",
            "test2": "dsa"
        }

        self.device_xml: str = os.path.join(DEVICES_SETTINGS_DIR, f'{serial}.xml')

    def load_settings_file(self):
        logging.info("Loading device settings...\n")

        logging.info(f'Checking for Device settings file at "{self.device_xml}" and possibly loading it..')

        try:
            tree = ET.parse(self.device_xml)
        except FileNotFoundError:
            logging.info("Settings file for device nonexistent! Clean slate... :)")
            return
        except ET.ParseError:
            logging.error("Failed to load Device settings! :( XML Error!")
            return

        return tree.getroot()

    def set_logs(self, logs_bool, fltr=None):
        if not isinstance(logs_bool, bool):
            logging.info('Logs setter got a non bool type... Defaulting to False.')
            self.logs_enabled = False
        else:
            self.logs_enabled = logs_bool
            logging.info(f"Logs enabled: {logs_bool}")

        if fltr is not None:
            self.logs_filter = fltr
            logging.info(f"Filter {fltr}")
