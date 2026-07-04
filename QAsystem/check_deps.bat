@echo off
cd /d d:\Inovation\TCM-QAsystem\QAsystem\src
set PYTHONPATH=d:\Inovation\TCM-QAsystem\QAsystem\src
D:\Install\miniconda3\envs\QA-system\python.exe -c "import flask; import flask_cors; import neo4j; import openai; print('All dependencies OK'); print('Flask:', flask.__version__)" > d:\Inovation\TCM-QAsystem\QAsystem\dep_check.txt 2>&1