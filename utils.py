from re import sub, match
from cv2 import cv2
from pathlib import Path
from os import path
import logging


def get_list_average(list_in: list, min_index: int = None, max_index: int = None) -> float:
    """
    Returns an average of all the items in passed list or of those between index min and max
    :param list_in:
    :param min_index:
    :param max_index:
    :return:
    """
    if not isinstance(list_in, list) and len(list_in) == 0:
        return

    if min_index is not None:
        if max_index is None:
            list_in = [list_in[min_index]]
        else:
            list_in = list_in[min_index:max_index]

    result = 0.0
    divider = 0

    for item in list_in:
        if isinstance(item, float) or isinstance(item, int) or (isinstance(item, str) and item.isdigit()):
            if isinstance(item, str) and item.isdigit():
                result += float(item)
                divider += 1
                continue
            result += item
            divider += 1
    if result == 0 or divider == 0:
        return 0.0

    return result / divider


def compare_lists(list1, list2) -> list:
    return [str(s) for s in (set(list1) ^ set(list2))]


def compare_sets(set1, set2) -> list:
    return [str(s) for s in (set1 ^ set2)]


def get_file_paths(line_list, f_pattern):
    file_paths = list()
    f_path = sub(r":", "/", line_list[0])

    while len(line_list) > 1:
        if match(f_pattern, line_list[1]):
            file_paths.append(f_path + line_list[1])
            line_list.pop(0)

        else:
            return file_paths

    if match(f_pattern, line_list[0]):
        file_paths.append(f_path + line_list[0])
        line_list.pop(0)
        return file_paths

    line_list.pop(0)


def extract_video_frame(videofile, start_frame, number_of_frames=None, end_frame=None, skip_frames=0,
                        subfolder=False, out_format="JPEG") -> list:
    output = list()

    formats = {
        "JPEG": "jpg",
        "PNG": "png"
    }

    file_name = path.basename(videofile)
    file_path = path.dirname(videofile)

    if subfolder:
        file_path = path.join(file_path, subfolder)
        # Create dirs if not exist
        Path(file_path).mkdir(parents=True, exist_ok=True)

    vidcap = cv2.VideoCapture(videofile)
    success, image = vidcap.read()

    current_frame = 1

    next_frame = start_frame

    img_out = []

    if end_frame is None or end_frame == 0:
        end_frame = start_frame + ((number_of_frames * skip_frames) if skip_frames else number_of_frames) - 1
    else:
        logging.log(logging.INFO, f"end frame is: {end_frame}")
        if start_frame > end_frame:
            logging.log(logging.ERROR, 'Start frame must be smaller int than end frame!')
            return

    while success:
        if start_frame <= current_frame <= end_frame:
            if skip_frames:
                if current_frame == next_frame:
                    img_out = path.join(file_path, f"{file_name}_frame{current_frame}.{formats[out_format]}")
                    output.append(img_out)
                    cv2.imwrite(img_out, image)  # save frame as JPEG file

                    next_frame += skip_frames
            else:
                img_out = path.join(file_path, f"{file_name}_frame{current_frame}.{formats[out_format]}")
                output.append(img_out)
                cv2.imwrite(img_out, image)  # save frame as JPEG file
        elif start_frame <= current_frame:
            break

        # Save some time..
        if number_of_frames is not None:
            if len(img_out) == number_of_frames:
                break
        elif current_frame >= end_frame:
            break

        success, image = vidcap.read()
        logging.log(logging.DEBUG, f'Read a new frame: {success}')
        current_frame += 1

    return output


def get_video_info(video_in) -> tuple:
    cap = cv2.VideoCapture(video_in)

    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = int(cap.get(cv2.CAP_PROP_FPS))
    n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    logging.log(logging.DEBUG, f"Width: {w}, height: {h}, fps: {fps}, nframes: {n_frames}")
    return w, h, fps, n_frames


