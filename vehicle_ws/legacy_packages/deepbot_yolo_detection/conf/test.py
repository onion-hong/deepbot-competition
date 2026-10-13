import cv2
import numpy as np
import time

# 配置参数
CONF_THRESHOLD = 0.5
NMS_THRESHOLD = 0.4
INPUT_WIDTH = 416
INPUT_HEIGHT = 416

# 模型路径
model_weights = "yolov4-tiny-traffic.weights"
model_config = "yolov4-tiny-traffic.cfg"
coco_names = "traffic.names"

# 加载类别标签
with open(coco_names, 'r') as f:
    classes = [line.strip() for line in f]

# 加载模型
net = cv2.dnn.readNetFromDarknet(model_config, model_weights)
net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)  # 强制使用CPU

# 获取输出层
layer_names = net.getLayerNames()
output_layers = [layer_names[i - 1] for i in net.getUnconnectedOutLayers()]

# 视频捕获
cap = cv2.VideoCapture(0)  # 改用摄像头
# cap = cv2.VideoCapture("test.mp4")  # 视频文件

# 帧率统计
prev_time = 0
fps = 0

def format_yolov5(frame):
    row, col, _ = frame.shape
    max_rc = max(row, col)
    result = np.zeros((max_rc, max_rc, 3), dtype=np.uint8)
    result[0:row, 0:col] = frame
    return result

while True:
    ret, frame = cap.read()
    if not ret:
        break
    
    # 预处理
    input_image = format_yolov5(frame)
    blob = cv2.dnn.blobFromImage(input_image, 1/255.0, (INPUT_WIDTH, INPUT_HEIGHT), swapRB=True, crop=False)
    
    # 推理
    net.setInput(blob)
    outs = net.forward(output_layers)
    
    # 后处理
    class_ids = []
    confidences = []
    boxes = []
    
    for out in outs:
        for detection in out:
            scores = detection[5:]
            class_id = np.argmax(scores)
            confidence = scores[class_id]
            if confidence > CONF_THRESHOLD:
                center_x = int(detection[0] * frame.shape[1])
                center_y = int(detection[1] * frame.shape[0])
                width = int(detection[2] * frame.shape[1])
                height = int(detection[3] * frame.shape[0])
                left = int(center_x - width / 2)
                top = int(center_y - height / 2)
                
                boxes.append([left, top, width, height])
                confidences.append(float(confidence))
                class_ids.append(class_id)
    
    # NMS
    indices = cv2.dnn.NMSBoxes(boxes, confidences, CONF_THRESHOLD, NMS_THRESHOLD)
    
    # 绘制结果
    for i in indices:
        box = boxes[i]
        left = box[0]
        top = box[1]
        width = box[2]
        height = box[3]
        cv2.rectangle(frame, (left, top), (left + width, top + height), (0,255,0), 2)
        label = f"{classes[class_ids[i]]}: {confidences[i]:.2f}"
        cv2.putText(frame, label, (left, top - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,0), 2)

    # 计算FPS
    current_time = time.time()
    fps = 1 / (current_time - prev_time)
    prev_time = current_time
    cv2.putText(frame, f"FPS: {fps:.2f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,0,255), 2)
    
    cv2.imshow("Detection", frame)
    
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
