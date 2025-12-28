import customtkinter
import tkinter as tk
from PIL import Image, ImageTk
import os
import sys
import json
import subprocess
import webbrowser
import hashlib
import uuid
from filelock import FileLock  # 导入文件锁库，解决并发写入问题
from typing import Optional, List

# 全局配置：解决中文路径和权限问题
APP_NAME = "Any Launcher"
# 优先使用用户AppData目录（可写），避免系统目录权限问题
USER_CONFIG_DIR = os.path.join(os.getenv("APPDATA", os.path.dirname(__file__)), APP_NAME)
os.makedirs(USER_CONFIG_DIR, exist_ok=True)  # 确保目录存在
LOCK_FILE_PATH = os.path.join(USER_CONFIG_DIR, "games.lock")  # 文件锁路径
GAMES_JSON_DEFAULT = os.path.join(USER_CONFIG_DIR, "games.json")

customtkinter.set_appearance_mode("dark")
ICON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.ico")
# 存储游戏子进程，用于主窗口关闭时清理
GAME_PROCESSES: List[subprocess.Popen] = []


def get_games_data_file() -> str:
    """
    获取游戏数据文件路径（修复权限问题）
    优先：用户AppData目录（确保可写）
    兼容：打包后exe目录（仅当可写时使用）
    """
    # 先尝试exe目录（兼容旧版本用户数据）
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        exe_json_path = os.path.join(exe_dir, "games.json")
        # 检查exe目录是否可写
        if os.access(exe_dir, os.W_OK):
            return exe_json_path
    # 不可写则使用AppData目录
    return GAMES_JSON_DEFAULT


def get_file_md5(file_path: str) -> Optional[str]:
    """计算文件MD5值（用于游戏文件完整性校验）"""
    if not os.path.exists(file_path):
        return None
    try:
        with open(file_path, "rb") as f:
            md5_obj = hashlib.md5()
            while chunk := f.read(4096):
                md5_obj.update(chunk)
        return md5_obj.hexdigest()
    except Exception:
        return None


def import_game():
    game_path = tk.filedialog.askopenfilename(
        title="选择游戏可执行文件",
        filetypes=[("可执行文件", "*.exe"), ("HTML文件", "*.html"), ("所有文件", "*.*")]
    )
    if not game_path:
        return
    # 处理中文路径：确保路径编码正确
    game_path = os.path.abspath(game_path)
    if not os.path.exists(game_path):
        tk.messagebox.showerror("错误", f"文件不存在：{game_path}")
        return

    # 提取默认名称（去除扩展名）
    default_name = os.path.splitext(os.path.basename(game_path))[0]
    # 计算MD5（可选校验）
    game_md5 = get_file_md5(game_path)
    # 打开编辑窗口（传入MD5）
    EditGameWindow(default_name, game_path, game_md5, get_games_data_file())


def start_game(game_path: str, game_md5: Optional[str] = None) -> int:
    """
    启动游戏（修复中文路径、添加MD5校验、跟踪子进程）
    :return: 1=成功, -1=启动失败, -2=文件不存在, -3=文件完整性校验失败
    """
    # 处理中文路径
    game_path = os.path.abspath(game_path)
    file_extension = os.path.splitext(game_path)[1].lower()

    # 1. 检查文件是否存在
    if not os.path.exists(game_path):
        tk.messagebox.showerror("错误", f"游戏文件不存在：{game_path}")
        return -2

    # 2. MD5完整性校验（若有）
    if game_md5:
        current_md5 = get_file_md5(game_path)
        if current_md5 != game_md5:
            tk.messagebox.showerror("错误", "游戏文件已被修改或损坏（MD5校验失败），请重新导入！")
            return -3

    # 3. 启动游戏（区分文件类型）
    try:
        if file_extension == ".html":
            webbrowser.open_new_tab(f"file:///{game_path}")  # 修复HTML中文路径
            return 1
        else:
            # 处理exe中文路径和工作目录
            game_dir = os.path.dirname(game_path)
            # 启动并跟踪子进程
            proc = subprocess.Popen(
                [game_path],
                cwd=game_dir,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP  # 便于后续关闭
            )
            GAME_PROCESSES.append(proc)
            return 1
    except PermissionError:
        tk.messagebox.showerror("错误", f"权限不足：无法执行 {game_path}\n请以管理员身份运行启动器！")
        return -1
    except FileNotFoundError:
        tk.messagebox.showerror("错误", f"找不到游戏文件：{game_path}\n可能是路径包含特殊字符或文件已删除！")
        return -1
    except Exception as e:
        tk.messagebox.showerror("错误", f"启动失败：{str(e)}\n建议检查文件完整性和系统环境！")
        return -1


