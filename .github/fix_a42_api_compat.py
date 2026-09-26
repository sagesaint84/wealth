from pathlib import Path

path = Path("app/main.py")
source = path.read_text(encoding="utf-8")
old = """            high_dividend_scenario=high_dividend_scenario,
            investment_scenario=investment_scenario,
"""
new = """            investment_scenario=investment_scenario,
            **(
                {"high_dividend_scenario": high_dividend_scenario}
                if high_dividend_scenario is not None
                else {}
            ),
"""
count = source.count(old)
if count != 1:
    raise SystemExit(f"expected one forwarding block, found {count}")
path.write_text(source.replace(old, new, 1), encoding="utf-8")
