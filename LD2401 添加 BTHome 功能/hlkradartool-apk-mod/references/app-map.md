# HLKRadarTool 1.6.112 地图速查

包名 `com.hlk.hlkradartool`。反编译树：`C:\AgentWorkspace\LD24\apk\tree`（`smali_classes2` 是主体）。

## 关键类

| 类 / 方法 | 作用 |
|---|---|
| `activity.BLEListActivity` | 设备列表页，也是**发送总入口**：`sendDataByMAC(String mac, String frame)`；有静态 `getInstance()` |
| `activity.DemoApplication` | 全局单例：`getInstance()`、字段 `nowSelectDevice`（`data.SearchBLEDeviceInfo`，`getMACAddress()`）；`parseByData(String mac, String raw, String model)` 是**收到的帧的唯一漏斗** |
| `activity.SetParameter2Activity` | 参数页（LD2401 的距离/光敏/灵敏度/OUT/密钥块都在这里）；`onReceiveInfoMessage(ReceiveInfo)` 是 ACK 分发 |
| `activity.VersionListActivity` | 固件版本页（“自定义固件升级”按钮 + `onActivityResult` 在这里注入） |
| `activity.ControlBLEActivity` | LD2401 控制页（补丁放行 `HLK-LD2401_` 名称） |
| `activity.Control2411s/2412/2417/2450/2451Activity` | 其它型号控制页，会话帧的另一种写法 |
| `data.CreateControlData$Companion` | 帧构造器：114 条 ASCII 模板，如 `FDFCFBFA140060000000`（0x60）、`FDFCFBFA0600AD00`（0xAD）、`FDFCFBFA0400FF00010004030201`（0xFF） |
| `data.ReceiveInfo` | 收到的帧：`getStrMac()`、`getICode()`、`getStrParam()`、`getBlParam()`、`getDataParam()` 等 |
| `view.AreaConfirmWindowHint` | 原生提示窗：`setMsgAndShow(String)` / `setMsgAndShow(String, String)` |
| `tool.CustomFwHelper` | 本地新增：自定义固件选择/复制/启动 OTA 页 |
| `tool.OutControlHelper` | 本地新增：设置页的 OUT 输出控制块 + BTHome 密钥块。`addTo`/`addKeyRow` 建界面，`onInfo` 挂在参数页 `onReceiveInfoMessage` 入口，`onFrame` 挂在数据漏斗 |

控制密码：**弹窗让用户输入**（`view/CheckCtrPwdWindowDialog`，`EditText edPwd`，提示 `shuru_kongzhi_mima`），
默认值 `HiLink` 由 `BLEListActivity$20` 传入；**模块没有“读密码”命令**（0xA8 只校验、0xA9 只设置）。
密码只决定配置权限，与 BTHome 密钥无关。

字符串资源：`R$string->shezhi_chenggong`（设置成功）、`shebei_xuyao_chongqi`、`liji_chongqi`、
`shezhi_shibai` 等；用 `p0.getString(id)` 取。

## `onReceiveInfoMessage` 里的 ACK 分支

```
FF01  FE01  6001  6401  A901  AA01  A101  AD01  B801  B301  6101  A001  AB01  AE01  D301  A601
```

链条结构：每段 `const-string v0, "<ACK>"` + `equalsIgnoreCase` + `if-eqz v0, :下一段`，
命中就干活并 `goto/16 :goto_0`。插入新段必须同时把**前一段的失配跳转**指到新标签。

**注意**：A6 应答走不到这条链 —— 它的状态字段是 `0000` ⇒ `getBlParam()` 为真，方法在链之前就跳到
`StrParam + shezhi_shibai`（“设置失败”）分支。所以 A6 应答只能在**方法入口**处理（`p1` 还是
`ReceiveInfo` 对象），`A601` 分支只用于 OUT 设置的“设置成功”提示。

方法开头还有两道门：`getStrMac()` 要等于当前设备 MAC、且 `isShowTask` 为真，否则直接返回。

## 收到的帧怎么走（A6 载荷为什么要另外取）

