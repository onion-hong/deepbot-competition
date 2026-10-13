# train.py
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
from torchvision import transforms
import pandas as pd
from PIL import Image
import numpy as np

epochs = 20

# 自定义数据集类
class DrivingDataset(Dataset):
    def __init__(self, csv_file, transform=None):
        self.data = pd.read_csv(csv_file)
        self.transform = transform

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx):
        img_path = self.data.iloc[idx, 0]
        steering = self.data.iloc[idx, 1]
        
        image = Image.open(img_path)
        if self.transform:
            image = self.transform(image)
            
        return image, torch.tensor([steering], dtype=torch.float32)

# 数据预处理
transform = transforms.Compose([
    transforms.Resize((120, 160)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], 
                         std=[0.229, 0.224, 0.225])
])

# 创建数据加载器
dataset = DrivingDataset("/home/deepbot/Work/train_data/data.csv", transform=transform)
dataloader = DataLoader(dataset, batch_size=32, shuffle=True)

class AutoPilot(nn.Module):
    def __init__(self):
        super().__init__()
        self.cnn = nn.Sequential(
            nn.Conv2d(3, 24, 5, stride=2),  # 输入通道3
            nn.ReLU(),
            nn.Conv2d(24, 36, 5, stride=2),
            nn.ReLU(),
            nn.Conv2d(36, 48, 5, stride=2),
            nn.ReLU(),
            nn.Flatten()  # 自动展平
        )
        
        # 动态计算全连接层输入
        with torch.no_grad():
            dummy = torch.randn(1, 3, 120, 160)  # 注意H,W顺序
            features = self.cnn(dummy)
            in_features = features.shape[1]
            
        self.fc = nn.Sequential(
            nn.Linear(in_features, 100),
            nn.ReLU(),
            nn.Linear(100, 50),
            nn.ReLU(),
            nn.Linear(50, 1)
        )

    def forward(self, x):
        x = self.cnn(x)
        return self.fc(x)

# 训练配置
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model = AutoPilot().to(device)
criterion = nn.MSELoss()
optimizer = optim.Adam(model.parameters(), lr=0.001)

# 训练循环
for epoch in range(epochs):
    running_loss = 0.0
    for i, (inputs, labels) in enumerate(dataloader):
        inputs, labels = inputs.to(device), labels.to(device)
        
        optimizer.zero_grad()
        outputs = model(inputs)
        loss = criterion(outputs, labels)
        loss.backward()
        optimizer.step()
        
        running_loss += loss.item()
        if i % 10 == 9:
            print(f'Epoch {epoch+1}, Batch {i+1}: loss {running_loss/10:.4f}')
            running_loss = 0.0

# 保存模型
torch.save(model.state_dict(), "autopilot.pth")
