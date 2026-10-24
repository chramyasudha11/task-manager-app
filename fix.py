import re

def fix(m):
    chunk = m.group(0)
    try:
        raw = bytearray()
        for c in chunk:
            try:
                raw += c.encode("cp1252")
            except UnicodeEncodeError:
                raw += c.encode("latin-1")
        return raw.decode("utf-8")
    except Exception:
        return chunk

for path in ["app.js", "productivity_ui.js"]:
    try:
        s = open(path, encoding="utf-8").read()
    except FileNotFoundError:
        print("not found:", path)
        continue
    s = re.sub(r"[^\x00-\x7f]+", fix, s)
    open(path, "w", encoding="utf-8", newline="").write(s)
    print("fixed", path)