KAAPI_CFLAGS=`pkg-config --cflags kaapi`
KAAPI_LDFLAGS=`pkg-config --libs kaapi`

STARPU_CFLAGS=`pkg-config --cflags starpu-1.1`
STARPU_LDFLAGS=`pkg-config --libs starpu-1.1`

OMPSS_CFLAGS=
OMPSS_LDFLAGS=

QUARK_PATH=/home/perarnau/Downloads/quark-0.9.0
QUARK_CFLAGS=-I$(QUARK_PATH)/ `pkg-config --cflags hwloc`
QUARK_LDFLAGS=-L$(QUARK_PATH)/ -lquark -lpthread `pkg-config --libs hwloc`

CFLAGS+= -Og -ggdb3 -std=c99 -Wall -D_GNU_SOURCE -Wextra -Wno-unused-parameter\
	 -Wno-unused-variable
LDFLAGS+= -ggdb3 -lrt

%.kaapi: %.kaapi.o sha1.o
	$(CC) -o $@ $^ $(KAAPI_LDFLAGS) $(LDFLAGS)
%.starpu: %.starpu.o sha1.o
	$(CC) -o $@ $^ $(STARPU_LDFLAGS) $(LDFLAGS)
%.ompss: %.ompss.o sha1.o
	mcc -o $@ $^ $(OMPSS_LDFLAGS) $(LDFLAGS)
%.quark: %.quark.o sha1.o
	$(CC) -o $@ $^ $(QUARK_LDFLAGS) $(LDFLAGS)

sha1.o: sha1.c sha.h

%.kaapi.o: %.kaapi.c
	$(CC) $(KAAPI_CFLAGS) $(CFLAGS) -c $<
%.starpu.o: %.starpu.c
	$(CC) $(STARPU_CFLAGS) $(CFLAGS) -c $<
%.ompss.o: %.ompss.c
	mcc $(OMPSS_CFLAGS) $(CFLAGS) -c $<
%.quark.o: %.quark.c
	$(CC) $(QUARK_CFLAGS) $(CFLAGS) -c $<

%.kaapi.c: %.yaml main.py
	./main.py --target=kaapi $< > $@
%.starpu.c: %.yaml main.py
	./main.py --target=starpu $< > $@
%.ompss.c: %.yaml main.py
	./main.py --target=ompss $< > $@
%.quark.c: %.yaml main.py
	./main.py --target=quark $< > $@

