iport cv2
import math
import cap
import numpy as np


def is_in_poly(p, poly):
    """
    对点进行筛选，选出符合ROI特定区域内的点
    :param p: 待判断的点坐标， [x, y]
    :param poly: 多边形顶点，[[x1,y1], [x2,y2], [x3,y3], [x4,y4], ...]
    return: is_in若为True，则说明点在ROI区域，保留，反之则删除。
    """
    px, py = p[0], p[1]
    is_in = False
    for i, corner in enumerate(poly):
        # len(poly) = 4    next_i=(0,1,2,3,0,1,2......)
        next_i = i + 1 if i + 1 < len(poly) else 0
        x1, y1 = corner
        x2, y2 = poly[next_i]
        if (x1 == px and y1 == py) or (x2 == px and y2 == py):  # if point is on vertex
            is_in = True
            break
        if min(y1, y2) < py <= max(y1, y2):  # 判断y是否处于y1与y2之间
            x = x1 + (py - y1) * (x2 - x1) / (y2 - y1)
            if x == px:  # if point is on edge
                is_in = True
                break
            elif x > px:  # if point is on left-side of line
                is_in = True
    return is_in


def handle_point(x, y):
    """
    根据x的大小对 x,y 进行排序。再找到最大间隔，并据此把控制点分成两部分。
    return: 返回的是左车道线的x,y坐标以及右车道线x,y的坐标
    """
    lx = [] # 存储左车道线x坐标
    ly = [] # 存储左车道线y坐标
    rx = [] # 存储右车道线x坐标
    ry = [] # 存储右车道线y坐标
    points = zip(x, y)
    # 从小到大排序
    sorted_points = sorted(points)
    x = [point[0] for point in sorted_points]
    y = [point[1] for point in sorted_points]
    # 分割
    Max = 0
    k = 0
    # 找出x坐标最大间隔，分出左车道和右车道
    for i in range(len(x) - 1):
        # 计算欧几里得距离
        d = np.int(math.hypot(x[i + 1] - x[i], y[i + 1] - y[i]))
        if d > Max:
            Max = d
            k = i
    for i in range(len(x)):
        # 坐车道点
        if i < k + 1:
            lx.append(x[i])
            ly.append(y[i])
        # 右车道点
        else:
            rx.append(x[i])
            ry.append(y[i])
    return lx, ly, rx, ry


def poly_fitting(lx, ly, rx, ry):
    """
    分别对两部分控制点进行二次多项式拟合
    """
    lx = np.array(lx)
    ly = np.array(ly)
    rx = np.array(rx)
    ry = np.array(ry)
    fl = np.polyfit(lx, ly, 2)  # 用2次多项式拟合
    fr = np.polyfit(rx, ry, 2)  # 用2次多项式拟合

    ploty = np.linspace(0, 719, 720)
    leftx = fl[0]*ploty**2 + fl[1]*ploty + fl[2]
    rightx = fr[0]*ploty**2 + fr[1]*ploty + fr[2]
    # 定义从像素空间到米的x和y转换
    ym_per_pix = 30/720  # meters per pixel in y dimension
    xm_per_pix = 3.7/700  # meters per pixel in x dimension
    y_eval = np.max(ploty) # 719

    # 将新多项式拟合到世界空间中的x，y
    left_fit_cr = np.polyfit(ploty*ym_per_pix, leftx*xm_per_pix, 2)
    right_fit_cr = np.polyfit(ploty*ym_per_pix, rightx*xm_per_pix, 2)

    # 计算新的曲率半径
    left_curverad = ((1 + (2*left_fit_cr[0]*y_eval*ym_per_pix + left_fit_cr[1])**2)**1.5) / np.absolute(2*left_fit_cr[0])
    right_curverad = ((1 + (2*right_fit_cr[0]*y_eval*ym_per_pix + right_fit_cr[1])**2)**1.5) / np.absolute(2*right_fit_cr[0])
    curvature = ((left_curverad + right_curverad) / 2)  # 曲率

    lane_width = np.absolute(leftx[719] - rightx[719])
    lane_xm_per_pix = 3.7 / lane_width
    # 车辆应该保持偏移的距离
    veh_pos = (((leftx[719] + rightx[719]) * lane_xm_per_pix) / 2.)
    # 当前车辆偏移的距离
    cen_pos = ((1280 * lane_xm_per_pix) / 2.)
    # cen_pos = ((cap.get(3) * lane_xm_per_pix) / 2.)
    # 计算车辆偏移距离
    distance_from_center = cen_pos - veh_pos
    return curvature, distance_from_center


def draw_values(img,curvature,distance_from_center):
    """
    将曲率和车道偏移距离里显示在图片上
    """
    font = cv2.FONT_HERSHEY_SIMPLEX
    radius_text = "Radius of Curvature: %sm"%(round(curvature))
    if distance_from_center > 0:
        pos_flag = 'right'
    else:
        pos_flag = 'left'
    cv2.putText(img, radius_text, (100, 100), font, 1, (255, 255, 255), 2)
    center_text = "Vehicle is %.3fm %s of center"%(abs(distance_from_center), pos_flag)
    cv2.putText(img, center_text, (100, 150), font, 1, (255, 255, 255), 2)
    return img


# if __name__ == "__main__":
#     poly = [[0, 0], [0, 719], [1279, 0], [1279, 719]]
#     lane_x = []
#     lane_y = []
#     is_in = is_in_poly(ppp, poly)
#     if is_in == True:
#         # 将处理后的点坐标添如一个空列表做拟合用
#         lane_x.append(ppp[0])
#         lane_y.append(ppp[1])
#         cv2.circle(frame, ppp, 5, (0, 255, 0), -1)
#
#     lx, ly, rx, ry = handle_point(lane_x, lane_y)
#     curvature, distance_from_center = poly_fitting(lx, ly, rx, ry)
#     draw_values(frame, curvature, distance_from_center)
