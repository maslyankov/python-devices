from cv2 import cv2
import logging

from Device import Device


class USBCamDevice(Device):
    def __init__(self, serial: str, port_id: int):
        super().__init__(serial)

        self.port_id = port_id

    def open_stream(self) -> cv2.VideoCapture:
        cap = cv2.VideoCapture(self.port_id)

        return cap

    def open_camera_stream_windowed(self) -> None:
        cap: cv2.VideoCapture = self.open_stream()

        if cap.isOpened():
            width = cap.get(3)  # Frame Width
            height = cap.get(4)  # Frame Height
            logging.debug(f'Default width: {width} height: {height}')

            while True:

                ret, frame = cap.read()
                cv2.imshow(f"Camera {self.port_id} Stream", frame)

                # key: 'ESC'
                key = cv2.waitKey(20)
                if key == 27:
                    break

            cap.release()
            cv2.destroyAllWindows()

    def take_photo(self):
        pass

    def start_video(self):
        pass

    def stop_video(self):
        pass
