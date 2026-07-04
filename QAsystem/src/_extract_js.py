import sys

with open(r'd:\Inovation\TCM-QAsystem\QAsystem\src\app_agent.py', 'r', encoding='utf-8') as f:
    content = f.read()

start_marker = '_DEBUG_HTML = r"""'
start_idx = content.index(start_marker) + len(start_marker)
end_idx = content.index('"""', start_idx)
html = content[start_idx:end_idx]

script_start = html.index('<script>')
script_end = html.index('</script>')
js = html[script_start + len('<script>'):script_end]

with open(r'd:\Inovation\TCM-QAsystem\QAsystem\src\_debug_check.js', 'w', encoding='utf-8') as f:
    f.write(js)

print(f"JS extracted: {len(js)} chars, {js.count(chr(10))} lines")

depth = 0
min_depth = 0
min_depth_line = 0
lines = js.split('\n')
for i, line in enumerate(lines, 1):
    for ch in line:
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
    if depth < min_depth:
        min_depth = depth
        min_depth_line = i
    if depth < 0:
        print(f"  NEGATIVE at JS line {i}: depth={depth}, line: {line.strip()[:60]}")

print(f"Final depth: {depth}, Min depth: {min_depth} at line {min_depth_line}")