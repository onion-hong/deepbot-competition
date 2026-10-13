python3 -m pip install --upgrade pip
sudo pip3 install  opencv-python==4.6.0.66 -i https://pypi.tuna.tsinghua.edu.cn/simple
sudo pip3 install  opencv_contrib_python==4.6.0.66 -i https://pypi.tuna.tsinghua.edu.cn/simple
sudo pip3 install matplotlib==3.2.2 -i https://pypi.tuna.tsinghua.edu.cn/simple
sudo pip3 install pillow pyyaml tensorboard tqdm scipy seaborn -i https://pypi.tuna.tsinghua.edu.cn/simple 
sudo pip3 install torch==1.8.0
sudo pip3 install Cython -i https://pypi.tuna.tsinghua.edu.cn/simple
sudo apt-get install python3-pip libopenblas-base libopenmpi-dev 

sudo apt-get install libjpeg-dev zlib1g-dev libpython3-dev libavcodec-dev libavformat-dev libswscale-dev
git clone --branch v0.9.0 https://github.com/pytorch/vision torchvision
cd torchvision
export BUILD_VERSION=0.9.0
sudo  OPENBLAS_CORETYPE=ARMV8 python3 setup.py install



#install labelimg
sudo apt install pyqt5*
sudo apt install qt5-default qttools5-dev-tools
sudo pip3 install pyqt5
sudo pip3 install labelimg


