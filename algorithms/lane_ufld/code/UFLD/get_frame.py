import cv2
import os
from copy import deepcopy

video_full_path = r"C:\data\lane_videos\2022-08-08-14-33-37 Usb Cam Image Raw.mp4"
cap = cv2.VideoCapture(video_full_path)
print(cap.isOpened())
video_name = video_full_path.split('\\')[-1][0:-4]
print(video_name)
frame_count = 1
success = True
while(success):
    success, frame = cap.read()
    print('Read a new frame: ', success)
    if success == False:
        break
    # params.append(cv.CV_IMWRITE_PXM_BINARY)
    # params.append(1)#
    # height, weight, banch = frame.shape
    # print(weight, height, banch)
    print(frame_count)
    if frame_count % 10 == 0:
        dim = (1280, 720)
        resized_img = cv2.resize(frame, dim, interpolation=cv2.INTER_AREA)
        save_path = os.path.join("C:\\data\\lane_videos\\frame\\", video_name)
        if not os.path.exists(save_path):
            os.makedirs(save_path)
        cv2.imwrite(save_path + "\\" + video_name + "_%d.png" % frame_count, resized_img)
        frame_line = deepcopy(resized_img)
        # for i in range(16, 72):
        #     cv2.line(frame_line, (0, i * 10), (1279, i * 10), (255, 0, 0), 1)
        # save_path_l = os.path.join("C:\\Users\\linf1\\Documents\\ZED\\img\\", video_name + '_l')
        # if not os.path.exists(save_path_l):
        #     os.makedirs(save_path_l)
        # cv2.imwrite(save_path_l + "\\" + video_name + "_%d.jpg" % frame_count, frame_line)
        print('save the %d frame' % frame_count)
    frame_count = frame_count + 1

cap.release()
