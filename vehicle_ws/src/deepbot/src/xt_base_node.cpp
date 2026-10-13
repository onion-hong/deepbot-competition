#include <ros/ros.h>
#include "xt_base.h"

int main(int argc, char** argv )
{
    ros::init(argc, argv, "xt_base_node");
    XTBase xt;
    ros::spin();
    return 0;
}
