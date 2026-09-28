---
name: hlkradartool-apk-mod
description: 修改 HLKRadarTool（HLK 雷达工具 App）的 APK 并重新签名、装机——加界面（OUT 输出控制、BTHome 密钥块与换钥、自定义固件升级入口）、改协议行为（配置会话谁开谁关、命令帧什么时候发）、修“设置成功/设置失败”弹窗与状态反馈、排“进参数设置闪退”。当用户说“改 app/改 APK/重新打包安装”“app 侧修，不要动固件”“HLKRadarTool”“自定义固件升级按钮”“OUT 输出控制”“BTHome 密钥/取密钥/换钥/重置密钥”“设置失败”“不弹设置成功”“参数页闪退”，或提到 apktool / smali / d8 / apksigner / 重签名时，都应当使用本 skill，即使用户没有说出“APK”两个字。
---

# 修改 HLKRadarTool APK

用户手机上装的是**改造过**的 HLKRadarTool 1.6.112（包名 `com.hlk.hlkradartool`，自有密钥签名）。
协议行为的问题优先改 app，不改雷达固件。

## 一、技能自带什么、环境要自备什么

项目目录是构建的工作区（`C:\AgentWorkspace\LD24`），可能被清理；**手写、拿不回来的东西**在技能里留了一份，
其余按下面的步骤自备即可。

**技能自带（`scripts/`）**

| 路径 | 内容 |
|---|---|
| `scripts/helper/*.java` | 辅助类源码：`OutControlHelper`（OUT 块 + BTHome 密钥块）、`CustomFwHelper`（自定义固件升级） |
| `scripts/helper/*.py` | `build_all.py` 与它调用的 5 个补丁脚本：`patch_smali`、`minimal_fix`、`patch_a601_popup`、`patch_bthome_key`、`patch_onframe_hook` |
| `scripts/verify_delivery.py` | 交付前静态校验：与原厂包差集、注入点计数、dex 标记断言、交互规则证据 |
| `scripts/check_helper_copy.py` | 技能副本与项目副本按哈希对账（`--update` 用项目那份刷新技能那份）；改完 `apk/helper` 记得跑一次 |

