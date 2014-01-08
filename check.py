#!/usr/bin/env python
import argparse
import hashlib
import sys
import struct
import binascii
import logging

class Arg:
    def __init__(self,uid,t):
        self.uid = uid
        self.access = t

class Data:
    def __init__(self,uid, sz):
        self.uid = uid
        self.size = sz

class Task:
    def __init__(self,uid):
        self.name = "t%u" % uid
        self.uid = uid
        self.size = 1
        self.allocs = []
        self.args = []
        self.children = []

    def finalize(self,names):
        for i in xrange(len(self.children)):
            self.children[i] = names[self.children[i]]

    def compute_hash(self,th,dh,datas):
        # start by hashing the task uid
        h = hashlib.sha1()
        h.update(struct.pack("@L",self.uid))
        # then hash each in parameter
        for i,a in enumerate(self.args):
            if a.access == 'IN':
                assert a.uid in dh
                logging.debug("update: %u %u %s", self.uid, a.uid,
                        repr(dh[a.uid]))
                h.update(dh[a.uid])
        # init allocs
        for i,d in enumerate(self.allocs):
            dh[d.uid] = bytearray(d.size)
            logging.debug("initalloc: %u %u %s", self.uid, d.uid,
                    repr(dh[d.uid]))
        # rehash the state size times
        d = h.digest()
        for i in xrange(1,self.size):
            h = hashlib.sha1()
            h.update(d)
            d = h.digest()
        h = hashlib.sha1()
        h.update(d)
        # save this value as the task digest
        g = h.copy()
        taskd = g.hexdigest()
        logging.debug("taskd: %u %s", self.uid, taskd)
        # now compute each out digest
        for i,a in enumerate(self.args):
            d = datas[a.uid]
            if a.access == 'OUT':
                g = h.copy()
                g.update(struct.pack("@I",i))
                ah = g.digest()
                real_hash = bytearray(d.size)
                l = min(g.digest_size,d.size)
                real_hash[:l] = ah[:l]
                dh[d.uid] = real_hash
                logging.debug("touchout: %u %u %u %s %s %s %u",self.uid, d.uid,
                            i, repr(dh[d.uid]),repr(ah),repr(g.hexdigest()),l)
        return taskd


### Main function
parser = argparse.ArgumentParser()
parser.add_argument("graph",type=argparse.FileType('r'))
parser.add_argument("trace",type=argparse.FileType('r'))
parser.add_argument("-d","--debug",help="show additional debug output",
                    action="store_true")
parser.add_argument("--data-size-key",help="name of the data size key", 
                    default="size")
parser.add_argument("--task-size-key",help="name of the task size key",
                    default="size")

argv = parser.parse_args()
if argv.debug:
    logging.basicConfig(level=logging.DEBUG)
else:
    logging.basicConfig(level=logging.WARNING)

print "checking graph \'%s\' with trace \'%s\'" %(argv.graph.name,argv.trace.name)
print "==== PARSING DATA"

graph = {}
N = 0
M = 0
datas = []
tasks = []
import yaml
graph = yaml.load(argv.graph)

N = graph['N']
M = graph['M']

for i in xrange(M):
    uid = graph['data'][i]['id']
    size = graph['data'][i][argv.data_size_key]
    datas.append(Data(uid,size))
    assert i == datas[i].uid
for i in xrange(N):
    t = Task(i)
    d = graph['tasks'][i]
    t.name = d['name']
    t.size = d[argv.task_size_key]
    for j in xrange(d['numallocs']):
        t.allocs.append(datas[d['allocs'][j]])
    for j in xrange(d['numargs']):
        uid = d['args'][j]['id']
        a = d['args'][j]['type']
        t.args.append(Arg(uid,a))
    # children can be ignored
    tasks.append(t)
names = {}
for t in tasks:
    names[t.name] = t
for t in tasks:
    t.finalize(names)

# parse log file:
lines = argv.trace.readlines()
# remove the last one, its just the timing
del lines[-1]
# now dict everything
digests = {}
for l in lines:
    fields = l.strip().split()
    name = fields[0]
    d = fields[1]
    digests[name] = d

print "==== CHECKING"
# check each task sha, by recomputing it.
thashes = {}
dhashes = {}
ok = True
for t in sorted(tasks,key=lambda t: t.uid):
    h = t.compute_hash(thashes,dhashes,datas)
    if h != digests[t.name]:
        print "%s %s %s ERROR" % (t.name,h,digests[t.name])
        ok = False
        break
    else:
        print "%s %s %s PASS" % (t.name,h,digests[t.name])
    thashes[t] = h
print "==== COMPUTED HASHES"
for k,v in thashes.iteritems():
    print "task hash: %s %s" % (k.name,v)
for k,v in dhashes.iteritems():
    print "data hash: %s %s" % (k,binascii.hexlify(v))
if ok:
    print "====> PASS: program execution was correct"
    sys.exit(0)
else:
    print "====> ERROR: program execution did not respect the original dependencies"
    sys.exit(1)
