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
        self.ref = None

class Data:
    def __init__(self,uid, sz):
        self.uid = uid
        self.size = sz

class Task:
    def __init__(self,uid):
        self.name = "t_%u" % uid
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
        h.update(self.name)
        # then hash each in parameter
        ins = [ a for a in self.args if a.access == 'IN' ]
        for a in sorted(ins, key=lambda a: a.ref.name):
            if a.access == 'IN':
                assert a.uid in dh
                logging.debug("update: %s %u %s", self.name, a.uid,
                        repr(dh[a.uid]))
                h.update(dh[a.uid])
        # init allocs
        for i,d in enumerate(self.allocs):
            dh[d.uid] = bytearray(d.size)
            logging.debug("initalloc: %s %u %s", self.name, d.uid,
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
        logging.debug("taskd: %s %s", self.name, taskd)
        # now compute each out digest
        # allocs are also outs
        outs = [datas[a.uid] for a in self.args if a.access == 'OUT']
        outs =  outs + self.allocs
        for d in outs:
            g = h.copy()
            ah = g.digest()
            real_hash = bytearray(d.size)
            l = min(g.digest_size,d.size)
            real_hash[:l] = ah[:l]
            dh[d.uid] = real_hash
            logging.debug("touchout: %s %u %s %s %s %u",self.name, d.uid,
                        repr(dh[d.uid]),repr(ah),repr(g.hexdigest()),l)
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
                    default="weight")
parser.add_argument("--type",choices=['yaml','dot'],default='dot')

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

if argv.type == 'yaml':
    import yaml
    graph = yaml.load(argv.graph)

    N = graph['N']
    M = graph['M']

    for i in xrange(M):
        uid = graph['data'][i]['id']
        size = int(float(graph['data'][i][argv.data_size_key]))
        datas.append(Data(uid,size))
        assert i == datas[i].uid
    for i in xrange(N):
        t = Task(i)
        d = graph['tasks'][i]
        t.name = d['name']
        t.size = int(float(d[argv.task_size_key]))
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

else:
    import pygraphviz

    graph = pygraphviz.AGraph(argv.graph.name)

    N = graph.number_of_nodes()
    M = graph.number_of_edges()

    # build the list of tasks
    for i,n in enumerate(graph.nodes()):
        t = Task(i)
        t.name = n
        node = graph.get_node(n)
        t.size = int(float(node.attr[argv.task_size_key]))
        tasks.append(t)

    edges = {}
    for i,e in enumerate(graph.edges()):
        uid = i
        edge = graph.get_edge(e[0],e[1])
        size = int(float(edge.attr[argv.data_size_key]))
        d = Data(uid,size)
        datas.append(d)
        edges[edge] = d

    task_names = dict((t.name,t) for t in tasks)

    for t in tasks:
        node = graph.get_node(t.name)
        aref = {}
        for s in graph.successors(node):
            e = graph.get_edge(node,s)
            uid = edges[e].uid
            a = Arg(uid,'OUT')
            aref[a] = task_names[s]
            t.args.append(a)
        for p in graph.predecessors(node):
            e = graph.get_edge(p,node)
            uid = edges[e].uid
            a = Arg(uid,'IN')
            aref[a] = task_names[p]
            t.args.append(a)
        t.args = sorted(t.args, key=lambda a: aref[a].name)

    # we need to allocate all datas in source
    source = next(n for (n,d) in graph.in_degree_iter() if d == 0)
    source = task_names[source]
    for d in datas:
        source.allocs.append(d)

    del edges

# transform all names, to be function name compatible
for t in tasks:
    t.name = "t_%s" % t.name

# parse log file:
# small note: the log file is guarantied to be a topological sort, because the
# yaml that generated the program is so. We use this topological sort to
# recompute the hashes in the right order...
toposort = []
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
    toposort.append(name)

# use the toposort to renumber all tasks
for t in tasks:
    t.uid = toposort.index(t.name)

# now use the toposort to give last accessor ref to all args
lastaccess = {}
for t in sorted(tasks,key=lambda t: t.uid):
    for a in t.allocs:
        lastaccess[a.uid] = t
    for a in t.args:
        if a.access == 'OUT':
            lastaccess[a.uid] = t
        elif a.access == 'IN':
            a.ref = lastaccess[a.uid]

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
