with open(r'd:\Inovation\TCM-QAsystem\QAsystem\src\_visualize_served.js', 'r', encoding='utf-8') as f:
    lines = f.readlines()

depth = 0
for i, line in enumerate(lines, 1):
    for ch in line:
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
    if 40 <= i <= 180:
        marker = " <<<NEGATIVE" if depth < 0 else ""
        print(f"L{i:3d} d={depth:2d}  {line.rstrip()[:70]}{marker}")