from pathlib import Path

for v in ['baseline', 'token_guard']:
    p = Path(f'benchmarks/blackbox_benchmark/variants/{v}/test_blackbox.py')
    text = p.read_text()
    old = 'str(Path(__file__).parent.parent / "buggy_codebase")'
    new = 'str(Path(__file__).parent)'
    text = text.replace(old, new)
    p.write_text(text)
    print(f'Fixed {v}')
