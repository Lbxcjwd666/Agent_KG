$env:PATH = "D:\Install\miniconda3\envs\QA-system;D:\Install\miniconda3\envs\QA-system\Scripts;" + $env:PATH
$python = "D:\Install\miniconda3\envs\QA-system\python.exe"
$srcDir = "d:\Inovation\TCM-QAsystem\QAsystem\src"

Set-Location $srcDir
& $python -c "import sys; sys.path.insert(0, r'$srcDir'); from app import app; print('Import OK')"