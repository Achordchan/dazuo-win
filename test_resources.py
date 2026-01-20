import os
import sys

def check_resources():
    # 获取程序所在目录
    if getattr(sys, 'frozen', False):
        base_dir = sys._MEIPASS
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 检查资源目录
    resource_dir = os.path.join(base_dir, 'src', 'ziyuan')
    print(f"Checking resource directory: {resource_dir}")
    
    if os.path.exists(resource_dir):
        print("Resource directory exists")
        # 列出所有文件
        for file in os.listdir(resource_dir):
            print(f"Found file: {file}")
    else:
        print("Resource directory not found!")

if __name__ == "__main__":
    check_resources() 