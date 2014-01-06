#!/usr/bin/env python
import yaml
import argparse
import hashlib
import sys
import struct
import binascii

class Data:
    def __init__(self,yaml):
        self.uid = yaml['id']
        self.size = yaml['size']

class Task:
    def __init__(self,uid,yaml,datas):
        self.name = yaml['name']
        self.uid = uid
        self.size = yaml['size']
        self.allocs = []
        for i in xrange(yaml['numallocs']):
            self.allocs.append(datas[yaml['allocs'][i]])
        self.args = []
        for i in xrange(yaml['numargs']):
            h = {}
            h['id'] = yaml['args'][i]['id']
            h['type'] = yaml['args'][i]['type']
            self.args.append(h)
        self.children = []
        for i in xrange(yaml['numchildren']):
            self.children.append(yaml['children'][i])

    def finalize(self,names):
        for i in xrange(len(self.children)):
            self.children[i] = names[self.children[i]]

    def compute_hash(self,th,dh,datas):
        # start by hashing the task uid
        h = hashlib.sha1()
        h.update(struct.pack("@L",self.uid))
        # then hash each in parameter
        for i,a in enumerate(self.args):
            if a['type'] == 'IN':
                assert a['id'] in dh
                #print "update", self.uid, a['id'], repr(dh[a['id']])
                h.update(dh[a['id']])
        # init allocs
        for i,d in enumerate(self.allocs):
            dh[d.uid] = bytearray(d.size)
            #print "initalloc", self.uid, d.uid, repr(dh[d.uid])
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
        #print "taskd", self.uid, taskd
        # now compute each out digest
        for i,a in enumerate(self.args):
            d = datas[a['id']]
            if a['type'] == 'OUT':
                g = h.copy()
                g.update(struct.pack("@I",i))
                ah = g.digest()
                real_hash = bytearray(d.size)
                l = min(g.digest_size,d.size)
                real_hash[:l] = ah[:l]
                dh[d.uid] = real_hash
                #print "touchout", self.uid, d.uid, i, repr(dh[d.uid]),repr(ah),repr(g.hexdigest()),l
        return taskd


### Main function
parser = argparse.ArgumentParser()
parser.add_argument("graph",type=argparse.FileType('r'))
parser.add_argument("log",type=argparse.FileType('r'))
argv = parser.parse_args()

print "checking graph \'%s\' with log \'%s\'" %(argv.graph.name,argv.log.name)
print "==== CHECKING"

tree = {}
tree = yaml.load(argv.graph)

N = tree['N']
M = tree['M']

datas = []
for i in xrange(M):
    datas.append(Data(tree['data'][i]))
    assert i == datas[i].uid
tasks = []
for i in xrange(N):
    tasks.append(Task(i,tree['tasks'][i],datas))
names = {}
for t in tasks:
    names[t.name] = t
for t in tasks:
    t.finalize(names)

# parse log file:
lines = argv.log.readlines()
# remove the last one, its just the timing
del lines[-1]
# now dict everything
digests = {}
for l in lines:
    fields = l.strip().split()
    name = fields[0]
    d = fields[1]
    digests[name] = d

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