def get_last_selected_game() -> Optional[dict]:
    """
    获取上次选中游戏（修复JSON字段缺失）
    返回：包含path、md5的字典，无则返回None
    """
    games_data_file = get_games_data_file()
    if not os.path.exists(games_data_file):
        return None

    # 加锁读取，防止并发冲突
    with FileLock(LOCK_FILE_PATH, timeout=5):
        try:
            with open(games_data_file, 'r', encoding='utf-8') as f:
                games = json.load(f)
            # 处理字段缺失：用get方法设默认值
            for game in games:
                if game.get("is_last_selected", False):
                    return {
                        "path": game.get("path", ""),
                        "md5": game.get("md5", None)
                    }
        except json.JSONDecodeError:
            tk.messagebox.showerror("错误", "游戏配置文件损坏，请删除games.json后重新导入！")
        except Exception as e:
            tk.messagebox.showerror("错误", f"读取游戏配置失败：{str(e)}")
    return None


class EditGameWindow(customtkinter.CTkToplevel):
    def __init__(self, default_name: str, game_path: str, game_md5: Optional[str], games_data_file: str):
        super().__init__()
        self.default_name = default_name
        self.game_path = game_path
        self.game_md5 = game_md5
        self.games_data_file = games_data_file

        # 窗口基础设置
        self.title("输入游戏名称")
        self.geometry("400x220")
        self.minsize(400, 220)
        self.resizable(False, False)
        self.transient(self.master)
        self.grab_set()

        # 主框架
        self.main_frame = customtkinter.CTkFrame(self)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 名称输入区
        self.label = customtkinter.CTkLabel(
            self.main_frame,
            text="请为游戏输入名称:",
            font=("Microsoft YaHei UI", 12)
        )
        self.label.pack(pady=(10, 10))

        self.input_frame = customtkinter.CTkFrame(self.main_frame, fg_color="transparent")
        self.input_frame.pack(fill=tk.X, padx=20, pady=(0, 10))

        self.name_label = customtkinter.CTkLabel(self.input_frame, text="名称:", font=("Microsoft YaHei UI", 12))
        self.name_label.pack(side=tk.LEFT, padx=(0, 10))

        self.name_entry = customtkinter.CTkEntry(self.input_frame, font=("Microsoft YaHei UI", 12), width=200)
        self.name_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.name_entry.insert(0, default_name)
        self.name_entry.focus_set()

        # MD5提示（可选显示）
        if self.game_md5:
            self.md5_label = customtkinter.CTkLabel(
                self.main_frame,
                text=f"文件MD5: {self.game_md5[:8]}...",  # 显示前8位，避免过长
                font=("Microsoft YaHei UI", 10),
                text_color="#888888"
            )
            self.md5_label.pack(pady=(0, 10))

        # 按钮区
        self.button_frame = customtkinter.CTkFrame(self.main_frame, fg_color="transparent")
        self.button_frame.pack(fill=tk.X, padx=20, pady=(10, 0))

        self.import_button = customtkinter.CTkButton(
            self.button_frame,
            text="确定",
            command=self.import_with_new_name,
            font=("Microsoft YaHei UI", 12)
        )
        self.import_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        self.cancel_button = customtkinter.CTkButton(
            self.button_frame,
            text="取消",
            command=self.destroy,
            font=("Microsoft YaHei UI", 12)
        )
        self.cancel_button.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(5, 0))

    def import_with_new_name(self):
        new_name = self.name_entry.get().strip()
        if not new_name:
            tk.messagebox.showerror("错误", "游戏名称不能为空！")
            return

        # 加锁读写，防止并发冲突
        with FileLock(LOCK_FILE_PATH, timeout=5):
            # 读取现有游戏（处理配置文件不存在/损坏）
            games = []
            if os.path.exists(self.games_data_file):
                try:
                    with open(self.games_data_file, 'r', encoding='utf-8') as f:
                        games = json.load(f)
                except json.JSONDecodeError:
                    if tk.messagebox.askyesno("警告", "配置文件损坏，是否清空重新创建？"):
                        games = []
                    else:
                        self.destroy()
                        return
                except Exception as e:
                    tk.messagebox.showerror("错误", f"读取配置失败：{str(e)}")
                    self.destroy()
                    return

            # 检查名称唯一性（基于ID，允许名称重复但提示）
            name_exists = any(game.get("name") == new_name for game in games)
            if name_exists:
                if not tk.messagebox.askyesno("提示", f"名称「{new_name}」已存在，是否继续？"):
                    return

            # 添加新游戏（带唯一ID，解决名称重复问题）
            new_game = {
                "id": str(uuid.uuid4()),  # 唯一ID，用于后续操作
                "name": new_name,
                "path": self.game_path,
                "md5": self.game_md5,
                "is_last_selected": False
            }
            games.append(new_game)

            # 写入配置
            try:
                with open(self.games_data_file, 'w', encoding='utf-8') as f:
                    json.dump(games, f, ensure_ascii=False, indent=4)
            except PermissionError:
                tk.messagebox.showerror("错误", "无写入权限，请以管理员身份运行启动器！")
                return
            except Exception as e:
                tk.messagebox.showerror("错误", f"保存配置失败：{str(e)}")
                return

        # 更新列表
        if hasattr(Select, 'instance') and Select.instance:
            Select.instance.load_games()
        if hasattr(self.master, 'select_window') and self.master.select_window:
            self.master.select_window.load_games()

        tk.messagebox.showinfo("成功", f"游戏「{new_name}」导入成功！")
        self.destroy()


