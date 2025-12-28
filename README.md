[中文](Readme.cn.md)

## Any Launcher - Lightweight and Versatile Game Launcher

Any Launcher is a lightweight game launcher developed based on Python. It supports core functions such as game import, management, and quick launch, and is compatible with exe and HTML format games. It has practical features including automatic configuration saving, last selected game memory, and file integrity verification. It also optimizes common issues such as Chinese path compatibility and permission adaptation, providing a smooth game management experience.

### ✨ Core Features

- Game Import: Supports selecting local exe/HTML game files, automatically extracting default names and generating file MD5 checkcodes
- Game Management: Supports modifying game names/paths, precise deletion of single games (based on unique ID to avoid accidental deletion), and game list refresh
- Quick Launch: Remembers the last selected game, enables one-click launch, and supports minimizing the launcher after launch
- File Verification: Automatically calculates MD5 value when importing games, verifies file integrity before launch to prevent files from being tampered with or damaged
- Compatibility Optimization: Perfectly supports Chinese/special character paths, and stores configuration files in the AppData directory by default (avoiding system directory permission issues)
- Friendly Interaction: Provides clear error prompts, operation confirmation pop-ups, and supports window hierarchy management to avoid multi-window interference

### 📋 Requirements

- Python Version: 3.8 or higher
- Dependent Libraries: customtkinter, pillow, filelock
- System Support: Windows 7/10/11 (32/64-bit)

### 🚀 Installation Steps

#### 1. Install Dependencies

After cloning the project, execute the following command in the project root directory to install dependencies:

```Plain
pip install customtkinter pillow filelock
```

### 📖 User Guide

#### 1. Import Game

1. Run the program and click the "Select Game" button to open the game selection window
2. Click "Import Game" and select the local game's exe or HTML file in the file selection window
3. Enter the game name in the pop-up window (the default file name is extracted, which can be modified), and click "Confirm" to complete the import

#### 2. Manage Game

- Modify Game: Select the game in the game selection window, click "Game Settings" to modify the name or reselect the game path (MD5 will be updated automatically)
- Delete Game: Select the game in the game selection window, click "Delete Game", and confirm to delete (only deletes the selected game, does not affect local game files)
- Refresh List: If you manually modify the configuration file, click "Refresh List" to reload the game data

#### 3. Launch Game

1. Select the target game through the "Select Game" window and click "Select and Close" to return to the main window
2. The main window will display the name of the currently selected game, click "Launch Game" to start
3. After successful launch, you can choose whether to minimize the launcher (does not affect game operation)

### 📁 Project Directory Explanation

```Plain
Any Launcher/
├── anylauncher.py          # Project entry file (core logic implementation)
├── app.ico          # Program icon (optional)
├── logo.png         # Launcher interface logo (optional, text prompt is displayed if missing)
├── # Game configuration file (stored in AppData/Roaming/Any Launcher by default)
└── LICENSE # License file
```

### 🔧 Troubleshooting

- Q: Prompt "No write permission" when importing games? A: Please run the program as an administrator, or manually set the configuration file path (AppData/Roaming/Any Launcher) to writable permission.
- Q: Prompt "File not found" when launching the game but the file actually exists? A: The path may contain special characters. It is recommended to reselect the game path through "Game Settings", and the program will automatically handle path encoding.
- Q: Configuration file is corrupted and cannot be loaded? A: Delete the games.json file in the AppData/Roaming/Any Launcher directory and re-import the game.
- Q: Logo display is abnormal? A: Check if there is a logo.png file in the project root directory, or replace it with a picture of the appropriate size (recommended size 400x200).

### 📄 License


This project is open source under the MIT License, and can be freely modified, distributed and used commercially. See the LICENSE file for details.
