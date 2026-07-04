@echo off

REM ============================================
REM 清理干扰环境变量
REM ============================================

REM 清理 API 密钥
set DASHSCOPE_API_KEY=
set OPENAI_API_KEY=
set ANTHROPIC_API_KEY=
set AZURE_OPENAI_KEY=

REM 清理代理相关
set HTTP_PROXY=
set HTTPS_PROXY=
set FTP_PROXY=
set SOCKS_PROXY=
set ALL_PROXY=
set NO_PROXY=
set http_proxy=
set https_proxy=
set ftp_proxy=
set socks_proxy=
set all_proxy=
set no_proxy=

REM 清理 SAFE_RM 工具变量
set SAFE_RM_ALLOWED_PATH=
set SAFE_RM_DENIED_PATH=
set SAFE_RM_PROTECTION_FLAG=
set SAFE_RM_AUTO_ADD_TEMP=

REM 清理 SSL/证书相关
set SSL_CERT_FILE=
set REQUESTS_CA_BUNDLE=
set CURL_CA_BUNDLE=

REM 可选：显示清理后的环境（调试用，正式可删除）
echo ==========================================
echo 环境变量已清理
echo DASHSCOPE_API_KEY=%DASHSCOPE_API_KEY%
echo HTTP_PROXY=%HTTP_PROXY%
echo SAFE_RM_ALLOWED_PATH=%SAFE_RM_ALLOWED_PATH%
echo ==========================================
echo 开始执行主程序...
echo ==========================================

REM ============================================
REM 你的原始代码从这里继续
REM ============================================

REM 例如，你的原始代码可能是：
REM python run_test.py
REM 或其他命令

set PYTHONPATH=d:\Inovation\TCM-QAsystem\QAsystem\src
cd /d d:\Inovation\TCM-QAsystem\QAsystem\src
D:\Install\miniconda3\envs\QA-system\python.exe start_server.py