class GameSettingsWindow(customtkinter.CTkToplevel):
    def __init__(self, parent, game_id: str, game_data: dict, games_data_file: str):
        super().__init__()
        self.parent = parent
        self.game_id = game_id  # 基于ID操作，解决名称重复
        self.original_data = game_data
        self.games_data_file = games_data_file
        self.main_window = self._get_main_window(parent)

        # 窗口设置
        self.title(f"设置游戏：{self.original_data.get('name', '未知')}")
        self.geometry("500x300")
        self.minsize(500, 300)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        # 主框架
        self.main_frame = customtkinter.CTkFrame(self)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 名称设置
        self.name_frame = customtkinter.CTkFrame(self.main_frame, fg_color="transparent")
        self.name_frame.pack(fill=tk.X, padx=20, pady=(10, 5))
        self.name_label = customtkinter.CTkLabel(self.name_frame, text="游戏名称:", font=("Microsoft YaHei UI", 12))
        self.name_label.pack(side=tk.LEFT, padx=(0, 10))
        self.name_entry = customtkinter.CTkEntry(
            self.name_frame,
            font=("Microsoft YaHei UI", 12),
            width=250
        )
        self.name_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.name_entry.insert(0, self.original_data.get("name", ""))

        # 路径设置
        self.path_frame = customtkinter.CTkFrame(self.main_frame, fg_color="transparent")
        self.path_frame.pack(fill=tk.X, padx=20, pady=(5, 5))
        self.path_label = customtkinter.CTkLabel(self.path_frame, text="游戏路径:", font=("Microsoft YaHei UI", 12))
        self.path_label.pack(side=tk.LEFT, padx=(0, 10))
        self.path_entry = customtkinter.CTkEntry(
            self.path_frame,
            font=("Microsoft YaHei UI", 12),
            width=250
        )
        self.path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.path_entry.insert(0, self.original_data.get("path", ""))
        self.browse_button = customtkinter.CTkButton(
            self.path_frame,
            text="浏览...",
            command=self.browse_path,
            font=("Microsoft YaHei UI", 10),
            width=80
        )
        self.browse_button.pack(side=tk.RIGHT, padx=(10, 0))

        # MD5校验设置
        self.md5_frame = customtkinter.CTkFrame(self.main_frame, fg_color="transparent")
        self.md5_frame.pack(fill=tk.X, padx=20, pady=(5, 10))
        self.md5_label = customtkinter.CTkLabel(
            self.md5_frame,
            text="文件MD5（自动生成）:",
            font=("Microsoft YaHei UI", 12)
        )
        self.md5_label.pack(side=tk.LEFT, padx=(0, 10))
        self.md5_entry = customtkinter.CTkEntry(
            self.md5_frame,
            font=("Microsoft YaHei UI", 10),
            text_color="#888888",
            state="readonly"
        )
        self.md5_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.update_md5_display()  # 初始显示MD5

        # 按钮区
        self.button_frame = customtkinter.CTkFrame(self.main_frame, fg_color="transparent")
        self.button_frame.pack(fill=tk.X, padx=20, pady=(20, 10))
        self.save_button = customtkinter.CTkButton(
            self.button_frame,
            text="保存",
            command=self.save_settings,
            font=("Microsoft YaHei UI", 12)
        )
        self.save_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.cancel_button = customtkinter.CTkButton(
            self.button_frame,
            text="取消",
            command=self.destroy,
            font=("Microsoft YaHei UI", 12)
        )
        self.cancel_button.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(5, 0))

    def _get_main_window(self, parent) -> Optional[tk.Tk]:
        """获取主窗口引用（修复层级问题）"""
        if isinstance(parent, AdaptiveApp):
            return parent
        elif hasattr(parent, 'parent') and isinstance(parent.parent, AdaptiveApp):
            return parent.parent
        return None

    def browse_path(self):
        """浏览游戏路径（处理中文路径）"""
        current_path = self.path_entry.get().strip()
        initial_dir = os.path.dirname(current_path) if current_path else os.path.expanduser("~")
        filetypes = [("可执行文件", "*.exe"), ("HTML文件", "*.html"), ("所有文件", "*.*")]
        
        filename = tk.filedialog.askopenfilename(
            title="选择游戏文件",
            filetypes=filetypes,
            initialdir=initial_dir
        )
        if filename:
            self.path_entry.delete(0, tk.END)
            self.path_entry.insert(0, os.path.abspath(filename))
            self.update_md5_display()  # 路径变化时更新MD5

    def update_md5_display(self):
        """更新MD5显示"""
        game_path = self.path_entry.get().strip()
        if not game_path or not os.path.exists(game_path):
            self.md5_entry.configure(state="normal")
            self.md5_entry.delete(0, tk.END)
            self.md5_entry.insert(0, "文件不存在或路径为空")
            self.md5_entry.configure(state="readonly")
            return
        
        md5 = get_file_md5(game_path)
        self.md5_entry.configure(state="normal")
        self.md5_entry.delete(0, tk.END)
        self.md5_entry.insert(0, md5[:16] + "..." if md5 else "计算失败")  # 显示前16位
        self.md5_entry.configure(state="readonly")

    def save_settings(self):
        new_name = self.name_entry.get().strip()
        new_path = self.path_entry.get().strip()
        new_md5 = get_file_md5(new_path) if new_path else None

        # 基础校验
        if not new_name:
            tk.messagebox.showerror("错误", "游戏名称不能为空！")
            return
        if not new_path:
            tk.messagebox.showerror("错误", "游戏路径不能为空！")
            return
        if not os.path.exists(new_path):
            tk.messagebox.showerror("错误", f"文件不存在：{new_path}")
            return

        # 加锁修改
        with FileLock(LOCK_FILE_PATH, timeout=5):
            games = []
            if os.path.exists(self.games_data_file):
                try:
                    with open(self.games_data_file, 'r', encoding='utf-8') as f:
                        games = json.load(f)
                except json.JSONDecodeError:
                    tk.messagebox.showerror("错误", "配置文件损坏，无法修改！")
                    return
                except Exception as e:
                    tk.messagebox.showerror("错误", f"读取配置失败：{str(e)}")
                    return

            # 找到对应游戏（基于ID）
            game_updated = False
            for i, game in enumerate(games):
                if game.get("id") == self.game_id:
                    # 检查名称重复（提示但允许）
                    name_exists = any(
                        g.get("name") == new_name and g.get("id") != self.game_id 
                        for g in games
                    )
                    if name_exists and not tk.messagebox.askyesno("提示", f"名称「{new_name}」已存在，是否继续？"):
                        return
                    
                    # 更新游戏数据
                    games[i]["name"] = new_name
                    games[i]["path"] = new_path
                    games[i]["md5"] = new_md5
                    game_updated = True
                    break

            if not game_updated:
                tk.messagebox.showerror("错误", "未找到要修改的游戏！")
                return

            # 保存配置
            try:
                with open(self.games_data_file, 'w', encoding='utf-8') as f:
                    json.dump(games, f, ensure_ascii=False, indent=4)
            except PermissionError:
                tk.messagebox.showerror("错误", "无写入权限，请以管理员身份运行！")
                return
            except Exception as e:
                tk.messagebox.showerror("错误", f"保存配置失败：{str(e)}")
                return

        # 更新UI
        if hasattr(Select, 'instance') and Select.instance:
            Select.instance.load_games()
        if self.main_window and self.main_window.selected_game_label:
            current_name = self.main_window.selected_game_label.cget("text")
            if current_name == self.original_data.get("name"):
                self.main_window.selected_game_label.configure(text=new_name)

        tk.messagebox.showinfo("成功", "游戏设置已保存！")
        self.destroy()


