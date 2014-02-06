#!/usr/bin/env python
import yaml
import argparse
import jinja2

class Arg:
    def __init__(self,uid,t):
        self.uid = uid
        self.access = t

    def __getitem__(self,key):
        return self.__getattr__(key)

class Data:
    def __init__(self,uid, sz):
        self.uid = uid
        self.size = sz

    def __getitem__(self,key):
        return self.__getattr__(key)

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

    def __getitem__(self,key):
        return self.__getattr__(key)

class TaskSig:
    def __init__(self,name,args):
        self.name = name
        self.args = args

    def __getitem__(self,key):
        return self.__getattr__(key)

### Main function
drivers = [ 'kaapi', 'starpu', 'ompss', 'quark' ]
kernels = [ 'verif', 'add' ]
parser = argparse.ArgumentParser()
parser.add_argument("--target",choices=drivers,default=drivers[0])
parser.add_argument("--kernel",choices=kernels,default=kernels[0])
parser.add_argument("--nedges",type=int,help="increase the number of edges",default=1)
parser.add_argument("--data-size-key",help="name of the data size key",
                    default="size")
parser.add_argument("--task-size-key",help="name of the task size key",
                    default="weight")
parser.add_argument("infile",type=argparse.FileType('r'))
argv = parser.parse_args()

print "//using file " + argv.infile.name + " as input"

graph = {}
N = 0
M = 0
datas = []
tasks = []
import yaml
graph = yaml.load(argv.infile)

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
    for j in xrange(d['numchildren']):
        t.children.append(d['children'][j])
    tasks.append(t)
names = {}
for t in tasks:
    names[t.name] = t
for t in tasks:
    t.finalize(names)

# transform all names, to be function name compatible
for t in tasks:
    t.name = "t_%s" % t.name

# apply modifications to the graph
if argv.nedges != 1:
    newd = []
    for d in datas:
        for i in xrange(argv.nedges):
            nd = Data(d.uid*argv.nedges+i,d.size)
            newd.append(nd)
    datas = newd
    for t in tasks:
        newa = []
        for a in t.allocs:
            for j in xrange(argv.nedges):
                newa.append(datas[a.uid*argv.nedges+j])
        t.allocs = newa
        newa = []
        for a in t.args:
            for j in xrange(argv.nedges):
                newa.append(Arg(a.uid*argv.nedges+j,a.access))
        t.args = newa
    M = M*argv.nedges

# verif kernel: sort args by last access name, tasks are already in topo order
if argv.kernel == 'verif':
    lastaccess = {}
    for t in tasks:
        for a in t.allocs:
            lastaccess[a.uid] = t
        for a in t.args:
            a.ref = lastaccess[a.uid]
            if a.access == 'OUT':
                lastaccess[a.uid] = t
        t.args.sort(key=lambda a: a.ref.name)

# register which task allocates a data
for t in tasks:
    for a in t.allocs:
        a.ref = t
for t in tasks:
    for a in t.args:
        a.alloc = datas[a.uid].ref

# find for each task its signature.
sigs = {}
modes = { 'IN': 'r', 'OUT' : 'w', 'INP' : 'rp', 'OUTP' : 'wp' }
for t in tasks:
    # take the list of arguments, and build a signature for them. For now, we
    # only need to group task by the list of parameter access modes, in order.
    sig = "s_" + ''.join([ modes[a.access] for a in t.args ])
    if sig not in sigs:
        # build sig
        sigs[sig] = TaskSig(sig,t.args)
    t.sig = sigs[sig]

# Generate the program
import sys
# load the environment
l = jinja2.FileSystemLoader('templates')
env = jinja2.Environment(loader=l, trim_blocks=True, lstrip_blocks=True)

# build the names of the template we are looking for
core_template_name = "c/common/main.templ"
target_template_name = "c/targets/%s.templ" % argv.target
kernel_template_name = "c/kernels/%s.templ" % argv.kernel

core_template = env.get_template(core_template_name)
target_template = env.get_template(target_template_name)
kernel_template = env.get_template(kernel_template_name)

print kernel_template.render(tasks=tasks, datas=datas, sigs=sigs.values(), core=core_template, target=target_template)
