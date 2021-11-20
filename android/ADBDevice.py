import xml.etree.cElementTree as ET
from subprocess import Popen
from time import sleep
from re import findall
from os import path, kill
from datetime import datetime
from pathlib import Path
from re import compile, match
import logging
import typing

from Device import Device
from utils import get_file_paths

XML_DIR = 'XML'
Path(XML_DIR).mkdir(parents=True, exist_ok=True)
# Action types
ACT_SEQUENCES = {
    'goto_photo': 'Change Mode to Photo',
    'photo': 'Shoot Photo',
    'goto_video': 'Change Mode to Video',
    'video_start': 'Start Shooting Video',
    'video_stop': 'Stop Shooting Video'
}


def push_file_send_progress(src, total_size, sent_size):
    logging.log(logging.DEBUG, f"{src} > {sent_size}/{total_size}")


def generate_sequence(subelem):
    seq_temp = []

    logging.log(logging.INFO, "Generating Sequence")

    for action_num, action in enumerate(subelem):

        action_list = []
        data_list = []

        for action_elem_num, action_elem in enumerate(action):
            # import pdb; pdb.set_trace()
            logging.debug(f"action elem: {action_elem}")
            logging.debug(f"data_list before {data_list}")
            if action_elem.tag == 'id':
                action_list.append(action_elem.text)
                logging.debug(f"Elem num: {action_elem_num}, elem text: {action_elem.text}")

            elif action_elem.tag == 'description':
                logging.debug(f'description: {action_elem.text}')
                if action_elem.text is not None:
                    data_list.append(action_elem.text)
                else:
                    data_list.append('')

            elif action_elem.tag == 'coordinates':
                coords_list = []

                for inner_num, inner in enumerate(action_elem):
                    # list should be: self.shoot_photo_seq = [
                    # ['element_id', ['Description', [x, y], 'tap' ] ]
                    # ]
                    coords_list.append(inner.text)
                data_list.append(coords_list)

            elif action_elem.tag == 'value':
                data_list.append(action_elem.text)

            logging.debug(f"data_list after {data_list}")
        try:
            data_list.append(action.attrib["type"])  # Set type
        except KeyError:
            logging.log(logging.ERROR, "Error! Invalid XML!")

        action_list.append(data_list)

        seq_temp.append(action_list)
        logging.debug(f'Generated list for action: {action_list}')
    return seq_temp


def xml_from_sequence(obj, prop, xml_obj):
    for action in getattr(obj, prop):
        elem = ET.SubElement(xml_obj, "action")
        elem_id = ET.SubElement(elem, "id")  # set
        elem_desc = ET.SubElement(elem, "description")  # set

        elem.set('type', action[1][2])
        if action[1][2] == 'tap':  # If we have coords set, its a tap action
            elem_coordinates = ET.SubElement(elem, "coordinates")

            x = ET.SubElement(elem_coordinates, "x")  # set
            y = ET.SubElement(elem_coordinates, "y")  # set

            # list should be: self.shoot_photo_seq = [
            # ['element_id', ['Description', [x, y] , type] ]
            # ]
            elem_id.text = str(action[0])
            elem_desc.text = str(action[1][0])
            x.text = str(action[1][1][0])
            y.text = str(action[1][1][1])
        else:
            elem_id.text = str(action[0])
            elem_desc.text = str(action[1][0])
            elem_value = ET.SubElement(elem, "value")
            elem_value.text = str(action[1][1])


