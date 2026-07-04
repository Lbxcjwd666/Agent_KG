import re
with open(r'd:\Inovation\TCM-QAsystem\QAsystem\src\app_agent.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

in_func = False
depth = 0
for i, line in enumerate(lines[1969:2145], start=1970):
    stripped = line.strip()
    if 'async function runDebug' in stripped:
        in_func = True
    if not in_func:
        continue
    for ch in stripped:
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
    print(f'L{i} depth={depth:+d}  {stripped[:90]}')
    if in_func and depth == 0 and 'function runDebug' not in stripped:
        print('=== FUNCTION ENDS HERE ===')
        break