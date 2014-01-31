#!/usr/bin/env python
import yaml
import argparse

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
            if a.access == "IN":
                self.out.write("KAAPI_ACCESS_MODE_R, ")
            elif a.access == "OUT":
                self.out.write("KAAPI_ACCESS_MODE_W, ")
            elif a.access == "INP":
                self.out.write("KAAPI_ACCESS_MODE_R|KAAPI_ACCESS_MODE_P, ")
            elif a.access == "OUTP":
                self.out.write("KAAPI_ACCESS_MODE_W|KAAPI_ACCESS_MODE_P, ")
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
            if task.args[i].access == 'IN':
                print >>self.out, "    depbench_core_touch_in(%u,context,datas[%u].mem,datas[%u].size,%u);" % (task.uid, task.args[i].uid, task.args[i].uid,i)
        # hash size times
        print >>self.out, "    depbench_core_do_work(%u, context,t->size);" % task.uid
        print >>self.out, "    depbench_core_save_state(%u,context);" % task.uid
        # touch allocated memory
        print >>self.out, "    for(unsigned int i = 0; i < t->num_allocs; i++)"
        print >>self.out, "    {"
        print >>self.out, "        data_t *d = t->allocs[i];"
        print >>self.out, "        depbench_core_touch_alloc(%u,context,d->mem,d->size,i);" % task.uid
        print >>self.out, "    }"
        # write to output variables
        for i in xrange(len(task.args)):
            if task.args[i].access == 'OUT':
                print >>self.out, "    depbench_core_touch_out(%u,context,datas[%u].mem,datas[%u].size,%u);" % (task.uid, task.args[i].uid, task.args[i].uid, i)
        # spawn
        for i,t  in enumerate(task.children):
            print >>self.out, "    ktasks[%u] = kaapi_thread_toptask(thread);" % i
            print >>self.out, "    kaapi_task_init(ktasks[%u], %s_body, " % (i,t.name)
            print >>self.out, "        kaapi_thread_pushdata(thread, sizeof(%s_arg_t)));" % t.name
            print >>self.out, "    arg%u = kaapi_task_getargst(ktasks[%u],%s_arg_t);" % (i,i,t.name)
            for j,a in enumerate(t.args):
                if a.uid in allocs:
                    print >>self.out, "    kaapi_access_init(&arg%u->arg%u,datas[%u].mem);" % (i,j,a.uid)
                else:
                    print >>self.out, "    arg%u->arg%u.data = datas[%u].mem;" % (i,j,a.uid)
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

