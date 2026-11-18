# 物理引导角色动画

[观看演示](https://xiuyuyang.github.io/physics-guided-character-animation/zh/) · [English](README.md)

奔跑中的角色受力后，有的继续跑，有的跌倒后重新起步，有的在试次结束时仍然倒地。这个工程用 **Perpetual Humanoid Control（PHC）** 和 Isaac Gym 计算受力反应，并把动作转移至 Unreal Engine 的默认角色 Manny。

[![Unreal 实拍。四条跑道分别展示小腿、肩侧、胸口和无外力对照](docs/media/contact-preview.gif)](https://xiuyuyang.github.io/physics-guided-character-animation/zh/)

## 看哪里

| Unreal 实拍 | 观察重点 |
| --- | --- |
| [同样的力，施加在不同部位](https://xiuyuyang.github.io/physics-guided-character-animation/zh/#title) | 250 N 下小腿组继续跑，肩侧组跌倒后重新站起，胸口组在试次结束时仍倒地。第四条跑道是无外力对照。 |
| [起身接跑优化前后](https://xiuyuyang.github.io/physics-guided-character-animation/zh/#recovery) | 两边用的是同一次肩侧受力。改进版在 32 帧（1.07 秒）内把重新迈步过渡到相位匹配的跑步循环。 |
| [三种落石尺寸与碰撞对照](https://xiuyuyang.github.io/physics-guided-character-animation/zh/#drops) | 对比 12、45、100 厘米球进入 16 人队列的表现，并以 1 米球对比人物间碰撞开关。 |
| [100 人测试](https://xiuyuyang.github.io/physics-guided-character-animation/zh/#scale) | 100 名 PHC 角色和 1 米球同场仿真。 |
| [滚石和八名跑者](https://xiuyuyang.github.io/physics-guided-character-animation/zh/#crowd) | 轻擦的角色恢复跑动，受到严重撞击的角色保持倒地。 |
| [闪光脉冲与箭形道具](https://xiuyuyang.github.io/physics-guided-character-animation/zh/#projectiles) | 两种游戏化效果用同一批点力试次展示受力和接跑。 |

## 在 Unreal 里运行

1. 安装 **Unreal Engine 5.8**、Python 3 和 Epic 的 [Unreal 5.8 Content Examples 示例工程](https://dev.epicgames.com/documentation/unreal-engine/content-examples-sample-project-for-unreal-engine?lang=en-US)。
2. 克隆仓库，在仓库根目录的 PowerShell 中执行以下命令。将参数改为本机示例工程文件夹。如果引擎装在其他目录，可加上 `-UnrealRoot "D:\Epic Games\UE_5.8"`。

   ```powershell
   python -m pip install -r requirements.txt
   .\Setup-Unreal.ps1 -ContentExamples "C:\Unreal Projects\Content Examples"
   ```

3. 打开 [BoulderCrowd.uproject](Unreal/BoulderCrowd/BoulderCrowd.uproject)，点 **Play**。在 Sequencer 打开 `LS_Recovery_250` 可逐帧观察第 **60–63 帧**的受力和第 **133–165 帧**的肩侧接跑过渡。

| 关卡 | 内容 |
| --- | --- |
| `L_Recovery_250` / `L_Recovery_700` | 带相位对齐和接跑过渡的局部受力演示 |
| `L_Contact_250` / `L_Contact_700` | 原始 PHC 试次，用作前后对照 |
| `L_BoulderCrowd` | 八名跑者的滚石群演 |
| `L_Drop_Palm` / `L_Drop_Medium` / `L_Drop_Large` | 16 人密集队列，三种球体尺寸，同一材料密度 |
| `L_Drop_Isolated` / `L_Drop_100` | 16 人关闭人物间碰撞的对照，以及单独的 100 人测试 |
| `L_Pulse` / `L_Dart` | 带接跑优化的两种局部命中演示 |

安装脚本从本机 Epic 示例工程导入 Manny，再用仓库里的试次记录生成关卡、动画和轨迹。计算新的仿真试次需要另行配置 PHC 和 Isaac Gym。

12 厘米球的释放位置微调了约 12 厘米，以确保碰到队列边缘。接触标记由受力和间距推断，并用关闭人物间碰撞的试次核对。终止状态采用演示的游戏规则。详见[试次结果](evidence/impact-showcase/)。

## 实现流程

1. 局部受力试次从同一个跑步相位起步。三次独立模拟将持续 4 个控制步的点力施加到指定 PHC 刚体上。青色标记显示转移到 Manny 后的接触位置。
2. 将记录中的骨骼姿态和根轨迹转换给 Manny。对重新站起来的角色，确认脚部支撑、选择匹配的跑步相位，再让姿态和速度逐渐接回循环。
3. 烘焙并在 Unreal Sequencer 中播放。[运行时核验](evidence/contact-probe/exact-contact/recovery-runtime-audit.json)记录了 3 处接缝，最大根速度跳变约 **0.000037 m/s**。

详见[运动转换代码](tools/)、[试次和验收证据](evidence/contact-probe/exact-contact/)及[素材来源](THIRD_PARTY.md)。
