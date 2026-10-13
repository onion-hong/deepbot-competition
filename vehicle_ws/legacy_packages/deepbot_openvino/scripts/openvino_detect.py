#!/usr/bin/env python
# _*_ coding:utf-8 _*_

import rospy
import numpy as np
import os,cv2
import time
from cv_bridge import CvBridge, CvBridgeError
from sensor_msgs.msg import Image, CompressedImage
from vision_msgs.msg import BoundingBox2D, Detection2DArray,ObjectHypothesisWithPose,Detection2D
from openvino.runtime import Layout
from openvino.preprocess import ColorFormat, ResizeAlgorithm
from openvino.runtime import Core, Type
from openvino.preprocess import PrePostProcessor


CLASS_NAMES = ["start", "crossing"]



class OpenvinoDetect():
    def __init__(self):
        rospy.init_node('detect_node', log_level=rospy.INFO)
        self.rate = rospy.get_param('~rate', 10)
        self.camera_topic = rospy.get_param('~camera_topic', '/camera/rgb/image_raw/')
        r = rospy.Rate(self.rate)
        self.name = rospy.get_name()
        rospy.on_shutdown(self.shutdown)

        self.sub_image_type = "raw"
        self.pub_type = "raw"
        self.cv_image = None

        self.prev_time = 0

        #init openvino
        self.model_path = "/home/deepbot/catkin_ws/src/deepbot_project/deepbot_openvino/model/"
        self.compiled_model = self.init_openvino_model(self.model_path + "race.xml", self.model_path + "race.bin")


        if self.sub_image_type == "compressed":
            self.sub_image_original = rospy.Subscriber(self.camera_topic+'compressed', CompressedImage, self.ImageCallback, queue_size = 1)
        elif self.sub_image_type == "raw":
            self.sub_image_original = rospy.Subscriber(self.camera_topic, Image, self.ImageCallback, queue_size = 1)

        if self.pub_type == "compressed":
            self.pub_det_image = rospy.Publisher('/object_image/compressed', CompressedImage, queue_size=1)
        else:
            self.pub_det_image = rospy.Publisher('/object_image', Image, queue_size=1)

        self.detect_pub = rospy.Publisher("/detect_node/detections", Detection2DArray, queue_size=10)

        self.cvBridge = CvBridge()

        while not rospy.is_shutdown():
            if self.cv_image is not None:
                input_tensor = self.preprocess(self.cv_image)
                infer_request = self.compiled_model.create_infer_request()
                infer_request.infer({self.compiled_model.inputs[0]: input_tensor})

                outputs = [infer_request.get_output_tensor(i).data for i in range(len(self.compiled_model.outputs))]
                boxes, scores, class_ids = self.postprocess(outputs, self.cv_image.shape)
                # 绘制结果
                object_msg = Detection2DArray()
                for box, score, cls_id in zip(boxes, scores, class_ids):
                    cv2.rectangle(self.cv_image, (box[0], box[1]), (box[2], box[3]), (0,255,0), 2)
                    label = f"{CLASS_NAMES[cls_id]}: {score:.2f}"
                    (text_width, text_height), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
                    text_y = box[1] - 10 if box[1] - 10 > 10 else box[1] + 20
                    detmsg = Detection2D()
                    detmsg.bbox.size_x = int(box[2] - box[0])
                    detmsg.bbox.size_y = int(box[3] - box[1])
                    detmsg.bbox.center.x = int(box[0]) + detmsg.bbox.size_x/2
                    detmsg.bbox.center.y = int(box[1]) + detmsg.bbox.size_y/2
                    detmsg.header.frame_id = CLASS_NAMES[cls_id]
                    hyp = ObjectHypothesisWithPose()
                    hyp.id = cls_id
                    hyp.score = score
                    detmsg.results.append(hyp)
                    object_msg.detections.append(detmsg)
                    self.detect_pub.publish(object_msg)
                    cv2.rectangle(self.cv_image,
                                 (box[0], text_y - text_height),
                                 (box[0] + text_width, text_y + 5),
                                 (0,255,0), -1)
                    cv2.putText(self.cv_image, label,
                               (box[0], text_y),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                               (0,0,0), 2)

                # 显示FPS
                curr_time = time.time()
                fps = 1 / (curr_time -self.prev_time)
                self.prev_time = curr_time
                cv2.putText(self.cv_image, f"FPS: {fps:.2f}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,0), 2)
                if self.pub_type == "compressed":
                # publishes traffic sign image in compressed type
                    self.pub_det_image.publish(self.cvBridge.cv2_to_compressed_imgmsg(self.cv_image, "jpg"))

                elif self.pub_type == "raw":
                # publishes traffic sign image in raw type
                    self.pub_det_image.publish(self.cvBridge.cv2_to_imgmsg(self.cv_image, "bgr8"))
            r.sleep()


    def init_openvino_model(self, model_xml, model_bin):
        core = Core()
        model = core.read_model(model=model_xml, weights=model_bin)

        ppp = PrePostProcessor(model)
        # 输入张量配置（需与摄像头数据流匹配）
        ppp.input().tensor() \
            .set_layout(Layout('NHWC')) \
            .set_color_format(ColorFormat.BGR) \
            .set_spatial_dynamic_shape()  # 启用动态分辨率支持[1](@ref)

        # 预处理流程（集成到模型执行图）
        ppp.input().preprocess() \
            .convert_color(ColorFormat.RGB) \
            .resize(ResizeAlgorithm.RESIZE_LINEAR, 640, 640) \
            .convert_layout(Layout('NCHW')) \
            .convert_element_type(Type.f32)  # 精度转换

        model = ppp.build()
        return core.compile_model(model, "CPU")

    def preprocess(self, frame):
        # 直接返回添加batch维度的原始帧数据（预处理由OpenVINO完成）
        #input_tensor = np.expand_dims(frame, 0).astype(np.float32) / 255.0
        return np.expand_dims(frame, 0).astype(np.float32) / 255.0
        #return input_tensor

    def postprocess(self, outputs, frame_shape, conf_thres=0.3, iou_thres=0.4):
        h, w = frame_shape[:2]
        boxes_list = []
        scores_list = []
        class_ids_list = []

        output = outputs[0][0]  # 去除batch维度
        grid_size = 640  # 模型输入尺寸

        # 置信度过滤
        scores = output[:, 4] * output[:, 5:].max(axis=1)
        mask = scores > conf_thres
        filtered_output = output[mask]

        # 坐标转换
        for det in filtered_output:
            cx, cy, width, height, conf = det[0], det[1], det[2], det[3], det[4]

            # 坐标计算
            x_center = cx * w / grid_size
            y_center = cy * h / grid_size
            box_width = width * w / grid_size
            box_height = height * h / grid_size

            x1 = int(x_center - box_width/2)
            y1 = int(y_center - box_height/2)
            x2 = int(x_center + box_width/2)
            y2 = int(y_center + box_height/2)

            x1 = max(0, min(x1, w-1))
            y1 = max(0, min(y1, h-1))
            x2 = max(0, min(x2, w-1))
            y2 = max(0, min(y2, h-1))

            boxes_list.append([x1, y1, x2, y2])
            scores_list.append(float(conf))
            class_ids_list.append(int(det[5:].argmax()))

        # NMS处理
        indices = cv2.dnn.NMSBoxes(boxes_list, scores_list, conf_thres, iou_thres)
        return [boxes_list[i] for i in indices], [scores_list[i] for i in indices], [class_ids_list[i] for i in indices]


    def ImageCallback(self, image_msg):
        if self.sub_image_type == "compressed":
            #converting compressed image to opencv image
            np_arr = np.fromstring(image_msg.data, np.uint8)
            self.cv_image = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        elif self.sub_image_type == "raw":
            self.cv_image = self.cvBridge.imgmsg_to_cv2(image_msg, "bgr8")


    def shutdown(self):
        # Release handle to the webcam
        rospy.logwarn("now will shutdown face_location_node ...")

if __name__ == '__main__':
    try:
        detect = OpenvinoDetect()
        rospy.spin()
    except Exception as e:
        rospy.logerr("%s", str(e))
        os._exit(1)

