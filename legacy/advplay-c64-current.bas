1 rem *** adventure player for commodore 64 ***
2 rem converted from picomite version
3 rem uses : as delimiter (not pipe)
4 rem enhanced with use command and responses
5 rem
6 rem *** array declarations ***
10 dim r$(20,4):rem rooms: name,desc,exits,flags
20 dim o$(30,4):rem objects: name,room,desc,flags
30 dim i$(10):rem inventory
40 dim v$(20,2):rem vocabulary: word,synonyms
50 dim m$(10,1):rem messages: key,text
60 dim f$(10):rem game flags
65 dim rs$(20,3):rem responses: cmd,condition,msg,action
70 rem
80 rem *** game variables ***
90 gt$="":ga$="":gv$="":rem game title,author,version
100 cr=0:ic=0:sc=0:ms=100:sr=1:rem current room,inv count,score,max,start
110 nr=0:no=0:nv=0:nm=0:nf=0:rem num rooms,objs,vocab,msgs,flags
115 nq=0:rem num responses
120 rem
130 rem *** parsing variables ***
140 c$="":o$="":f=0:n=0:rem command,object,found,new room
150 dl$=":":rem delimiter character
160 rem
170 rem *** main program ***
180 print chr$(147):rem clear screen
190 print "adventure player for c64"
200 print:print "adventure file to load:"
210 input f$
220 if f$="" then print "no file. goodbye!":end
230 if len(f$)<4 or right$(f$,4)<>".adv" then f$=f$+".adv"
240 gosub 1000:rem load file
250 gosub 5000:rem start game
260 end
270 rem
1000 rem *** load adventure file ***
1010 print:print "loading ";f$;"..."
1020 open 1,8,2,f$
1030 se$="":l=0:rem section,line count
1040 rem
1050 rem *** read file line by line ***
1060 if st<>0 then 1900:rem end of file
1070 l$="":rem line buffer
1080 get#1,a$
1082 if a$=chr$(13) then 1100
1084 if a$<>"" then l$=l$+a$
1086 if st=0 then 1080
1088 if l$="" then 1900
1100 l=l+1
1110 rem trim spaces
1120 if left$(l$,1)=" " and len(l$)>0 then l$=mid$(l$,2):goto 1120
1130 if right$(l$,1)=" " and len(l$)>0 then l$=left$(l$,len(l$)-1):goto 1130
1140 rem
1150 rem skip comments and blank lines
1160 if left$(l$,1)="#" or l$="" then 1060
1170 rem
1180 rem check for section header
1190 if left$(l$,1)="[" and right$(l$,1)="]" then se$=mid$(l$,2,len(l$)-2):print se$:goto 1060
1200 rem
1210 rem parse by section
1220 if se$="settings" then gosub 2000:goto 1060
1230 if se$="rooms" then gosub 2500:goto 1060
1240 if se$="objects" then gosub 3000:goto 1060
1250 if se$="vocabulary" then gosub 3500:goto 1060
1260 if se$="messages" then gosub 4000:goto 1060
1265 if se$="responses" then gosub 4500:goto 1060
1270 goto 1060
1280 rem
1900 rem *** close file ***
1910 close 1
1920 cr=sr:rem set current room to start
1930 print:print "loaded ";l;" lines"
1940 print "rooms:";nr;" objects:";no
1945 print "responses:";nq
1950 print "vocab:";nv;" messages:";nm
1960 print:return
1970 rem
2000 rem *** parse settings ***
2010 p=1:rem find = sign
2020 for i=1 to len(l$)
2030   if mid$(l$,i,1)="=" then p=i:i=len(l$)
2040 next i
2050 if p=1 then return:rem no = found
2055 rem extract key and value
2060 k$=left$(l$,p-1)
2065 v$=""
2070 for i=p+1 to len(l$)
2072   v$=v$+mid$(l$,i,1)
2074 next i
2078 rem check key and set variables
2080 if k$="title" then gt$=v$
2081 if k$="author" then ga$=v$
2082 if k$="version" then gv$=v$
2083 if k$="startroom" then sr=val(v$)
2084 if k$="maxscore" then ms=val(v$)
2085 if k$="winmessage" then gw$=v$
2090 return
2130 rem
2500 rem *** parse rooms ***
2509 if l$="" then return
2510 nr=nr+1:if nr>20 then return
2520 rem format: id:name:desc:exits:flags
2530 p1=1:p2=1:fi=0:rem positions,field
2540 for i=1 to len(l$)
2550   if mid$(l$,i,1)=dl$ then p2=i:gosub 2600:p1=p2+1:fi=fi+1
2560 next i
2570 rem last field
2580 p2=len(l$)+1:gosub 2600
2590 return
2600 rem extract field
2610 t$=mid$(l$,p1,p2-p1)
2620 if fi=0 then ri=val(t$):rem room id
2630 if fi=1 then r$(ri,0)=t$:rem name
2640 if fi=2 then r$(ri,1)=t$:rem description
2650 if fi=3 then r$(ri,2)=t$:rem exits
2660 if fi=4 then r$(ri,3)=t$:rem flags
2670 return
2680 rem
3000 rem *** parse objects ***
3009 if l$="" then return
3010 no=no+1:if no>30 then return
3020 rem format: id:room:name:desc:flags
3030 p1=1:p2=1:fi=0
3040 for i=1 to len(l$)
3050   if mid$(l$,i,1)=dl$ then p2=i:gosub 3100:p1=p2+1:fi=fi+1
3060 next i
3070 p2=len(l$)+1:gosub 3100
3080 return
3100 rem extract field
3110 t$=mid$(l$,p1,p2-p1)
3120 if fi=0 then o$(no,0)=t$:rem id/name
3130 if fi=1 then o$(no,1)=t$:rem room
3140 if fi=2 then rem skip display name
3150 if fi=3 then o$(no,2)=t$:rem description
3160 if fi=4 then o$(no,3)=t$:rem flags
3170 return
3180 rem
3500 rem *** parse vocabulary ***
3509 if l$="" then return
3510 nv=nv+1:if nv>20 then return
3520 rem format: word=synonyms
3530 p=1
3540 for i=1 to len(l$)
3550   if mid$(l$,i,1)="=" then p=i:i=len(l$)
3560 next i
3570 if p=1 then return
3580 v$(nv,0)=left$(l$,p-1)
3590 v$(nv,1)=mid$(l$,p+1)
3600 return
3610 rem
4000 rem *** parse messages ***
4009 if l$="" then return
4010 nm=nm+1:if nm>10 then return
4020 rem format: key=message
4030 p=1
4040 for i=1 to len(l$)
4050   if mid$(l$,i,1)="=" then p=i:i=len(l$)
4060 next i
4070 if p=1 then return
4080 m$(nm,0)=left$(l$,p-1)
4090 m$(nm,1)=mid$(l$,p+1)
4100 return
4110 rem
4500 rem *** parse responses ***
4509 if l$="" then return
4510 nq=nq+1:if nq>20 then return
4520 rem format: cmd:condition:msg:action
4530 p1=1:p2=1:fi=0
4540 for i=1 to len(l$)
4550   if mid$(l$,i,1)=dl$ then p2=i:gosub 4600:p1=p2+1:fi=fi+1
4560 next i
4570 p2=len(l$)+1:gosub 4600
4580 return
4600 rem extract response field
4610 t$=mid$(l$,p1,p2-p1)
4620 if fi=0 then rs$(nq,0)=t$:rem command
4630 if fi=1 then rs$(nq,1)=t$:rem condition
4640 if fi=2 then rs$(nq,2)=t$:rem message
4650 if fi=3 then rs$(nq,3)=t$:rem action
4660 return
4670 rem
5000 rem *** start game ***
5010 rem print chr$(147):rem clear screen
5020 print "==================================="
5025 if gt$<>"" then print gt$
5026 if gt$="" then print "(untitled adventure)"
5030 if ga$<>"" then print "by ";ga$
5035 if gv$<>"" then print "version ";gv$
5040 print "==================================="
5050 print
5080 gosub 6000:rem show room
5090 rem
5100 rem *** main game loop ***
5110 print
5115 print ">";
5120 c$=""
5125 get k$:if k$="" then 5125
5127 if k$=chr$(20) then if len(c$)>0 then c$=left$(c$,len(c$)-1):print chr$(20);" ";chr$(20);:goto 5125
5130 if k$=chr$(13) then print:goto 5140
5135 if k$<chr$(32) then 5125
5137 c$=c$+k$:print k$;:goto 5125
5140 rem execution continues here
5150 rem normalize command to uppercase
5160 gosub 7000:rem to uppercase
5170 c$=uc$:rem **C$ is now ALL UPPERCASE**
5175 gosub 7100:rem expand vocabulary synonyms
5180 rem
5190 rem check for basic commands
5200 if c$="quit" or c$="q" then input "really (y or n)";b$
5201 if left$(b$,1) = "y" then print "goodbye!":end
5202 if c$="quit" or c$="q" then goto 5110
5210 if c$="inventory" or c$="i" then gosub 8000:goto 5110
5220 if c$="look" or c$="l" then gosub 6000:goto 5110
5230 if c$="score" then print "score:";sc;" of";ms:goto 5110
5240 if c$="help" or c$="?" then gosub 8500:goto 5110
5250 rem
5260 rem check for movement
5270 if c$="n" or c$="north" then d=1:gosub 9000:goto 5110
5280 if c$="s" or c$="south" then d=2:gosub 9000:goto 5110
5290 if c$="e" or c$="east" then d=3:gosub 9000:goto 5110
5300 if c$="w" or c$="west" then d=4:gosub 9000:goto 5110
5310 rem
5320 rem check for take/drop
5330 if left$(c$,4)="take" or left$(c$,3)="get" then gosub 10000:goto 5110
5340 if left$(c$,4)="drop" then gosub 11000:goto 5110
5350 rem
5360 rem check for examine
5370 if left$(c$,7)="examine" or left$(c$,4)="look" then gosub 12000:goto 5110
5380 rem
5385 rem check for use command
5390 if left$(c$,4)="use " then gosub 13000:goto 5110
5395 rem
5400 rem unknown command
5410 print "i don't understand that."
5420 goto 5110
5430 rem
6000 rem *** show room ***
6010 print:print r$(cr,0):rem room name
6020 print r$(cr,1):rem description
6030 rem
6040 rem show objects in room
6050 for i=1 to no
6060   if val(o$(i,1))=cr then print "you see: ";o$(i,0)
6070 next i
6080 rem
6090 rem show exits
6100 e$=r$(cr,2):rem exits string
6110 gosub 6250:rem parse exits
6120 print "exits:";
6130 x=0:rem count exits
6140 if en>0 then print " north";:x=x+1
6150 if es>0 then if x>0 then print ",";
6160 if es>0 then print " south";:x=x+1
6170 if ee>0 then if x>0 then print ",";
6180 if ee>0 then print " east";:x=x+1
6190 if ew>0 then if x>0 then print ",";
6200 if ew>0 then print " west";:x=x+1
6210 if x=0 then print " none"
6220 print
6230 return
6240 rem
6250 rem *** parse exits (n,s,e,w) ***
6260 en=0:es=0:ee=0:ew=0:p=1:fi=0
6270 for i=1 to len(e$)
6280   if mid$(e$,i,1)="," then gosub 6340:fi=fi+1:p=i+1
6290 next i
6300 rem last exit
6310 gosub 6340
6320 return
6330 rem
6340 rem extract exit
6350 t$=mid$(e$,p,i-p)
6360 v=val(t$)
6370 if fi=0 then en=v:rem north
6380 if fi=1 then es=v:rem south
6390 if fi=2 then ee=v:rem east
6400 if fi=3 then ew=v:rem west
6410 return
6420 rem
7000 rem *** convert string to uppercase ***
7010 uc$=""
7020 for i=1 to len(c$)
7030   a$=mid$(c$,i,1)
7040   a=asc(a$)
7050   if a>=97 and a<=122 then a=a-32:rem a-z
7060   uc$=uc$+chr$(a)
7070 next i
7080 return
7090 rem
7100 rem *** expand first word via vocabulary ***
7105 rem maps a synonym onto its canonical word, so a game's
7106 rem [vocabulary] table finally has an effect here.
7110 if nv=0 then return
7115 sp=0
7120 for i=1 to len(c$)
7125   if mid$(c$,i,1)=" " then sp=i:i=len(c$)
7130 next i
7135 if sp=0 then fw$=c$:rw$=""
7140 if sp>0 then fw$=left$(c$,sp-1):rw$=mid$(c$,sp)
7145 rem walk the table looking for the typed word
7150 for i=1 to nv
7155   if v$(i,0)=fw$ then return:rem already canonical
7160   sy$=v$(i,1)+","
7165   pv=1
7170   for j=1 to len(sy$)
7175     if mid$(sy$,j,1)<>"," then 7190
7180     tw$=mid$(sy$,pv,j-pv)
7185     if tw$=fw$ then c$=v$(i,0)+rw$:return
7188     pv=j+1
7190   next j
7195 next i
7198 return
7199 rem
8000 rem *** show inventory ***
8010 print:print "you are carrying:"
8020 if ic=0 then print "nothing":return
8030 for i=1 to no
8040   if o$(i,1)="-1" then print "  ";o$(i,0)
8050 next i
8060 return
8070 rem
8500 rem *** show help ***
8510 print:print "available commands:"
8520 print "  n,s,e,w - move"
8530 print "  take/get [object]"
8540 print "  drop [object]"
8545 print "  use [object] [on object]"
8550 print "  examine/look [object]"
8560 print "  inventory (i)"
8570 print "  look (l)"
8580 print "  score"
8590 print "  quit (q)"
8600 return
8610 rem
9000 rem *** move in direction d ***
9010 e$=r$(cr,2):gosub 6250:rem parse exits
9020 n=0:rem new room
9030 if d=1 then n=en:rem north
9040 if d=2 then n=es:rem south
9050 if d=3 then n=ee:rem east
9060 if d=4 then n=ew:rem west
9070 if n>0 then cr=n:gosub 6000:return
9080 print "you can't go that way."
9090 return
9100 rem
10000 rem *** take object ***
10010 rem extract object name
10020 if len(c$)<=5 then print "take what?":return
10030 if left$(c$,4)="take" then o$=mid$(c$,6)
10040 if left$(c$,3)="get" then o$=mid$(c$,5)
10050 rem
10060 rem find object in room
10070 f=0:rem found flag
10080 for i=1 to no
10090   if val(o$(i,1))=cr then gosub 10150
10100 next i
10110 if f=0 then print "i don't see that here."
10120 return
10130 rem
10150 rem check if name matches
10160 if o$(i,0)<>"" then if left$(o$(i,0),len(o$))=o$ then f=1:gosub 10200:i=30
10170 return
10180 rem
10200 rem take the object
10210 rem check if takeable
10220 if o$(i,3)<>"takeable" then print "you can't take that.":return
10230 o$(i,1)="-1":rem move to inventory
10240 ic=ic+1
10250 print "taken."
10260 return
10270 rem
11000 rem *** drop object ***
11010 if len(c$)<=5 then print "drop what?":return
11020 o$=mid$(c$,6)
11030 rem
11040 rem find object in inventory
11050 f=0
11060 for i=1 to no
11070   if o$(i,1)="-1" then gosub 11120
11080 next i
11090 if f=0 then print "you don't have that."
11100 return
11110 rem
11120 rem check if name matches
11130 if o$(i,0)<>"" then if left$(o$(i,0),len(o$))=o$ then f=1:gosub 11170:i=30
11140 return
11150 rem
11170 rem drop the object
11180 o$(i,1)=str$(cr):rem move to current room
11190 ic=ic-1
11200 print "dropped."
11210 return
11220 rem
12000 rem *** examine object ***
12010 if len(c$)<=8 then print "examine what?":return
12020 if left$(c$,7)="examine" then o$=mid$(c$,9)
12030 if left$(c$,4)="look" then o$=mid$(c$,9)
12040 rem
12050 rem find object (in room or inventory)
12060 f=0
12070 for i=1 to no
12080   if val(o$(i,1))=cr or o$(i,1)="-1" then gosub 12130
12090 next i
12100 if f=0 then print "i don't see that."
12110 return
12120 rem
12130 rem check if name matches
12140 if o$(i,0)<>"" then if left$(o$(i,0),len(o$))=o$ then f=1:gosub 12180:i=30
12150 return
12160 rem
12180 rem show description
12190 print o$(i,2)
12200 return
12210 rem
13000 rem *** use command ***
13010 if len(c$)<=4 then print "use what?":return
13020 t$=mid$(c$,5):rem get rest of command
13030 rem
13040 rem check for "on" or "with"
13050 p=0:rem position of on/with
13060 for i=1 to len(t$)-3
13070   if mid$(t$,i,4)=" on " then p=i:i=len(t$)
13080 next i
13090 if p<>0 then 13130
13100 for i=1 to len(t$)-5
13110   if mid$(t$,i,6)=" with " then p=i:i=len(t$)
13120 next i
13130 if p>0 then goto 13200:rem two objects
13140 rem
13150 rem single object use
13160 o$=t$
13170 c2$="use "+o$:rem normalized command
13180 goto 13300
13190 rem
13200 rem two object use
13210 o$=left$(t$,p-1):rem first object
13220 o2$=mid$(t$,p+4):rem skip " on "
13230 if left$(o2$,1)=" " then o2$=mid$(o2$,2):rem trim space
13240 if mid$(t$,p,6)=" with " then o2$=mid$(t$,p+6)
13250 c2$="use "+o$+" "+o2$:rem normalized
13260 rem
13300 rem *** check responses ***
13310 f=0:rem found flag
13320 for i=1 to nq
13330   if rs$(i,0)<>"" then gosub 13400
13335   if f=1 then i=nq:rem exit if found
13340 next i
13350 if f=0 then print "nothing happens."
13360 return
13370 rem
13400 rem *** check single response ***
13410 rem check if command matches
13420 rc$=rs$(i,0):rem response command
13430 rem simple substring match
13440 if len(rc$)>len(c2$) then return
13450 rem check if rc$ is in c2$
13460 m=0
13470 for j=1 to len(c2$)-len(rc$)+1
13480   if mid$(c2$,j,len(rc$))=rc$ then m=1:j=len(c2$)
13490 next j
13500 if m=0 then return:rem no match
13510 rem
13520 rem check condition
13530 co$=rs$(i,1):rem condition
13540 co=1:rem condition result
13550 if co$<>"" then gosub 14000
13560 if co=0 then return:rem condition failed
13570 rem
13580 rem show message
13590 if rs$(i,2)<>"" then print rs$(i,2)
13600 rem
13610 rem execute action
13620 if rs$(i,3)<>"" then ac$=rs$(i,3):gosub 15000
13630 f=1:rem mark as found
13650 return
13660 rem
14000 rem *** evaluate condition ***
14010 rem simple conditions only
14020 co=1:rem condition result (default true)
14030 rem
14040 rem check for "has object"
14050 if left$(co$,4)="has " then goto 14100
14060 rem
14070 rem check for flag
14080 if left$(co$,5)="flag." then goto 14200
14090 return
14100 rem *** has object condition ***
14110 ob$="":for k=5 to len(co$):ob$=ob$+mid$(co$,k,1):next k
14120 co=0:rem default false
14130 for j=1 to no
14140   if o$(j,1)="-1" then if left$(o$(j,0),len(ob$))=ob$ then co=1:j=no
14150 next j
14160 return
14170 rem
14200 rem *** flag condition ***
14210 fl$="":for k=6 to len(co$):fl$=fl$+mid$(co$,k,1):next k
14220 co=0:rem default false
14230 for j=1 to nf
14240   if f$(j)=fl$ then co=1:j=nf
14250 next j
14260 return
14270 rem
15000 rem *** execute action ***
15010 rem simple actions only
15020 rem
15030 rem check for "unlock"
15040 if left$(ac$,7)="unlock " then goto 15300
15050 rem
15060 rem check for "move to"
15070 if left$(ac$,8)="move to " then goto 15100
15080 rem check for "set flag"
15085 if left$(ac$,9)="set flag." then goto 15200
15086 rem check for "win"
15087 if left$(ac$,3)="win" then goto 15900
15088 rem check for "score"
15089 if left$(ac$,6)="score " then goto 16000
15090 return
15100 rem *** move to room ***
15110 t$="":for k=9 to len(ac$):t$=t$+mid$(ac$,k,1):next k
15115 rn=val(t$):rem room number
15120 cr=rn
15130 gosub 6000:rem show new room
15140 return
15150 rem
15200 rem *** set flag ***
15210 fl$="":for k=10 to len(ac$):fl$=fl$+mid$(ac$,k,1):next k
15220 rem check if flag already exists
15230 for j=1 to nf
15240   if f$(j)=fl$ then return:rem already set
15250 next j
15260 rem add new flag
15270 if nf<10 then nf=nf+1:f$(nf)=fl$
15280 return
15290 rem
15300 rem *** unlock exit ***
15310 rem format: unlock direction room to dest
15320 rem example: unlock west 2 to 6
15330 rem
15340 rem extract direction
15350 dr=0:rp=0
15360 if mid$(ac$,8,5)="north" then dr=1:rp=14
15370 if mid$(ac$,8,5)="south" then dr=2:rp=14
15380 if mid$(ac$,8,4)="east" then dr=3:rp=13
15390 if mid$(ac$,8,4)="west" then dr=4:rp=13
15400 rem dr=direction 1-4, rp=pos after dir
15410 rem
15420 rem extract room number
15430 rm$=""
15440 for k=rp to len(ac$)
15450   if mid$(ac$,k,1)>="0" and mid$(ac$,k,1)<="9" then rm$=rm$+mid$(ac$,k,1)
15460   if mid$(ac$,k,1)=" " and rm$<>"" then k=len(ac$)
15470 next k
15480 rm=val(rm$)
15490 rem
15500 rem find " to " and extract dest
15510 tp=0
15520 for k=rp to len(ac$)-3
15530   if mid$(ac$,k,4)=" to " then tp=k+4:k=len(ac$)
15540 next k
15550 ds$=""
15560 for k=tp to len(ac$)
15570   if mid$(ac$,k,1)>="0" and mid$(ac$,k,1)<="9" then ds$=ds$+mid$(ac$,k,1)
15580 next k
15590 ds=val(ds$)
15600 rem
15610 rem get current exits for room rm
15620 e$=r$(rm,2)
15630 rem
15640 rem parse exits: n,s,e,w
15650 en=0:es=0:ee=0:ew=0:p=1:fi=0
15660 for k=1 to len(e$)
15670   if mid$(e$,k,1)="," then gosub 15780:fi=fi+1:p=k+1
15680 next k
15690 gosub 15780:rem last exit
15700 rem
15710 rem update the specified direction
15720 if dr=1 then en=ds
15730 if dr=2 then es=ds
15740 if dr=3 then ee=ds
15750 if dr=4 then ew=ds
15760 rem
15770 rem rebuild and store exits string
15775 r$(rm,2)=str$(en)+","+str$(es)+","+str$(ee)+","+str$(ew)
15777 return
15780 rem
15790 rem *** parse single exit value ***
15800 t$=""
15810 for l=p to k-1
15820   t$=t$+mid$(e$,l,1)
15830 next l
15840 v=val(t$)
15850 if fi=0 then en=v
15860 if fi=1 then es=v
15870 if fi=2 then ee=v
15880 if fi=3 then ew=v
15890 return
15900 rem *** win the game ***
15910 if gw$<>"" then print gw$
15920 if gw$="" then print "congratulations! you have won!"
15930 print "final score:";sc;" of";ms
15940 print
15950 print "the end."
15960 end
16000 rem *** add to score ***
16010 rem format: score nnn
16020 t$=""
16030 for k=7 to len(ac$)
16040   if mid$(ac$,k,1)>="0" and mid$(ac$,k,1)<="9" then t$=t$+mid$(ac$,k,1)
16050 next k
16060 sc=sc+val(t$)
16070 return
