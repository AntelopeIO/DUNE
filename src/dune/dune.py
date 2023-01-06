# pylint: disable=missing-function-docstring, missing-module-docstring
import os
import sys                      # sys.stderr
from context import context
from docker import docker
from node_state import node_state

# VERSION INFORMATION
def version_major():
    return 1


def version_minor():
    return 0


def version_patch():
    return 0


def version_suffix():
    return ""


def version_full():
    main_version = "v" + str(version_major()) + "." + str(
        version_minor()) + "." + str(version_patch())
    if version_suffix() == "":
        return main_version
    return main_version + "." + version_suffix()


class dune_error(Exception):
    pass


class dune_node_not_found(dune_error):
    _name = ""

    def __init__(self, n):
        self._name = n

    def name(self):
        return self._name


class node:
    _name = ""
    _cfg = ""

    def __init__(self, name, cfg=None):
        self._name = name
        self._cfg = cfg

    def name(self):
        return self._name

    def config(self):
        return self._cfg

    def set_config(self, cfg):
        self._cfg = cfg

    def data_dir(self):
        return '/app/nodes/' + self.name()

    def config_dir(self):
        return '/app/nodes/' + self.name()


class dune:
    _docker = None
    _wallet_pw = None
    _context = None
    _cl_args = None
    _token_priv_key = "5JPJoZXizFVi19wHkboX5fwwEU2jZVvtSJpQkQu3uqgNu8LNdQN"
    _token_pub_key = "EOS6v86d8DAxjfGu92CLrnEzq7pySpVWYV2LjaxPaDJJvyf9Vpx5R"

    def __init__(self, cl_args):
        self._cl_args = cl_args
        self._docker = docker('dune_container', 'dune:latest', cl_args)
        self._wallet_pw = self.get_wallet_pw()
        self._context = context(self._docker)

    def node_exists(self, nod):
        return self._docker.dir_exists('/app/nodes/' + nod.name())

    def is_node_running(self, nod):
        return self._docker.find_pid('/app/nodes/' + nod.name() + ' ') != -1

    def set_active(self, nod):
        if self.node_exists(nod):
            self._context.set_active(nod)
        else:
            raise dune_node_not_found(nod.name())

    def get_active(self):
        return self._context.get_active()

    def create_node(self, nod):
        print("Creating node [" + nod.name() + "]")
        self._docker.execute_cmd(['mkdir', '-p', nod.data_dir()])

    def start_node(self, nod, snapshot=None):
        stdout, stderr, exit_code = self._docker.execute_cmd(['ls', '/app/nodes'])

        if self.is_node_running(nod):
            print("Node [" + nod.name() + "] is already running.")
            return

        cmd = ['sh', 'start_node.sh', nod.data_dir(), nod.config_dir()]

        if snapshot is not None:
            cmd = cmd + ['--snapshot /app/nodes/' + nod.name() + '/snapshots/' + snapshot + ' -e']
        else:
            cmd = cmd + [' ']

        # if node name is not found we need to create it
        is_restart=True
        if not nod.name() in stdout:
            is_restart=False
            self.create_node(nod)

        # copy config.ini to config-dir
        if not is_restart and nod.config() is None:
            nod.set_config('/app/config.ini')

        if nod.config() is not None:
            self._docker.execute_cmd(['cp', nod.config(), nod.config_dir()])
            print("Using Configuration [" + nod.config() + "]")

        ctx = self._context.get_ctx()
        cfg_args = self._context.get_config_args(nod)

        if self.node_exists(node(ctx.active)):
            if cfg_args[0] == ctx.http_port:
                print("Currently active node [" + ctx.active + "] http port is the same as this nodes [" + nod.name() + "]")
                self.stop_node(node(ctx.active))
            elif cfg_args[1] == ctx.p2p_port:
                print("Currently active node [" + ctx.active + "] p2p port is the same as this nodes [" + nod.name() + "]")
                self.stop_node(node(ctx.active))
            elif cfg_args[2] == ctx.ship_port:
                print("Currently active node [" + ctx.active + "] ship port is the same as this nodes [" + nod.name() + "]")
                self.stop_node(node(ctx.active))

        stdout, stderr, exit_code = self._docker.execute_cmd(cmd + [nod.name()])

        if exit_code == 0:
            self.set_active(nod)
            print("Active [" + nod.name() + "]")
            print(stdout)
            print(stderr)
        else:
            print(stderr)

    def cleos_cmd(self, cmd, quiet=True):
        self.unlock_wallet()
        ctx = self._context.get_ctx()
        if quiet:
            return self._docker.execute_cmd(
                ['cleos', '--verbose', '-u', 'http://' + ctx.http_port] + cmd)
        return self._docker.execute_cmd2(
            ['cleos', '--verbose', '-u', 'http://' + ctx.http_port] + cmd)

    def monitor(self):
        stdout, stderr, exit_code = self.cleos_cmd(['get', 'info'])
        print(stdout)
        if exit_code != 0:
            print(stderr)
            raise dune_error

    def stop_node(self, nod):
        if self.node_exists(nod):
            if self.is_node_running(nod):
                pid = self._docker.find_pid(
                    '/app/nodes/' + nod.name() + ' ')
                print("Stopping node [" + nod.name() + "]")
                self._docker.execute_cmd(['kill', pid])
            else:
                print("Node [" + nod.name() + "] is not running")
        else:
            raise dune_node_not_found(nod.name())

    def remove_node(self, nod):
        self.stop_node(nod)
        print("Removing node [" + nod.name() + "]")
        self._docker.execute_cmd(
            ['rm', '-rf', '/app/nodes/' + nod.name()])

    def destroy(self):
        self._docker.destroy()

    def stop_container(self):
        stdout, stderr, exit_code = self._docker.execute_cmd(
            ['ls', '/app/nodes'])
        for string in stdout.split():
            if self.is_node_running(node(string)):
                self.stop_node(node(string))

        self._docker.stop()

    def start_container(self):
        self._docker.start()


    def state_list(self):
        # [(node_name, active, running, ports),...]
        rv=[]
        stdout, stderr, exit_code = self._docker.execute_cmd(['ls', '/app/nodes'])
        ctx = self._context.get_ctx()
        for node_name in stdout.split():
            active = False
            if node_name == ctx.active:
                active=True
            running = self.is_node_running(node(node_name))
            addrs = self._context.get_config_args(node(node_name))
            rv.append( node_state(node_name, active, running, addrs[0], addrs[1], addrs[2]) )
        return rv


    # pylint: disable=too-many-branches
    def list_nodes(self, simple=False, sep='|'):

        buffer = 3
        node_name = "Node Name"

        states=self.state_list()
        name_width = len(node_name) + buffer
        if not simple:
            for state in states:
                name_width = max( len(state.name) + buffer, name_width)

        if simple:
            print("Node|Active|Running|HTTP|P2P|SHiP")
        else:
            header = '| Active? | Running? | HTTP           | P2P          | SHiP          '
            print(f'{node_name : <{name_width}}{header}')
            print(f'{"":{"-"}<{name_width + len(header)}}')

        for state in states:
            print( state.string(sep=sep, simple=simple, name_width=name_width) )

    # pylint: disable=too-many-locals,too-many-statements
    def export_node(self, nod, path):
        # Sanity check
        if not self.node_exists(nod):
            raise dune_node_not_found(nod.name())

        ctx = self._context.get_ctx()

        is_active=nod.name() == ctx.active
        is_running=self.is_node_running(nod)
        my_addrs=self._context.get_config_args(nod)

        was_running=[]
        was_active=None

        initial_states=[]

        if not is_active or not is_running:
            # Get the current states.
            initial_states=self.state_list()

            # For each state, make decisions based on it's
            for state in initial_states:
                # Don't operate on our node.
                if state.name == nod.name():
                    continue
                if state.is_active:
                    was_active = state.name
                if state.is_running:
                    # We only need to stop a running node if there are address collisions.
                    if state.http in my_addrs or state.p2p in my_addrs or state.ship in my_addrs:
                        was_running.append(state.name)
                        self.stop_node(node(state.name))
                        print("\t", state.name, "was stopped due to address collision.")

        # Get this node ready for export.
        if not is_active:
            self.set_active(nod)
        if not is_running:
            self.start_node(nod)


        # Paths:
        directory=path
        filename=nod.name()+".tgz"

        # Update paths based on input.
        if os.path.splitext(path)[1].lower() == ".tgz":
            directory=os.path.split(path)[0]
            filename=os.path.split(path)[1]

        # Ensure the directory is absolute and it exists.
        directory=os.path.realpath(directory)
        if not os.path.exists(directory):
            os.makedirs(directory)

        # Determine the final full path.
        fullpath=os.path.join(directory,filename)

        src_path='/app/nodes/' + nod.name()
        dst_path='/app/tmp/' + nod.name()


        print("Exporting data from node [" + nod.name() + "] to location " + fullpath)

        # Create the snapshot
        self.create_snapshot()
        # Stop the node for copy.
        self.stop_node(nod)

        self._docker.execute_cmd(['mkdir', '-p', dst_path])
        self._docker.execute_cmd(['cp', '-R', src_path + '/blocks', dst_path + '/blocks'])
        self._docker.execute_cmd(['cp', src_path + '/config.ini', dst_path + '/config.ini'])
        self._docker.execute_cmd(['cp', '-R', src_path + '/protocol_features', dst_path + '/protocol_features'])
        self._docker.execute_cmd(['cp', '-R', src_path + '/snapshots', dst_path + '/snapshots'])

        self._docker.tar_dir(nod.name(), 'tmp/' + nod.name())
        self._docker.cp_to_host('/app/' + nod.name() + '.tgz', fullpath)
        self._docker.rm_file('/app/' + nod.name() + '.tgz')
        self._docker.rm_file(dst_path)

        # Restore previously active node.
        if not is_active and was_active is not None:
            self.set_active(node(was_active))

        # Restart the node if necessary.
        if is_running:
            self.start_node(nod)

        # Restart any nodes that were previously running.
        for old_runner in was_running:
            self.start_node(node(old_runner))


    def import_node(self, path, nod):

        # Sanity check path
        if not os.path.exists(path):
            print("File not found: ", path, file=sys.stderr)
            raise dune_error
        if os.path.splitext(path)[1].lower() != ".tgz":
            print("Path extension must be `.tgz`: ", path, file=sys.stderr)
            raise dune_error

        print("Importing node data [" + nod.name() + "]")

        # If the node already exists we delete it.
        if self.node_exists(nod):
            self.remove_node(nod)

        # Copy the tgz file.
        stdout, stderr, exit_code = self._docker.cp_from_host(path, '/app/tmp.tgz')
        if exit_code != 0:
            print(stderr)
            raise dune_error

        # Clean up the tmp file, untar, and remove the file.
        self._docker.rm_file('/app/tmp') # remove any existing file
        self._docker.untar('/app/tmp.tgz')
        self._docker.rm_file('/app/tmp.tgz')

        # Find the path inside temp of the import data.
        stdout, stderr, exit_code = self._docker.execute_cmd(['ls', '/app/tmp'])
        src_name=stdout.split()[0]
        src_path='/app/tmp/' + src_name

        # Calculate and create the destination path.
        dst_path='/app/nodes/' + nod.name()
        self._docker.execute_cmd(['mkdir', '-p', dst_path + '/blocks'])

        # Move data to the destination.
        self._docker.execute_cmd(['mv', src_path + '/blocks/blocks.index', dst_path + '/blocks/blocks.index'])
        self._docker.execute_cmd(['mv', src_path + '/blocks/blocks.log',   dst_path + '/blocks/blocks.log'])
        self._docker.execute_cmd(['mv', src_path + '/config.ini',          dst_path + '/config.ini'])
        self._docker.execute_cmd(['mv', src_path + '/protocol_features',   dst_path + '/protocol_features'])
        self._docker.execute_cmd(['mv', src_path + '/snapshots',           dst_path + '/snapshots'])
        # Clean up the temp.
        self._docker.rm_file('/app/tmp')

        # Ensure a snapshot exists
        stdout, stderr, exit_code = self._docker.execute_cmd(['ls', dst_path + '/snapshots'])
        if len(stdout) == 0:
            print('No snapshot found for ', nod.name(), ' sourced from: \n\t', path, file=sys.stderr)
            raise dune_error

        # Start and activate the node...
        self.start_node(nod, stdout.split()[0])
        self.set_active(nod)

    def get_wallet_pw(self):
        stdout, stderr, exit_code = self._docker.execute_cmd(['cat', '.wallet.pw'])
        return stdout

    def unlock_wallet(self):
        stdout, stderr, exit_code = self._docker.execute_cmd(
            ['cleos', 'wallet', 'unlock', '--password', self.get_wallet_pw()])

    def import_key(self, key):
        self.unlock_wallet()
        return self.cleos_cmd(['wallet', 'import', '--private-key', key])

    def create_key(self):
        stdout, stderr, exit_code = self.cleos_cmd(['create', 'key', '--to-console'])
        return stdout

    def export_wallet(self):
        self._docker.execute_cmd(['mkdir', '/app/_wallet'])
        self._docker.execute_cmd(['cp', '-R', '/root/eosio-wallet/', '/app/_wallet/eosio-wallet'])
        self._docker.execute_cmd(['cp', '-R', '/app/.wallet.pw', '/app/_wallet/.wallet.pw'])
        self._docker.tar_dir("wallet", "_wallet")
        self._docker.cp_to_host("/app/wallet.tgz", "wallet.tgz")

    def import_wallet(self, path):
        self._docker.cp_from_host(path, "/app/wallet.tgz")
        self._docker.untar("/app/wallet.tgz")
        self._docker.execute_cmd(["mv", "/app/_wallet/.wallet.pw", "/app"])
        self._docker.execute_cmd(["cp", "-R", "/app/_wallet/eosio-wallet/", "/root"])
        self._docker.execute_cmd(["rm", "-R", "/app/_wallet/"])
        self._docker.execute_cmd(["rm", "/app/wallet.tgz"])

    # pylint: disable=fixme
    # TODO cleos has a bug displaying keys for K1 so, we need the public key
    #  if providing the private key
    # Remove that requirement when we fix cleos.
    def create_account(self, name, creator=None, pub=None, private=None):
        if private is None:
            keys = self.create_key()
            private = keys.splitlines()[0].split(':')[1][1:]
            pub = keys.splitlines()[1].split(':')[1][1:]
            print(
                "Creating account [" + name + "] with key pair [Private: " +
                private + ", Public: " + pub + "]")

        if creator is None:
            stdout, stderr, exit_code = self.cleos_cmd(
                ['create', 'account', 'eosio', name, pub])
        else:
            stdout, stderr, exit_code = self.cleos_cmd(
                ['create', 'account', creator, name, pub])
        self.import_key(private)
        print(stderr)

    def execute_cmd(self, args):
        self._docker.execute_cmd2(args)

    def execute_cmd_at(self, args, at_dir):
        self._docker.execute_cmd_at(args, at_dir)

    def execute_interactive_cmd(self, args):
        self._docker.execute_interactive_cmd(args)

    def build_cmake_proj(self, directory, flags):
        container_dir = self._docker.abs_host_path(directory)
        build_dir = container_dir + '/build'
        if not self._docker.dir_exists(build_dir):
            self._docker.execute_cmd(['mkdir', '-p', build_dir])
        self._docker.execute_cmd2(
            ['cmake', '-S', container_dir, '-B', build_dir] + flags)
        self._docker.execute_cmd2(['cmake', '--build', build_dir])

    def ctest_runner(self, directory, flags):
        container_dir = self._docker.abs_host_path(directory)
        self._docker.execute_cmd_at(container_dir, ['ctest'] + flags)

    def gdb(self, executable, flags):
        container_exec = self._docker.abs_host_path(executable)
        self._docker.execute_interactive_cmd(['gdb', container_exec] + flags)

    def build_other_proj(self, cmd):
        self._docker.execute_cmd2([cmd])

    def init_project(self, name, directory, cmake=True):
        if cmake:
            bare = []
        else:
            bare = ["--bare"]

        stdout, stderr, exit_code = self._docker.execute_cmd(
            ['cdt-init', '-project', name, '-path', directory] + bare)
        if exit_code != 0:
            print(stdout)
            raise dune_error()

    def create_snapshot(self):
        ctx = self._context.get_ctx()
        url = "http://" + ctx.http_port + "/v1/producer/create_snapshot"
        stdout, stderr, exit_code = self._docker.execute_cmd(['curl', '-X', 'POST', url])
        print(stdout)
        print(stderr)
        print(url)

    def deploy_contract(self, directory, acnt):
        self.cleos_cmd(
            ['set', 'account', 'permission', acnt, 'active', '--add-code'])
        stdout, stderr, exit_code = self.cleos_cmd(
            ['set', 'contract', acnt, directory])

        if exit_code == 0:
            print(stdout)
        else:
            print(stderr)
            raise dune_error()

    def preactivate_feature(self):
        ctx = self._context.get_ctx()
        stdout, stderr, exit_code = \
            self._docker.execute_cmd(
                ['curl', '--noproxy', '-x', 'POST',
                 ctx.http_port +
                 '/v1/producer/schedule_protocol_feature_activations',
                 '-d',
                 '{"protocol_features_to_activate": ['
                 '"0ec7e080177b2c02b278d5088611686b49'
                 'd739925a92d9bfcacd7fc6b74053bd"]}'])

        if exit_code != 0:
            print(stderr)
            raise dune_error()
        print("Preactivate Features: " + stdout)

    def send_action(self, action, acnt, data, permission='eosio@active'):
        self.cleos_cmd(
            ['push', 'action', acnt, action, data, '-p', permission], False)

    def get_table(self, acnt, scope, tab):
        self.cleos_cmd(['get', 'table', acnt, scope, tab], False)

    @staticmethod
    def features():
        return ["KV_DATABASE",
                "ACTION_RETURN_VALUE",
                "CONFIGURABLE_WASM_LIMITS2",
                "BLOCKCHAIN_PARAMETERS",
                "GET_SENDER",
                "FORWARD_SETCODE",
                "ONLY_BILL_FIRST_AUTHORIZER",
                "RESTRICT_ACTION_TO_SELF",
                "DISALLOW_EMPTY_PRODUCER_SCHEDULE",
                "FIX_LINKAUTH_RESTRICTION",
                "REPLACE_DEFERRED",
                "NO_DUPLICATE_DEFERRED_ID",
                "ONLY_LINK_TO_EXISTING_PERMISSION",
                "RAM_RESTRICTIONS",
                "WEBAUTHN_KEY",
                "WTMSIG_BLOCK_SIGNATURES"]

    def activate_feature(self, code_name, preactivate=False):
        if preactivate:
            self.preactivate_feature()
            self.deploy_contract(
                '/app/reference-contracts/build/contracts/eosio.boot', 'eosio')

        if code_name == "KV_DATABASE":
            self.send_action(
                'activate',
                'eosio',
                '["825ee6288fb1373eab1b5187ec2f04f6ea'
                'cb39cb3a97f356a07c91622dd61d16"]',
                'eosio@active')
        elif code_name == "ACTION_RETURN_VALUE":
            self.send_action('activate', 'eosio',
                             '["c3a6138c5061cf291310887c0b5c71'
                             'fcaffeab90d5deb50d3b9e687cead45071"]',
                             'eosio@active')
        elif code_name == "CONFIGURABLE_WASM_LIMITS2":
            self.send_action('activate', 'eosio',
                             '["d528b9f6e9693f45ed277af93474fd47'
                             '3ce7d831dae2180cca35d907bd10cb40"]',
                             'eosio@active')
        elif code_name == "BLOCKCHAIN_PARAMETERS":
            self.send_action('activate', 'eosio',
                             '["5443fcf88330c586bc0e5f3dee10e7f'
                             '63c76c00249c87fe4fbf7f38c082006b4"]',
                             'eosio@active')
        elif code_name == "GET_SENDER":
            self.send_action('activate', 'eosio',
                             '["f0af56d2c5a48d60a4a5b5c903edfb7db3a'
                             '736a94ed589d0b797df33ff9d3e1d"]',
                             'eosio@active')
        elif code_name == "FORWARD_SETCODE":
            self.send_action('activate', 'eosio',
                             '["2652f5f96006294109b3dd0bbde63693f'
                             '55324af452b799ee137a81a905eed25"]',
                             'eosio@active')
        elif code_name == "ONLY_BILL_FIRST_AUTHORIZER":
            self.send_action('activate', 'eosio',
                             '["8ba52fe7a3956c5cd3a656a3174b931d'
                             '3bb2abb45578befc59f283ecd816a405"]',
                             'eosio@active')
        elif code_name == "RESTRICT_ACTION_TO_SELF":
            self.send_action('activate', 'eosio',
                             '["ad9e3d8f650687709fd68f4b90b41f7d8'
                             '25a365b02c23a636cef88ac2ac00c43"]',
                             'eosio@active')
        elif code_name == "DISALLOW_EMPTY_PRODUCER_SCHEDULE":
            self.send_action('activate', 'eosio',
                             '["68dcaa34c0517d19666e6b33add67351d8'
                             'c5f69e999ca1e37931bc410a297428"]',
                             'eosio@active')
        elif code_name == "FIX_LINKAUTH_RESTRICTION":
            self.send_action('activate', 'eosio',
                             '["e0fb64b1085cc5538970158d05a009c24e2'
                             '76fb94e1a0bf6a528b48fbc4ff526"]',
                             'eosio@active')
        elif code_name == "REPLACE_DEFERRED":
            self.send_action('activate', 'eosio',
                             '["ef43112c6543b88db2283a2e077278c315ae'
                             '2c84719a8b25f25cc88565fbea99"]',
                             'eosio@active')
        elif code_name == "NO_DUPLICATE_DEFERRED_ID":
            self.send_action('activate', 'eosio',
                             '["4a90c00d55454dc5b059055ca213579c6ea85'
                             '6967712a56017487886a4d4cc0f"]',
                             'eosio@active')
        elif code_name == "ONLY_LINK_TO_EXISTING_PERMISSION":
            self.send_action('activate', 'eosio',
                             '["1a99a59d87e06e09ec5b028a9cbb7749b4a5ad'
                             '8819004365d02dc4379a8b7241"]',
                             'eosio@active')
        elif code_name == "RAM_RESTRICTIONS":
            self.send_action('activate', 'eosio',
                             '["4e7bf348da00a945489b2a681749eb56f5de00'
                             'b900014e137ddae39f48f69d67"]',
                             'eosio@active')
        elif code_name == "WEBAUTHN_KEY":
            self.send_action('activate', 'eosio',
                             '["4fca8bd82bbd181e714e283f83e1b45d95ca5af'
                             '40fb89ad3977b653c448f78c2"]',
                             'eosio@active')
        elif code_name == "WTMSIG_BLOCK_SIGNATURES":
            self.send_action('activate', 'eosio',
                             '["299dcb6af692324b899b39f16d5a530a3306280'
                             '4e41f09dc97e9f156b4476707"]',
                             'eosio@active')
        else:
            print("Feature Not Found")
            raise dune_error()

    def bootstrap_system(self, full):
        self.preactivate_feature()
        if full:
            # create account for multisig contract
            self.create_account('eosio.msig', 'eosio')
            # create account for token contract
            self.create_account('eosio.token', 'eosio')
            # create accounts needed by core contract
            self.create_account('eosio.bpay', 'eosio')
            self.create_account('eosio.names', 'eosio')
            self.create_account('eosio.ram', 'eosio')
            self.create_account('eosio.ramfee', 'eosio')
            self.create_account('eosio.saving', 'eosio')
            self.create_account('eosio.stake', 'eosio')
            self.create_account('eosio.vpay', 'eosio')
            self.create_account('eosio.rex', 'eosio')

        # activate features
        self.deploy_contract(
            '/app/reference-contracts/build/contracts/eosio.boot', 'eosio')

        for feature in self.features():
            self.activate_feature(feature)

        if full:
            self.deploy_contract(
                '/app/reference-contracts/build/contracts/eosio.msig',
                'eosio.msig')
            self.deploy_contract(
                '/app/reference-contracts/build/contracts/eosio.token',
                'eosio.token')
            self.deploy_contract(
                '/app/reference-contracts/build/contracts/eosio.system',
                'eosio')

    def start_webapp(self, directory):
        # pylint: disable=fixme
        # TODO readdress after the launch
        pass

    @property
    def docker(self):
        return self._docker
