#ifndef RIKIBOT_YOLO_DETECTION_NODE_HPP
#define RIKIBOT_YOLO_DETECTION_NODE_HPP

#include <ros/ros.h>
#include <opencv2/opencv.hpp>
#include <cv_bridge/cv_bridge.h>
#include <image_transport/image_transport.h>
#include "yolo_v2_class.hpp"



namespace yolo_detection
{

class YoloDetectionNode
{

public:
    YoloDetectionNode();
    ~YoloDetectionNode();
    void imageCallback(const sensor_msgs::ImageConstPtr& msg_rgb);
    void run();
    void drawBoxes(cv::Mat mat_img);

private:
    ros::NodeHandle nh, privateNh;
    image_transport::ImageTransport it;
    image_transport::Subscriber rgbSub;
    image_transport::Publisher  image_pub;
    ros::Publisher detection_pub;
    Detector *yoloDetector; // use smart ptr instead
    std::vector<std::string> objectsNames;
    std::vector<bbox_t> objects;
    int cnt;
};

} // namespace yolo_detection

#endif // YOLO_DETECTION_NODE_HPP
