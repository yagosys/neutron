from ginkgo import Service

import eventlet
import os
import sys
sys.path.insert(0, os.getcwd())
from quantum.server import main as server
#eventlet.monkey_patch(thread=False)

import uuid
import time
import errno
import socket
import subprocess
import vnc_cfg_api_server

import unittest
from vnc_api import *

import json
sys.path.insert(2, '/opt/stack/python-quantumclient')
from pprint import pformat
from quantumclient.quantum import client
from quantumclient.client import HTTPClient
from quantumclient.common import exceptions

CASS_SVR_IP = '127.0.0.1'
CASS_SVR_PORT = '9160'
ZK_SVR_IP = '127.0.0.1'
ZK_SVR_PORT = '2181'
IFMAP_SVR_IP = '127.0.0.1'
IFMAP_SVR_PORT = '8443'
# publish user
IFMAP_SVR_USER = 'test'
IFMAP_SVR_PASSWD = 'test'
# subscribe users
IFMAP_SVR_USER2 = 'test2'
IFMAP_SVR_PASSWD2 = 'test2'
IFMAP_SVR_USER3 = 'test3'
IFMAP_SVR_PASSWD3 = 'test3'

API_SVR_IP = '127.0.0.1'
API_SVR_PORT = '8082'
QUANTUM_SVR_IP = '127.0.0.1'
QUANTUM_SVR_PORT = '9696'
BGP_SVR_PORT = '9023'
BGP_SANDESH_PORT = '9024'

IFMAP_SVR_LOC='/home/stack/source/ifmap-server/'
QUANTUM_SVR_LOC='/opt/stack/quantum/'
#SCHEMA_TRANSFORMER_LOC='/usr/local/lib/python2.7/dist-packages/schema_transformer-0.1dev-py2.7.egg/schema_transformer/'
SCHEMA_TRANSFORMER_LOC='/home/contrail/source/ctrlplane/src/cfgm/schema-transformer/'
BGP_SVR_ROOT='/home/contrail/source/ctrlplane/'

