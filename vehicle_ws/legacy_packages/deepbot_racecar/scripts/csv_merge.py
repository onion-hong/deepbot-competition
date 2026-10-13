import pandas as pd

def merge_csv_files(file1, file2, output_file='merged.csv'):
    """
    合并两个结构相同的CSV文件
    :param file1: 第一个CSV文件路径
    :param file2: 第二个CSV文件路径
    :param output_file: 合并后的输出路径
    """
    try:
        # 分块读取避免内存溢出
        reader1 = pd.read_csv(file1, chunksize=10000)
        reader2 = pd.read_csv(file2, chunksize=10000)
        
        # 初始化标记确保只保留一个表头
        header_flag = True
        
        with open(output_file, 'w', encoding='utf-8') as f:
            for chunk in reader1:
                chunk.to_csv(f, mode='a', index=False, header=header_flag)
                header_flag = False
            for chunk in reader2:
                chunk.to_csv(f, mode='a', index=False, header=False)
                
        print(f"成功合并文件到 {output_file}")
        
    except FileNotFoundError as e:
        print(f"文件不存在: {e}")
    except pd.errors.ParserError as e:
        print(f"CSV解析错误: {e}")
    except Exception as e:
        print(f"未知错误: {e}")

# 使用示例
merge_csv_files('/home/deepbot/Work/zhangaitrain_data/data.csv', '/home/deepbot/Work/zx02train_data/data.csv', '/home/deepbot/Work/train_data/data.csv')