class StarPU:
    def __init__(self,output):
        self.out = output
        pass

    def includes(self):
       print >>self.out, "#include<starpu.h>"

    def task_body_prototype(self,task):
        print >>self.out, "void {0}_body (void *buffers[], void *cl_arg);".format(task.name)

    def task_register(self,task):
        name = task.name
        numargs = len(task.args)
        print >>self.out, "struct starpu_codelet %s_cl =" % name
        print >>self.out, "{"
        print >>self.out, ".cpu_funcs = { %s_body, NULL }," % name
        print >>self.out, ".nbuffers = %u," % numargs
        self.out.write(".modes = {")
        for a in task.args:
            if a.access == "IN":
                self.out.write("STARPU_R, ")
            else:
                self.out.write("STARPU_W, ")
        print >>self.out, "}"
        print >>self.out, "};"
        print >>self.out, "starpu_data_handle_t %s_alloc_handles[%u];" % (name, len(task.allocs)) 

    def task_body(self,task):
        print >>self.out, "void {0}_body (void *buffers[], void *cl_arg)".format(task.name)
        print >>self.out, "{"
        # declare everything
        if task.children:
            print >>self.out, "    struct starpu_task *stasks[%u];" % len(task.children)
        print >>self.out, "    task_t *t = &tasks[%u];" % task.uid
        print >>self.out, "    void *context;"
        # allocate new data
        print >>self.out, "    for(unsigned int i = 0; i < t->num_allocs; i++)"
        print >>self.out, "    {"
        print >>self.out, "        data_t *d = t->allocs[i];"
        print >>self.out, "        d->mem = calloc(d->size,1);"
        # register them
        print >>self.out, "        starpu_vector_data_register(&%s_alloc_handles[i],0, (uintptr_t)d->mem,d->size,1);" % task.name
        print >>self.out, "    }"
        # pass IN args to core
        print >>self.out, "    depbench_core_init(%u,&context);" % task.uid
        for i in xrange(len(task.args)):
            if task.args[i].access == 'IN':
                print >>self.out, "    depbench_core_touch_in(%u,context,datas[%u].mem,datas[%u].size,%u);" % (task.uid, task.args[i].uid, task.args[i].uid,i)
        # hash size times
        print >>self.out, "    depbench_core_do_work(%u, context,t->size);" % task.uid
        print >>self.out, "    depbench_core_save_state(%u,context);" % task.uid
        # touch allocated memory
        print >>self.out, "    for(unsigned int i = 0; i < t->num_allocs; i++)"
        print >>self.out, "    {"
        print >>self.out, "        data_t *d = t->allocs[i];"
        print >>self.out, "        depbench_core_touch_alloc(%u,context,d->mem,d->size,i);" % task.uid
        print >>self.out, "    }"
        # write to output variables
        for i in xrange(len(task.args)):
            if task.args[i].access == 'OUT':
                print >>self.out, "    depbench_core_touch_out(%u,context,datas[%u].mem,datas[%u].size,%u);" % (task.uid, task.args[i].uid, task.args[i].uid, i)
        # spawn
        for i,t  in enumerate(task.children):
            print >>self.out, "    stasks[%u] = starpu_task_create();" % i
            print >>self.out, "    stasks[%u]->cl = &%s_cl;" % (i,t.name)
            for j,a in enumerate(t.args):
                idx = [ d.uid for d in a.alloc.allocs ]
                print >>self.out, "    stasks[%u]->handles[%u] = %s_alloc_handles[%u];" % (i,j,a.alloc.name, idx.index(a.uid))
            print >>self.out, "    assert(!starpu_task_submit(stasks[%u]));" % i
        print >>self.out, "}"

    def main_definitions(self):
        print >>self.out, "    struct starpu_task *task;"

    def main_init(self):
        print >>self.out, "    assert(!starpu_init(NULL));"

    def main_spawnsource(self,source):
        print >>self.out, "    task = starpu_task_create();"
        print >>self.out, "    task->cl = &{0}_cl;".format(source.name)
        print >>self.out, "    assert(!starpu_task_submit(task));"
        print >>self.out, "    starpu_task_wait_for_all();"

    def main_finalize(self):
        print >>self.out, "    starpu_shutdown();"

class OmpSs:
    def __init__(self,output):
        self.out = output

    def includes(self):
        print >>self.out, "#include<stdlib.h>"

    def task_body_prototype(self,task):
        self.out.write("void {0}_body (".format(task.name))
        self.out.write(",".join(["void *arg%u" % i for i in xrange(len(task.args))]))
        print >>self.out, ");"


    def task_register(self,task):
        pass

    def task_body(self,task):
        self.out.write("void {0}_body (".format(task.name))
        self.out.write(",".join(["void *arg%u" % i for i in xrange(len(task.args))]))
        print >>self.out, ")"
        print >>self.out, "{"
        # declare everything
        print >>self.out, "    task_t *t = &tasks[%u];" % task.uid
        print >>self.out, "    void *context;"
        # allocate new data
        print >>self.out, "    for(unsigned int i = 0; i < t->num_allocs; i++)"
        print >>self.out, "    {"
        print >>self.out, "        data_t *d = t->allocs[i];"
        print >>self.out, "        d->mem = calloc(d->size,1);"
        print >>self.out, "    }"
        # pass IN args to core
        print >>self.out, "    depbench_core_init(%u,&context);" % task.uid
        for i in xrange(len(task.args)):
            if task.args[i].access == 'IN':
                print >>self.out, "    depbench_core_touch_in(%u,context,datas[%u].mem,datas[%u].size,%u);" % (task.uid, task.args[i].uid, task.args[i].uid,i)
        # hash size times
        print >>self.out, "    depbench_core_do_work(%u, context,t->size);" % task.uid
        print >>self.out, "    depbench_core_save_state(%u,context);" % task.uid
        # touch allocated memory
        print >>self.out, "    for(unsigned int i = 0; i < t->num_allocs; i++)"
        print >>self.out, "    {"
        print >>self.out, "        data_t *d = t->allocs[i];"
        print >>self.out, "        depbench_core_touch_alloc(%u,context,d->mem,d->size,i);" % task.uid
        print >>self.out, "    }"
        # write to output variables
        for i in xrange(len(task.args)):
            if task.args[i].access == 'OUT':
                print >>self.out, "    depbench_core_touch_out(%u,context,datas[%u].mem,datas[%u].size,%u);" % (task.uid, task.args[i].uid, task.args[i].uid, i)
        # spawn
        for i,t  in enumerate(task.children):
            self.out.write("#pragma omp task ")
            for j,a in enumerate(t.args):
                if a.access == 'IN':
                    self.out.write("in(datas[%u].mem [ datas[%u].size ]) " % (a.uid,a.uid))
                else:
                    self.out.write("out(datas[%u].mem [ datas[%u].size ]) " % (a.uid,a.uid))
            print >>self.out,""
            self.out.write("    {0}_body(".format(t.name))
            self.out.write(",".join(["datas[{0}].mem".format(a.uid) for a in t.args]))
            print >>self.out, ");"
        print >>self.out, "}"

    def main_definitions(self):
        pass

    def main_init(self):
        pass

    def main_spawnsource(self,source):
        print >>self.out, "#pragma omp task"
        print >>self.out, "    {0}_body();".format(source.name);
        print >>self.out, "#pragma omp taskwait"

    def main_finalize(self):
        pass

