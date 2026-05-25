import os
import re

import cv2

rootdir = 'C:\\data\\Tusimple\\test_set\\51'
pattern_number_oeder = '(\d*?).jpg'
f1 = open('C:\\data\\Tusimple\\test_set\\51.txt', 'w')
for root, dirs, files in os.walk(rootdir):
    for dir in dirs:
        print(os.path.join(root, dir))
    files.sort(key=lambda x:int(re.findall(pattern_number_oeder, x)[0]))
    for file in files:
        img_path = os.path.join(root, file)
        # img = cv2.imread(img_path)
        # dim = (1280, 720)
        # resized_img = cv2.resize(img, dim, interpolation=cv2.INTER_AREA)
        # cv2.imwrite(img_path, img)
        # save_path = os.path.join(root.split('\\')[-1], file)
        save_path = img_path
        print(save_path)
        # print(os.path.join(root, file))
        f1.write(save_path)
        f1.write('\n')
f1.close()