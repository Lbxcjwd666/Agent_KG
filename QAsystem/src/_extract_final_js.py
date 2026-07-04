with open(r'd:\Inovation\TCM-QAsystem\QAsystem\src\_visualize_final.html', 'r', encoding='utf-8') as f:
    html = f.read()

script_start = html.index('<script>')
script_end = html.index('</script>')
js = html[script_start + len('<script>'):script_end]

with open(r'd:\Inovation\TCM-QAsystem\QAsystem\src\_visualize_final.js', 'w', encoding='utf-8') as f:
    f.write(js)

print(f"JS: {len(js)} chars, {js.count(chr(10))} lines")