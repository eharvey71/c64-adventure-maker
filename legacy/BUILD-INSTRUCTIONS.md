# Building C64 Adventure D64 from macOS

## Prerequisites

Install the required tools using Homebrew:

```bash
brew install vice
```

This installs:

- `petcat` - BASIC tokenizer
- `c1541` - D64 disk image creator

On my MacOS, petcat is in `/Applications/vice-arm64-gtk3-3.8/bin` since I installed using the installer from VICE directly. Currently not the PATH, so I'm using the full path when running `/Applications/vice-arm64-gtk3-3.8/bin/petcat`

## Files Needed

- `advplay-lowercase.bas` - Adventure player BASIC source (lowercase)
- `castle.adv` - Adventure data file (text format)

## Build Steps

### 1. Tokenize the BASIC Program

Convert the ASCII BASIC source to a tokenized `.prg` file:

```bash
petcat -w2 -o advplay.prg -- advplay-lowercase.bas
```

**Important:** The BASIC source must be in lowercase for `petcat` to tokenize correctly.

### 2. Convert Adventure File to C64 Format

The adventure file needs CR (carriage return) line endings instead of LF:

```bash
python3 << 'EOF'
with open('castle.adv', 'r') as f:
    content = f.read()

with open('castle-c64.adv', 'wb') as f:
    for line in content.split('\n'):
        line = line.rstrip()
        if line:
            f.write(line.encode('ascii') + b'\r')
EOF
```

### 3. Create the D64 Disk Image

Create a formatted D64 and add both files:

```bash
c1541 -format "adventure,01" d64 adventure.d64 \
  -write advplay.prg advplay,p \
  -write castle-c64.adv "castle.adv,s"
```

### 4. Verify the D64

Check the disk directory:

```bash
c1541 -attach adventure.d64 -list
```

You should see:

```
0 "adventure       " 01 2a
54   "advplay"          prg
7    "castle.adv"       seq
603 blocks free.
```

## Complete Build Script

Save this as `build.sh`:

```bash
#!/bin/bash

# Build C64 Adventure D64

echo "Tokenizing BASIC..."
petcat -w2 -o advplay.prg -- advplay-lowercase.bas

echo "Converting adventure file to C64 format..."
python3 << 'EOF'
with open('castle.adv', 'r') as f:
    content = f.read()
with open('castle-c64.adv', 'wb') as f:
    for line in content.split('\n'):
        line = line.rstrip()
        if line:
            f.write(line.encode('ascii') + b'\r')
EOF

echo "Creating D64 disk image..."
rm -f adventure.d64
c1541 -format "adventure,01" d64 adventure.d64 \
  -write advplay.prg advplay,p \
  -write castle-c64.adv "castle.adv,s"

echo "Verifying D64..."
c1541 -attach adventure.d64 -list

echo "Done! adventure.d64 ready to use."
```

Make it executable:

```bash
chmod +x build.sh
```

Run it:

```bash
./build.sh
```

## Loading on C64/VICE

1. Load the D64 in VICE or transfer to real C64
2. Type: `LOAD "ADVPLAY",8`
3. Type: `RUN`
4. When prompted for adventure file, enter: `CASTLE.ADV`

## Troubleshooting

**petcat not found:**

```bash
which petcat
# Should show: /usr/local/bin/petcat or /opt/homebrew/bin/petcat
```

**Wrong tokenization:**

- Ensure BASIC source is lowercase
- Check that `petcat` is from VICE (not another tool)

**D64 won't load:**

- Verify files exist before creating D64
- Check file sizes (advplay.prg should be ~13-14KB)
- Try recreating with `rm -f adventure.d64` first

**Adventure file not found:**

- File must be named with `.adv` extension on the D64
- Use exact case: `CASTLE.ADV` (uppercase on C64)
