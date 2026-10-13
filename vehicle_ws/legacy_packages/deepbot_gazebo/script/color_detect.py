#!/usr/bin/env python
# -*- coding: UTF-8 -*-
import cv2
import numpy as np

path = './color_detect.jpg'
lower = np.array([0, 87,155])
upper = np.array([22,255,255])

img = cv2.imread(path)
imgHSV = cv2.cvtColor(img,cv2.COLOR_BGR2HSV)


# 获得指定颜色范围内的掩码
mask = cv2.inRange(imgHSV,lower,upper)
# 对原图图像进行按位与的操作，掩码区域保留
imgResult = cv2.bitwise_and(img, img, mask=mask)

cnts = cv2.findContours(mask.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[-2]
c = max(cnts, key=cv2.contourArea)
((x, y), radius) = cv2.minEnclosingCircle(c)
cv2.circle(img, (int(x), int(y)), int(radius), (0, 0, 0), 4)

cv2.imshow("detect", img)
cv2.imshow("Mask", mask)
cv2.imshow("Result", imgResult)
    
cv2.waitKey(0)