class Select(customtkinter.CTkToplevel):
    instance: Optional["Select"] = None  # 单例引用，便于更新列表

    def __init__(self, parent):
        super().__init__(parent)
        Select.instance = self  # 记录单例
        self.parent = parent
        self.games_data_file = get_games_data_file()
        self.current_games: List[dict] = []  # 存储当前游戏数据（含ID）

        # 窗口设置
        self.title("选择游戏")
        self.geometry("600x400")
        self.minsize(600, 400)
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.grab_set()

        # 顶部按钮区
        self.top_button_frame = customtkinter.CTkFrame(self, fg_color="transparent")
        self.top_button_frame.pack(side=tk.TOP, fill=tk.X, pady=(0, 10))
        self.import_button = customtkinter.CTkButton(
            self.top_button_frame,
            text="导入游戏",
            font=("Microsoft YaHei UI", 14),
            command=import_game,
            height=40
        )
        self.import_button.pack(side=tk.LEFT, padx=(5, 10), pady=5)
        self.refresh_button = customtkinter.CTkButton(
            self.top_button_frame,
            text="刷新列表",
            font=("Microsoft YaHei UI", 14),
            height=40,
            command=self.load_games
        )
        self.refresh_button.pack(side=tk.RIGHT, padx=(10, 5), pady=5)

        # 游戏列表区
        self.list_frame = customtkinter.CTkFrame(self)
        self.list_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(0, 10))
        self.game_listbox = tk.Listbox(
            self.list_frame,
            bg="#2b2b2b",
            fg="white",
            selectbackground="#1f538d",
            selectforeground="white",
            font=("Microsoft YaHei UI", 16),
            relief=tk.FLAT,
            bd=0,
            activestyle="none"
        )
        self.game_listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.game_listbox.bind("<Double-1>", self.on_double_click)

        # 底部按钮区
        self.bottom_button_frame = customtkinter.CTkFrame(self, fg_color="transparent")
        self.bottom_button_frame.pack(side=tk.BOTTOM, fill=tk.X)
        self.settings_button = customtkinter.CTkButton(
            self.bottom_button_frame,
            text="游戏设置",
            command=self.open_game_settings,
            font=("Microsoft YaHei UI", 12),
            width=100,
            height=35
        )
        self.settings_button.pack(side=tk.LEFT, padx=(10, 5), pady=5)
        self.delete_button = customtkinter.CTkButton(
            self.bottom_button_frame,
            text="删除游戏",
            command=self.delete_game,
            font=("Microsoft YaHei UI", 12),
            width=100,
            height=35
        )
        self.delete_button.pack(side=tk.LEFT, padx=(5, 5), pady=5)
        self.save_button = customtkinter.CTkButton(
            self.bottom_button_frame,
            text="选择并关闭",
            command=self.save_and_close,
            font=("Microsoft YaHei UI", 12),
            width=150,
            height=35
        )
        self.save_button.pack(side=tk.RIGHT, padx=(5, 10), pady=5)

        # 初始加载
        self.load_games()

    def load_games(self):
        """加载游戏列表（修复JSON字段缺失、重复错误提示）"""
        self.game_listbox.delete(0, tk.END)
        self.current_games.clear()

        if not os.path.exists(self.games_data_file):
            self.current_games = []
            return

        # 加锁读取
        with FileLock(LOCK_FILE_PATH, timeout=5):
            try:
                with open(self.games_data_file, 'r', encoding='utf-8') as f:
                    games = json.load(f)
                # 处理字段缺失：补全默认值
                for game in games:
                    self.current_games.append({
                        "id": game.get("id", str(uuid.uuid4())),  # 无ID则自动生成
                        "name": game.get("name", "未知游戏"),
                        "path": game.get("path", ""),
                        "md5": game.get("md5", None),
                        "is_last_selected": game.get("is_last_selected", False)
                    })
                # 排序：上次选中的排在前面
                self.current_games.sort(key=lambda x: not x["is_last_selected"])
                # 填充列表
                for game in self.current_games:
                    self.game_listbox.insert(tk.END, game["name"])
            except json.JSONDecodeError:
                tk.messagebox.showerror("错误", "配置文件损坏，请删除games.json后重新导入！")
            except Exception as e:
                tk.messagebox.showerror("错误", f"加载游戏列表失败：{str(e)}")

    def on_double_click(self, event):
        """双击选择游戏"""
        self.save_and_close()

    def save_and_close(self):
        """保存选中游戏（基于ID，修复名称重复问题）"""
        selected_indices = self.game_listbox.curselection()
        if not selected_indices:
            tk.messagebox.showinfo("提示", "请先选择一个游戏！")
            return

        selected_idx = selected_indices[0]
        if selected_idx >= len(self.current_games):
            tk.messagebox.showerror("错误", "选中的游戏不存在！")
            return

        selected_game = self.current_games[selected_idx]
        selected_game_id = selected_game["id"]

        # 加锁更新选中状态
        with FileLock(LOCK_FILE_PATH, timeout=5):
            games = []
            if os.path.exists(self.games_data_file):
                try:
                    with open(self.games_data_file, 'r', encoding='utf-8') as f:
                        games = json.load(f)
                except Exception as e:
                    tk.messagebox.showerror("错误", f"读取配置失败：{str(e)}")
                    return

            # 更新选中状态（基于ID）
            for game in games:
                game["is_last_selected"] = (game.get("id") == selected_game_id)

            # 保存配置
            try:
                with open(self.games_data_file, 'w', encoding='utf-8') as f:
                    json.dump(games, f, ensure_ascii=False, indent=4)
            except PermissionError:
                tk.messagebox.showerror("错误", "无写入权限，请以管理员身份运行！")
                return
            except Exception as e:
                tk.messagebox.showerror("错误", f"保存配置失败：{str(e)}")
                return

        # 更新主窗口标签
        self.parent.update_selected_game_label(selected_game["name"])
        self.on_close()

    def open_game_settings(self):
        """打开游戏设置（基于ID）"""
        selected_indices = self.game_listbox.curselection()
        if not selected_indices:
            tk.messagebox.showinfo("提示", "请先选择一个游戏！")
            return

        selected_idx = selected_indices[0]
        if selected_idx >= len(self.current_games):
            tk.messagebox.showerror("错误", "选中的游戏不存在！")
            return

        selected_game = self.current_games[selected_idx]
        GameSettingsWindow(
            parent=self,
            game_id=selected_game["id"],
            game_data=selected_game,
            games_data_file=self.games_data_file
        )

    def delete_game(self):
        """删除游戏（基于ID，修复名称重复删除问题）"""
        selected_indices = self.game_listbox.curselection()
        if not selected_indices:
            tk.messagebox.showinfo("提示", "请先选择一个游戏！")
            return

        selected_idx = selected_indices[0]
        if selected_idx >= len(self.current_games):
            tk.messagebox.showerror("错误", "选中的游戏不存在！")
            return

        selected_game = self.current_games[selected_idx]
        if not tk.messagebox.askyesno("确认删除", f"确定要删除游戏「{selected_game['name']}」吗？"):
            return

        # 加锁删除
        with FileLock(LOCK_FILE_PATH, timeout=5):
            games = []
            if os.path.exists(self.games_data_file):
                try:
                    with open(self.games_data_file, 'r', encoding='utf-8') as f:
                        games = json.load(f)
                except Exception as e:
                    tk.messagebox.showerror("错误", f"读取配置失败：{str(e)}")
                    return

            # 基于ID删除（仅删除选中的游戏）
            original_count = len(games)
            games = [game for game in games if game.get("id") != selected_game["id"]]
            if len(games) == original_count:
                tk.messagebox.showerror("错误", "未找到要删除的游戏！")
                return

            # 保存配置
            try:
                with open(self.games_data_file, 'w', encoding='utf-8') as f:
                    json.dump(games, f, ensure_ascii=False, indent=4)
            except PermissionError:
                tk.messagebox.showerror("错误", "无写入权限，请以管理员身份运行！")
                return
            except Exception as e:
                tk.messagebox.showerror("错误", f"保存配置失败：{str(e)}")
                return

        # 更新UI
        self.load_games()
        # 若删除的是当前选中游戏，更新主窗口标签
        current_label = self.parent.selected_game_label.cget("text")
        if current_label == selected_game["name"]:
            self.parent.selected_game_label.configure(text="未选择游戏")

        tk.messagebox.showinfo("成功", f"游戏「{selected_game['name']}」已删除！")

    def on_close(self):
        """关闭窗口（清理单例）"""
        self.parent.select_window = None
        Select.instance = None
        self.destroy()


