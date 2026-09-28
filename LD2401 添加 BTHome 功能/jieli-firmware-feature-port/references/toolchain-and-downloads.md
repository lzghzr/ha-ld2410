# 工具边界、下载和解包

技能目录只放 Python 标准库脚本和文字参考，避免把大型 SDK、编译器、Android 工具或下载器复制进全局技能。内置脚本位于 `scripts/`：

```powershell
python "<技能目录>\scripts\inspect_ufw.py" "<固件.ufw>" --json "<报告.json>"
python "<技能目录>\scripts\unpack_ufw.py" "<固件.ufw>" --out "<解包目录>"
```

`inspect_ufw.py` 只读检查 UFW/JLFS、镜像、应用文件、VM/PRCT 边界和 CRC。`unpack_ufw.py` 输出可反汇编的 `app.bin`、配置工具和非敏感应用文件，并写入 `manifest.json`；默认不导出 `isd_config.ini` 或 `VM`，以免把升级密钥、BTHome 密钥和计数器写到可随意复制的解包目录。

## Q32S 编译工具链

优先使用已经验证的杰理 SDK 工具链，不把可执行文件放入技能目录。Windows 上的默认查找位置是：

```text
C:\JL\pi32\bin\clang.exe
C:\JL\pi32\bin\q32s-ld.exe
C:\JL\pi32\bin\llvm-objdump.exe
C:\JL\pi32\bin\llvm-objcopy.exe
```

取得方法：从杰理 AC632N/AC635N SDK 的官方交付包或供应商提供的 SDK 下载页获取对应版本，解压到 `C:\JL`，然后在构建脚本中通过绝对路径或 `JL_TOOLCHAIN` 环境变量指定 `pi32\bin`。每次记录工具链版本和可执行文件 SHA-256；不要用主机的 ARM/普通 RISC-V 编译器替代 Q32S 工具链。

## UFW/JLFS 和 OTA 工具

格式检查和解包使用本技能自带脚本。需要把 donor `update.ufw` 封装到 LD2401 原厂包时，使用全局 `ld2401-ufw-transplant` 技能中的标准库脚本；其输入、Key 保留和 CRC 约束已写在该技能中。OTA 下载器使用用户已经验证的 HLK/JieLi 官方工具或手机 App，技能只生成并审计包，不连接设备。

## 反汇编和 APK 辅助工具

`llvm-objdump` 随 Q32S SDK 提供。需要分析 Android App 时，单独安装官方发布的 apktool、JADX 和 Android build-tools（`apksigner`），并把它们放入临时工具目录或 PATH；这些工具和 APK 不属于固件功能技能的最小运行集。
