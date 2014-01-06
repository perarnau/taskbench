CFLAGS=`pkg-config --cflags kaapi`
LDFLAGS=`pkg-config --libs kaapi`

CFLAGS+= -Og -ggdb3 -std=c99 -Wall -D_GNU_SOURCE -Wextra
LDFLAGS+= -ggdb3 -lrt

%: %.o sha1.o
	$(CC) -o $@ $^ $(LDFLAGS)

sha1.o: sha1.c sha.h
%.o: %.c
	$(CC) $(CFLAGS) -c $<

%.c: %.yaml main.py
	./main.py $< > $@
