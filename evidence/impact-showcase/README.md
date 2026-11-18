# Dense-crowd trial data / 密集人群试次

| Replay | GPU simulation inputs and results |
| --- | --- |
| 16 runners / 16 人 | [Report](dense-16/review.json), no-rock control, three sizes, and 1 m with runner collisions off |
| 100 runners / 100 人 | [Report](scale-100/review.json), no-rock control and 1 m with runner collisions on |

Each gzip file contains the recorded 30 Hz body transforms, sphere transforms, and net forces. The 16-runner takes span 180 frames. The 100-runner takes span 240 frames to leave more time for recovery. The sphere shares the same density across sizes. The 12 cm release was moved slightly to make edge contact.

Direct-contact markers use measured net forces and geometric proximity. Secondary markers in the 16-runner scene also use deviation from the run with collisions between runners disabled. The per-actor attribution is inferred from nearby moving or falling actors. A terminal state uses a scene-specific rule and holds the measured down pose. Other actors continue to follow PHC. Recovered actors use the stance-matched Unreal run transition when the recording includes enough time for a complete handoff.

每个 gzip 文件包含 30 Hz 的角色姿态、球体轨迹和净受力。16 人试次为 180 帧，100 人试次延长到 240 帧，以便观察起身。三种尺寸共用同一密度，12 厘米球的释放位置略有调整，以便擦到队列边缘。

直接接触用实测净力与几何距离推断。16 人场景的连锁标记还参考关闭人物间碰撞后轨迹的变化，再按近邻推断受影响角色的来源。达到游戏终止规则的角色保持倒地姿态，其他角色继续由 PHC 尝试恢复。起身后有足够时间的角色会按脚步相位接回跑步循环。
