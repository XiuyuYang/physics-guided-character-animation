param(
    [Parameter(Mandatory = $true)]
    [string]$ContentExamples,
    [string]$UnrealRoot = (Join-Path $env:ProgramFiles 'Epic Games/UE_5.8'),
    [string]$Python = 'python'
)

$ErrorActionPreference = 'Stop'
$project = Join-Path $PSScriptRoot 'Unreal/BoulderCrowd'
$mannequins = Join-Path (Resolve-Path -LiteralPath $ContentExamples).Path 'Content/Characters/Mannequins'
$editor = Join-Path $UnrealRoot 'Engine/Binaries/Win64/UnrealEditor-Cmd.exe'
if (-not (Test-Path -LiteralPath $editor -PathType Leaf)) {
    throw 'Set -UnrealRoot to your Unreal Engine 5.8 installation.'
}
foreach ($asset in @('Meshes/SKM_Manny_Simple.uasset', 'Animations/Manny/MM_Run_Fwd.uasset')) {
    if (-not (Test-Path -LiteralPath (Join-Path $mannequins $asset) -PathType Leaf)) {
        throw "Use the root of the Epic Content Examples project for UE 5.8. Missing $asset."
    }
}
$pythonPath = (Get-Command $Python -CommandType Application).Source
& $pythonPath -c 'import numpy, scipy'
if ($LASTEXITCODE -ne 0) {
    throw 'Install Python dependencies using python -m pip install -r requirements.txt.'
}

$characters = Join-Path $project 'Content/Characters'
New-Item -ItemType Directory -Force -Path $characters | Out-Null
Copy-Item -LiteralPath $mannequins -Destination $characters -Recurse -Force
$script = (Join-Path $project 'Scripts/build_showcase.py').Replace('\', '/')
$previousPython = $env:PGCA_BUILD_PYTHON
try {
    $env:PGCA_BUILD_PYTHON = $pythonPath
    $process = Start-Process -FilePath $editor -ArgumentList @(
        ('"{0}"' -f (Join-Path $project 'BoulderCrowd.uproject')),
        '-run=pythonscript',
        ('-script="{0}"' -f $script),
        '-unattended',
        '-nullrhi'
    ) -PassThru -Wait
    if ($process.ExitCode -ne 0) {
        throw "Unreal asset build exited with code $($process.ExitCode). See Unreal/BoulderCrowd/Saved/Logs/BoulderCrowd.log."
    }
} finally {
    $env:PGCA_BUILD_PYTHON = $previousPython
}

foreach ($map in @('L_Recovery_250', 'L_Recovery_700', 'L_Contact_250', 'L_Contact_700', 'L_BoulderCrowd', 'L_Pulse', 'L_Dart')) {
    if (-not (Test-Path -LiteralPath (Join-Path $project "Content/BoulderDemo/$map.umap") -PathType Leaf)) {
        throw "Unreal did not generate $map."
    }
}
Write-Output 'Open Unreal/BoulderCrowd/BoulderCrowd.uproject and press Play.'
