from PIL import Image, ImageDraw, ImageFont
import os

def create_icon():
    # 确保目录存在
    icon_dir = "src/ziyuan"
    if not os.path.exists(icon_dir):
        os.makedirs(icon_dir)
        
    # 创建一个 256x256 的图像
    size = 256
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # 绘制背景圆形
    margin = 20
    draw.ellipse([margin, margin, size-margin, size-margin], fill='#0A84FF')
    
    try:
        # 尝试加载系统字体
        font_path = "C:/Windows/Fonts/msyh.ttc"  # 微软雅黑
        if not os.path.exists(font_path):
            font_path = "C:/Windows/Fonts/simhei.ttf"  # 黑体
        font = ImageFont.truetype(font_path, 80)
    except Exception:
        # 如果无法加载系统字体，使用默认字体
        font = ImageFont.load_default()
    
    # 绘制文字
    text = "大佐"
    # 获取文字大小
    text_bbox = draw.textbbox((0, 0), text, font=font)
    text_width = text_bbox[2] - text_bbox[0]
    text_height = text_bbox[3] - text_bbox[1]
    
    # 计算文字位置使其居中
    x = (size - text_width) // 2
    y = (size - text_height) // 2
    
    # 绘制文字
    draw.text((x, y), text, fill='white', font=font)
    
    # 生成不同尺寸的图标
    sizes = [16, 32, 48, 64, 128, 256]
    icons = []
    for s in sizes:
        icon = img.resize((s, s), Image.Resampling.LANCZOS)
        icons.append(icon)
    
    # 保存为 ICO 文件
    icon_path = os.path.join(icon_dir, "logo.ico")
    icons[0].save(icon_path, format='ICO', sizes=[(s, s) for s in sizes], append_images=icons[1:])
    print(f"图标已保存到: {icon_path}")

if __name__ == "__main__":
    create_icon() 