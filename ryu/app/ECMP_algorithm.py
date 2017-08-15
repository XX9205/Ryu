#conding=utf-8
from __future__ import division
import numpy as np
import logging
import struct
import copy
import networkx as nx
from operator import attrgetter
from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import MAIN_DISPATCHER, DEAD_DISPATCHER
from ryu.controller.handler import CONFIG_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet
from ryu.lib.packet import ipv4
from ryu.lib.packet import arp
from ryu.lib import hub

from ryu.topology import event, switches
from ryu.topology.api import get_switch, get_link
import math

SLEEP_PERIOD = 10
IS_UPDATE = True

# ECMP-Hash Agorithm
class exp_four_test(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
    _NAME = 'exp_four_test'

    def __init__(self, *args, **kwargs):
        super(exp_four_test, self).__init__(*args, **kwargs)
        self.topology_api_app = self

        # links_to_port:(src_dpid,dst_dpid)->(src_port,dst_port)
        self.link_to_port = {}
        # access_table:{(sw,port) :[host1_ip]}
        self.access_table = {}
        # switch_port_table:dpip->port_num
        self.switch_port_table = {}
        # access_port:dpid->port_num
        self.access_ports = {}
        # interior_ports: dpid->port_num
        self.interior_ports = {}

        """
        # the other data structure
        self.graph = {}
        self.pre_graph = {}
        """

        self.graph = nx.DiGraph()
        self.pre_graph = nx.DiGraph()

        self.pre_access_table = {}
        self.pre_link_to_port = {}
        self.shortest_paths = None

        self.mac_to_port = {}
        self.datapaths = {}

        self.port_stats = {}
        self.port_speed = {}
        self.flow_stats = {}
        self.flow_speed = {}
        self.stats = {}
        self.port_features = {}
        self.free_bandwidth = {}
        self.path_monitor = {}
        self.best_paths = {}
        self.test_thread = hub.spawn(self._test)
        #self.f = open("/home/guoxiao/iperf_test/path.txt", "w")
        self.packet_in_table = []
        self.path_dict = {}
        self.core_node_list = []
        self.aggregation_node_list = []
        self.edge_node_list = []
        self.pod_list = []
        self.flow_num = {}

#########################---------- main ----------##########################

    def _test(self):
        self.f = open("/home/guoxiao/iperf_test/path.txt", "w")
        self.stats['flow'] = {}
        self.stats['port'] = {}

        i = 0
        while(i<=20):
            hub.sleep(1)
            print "\n", i
            i = i + 1
        self.get_topology(None)

        self.logger.info("first get topology successful")
        print "\n"
        print "\n"
        self.show_topology()
        print "\n"
        print "\n"
        self.logger.info("first show topology successful")
        i = 0
        while True:
            self.logger.info('begin monitor')
            print "\n"
            print "\n"
            self.show_topology()
            print "\n"
            print "\n"
            for dp in self.datapaths.values():
                self.port_features.setdefault(dp.id, {})
                self._request_stats(dp)
                #self.best_paths = {}
            self.logger.info("send monitor stats successful")
            hub.sleep(1)


            if self.stats['flow'] or self.stats['port']:
                print "\n"
                print "\n"
                self.show_stat('flow')
                print "\n"
                print "\n"
                self.logger.info("show flow information")
                print "\n"
                print "\n"
                self.show_stat('port')
                print "\n"
                print "\n"
                self.logger.info("show port information")
                self._save_bw_graph()
            print "%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%"
            for pack in self.packet_in_table:
                print pack[-2], " --- ", pack[-1]
            print "%%%%%%%%%%%%%%%%%%%%%%---703---%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%"
            if self.path_dict:
                for ip_pair in self.path_dict.keys():
                    print ip_pair[-2], " <---> ", ip_pair[-1], " : ", self.path_dict[ip_pair]
            else:
                pass
            print "%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%"
            self.best_paths = {}

            #print self.flow_speed
            hub.sleep(1)
            if i%2 == 1:
                self.del_path_monitor()
                self.logger.info("delete path momitor running")

                self.forwarding_path_monitor()
                self.logger.info("forwarding path momitor running")
                hub.sleep(1)

            i+=1
            """
            print "\n"
            print "-----------------------switch_port_table-------------------------------"
            print self.switch_port_table
            print "\n"

            print "\n"
            print "--------------------------link_to_port---------------------------------"
            print self.link_to_port
            print "\n"

            print "\n"
            print "-------------------------interior_ports--------------------------------"
            print self.interior_ports
            print "\n"

            print "\n"
            print "--------------------------access_ports---------------------------------"
            print self.access_ports
            print "\n"

            print "\n"
            print "--------------------------access_table---------------------------------"
            print self.access_table
            print "\n"

            print "\n"
            print "--------------------------paths---------------------------------"
            print self.shortest_paths
            print "\n"
            """
    def forwarding_path_monitor(self):
        if 0:
        #if self.path_monitor:
            self.logger.info("begin forwarding path momitor")
            #print self.path_monitor
            hub.sleep(10)
            multi_path = {}
            # path_monitor = {(src_sw, dst_sw):{(ip_src, ip_dst):{'info':(msg, eth_type, ip_src, ip_dst),
            #                                                      'path': []}}}
            for (src_sw, dst_sw) in self.path_monitor.keys():
                self.logger.info("begin path_monitor")
                if len(self.path_monitor[(src_sw, dst_sw)]) >= 2:
                    self.logger.info("entering --> path_monitor[(src_sw, dst_sw)]")
                    for (src_ip, dst_ip) in self.path_monitor[(src_sw, dst_sw)].keys():
                        self.logger.info("entering --> path_monitor[(src_sw, dst_sw)][(src_ip, dst_ip)]")
                        if self.path_monitor[(src_sw, dst_sw)][(src_ip, dst_ip)]:
                            path = self.path_monitor[(src_sw, dst_sw)][(src_ip, dst_ip)]['path']
                            self.logger.info("entering --> path_monitor[path]")
                            path_pingjia = self.usebw_to_num(self.get_min_bw_of_links(self.graph, path, 10000000))
                            multi_path[path_pingjia] = (src_ip, dst_ip)
                            # multi_path = {path_pingjia : (src_ip, dst_ip)}
                            self.logger.info("Multi_Path:   %s ", multi_path)
                            min_pingjia = min(multi_path.keys())
                            self.logger.info("Min_Link_Evaluate:   %s ", min_pingjia)
                            if min_pingjia < 20:
                                self.logger.info("Route Again")
                                (src, dst) = multi_path[min_pingjia]
                                #self.logger.info("best_paths: %s ", self.best_paths)
                                # print self.shortest_paths.get((src, dst)[0]).get((src, dst)[1])
                                self.logger.info("second send forwarding path")
                                msg = self.path_monitor[(src_sw, dst_sw)][(src, dst)]['info'][0]
                                eth_type = self.path_monitor[(src_sw, dst_sw)][(src, dst)]['info'][1]
                                ip_src = self.path_monitor[(src_sw, dst_sw)][(src, dst)]['info'][2]
                                ip_dst = self.path_monitor[(src_sw, dst_sw)][(src, dst)]['info'][3]
                                #self.best_paths = {}
                                #self.second_forwarding(msg, eth_type, ip_src, ip_dst)

                                # second send forwarding path and delete the path information,because only change one time
                            break
                else:
                    continue

    def del_path_monitor(self):
        if 0:
        #if self.path_monitor:
            hub.sleep(5)
            for (src_sw, dst_sw) in self.path_monitor.keys():
                hub.sleep(5)
                self.logger.info("begin del_path_monitor")
                if self.path_monitor[(src_sw, dst_sw)]:
                    self.logger.info("entering --> path_monitor[(src_sw, dst_sw)]")
                    for (src_ip, dst_ip) in self.path_monitor[(src_sw, dst_sw)].keys():
                        hub.sleep(5)
                        self.logger.info("entering --> path_monitor[(src_sw, dst_sw)][(src_ip, dst_ip)]")
                        dst_hop_ip = (src_ip, dst_ip)[-1]
                        if self.path_monitor[(src_sw, dst_sw)][(src_ip, dst_ip)]['path']:
                            self.logger.info("entering --> path_monitor[path]")
                            path = self.path_monitor[(src_sw, dst_sw)][(src_ip, dst_ip)]['path']
                            if len(path) == 1:
                                self.path_monitor[(src_sw, dst_sw)].pop((src_ip, dst_ip))
                                continue
                            for (sw, port) in self.access_table:
                                self.logger.info("search --> (src_sw, first_in_port)")
                                #print (src_ip, dst_ip)[0]
                                #print self.access_table
                                if self.access_table[(sw, port)][0] == (src_ip, dst_ip)[0]:
                                    self.logger.info("search over")
                                    first_in_port = (sw, port)[-1]
                                    first_sw, second_sw = path[0], path[1]
                                    first_out_port, second_in_port = self.link_to_port[(first_sw, second_sw)]
                                    #print first_sw
                                    #print (first_in_port, dst_hop_ip, first_out_port)
                                    try:
                                        if self.flow_speed[first_sw][(first_in_port, dst_hop_ip, first_out_port)][-1] == 0:
                                            #print self.flow_speed[first_sw][(first_in_port, dst_hop_ip, first_out_port)][-1]
                                            self.logger.info("delete path monitor")
                                            #print self.path_monitor
                                            self.path_monitor[(src_sw, dst_sw)].pop((src_ip, dst_ip))
                                            self.logger.info("delete over ")
                                            #print self.path_monitor
                                    except:
                                        continue
                        else:
                            self.path_monitor[(src_sw, dst_sw)].pop((src_ip, dst_ip))
                else:
                    self.path_monitor.pop((src_sw, dst_sw))


#########################---------- handler ----------##########################
    """
    def remove_table_flows(self, dp, match):
        ofproto = dp.ofproto
        parser = dp.ofproto_parser
        flow_mod = parser.OFPFlowMod(datapath=dp, priority=10,
                                        command=ofproto.OFPFC_DELETE,
                                            match=match)
        print "yes,yes,yes,yes,yes,yes,yes,yes,yes,yes"
        dp.send_msg(flow_mod)
        print "delete,delete,delete,delete,delete,delete"

    def send_remove_flow(self, datapath, flow_info):
        parser = datapath.ofproto_parser
        #instruction = []
        match = parser.OFPMatch(eth_type=flow_info[0],
                                   ipv4_src=flow_info[1],
                                      ipv4_dst=flow_info[2])
        print match
        self.remove_table_flows(datapath, match)

    def del_flow(self, datapath):
        #print flow_info
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        match = parser.OFPMatch(eth_type=2048, ipv4_src='10.0.0.1', in_port=1, ipv4_dst='10.0.0.8')
        mod = parser.OFPFlowMod(datapath=datapath, match=match, command=ofproto.OFPPR_DELETE)
        print mod

        datapath.send_msg(mod)
    """

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        msg = ev.msg
        self.logger.info("switch:%s connected", datapath.id)

        # install table-miss flow entry
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                            ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)

    @set_ev_cls(ofp_event.EventOFPStateChange,
                [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def _state_change_handler(self, ev):
        datapath = ev.datapath
        if ev.state == MAIN_DISPATCHER:
            if not datapath.id in self.datapaths:
                self.logger.debug('register datapath: %016x', datapath.id)
                self.datapaths[datapath.id] = datapath
        elif ev.state == DEAD_DISPATCHER:
            if datapath.id in self.datapaths:
                self.logger.debug('unregister datapath: %016x', datapath.id)
                del self.datapaths[datapath.id]

#########################---------- monitor ----------##########################

    def _save_bw_graph(self):
        self.graph = self.create_bw_graph(self.free_bandwidth)
        # print self.free_bandwidth
        self.logger.debug("save_freebandwidth")
        hub.sleep(10)

    def create_bw_graph(self, bw_dict):
        try:
            for link in self.link_to_port:
                (src_dpid, dst_dpid) = link
                (src_port, dst_port) = self.link_to_port[link]
                if src_dpid in bw_dict and dst_dpid in bw_dict:
                    bw_src = bw_dict[src_dpid][src_port]
                    bw_dst = bw_dict[dst_dpid][dst_port]
                    bandwidth = min(bw_src, bw_dst)
                    self.graph[src_dpid][dst_dpid]['bandwidth'] = bandwidth
                else:
                    self.graph[src_dpid][dst_dpid]['bandwidth'] = 0
            self.logger.info("Create bw graph successful")
            return self.graph
        except:
            self.logger.info("Create bw graph exception")
            return self.graph

    def _save_freebandwidth(self, dpid, port_no, speed):
        port_state = self.port_features.get(dpid).get(port_no)
        #print self.port_features

        #print port_state
        # print self.port_features
        if port_state:
            capacity = port_state[2]
            # print "speed: %s" % speed
            curr_bw = self._get_free_bw(capacity, speed)
            # print "curr_bw: %s" % curr_bw
            self.free_bandwidth[dpid].setdefault(port_no, None)
            self.free_bandwidth[dpid][port_no] = curr_bw
        else:
            self.logger.info("Fail in getting port state")

    def _get_free_bw(self, capacity, speed):
        #capacity:Kbps, speed:B/s -->BW:Mbit/s,
        #return max(capacity/10**3 - speed*8/10**6, 0)  #bw:Mbit/s
        return max(100 - speed * 8 / 10 ** 6, 0)        #link set 100M -->capacity should 100M,
                                                        # but I dont replace system.port_capacity

    def _request_stats(self, datapath):
        self.logger.debug('send stats request: %016x', datapath.id)
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        req = parser.OFPFlowStatsRequest(datapath)
        datapath.send_msg(req)

        req = parser.OFPPortStatsRequest(datapath, 0, ofproto.OFPP_ANY)
        datapath.send_msg(req)

        req = parser.OFPPortDescStatsRequest(datapath, 0)
        datapath.send_msg(req)

    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def _flow_stats_reply_handler(self, ev):
        body = ev.msg.body
        dpid = ev.msg.datapath.id
        self.stats['flow'][dpid] = body
        self.flow_stats.setdefault(dpid, {})
        self.flow_speed.setdefault(dpid, {})
        for stat in sorted([flow for flow in body if flow.priority == 1],
                           key=lambda flow: (flow.match.get('in_port'),
                                             flow.match.get('ipv4_dst'))):
            key = (stat.match['in_port'], stat.match.get('ipv4_dst'),
                   stat.instructions[0].actions[0].port)
            value = (stat.packet_count, stat.byte_count,
                     stat.duration_sec, stat.duration_nsec)
            self._save_stats(self.flow_stats[dpid], key, value, 5)

            # Get flow's speed.
            pre = 0
            period = SLEEP_PERIOD
            tmp = self.flow_stats[dpid][key]
            if len(tmp) > 1:
                pre = tmp[-2][1]
                period = self._get_period(tmp[-1][2], tmp[-1][3],
                                          tmp[-2][2], tmp[-2][3])

            speed = self._get_speed(self.flow_stats[dpid][key][-1][1],
                                    pre, period)

            self._save_stats(self.flow_speed[dpid], key, speed, 5)

    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def _port_stats_reply_handler(self, ev):
        body = ev.msg.body
        dpid = ev.msg.datapath.id
        self.stats['port'][dpid] = body
        #print body
        self.free_bandwidth.setdefault(dpid, {})

        for stat in sorted(body, key=attrgetter('port_no')):
            port_no = stat.port_no
            if port_no != ofproto_v1_3.OFPP_LOCAL:
                key = (dpid, port_no)
                value = (stat.tx_bytes, stat.rx_bytes, stat.rx_errors,
                         stat.duration_sec, stat.duration_nsec)

                self._save_stats(self.port_stats, key, value, 5)

                # Get port speed.
                pre = 0
                period = 10
                tmp = self.port_stats[key]
                if len(tmp) > 1:
                    pre = tmp[-2][0] + tmp[-2][1]
                    period = self._get_period(tmp[-1][3], tmp[-1][4],
                                              tmp[-2][3], tmp[-2][4])

                speed = self._get_speed(
                    self.port_stats[key][-1][0] + self.port_stats[key][-1][1],
                    pre, period)

                self._save_stats(self.port_speed, key, speed, 5)
                self._save_freebandwidth(dpid, port_no, speed)

    @set_ev_cls(ofp_event.EventOFPPortDescStatsReply, MAIN_DISPATCHER)
    def port_desc_stats_reply_handler(self, ev):
        msg = ev.msg
        dpid = msg.datapath.id
        ofproto = msg.datapath.ofproto

        config_dict = {ofproto.OFPPC_PORT_DOWN: "Down",
                       ofproto.OFPPC_NO_RECV: "No Recv",
                       ofproto.OFPPC_NO_FWD: "No Farward",
                       ofproto.OFPPC_NO_PACKET_IN: "No Packet-in"}

        state_dict = {ofproto.OFPPS_LINK_DOWN: "Down",
                      ofproto.OFPPS_BLOCKED: "Blocked",
                      ofproto.OFPPS_LIVE: "Live"}

        ports = []
        for p in ev.msg.body:
            ports.append('port_no=%d hw_addr=%s name=%s config=0x%08x '
                         'state=0x%08x curr=0x%08x advertised=0x%08x '
                         'supported=0x%08x peer=0x%08x curr_speed=%d '
                         'max_speed=%d' %
                         (p.port_no, p.hw_addr,
                          p.name, p.config,
                          p.state, p.curr, p.advertised,
                          p.supported, p.peer, p.curr_speed,
                          p.max_speed))
            #print p
            if p.config in config_dict:
                #print p.config
                config = config_dict[p.config]
            else:
                config = "up"

            if p.state in state_dict:
                state = state_dict[p.state]
            else:
                state = "up"

            port_feature = (config, state, p.curr_speed)
            self.port_features[dpid][p.port_no] = port_feature

    @set_ev_cls(ofp_event.EventOFPPortStatus, MAIN_DISPATCHER)
    def _port_status_handler(self, ev):
        msg = ev.msg
        reason = msg.reason
        port_no = msg.desc.port_no
        dpid = msg.datapath.id
        ofproto = msg.datapath.ofproto

        reason_dict = {ofproto.OFPPR_ADD: "added",
                       ofproto.OFPPR_DELETE: "deleted",
                       ofproto.OFPPR_MODIFY: "modified",}

        if reason in reason_dict:

            print "switch%d: port %s %s" % (dpid, reason_dict[reason], port_no)
        else:
            print "switch%d: Illeagal port state %s %s" % (port_no, reason)

    def _save_stats(self, dist, key, value, length):
        if key not in dist:
            dist[key] = []
        dist[key].append(value)

        if len(dist[key]) > length:
            dist[key].pop(0)

    def _get_speed(self, now, pre, period):
        if period:
            return (now - pre) / (period)
        else:
            return 0

    def _get_time(self, sec, nsec):
        return sec + nsec / (10 ** 9)

    def _get_period(self, n_sec, n_nsec, p_sec, p_nsec):
        return self._get_time(n_sec, n_nsec) - self._get_time(p_sec, p_nsec)

    def show_stat(self, type):
        '''
            type: 'port' 'flow'
        '''


        bodys = self.stats[type]
        if (type == 'flow'):
            print('datapath         ''   in-port        ip-dst      '
                  'out-port packets  bytes  flow-speed(B/s)')
            print('---------------- ''  -------- ----------------- '
                  '-------- -------- -------- -----------')
            for dpid in bodys.keys():
                for stat in sorted(
                        [flow for flow in bodys[dpid] if flow.priority == 1],
                        key=lambda flow: (flow.match.get('in_port'),
                                          flow.match.get('ipv4_dst'))):
                    print('%016x %8x %17s %8x %8d %8d %8.1f' % (
                        dpid,
                        stat.match['in_port'], stat.match['ipv4_dst'],
                        stat.instructions[0].actions[0].port,
                        stat.packet_count, stat.byte_count,
                        abs(self.flow_speed[dpid][
                                (stat.match.get('in_port'),
                                 stat.match.get('ipv4_dst'),
                                 stat.instructions[0].actions[0].port)][-1])))
            print '\n'

        if (type == 'port'):
            print('datapath             port   ''rx-pkts  rx-bytes rx-error '
                  'tx-pkts  tx-bytes tx-error  port-speed(Mbit/s)'
                  ' current-capacity(Mbps)  '
                  'port-stat   link-stat')
            print('----------------   -------- ''-------- -------- -------- '
                  '-------- -------- -------- '
                  '----------------  ----------------   '
                  '   -----------    -----------')
            format = '%016x %8x %8d %8d %8d %8d %8d %8d %8.4f %16d %16s %16s'
            for dpid in bodys.keys():
                for stat in sorted(bodys[dpid], key=attrgetter('port_no')):
                    if stat.port_no != ofproto_v1_3.OFPP_LOCAL:
                        print(format % (
                            dpid, stat.port_no,
                            stat.rx_packets, stat.rx_bytes, stat.rx_errors,
                            stat.tx_packets, stat.tx_bytes, stat.tx_errors,
                            abs(self.port_speed[(dpid, stat.port_no)][-1])*8/10**6,
                            self.port_features[dpid][stat.port_no][2]/10**3,
                            self.port_features[dpid][stat.port_no][0],
                            self.port_features[dpid][stat.port_no][1]))
            print '\n'
            #print 'port_stats'
            #print self.port_stats
            #print '\n'
            #print 'port_speed'
            #print self.port_speed
            #print '\n'
            #print 'flow_stats'
            #print self.flow_stats
            #print '\n'
            #print 'flow_speed'
            #print self.flow_speed
            #print '\n'
            #print 'stats'
            #print self.stats
            #print '\n'

#########################---------- awareness ----------##########################

    def create_port_map(self, switch_list):
        for sw in switch_list:
            dpid = sw.dp.id
            self.switch_port_table.setdefault(dpid, set())
            self.interior_ports.setdefault(dpid, set())
            self.access_ports.setdefault(dpid, set())

            for p in sw.ports:
                self.switch_port_table[dpid].add(p.port_no)

    # get links`srouce port to dst port  from link_list,
    # link_to_port:(src_dpid,dst_dpid)->(src_port,dst_port)
    def create_interior_links(self, link_list):
        for link in link_list:
            src = link.src
            dst = link.dst
            self.link_to_port[
                (src.dpid, dst.dpid)] = (src.port_no, dst.port_no)

            # find the access ports and interiorior ports
            if link.src.dpid in self.switches:
                self.interior_ports[link.src.dpid].add(link.src.port_no)
            if link.dst.dpid in self.switches:
                self.interior_ports[link.dst.dpid].add(link.dst.port_no)

    # get ports without link into access_ports
    def create_access_ports(self):
        for sw in self.switch_port_table:
            self.access_ports[sw] = self.switch_port_table[
                sw] - self.interior_ports[sw]

    def usebw_to_num(self, usebw):
        if usebw <= 131072:
            return 10
        elif usebw <= (131072 * 2):
            return 20
        elif usebw <= (131072 * 3):
            return 30
        elif usebw <= (131072 * 4):
            return 40
        elif usebw <= (131072 * 5):
            return 50
        elif usebw <= (131072 * 6):
            return 60
        elif usebw <= (131072 * 7):
            return 70
        elif usebw <= (131072 * 8):
            return 80
        elif usebw <= (131072 * 9):
            return 90
        elif usebw <= (131072 * 10):
            return 100
        elif usebw > (131072 * 10):
            return 200

    def set_weight(self, link_list):
        for src in self.switch_port_table.keys():
            for dst in self.switch_port_table.keys():
                if (src, dst) in link_list:
                    src_port = self.link_to_port[(src, dst)][0]
                    # print 'port_speed'
                    # print self.port_speed
                    # print 'link_to_port'
                    # print self.link_to_port
                    # self.graph[src][dst] = self.map[(src, dst)]
                    if self.port_speed:
                        self.graph[src][dst] = self.usebw_to_num(self.port_speed[(src, src_port)][-1])
        # print 'aidingyi'
        return self.graph

#######################------------two get graph----------------###########################
    """
    # get Adjacency matrix from link_to_port
    def get_graph(self, link_list):
        for src in self.switch_port_table.keys():
            self.graph.setdefault(src, {})
            for dst in self.switch_port_table.keys():
                self.graph[src].setdefault(dst, float('inf'))
                if src == dst:
                    self.graph[src][dst] = 0
                elif (src, dst) in link_list:
                    self.graph[src][dst] = 1

        return self.graph
    """

    def get_graph(self, link_list):
        for src in self.switches:
            for dst in self.switches:
                self.graph.add_edge(src, dst, weight=float('inf'))
                if src == dst:
                    self.graph.add_edge(src, dst, weight=0)
                elif (src, dst) in link_list:
                    self.graph.add_edge(src, dst, weight=1)
        return self.graph

#############################################################################################

    #events = [event.EventSwitchEnter,
     #         event.EventSwitchLeave, event.EventPortAdd,
     #         event.EventPortDelete, event.EventPortModify,
     #         event.EventLinkAdd, event.EventLinkDelete]
   # @set_ev_cls(events)
    def get_topology(self, ev):
        switch_list = get_switch(self.topology_api_app, None)

        print "\n"
        print "-----------------------switch_list-------------------------------"
        print switch_list, "\n", len(switch_list)
        print "\n"

        #hub.sleep(30)
        self.create_port_map(switch_list)
        self.switches = self.switch_port_table.keys()
        links = get_link(self.topology_api_app, None)

        print "\n"
        print "-----------------------link_list-------------------------------"
        print links, "\n", len(links)
        print "\n"

        self.create_interior_links(links)
        self.create_access_ports()
        self.get_graph(self.link_to_port.keys())

        self.nodes_classified()
        self.flow_num_init()
        print self.flow_num
        j = 0
        while (j <= 10):
            hub.sleep(1)
            print "\n", j
            j = j + 1
        #self.shortest_paths = self.my_shortest_paths()
        # two Algorithm module to choose
        """
        self.get_shortest_paths()
        """
        self.shortest_paths = self.all_k_shortest_paths(
                                    self.graph, weight='weight', k=5)

        #print self.shortest_paths

#####################################################################################
    def nodes_classified(self):
        k = int(len(self.switches) / 5)
        self.core_node_list = self.switches[:k]
        self.aggregation_node_list = self.switches[k:3 * k]
        self.edge_node_list = self.switches[3 * k:5 * k]

        for pod in xrange(k):
            pod_node_list = []
            pod_node_list = self.aggregation_node_list[pod * 2:pod * 2 + 2] + self.edge_node_list[pod * 2:pod * 2 + 2]
            self.pod_list.append(pod_node_list)

######################################################################################
    def flow_num_init(self):
        for node in self.switches:
            self.flow_num.setdefault(node, 0)

#######################################################################################

    def my_shortest_paths(self):
        _graph = copy.deepcopy(self.graph)
        paths = {}
        for src in self.edge_node_list:
            paths.setdefault(src, {src: []})
            for dst in self.edge_node_list:
                if src == dst:
                    paths[src][dst] = [src]
                else:
                    paths[src].setdefault(dst, [])
                    for pod in self.pod_list:
                        if src in pod and dst in pod:
                            for node in pod:
                                if node != src and node != dst:
                                    paths[src][dst].append([src, node, dst])
                    """
                    if paths[src][dst]:
                        generator = nx.shortest_simple_paths(_graph, source=src, target=dst, weight='weight')
                        k = 6
                        try:
                            for path in generator:
                                if k <= 0:
                                    break
                                elif path not in paths[src][dst]:
                                    paths[src][dst].append(path)
                                    k -= 1
                        except:
                            continue
                    """
                    if not paths[src][dst]:  # indicate (src,dst) do not in a pod
                        for core in self.core_node_list:
                            for aggregation_up in self.aggregation_node_list:
                                if (src, aggregation_up) in self.link_to_port.keys() \
                                        and (aggregation_up, core) in self.link_to_port.keys():
                                    for aggregation_down in self.aggregation_node_list:
                                        if (core, aggregation_down) in self.link_to_port.keys() \
                                                and (aggregation_down, dst) in self.link_to_port.keys():
                                            paths[src][dst].append([src, aggregation_up, core, aggregation_down, dst])
                        """
                        generator = nx.shortest_simple_paths(_graph, source=src, target=dst, weight='weight')
                        k = 4
                        try:
                            for path in generator:
                                if k <= 0:
                                    break
                                elif path not in paths[src][dst]:
                                    paths[src][dst].append(path)
                                    k -= 1
                        except:
                            continue"""
        return paths

#######################################################################################



#####################--------------Algorithm module two------------------######################

    def k_shortest_paths(self, graph, src, dst, weight='weight', k=1):
        generator = nx.shortest_simple_paths(graph, source=src,
                                             target=dst, weight=weight)
        shortest_paths = []
        try:
            for path in generator:
                if k <= 0:
                    break
                shortest_paths.append(path)
                k -= 1
            return shortest_paths
        except:
            self.logger.debug("No path between %s and %s" % (src, dst))

    def all_k_shortest_paths(self, graph, weight='weight', k=1):
        _graph = copy.deepcopy(graph)
        paths = {}

        # find ksp in graph.

        for src in _graph.nodes():         # only calculate edge node,do not all node
            paths.setdefault(src, {src: [[src] for i in xrange(k)]})
            for dst in _graph.nodes():
                if src == dst:
                    continue
                paths[src].setdefault(dst, [])
                paths[src][dst] = self.k_shortest_paths(_graph, src, dst,
                                                        weight=weight, k=k)
        return paths

###########------------Algorithm module one------------------#####################
    """
    def floyd_dict(self, graph):
        floyd_path = {}
        floyd_map = copy.deepcopy(graph)

        for k in self.switch_port_table.keys():
            for i in self.switch_port_table.keys():
                floyd_path.setdefault(i, {})
                for j in self.switch_port_table.keys():
                    floyd_path[i].setdefault(j, [i, j])
                    floyd_path[i].setdefault(k, [i, k])
                    floyd_path[k].setdefault(j, [k, j])
                    if floyd_map[i][j] > (floyd_map[i][k] + floyd_map[k][j]):
                        floyd_map[i][j] = floyd_map[i][k] + floyd_map[k][j]
                        floyd_path[i][j] = floyd_path[i][k] + floyd_path[k][j][1:]

        return floyd_path

    def get_shortest_paths(self):
        self.shortest_paths = self.floyd_dict(self.graph)
        return self.shortest_paths
    """
################################################################################
    """
    def get_path(self, src, dst):
        return self.shortest_paths[src][dst]
    """

    def get_path(self, src, dst):
        try:
            path = self.ECMP_algorithm(src, dst, self.shortest_paths)
            self.logger.debug("get path successful")
            return path
        except:
            path = self.ECMP_algorithm(src, dst, self.shortest_paths)
            self.logger.debug("get path failure")
            return path

####################--------------ECMP----------------#########################
    def ECMP_algorithm(self, src, dst, shortest_paths):
        print src
        print dst

        paths = shortest_paths[src][dst]
        path_num = self.flow_num[src] % 4     #4 is path numbers
        best_path = paths[path_num]

        print "\n"
        print "        s" + str(src)+" <---> " + "s" + str(dst) + " :", paths
        print "\n"

        print "\n"
        print "        Flow_num:", self.flow_num[src], "Hash:", path_num
        print "\n"

        print "        best_path:", best_path
        print "\n"
        self.flow_num[src] += 1
        return best_path
############################################################################################

    def get_host_location(self, host_ip):
        for key in self.access_table.keys():
            if self.access_table[key][0] == host_ip:
                return key
        #self.logger.info("%s location is not found." % host_ip)
        return None

    def register_access_info(self, dpid, in_port, ip, mac):
        if in_port in self.access_ports[dpid]:
            if (dpid, in_port) in self.access_table:
                if self.access_table[(dpid, in_port)] == (ip, mac):
                    return
                else:
                    self.access_table[(dpid, in_port)] = (ip, mac)
                    return
            else:
                self.access_table.setdefault((dpid, in_port), None)
                self.access_table[(dpid, in_port)] = (ip, mac)
                return

#########################---------- forwarding ----------##########################

    def shortest_forwarding(self, msg, eth_type, ip_src, ip_dst):
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']

        result = self.get_sw(datapath.id, in_port, ip_src, ip_dst)
        if result:
            src_sw, dst_sw = result[0], result[1]
            if dst_sw:
                path = self.get_path(src_sw, dst_sw)

                self.logger.info("        [PATH]%s<-->%s: %s" % (ip_src, ip_dst, path))
                print '\n'
                print '\n'

                self.path_dict[(ip_src, ip_dst)] = path

                path_msg = ip_src + " <--> " + ip_dst + " : " + str(path)
                #self.f.write(path_msg)

                #print >> self.f, "[PATH]%s<-->%s: %s" % (ip_src, ip_dst, path)
                print >> self.f, path_msg

                flow_info = (eth_type, ip_src, ip_dst, in_port)

                self.install_flow(self.datapaths,
                                  self.link_to_port,
                                  self.access_table, path,
                                  flow_info, msg.buffer_id, msg.data)

                # path information
                # path_monitor = {(src_sw, dst_sw):{(ip_src, ip_dst):{'info':(msg, eth_type, ip_src, ip_dst), 'path': []}}}
                if not (src_sw, dst_sw) in self.path_monitor:
                    self.path_monitor.setdefault((src_sw, dst_sw))
                    self.path_monitor[(src_sw, dst_sw)] = {}
                    self.path_monitor[(src_sw, dst_sw)].setdefault((ip_src, ip_dst))
                    self.path_monitor[(src_sw, dst_sw)][(ip_src, ip_dst)] = {'info': (msg, eth_type, ip_src, ip_dst),
                                                                             'path': path}
                elif not (ip_src, ip_dst) in self.path_monitor[(src_sw, dst_sw)]:
                    self.path_monitor[(src_sw, dst_sw)][(ip_src, ip_dst)] = {'info': (msg, eth_type, ip_src, ip_dst),
                                                                             'path': path}
                elif path != self.path_monitor[(src_sw, dst_sw)][(ip_src, ip_dst)]['path']:
                    self.path_monitor[(src_sw, dst_sw)][(ip_src, ip_dst)]['path'] = path
                #self.logger.info("Path_Monitor:   %s ", self.path_monitor)
        #self.packet_in_table.remove((ip_src, ip_dst))
        return

    def second_forwarding(self, msg, eth_type, ip_src, ip_dst):
        datapath = msg.datapath
        print datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']

        result = self.get_sw(datapath.id, in_port, ip_src, ip_dst)
        if result:
            src_sw, dst_sw = result[0], result[1]
            if dst_sw:
                path = self.get_path(src_sw, dst_sw)
                self.logger.info("second--[PATH]%s<-->%s: %s" % (ip_src, ip_dst, path))

                flow_info = (eth_type, ip_src, ip_dst, in_port)
                self.install_flow_second(self.datapaths,
                                         self.link_to_port,
                                         self.access_table, path,
                                         flow_info, msg.buffer_id, msg.data)

                pre_path = self.path_monitor[(src_sw, dst_sw)][(ip_src, ip_dst)]['path']

                # path_monitor = {(src_sw, dst_sw):{(ip_src, ip_dst):{'info':(msg, eth_type, ip_src, ip_dst), 'path': []}}}
                if not (src_sw, dst_sw) in self.path_monitor:
                    self.path_monitor.setdefault((src_sw, dst_sw))
                    self.path_monitor[(src_sw, dst_sw)] = {}
                    self.path_monitor[(src_sw, dst_sw)].setdefault((ip_src, ip_dst))
                    self.path_monitor[(src_sw, dst_sw)][(ip_src, ip_dst)] = {'info': (msg, eth_type, ip_src, ip_dst),
                                                                             'path': path}
                elif not (ip_src, ip_dst) in self.path_monitor[(src_sw, dst_sw)]:
                    self.path_monitor[(src_sw, dst_sw)][(ip_src, ip_dst)] = {'info': (msg, eth_type, ip_src, ip_dst),
                                                                             'path': path}
                elif path != self.path_monitor[(src_sw, dst_sw)][(ip_src, ip_dst)]['path']:
                    self.path_monitor[(src_sw, dst_sw)][(ip_src, ip_dst)]['path'] = path
        return

    def get_sw(self, dpid, in_port, src, dst):
        src_sw = dpid
        dst_sw = None

        src_location = self.get_host_location(src)
        if in_port in self.access_ports[dpid]:
            if (dpid, in_port) == src_location:
                src_sw = src_location[0]
            else:
                return None

        dst_location = self.get_host_location(dst)
        if dst_location:
            dst_sw = dst_location[0]

        return src_sw, dst_sw

    def install_flow(self, datapaths, link_to_port, access_table, path,
                     flow_info, buffer_id, data=None):
        ''' path=[dpid1, dpid2...]
            flow_info=(eth_type, src_ip, dst_ip, in_port)
        '''
        if path is None or len(path) == 0:
            self.logger.info("Path error!")
            return
        in_port = flow_info[3]
        first_dp = datapaths[path[0]]
        out_port = first_dp.ofproto.OFPP_LOCAL
        back_info = (flow_info[0], flow_info[2], flow_info[1])
        # inter_link
        if len(path) > 2:
            for i in xrange(1, len(path) - 1):
                port = self.get_link_to_port(link_to_port, path[i - 1], path[i])
                port_next = self.get_link_to_port(link_to_port,
                                                  path[i], path[i + 1])
                if port and port_next:
                    src_port, dst_port = port[1], port_next[0]
                    datapath = datapaths[path[i]]
                    self.send_flow_mod(datapath, flow_info, src_port, dst_port)
                    self.send_flow_mod(datapath, back_info, dst_port, src_port)
                    self.logger.debug("inter_link flow install")
        if len(path) > 1:
            # the last flow entry: tor -> host
            port_pair = self.get_link_to_port(link_to_port, path[-2], path[-1])
            if port_pair is None:
                self.logger.info("Port is not found")
                return
            src_port = port_pair[1]

            dst_port = self.get_port(flow_info[2], access_table)
            if dst_port is None:
                self.logger.info("Last port is not found.")
                return

            last_dp = datapaths[path[-1]]
            self.send_flow_mod(last_dp, flow_info, src_port, dst_port)
            self.send_flow_mod(last_dp, back_info, dst_port, src_port)

            # the first flow entry
            port_pair = self.get_link_to_port(link_to_port, path[0], path[1])
            if port_pair is None:
                self.logger.info("Port not found in first hop.")
                return
            out_port = port_pair[0]
            self.send_flow_mod(first_dp, flow_info, in_port, out_port)
            self.send_flow_mod(first_dp, back_info, out_port, in_port)
            self.send_packet_out(first_dp, buffer_id, in_port, out_port, data)

        # src and dst on the same datapath
        else:
            out_port = self.get_port(flow_info[2], access_table)
            if out_port is None:
                self.logger.info("Out_port is None in same dp")
                return
            self.send_flow_mod(first_dp, flow_info, in_port, out_port)
            self.send_flow_mod(first_dp, back_info, out_port, in_port)
            self.send_packet_out(first_dp, buffer_id, in_port, out_port, data)

    def install_flow_second(self, datapaths, link_to_port, access_table, path,
                                    flow_info, buffer_id, data=None):
        ''' path=[dpid1, dpid2...]
            flow_info=(eth_type, src_ip, dst_ip, in_port)
        '''
        if path is None or len(path) == 0:
            self.logger.info("Path error!")
            return
        in_port = flow_info[3]
        first_dp = datapaths[path[0]]
        out_port = first_dp.ofproto.OFPP_LOCAL
        back_info = (flow_info[0], flow_info[2], flow_info[1])
        # inter_link
        if len(path) > 2:
            for i in xrange(1, len(path) - 1):
                port = self.get_link_to_port(link_to_port,
                                                    path[i - 1], path[i])
                port_next = self.get_link_to_port(link_to_port,
                                                         path[i], path[i + 1])
                if port and port_next:
                    src_port, dst_port = port[1], port_next[0]
                    datapath = datapaths[path[i]]
                    self.send_flow_mod_second(datapath, flow_info, src_port, dst_port)
                    self.send_flow_mod_second(datapath, back_info, dst_port, src_port)
                    self.logger.debug("inter_link flow install")
        if len(path) > 1:
            # the last flow entry: tor -> host
            port_pair = self.get_link_to_port(link_to_port,
                                                     path[-2], path[-1])
            if port_pair is None:
                self.logger.info("Port is not found")
                return
            src_port = port_pair[1]

            dst_port = self.get_port(flow_info[2], access_table)
            if dst_port is None:
                self.logger.info("Last port is not found.")
                return

            last_dp = datapaths[path[-1]]
            self.send_flow_mod_second(last_dp, flow_info, src_port, dst_port)
            self.send_flow_mod_second(last_dp, back_info, dst_port, src_port)

            # the first flow entry
            port_pair = self.get_link_to_port(link_to_port,
                                                     path[0], path[1])
            if port_pair is None:
                self.logger.info("Port not found in first hop.")
                return
            out_port = port_pair[0]
            self.send_flow_mod_second(first_dp, flow_info, in_port, out_port)
            self.send_flow_mod_second(first_dp, back_info, out_port, in_port)
            self.send_packet_out(first_dp, buffer_id, in_port, out_port, data)

        # src and dst on the same datapath
        else:
            out_port = self.get_port(flow_info[2], access_table)
            if out_port is None:
                self.logger.info("Out_port is None in same dp")
                return
            self.send_flow_mod_second(first_dp, flow_info, in_port, out_port)
            self.send_flow_mod_second(first_dp, back_info, out_port, in_port)
            self.send_packet_out(first_dp, buffer_id, in_port, out_port, data)

    def get_link_to_port(self, link_to_port, src_dpid, dst_dpid):
        if (src_dpid, dst_dpid) in link_to_port:
            return link_to_port[(src_dpid, dst_dpid)]
        else:
            self.logger.info("dpid:%s->dpid:%s is not in links" % (
                src_dpid, dst_dpid))
            return None

    def get_port(self, dst_ip, access_table):
        # access_table: {(sw,port) :(ip, mac)}
        if access_table:
            if isinstance(access_table.values()[0], tuple):
                for key in access_table.keys():
                    if dst_ip == access_table[key][0]:
                        dst_port = key[1]
                        return dst_port
        return None

    def show_topology(self):
        switch_num = len(self.graph.nodes())
        if self.pre_graph != self.graph :
            print "      --------------------------Topo Link--------------------------"
            print '%10s' % ("switch"),
            for i in xrange(1, switch_num + 1):
                print '%10d' % i,
            print ""
            for i in self.graph.nodes():
                print '%10d' % i,
                for j in self.graph[i].values():
                    print '%10.0f' % j['weight'],
                print ""
            self.pre_graph = copy.deepcopy(self.graph)

        if self.pre_link_to_port != self.link_to_port :
            print "     --------------------------Link Port---------------------------"
            print '%10s' % ("switch"),
            for i in xrange(1, switch_num + 1):
                print '%10d' % i,
            print ""
            for i in xrange(1, switch_num + 1):
                print '%10d' % i,
                for j in xrange(1, switch_num + 1):
                    if (i, j) in self.link_to_port.keys():
                        print '%10s' % str(self.link_to_port[(i, j)]),
                    else:
                        print '%10s' % "No-link",
                print ""
            self.pre_link_to_port = copy.deepcopy(self.link_to_port)

        if self.pre_access_table != self.access_table :
            print "      -------------------------Access Host--------------------------"
            print '%10s' % ("switch"), '%12s' % "Host"
            if not self.access_table.keys():
                print "    NO found host"
            else:
                for tup in self.access_table:
                    print '%10d:    ' % tup[0], self.access_table[tup]
            self.pre_access_table = copy.deepcopy(self.access_table)

#############-----------information between controller and switch--------------#################

    def add_flow(self, dp, p, match, actions, idle_timeout=0, hard_timeout=0):
        ofproto = dp.ofproto
        parser = dp.ofproto_parser

        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,
                                             actions)]

        mod = parser.OFPFlowMod(datapath=dp, priority=p,
                                idle_timeout=idle_timeout,
                                hard_timeout=hard_timeout,
                                match=match, command=ofproto.OFPFC_ADD, instructions=inst)
        dp.send_msg(mod)

    def send_flow_mod(self, datapath, flow_info, src_port, dst_port):
        parser = datapath.ofproto_parser
        actions = []
        actions.append(parser.OFPActionOutput(dst_port))

        match = parser.OFPMatch(
            in_port=src_port, eth_type=flow_info[0],
            ipv4_src=flow_info[1], ipv4_dst=flow_info[2])
        #print match

        self.add_flow(datapath, 10, match, actions,
                      idle_timeout=30, hard_timeout=80)

    def send_flow_mod_second(self, datapath, flow_info, src_port, dst_port):
        parser = datapath.ofproto_parser
        actions = []
        actions.append(parser.OFPActionOutput(dst_port))

        match = parser.OFPMatch(
            in_port=src_port, eth_type=flow_info[0],
            ipv4_src=flow_info[1], ipv4_dst=flow_info[2])

        self.add_flow(datapath, 5, match, actions,
                      idle_timeout=100, hard_timeout=200)

    def _build_packet_out(self, datapath, buffer_id, src_port, dst_port, data):
        actions = []
        if dst_port:
            actions.append(datapath.ofproto_parser.OFPActionOutput(dst_port))

        msg_data = None
        if buffer_id == datapath.ofproto.OFP_NO_BUFFER:
            if data is None:
                return None
            msg_data = data

        out = datapath.ofproto_parser.OFPPacketOut(
            datapath=datapath, buffer_id=buffer_id,
            data=msg_data, in_port=src_port, actions=actions)
        return out

    def send_packet_out(self, datapath, buffer_id, src_port, dst_port, data):
        out = self._build_packet_out(datapath, buffer_id,
                                     src_port, dst_port, data)
        if out:
            datapath.send_msg(out)

    def flood(self, msg):
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        for dpid in self.access_ports:
            for port in self.access_ports[dpid]:
                if (dpid, port) not in self.access_table.keys():
                    datapath = self.datapaths[dpid]
                    out = self._build_packet_out(
                        datapath, ofproto.OFP_NO_BUFFER,
                        ofproto.OFPP_CONTROLLER, port, msg.data)
                    datapath.send_msg(out)
        self.logger.debug("Flooding msg")

    def arp_forwarding(self, msg, src_ip, dst_ip):
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        result = self.get_host_location(dst_ip)
        if result:  # host record in access table.
            datapath_dst, out_port = result[0], result[1]
            datapath = self.datapaths[datapath_dst]
            out = self._build_packet_out(datapath, ofproto.OFP_NO_BUFFER,
                                         ofproto.OFPP_CONTROLLER,
                                         out_port, msg.data)
            datapath.send_msg(out)
            self.logger.debug("Reply ARP to knew host")
        else:
            self.flood(msg)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        '''
            In packet_in handler, we need to learn access_table by ARP.
            Therefore, the first packet from UNKOWN host MUST be ARP.
        '''
        msg = ev.msg
        datapath = msg.datapath

        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']
        pkt = packet.Packet(msg.data)

        eth_type = pkt.get_protocols(ethernet.ethernet)[0].ethertype
        arp_pkt = pkt.get_protocol(arp.arp)
        ip_pkt = pkt.get_protocol(ipv4.ipv4)

        if isinstance(arp_pkt, arp.arp):
            self.logger.debug("ARP processing")
            # record the access info
            self.register_access_info(datapath.id, in_port, arp_pkt.src_ip, arp_pkt.src_mac)
            self.arp_forwarding(msg, arp_pkt.src_ip, arp_pkt.dst_ip)

        if isinstance(ip_pkt, ipv4.ipv4):
            self.logger.debug("IPV4 processing")
            if len(pkt.get_protocols(ethernet.ethernet)):
                eth_type = pkt.get_protocols(ethernet.ethernet)[0].ethertype
                #print eth_type, ip_pkt.src, ip_pkt.dst
                packet_msg = (ip_pkt.src, ip_pkt.dst)
                if packet_msg in self.packet_in_table:
                    pass
                else:
                    self.packet_in_table.append(packet_msg)
                    self.shortest_forwarding(msg, eth_type, ip_pkt.src, ip_pkt.dst)