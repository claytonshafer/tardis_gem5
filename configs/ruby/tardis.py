# Copyright (c) 2019 ARM Limited
# All rights reserved.
#
# The license below extends only to copyright in the software and shall
# not be construed as granting a license to any other intellectual
# property including but not limited to intellectual property relating
# to a hardware implementation of the functionality of the software
# licensed hereunder.  You may use the software subject to the license
# terms below provided that you ensure that this notice is replicated
# unmodified and in its entirety in all distributions of the software,
# modified or unmodified, in source code or in binary form.
#
# Copyright (c) 2006-2007 The Regents of The University of Michigan
# Copyright (c) 2009 Advanced Micro Devices, Inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met: redistributions of source code must retain the above copyright
# notice, this list of conditions and the following disclaimer;
# redistributions in binary form must reproduce the above copyright
# notice, this list of conditions and the following disclaimer in the
# documentation and/or other materials provided with the distribution;
# neither the name of the copyright holders nor the names of its
# contributors may be used to endorse or promote products derived from
# this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
# A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
# OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
# THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import math
import m5
from m5.objects import *
from m5.defines import buildEnv
from .Ruby import create_topology, create_directories
from .Ruby import send_evicts

#
# Declare caches used by the protocol
#
class L1Cache(RubyCache):
    dataAccessLatency = 1
    tagAccessLatency = 1

def define_options(parser):
    return