class CRUDTestCase(unittest.TestCase):
    def setUp(self):
        httpclient = HTTPClient(username='admin',
                                tenant_name='admin',
                                password='contrail123',
                                #region_name=self._region_name,
                                auth_url='http://localhost:5000/v2.0')
        httpclient.authenticate()
        
        #OS_URL = httpclient.endpoint_url
        OS_URL = 'http://%s:%s/' %(QUANTUM_SVR_IP, QUANTUM_SVR_PORT)
        OS_TOKEN = httpclient.auth_token
        self._quantum = client.Client('2.0', endpoint_url=OS_URL, token = OS_TOKEN)
    #end setUp
        
    def _test_network(self):
        # Create; Verify with show + list 
        net_name = 'vn1'
        net_req = {'name': net_name}
        net_rsp = self._quantum.create_network({'network': net_req})
        net_admin_state = net_rsp['network']['admin_state_up']
        # TODO create with partial perms (only user)

        # Read
        net_id = net_rsp['network']['id']
        net_rsp = self._quantum.show_network(net_id)
        self.assertEqual(net_rsp['network']['name'], net_name)

        net_rsp = self._quantum.list_networks()
        self.assertTrue(net_name in [network['name'] \
                                     for network in net_rsp['networks']])

        # Update property
        net_req = {'admin_state_up': not net_admin_state}
        net_rsp = self._quantum.update_network(net_id, {'network': net_req})
        self.assertNotEqual(net_admin_state,
                            net_rsp['network']['admin_state_up'])
 
        # Delete; Verify with show + list
        self._quantum.delete_network(net_id)

        with self.assertRaisesRegexp(exceptions.QuantumClientException,
                                     'could not be found') as e:
            self._quantum.show_network(net_id)

        net_rsp = self._quantum.list_networks()
        self.assertFalse(net_name in [network['name'] \
                                     for network in net_rsp['networks']])
    #end test_network

    def test_subnet(self):
        # Create; Verify with show + list 
        param = {'contrail:fq_name': [VirtualNetwork().get_fq_name()]}
        nets = self._quantum.list_networks(**param)['networks']
        self.assertEqual(len(nets), 1)
        net_id = nets[0]['id']

        ipam_fq_name = NetworkIpam().get_fq_name()

        cidr = u'1.1.1.0/24'
        gw = u'1.1.1.254'
        subnet_req = {'network_id': net_id,
                      'cidr': cidr,
                      'ip_version': 4,
                      'contrail:ipam_fq_name': ipam_fq_name}
        subnet_rsp = self._quantum.create_subnet({'subnet': subnet_req})
        subnet_cidr = subnet_rsp['subnet']['cidr']
        subnet_gw = subnet_rsp['subnet']['gateway_ip']
        self.assertEqual(subnet_cidr, cidr)
        self.assertEqual(subnet_gw, gw)

    #end test_subnet

    def _test_same_name(self):
        print "Creating net with name vn1"
        net_name = 'vn1'
        net_req = {'name': net_name}
        net_rsp = self._quantum.create_network({'network': net_req})

        print "Creating ipam with name vn1"
        ipam_req = {'name': net_name}
        ipam_rsp = self._quantum.create_ipam({'ipam': ipam_req})

        print "Making sure no duplicates in net-list and ipam-list"
        net_name_list = [net['name'] for net in self._quantum.list_networks()['networks']]
        net_name_set = set(net_name_list)
        self.assertEqual(len(net_name_list), len(net_name_set))

        ipam_name_list = [ipam['name'] for ipam in self._quantum.list_ipams()['ipams']]
        ipam_name_set = set(ipam_name_list)
        self.assertEqual(len(ipam_name_list), len(ipam_name_set))
    #end test_same_name

    def _test_port(self):
        print "Creating network VN1, subnet 10.1.1.0/24"
        net_req = {'name': 'vn1', 'tenant_id': 'test-tenant'}
        net_rsp = self._quantum.create_network({'network': net_req})
        net1_id = net_rsp['network']['id']
        net1_fq_name = net_rsp['network']['contrail:fq_name']
        net1_fq_name_str = ':'.join(net1_fq_name)
        sn1_id = self._create_subnet(u'10.1.1.0/24', net1_id)

        print "Creating port"
        instance_id = str(uuid.uuid4())
        port_req = {'network_id': net1_id, 'tenant_id': 'test-tenant',
                    'device_id': instance_id,
                    'compute_node_id': 'test-server'}
        port_rsp = self._quantum.create_port({'port': port_req})
        port_id = port_rsp['port']['id']
        port_admin_state = port_rsp['port']['admin_state_up']

        print "Reading port"
        port_rsp = self._quantum.show_port(port_id)
        self.assertEqual(port_rsp['port']['device_id'], instance_id)
        fixed_ips = port_rsp['port']['fixed_ips']
        self.assertEqual(len(fixed_ips), 1)
        self.assertEqual(fixed_ips[0]['subnet_id'], sn1_id)
        #TODO assert addr is in subnet and not in reserved range

        print "Updating port"
        port_req = {'admin_state_up': not port_admin_state}
        port_rsp = self._quantum.update_port(port_id, {'port': port_req})
        self.assertNotEqual(port_admin_state,
                            port_rsp['port']['admin_state_up'])

        print "Listing port"
        port_rsp = self._quantum.list_ports(device_id = [instance_id])
        self.assertIn(port_id, [port['id'] for port in port_rsp['ports']])
        port_rsp = self._quantum.list_ports(tenant_id = ['test-tenant'])
        self.assertIn(port_id, [port['id'] for port in port_rsp['ports']])

        # Delete; Verify with show + list
        print "Deleting port"
        self._quantum.delete_port(port_id)

        with self.assertRaises(exceptions.QuantumClientException) as e:
            self._quantum.show_port(port_id)

        port_rsp = self._quantum.list_ports(device_id = [instance_id])
        self.assertFalse(port_id in [port['id'] \
                                     for port in port_rsp['ports']])
    #end test_port

    def _test_policy(self):
        print "Creating policy pol1"
        np_rules = [PolicyRuleType(None, '<>', 'pass', 'any',
                        [AddressType(virtual_network = 'local')], [PortType(-1, -1)], None,
                        [AddressType(virtual_network = 'any')], [PortType(-1, -1)], None)]
        pol_entries = PolicyEntriesType(np_rules)
        pol_entries_dict = \
            json.loads(json.dumps(pol_entries,
                            default=lambda o: {k:v for k, v in o.__dict__.iteritems()}))
        import pdb; pdb.set_trace()
        policy_req = {'name': 'pol1',
                      'entries': pol_entries_dict}
        
        policy_rsp = self._quantum.create_policy({'policy': policy_req})
        policy1_fq_name = policy_rsp['policy']['fq_name']
        policy1_id = policy_rsp['policy']['id']

        print "Reading policy pol1"
        policy_rsp = self._quantum.show_policy(policy1_id)
        self.assertEqual(len(policy_rsp['policy']['entries']), 1)

        print "Updating policy pol1"
        np_rules = [PolicyRuleType(None, '->', 'deny', 'any',
                        [AddressType(virtual_network = 'local')], [PortType(-1, -1)], None,
                        [AddressType(virtual_network = 'any')], [PortType(-1, -1)], None)]
        pol_entries = PolicyEntriesType(np_rules)
        pol_entries_dict = \
            json.loads(json.dumps(pol_entries,
                            default=lambda o: {k:v for k, v in o.__dict__.iteritems()}))
        policy_req = {'entries': pol_entries_dict}
        policy_rsp = self._quantum.update_policy(policy1_id, {'policy': policy_req})
    #end test_policy

    def _test_policy_link_vns(self):
        print "Creating network VN1, subnet 10.1.1.0/24"
        net_req = {'name': 'vn1'}
        net_rsp = self._quantum.create_network({'network': net_req})
        net1_id = net_rsp['network']['id']
        net1_fq_name = net_rsp['network']['contrail:fq_name']
        net1_fq_name_str = ':'.join(net1_fq_name)
        self._create_subnet(u'10.1.1.0/24', net1_id)

        print "Creating network VN2, subnet 20.1.1.0/24"
        net_req = {'name': 'vn2'}
        net_rsp = self._quantum.create_network({'network': net_req})
        net2_id = net_rsp['network']['id']
        net2_fq_name = net_rsp['network']['contrail:fq_name']
        net2_fq_name_str = ':'.join(net2_fq_name)
        self._create_subnet(u'20.1.1.0/24', net2_id)

        print "Creating policy pol1"
        np_rules = [PolicyRuleType(None, '<>', 'pass', 'any',
                        [AddressType(virtual_network = 'local')], [PortType(-1, -1)], None,
                        [AddressType(virtual_network = net2_fq_name_str)], [PortType(-1, -1)], None)]
        pol_entries = PolicyEntriesType(np_rules)
        pol_entries_dict = \
            json.loads(json.dumps(pol_entries,
                            default=lambda o: {k:v for k, v in o.__dict__.iteritems()}))
        policy_req = {'name': 'pol1',
                      'entries': pol_entries_dict}
        
        policy_rsp = self._quantum.create_policy({'policy': policy_req})
        policy1_fq_name = policy_rsp['policy']['fq_name']
        
        print "Creating policy pol2"
        np_rules = [PolicyRuleType(None, '<>', 'pass', 'any',
                        [AddressType(virtual_network = 'local')], [PortType(-1, -1)], None,
                        [AddressType(virtual_network = net1_fq_name_str)], [PortType(-1, -1)], None)]
        pol_entries = PolicyEntriesType(np_rules)
        pol_entries_dict = \
            json.loads(json.dumps(pol_entries,
                            default=lambda o: {k:v for k, v in o.__dict__.iteritems()}))
        policy_req = {'name': 'pol2',
                      'entries': pol_entries_dict}
        
        policy_rsp = self._quantum.create_policy({'policy': policy_req})
        policy2_fq_name = policy_rsp['policy']['fq_name']
        
        print "Setting VN1 policy to [pol1]"
        net_req = {'contrail:policys': [policy1_fq_name]}
        net_rsp = self._quantum.update_network(net1_id, {'network': net_req})
        
        print "Setting VN2 policy to [pol2]"
        net_req = {'contrail:policys': [policy2_fq_name]}
        net_rsp = self._quantum.update_network(net2_id, {'network': net_req})
        
        # Operational (interface directly with vnc-lib)
        # TODO go thru quantum in future
        #instance_id = str(uuid.uuid4())
        #port_req = {'network_id': net1_id, 'tenant_id': 'test-tenant',
        #            'device_id': instance_id,
        #            'compute_node_id': 'test-server'}
        #port_rsp = self._quantum.create_port({'port': port_req})
        #port_id = port_rsp['port']['id']

        #port_rsp = self._quantum.list_ports(device_id = [instance_id])
        #self.assertIn(port_id, [port['id'] for port in port_rsp['ports']])

    #end test_policy_link_vns

    def _create_subnet(self, cidr, net_id, ipam_fq_name = None):
        if not ipam_fq_name:
            ipam_fq_name = NetworkIpam().get_fq_name()

        subnet_req = {'network_id': net_id,
                      'cidr': cidr,
                      'ip_version': 4,
                      'contrail:ipam_fq_name': ipam_fq_name}
        subnet_rsp = self._quantum.create_subnet({'subnet': subnet_req})
        subnet_cidr = subnet_rsp['subnet']['cidr']
        self.assertEqual(subnet_cidr, cidr)
        return subnet_rsp['subnet']['id']
    #end _create_subnet

