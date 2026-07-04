with open(r'd:\Inovation\TCM-QAsystem\QAsystem\src\app_agent.py', 'r', encoding='utf-8') as f:
    content = f.read()

start_marker = '_DEBUG_HTML = r"""'
start_idx = content.index(start_marker) + len(start_marker)
end_idx = content.index('"""', start_idx)
html = content[start_idx:end_idx]

script_start = html.index('<script>')
script_end = html.index('</script>')
js_from_string = html[script_start + len('<script>'):script_end]

with open(r'd:\Inovation\TCM-QAsystem\QAsystem\src\_debug_check.js', 'r', encoding='utf-8') as f:
    js_from_file = f.read()

print(f"From _DEBUG_HTML string: {len(js_from_string)} chars, {js_from_string.count(chr(10))} lines")
print(f"From _debug_check.js:    {len(js_from_file)} chars, {js_from_file.count(chr(10))} lines")
print(f"Match: {js_from_string == js_from_file}")

if js_from_string != js_from_file:
    for i, (c1, c2) in enumerate(zip(js_from_string, js_from_file)):
        if c1 != c2:
            print(f"First diff at char {i}: string='{c1}' ({ord(c1)}), file='{c2}' ({ord(c2)})")
            print(f"  Context string: ...{js_from_string[max(0,i-20):i+20]}...")
            print(f"  Context file:    ...{js_from_file[max(0,i-20):i+20]}...")
            break
    if len(js_from_string) != len(js_from_file):
        print(f"Length diff: string={len(js_from_string)}, file={len(js_from_file)}")