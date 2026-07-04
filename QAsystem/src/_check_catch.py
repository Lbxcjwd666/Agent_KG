with open(r'd:\Inovation\TCM-QAsystem\QAsystem\src\app_agent.py', 'r', encoding='utf-8') as f:
    content = f.read()

start_marker = '_DEBUG_HTML = r"""'
start_idx = content.index(start_marker) + len(start_marker)
end_idx = content.index('"""', start_idx)
html = content[start_idx:end_idx]

script_start = html.index('<script>')
script_end = html.index('</script>')
js = html[script_start + len('<script>'):script_end]

catch_idx = js.index('} catch (e) {')
before_catch = js[max(0, catch_idx-200):catch_idx+20]

print("=== 200 chars before '} catch' ===")
print(before_catch)
print()

lines_before = before_catch.split('\n')
for i, line in enumerate(lines_before):
    print(f"  {i}: {line}")