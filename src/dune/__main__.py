import os   # path
import sys  # sys.exit()

from args import arg_parser
from args import parse_optional
from dune import dune
from dune import dune_error
from dune import dune_node_not_found
from dune import node
from dune import version_full

def handle_version():
    print("DUNE " + version_full())

def handle_simple_args():
    # Handle args that do not require docker started up
    if args.version is True:
        handle_version()
        sys.exit(0)

if __name__ == '__main__':

    parser = arg_parser()

    args = parser.parse()

    handle_simple_args()

    dune_sys = dune(args)

    if parser.is_forwarding():
        dune_sys.execute_interactive_cmd(parser.get_forwarded_args())
    else:

        try:
            if args.start is not None:
                n: object
                if args.config is None:
                    n = node(args.start[0])
                elif len(args.config) == 1:
                    cfg_temp = args.config[0]
                    if not os.path.exists(cfg_temp):
                        parser.exit_with_help_message("--config: config.ini unknown path\n",
                                                       "bad value: ", cfg_temp)
                    if os.path.isdir(cfg_temp):
                        cfg_temp = os.path.join(cfg_temp, "config.ini")
                    if os.path.split(cfg_temp)[1] != "config.ini":
                        parser.exit_with_help_message("--config: config must either be a config.ini"
                                                      "file or a path containg one\n"
                                                      "bad value: ", cfg_temp)
                    if not os.path.exists(cfg_temp):
                        parser.exit_with_help_message("--config: config.ini file must exist\n"
                                                      "bad value: ", cfg_temp)
                    n = node(args.start[0], dune_sys.docker.abs_host_path(cfg_temp))
                else:
                    parser.exit_with_help_message("--start / --config error")
                dune_sys.start_node(n)

            elif args.config is not None:
                parser.exit_with_help_message("--config without --start")

            elif args.remove is not None:
                dune_sys.remove_node(node(args.remove))

            elif args.destroy_container:
                dune_sys.destroy()

            elif args.stop_container:
                dune_sys.stop_container()

            elif args.start_container:
                dune_sys.start_container()

            elif args.stop is not None:
                dune_sys.stop_node(node(args.stop))

            elif args.list:
                dune_sys.list_nodes()

            elif args.simple_list:
                dune_sys.list_nodes(True)

            elif args.set_active is not None:
                dune_sys.set_active(node(args.set_active))

            elif args.get_active:
                print(dune_sys.get_active())

            elif args.monitor:
                dune_sys.monitor()

            elif args.export_wallet:
                dune_sys.export_wallet()

            elif args.import_wallet is not None:
                dune_sys.import_wallet(args.import_wallet)

            elif args.export_node is not None:
                dune_sys.export_node(node(args.export_node[0]),
                                     args.export_node[1])

            elif args.import_node is not None:
                dune_sys.import_node(args.import_node[0],
                                     node(args.import_node[1]))

            elif args.import_dev_key is not None:
                dune_sys.import_key(args.import_dev_key)

            elif args.create_key:
                print(dune_sys.create_key())

            elif args.create_account is not None:
                if len(args.create_account) > 2:
                    dune_sys.create_account(args.create_account[0],
                                            args.create_account[1],
                                            args.create_account[2],
                                            args.create_account[3])
                elif len(args.create_account) > 1:
                    dune_sys.create_account(args.create_account[0],
                                            args.create_account[1])
                else:
                    dune_sys.create_account(args.create_account[0])

            elif args.create_cmake_app is not None:
                dune_sys.init_project(args.create_cmake_app[0],
                                      dune_sys.docker.abs_host_path(
                                          args.create_cmake_app[1]), True)

            elif args.create_bare_app is not None:
                dune_sys.init_project(args.create_bare_app[0],
                                      dune_sys.docker.abs_host_path(
                                          args.create_bare_app[1]),
                                      False)

            elif args.cmake_build is not None:
                dune_sys.build_cmake_proj(args.cmake_build[0],
                                          parse_optional(args.remainder))

            elif args.ctest is not None:
                dune_sys.ctest_runner(args.ctest[0],
                                      parse_optional(args.remainder))

            elif args.gdb is not None:
                dune_sys.gdb(args.gdb[0], parse_optional(args.remainder))

            elif args.deploy is not None:
                dune_sys.deploy_contract(
                    dune_sys.docker.abs_host_path(args.deploy[0]),
                    args.deploy[1])

            elif args.set_bios_contract is not None:
                dune_sys.deploy_contract(
                    '/app/reference-contracts/build/contracts/eosio.bios',
                    args.set_bios_contract)

            elif args.set_core_contract is not None:
                dune_sys.deploy_contract(
                    '/app/reference-contracts/build/contracts/eosio.system',
                    args.set_core_contract)

            elif args.set_token_contract is not None:
                dune_sys.deploy_contract(
                    '/app/reference-contracts/build/contracts/eosio.token',
                    args.set_token_contract)

            elif args.bootstrap_system:
                dune_sys.bootstrap_system(False)

            elif args.bootstrap_system_full:
                dune_sys.bootstrap_system(True)

            elif args.activate_feature is not None:
                dune_sys.activate_feature(args.activate_feature, True)

            elif args.list_features:
                for f in dune_sys.features():
                    print(f)

            elif args.send_action is not None:
                dune_sys.send_action(args.send_action[1], args.send_action[0],
                                     args.send_action[2], args.send_action[3])

            elif args.get_table is not None:
                dune_sys.get_table(args.get_table[0], args.get_table[1],
                                   args.get_table[2])

            elif args.upgrade:
                dune_sys.docker.upgrade()

            elif args.leap:
                dune_sys.execute_cmd(['sh', 'bootstrap_leap.sh', args.leap])

            elif args.cdt:
                dune_sys.execute_cmd(['sh', 'bootstrap_cdt.sh', args.cdt])

            elif args.version_all:
                handle_version()
                dune_sys.execute_interactive_cmd(['apt','list','leap'])
                dune_sys.execute_interactive_cmd(['apt','list','cdt'])

        except KeyboardInterrupt:
            pass
        except dune_node_not_found as err:
            print('Node not found [' + err.name() + ']', file=sys.stderr)
            sys.exit(1)
        except dune_error as err:
            print("Internal Error", file=sys.stderr)
            sys.exit(1)