# Splits video in half
def split_video(video_in):
    w, h, fps, n_frames = get_video_info(video_in)

    x, y = 0, 0
    height = int(h / 2)
    width = w

    logging.log(logging.DEBUG, f"split video got file: {video_in}")
    logging.log(logging.DEBUG, f"height: {height}, width: {width}, fps: {fps}, n_frames: {n_frames}")

    # (x, y, w, h) = cv2.boundingRect(c)
    # cv2.rectangle(frame, (x,y), (x+w, y+h), (0, 255, 0), 20)
    # roi = frame[y:y+h, x:x+w]
    cap = cv2.VideoCapture(video_in)
    # get fps info from file CV_CAP_PROP_FPS, if possible
    fps = int(round(cap.get(5)))
    # check if we got a value, otherwise use any number - you might need to change this
    if fps == 0:
        fps = 30  # so change this number if cropped video has stange steed, higher number gives slower speed

    vid_name = path.basename(video_in)
    vid_name_no_ext = vid_name.split(".")[0]

    out_cropped = f"{vid_name_no_ext}_cropped"
    logging.log(logging.INFO, f"cropping {vid_name} to {out_cropped}")

    out_path = f'{path.dirname(video_in)}/{out_cropped}.mp4'
    logging.log(logging.DEBUG, f"Is file: {path.isfile(out_path)}")

    suff = 1

    check_path = out_path

    while path.isfile(check_path):
        logging.log(logging.DEBUG, f"Checking {check_path}")

        check_path = f"{out_path.split('.')[0]}_{suff}.mp4"
        suff += 1

    out_path0 = f"{check_path.split('.')[0]}_top.mp4"
    out_path1 = f"{check_path.split('.')[0]}_bottom.mp4"
    logging.log(logging.DEBUG, f'Saving to {out_path0}')
    logging.log(logging.DEBUG, f'Saving to {out_path1}')

    # output_movie = cv2.VideoWriter(out_path, cv2.VideoWriter_fourcc('M','J','P','G'), fps, (width,height))
    output_movie0 = cv2.VideoWriter(out_path0, cv2.VideoWriter_fourcc(*'MP4V'), fps, (width, height))
    output_movie1 = cv2.VideoWriter(out_path1, cv2.VideoWriter_fourcc(*'MP4V'), fps, (width, height))

    while cap.isOpened():
        ret, frame = cap.read()
        # (height, width) = frame.shape[:2]
        if frame is not None:
            curr_frame = int(cap.get(cv2.CAP_PROP_POS_FRAMES))

            # Crop frame
            cropped0 = frame[x:x + height, y:y + width]
            cropped1 = frame[x + height:x + height * 2, y:y + width]

            # Save to file
            output_movie0.write(cropped0)
            output_movie1.write(cropped1)

            # Display the resulting frame - trying to move window, but does not always work
            cv2.namedWindow('producing video', cv2.WINDOW_NORMAL)
            cv2.resizeWindow('producing video', cropped0.shape[1], cropped0.shape[0])
            x_pos = round(width / 2) - round(cropped0.shape[1] / 2)
            y_pos = round(height / 2) - round(cropped0.shape[0] / 2)
            cv2.moveWindow("producing video", x_pos, y_pos)
            cv2.imshow('producing video', cropped0)

            logging.log(logging.INFO, f"Exporting videos... [frame {curr_frame}/{n_frames}]")

            # Press Q on keyboard to stop recording early
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
        else:
            break

    # Close video capture
    cap.release()
    # Closes the video writer.
    output_movie0.release()
    output_movie1.release()

    # Make sure all windows are closed
    cv2.destroyAllWindows()

    logging.log(logging.INFO, 'Video split!')


def only_digits(val) -> int:
    if isinstance(val, str):
        return int(''.join(filter(lambda x: x.isdigit(), val)))
    elif isinstance(val, int):
        return val


def only_chars(val: str) -> int:
    if isinstance(val, str):
        return ''.join(filter(lambda x: x.isalpha(), val))
