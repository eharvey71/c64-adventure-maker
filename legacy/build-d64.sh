#!/bin/bash

# Build C64 Adventure D64

echo "Tokenizing BASIC..."
/Applications/vice-arm64-gtk3-3.8/bin/petcat -w2 -o advplay.prg -- advplay-c64-current.bas

echo "Converting adventure file to C64 format..."
python3 << 'EOF'
with open('castle-c64-current.adv', 'r') as f:
    content = f.read()
with open('castle-c64.adv', 'wb') as f:
    for line in content.split('\n'):
        line = line.rstrip()
        if line:
            f.write(line.encode('ascii') + b'\r')
EOF

echo "Creating D64 disk image..."
rm -f adventure.d64
/Applications/vice-arm64-gtk3-3.8/bin/c1541 -format "adventure,01" d64 adventure.d64 \
  -write advplay.prg advplay,p \
  -write castle-c64.adv "castle.adv,s"

echo "Verifying D64..."
/Applications/vice-arm64-gtk3-3.8/bin/c1541 -attach adventure.d64 -list

echo "Done! adventure.d64 ready to use."