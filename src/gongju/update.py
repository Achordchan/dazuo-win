import os
import sys
import json
import aiohttp
import asyncio
import logging
import tempfile
import subprocess
from PyQt5.QtCore import QObject, pyqtSignal
from src.version import APP_VERSION

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class Updater(QObject):
    # 定义信号
    update_available = pyqtSignal(str, str, bool)  # 版本号, 更新说明, 是否强制更新
    update_progress = pyqtSignal(int)  # 下载进度
    update_error = pyqtSignal(str)  # 错误信息
    update_complete = pyqtSignal(str)  # 下载完成的文件路径

    def __init__(self):
        super().__init__()
        self.current_version = APP_VERSION  # 当前版本号
        self.gitee_api = "https://gitee.com/api/v5/repos/Achordchan/dazuofanyiguan/releases/latest"
        self.update_url = None
        self.release_notes = None
        self.force_update = False
        self.asset_suffix = None

    async def check_update(self):
        """检查是否有新版本可用"""
        try:
            logger.info("开始检查更新...")
            async with aiohttp.ClientSession() as session:
                logger.info(f"正在请求 Gitee API: {self.gitee_api}")
                async with session.get(self.gitee_api) as response:
                    if response.status == 404:
                        logger.error("仓库不存在或无法访问")
                        self.update_error.emit(
                            "检查更新失败：Gitee 返回 404。可能是仓库地址错误、仓库被删除或被设为私有。"
                        )
                        return False
                    if response.status == 403:
                        logger.error("访问被拒绝或频率限制")
                        self.update_error.emit(
                            "检查更新失败：Gitee 返回 403。可能是访问被拒绝、触发频率限制或需要鉴权。"
                        )
                        return False
                    if response.status != 200:
                        logger.error(f"Gitee API 请求失败: HTTP {response.status}")
                        self.update_error.emit(
                            f"检查更新失败：Gitee 返回 HTTP {response.status}。"
                        )
                        return False
                    
                    data = await response.json()
                    tag_name = data.get('tag_name') or data.get('name') or ""
                    latest_version = tag_name.lstrip('v')
                    logger.info(f"获取到最新版本: {latest_version}, 当前版本: {self.current_version}")
                    
                    # 比较版本号
                    if self._compare_versions(latest_version, self.current_version) > 0:
                        logger.info(f"发现新版本: {latest_version}")
                        
                        # 获取更新信息
                        self.release_notes = data.get('body') or "暂无更新说明"
                        logger.info(f"更新说明: {self.release_notes}")
                        
                        # 检查是否强制更新
                        marker = "update=1"
                        self.force_update = marker in self.release_notes
                        # 移除强制更新标记
                        clean_notes = self.release_notes.replace(marker, "").strip()
                        logger.info(f"是否强制更新: {self.force_update}")
                        
                        # 获取下载链接
                        platform_suffixes = []
                        if sys.platform == "darwin":
                            platform_suffixes = [".dmg"]
                        elif sys.platform == "win32":
                            platform_suffixes = [".exe", ".msi"]
                        else:
                            self.update_error.emit("暂不支持该平台自动更新。")
                            return False

                        for asset in data.get('assets', []):
                            asset_name = (asset.get('name') or "").lower()
                            logger.info(f"检查资源: {asset_name}")
                            if any(asset_name.endswith(suffix) for suffix in platform_suffixes):
                                self.update_url = asset.get('browser_download_url')
                                self.asset_suffix = os.path.splitext(asset_name)[1]
                                if self.update_url:
                                    logger.info(f"找到更新包下载链接: {self.update_url}")
                                    break
                        
                        if self.update_url:
                            logger.info("发送更新可用信号")
                            self.update_available.emit(latest_version, clean_notes, self.force_update)
                            return True
                        suffix_text = "/".join(platform_suffixes)
                        self.update_error.emit(f"未找到安装包资源，请在 Gitee Release 中上传 {suffix_text} 文件")
                        return False
                    else:
                        logger.info("当前已是最新版本")
            
            return False
        except aiohttp.ClientError as e:
            logger.error(f"网络请求错误: {e}")
            self.update_error.emit(f"网络请求错误：{str(e)}。请检查网络/代理/证书设置。")
            return False
        except Exception as e:
            logger.error(f"检查更新出错: {e}")
            self.update_error.emit(f"检查更新失败: {str(e)}")
            return False

    async def download_update(self):
        """下载更新文件"""
        if not self.update_url:
            self.update_error.emit("没有可用的更新")
            return

        try:
            # 创建临时文件
            suffix = self.asset_suffix or (".dmg" if sys.platform == "darwin" else ".exe")
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
                temp_path = tmp_file.name

            async with aiohttp.ClientSession() as session:
                async with session.get(self.update_url) as response:
                    if response.status == 404:
                        self.update_error.emit("下载失败：安装包资源不存在（HTTP 404）。")
                        return
                    if response.status == 403:
                        self.update_error.emit("下载失败：下载被拒绝或频率限制（HTTP 403）。")
                        return
                    if response.status != 200:
                        self.update_error.emit(f"下载失败：HTTP {response.status}。")
                        return

                    # 获取文件大小
                    total_size = int(response.headers.get('content-length', 0))
                    
                    # 下载文件
                    with open(temp_path, 'wb') as f:
                        downloaded = 0
                        async for chunk in response.content.iter_chunked(8192):
                            f.write(chunk)
                            downloaded += len(chunk)
                            # 更新进度
                            if total_size:
                                progress = int((downloaded / total_size) * 100)
                                self.update_progress.emit(progress)

            logger.info(f"更新文件下载完成: {temp_path}")
            self.update_complete.emit(temp_path)
            
        except Exception as e:
            logger.error(f"下载更新出错: {e}")
            self.update_error.emit(f"下载更新失败：{str(e)}")
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def install_update(self, file_path):
        """安装更新"""
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", file_path])
                return

            # 使用subprocess启动安装程序
            subprocess.Popen([file_path], shell=True)
            # 退出当前程序
            sys.exit(0)
        except Exception as e:
            logger.error(f"安装更新出错: {e}")
            self.update_error.emit(f"安装更新失败: {str(e)}")

    def _compare_versions(self, version1, version2):
        """比较版本号，返回1表示version1更新，-1表示version2更新，0表示相同"""
        v1_parts = list(map(int, version1.split('.')))
        v2_parts = list(map(int, version2.split('.')))
        
        # 补齐版本长度
        while len(v1_parts) < 3:
            v1_parts.append(0)
        while len(v2_parts) < 3:
            v2_parts.append(0)
        
        for i in range(3):
            if v1_parts[i] > v2_parts[i]:
                return 1
            elif v1_parts[i] < v2_parts[i]:
                return -1
        return 0