class Quark:
    def __init__(self,output):
        self.out = output
        pass

    def includes(self):
       print >>self.out, "#include<quark.h>"

    def task_body_prototype(self,task):
        print >>self.out, "void {0}_body (Quark *);".format(task.name)

    def task_register(self,task):
        pass

    def task_body(self,task):
        print >>self.out, "void {0}_body (Quark *quark)".format(task.name)
        print >>self.out, "{"
        # declare everything
        if task.children:
            print >>self.out, "    Quark_Task *qtasks[%u];" % len(task.children)
        print >>self.out, "    task_t *t = &tasks[%u];" % task.uid
        print >>self.out, "    void *context;"
        # allocate new data
        print >>self.out, "    for(unsigned int i = 0; i < t->num_allocs; i++)"
        print >>self.out, "    {"
        print >>self.out, "        data_t *d = t->allocs[i];"
        print >>self.out, "        d->mem = calloc(d->size,1);"
        print >>self.out, "    }"
        # pass IN args to core
        print >>self.out, "    depbench_core_init(%u,&context);" % task.uid
        for i in xrange(len(task.args)):
            if task.args[i].access == 'IN':
                print >>self.out, "    depbench_core_touch_in(%u,context,datas[%u].mem,datas[%u].size,%u);" % (task.uid, task.args[i].uid, task.args[i].uid,i)
        # hash size times
        print >>self.out, "    depbench_core_do_work(%u, context,t->size);" % task.uid
        print >>self.out, "    depbench_core_save_state(%u,context);" % task.uid
        # touch allocated memory
        print >>self.out, "    for(unsigned int i = 0; i < t->num_allocs; i++)"
        print >>self.out, "    {"
        print >>self.out, "        data_t *d = t->allocs[i];"
        print >>self.out, "        depbench_core_touch_alloc(%u,context,d->mem,d->size,i);" % task.uid
        print >>self.out, "    }"
        # write to output variables
        for i in xrange(len(task.args)):
            if task.args[i].access == 'OUT':
                print >>self.out, "    depbench_core_touch_out(%u,context,datas[%u].mem,datas[%u].size,%u);" % (task.uid, task.args[i].uid, task.args[i].uid, i)
        # quark doesn't support task children.
        print >>self.out, "}"

    def main_definitions(self):
        print >>self.out, "    Quark *quark;"
        print >>self.out, "    Quark_Task *task;"
        print >>self.out, "    Quark_Task_Flags task_flags = Quark_Task_Flags_Initializer;"

    def main_init(self):
        print >>self.out, "    quark = QUARK_New(0);"

    def main_spawnsource(self,source):
        # since all tasks must be create by thread 0, we call source's body
        # without tasking, and create its children after.
        print >>self.out, "    {0}_body(quark);".format(source.name)
        for i,t in enumerate(source.children):
            print >>self.out, "    task = QUARK_Task_Init(quark,%s_body,&task_flags);" % t.name
            for a in t.args:
                self.out.write("    QUARK_Task_Pack_Arg(quark,task,datas[{0}].size,datas[{0}].mem,".format(a.uid));
                if a.access == 'IN':
                    print >>self.out, "INPUT);"
                else:
                    print >>self.out, "OUTPUT);"
            print >>self.out, "    QUARK_Insert_Task_Packed(quark,task);"
        print >>self.out, "    QUARK_Waitall(quark);"

    def main_finalize(self):
        print >>self.out, "    QUARK_Delete(quark);"
        pass