1. `DemoApplication.parseByData(mac, raw, model)` 从接收缓冲里切出**完整帧**（`FDFCFBFA`/`F4F3F2F1`
   开头、`04030201`/`F8F7F6F5` 结尾）并按型号分发到 `DataAnalysisHelper.startDataAnalysis*`。
   app 自己会把它打成 `接收蓝牙有效数据：<完整帧>`。
2. `DataAnalysisHelper` 用它构造 `ReceiveInfo`：命令字进 `getStrParam()`（A6 应答 = `"A601"`），
   **但 20 字节的 A6 帧没有对应分支，`getDataParam()` 会是空串**，其余 String getter 也没有载荷
   （`getObjects()` 从不赋值）。实测一行日志：`info: cmd=A601 pay= key=null`。
3. ⇒ **想要 A6 应答的载荷，就得自己在第 1 步的漏斗里取**。`OutControlHelper.onFrame(String)` 就挂在
   那里（`patch_onframe_hook.py`）：对每帧做一次 `toUpperCase + indexOf("A6010000")`，命中就把其后
   32 位 hex 存进 `LAST_KEY`；参数页的 `onInfo` 收到 `A601` 时取用（帧先到、事件后到，都在主线程）。

## 会话帧（FF/FE）

- **参数页 `SetParameter2Activity.onResume()`** 发 `FDFCFBFA0400FF00010004030201`（`0x00FF`）开会话，
  **从不发 FE**；控制页在 `sendSetValue`/`refreshListener` 发 FF，FE 在收到 `A201` 等 ACK 之后的
  `onReceiveInfoMessage` 里发。各页都是硬编码字面量，没有统一管理。
- FE 会关掉模块里的会话（`0x4388`）：该页之后所有写都回 status 1（“设置失败”），且不退出重进不会恢复。
  ⇒ 注入的代码只发命令帧：不补发 FF，更不发 FE。

## OUT 控制（本地新增）的协议

- 命令 `0x00A6`，载荷 4 字节：`A6 00 <参数 2 字节 LE>`；固件语义 `0`=保持低、`1`=保持高、`2`=释放覆盖。
- **只发这一帧**，从单选回调里直接发；应答是 `A601`，页面上靠 `A601` 分支弹“设置成功”。

## BTHome 密钥块（本地新增）

界面（`rlCtrPwd` 下方，主行 40dp + 一行 11sp 红字提示）：

```
BTHome 密钥： 点击获取                               点击重置
 重置后模块换新密钥，需在 HA 里重新填写 bindkey
```

取到密钥后那一格被密钥替换（太长用 `...` 截断）：

```
BTHome 密钥： f076b1fc19fd86ff85e7ccfbbdd258f3        点击重置
 重置后模块换新密钥，需在 HA 里重新填写 bindkey
```

- 那一格**兼任取钥入口**：`width=0, weight=1` 占满 label 与「点击重置」之间，`singleLine` +
  末尾 `...`；样式抄 `tvpass`，label 抄 `tvCtrTitle`。「点击重置」`ALIGN_PARENT_RIGHT`、红字
  （`styleResetAction`：抄 `tvpass` 字号/字体 + 恒定 `0xFFFF0000`）。行本身**不可点**。
  id：行 `0x4f2a`、值 `0x4f2b`、重置 `0x4f2e`（原厂 id 都是 `0x7f……`，不会撞）。
- **手势**：点那一格 = 取钥（只在它显示「点击获取」或状态字时）；**密钥已显示时点它不响应**；
  长按它 = 复制；点「点击重置」第一次只上膛（不发帧，5 秒自动回退）、第二次才发 `A604`；
  点那一格会取消上膛（`disarmReset`，靠 `RESET_TOKEN` 递增让旧的延时回退失效）。
- 值里出现的字都是纯 UI 状态、不发帧：`点击获取` → `读取中…` → 密钥 / `未收到应答`（2.5 秒无应答）/
  `应答无法识别`（收到 A6 应答但解析不出密钥）。
- **行里每个可点元素都要自己的 `OnClickListener`**：只挂长按监听的可点子视图会吞掉点击，
  只有没挂监听的那部分（如 label）才把事件留给行。

协议：

