
import numpy as np
import pandas as pd
from time import time
from tqdm import tqdm
import matplotlib.pyplot as plt
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
from torchvision import transforms
from PIL import Image


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


def batch_validation(model, csv_path, img_dir, batch_size=64):
    """ 批量验证函数
    Args:
        model: 训练好的模型
        csv_path: 验证集CSV路径
        img_dir: 图像存储目录
        batch_size: 批处理大小
    """
    # 复用训练时的数据集类[4](@ref)
    class ValDataset(torch.utils.data.Dataset):
        def __init__(self):
            self.df = pd.read_csv(csv_path)
            self.transform = transforms.Compose([
                transforms.Resize((120, 160)),  # 保持原始尺寸
                transforms.ToTensor(),
                transforms.Normalize(mean=[0.485, 0.456, 0.406],  # ImageNet标准化
                                    std=[0.229, 0.224, 0.225])
            ])
            
        def __len__(self):
            return len(self.df)
        
        def __getitem__(self, idx):
            img_path = self.df.iloc[idx, 0]
            steering = self.df.iloc[idx, 1]
            img = Image.open(img_path).convert('RGB')
            return self.transform(img), torch.tensor(steering, dtype=torch.float32)
    
    # 初始化组件
    dataset = ValDataset()
    loader = torch.utils.data.DataLoader(dataset, batch_size=batch_size, shuffle=False)
    model.eval()  # 切换评估模式[5](@ref)
    
    # 指标容器
    total_mse = 0.0
    total_mae = 0.0
    predictions = []
    ground_truth = []
    batch_times = []
    
    # 验证循环
    with torch.no_grad():
        print("\n[验证开始] 数据集样本数: {} | 批次大小: {}".format(len(dataset), batch_size))
        for i, (inputs, targets) in enumerate(tqdm(loader, desc="处理进度")):
            start_time = time()
            
            # 前向传播
            outputs = model(inputs).squeeze()
            
            # 计算指标
            mse = torch.nn.functional.mse_loss(outputs, targets)
            mae = torch.nn.functional.l1_loss(outputs, targets)
            
            # 记录数据
            total_mse += mse.item() * inputs.size(0)
            total_mae += mae.item() * inputs.size(0)
            predictions.extend(outputs.cpu().numpy())
            ground_truth.extend(targets.cpu().numpy())
            batch_time = time() - start_time
            batch_times.append(batch_time)
            
            # 批次日志[7](@ref)
            print(
                "\n[批次 {}]".format(i+1),
                "MSE: {:.4f}".format(mse.item()),
                "MAE: {:.4f}".format(mae.item()),
                "耗时: {:.2f}s".format(batch_time),
                "平均推理速度: {:.1f} 样本/秒".format(inputs.size(0)/batch_time)
            )
    
    # 最终统计
    avg_mse = total_mse / len(dataset)
    avg_mae = total_mae / len(dataset)
    avg_speed = len(dataset)/sum(batch_times)
    
    print("\n[验证完成]")
    print("="*40)
    print("总样本数: {}".format(len(dataset)))
    print("平均MSE: {:.4f}".format(avg_mse))
    print("平均MAE: {:.4f}".format(avg_mae))
    print("平均推理速度: {:.1f} 样本/秒".format(avg_speed))
    print("最大批次耗时: {:.2f}s".format(max(batch_times)))
    print("最小批次耗时: {:.2f}s".format(min(batch_times)))
    print("="*40)
    
    # 可视化分析[3](@ref)
    plt.figure(figsize=(12,5))
    
    # 散点图
    plt.subplot(1,2,1)
    plt.scatter(ground_truth, predictions, alpha=0.3)
    plt.plot([-1,1], [-1,1], 'r--', linewidth=2)
    plt.xlabel("真实转向值")
    plt.ylabel("预测转向值")
    plt.title("预测值 vs 真实值 (MAE={:.4f})".format(avg_mae))
    plt.grid(True)
    
    # 误差分布
    plt.subplot(1,2,2)
    errors = np.array(predictions) - np.array(ground_truth)
    plt.hist(errors, bins=50, density=True, alpha=0.7)
    plt.xlabel("预测误差")
    plt.ylabel("频率密度")
    plt.title("误差分布 (标准差={:.4f})".format(np.std(errors)))
    plt.grid(True)
    
    plt.tight_layout()
    plt.savefig("validation_analysis.png")
    print("\n可视化分析图已保存至 validation_analysis.png")

# 使用示例
if __name__ == "__main__":
    model = AutoPilot()  # 您的模型类
    model.load_state_dict(torch.load("autopilot.pth"))
    batch_validation(
        model, 
        csv_path="/home/deepbot/Work/train_data/data.csv",
        img_dir="dataset/images"
    )