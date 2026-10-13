#include <ros/ros.h>
#include <yolo_detection_node.hpp>

using namespace yolo_detection;



int main(int argc, char** argv)
{
  ros::init(argc, argv, "deepbot_yolo_detection_node");

  YoloDetectionNode node;

  node.run();
  
  return 0;
}