class AdaptiveApp(customtkinter.CTk):
    def __init__(self):
        super().__init__()
        self.title("Any Launcher")
        self.geometry("750x370")
        self.resizable(width=False, height=False)
        self.select_window: Optional[Select] = None

        # 图标设置（处理图标不存在的情况）
        try:
            self.iconbitmap(ICON_PATH)
        except Exception:
            pass  # 忽略图标不存在的错误

        # 主框架
        self.main_frame = customtkinter.CTkFrame(self)
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        # Logo显示（修复中文路径和图片不存在问题）
        self.load_logo()

        # 右下角信息区
        self.bottom_right_frame = customtkinter.CTkFrame(self.main_frame, fg_color="transparent")
        self.bottom_right_frame.pack(side=tk.BOTTOM, anchor=tk.SE, padx=10, pady=10)

        # 选中游戏标签（移除冗余replace）
        self.selected_game_label = customtkinter.CTkLabel(
            self.bottom_right_frame,
            text="未选择游戏",
            font=("Microsoft YaHei UI", 15),
            fg_color="transparent"
        )
        self.selected_game_label.pack(side=tk.TOP, anchor=tk.E, padx=5, pady=(0, 5))

        # 功能按钮区
        self.button_frame = customtkinter.CTkFrame(self.bottom_right_frame, fg_color="transparent")
        self.button_frame.pack(side=tk.BOTTOM, anchor=tk.SE)
        self.button_frame.grid_columnconfigure((0, 1), weight=1, uniform="btn_col")
        self.button_frame.grid_rowconfigure((0, 1), weight=1)

        self.button_select = customtkinter.CTkButton(
            self.button_frame,
            text="选择游戏",
            command=self.open_select_window,
            font=("Microsoft YaHei UI", 12),
            width=100,
            height=40
        )
        self.button_select.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")

        self.button_setting = customtkinter.CTkButton(
            self.button_frame,
            text="游戏设置",
            command=self.open_game_settings,
            font=("Microsoft YaHei UI", 12),
            width=100,
            height=40
        )
        self.button_setting.grid(row=0, column=1, padx=5, pady=5, sticky="nsew")

        self.button_start = customtkinter.CTkButton(
            self.button_frame,
            text="启动游戏",
            command=self.start_selected_game,
            font=("Microsoft YaHei UI", 12),
            width=210,
            height=40
        )
        self.button_start.grid(row=1, column=0, columnspan=2, padx=5, pady=5, sticky="nsew")

        # 初始化加载上次选中游戏
        self.load_last_selected_game()
        # 绑定关闭事件（清理子进程）
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def load_logo(self):
        """加载Logo（修复中文路径和图片不存在问题）"""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        image_path = os.path.join(script_dir, "logo.png")
        image_path = os.path.abspath(image_path)  # 处理中文路径

        try:
            if os.path.exists(image_path):
                self.image = Image.open(image_path)
            else:
                # 图片不存在时显示默认红色背景
                self.image = Image.new("RGB", (400, 200), color="#333333")
                # 添加文字提示
                from PIL import ImageDraw, ImageFont
                draw = ImageDraw.Draw(self.image)
                font = ImageFont.truetype("simhei.ttf", 20) if os.path.exists("simhei.ttf") else None
                if font:
                    draw.text((50, 80), "Logo图片缺失", fill="white", font=font)
                    draw.text((50, 110), f"路径：{image_path}", fill="#888888", font=ImageFont.truetype("simhei.ttf", 12))
        except Exception as e:
            # 图片损坏时显示错误
            self.image = Image.new("RGB", (400, 200), color="#442222")
            from PIL import ImageDraw, ImageFont
            draw = ImageDraw.Draw(self.image)
            font = ImageFont.truetype("simhei.ttf", 20) if os.path.exists("simhei.ttf") else None
            if font:
                draw.text((50, 80), "Logo加载失败", fill="white", font=font)
                draw.text((50, 110), str(e), fill="#888888", font=ImageFont.truetype("simhei.ttf", 12))

        # 调整图片大小
        self.update_image_size()
        self.photo_image = ImageTk.PhotoImage(self.image)
        self.image_label = customtkinter.CTkLabel(
            self.main_frame,
            image=self.photo_image,
            text="",
            fg_color="transparent"
        )
        self.image_label.pack(side=tk.TOP, anchor=tk.N, pady=10)

    def update_image_size(self):
        """调整Logo大小以适应窗口"""
        max_width = int(self.winfo_width() * 0.8)
        max_height = int(self.winfo_height() * 0.6)
        original_width, original_height = self.image.size

        # 计算缩放比例
        scale = min(max_width / original_width, max_height / original_height, 1.0)
        new_width = int(original_width * scale)
        new_height = int(original_height * scale)

        if new_width != original_width or new_height != original_height:
            self.image = self.image.resize((new_width, new_height), Image.LANCZOS)

    def open_select_window(self):
        """打开游戏选择窗口（单例，避免多窗口）"""
        if self.select_window and self.select_window.winfo_exists():
            self.select_window.lift()
            self.select_window.focus()
            return
        self.select_window = Select(self)
        self.select_window.lift()

    def open_game_settings(self):
        """打开当前选中游戏的设置（基于名称匹配ID）"""
        current_name = self.selected_game_label.cget("text")
        if current_name in ["未选择游戏", "UNKNOWN"]:
            tk.messagebox.showinfo("提示", "请先选择一个游戏！")
            return

        games_data_file = get_games_data_file()
        if not os.path.exists(games_data_file):
            tk.messagebox.showerror("错误", "配置文件不存在，无游戏可设置！")
            return

        # 查找当前游戏的ID和数据
        with FileLock(LOCK_FILE_PATH, timeout=5):
            try:
                with open(games_data_file, 'r', encoding='utf-8') as f:
                    games = json.load(f)
                # 匹配名称（优先上次选中的）
                target_game = None
                for game in games:
                    if game.get("name") == current_name:
                        if game.get("is_last_selected", False):
                            target_game = game
                            break
                        target_game = target_game or game
                if not target_game:
                    tk.messagebox.showerror("错误", f"未找到游戏「{current_name}」！")
                    return

                # 打开设置窗口
                GameSettingsWindow(
                    parent=self,
                    game_id=target_game.get("id", str(uuid.uuid4())),
                    game_data=target_game,
                    games_data_file=games_data_file
                )
            except Exception as e:
                tk.messagebox.showerror("错误", f"读取配置失败：{str(e)}")

    def start_selected_game(self):
        """启动当前选中游戏"""
        last_game = get_last_selected_game()
        if not last_game or not last_game["path"]:
            tk.messagebox.showinfo("提示", "请先选择一个游戏！")
            return

        # 启动游戏并处理结果
        result = start_game(last_game["path"], last_game["md5"])
        if result == 1:
            # 启动成功可选项：最小化主窗口
            if tk.messagebox.askyesno("成功", "游戏已启动，是否最小化启动器？"):
                self.iconify()

    def update_selected_game_label(self, game_name: str):
        """更新选中游戏标签（移除冗余代码）"""
        self.selected_game_label.configure(text=game_name if game_name else "未选择游戏")

    def load_last_selected_game(self):
        """加载上次选中游戏（修复字段缺失）"""
        last_game = get_last_selected_game()
        if last_game:
            # 读取游戏名称（避免直接用路径推导）
            games_data_file = get_games_data_file()
            with FileLock(LOCK_FILE_PATH, timeout=5):
                try:
                    with open(games_data_file, 'r', encoding='utf-8') as f:
                        games = json.load(f)
                    for game in games:
                        if game.get("path") == last_game["path"] and game.get("is_last_selected", False):
                            self.update_selected_game_label(game.get("name", "未知游戏"))
                            return
                except Exception:
                    pass  # 忽略读取错误，显示路径推导名称
            # 备选：从路径推导名称
            game_name = os.path.splitext(os.path.basename(last_game["path"]))[0]
            self.update_selected_game_label(game_name)
        else:
            self.update_selected_game_label("未选择游戏")

    def on_closing(self):
        """关闭主窗口（清理子进程和子窗口）"""
        # 关闭所有游戏子进程
        if GAME_PROCESSES:
            if tk.messagebox.askyesno("确认关闭", "是否关闭所有已启动的游戏？"):
                for proc in GAME_PROCESSES:
                    try:
                        proc.terminate()
                        proc.wait(timeout=3)
                    except Exception:
                        pass  # 忽略关闭失败的进程

        # 关闭子窗口
        if self.select_window and self.select_window.winfo_exists():
            self.select_window.destroy()

        # 销毁主窗口
        self.destroy()


if __name__ == "__main__":
    # 检查依赖库（提示用户安装缺失库）
    try:
        from filelock import FileLock
    except ImportError:
        tk.messagebox.showerror("错误", "缺少依赖库，请先运行：pip install filelock pillow customtkinter")
        sys.exit(1)

    app = AdaptiveApp()
    app.mainloop()