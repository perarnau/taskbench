A Benchmark Generator
=====================

This tool takes as input a YAML file describing tasks, data and dependencies.
Using this file, it generates a program creating and executing those tasks,
using one of the frameworks supported.

Code generation is done by templates. Add a new template do add support for
another target or kernel.

The yaml file must respect some constraints:
- the format must respect:
	- number of tasks
	- number of datas
	- list of data
		- each data has an id and a size
	- list of tasks
		- each task has a name, a numallocs, a numargs, a numchildren,
		- each task has the list of allocs, list of args, list of
		  children
		- each task has a weight

- Tasks are in a valid topological order.
- Children list are in a valid topological order.
- the file represent a creation tree that is valid for the target framework.
- the uid of the datas are between 0 and M-1, in order.

Frameworks
==========

Currently support XKaapi, StarPU, OpenMP 4.0 (via OmpSs) and Quark

Input Generation
================

It should be possible to automatically generate the input to this program too.
Currently, this is done in the ggen tool.

Input examples are in the `examples` directory. Note that Quark requires the
flat version, StarPU and OpenMP the flat or cluster version, and XKaapi support
all of them.


License & Copyright
===================

This code is under no license right now (all rights reserved).
