# Neural Network–Driven Skeletal Character Animation

[Watch the final demo](https://xiuyuyang.github.io/physics-guided-character-animation/) · [简体中文](README.zh-CN.md)

**Physics-based character control with pretrained PHC neural networks, demonstrated with 100 characters reacting, falling, and recovering.** Each character responds independently to falling spheres and neighboring bodies. The resulting skeletal motion is retargeted to Manny in Unreal Engine.

[![Final-stage 100-character falling-sphere demonstration](docs/media/scale.jpg)](https://xiuyuyang.github.io/physics-guided-character-animation/)

## Final results

- [100-character scene](https://xiuyuyang.github.io/physics-guided-character-animation/#scale) shows eight seconds of simulation. Four characters complete their return to running and nine enter the terminal state and stay down.
- [Three falling-sphere sizes](https://xiuyuyang.github.io/physics-guided-character-animation/#drops) demonstrate 12, 45 and 100 cm spheres in a dense 16-character group. Mass scales with volume at one density.
- [Localized impacts](https://xiuyuyang.github.io/physics-guided-character-animation/#projectiles) visualize the same point-force trials with a flash pulse and a stylized dart.

## Neural animation pipeline

**Character state and reference motion → PHC neural inference → joint-control actions → PD and PhysX → skeletal motion → Manny retargeting and Unreal playback.**

Characters share policy weights and retain independent physical states. The neural controller continuously drives posture and recovery attempts during offline simulation. Unreal plays the baked results. Code handles phase matching and speed blending back into the reference run. A scene-defined terminal rule holds the down pose. This project uses existing pretrained PHC weights.

## Run in Unreal

1. Install **Unreal Engine 5.8**, Python 3, and Epic's [Content Examples for Unreal 5.8](https://dev.epicgames.com/documentation/unreal-engine/content-examples-sample-project-for-unreal-engine?lang=en-US).
2. Clone this repository and run the following from its root in PowerShell. Pass the local Content Examples folder. If the engine lives outside Program Files, add `-UnrealRoot "D:\Epic Games\UE_5.8"`.

   ```powershell
   python -m pip install -r requirements.txt
   .\Setup-Unreal.ps1 -ContentExamples "C:\Unreal Projects\Content Examples"
   ```

3. Open [BoulderCrowd.uproject](Unreal/BoulderCrowd/BoulderCrowd.uproject), open `L_Drop_100`, and press **Play**. Use `LS_Drop_100` in Sequencer for frame-by-frame viewing.

The setup script imports Manny from local Epic Content Examples and rebuilds the final demonstrations from the included data. New physical trials require a separate PHC and Isaac Gym installation.

[Credits and asset sources](THIRD_PARTY.md) · [PHC upstream](https://github.com/ZhengyiLuo/PHC)
