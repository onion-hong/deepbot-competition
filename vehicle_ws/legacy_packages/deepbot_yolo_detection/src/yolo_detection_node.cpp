#include <yolo_detection_node.hpp>
#include <iostream>
#include <fstream>
#include <cv_bridge/cv_bridge.h>
#include <opencv2/imgproc.hpp>
#include <vision_msgs/Detection2DArray.h>
#include <vision_msgs/VisionInfo.h>


namespace yolo_detection {
vision_msgs::VisionInfo info_msg;

static std::vector<std::string> objects_names_from_file(std::string const filename)
{
    std::ifstream file(filename);
    std::vector<std::string> file_lines;
    if (!file.is_open()) return file_lines;
    for(std::string line; getline(file, line);) file_lines.push_back(line);
    std::cout << "object names loaded \n";

    return file_lines;
}

YoloDetectionNode::YoloDetectionNode()
    : privateNh("~"),
      it(nh)
{
    std::string yolo_config_file, yolo_names_file, yolo_weights_file;
    float yolo_thresh;
    cnt = 0;

    privateNh.getParam("yolo_names_file", yolo_names_file);
    privateNh.getParam("yolo_config_file", yolo_config_file);
    privateNh.getParam("yolo_weights_file", yolo_weights_file);
    if(!privateNh.getParam("yolo_thresh", yolo_thresh))
    	privateNh.param<float>("yolo_thresh", yolo_thresh, 0.5f);

    printf("yolo_thresh: %f", yolo_thresh);

    yoloDetector = new Detector(yolo_config_file, yolo_weights_file, yolo_thresh/* thresh*/);
    objectsNames = objects_names_from_file(yolo_names_file);

    rgbSub = it.subscribe("/image_color", 1, &YoloDetectionNode::imageCallback, this);
    image_pub = it.advertise("/yolo_detect_node/detections/detect_image", 1);
    detection_pub = privateNh.advertise<vision_msgs::Detection2DArray>("/yolo_detect_node/detections", 25);

}

YoloDetectionNode::~YoloDetectionNode()
{
    delete yoloDetector;
}

void YoloDetectionNode::imageCallback(const sensor_msgs::ImageConstPtr& im_msg)
{
    
    if ((cnt%2) != 0){
    	cnt += 1;
        return;
    }else{
        cnt = 1;
    }
    cv::Mat det_image;
    cv_bridge::CvImage img_bridge;
    sensor_msgs::Image img_msg; // >> message to be sent
    std_msgs::Header header; // empty header
    cv_bridge::CvImageConstPtr cv_ptr_im = cv_bridge::toCvShare(im_msg);

    cv::Mat color = cv_ptr_im->image.clone();
    cv::cvtColor(color, color, cv::COLOR_RGB2BGR);
    cv::resize(color, det_image,  cv::Size(color.cols / 4, color.rows / 4), 0, 0, cv::INTER_NEAREST);

    objects.clear();
    //objects = yoloDetector->detect(color);
    objects = yoloDetector->detect(det_image);
    //header.seq = counter; // user defined counter
    header.stamp = ros::Time::now(); // time

    //cv::Mat detection = color.clone();
    cv::Mat detection = det_image.clone();
    drawBoxes(detection);
    img_bridge = cv_bridge::CvImage(header, sensor_msgs::image_encodings::BGR8, detection);
    img_bridge.toImageMsg(img_msg); 
    image_pub.publish(img_msg);

    //cv::imshow("color", color);
    //cv::imshow("detection", detection);

    //cv::waitKey(1);
}

void YoloDetectionNode::run()
{
    ros::spin();
}

void YoloDetectionNode::drawBoxes(cv::Mat mat_img)
{
    int const colors[6][3] = { { 1,0,1 },{ 0,0,1 },{ 0,1,1 },{ 0,1,0 },{ 1,1,0 },{ 1,0,0 } };
    vision_msgs::Detection2DArray msg;
    for(auto &i : objects)
    {
        cv::Scalar color = obj_id_to_color(i.obj_id);
        cv::rectangle(mat_img, cv::Rect(i.x, i.y, i.w, i.h), color, 2);

        if(objectsNames.size() > i.obj_id)
        {
            vision_msgs::Detection2D detMsg;

            std::string obj_name = objectsNames[i.obj_id];
            if (i.track_id > 0) obj_name += " - " + std::to_string(i.track_id);
            cv::Size const text_size = getTextSize(obj_name, cv::FONT_HERSHEY_COMPLEX_SMALL, 1.2, 2, 0);
            int max_width = (text_size.width > i.w + 2) ? text_size.width : (i.w + 2);
            max_width = std::max(max_width, (int)i.w + 2);

	    detMsg.bbox.size_x = i.w;
            detMsg.bbox.size_y = i.h;

	    detMsg.bbox.center.x = i.x + i.w/2;
            detMsg.bbox.center.y = i.y + i.h/2;

	    detMsg.bbox.center.theta = 0.0f;
	    vision_msgs::ObjectHypothesisWithPose hyp;
	    detMsg.header.frame_id = obj_name.c_str();
	    hyp.id = i.obj_id ;
            hyp.score = i.prob;

	    detMsg.results.push_back(hyp);
            msg.detections.push_back(detMsg);
	    ROS_INFO("object id: %d object name: %s , core : %f\n", i.obj_id, obj_name.c_str(), i.prob);


            cv::rectangle(mat_img, cv::Point2f(std::max((int)i.x - 1, 0), std::max((int)i.y - 35, 0)),
                          cv::Point2f(std::min((int)i.x + max_width, mat_img.cols - 1), std::min((int)i.y, mat_img.rows - 1)), color, CV_FILLED, 8, 0);
            putText(mat_img, obj_name, cv::Point2f(i.x, i.y - 16), cv::FONT_HERSHEY_COMPLEX_SMALL, 1.2, cv::Scalar(0, 0, 0), 2);
        }
	detection_pub.publish(msg);

    }
}

} // namespace deepbot_yolo_detection