#end class CRUDTestCase

class TestBench(Service):
    def __init__(self):
        self._ifmap_server = None
        self._quantum_server = None
    #end __init__

    def do_start(self):
        self.spawn(self.launch_ifmap_server)
        self.spawn(self.launch_api_server)
        self.spawn(self.launch_quantum_plugin)
        self.spawn(self.launch_schema_transformer)
        #self.spawn(self.launch_bgp_server)
        self.spawn(self.launch_unit_tests)
    #end do_start

    def do_reload(self):
        import pdb; pdb.set_trace()
    #end do_reload

    def do_stop(self):
        if self._ifmap_server:
            self._ifmap_server.kill()
        if self._quantum_server:
            self._quantum_server.kill()
    #end do_stop

    def launch_ifmap_server(self):
        self._ensure_port_not_listened(IFMAP_SVR_IP, IFMAP_SVR_PORT)
        logf_out = open('ifmap-server.out', 'w')
        logf_err = open('ifmap-server.err', 'w')
        maps = subprocess.Popen(['java', '-jar', 'build/irond.jar'],
                                cwd=IFMAP_SVR_LOC, stdout = None, stderr = None) 
        self._ifmap_server = maps
    #end launch_ifmap_server

    def launch_api_server(self):
        self._ensure_port_not_listened(API_SVR_IP, API_SVR_PORT)
        # Wait for IFMAP server to be running before launching api server
        self._block_till_port_listened('ifmap-server', IFMAP_SVR_IP, IFMAP_SVR_PORT)

        args_str = '%s %s %s %s %s %s' %(IFMAP_SVR_IP,
                                         IFMAP_SVR_PORT,
                                         IFMAP_SVR_USER,
                                         IFMAP_SVR_PASSWD,
                                         CASS_SVR_IP,
                                         CASS_SVR_PORT)
        vnc_cfg_api_server.main(args_str)
    #end launch_api_server

    def launch_quantum_plugin(self):
        self._ensure_port_not_listened(QUANTUM_SVR_IP, QUANTUM_SVR_PORT)
        # Wait for API server to be running before launching Q plugin
        self._block_till_port_listened('api-server', API_SVR_IP, API_SVR_PORT)

        quantum_server = subprocess.Popen([QUANTUM_SVR_LOC + '/bin/quantum-server',
                                           '--config-file=quantum.conf',
                                           '--config-file=contrail_plugin.ini'])
        self._quantum_server = quantum_server
    #end launch_quantum_plugin

    def launch_schema_transformer(self):
        # Wait for API server to be running before launching schema tranformer
        self._block_till_port_listened('api-server', API_SVR_IP, API_SVR_PORT)

        schema_transformer = subprocess.Popen(['python', 'to_bgp.py',
                                               IFMAP_SVR_IP, IFMAP_SVR_PORT,
                                               IFMAP_SVR_USER2, IFMAP_SVR_PASSWD2,
                                               API_SVR_IP, API_SVR_PORT,
                                               ZK_SVR_IP, ZK_SVR_PORT],
                                              cwd = SCHEMA_TRANSFORMER_LOC)
        self._schema_transformer = schema_transformer
    #end launch_schema_transformer

    def launch_bgp_server(self):
        # Wait for IFMAP server to be running before launching bgp server 
        self._block_till_port_listened('ifmap-server', IFMAP_SVR_IP, IFMAP_SVR_PORT)

        bgp_server = subprocess.Popen([ './build/debug/bgp/control-node',
            '--map-server-url', 'https://%s:%s' %(IFMAP_SVR_IP, IFMAP_SVR_PORT),
            '--map-user', IFMAP_SVR_USER3, '--map-password', IFMAP_SVR_PASSWD3,
            '--bgp-port', BGP_SVR_PORT, '--sandesh-port', BGP_SANDESH_PORT],
            cwd = BGP_SVR_ROOT, env = {'LD_LIBRARY_PATH': '%s/build/lib' %(BGP_SVR_ROOT)})
        self._bgp_server = bgp_server
    #end launch_bgp_server

    def launch_unit_tests(self):
        self._block_till_port_listened('quantum-server', QUANTUM_SVR_IP,
                                                         QUANTUM_SVR_PORT)
 
        del sys.argv[1:]
        suite1 = unittest.TestLoader().loadTestsFromTestCase(CRUDTestCase)
        #all_tests = unittest.TestSuite([suite1])
        #unittest.main(defaultTest=all_tests)
        unittest.TextTestRunner(verbosity=2).run(suite1)
    #end launch_unit_tests

    def _ensure_port_not_listened(self, server_ip, server_port):
        try:
            s = socket.create_connection((server_ip, server_port))
            s.close()
            raise Exception("IP %s port %d already listened on" 
                             %(server_ip, server_port))
        except Exception as err:
            if err.errno == errno.ECONNREFUSED:
                return # all is well
    #end _ensure_port_not_listened

    def _block_till_port_listened(self, server_name, server_ip, server_port):
        svr_running = False
        while not svr_running:
            try:
                s = socket.create_connection((server_ip, server_port))
                s.close()
                svr_running = True
            except Exception as err:
                if err.errno == errno.ECONNREFUSED:
                    print "%s not up, retrying in 2 secs" %(server_name)
                    time.sleep(2)
                else:
                    import pdb; pdb.set_trace()
    #end _block_till_port_listened

#end Class TestBench
