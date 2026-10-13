cmake_minimum_required(VERSION 3.0.2)
project(deepbot)
find_package(catkin REQUIRED COMPONENTS geometry_msgs nav_msgs roscpp rospy sensor_msgs riki_msgs std_msgs tf)
catkin_package(INCLUDE_DIRS include LIBRARIES deep_base
  CATKIN_DEPENDS roscpp rospy tf nav_msgs riki_msgs geometry_msgs sensor_msgs std_msgs)
include_directories(include ${catkin_INCLUDE_DIRS})
add_library(deep_base src/xt_base.cpp)
add_executable(deep_base_node src/xt_base_node.cpp)
add_dependencies(deep_base ${catkin_EXPORTED_TARGETS})
add_dependencies(deep_base_node ${catkin_EXPORTED_TARGETS})
target_link_libraries(deep_base ${catkin_LIBRARIES})
target_link_libraries(deep_base_node deep_base ${catkin_LIBRARIES})
install(TARGETS deep_base deep_base_node
  ARCHIVE DESTINATION ${CATKIN_PACKAGE_LIB_DESTINATION}
  LIBRARY DESTINATION ${CATKIN_PACKAGE_LIB_DESTINATION}
  RUNTIME DESTINATION ${CATKIN_PACKAGE_BIN_DESTINATION})
install(DIRECTORY include/ DESTINATION ${CATKIN_GLOBAL_INCLUDE_DESTINATION})
install(DIRECTORY launch param DESTINATION ${CATKIN_PACKAGE_SHARE_DESTINATION})