class Cdriver:
    def __init__(self,output):
        self.out = output

    def includes(self):
        print >>self.out, "#include <time.h>"
        print >>self.out, "#include <stdlib.h>"
        print >>self.out, "#include <assert.h>"

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
        print >>self.out, "    const char *name;"
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
            f = (t.uid, t.name, t.size, len(t.allocs), len(t.args), len(t.children))
            print >>self.out, "    { %u, \"%s\", %u, %u, %u, %u, NULL, NULL, NULL }," % f
        print >>self.out, "};"
        # topological sort
        print >>self.out, "unsigned long toposort[N] = {"
        for t in tasks:
                self.out.write("%u, " % t.uid)
        print >>self.out, "};"

    def kernel_verif(self):
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
    const char *name;
    name = tasks[taskid].name;
    SHA_CTX *c = malloc(sizeof(SHA_CTX));
    SHA1_Init(c);
    SHA1_Update(c,(sha1_byte*)name,strlen(name));
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
    //SHA1_Update(&ctxt,(sha1_byte*)&argnum,sizeof(argnum));
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

void depbench_core_touch_alloc(unsigned long taskid, void *context,
                        void *data, unsigned long size, unsigned int argnum)
{
    SHA_CTX ctxt;
    sha1_byte digest[SHA1_DIGEST_LENGTH];
    memcpy(&ctxt,context,sizeof(SHA_CTX));
    SHA1_Final(digest,&ctxt);
    memcpy(data,digest,min(size,SHA1_DIGEST_LENGTH));
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

    def kernel_add(self):
        print >>self.out, """
void depbench_core_init(unsigned long taskid, void **context)
{
    *context = malloc(sizeof(unsigned long));
}

void depbench_core_touch_in(unsigned long taskid, void *context,
                        void *data, unsigned long size, unsigned int argnum)
{
}

void depbench_core_touch_out(unsigned long taskid, void *context,
                        void *data, unsigned long size, unsigned int argnum)
{
}

void depbench_core_touch_alloc(unsigned long taskid, void *context,
                        void *data, unsigned long size, unsigned int argnum)
{
}

void depbench_core_do_work(unsigned long taskid, void *context, unsigned long size)
{
    unsigned long i;
    unsigned long *p = (unsigned long *)context;
    for(i = 0; i < size*10; i++)
        *p += 2*i + *p;
}

void depbench_core_save_state(unsigned long taskid, void *context)
{
}

void depbench_core_print_meta(unsigned long taskid, char *taskname)
{
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
                print >>self.out, "    tasks[%u].args[%u] = &datas[%u];" % (i,j,a.uid)
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
drivers = { 'kaapi': Kaapi, 'starpu': StarPU, 'ompss': OmpSs, 'quark' : Quark }
kernels = { 'verif': "kernel_verif", 'add': 'kernel_add' }
parser = argparse.ArgumentParser()
parser.add_argument("--target",choices=drivers.keys(),default=drivers.keys()[0])
parser.add_argument("--kernel",choices=kernels.keys(),default='verif')
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

# Generate the program
import sys
driver = drivers[argv.target](sys.stdout)
driver.includes()
# global data
gdriver = Cdriver(sys.stdout)
gdriver.includes()
gdriver.global_symbols(tasks,datas)
# print kernel
k = getattr(gdriver,kernels[argv.kernel])
k()
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