def create_system(options, full_system, system, dma_ports, bootmem,
                  ruby_system):

    if buildEnv['PROTOCOL'] != 'tardis':
        panic("This MOESI_CMP_directory protocol to be built.")

    cpu_sequencers = []

    #
    # The ruby network creation expects the list of nodes in the system to be
    # consistent wist list.  Therefore the l1 controller nodes must be
    # listed beforetory nodes and directory nodes before dma nodes, etc.
    #
    l1_cntrl_nodes = []

    dma_cntrl_nodes = []

    #
    # Must create the individual controllers before the network to ensure the
    # controller constructors are called before the network constructor
    #
    block_size_bits = int(math.log(options.cacheline_size, 2))

    for i in range(options.num_cpus):
        #
        # First create the Ruby objects associated with this cpu
        #
        l1i_cache = L1Cache(size = options.l1i_size,
                            assoc = options.l1i_assoc,
                            start_index_bit = block_size_bits,
                            is_icache = True)
        l1d_cache = L1Cache(size = options.l1d_size,
                            assoc = options.l1d_assoc,
                            start_index_bit = block_size_bits,
                            is_icache = False)

        # the ruby random tester reuses num_cpus to specify the
        # number of cpu ports connected to the tester object, which
        # is stored in system.cpu. because there is only ever one
        # tester object, num_cpus is not necessarily equal to the
        # size of system.cpu; therefore if len(system.cpu) == 1
        # we use system.cpu[0] to set the clk_domain, thereby ensuring
        # we don't index off the end of the cpu list.
        if len(system.cpu) == 1:
            clk_domain = system.cpu[0].clk_domain
        else:
            clk_domain = system.cpu[i].clk_domain

        l1_cntrl = L1Cache_Controller(version=i, L1Icache=l1i_cache,
                                      L1Dcache=l1d_cache,
                                      send_evictions=send_evicts(options),
                                      transitions_per_cycle=options.ports,
                                      clk_domain=clk_domain,
                                      ruby_system=ruby_system)

        cpu_seq = RubySequencer(version=i,
                                dcache=l1d_cache, clk_domain=clk_domain,
                                ruby_system=ruby_system)

        l1_cntrl.sequencer = cpu_seq
        exec("ruby_system.l1_cntrl%d = l1_cntrl" % i)

        # Add controllers and sequencers to the appropriate lists
        cpu_sequencers.append(cpu_seq)
        l1_cntrl_nodes.append(l1_cntrl)

        # Connect the L1 controllers and the network
        l1_cntrl.mandatoryQueue = MessageBuffer()
        l1_cntrl.requestFromDir = MessageBuffer()
        l1_cntrl.requestFromDir.master = ruby_system.network.slave
        l1_cntrl.responseFromDir = MessageBuffer()
        l1_cntrl.responseFromDir.master = ruby_system.network.slave
        l1_cntrl.requestToDir = MessageBuffer()
        l1_cntrl.requestToDir.slave = ruby_system.network.master
        l1_cntrl.responseToDir = MessageBuffer()
        l1_cntrl.responseToDir.slave = ruby_system.network.master
        l1_cntrl.triggerQueue = MessageBuffer(ordered = True)

        l1_cntrl.cacheMemory = RubyCache(size = '16kB',
                               assoc = 8,
                               start_index_bit = block_size_bits)
        l1_cntrl.progTS_global = 1

    # Run each of the ruby memory controllers at a ratio of the frequency of
    # the ruby system.
    # clk_divider value is a fix to pass regression.
    ruby_system.memctrl_clk_domain = DerivedClockDomain(
                                          clk_domain=ruby_system.clk_domain,
                                          clk_divider=3)


    mem_dir_cntrl_nodes, rom_dir_cntrl_node = create_directories(
        options, bootmem, ruby_system, system)
    dir_cntrl_nodes = mem_dir_cntrl_nodes[:]
    if rom_dir_cntrl_node is not None:
        dir_cntrl_nodes.append(rom_dir_cntrl_node)
    for dir_cntrl in dir_cntrl_nodes:
        # Connect the directory controllers and the network
        dir_cntrl.requestFromCache = MessageBuffer()
        dir_cntrl.requestFromCache.slave = ruby_system.network.master
        dir_cntrl.responseFromCache = MessageBuffer()
        dir_cntrl.responseFromCache.slave = ruby_system.network.master
        dir_cntrl.responseToCache = MessageBuffer()
        dir_cntrl.responseToCache.master = ruby_system.network.slave
        dir_cntrl.requestToCache = MessageBuffer()
        dir_cntrl.requestToCache.master = ruby_system.network.slave
        dir_cntrl.requestToDir = MessageBuffer()
        dir_cntrl.requestToDir.slave = ruby_system.network.master
        dir_cntrl.responseToDir = MessageBuffer()
        dir_cntrl.responseToDir.slave = ruby_system.network.master
        dir_cntrl.responseFromDir = MessageBuffer()
        dir_cntrl.responseFromDir.master = ruby_system.network.slave
        dir_cntrl.requestFromDir = MessageBuffer()
        dir_cntrl.requestFromDir.master = ruby_system.network.slave
        dir_cntrl.requestToMemory = MessageBuffer()
        dir_cntrl.responseFromMemory = MessageBuffer()
        dir_cntrl.triggerQueue = MessageBuffer(ordered = True)
        dir_cntrl.dmaRequestToDir = MessageBuffer()
        dir_cntrl.dmaRequestToDir.slave = ruby_system.network.master
        dir_cntrl.dmaResponseFromDir = MessageBuffer()
        dir_cntrl.dmaResponseFromDir.master = ruby_system.network.slave


    for i, dma_port in enumerate(dma_ports):
        #
        # Create the Ruby objects associated with the dma controller
        #
        dma_seq = DMASequencer(version = i,
                               ruby_system = ruby_system,
                               slave = dma_port)

        dma_cntrl = DMA_Controller(version = i,
                                   dma_sequencer = dma_seq,
                                   transitions_per_cycle = options.ports,
                                   ruby_system = ruby_system)

        exec("ruby_system.dma_cntrl%d = dma_cntrl" % i)
        dma_cntrl_nodes.append(dma_cntrl)

        # Connect the dma controller to the network
        dma_cntrl.mandatoryQueue = MessageBuffer()
        dma_cntrl.responseFromDir = MessageBuffer()
        dma_cntrl.responseFromDir.slave = ruby_system.network.master
        dma_cntrl.requestToDir = MessageBuffer()
        dma_cntrl.requestToDir.master = ruby_system.network.slave
        dma_cntrl.responseToDir = MessageBuffer()
        dma_cntrl.responseToDir.master = ruby_system.network.slave
#        dma_cntrl.triggerQueue = MessageBuffer(ordered = True)


    all_cntrls = l1_cntrl_nodes + \
                 dir_cntrl_nodes + \
                 dma_cntrl_nodes

    # Create the io controller and the sequencer
    if full_system:
        io_seq = DMASequencer(version=len(dma_ports), ruby_system=ruby_system)
        ruby_system._io_port = io_seq
        io_controller = DMA_Controller(version = len(dma_ports),
                                       dma_sequencer = io_seq,
                                       ruby_system = ruby_system)
        ruby_system.io_controller = io_controller

        # Connect the dma controller to the network
        io_controller.mandatoryQueue = MessageBuffer()
        io_controller.responseFromDir = MessageBuffer()
        io_controller.responseFromDir.slave = ruby_system.network.master
        io_controller.requestToDir = MessageBuffer()
        io_controller.requestToDir.master = ruby_system.network.slave
        io_controller.responseToDir = MessageBuffer()
        io_controller.responseToDir.master = ruby_system.network.slave
        io_controller.triggerQueue = MessageBuffer(ordered = True)

        all_cntrls = all_cntrls + [io_controller]

    ruby_system.network.number_of_virtual_networks = 6
    topology = create_topology(all_cntrls, options)
    return (cpu_sequencers, mem_dir_cntrl_nodes, topology)