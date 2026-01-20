import ctypes
import sys
import os

def run_as_admin():
    try:
        if ctypes.windll.shell32.IsUserAnAdmin():
            # 已经是管理员权限，直接运行程序
            os.system('python src/main.py')
        else:
            # 请求管理员权限
            ctypes.windll.shell32.ShellExecuteW(
                None, 
                "runas", 
                sys.executable, 
                "src/main.py", 
                None, 
                1
            )
    except Exception as e:
        print(f"启动失败: {e}")
        input("按回车键退出...")

if __name__ == "__main__":
    run_as_admin() 