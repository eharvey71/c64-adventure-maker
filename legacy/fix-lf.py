with open("castle-c64-CURRENT.adv", "r") as f:
    content = f.read()

with open("castle-c64.adv", "wb") as f:
    for line in content.split("\n"):
        line = line.rstrip()
        if line:
            f.write(line.encode("ascii") + b"\r")