**要自备的**（脚本里的路径按 `apk\tools\`、`apk\tree\`、`doc\` 这个布局写死）：

| 需要 | 放哪 | 怎么来 | 本项目用的版本 |
|---|---|---|---|
| **签名密钥** | `apk\keys\hlk_key.p8` + `apk\keys\hlk_cert.der` | 本项目自有的这一对，**只存在项目里、不进技能**（私钥不随身带）。**它丢了，手机上就只能卸载重装（配置全丢）**，所以自己再备份一份到别处；证书指纹 `41df17236cfec03f…`，`scripts/check_helper_copy.py` 每次会报告它在不在 | — |
| JDK（`java` / `javac`） | 系统 PATH | 任意 JDK 8+ | `build_all.py` 顶部的 `JAVA`/`JAVAC` 写死的是 Oracle javapath，换机器要改这两行 |
| apktool | `apk\tools\apktool-cli.jar` | Apktool releases 的 `apktool-cli.jar`（`baksmali` 也从它调用：`-cp apktool-cli.jar com.android.tools.smali.baksmali.Main`）<br>https://github.com/iBotPeaches/Apktool/releases | 3.0.3 |
| d8 / apksigner / zipalign | `apk\tools\android-14\{lib\d8.jar, lib\apksigner.jar, zipalign.exe}` | Android SDK `build-tools\<ver>\`（或命令行工具包） | SDK 同版本线即可 |
| `android.jar` | `apk\tools\android.jar` | SDK `platforms\android-<api>\android.jar`，只给 javac 编译辅助类用 | 任一近年平台 |
| jadx（可选，读 app 的 Java 逻辑） | `apk\tools\jadx\` | https://github.com/skylot/jadx/releases | 1.5.1 |
| cfr（可选，单个类反编译） | `apk\tools\cfr-0.152.jar` | https://www.benf.org/other/cfr/ | 0.152 |
| 原厂底包 | `doc\HLKRadarTool_release_1.6.112.apk` | HLK 官方渠道。**必须是 1.6.112 这一版**：补丁的锚点断言按它写，换版本会直接 assert 失败 | 1.6.112，sha256 `96d514f03005cef5938e8e41a0e345ff1432340d2c1ba0bd3de3ba619e75fcda` |
| 反编译树 | `apk\tree\` | 由底包生成，交给 `build_all.py --fresh` 自己做：`apktool d doc\HLKRadarTool_release_1.6.112.apk -o apk\tree` | — |

**项目目录被清理后的恢复顺序**：拿到 1.6.112 底包放进 `doc\` → 按上表建好 `apk\tools\`（apktool / d8 / apksigner /
zipalign / android.jar）→ 把技能的 `scripts/helper` 拷回 `apk\helper`、把备份的签名密钥放回 `apk\keys` →
`python -B apk/helper/build_all.py --fresh`。

一键构建（约 3–5 分钟：重新解码 → 编译辅助类 → 打补丁 → 重打包 → 签名 → 覆盖交付包）：

```
python -B apk/helper/build_all.py --fresh
python -B scripts/verify_delivery.py          # 技能里那份；项目里另有一份在 analysis/apk_randomkey_reset/
adb install -r apk/dist/HLKRadarTool_1.6.112_customfw_light_signed.apk
```

## 二、管线

1. `apktool d <release.apk> -o apk/tree`（只做 `--fresh` 时）
2. `javac -encoding UTF-8 -cp android.jar …` → `d8`（**输出目录必须先存在**）→ `baksmali`，得到辅助类 smali
3. `patch_smali.py`：VersionListActivity 的“自定义固件升级”入口、ControlBLEActivity/SetParameter2Activity
   的光敏可见性、`OutControlHelper` 的 OUT 块
4. `minimal_fix.py`：把 OUT 块做成**只发 A6 一帧**（按 glob 装全部 `OutControlHelper*.smali`）
5. `patch_a601_popup.py`：给参数页 ACK 分发加 `A601` 分支（弹“设置成功”）
6. `patch_bthome_key.py`：密钥块的两个注入点 —— `init()` 里 `OutControlHelper.addKeyRow(this)`、
   `onReceiveInfoMessage` **方法入口**一行 `void` 的 `OutControlHelper.onInfo(this, info)`
7. `patch_onframe_hook.py`：数据漏斗 `DemoApplication.parseByData` 里、LD2401 分发调用前，插一行
   `OutControlHelper.onFrame(frame)`（密钥块的取数来源，见 app-map）
8. `apktool b` → 把新的 `classes2.dex` 换回**原厂 release APK**（保留其它 dex/资源/**非签名 META-INF**）→
   `zipalign -p 4` → `apksigner sign --key … --cert …`

**换 dex 时只排除 JAR 签名条目**（`MANIFEST.MF`/`*.SF`/`*.RSA`/`*.DSA`/`*.EC`）：官方包里带着
`META-INF/services/kotlinx.coroutines.*`、`androidx.*.version` 等数据文件，丢掉会引入无谓差异。
这样产出的包与原厂 release 包**只差 `classes2.dex`**，出问题时排查面最小。

**每一步都要独立断言**：`javac` 的 class 个数、`d8` 后 smali 里的方法名、进树后的调用点计数、
重打包 dex 里的字符串标记、签名包复查。任何一步静默产出空结果都会变成“改了不生效”或运行时
`NoSuchMethodError`，`build_all.py` 把这些断言串在一起。

## 三、常见诉求怎么做

**加界面 / 加交互**：写一个 Java 辅助类（放 `apk/helper/`，包名 `com.hlk.hlkradartool.tool`），
在目标 activity 的 smali 里**插一条静态调用**。插调用时优先选**少参数、无参数**的方法签名——
在 smali 里就地改 `.locals` 找空闲寄存器风险高，用辅助类可以把寄存器问题关在 Java 里。

**加功能的两个硬规矩**：

1. **代码加进该页面本来就会加载的辅助类**（设置页用 `OutControlHelper`）。smali 里插的
   `invoke-static` **不在任何 try/catch 里**，而类校验就发生在那个调用点上；新建一个类等于把一个
   新的校验/解析点放到调用处，失败会（`VerifyError`/`NoClassDefFoundError`）把整个页面带走。
2. **入口 hook 用 `void`、不碰控制流**：只插一行 `invoke-static`，不要 `move-result` + `if-eqz` + `goto :标签`。
   把 hook 跳到方法**中段**的标签尤其危险：那会在方法里造出汇合点，两条路径携带的寄存器类型不同，
   是 ART 校验最容易判死的形状。功能失败最多“不显示”，不能影响页面本身。

**从 `ReceiveInfo` 取数据**：命令字在 `getStrParam()`、状态在 `getBlParam()`。
`blParam` 为真（状态字段 `0000`）时方法在 ACK 比对链**之前**就跳到“参数 + 设置失败”分支，
所以 **A6 应答不会进 ACK 链**——要处理它就只能在 `onReceiveInfoMessage` **方法入口**取 `ReceiveInfo` 对象。
`getDataParam()` 对 ACK 类帧常是空串（见 app-map 的 A6 载荷说明）；按名字取不到时的兜底：
扫描所有无参 String getter，取值等于 `A601` 的当命令字、形如 32+ 位 hex 的当载荷。

**改协议行为**：帧模板是 ASCII 十六进制字符串，集中在
`com.hlk.hlkradartool.data.CreateControlData$Companion`（114 条 `FDFCFBFA…04030201`）；
发送入口是 `BLEListActivity.sendDataByMAC(String mac, String frame)`。
辅助类发帧用反射：`BLEListActivity.getInstance()` → `sendDataByMAC`；MAC 取
`DemoApplication.getInstance().nowSelectDevice.getMACAddress()`。

**加提示/弹窗**：参数页的 ACK 分发是 `SetParameter2Activity.onReceiveInfoMessage(ReceiveInfo)` 里
一串 `const-string v0, "6001" / "AD01" / …` + `equalsIgnoreCase` 的比对链。原生“设置成功”长这样：

```
iget-object p1, p0, …SetParameter2Activity;->areaConfirmWindowHint:Lcom/hlk/hlkradartool/view/AreaConfirmWindowHint;
sget v0, Lcom/hlk/hlkradartool/R$string;->shezhi_chenggong:I
invoke-virtual {p0, v0}, …;->getString(I)Ljava/lang/String;
move-result-object v0
invoke-virtual {p1, v0}, …AreaConfirmWindowHint;->setMsgAndShow(Ljava/lang/String;)V
```

新增分支时**先改前一个分支的失配跳转、再插入新块**：`str.replace` 会替换所有匹配，
如果把新块里的落点也一起改掉，新块就会跳到自己形成死循环。

## 四、会话语义与发送时序

配置会话的标志在模块里是 `0x4388`，**开关都由页面自己的代码发，各页位置不统一**：

- **参数页 `SetParameter2Activity.onResume()`** 进入时发
  `FDFCFBFA0400FF00010004030201`（`0x00FF`）开会话（原厂代码），**从不发 FE**；
- 控制页在 `sendSetValue` / `refreshListener` 发 FF，FE 在收到 `A201`（设置成功）等 ACK 之后、
  于 `onReceiveInfoMessage` 里发；
- 会话被关掉后，该页后续的写会全部回 status 1（“设置失败”），且本页不会自己重开——
  退出重进由 `onResume` 重新打开。

⇒ **注入的块只发命令帧**：既不补发 FF（页面已经开好了会话），更绝不能发 FE
（那会把整页的会话关掉，之后距离/光敏/OUT 全部“设置失败”）。

⇒ **一次操作发一条命令帧，不写定时重试**。原厂参数页没有延时重发机制（全页唯一的 `postDelayed`
在 `onResume` 里、且不发数据），控制页的“保证送达”是 ACK 驱动的：`sendSetValue` 把待发帧塞进
`strWillSendData` 单槽，等上一帧 ACK（`onReceiveInfoMessage` 的 `FF01`/`A001` 分支）再发出去。

⇒ **要发帧就在具体的点击回调里发**：`sendDataByMAC` 是总入口，参数页进入时有突发读、之后最多
19 个发送点，在那里逐帧加一帧 + 一次反射会让页面卡到不可用。

## 五、验证与交付

- 装机：`adb install -r`（同一把密钥才能覆盖安装）→ 启动后
  `adb logcat -d | grep -E 'VerifyError|FATAL EXCEPTION'` 应为空（`VerifyError` 说明插进去的调用点
  过不了 ART 校验，整页或整个 app 会被带走）。
- **交付前做“与原厂包的差集”检查**：只应多出自己签的 3 个 `META-INF` 条目，内容差异只应有
  `classes2.dex`；再 `apksigner verify --verbose`（v2/v3 为 true；v1=false 不影响安装）。
  这两项与注入点计数、dex 标记断言都在 `scripts/verify_delivery.py`（项目里另有一份副本）里。
- 交付文件 `doc/HLKRadarTool_1.6.112_customfw_light.apk`，覆盖前把上一版留一份备份（回滚要用）。
- 按帧核对：辅助类都打了 `OutControlHelper`/`CustomFwHelper` 的 tag，直接 `adb logcat` 过滤即可；
  app 自己也会把每个收到的帧打成 `接收蓝牙有效数据：<完整帧>`。

细节速查（关键类、ACK 表、会话帧、密钥块、补丁脚本、陷阱）见 `references/app-map.md`。
