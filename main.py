#!/usr/bin/env python
import yaml
import argparse

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

class Kaapi:
    def __init__(self,output):
        self.out = output
        pass

    def includes(self):
       print >>self.out, "#include<kaapi.h>"
       print >>self.out, "#include<stddef.h>"

    def task_body_prototype(self,task):
        print >>self.out, "void {0}_body (void *taskarg, kaapi_thread_t *thread);".format(task.name)

    def task_register(self,task):
        name = task.name
        numargs = len(task.args)
        print >>self.out, "typedef struct %s_arg_t {" % name 
        for i in xrange(numargs):
            print >>self.out, "  kaapi_access_t arg%u;" % i
        print >>self.out, "} %s_arg_t;" % name

        print >>self.out, "KAAPI_REGISTER_TASKFORMAT( %s_format," % name
        print >>self.out, "    \"{0}\", {0}_body, sizeof({0}_arg_t), {1},".format(name,numargs)

        self.out.write("    (kaapi_access_mode_t[]) { ")
        for a in task.args:
            if a['type'] == "IN":
                self.out.write("KAAPI_ACCESS_MODE_R, ")
            else:
                self.out.write("KAAPI_ACCESS_MODE_W, ")
        print >>self.out, "},"

        self.out.write("    (kaapi_offset_t[]) { ")
        for i in xrange(numargs):
                self.out.write("offsetof(%s_arg_t, arg%u.data), " % (name,i))
        print >>self.out, "},"

        self.out.write("    (kaapi_offset_t[]) { ")
        for i in xrange(numargs):
                self.out.write("offsetof(%s_arg_t, arg%u.version), " % (name,i))
        print >>self.out, "},"

        self.out.write("    (const struct kaapi_format_t*[]) { ")
        for i in xrange(numargs):
                self.out.write("kaapi_voidp_format,")
        print >>self.out, "},"
        print >>self.out, "    0"
        print >>self.out, ")"

    def task_body(self,task):
        print >>self.out, "void {0}_body (void *taskarg, kaapi_thread_t *thread)".format(task.name)
        print >>self.out, "{"
        # declare everything
        if task.children:
            print >>self.out, "    kaapi_task_t *ktasks[%u];" % len(task.children)
            for i,t in enumerate(task.children):
                print >>self.out, "    %s_arg_t* arg%u;" % (t.name,i)
        print >>self.out, "    task_t *t = &tasks[%u];" % task.uid
        print >>self.out, "    void *context;"
        # allocate new data
        allocs = {}
        for d in task.allocs:
            allocs[d.uid] = True
        print >>self.out, "    for(unsigned int i = 0; i < t->num_allocs; i++)"
        print >>self.out, "    {"
        print >>self.out, "        data_t *d = t->allocs[i];"
        print >>self.out, "        d->mem = calloc(d->size,1);"
        print >>self.out, "    }"
        # unpack arguments and send them to the core kernel
        print >>self.out, "    {0}_arg_t* arg = ({0}_arg_t*)taskarg;".format(task.name)
        print >>self.out, "    depbench_core_init(%u,&context);" % task.uid
        for i in xrange(len(task.args)):
            if task.args[i]['type'] == 'IN':
                print >>self.out, "    depbench_core_touch_in(%u,context,datas[%u].mem,datas[%u].size,%u);" % (task.uid, task.args[i]['id'], task.args[i]['id'],i)
        # hash size times
        print >>self.out, "    depbench_core_do_work(%u, context,t->size);" % task.uid
        print >>self.out, "    depbench_core_save_state(%u,context);" % task.uid
        # write to output variables
        for i in xrange(len(task.args)):
            if task.args[i]['type'] == 'OUT':
                print >>self.out, "    depbench_core_touch_out(%u,context,datas[%u].mem,datas[%u].size,%u);" % (task.uid, task.args[i]['id'], task.args[i]['id'], i)
        # spawn
        for i,t  in enumerate(task.children):
            print >>self.out, "    ktasks[%u] = kaapi_thread_toptask(thread);" % i
            print >>self.out, "    kaapi_task_init(ktasks[%u], %s_body, " % (i,t.name)
            print >>self.out, "        kaapi_thread_pushdata(thread, sizeof(%s_arg_t)));" % t.name
            print >>self.out, "    arg%u = kaapi_task_getargst(ktasks[%u],%s_arg_t);" % (i,i,t.name)
            for j,a in enumerate(t.args):
                if a['id'] in allocs: 
                    print >>self.out, "    kaapi_access_init(&arg%u->arg%u,datas[%u].mem);" % (i,j,a['id'])
                else:
                    print >>self.out, "    arg%u->arg%u.data = datas[%u].mem;" % (i,j,a['id'])
            print >>self.out, "    kaapi_thread_pushtask(thread);"
        print >>self.out, "}"

    def main_definitions(self):
        print >>self.out, "    kaapi_task_t *task;"
        print >>self.out, "    kaapi_thread_t *thread;"

    def main_init(self):
        print >>self.out, "    kaapi_init(1,&argc,&argv);"
        print >>self.out, "    thread = kaapi_self_thread();"
    
    def main_spawnsource(self,source):
        print >>self.out, "    task = kaapi_thread_toptask(thread);"
        print >>self.out, "    kaapi_task_init(task,{0}_body,kaapi_thread_pushdata(thread,sizeof({0}_arg_t)));".format(source.name)
        print >>self.out, "    kaapi_thread_pushtask(thread);"
        print >>self.out, "    kaapi_sched_sync();"
        
    def main_finalize(self):
        print >>self.out, "    kaapi_finalize();"

