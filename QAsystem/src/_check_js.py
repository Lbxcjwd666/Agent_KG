with open(r'd:\Inovation\TCM-QAsystem\QAsystem\src\app_agent.py', 'r', encoding='utf-8') as f:
    content = f.read()

start_marker = '_DEBUG_HTML = r"""'
start_idx = content.index(start_marker) + len(start_marker)
end_idx = content.index('"""', start_idx)
html = content[start_idx:end_idx]

script_start = html.index('<script>')
script_end = html.index('</script>')
js = html[script_start + len('<script>'):script_end]

depth = 0
lines = js.split('\n')
for i, line in enumerate(lines, 1):
    in_string = False
    in_regex = False
    for ch in line:
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
    if depth < 0:
        print(f"!!! NEGATIVE DEPTH at JS line {i}: depth={depth}")
        print(f"   {line.strip()[:80]}")
    if abs(depth) > 10:
        print(f"!!! SUSPICIOUS DEPTH at JS line {i}: depth={depth}")
        print(f"   {line.strip()[:80]}")

print(f"\nFinal depth: {depth}")
if depth != 0:
    print("ERROR: Braces are NOT balanced!")
else:
    print("OK: Braces are balanced.")