# ---------- CLASS ADBDevice ----------
class ADBDevice(Device):
    """
    Class for interacting with devices using adb (ppadb) and AdbClient class
    """

    # ----- INITIALIZER -----
    def __init__(self, client, device_serial):
        super().__init__(
            serial=device_serial,  # Assign device serial as received in arguments
        )

        # Object Parameters #
        # Settings
        self.camera_app: str = ""
        self.images_save_loc: str = ""

        # States
        self.current_camera_app_mode: str = 'photo'

        # Sequences
        self.actions_sequences: dict[str, list] = dict()
        self.actions_time_gap = 1

        # Persistence
        self.adb = client
        self.scrcpy: list[Popen] = list()

        self.is_rooted: bool = False
        self.root()  # Make sure we are using root for device

        self.d = self.adb.client.device(device_serial)  # Create device client object

        try:
            self.friendly_name = self.get_device_model()
            android_ver_response = self.get_android_version()
            self.android_ver = int(android_ver_response.split('.')[0]) if android_ver_response else None
        except RuntimeError:
            logging.log(logging.ERROR, "Device went offline!")
        except ValueError as e:
            logging.log(logging.ERROR, e)

        # TODO: Move to parent class
        self.load_settings_file()

        self.print_attributes()

        self.setup_device_settings()
        self.turn_on_and_unlock()

    # ----- Base methods -----
    def root(self):
        """
        Root the device
        :return:None
        """
        logging.log(logging.INFO, f"Rooting device {self.device_serial}")

        try:
            self.is_rooted = self.adb.root(self.device_serial)
        except ValueError as e:
            logging.log(logging.ERROR, e)

    def remount(self):
        """
        Remount the device
        :return:None
        """
        logging.log(logging.INFO, f"Remount device serial: {self.device_serial}")

        self.adb.remount(self.device_serial)

    def disable_verity(self):
        """
        Disabled verity of device
        :return:None
        """
        logging.log(logging.INFO, "Disabling verity device serial: " + self.device_serial)

        self.adb.disable_verity(self.device_serial)

    def open_shell(self, cmd_str: str = None):
        """
        Open shell terminal of device
        :return:None
        """
        logging.log(logging.INFO, f"Opening shell terminal of: {self.device_serial}")

        self.adb.open_shell(cmd_str=cmd_str)

    def close_shell(self, subp: Popen):
        self.adb.close_shell(subp=subp)

    def open_device_ctrl(self, extra_args=None):
        """
        Open device screen view and control using scrcpy
        :return:None
        """
        self.adb.open_device_ctrl(self)

    def kill_scrcpy(self):
        self.adb.kill_scrcpy(self)

    def record_device_ctrl(self, save_dest):
        self.kill_scrcpy()

        filename = f"{self.friendly_name}_screenrec_{datetime.now().strftime('%Y%m%d-%H%M%S')}.mp4"
        save_dest = path.join(save_dest, filename)

        logging.log(logging.INFO, f"Starting device screen recording to: {save_dest}")

        self.open_device_ctrl(f"-r {save_dest}")

    def exec_shell(self, cmd):
        """
        Execute a shell command on the device
        :param cmd:String command to execute
        :return:None
        """
        try:
            logging.debug(f'executing {cmd}')
            return self.d.shell(cmd)
        except AttributeError as e:
            logging.exception('You tried to reach a device that is already disconnected!')
            self.detach_device(spurious_bool=True)
        except RuntimeError as e:
            logging.log(logging.ERROR, 'Device Disconnected unexpectedly! Detaching...')
            self.detach_device(spurious_bool=True)

    def push_file(self, src, dst):
        """
        Push file to device
        :param src: Path to file to push
        :param dst: Destination on device of file
        :return:None
        """
        src = path.realpath(src)  # .replace(" ", "^ ")
        # dst = dst.replace(" ", "^ ")

        logging.debug(f'Pushing {src} to {dst}')
        try:
            self.d.push(src, dst, progress=push_file_send_progress)
        except RuntimeError as e:
            logging.log(logging.ERROR, e)

    def pull_file(self, src, dst):
        """
        Pull file from device
        :param src: Path file on device to pull
        :param dst: Destination to save the file to
        :return:None
        """
        dst = path.realpath(dst)
        logging.debug(f'Pulling {src} into {dst}')  # Debugging
        self.d.pull(src, dst)

    def detach_device(self, spurious_bool=False):
        self.adb.detach_device(self.device_serial, spurious_bool)

    def is_installed(self, apk):
        return self.d.is_installed(apk)

    def install_apk(self, apk):
        if self.is_installed(apk):
            logging.log(logging.INFO, f"Updating {apk}")
        else:
            logging.log(logging.INFO, f"Installing {apk}")

        self.d.install(apk)

    def uninstall_apk(self, apk):
        if self.is_installed(apk):
            logging.log(logging.INFO, f"Uninstalling {apk}")
            self.d.uninstall(apk)
            return True
        else:
            logging.log(logging.INFO, f"Can't uninstall. {apk} not installed.")
            return False

    # ----- Getters/Setters -----
    def set_sequence(self, seq: str, value: list) -> list:
        self.actions_sequences[seq] = value
        return value

    def get_sequence(self, seq: str):
        return self.actions_sequences.get(seq, None)

    def set_camera_app_pkg(self, pkg):
        self.camera_app = pkg

    def set_images_save_loc(self, loc):
        self.images_save_loc = loc

    def get_camera_app_pkg(self):
        return self.camera_app

    # ----- Getters -----
    def get_device_model(self):
        """
        Get the device model
        :return: String of device model
        """
        response = self.exec_shell("getprop ro.product.model")
        return response.strip() if response else None

    def get_device_name(self):
        """
        Get the device name
        :return: String of device name
        """
        response = self.exec_shell("getprop ro.product.name")
        return response.strip() if response else None

    def get_manufacturer(self):
        return self.exec_shell("getprop ro.product.manufacturer").strip()

    def get_board(self):
        response = self.exec_shell("getprop ro.product.board")
        return response.strip() if response else None

    def get_android_version(self):
        response = self.exec_shell("getprop ro.build.version.release")
        return response.strip() if response else None

    def get_sdk_version(self):
        response = self.exec_shell("getprop ro.build.version.sdk")
        return response.strip() if response else None

    def get_cpu(self):
        response = self.exec_shell("getprop ro.product.cpu.abi")
        return response.strip() if response else None

    def get_current_app(self):
        """
        Returns currently opened app package and its current activity
        :return:None
        """
        # dumpsys window windows | grep -E 'mFocusedApp' <- had issues with this one, sometimes returns null
        # Alternative -> dumpsys activity | grep top-activity
        # First try
        try:  # This works on older Android versions
            current = self.exec_shell("dumpsys activity | grep -E 'mFocusedActivity'").strip().split(' ')[3].split('/')
            if current is None:
                logging.debug('(Get Current App) Focused Activity is empty, trying top-activity...')
                current = self.exec_shell("dumpsys activity | grep top-activity").strip().split(' ')[9].split(':')
                temp = current[1].split('/')
                temp.append(current[0])  # -> [pkg, activity_id, pid]
                return temp
        except IndexError:
            pass
        else:
            return current

        # Second try
        try:
            current = self.exec_shell("dumpsys window windows | grep -E 'mFocusedApp'").split(' ')[6].split('/')
        except IndexError:
            pass
        else:
            return current

        # Third try
        try:
            current = self.exec_shell("dumpsys window windows | grep -E 'ActivityRecord'").split(' ')[13].split('/')
        except IndexError:
            pass
        else:
            logging.debug(f"Current app: {current}")
            return current
        # else
        logging.log(logging.ERROR, "Can't fetch currently opened app! \nOutput of dumpsys: ")

        logging.log(logging.ERROR, self.exec_shell("dumpsys window windows"))
        return None

    def get_installed_packages(self):
        """
        Get the packages (apps) installed on device
        pm list packages - more widely available than:
        'cmd package list packages -e'
        :return:List of strings, each being an app package on the device
        """
        return sorted(self.exec_shell("pm list packages").replace('package:', '').splitlines())

    def get_recursive_files_list(self, target_dir):
        files_list = self.exec_shell(f"ls -R {target_dir}").splitlines()

        directory_pattern = compile(r"^\/.*\:$")
        file_pattern = compile(r"^\w+.*\w+$")

        files = list()
        while files_list:
            if match(directory_pattern, files_list[0]):
                files.append(get_file_paths(files_list, file_pattern))
            else:
                files_list.pop(0)

        logging.debug(files)
        return files
        # for num, f in enumerate(files_list):
        #     files_list[num] = f.split()

    def get_files_list(self, target_dir, extra_args=None, get_full_path=False):
        """
        Get a list of files in target_dir on the device
        :return: List of strings, each being a file located in target_dir
        """
        if not target_dir.startswith("/"):
            logging.debug(f"Prepending / to path {target_dir}")
            target_dir = f"/{target_dir}"
        if not target_dir.endswith("/"):
            logging.debug(f"Appending / to path {target_dir}")
            target_dir = f"{target_dir}/"

        # Command arguments
        args = ''
        if get_full_path:
            logging.debug("get_full_path is True")
            if extra_args is None:
                extra_args = list()
            extra_args.append('-d')
            target_dir += '*'

        if extra_args:
            for arg in extra_args:
                if isinstance(arg, tuple):
                    args += f"{arg[0]} {arg[1]} "
                elif isinstance(arg, str):
                    args += f"{arg} "
                else:
                    logging.log(logging.ERROR, f"Unexpected argument: {str(arg)}")

        # Executing command
        files_list = self.exec_shell(
            f"ls {args.rstrip(' ')} {target_dir}"
        ).splitlines()

        logging.debug(f"Files List Got: {files_list}")

        # Clear whitespaces from filenames
        #       Turns out some devices add a trailing whitespace to each filename, we don't want that
        for i, f in enumerate(files_list):
            if f.startswith("total"):
                total_num_of_files = f.split()[1]
                logging.debug(f"Total num of files {total_num_of_files}")
                continue
            files_list[i] = f.strip()

        logging.log(logging.DEBUG, f"Files List After strip: {files_list}")

        try:
            check_for_missing_dir = files_list[0]
        except IndexError:
            return []

        if 'No such file or directory' in check_for_missing_dir \
                or "Not a directory" in check_for_missing_dir:
            return None
        else:
            return files_list

    def get_files_and_folders(self, target_dir):
        total_size = None
        files_list = self.get_files_list(target_dir, extra_args=['-l'])
        # links: lrwxrwxrwx root     root              1970-01-01 02:00 fg_algo_cos -> /sbin/fg_algo_cos
        # folders: drwxrwx--- system   cache             2020-09-04 15:20 cache
        # files: -rwxr-x--- root     root       526472 1970-01-01 02:00 init
        # Some devices return size for folders as well

        try:
            check_for_missing_dir = files_list[0]
        except IndexError:
            logging.log(logging.ERROR, f"files_list: {files_list}")
            return []
        except TypeError:
            logging.log(logging.ERROR, f"files_list: {files_list}")
            return []

        if 'No such file or directory' in check_for_missing_dir \
                or "Not a directory" in check_for_missing_dir:
            return None

        ret_list = list()

        for item in files_list:
            item_split = list()

            for listed_item in item.split(" "):
                if listed_item != '':
                    item_split.append(listed_item)

            if item[0] == 'total':
                total_size = item[1]

            item_flags = item_split[0]

            if 'd' in item_flags:
                # It's a dir
                file_type = 'dir'
            elif 'l' in item_flags:
                # It's a link
                file_type = 'link'
            else:
                # It's a file
                file_type = 'file'

            try:
                index_count = 1
                if item_split[index_count].isdigit():
                    # logging.debug("Item has subelements count column")
                    index_count += 1

                item_owner = item_split[index_count]
                item_owner_group = item_split[index_count + 1]

                if file_type != 'link':
                    item_date = item_split[-3]
                    item_time = item_split[-2]
                    item_name = item_split[-1]
                    # if file_type == 'file':
                    try:
                        if item_split[-4].isdigit():
                            item_size = int(item_split[-4])
                    except ValueError:
                        item_size = None
                else:
                    item_date = item_split[-5]
                    item_time = item_split[-4]
                    item_name = item_split[-3]
                    item_link_endpoint = item_split[-1]

                ret_list.append(
                    {
                        'file_type': file_type,
                        'flags': item_flags,
                        'owner': item_owner,
                        'owner_group': item_owner_group,
                        'date': item_date,
                        'time': item_time,
                        'name': item_name
                    }
                )

                if index_count == 2:
                    logging.debug(f"Item {item_name} has {item_split[index_count - 1]} subelements.")

                # print(f"{file_type} '{item_name}' owned by {item_owner}:{item_owner_group} from {item_date} {item_time} \t {item_flags}")
                if file_type == 'file':
                    try:
                        ret_list[-1]['file_size'] = item_size
                    except NameError as e:
                        logging.log(logging.ERROR, e)
                elif file_type == 'link':
                    ret_list[-1]['link_endpoint'] = item_link_endpoint

            except IndexError as e:
                logging.exception(e)
                logging.debug(f"files_list: {files_list}")
                logging.debug(f"item: {item}")
                logging.debug(f"item_split: {item_split}")

        ret_list.sort(key=lambda x: x['file_type'])
        logging.debug(f"Returning list: {ret_list}")

        if total_size:
            logging.log(logging.INFO, f"Total size of {target_dir} is '{total_size}'")

        return ret_list

    def get_file_type(self, target_file):
        # TODO Optimize get_file_type
        logging.debug(f"Checking '{target_file}'...")

        target_file = target_file.rstrip('/')
        parent_folder = path.dirname(target_file)
        files_in_dir = self.get_files_and_folders(parent_folder)

        filename = target_file.split('/')[-1]

        file_info = next((item for item in files_in_dir if item["name"] == filename), False)
        logging.debug(f"Returning filetype for file '{target_file}' (Searching for '{filename}'): {file_info}")

        if not file_info:
            logging.debug(f"Files in dir: {files_in_dir}")
            logging.debug(f"File basename: {path.basename(target_file)}")

        return file_info['file_type'] if file_info else None

    def get_screen_resolution(self):
        """
        Get screen resolution of device
        :return:List height and width
        """
        try:
            res = self.exec_shell('dumpsys window | grep "mUnrestricted"').strip().split(' ')[1].split('x')
        except IndexError:
            res = self.exec_shell('dumpsys window | grep "mUnrestricted"').rstrip().split('][')[1].strip(']').split(',')

        return res

    def get_wakefulness(self):
        try:
            return self.exec_shell("dumpsys activity | grep -E 'mWakefulness'").split('=')[1]
        except IndexError:
            logging.warning('There was an issue with getting device wakefullness - probably a shell error!')
            return None

    def get_device_leds(self):
        """
        Get a list of the leds that the device has
        :return:None
        """
        return self.exec_shell("ls /sys/class/leds/").strip().replace('\n', '').replace('  ', ' ').split(' ')

    # ----- Binary getters -----

    def has_screen(self):  # TODO Make this return a valid boolean (now it sometimes works, sometimes doesn't)
        """
        Check if the device has an integrated screen (not working all the time)
        :return:Bool Should return a Bool
        """
        before = self.exec_shell("dumpsys deviceidle | grep mScreenOn").split('=')[1].strip()
        self.exec_shell('input keyevent 26')
        sleep(0.5)
        after = self.exec_shell("dumpsys deviceidle | grep mScreenOn").split('=')[1].strip()

        if before == after:
            logging.log(logging.INFO, "Device has no integrated screen!")

        self.exec_shell('input keyevent 26')

    def is_sleeping(self):
        response = self.exec_shell("dumpsys activity | grep -E 'mSleeping'")
        state = response.strip() if response else None

        if response is None:
            return

        if "No such file" in state:
            logging.log(logging.ERROR, f"Found no such file in state: {state}")
            return None, None

        try:
            state = state.split(' ')
            is_sleeping = state[0].split('=')[1]
        except IndexError as e:
            is_sleeping = None
            logging.log(logging.ERROR, f"State: {state}\n{e}")

        try:
            lock_screen = state[1].split('=')[1]
        except IndexError as e:
            lock_screen = None
            logging.log(logging.ERROR, f"State: {state}\n{e}")
        return is_sleeping, lock_screen

    def is_adb_enabled(self):
        # Kind of useless as if this is actually false, we will not be able to connect
        return True if self.exec_shell('settings get global adb_enabled').strip() == '1' else False

    # ----- Device Actions -----
    def reboot(self):
        """
        Reboots the device.
        :return:None
        """
        self.exec_shell("reboot")  # TODO Remove device from connected_devices list after reboot
        # self.adb.detach_device(self.device_serial, self)

    def input_tap(self, *coords):  # Send tap events
        """
        Sends tap input to device
        :param coords: tap coordinates to use
        :return:None
        """
        logging.debug(f"X: {coords[0][0]}, Y: {coords[0][1]}")

        if self.android_ver <= 5:
            return self.exec_shell("input touchscreen tap {} {}".format(coords[0][0], coords[0][1]))
        else:
            return self.exec_shell("input tap {} {}".format(coords[0][0], coords[0][1]))

    def open_app(self, package):
        """
        Open an app package
        :param package: Specify the app package that you want to open
        :return:None
        """
        if self.get_current_app()[0] != package:
            logging.debug(f'Currently opened: {self.get_current_app()}')
            logging.debug("Opening {}...".format(package))
            self.exec_shell("monkey -p '{}' -v 1".format(package))
            sleep(1)  # Give a bit of time to the device to load the app
        else:
            logging.debug("{} was already opened! Continuing...".format(package))

    def delete_file(self, target):
        """
         Deletes a file if a folder -> the folder's contents
         :return:None
        """
        file_type = self.get_file_type(target)
        args = ""
        if file_type == 'dir' or file_type == 'link':
            target += "/*"
            args += "-rf "

        logging.debug(f"Deleting {file_type} {target} from device!")
        self.exec_shell(f"rm {args}{target}")

    def pull_files(self, files_list: list, save_dest):
        pulled_files = list()

        if not path.isdir(save_dest):
            logging.log(logging.ERROR, "Got a save_dir that is not a dir!")
            return

        for file in files_list:
            if file != '':
                file_dest = path.realpath(path.join(save_dest, path.basename(file)))
                self.pull_file(file, file_dest)
                pulled_files.append(file_dest)

        return pulled_files

    def pull_files_recurse(self, files_list: list, save_dest):
        if not path.isdir(save_dest):
            logging.log(logging.ERROR, "Got a save_dir that is not a dir!")
            return

        if not files_list:
            logging.log(logging.INFO, "No files to pull.")
            return

        for file in files_list:
            if isinstance(file, str) and file != '':
                # logging.debug("file is: ", file)
                filename = file.replace("\\", "/").rstrip("/").split('/')[-1]
                filetype = self.get_file_type(file)
                if filetype:
                    if filetype == 'dir':
                        subdir_files = self.get_files_list(file, get_full_path=True)
                        subdir_save_dest = path.join(save_dest, filename)

                        # Create new folder for the new subdir
                        logging.debug(f"Creating dir: {filename} in {save_dest}")
                        Path(subdir_save_dest).mkdir(parents=True, exist_ok=True)

                        if subdir_files:
                            # Pull into new dir
                            self.pull_files_recurse(subdir_files, subdir_save_dest)
                    elif filetype == 'file':
                        self.pull_file(file, path.join(save_dest, filename))
                    else:
                        logging.warning(f"File {file} is {filetype}. Idk what to do with it...")
                else:
                    logging.log(logging.ERROR, f"Couldn't get filetype for '{file}' :(")
            else:
                logging.log(logging.ERROR, f"Unexpected type {type(file)} of: {str(file)}")

    def pull_and_rename(self, dest, file_loc, filename, suffix=None):
        pulled_files = []

        files_list = self.get_files_list(file_loc, get_full_path=True)

        if not files_list:
            return []
        for num, file in enumerate(files_list):
            if num > 0:
                suffix = f"_{str(num)}"
            new_filename = path.join(dest, f"{filename}{suffix if suffix else ''}.{file.split('.')[1]}")
            self.pull_file(f"{file_loc}{file}", new_filename)
            pulled_files.append(new_filename)
        return pulled_files

    def pull_images(self, dest, clear_folder: bool = False):
        if not self.images_save_loc:
            logging.debug("images_save_loc empty.")
            return

        files = self.get_files_list(self.images_save_loc, get_full_path=True)
        logging.debug(f"Files list: {files}")
        if files is None or len(files) == 0:
            logging.log(logging.INFO, "Images source dir seems empty...")
            return 0

        pulled_images = self.pull_files(files, dest)

        if clear_folder:
            self.delete_file(self.images_save_loc)

        return pulled_images

    def setup_device_settings(self):
        # TODO: Make this save initial settings and set them back on exit
        logging.log(logging.INFO, 'Making the device an insomniac!')
        self.exec_shell('settings put global stay_on_while_plugged_in 1')
        self.exec_shell('settings put system screen_off_timeout 9999999')

    def push_files(self, files_list, files_dest):
        logging.debug(f'Files list: {files_list}')

        for file in files_list:
            logging.debug(f'Pushing: {file}')
            filename = path.basename(file)
            self.push_file(path.normpath(file), files_dest + filename)

    def turn_on_and_unlock(self, skip_state_check: bool = False) -> None:
        if not skip_state_check:
            state = self.is_sleeping()
            if state is None:
                # Probably it's already unlocked and awake?
                logging.error("Probably the device is already unlocked and awake?")
                return

        if skip_state_check or state[0] == 'true':
            self.exec_shell('input keyevent 26')  # Event Power Button
            self.exec_shell('input keyevent 82')  # Unlock

    def set_led_color(self, value, led, target):
        """
        Send a value to a led and a target
        ex: /sys/class/leds/RGB1/group_onoff - led is RGB1, target is group_onoff
        :param value: RGB HEX Value to send
        :param led: To which led to send
        :param target: To which target to send
        :return:None
        """
        try:
            self.exec_shell('echo {} > /sys/class/leds/{}/{}'.format(value, led, target))
            self.exec_shell('echo 60 > /sys/class/leds/{}/global_enable'.format(led))
        except RuntimeError:
            logging.warning("Device was disconnected before we could detach it properly.. :(")

    def identify(self):
        """
        Identify device by blinking it's screen or leds
        :return:None
        """
        leds = self.get_device_leds()
        logging.debug(f"Device leds: {leds}")  # Debugging

        self.exec_shell('echo 1 > /sys/class/leds/{}/global_onoff'.format(leds[0]))

        for k in range(1, 60, 5):  # Blink Leds and screen
            if k != 1:
                sleep(0.3)
            self.exec_shell('echo {}{}{} > /sys/class/leds/{}/global_enable'.format(k, k, k, leds[0]))

            # Devices with screen
            if (k % 11) % 2:
                self.exec_shell('input keyevent 26')  # Event Power Button

        self.exec_shell('echo 60 > /sys/class/leds/{}/global_enable'.format(leds[0]))
        logging.log(logging.INFO, 'Finished identifying!')

    # ----- Settings Persistence -----
    def load_settings_file(self):
        root = super().load_settings_file()
        if root is None:
            return

        # all item attributes
        for elem in root:
            for subelem in elem:
                if subelem.tag == 'serial' and subelem.text != self.device_serial:
                    logging.log(logging.ERROR, 'XML ERROR! Serial mismatch!')

                if subelem.tag == 'friendly_name':
                    self.friendly_name = subelem.text

                if subelem.tag == 'camera_app':
                    self.camera_app = subelem.text

                if subelem.tag == 'images_save_location':
                    self.images_save_loc = subelem.text

                if subelem.tag == 'logs':
                    for data in subelem:
                        if data.tag == 'enabled':
                            if data.text == '1':
                                self.logs_enabled = True
                            else:
                                self.logs_enabled = False
                        if data.tag == 'filter':
                            self.logs_filter = data.text if data.text is not None else ''

                for seq_type in list(ACT_SEQUENCES.keys()):
                    if subelem.tag == seq_type:
                        self.set_sequence(seq_type, generate_sequence(subelem))
                        logging.debug(f'Device Obj New Seq : {self.get_sequence(seq_type)}')

                if subelem.tag == 'actions_time_gap':
                    self.actions_time_gap = int(subelem.text)

                # Device settings persistance
                if elem.tag == 'device_settings_persistence':
                    self.device_settings_persistence[subelem.tag] = subelem.text
                    logging.debug(f"Loading persistent setting {subelem.tag} -> {subelem.text}")

    def get_persist_setting(self, key):
        try:
            resp = self.device_settings_persistence[key]
        except KeyError:
            resp = None

        return resp

    def set_persist_setting(self, key, value):
        self.device_settings_persistence[key] = value

    def save_settings(self):
        root = ET.Element('device')

        # Device info
        info = ET.SubElement(root, 'info')

        serial = ET.SubElement(info, "serial")
        serial.text = self.device_serial

        manufacturer = ET.SubElement(info, "manufacturer")
        manufacturer.text = self.get_manufacturer()

        board = ET.SubElement(info, "board")
        board.text = self.get_board()

        name = ET.SubElement(info, "name")
        name.text = self.get_device_name()

        model = ET.SubElement(info, "model")
        model.text = self.get_device_model()

        cpu = ET.SubElement(info, "cpu")
        cpu.text = self.get_cpu()

        resolution = ET.SubElement(info, "screen_resolution")
        res_data = self.get_screen_resolution()
        try:
            resolution.text = f'{res_data[0]}x{res_data[1]}'
        except IndexError:
            resolution.text = ""

        android_version = ET.SubElement(info, "android_version")
        android_version.text = self.get_android_version()

        friendly = ET.SubElement(info, "friendly_name")
        friendly.text = self.friendly_name

        # Device settings
        settings = ET.SubElement(root, 'settings')

        cam_app = ET.SubElement(settings, "camera_app")
        cam_app.text = self.camera_app

        images_save_loc = ET.SubElement(settings, "images_save_location")
        images_save_loc.text = self.images_save_loc

        logs = ET.SubElement(settings, "logs")

        logs_bool = ET.SubElement(logs, "enabled")
        logs_bool.text = str(1 if self.logs_enabled else 0)

        logs_filter = ET.SubElement(logs, "filter")
        logs_filter.text = self.logs_filter

        for seq_type in list(ACT_SEQUENCES.keys()):
            curr_seq = ET.SubElement(settings, seq_type)
            xml_from_sequence(self, seq_type, curr_seq)

        actions_time_gap = ET.SubElement(settings, "actions_time_gap")
        actions_time_gap.text = str(self.actions_time_gap)

        # Device settings persistance
        settings_device_settings_persistence = ET.SubElement(root, 'device_settings_persistence')

        for key, value in self.device_settings_persistence.items():
            cam_app = ET.SubElement(settings_device_settings_persistence, key)
            cam_app.text = value

        tree = ET.ElementTree(root)
        logging.log(logging.INFO, f'Writing settings to file {self.device_xml}')
        tree.write(self.device_xml, encoding='UTF8', xml_declaration=True)

    # ----- Device UI Parsing -----
    def dump_window_elements(self):
        """
        Dump elements of currently opened app activity window
        and pull them from device to folder XML
        :return:
        None
        """
        source = self.exec_shell('uiautomator dump').split(': ')[1].rstrip()
        current_app = self.get_current_app()
        if source == "null root node returned by UiTestAutomationBridge.":
            logging.log(logging.ERROR, "UIAutomator error! :( Try dumping UI elements again. (It looks like a known error)")
            return

        logging.debug(f'Source returned: {source}')

        self.pull_file(
            source,
            path.join(XML_DIR,
                      '{}_{}_{}.xml'.format(self.device_serial, current_app[0], current_app[1]))
        )
        logging.log(logging.INFO, 'Dumped window elements for current app.')

    def get_clickable_window_elements(self, force_dump=False) -> dict:
        """
        Parse the dumped window elements file and filter only elements that are "clickable"
        :return:
        Dict
            key: element_id or number,
            value: String of elem description, touch location (a list of x and y)
        """
        logging.debug('Parsing UI XML...')
        current_app = self.get_current_app()

        if current_app is None:
            logging.log(logging.ERROR, "Current app unknown... We don't know how to name the xml file so we will say NO! :D ")
            return {}

        logging.debug("Serial {} , app: {}".format(self.device_serial, current_app))
        file = path.join(XML_DIR,
                         '{}_{}_{}.xml'.format(self.device_serial, current_app[0], current_app[1]))

        if force_dump:
            self.dump_window_elements()

        xml_tree = None

        try:
            xml_tree = ET.parse(file)
        except FileNotFoundError:
            logging.log(logging.INFO, 'XML for this UI not found, dumping a new one...')
            self.dump_window_elements()
            try:
                xml_tree = ET.parse(file)
            except ET.ParseError:
                logging.log(logging.ERROR, "Could not get a UI elements file from this device... :(")
                return {}
        except ET.ParseError as error:
            logging.log(logging.ERROR, f"XML Parse Error: {error}")

        try:
            xml_root = xml_tree.getroot()
        except AttributeError:
            logging.log(logging.ERROR, "XML wasn't opened correctly!")
            return {}
        except UnboundLocalError:
            logging.warning("UI Elements XML is probably empty... :( Retrying...")
            self.dump_window_elements()
            xml_tree = ET.parse(file)
            xml_root = xml_tree.getroot()
        elements = {}

        for num, element in enumerate(xml_root.iter("node")):
            elem_res_id = element.attrib['resource-id'].split('/')
            elem_desc = element.attrib['content-desc']
            elem_bounds = findall(r'\[([^]]*)]', element.attrib['bounds'])[0].split(',')

            if (elem_res_id or elem_desc) and int(elem_bounds[0]) > 0:
                elem_bounds[0] = int(elem_bounds[0]) + 1
                elem_bounds[1] = int(elem_bounds[1]) + 1
                if elem_res_id[0] != '':
                    try:
                        elements[elem_res_id[1]] = elem_desc, elem_bounds
                    except IndexError:
                        # For elements that don't have an app id as first element
                        elements[elem_res_id[0]] = elem_desc, elem_bounds
                else:
                    elements[num] = elem_desc, elem_bounds

        return elements

    # ----- Actions Parsing -----
    def do(self, sequence):
        """
        Parses an actions sequence that is passed
        :param sequence: List of actions
        :return:
        """
        self.open_app(self.camera_app)

        logging.debug(f'Doing sequence using device {self.device_serial}')

        for action in sequence:
            act_id = action[0]
            act_data = action[1]
            act_type = act_data[2]
            act_value = act_data[1]
            logging.debug(f"Performing {act_id}")
            if act_type == 'tap':
                self.input_tap(act_value)
            if act_type == 'delay':
                logging.debug(f"Sleeping {act_value}")
                sleep(int(act_value))
            sleep(self.actions_time_gap)

    def take_photo(self):
        logging.debug(f"Current mode: {self.current_camera_app_mode}")
        if self.current_camera_app_mode != 'photo':
            self.do(self.get_sequence("goto_photo"))
            self.current_camera_app_mode = 'photo'
        self.do(self.get_sequence("shoot_photo"))

    def start_video(self):
        logging.debug(f"Current mode: {self.current_camera_app_mode}")
        if self.current_camera_app_mode != 'video':
            self.do(self.get_sequence("goto_video"))
            self.current_camera_app_mode = 'video'
            self.is_recording_video = True
        self.do(self.get_sequence("start_video"))

    def stop_video(self):
        if self.is_recording_video:
            self.do(self.get_sequence("stop_video"))

    # ----- Other -----
    def print_attributes(self):
        # For debugging
        logging.debug("Object properties:\n")
        logging.debug(f"Friendly Name: {self.friendly_name}")
        logging.debug(f"Serial: {self.device_serial}")
        logging.debug(f"Cam app: {self.camera_app}")
        logging.debug(f"images save path: {self.images_save_loc}")
        logging.debug(f"Logs enabled: ({self.logs_enabled}), filter ({self.logs_filter})")
        logging.debug(f"shoot_photo_seq: {self.actions_sequences}")
        logging.debug(f"actions_time_gap: {self.actions_time_gap}")
        logging.debug(f"settings xml file location: {self.device_xml}")