class Cdriver:
    def __init__(self,output):
        self.out = output

    def includes(self):
        print >>self.out, "#include <time.h>"

    def global_symbols(self,tasks,datas):
        print >>self.out, "#define N (%u)" % len(tasks)
        print >>self.out, "#define M (%u)" % len(datas)
		# data struct definition
        print >>self.out, "typedef struct data_st {"
        print >>self.out, "    void *mem;"
        print >>self.out, "    unsigned long size;"
        print >>self.out, "    unsigned long uid;"
        print >>self.out, "} data_t;"
        # data init
        print >>self.out, "data_t datas[M] = {"
        for d in datas:
                print >>self.out, "    { NULL, %u, %u }," % (d.size,d.uid)
        print >>self.out, "};"
        ## task struct definition
        print >>self.out, "typedef struct task_st {"
        print >>self.out, "    unsigned long uid;"
        print >>self.out, "    unsigned long size;"
        print >>self.out, "    unsigned long num_allocs;"
        print >>self.out, "    unsigned long num_args;"
        print >>self.out, "    unsigned long num_children;"
        print >>self.out, "    data_t **allocs;"
        print >>self.out, "    data_t **args;"
        print >>self.out, "    struct task_st **children;"
        print >>self.out, "} task_t;"
        # tasks
        print >>self.out, "task_t tasks[N] = {"
        for t in tasks:
            t = (t.uid, t.size, len(t.allocs), len(t.args), len(t.children))
            print >>self.out, "    { %u, %u, %u, %u, %u, NULL, NULL, NULL }," % t
        print >>self.out, "};"
        # topological sort
        print >>self.out, "unsigned long toposort[N] = {"
        for t in tasks:
                self.out.write("%u, " % t.uid)
        print >>self.out, "};"

    def verif_kernel(self):
        # print function definitions for the kernel suite of functions
        print >>self.out, """
#include <string.h>
#include "sha.h"

typedef struct kern_meta_st {
    sha1_byte task_h[SHA1_DIGEST_LENGTH];
    sha1_byte **args_h;
} kern_meta_t;

kern_meta_t kern_metas[N];

void depbench_core_init(unsigned long taskid, void **context)
{
    unsigned long i;
    SHA_CTX *c = malloc(sizeof(SHA_CTX));
    SHA1_Init(c);
    SHA1_Update(c,(sha1_byte*)&taskid,sizeof(taskid));
    *context = c;
    kern_metas[taskid].args_h = calloc(tasks[taskid].num_args,sizeof(sha1_byte *));
    for(i = 0; i < tasks[taskid].num_args; i++)
        kern_metas[taskid].args_h[i] = calloc(tasks[taskid].args[i]->size,sizeof(sha1_byte));
}

void depbench_core_touch_in(unsigned long taskid, void *context, 
                        void *data, unsigned long size, unsigned int argnum)
{
    unsigned long i;
    //for(i = 0; i< size; i++)
    //    printf("%02hx",((unsigned short*)data)[i]);
    //printf("\\n");
    memcpy(kern_metas[taskid].args_h[argnum],data,size);
    SHA1_Update(context,data,size);

}

#define min(x,y) ((x) < (y) ? (x) : (y))
void depbench_core_touch_out(unsigned long taskid, void *context, 
                        void *data, unsigned long size, unsigned int argnum)
{
    /* copy the context, update with arg number, finalize and write */
    SHA_CTX ctxt;
    unsigned long i;
    sha1_byte digest[SHA1_DIGEST_LENGTH];
    memcpy(&ctxt,context,sizeof(SHA_CTX));
    SHA1_Update(&ctxt,(sha1_byte*)&argnum,sizeof(argnum));
    SHA1_Final(digest,&ctxt);
    //printf("outd %p ",data);
    //for(i = 0; i < SHA1_DIGEST_LENGTH ; i++)
    //    printf("%02hx",digest[i]);
    //printf("\\n");
    memcpy(data,digest,min(size,SHA1_DIGEST_LENGTH));
    memcpy(kern_metas[taskid].args_h[argnum],digest,min(size,SHA1_DIGEST_LENGTH));
    //printf("out %p ",data);
    //for(i = 0; i< size; i++)
    //    printf("%02hx",((unsigned short *)data)[i]);
    //printf("\\n");
}

void depbench_core_do_work(unsigned long taskid, void *context, unsigned long size)
{
    /* rehash the state size times. */
    SHA_CTX ctxt;
    sha1_byte digest[SHA1_DIGEST_LENGTH];
    unsigned long i;
    SHA1_Final(digest,context);
    for(i = 1; i < size; i++)
    {
        SHA1_Init(&ctxt);
        SHA1_Update(&ctxt,digest,SHA1_DIGEST_LENGTH);
        SHA1_Final(digest,&ctxt);
    }
    SHA1_Init(context);
    SHA1_Update(context,digest,SHA1_DIGEST_LENGTH);
}

void depbench_core_save_state(unsigned long taskid, void *context)
{
    SHA_CTX ctxt;
    int i;
    sha1_byte digest[SHA1_DIGEST_LENGTH];
    memcpy(&ctxt,context,sizeof(SHA_CTX));
    SHA1_Final(digest,&ctxt);
    memcpy(kern_metas[taskid].task_h,digest,SHA1_DIGEST_LENGTH);
}

void depbench_core_print_meta(unsigned long taskid, char *taskname)
{
    unsigned long i,j;
    printf("%s ", taskname);
    for(i = 0; i < SHA1_DIGEST_LENGTH; i++)
        printf("%02hx",kern_metas[taskid].task_h[i]);
    printf(" ");
    for(j = 0; j < tasks[taskid].num_args; j++)
    {
        for(i = 0; i < min(SHA1_DIGEST_LENGTH,tasks[taskid].args[j]->size); i++)
            printf("%02hx",kern_metas[taskid].args_h[j][i]);
        printf(" ");
    }
    printf("\\n");
}
"""


    def main(self,driver,tasks):
        print >>self.out, """
int main(int argc, char *argv[])
{
"""
        driver.main_definitions()
        print >>self.out, "    struct timespec start,stop;"
        for i,t in enumerate(tasks):
            print >>self.out, "    tasks[%u].allocs = calloc(%u,sizeof(data_t *));" % (i,len(t.allocs))
            for j,d in enumerate(t.allocs):
                print >>self.out, "    tasks[%u].allocs[%u] = &datas[%u];" %(i,j,d.uid)
            print >>self.out, "    tasks[%u].args = calloc(%u,sizeof(data_t *));" % (i,len(t.args))
            for j,a in enumerate(t.args):
                print >>self.out, "    tasks[%u].args[%u] = &datas[%u];" % (i,j,a['id'])
            print >>self.out, "    tasks[%u].children = calloc(%u,sizeof(task_t *));" % (i,len(t.children))
            for j,c in enumerate(t.children):
                print >>self.out, "    tasks[%u].children[%u] = &tasks[%u];" % (i,j,c.uid)
        driver.main_init()
        print >>self.out, "    clock_gettime(CLOCK_MONOTONIC,&start);"
        driver.main_spawnsource(tasks[0])
        print >>self.out, "    clock_gettime(CLOCK_MONOTONIC,&stop);"
        driver.main_finalize()
        for t in tasks:
            print >>self.out, "    depbench_core_print_meta(%u, \"%s\");" % (t.uid,t.name)
        print >>self.out, """
    long long int time = (stop.tv_nsec - start.tv_nsec) + 1e9* (stop.tv_sec - start.tv_sec);
    printf("timing: %Ld\\n",time);
    return 0;
}"""


### Main function
parser = argparse.ArgumentParser()
parser.add_argument("--target",choices=['kaapi'],default='kaapi')
parser.add_argument("--kernel",choices=['verif'],default='verif')
parser.add_argument("infile",type=argparse.FileType('r'))
argv = parser.parse_args()

print "//using file " + argv.infile.name + " as input"

tree = {}
tree = yaml.load(argv.infile)

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

# Generate the program
import sys
driver = Kaapi(sys.stdout)
driver.includes()
# global data
gdriver = Cdriver(sys.stdout)
gdriver.includes()
gdriver.global_symbols(tasks,datas)
gdriver.verif_kernel()
# task bodies prototypes
for t in tasks:
    driver.task_body_prototype(t)
# task registration
for t in tasks:
    driver.task_register(t)
# task bodies
for t in tasks:
    driver.task_body(t)
# main
gdriver.main(driver,tasks)