| 动作 | 帧 |
|---|---|
| 取密钥 | `FDFCFBFA0400A600030004030201`（A6 参数 3） |
| 换钥 | `FDFCFBFA0400A600040004030201`（A6 参数 4；与取密钥帧只差参数 2 字节） |
| 应答 | 命令字 `A601`，载荷 `A6010000` + 16 字节密钥 |

- 实测应答（BLE 上带壳）：`FDFCFBFA 1400 A6010000 <16 字节密钥> 04030201`。
- **解析锚点**：候选串可能是整帧（带 `FDFCFBFA`/`04030201` 外壳），也可能只有载荷，所以密钥位置
  按 `A6010000` 锚点定位：它后面紧跟的 32 位 hex 就是密钥。候选串的末两位是帧尾 `04030201`，
  按字符串末尾定位会取到帧尾并丢掉密钥前 8 位。
- **一次操作一条命令帧，没有重试**：`A604` 之后也不补读（换钥的 `A601` 会自己刷新那一格）。
  参数 4 需要固件 `26092424`+；更早的固件把 A6 参数 4 当未知参数拒绝，那一格会停在「点击获取」。

固件侧的接口约定：`A603` 返回当前密钥、`A604` 生成新随机密钥（计数器归零并持久化）后按同样格式返回；
改密码、重启、OTA 都不动密钥与计数器。新密钥落盘并回读通过之前不应回 `A601`——
app 拿到应答就会显示它。

## 补丁脚本一览（`apk/helper/`）

| 脚本 | 做什么 | 幂等性 |
|---|---|---|
| `patch_smali.py` | 自定义固件入口、光敏可见性、OUT 块注入 | 只能在**新解码的树**上跑（有 `assert ... not in t`） |
| `minimal_fix.py` | OUT 块只发 A6 一帧（按 glob 替换全部 `OutControlHelper*.smali`） | 可重复跑 |
| `patch_a601_popup.py` | 加 `A601` 弹窗分支 | 跑第二次会 assert |
| `patch_bthome_key.py` | 密钥块两个注入点：`addKeyRow` + `void onInfo` | 可重复跑（第二次报 already present） |
| `patch_onframe_hook.py` | 数据漏斗注入 `onFrame`（LD2401 分发调用前一行） | 可重复跑 |
| `build_all.py` | 串起全部步骤 + 重打包/换 dex/对齐/签名 | `--fresh` 从头；`--skip-patches` 在现有树上只重打包 |

## 陷阱清单

1. `str.replace` 替换全部匹配 —— 插入 smali 块时先改跳转、再插入。
2. `d8 --output` 的目录必须已存在，否则报 “Invalid output”。
3. 帧常量常常在内嵌类里（发帧的监听器是 `OutControlHelper$N.smali`），断言和拷贝都要用 glob 扫
   全部 `OutControlHelper*.smali`，别写死文件名：加了匿名类就会多出 `$3/$4/$5`，
   漏拷一个就是运行时 `NoClassDefFoundError`。
4. 终端里的 `grep` 大参数列表会 `Argument list too long`，用 Python 读文件代替。
5. 重新签名必须用 `apk/keys/` 里那对密钥，否则手机上要卸载重装（丢配置）。
6. 装机后先看 `VerifyError` 与 `FATAL EXCEPTION` 计数：`VerifyError` 是注入点过不了 ART 校验，
   `NoSuchMethodError` 通常是“改了没生效 / 旧 smali 被沿用”。
7. **把代码加进页面已加载的类、hook 用一行 `void`**：类校验发生在插进去的 `invoke-static` 处，
   那里不在任何 try/catch 里，一个新类或一次控制流改动失败就会把整页带走。
8. **写源码和脚本用 Write/Edit 工具**：bash heredoc 会吃掉 `\n`（连 `\a` 也会变成 0x07 控制字符），
   结果是 Python/Java 语法错误或文件里藏控制字节。
9. 替换 dex 时保留非签名 `META-INF/`（`services/*`、`*.version`），只排除 JAR 签名条目。
10. 覆盖交付包前先备份上一版：唯一的构建产物被覆盖后就没法再对比 dex，只能重建。
